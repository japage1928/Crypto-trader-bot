"""Main orchestration engine for paper trading."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import asyncio
import contextlib
import time
from typing import Any
import yaml
from trading_bot.accounting.balance import AccountBalance
from trading_bot.accounting.pnl_tracker import PnLTracker
from trading_bot.data.market_feed import LiveMarketFeed, MarketFeed
from trading_bot.edge.edge_gate import EdgeGate
from trading_bot.edge.regime_detector import RegimeDetector
from trading_bot.execution.paper_broker import PaperBroker
from trading_bot.logging.metrics import summarize_metrics
from trading_bot.logging.signal_log import get_signal_logger
from trading_bot.logging.trade_log import get_trade_logger
from trading_bot.risk.daily_limits import DailyLimits
from trading_bot.risk.position_sizer import PositionSizer
from trading_bot.risk.trade_limiter import TradeLimiter
from trading_bot.strategy.mean_reversion import MeanReversionStrategy

@dataclass
class EngineConfig:
    raw: dict[str, Any]
    @classmethod
    def from_yaml(cls, path: str | Path) -> "EngineConfig":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(raw=data)

class TradingEngine:
    def __init__(self, config: EngineConfig) -> None:
        cfg = config.raw
        self.market = MarketFeed(seed=cfg["engine"]["seed"])
        self.strategy = MeanReversionStrategy(
            ema_period=cfg["strategy"]["ema_period"],
            entry_deviation_pct=cfg["strategy"]["entry_deviation_pct"],
        )
        self.regime_detector = RegimeDetector(
            volatility_window=cfg["edge"]["volatility_window"],
            volatility_threshold=cfg["edge"]["volatility_threshold"],
            trend_window=cfg["edge"]["trend_window"],
            trend_strength_threshold=cfg["edge"]["trend_strength_threshold"],
            range_ratio_threshold=cfg["edge"]["range_ratio_threshold"],
        )
        self.edge_gate = EdgeGate(
            volatility_threshold=cfg["edge"]["volatility_threshold"],
            trend_strength_threshold=cfg["edge"]["trend_strength_threshold"],
            min_confidence=cfg["edge"]["min_confidence"],
        )
        self.sizer = PositionSizer(
            risk_per_trade_pct=cfg["risk"]["risk_per_trade_pct"],
            min_notional_usdt=cfg["risk"]["min_notional_usdt"],
        )
        self.limits = DailyLimits(
            daily_profit_cap_pct=cfg["risk"]["daily_profit_cap_pct"],
            daily_loss_cap_pct=cfg["risk"]["daily_loss_cap_pct"],
        )
        self.trade_limiter = TradeLimiter(
            max_signals_per_regime=cfg["risk"]["max_signals_per_regime"],
            max_trades_per_day=cfg["risk"]["max_trades_per_day"],
        )
        self.broker = PaperBroker(
            fee_rate=cfg["exchange"]["fee_rate"],
            partial_fill_probability=cfg["execution"]["partial_fill_probability"],
            min_partial_fill_ratio=cfg["execution"]["min_partial_fill_ratio"],
            max_partial_fill_ratio=cfg["execution"]["max_partial_fill_ratio"],
            slippage_bps=cfg["execution"]["slippage_bps"],
            seed=cfg["engine"]["seed"],
        )
        start_usdt = float(cfg["account"]["initial_usdt_balance"])
        self.balance = AccountBalance(usdt_free=start_usdt, btc_free=0.0, day_start_equity=start_usdt)
        self.pnl = PnLTracker(peak_equity=start_usdt)
        self.signal_logger = get_signal_logger()
        self.trade_logger = get_trade_logger()
        self.pair = cfg["exchange"]["pair"]
        self.take_profit_pct = cfg["strategy"]["take_profit_pct"]
        self.stop_loss_pct = cfg["strategy"]["stop_loss_pct"]
        self.max_ticks = int(cfg["engine"]["max_ticks"])
        self.loop_sleep_seconds = float(cfg["engine"]["loop_sleep_seconds"])

    def step(self) -> None:
        """Perform one market cycle (one iteration of the main loop)."""
        candle = self.market.next_candle()
        if not hasattr(self, '_closes'):
            candles = self.market.warmup(60)
            self._closes = [c.close for c in candles]
            self._highs = [c.high for c in candles]
            self._lows = [c.low for c in candles]
        self._closes.append(candle.close)
        self._highs.append(candle.high)
        self._lows.append(candle.low)
        regime = self.regime_detector.classify(self._highs, self._lows, self._closes)
        edge = self.edge_gate.evaluate(regime)
        self.pnl.mark_edge_state(edge.is_on)
        mark_price = candle.close
        equity = self.balance.equity(mark_price)
        self.pnl.update_equity(equity)
        can_trade, limit_reason = self.limits.can_continue(self.balance.day_start_equity, equity)
        if not can_trade:
            self.signal_logger.info("daily_limit_stop reason=%s equity=%.2f", limit_reason, equity)
            return
        exit_fill, exit_reason = self.broker.check_exit(candle.ts, mark_price)
        if exit_fill:
            proceeds = (exit_fill.price * exit_fill.qty) - exit_fill.fee
            self.balance.usdt_free += proceeds
            self.balance.btc_free -= exit_fill.qty
            self.pnl.mark_exit(gross_proceeds=proceeds)
            self.trade_logger.info(
                "exit reason=%s qty=%.6f price=%.2f fee=%.4f usdt=%.2f",
                exit_reason,
                exit_fill.qty,
                exit_fill.price,
                exit_fill.fee,
                self.balance.usdt_free,
            )
        signal = self.strategy.generate(candle.ts, self._closes)
        if signal is None:
            self.signal_logger.info("no_signal ts=%s", candle.ts.isoformat())
            return
        regime_key = f"range={regime.is_range_bound}|vol={regime.volatility:.4f}|trend={regime.trend_strength:.4f}"
        allowed_signal, signal_reason = self.trade_limiter.allow_signal(regime_key)
        if not edge.is_on:
            self.signal_logger.info(
                "skip signal reason=edge_off confidence=%.2f detail=%s",
                edge.confidence,
                edge.reason,
            )
            return
        if not allowed_signal:
            self.signal_logger.info("skip signal reason=%s", signal_reason)
            return
        if self.broker.position is not None:
            self.signal_logger.info("skip signal reason=position_open")
            return
        qty = self.sizer.size(available_usdt=self.balance.usdt_free, price=signal.ref_price)
        if qty <= 0:
            self.signal_logger.info("skip signal reason=insufficient_balance")
            return
        entry_fill = self.broker.try_open_long(
            ts=signal.ts,
            price=signal.ref_price,
            qty=qty,
            pair=self.pair,
            take_profit_pct=self.take_profit_pct,
            stop_loss_pct=self.stop_loss_pct,
        )
        if entry_fill:
            cost = (entry_fill.price * entry_fill.qty) + entry_fill.fee
            self.balance.usdt_free -= cost
            self.balance.btc_free += entry_fill.qty
            self.pnl.mark_entry(gross_cost=cost)
            self.trade_limiter.mark_trade()
            self.trade_logger.info(
                "entry qty=%.6f price=%.2f fee=%.4f partial=%s usdt=%.2f",
                entry_fill.qty,
                entry_fill.price,
                entry_fill.fee,
                entry_fill.is_partial,
                self.balance.usdt_free,
            )
        else:
            self.signal_logger.info("skip signal reason=entry_rejected")

    def shutdown(self) -> None:
        """Gracefully shut down the engine: flush logs, persist metrics, close resources."""
        if hasattr(self, '_closes') and self._closes:
            current_equity = self.balance.equity(self._closes[-1])
        else:
            current_equity = self.balance.equity(0)
        metrics = summarize_metrics(
            pnl=self.pnl,
            day_start_equity=self.balance.day_start_equity,
            current_equity=current_equity,
        )
        print("=== RUN SUMMARY ===")
        for k, v in metrics.items():
            print(f"{k}: {v:.6f}" if isinstance(v, float) else f"{k}: {v}")
        for logger in [self.signal_logger, self.trade_logger]:
            for handler in logger.handlers:
                handler.flush()
        print("Engine shutdown complete.")
        def step(self) -> None:
            """Perform one market cycle (one iteration of the main loop)."""
            # This is adapted from one iteration of the run() method
            candle = self.market.next_candle()
            # Maintain rolling lists for closes, highs, lows
            if not hasattr(self, '_closes'):
                candles = self.market.warmup(60)
                self._closes = [c.close for c in candles]
                self._highs = [c.high for c in candles]
                self._lows = [c.low for c in candles]
            self._closes.append(candle.close)
            self._highs.append(candle.high)
            self._lows.append(candle.low)

            regime = self.regime_detector.classify(self._highs, self._lows, self._closes)
            edge = self.edge_gate.evaluate(regime)
            self.pnl.mark_edge_state(edge.is_on)

            mark_price = candle.close
            equity = self.balance.equity(mark_price)
            self.pnl.update_equity(equity)

            can_trade, limit_reason = self.limits.can_continue(self.balance.day_start_equity, equity)
            if not can_trade:
                self.signal_logger.info("daily_limit_stop reason=%s equity=%.2f", limit_reason, equity)
                return

            exit_fill, exit_reason = self.broker.check_exit(candle.ts, mark_price)
            if exit_fill:
                proceeds = (exit_fill.price * exit_fill.qty) - exit_fill.fee
                self.balance.usdt_free += proceeds
                self.balance.btc_free -= exit_fill.qty
                self.pnl.mark_exit(gross_proceeds=proceeds)
                self.trade_logger.info(
                    "exit reason=%s qty=%.6f price=%.2f fee=%.4f usdt=%.2f",
                    exit_reason,
                    exit_fill.qty,
                    exit_fill.price,
                    exit_fill.fee,
                    self.balance.usdt_free,
                )

            signal = self.strategy.generate(candle.ts, self._closes)
            if signal is None:
                self.signal_logger.info("no_signal ts=%s", candle.ts.isoformat())
                return

            regime_key = f"range={regime.is_range_bound}|vol={regime.volatility:.4f}|trend={regime.trend_strength:.4f}"
            allowed_signal, signal_reason = self.trade_limiter.allow_signal(regime_key)

            if not edge.is_on:
                self.signal_logger.info(
                    "skip signal reason=edge_off confidence=%.2f detail=%s",
                    edge.confidence,
                    edge.reason,
                )
                return

            if not allowed_signal:
                self.signal_logger.info("skip signal reason=%s", signal_reason)
                return

            if self.broker.position is not None:
                self.signal_logger.info("skip signal reason=position_open")
                return

            qty = self.sizer.size(available_usdt=self.balance.usdt_free, price=signal.ref_price)
            if qty <= 0:
                self.signal_logger.info("skip signal reason=insufficient_balance")
                return

            entry_fill = self.broker.try_open_long(
                ts=signal.ts,
                price=signal.ref_price,
                qty=qty,
                pair=self.pair,
                take_profit_pct=self.take_profit_pct,
                stop_loss_pct=self.stop_loss_pct,
            )
            if entry_fill:
                cost = (entry_fill.price * entry_fill.qty) + entry_fill.fee
                self.balance.usdt_free -= cost
                self.balance.btc_free += entry_fill.qty
                self.pnl.mark_entry(gross_cost=cost)
                self.trade_limiter.mark_trade()
                self.trade_logger.info(
                    "entry qty=%.6f price=%.2f fee=%.4f partial=%s usdt=%.2f",
                    entry_fill.qty,
                    entry_fill.price,
                    entry_fill.fee,
                    entry_fill.is_partial,
                    self.balance.usdt_free,
                )
            else:
                self.signal_logger.info("skip signal reason=entry_rejected")

        def shutdown(self) -> None:
            """Perform graceful shutdown: log summary metrics and cleanup."""
            # Summarize and print metrics at shutdown
            if hasattr(self, '_closes') and self._closes:
                current_equity = self.balance.equity(self._closes[-1])
            else:
                current_equity = self.balance.equity(0)
            metrics = summarize_metrics(
                pnl=self.pnl,
                day_start_equity=self.balance.day_start_equity,
                current_equity=current_equity,
            )
            print("=== PAPER RUN SUMMARY ===")
            for k, v in metrics.items():
                print(f"{k}: {v:.6f}" if isinstance(v, float) else f"{k}: {v}")
    """Coordinates feed, strategy, risk, and paper execution modules."""

    def __init__(self, config: EngineConfig) -> None:
        cfg = config.raw

        self.market = MarketFeed(seed=cfg["engine"]["seed"])
        self.strategy = MeanReversionStrategy(
            ema_period=cfg["strategy"]["ema_period"],
            entry_deviation_pct=cfg["strategy"]["entry_deviation_pct"],
        )
        self.regime_detector = RegimeDetector(
            volatility_window=cfg["edge"]["volatility_window"],
            volatility_threshold=cfg["edge"]["volatility_threshold"],
            trend_window=cfg["edge"]["trend_window"],
            trend_strength_threshold=cfg["edge"]["trend_strength_threshold"],
            range_ratio_threshold=cfg["edge"]["range_ratio_threshold"],
        )
        self.edge_gate = EdgeGate(
            volatility_threshold=cfg["edge"]["volatility_threshold"],
            trend_strength_threshold=cfg["edge"]["trend_strength_threshold"],
            min_confidence=cfg["edge"]["min_confidence"],
        )
        self.sizer = PositionSizer(
            risk_per_trade_pct=cfg["risk"]["risk_per_trade_pct"],
            min_notional_usdt=cfg["risk"]["min_notional_usdt"],
        )
        self.limits = DailyLimits(
            daily_profit_cap_pct=cfg["risk"]["daily_profit_cap_pct"],
            daily_loss_cap_pct=cfg["risk"]["daily_loss_cap_pct"],
        )
        self.trade_limiter = TradeLimiter(
            max_signals_per_regime=cfg["risk"]["max_signals_per_regime"],
            max_trades_per_day=cfg["risk"]["max_trades_per_day"],
        )
        self.broker = PaperBroker(
            fee_rate=cfg["exchange"]["fee_rate"],
            partial_fill_probability=cfg["execution"]["partial_fill_probability"],
            min_partial_fill_ratio=cfg["execution"]["min_partial_fill_ratio"],
            max_partial_fill_ratio=cfg["execution"]["max_partial_fill_ratio"],
            slippage_bps=cfg["execution"]["slippage_bps"],
            seed=cfg["engine"]["seed"],
        )

        start_usdt = float(cfg["account"]["initial_usdt_balance"])
        self.balance = AccountBalance(usdt_free=start_usdt, btc_free=0.0, day_start_equity=start_usdt)
        self.pnl = PnLTracker(peak_equity=start_usdt)
        self.signal_logger = get_signal_logger()
        self.trade_logger = get_trade_logger()

        self.pair = cfg["exchange"]["pair"]
        self.take_profit_pct = cfg["strategy"]["take_profit_pct"]
        self.stop_loss_pct = cfg["strategy"]["stop_loss_pct"]
        self.max_ticks = int(cfg["engine"]["max_ticks"])
        self.loop_sleep_seconds = float(cfg["engine"]["loop_sleep_seconds"])

    def run(self) -> dict[str, float]:
        """Execute the bounded main loop with shutdown-friendly controls."""
        candles = self.market.warmup(60)
        closes = [c.close for c in candles]
        highs = [c.high for c in candles]
        lows = [c.low for c in candles]

        for _ in range(self.max_ticks):
            candle = self.market.next_candle()
            closes.append(candle.close)
            highs.append(candle.high)
            lows.append(candle.low)

            regime = self.regime_detector.classify(highs, lows, closes)
            edge = self.edge_gate.evaluate(regime)
            self.pnl.mark_edge_state(edge.is_on)

            mark_price = candle.close
            equity = self.balance.equity(mark_price)
            self.pnl.update_equity(equity)

            can_trade, limit_reason = self.limits.can_continue(self.balance.day_start_equity, equity)
            if not can_trade:
                self.signal_logger.info("daily_limit_stop reason=%s equity=%.2f", limit_reason, equity)
                break

            exit_fill, exit_reason = self.broker.check_exit(candle.ts, mark_price)
            if exit_fill:
                proceeds = (exit_fill.price * exit_fill.qty) - exit_fill.fee
                self.balance.usdt_free += proceeds
                self.balance.btc_free -= exit_fill.qty
                self.pnl.mark_exit(gross_proceeds=proceeds)
                self.trade_logger.info(
                    "exit reason=%s qty=%.6f price=%.2f fee=%.4f usdt=%.2f",
                    exit_reason,
                    exit_fill.qty,
                    exit_fill.price,
                    exit_fill.fee,
                    self.balance.usdt_free,
                )

            signal = self.strategy.generate(candle.ts, closes)
            if signal is None:
                self.signal_logger.info("no_signal ts=%s", candle.ts.isoformat())
                time.sleep(self.loop_sleep_seconds)
                continue

            regime_key = f"range={regime.is_range_bound}|vol={regime.volatility:.4f}|trend={regime.trend_strength:.4f}"
            allowed_signal, signal_reason = self.trade_limiter.allow_signal(regime_key)

            if not edge.is_on:
                self.signal_logger.info(
                    "skip signal reason=edge_off confidence=%.2f detail=%s",
                    edge.confidence,
                    edge.reason,
                )
                time.sleep(self.loop_sleep_seconds)
                continue

            if not allowed_signal:
                self.signal_logger.info("skip signal reason=%s", signal_reason)
                time.sleep(self.loop_sleep_seconds)
                continue

            if self.broker.position is not None:
                self.signal_logger.info("skip signal reason=position_open")
                time.sleep(self.loop_sleep_seconds)
                continue

            qty = self.sizer.size(available_usdt=self.balance.usdt_free, price=signal.ref_price)
            if qty <= 0:
                self.signal_logger.info("skip signal reason=insufficient_balance")
                time.sleep(self.loop_sleep_seconds)
                continue

            entry_fill = self.broker.try_open_long(
                ts=signal.ts,
                price=signal.ref_price,
                qty=qty,
                pair=self.pair,
                take_profit_pct=self.take_profit_pct,
                stop_loss_pct=self.stop_loss_pct,
            )
            if entry_fill:
                cost = (entry_fill.price * entry_fill.qty) + entry_fill.fee
                self.balance.usdt_free -= cost
                self.balance.btc_free += entry_fill.qty
                self.pnl.mark_entry(gross_cost=cost)
                self.trade_limiter.mark_trade()
                self.trade_logger.info(
                    "entry qty=%.6f price=%.2f fee=%.4f partial=%s usdt=%.2f",
                    entry_fill.qty,
                    entry_fill.price,
                    entry_fill.fee,
                    entry_fill.is_partial,
                    self.balance.usdt_free,
                )
            else:
                self.signal_logger.info("skip signal reason=entry_rejected")

            time.sleep(self.loop_sleep_seconds)

        return summarize_metrics(
            pnl=self.pnl,
            day_start_equity=self.balance.day_start_equity,
            current_equity=self.balance.equity(closes[-1]),
        )

    async def run_live(self, feed: LiveMarketFeed, warmup: int = 60) -> dict[str, float]:
        """Execute the main loop using live candles from a websocket feed."""
        ws_task = asyncio.create_task(feed.connect())
        try:
            closes: list[float] = []
            highs: list[float] = []
            lows: list[float] = []

            for _ in range(warmup):
                candle = await feed.next_candle()
                closes.append(candle.close)
                highs.append(candle.high)
                lows.append(candle.low)

            for _ in range(self.max_ticks):
                candle = await feed.next_candle()
                closes.append(candle.close)
                highs.append(candle.high)
                lows.append(candle.low)

                regime = self.regime_detector.classify(highs, lows, closes)
                edge = self.edge_gate.evaluate(regime)
                self.pnl.mark_edge_state(edge.is_on)

                mark_price = candle.close
                equity = self.balance.equity(mark_price)
                self.pnl.update_equity(equity)

                can_trade, limit_reason = self.limits.can_continue(self.balance.day_start_equity, equity)
                if not can_trade:
                    self.signal_logger.info("daily_limit_stop reason=%s equity=%.2f", limit_reason, equity)
                    break

                exit_fill, exit_reason = self.broker.check_exit(candle.ts, mark_price)
                if exit_fill:
                    proceeds = (exit_fill.price * exit_fill.qty) - exit_fill.fee
                    self.balance.usdt_free += proceeds
                    self.balance.btc_free -= exit_fill.qty
                    self.pnl.mark_exit(gross_proceeds=proceeds)
                    self.trade_logger.info(
                        "exit reason=%s qty=%.6f price=%.2f fee=%.4f usdt=%.2f",
                        exit_reason,
                        exit_fill.qty,
                        exit_fill.price,
                        exit_fill.fee,
                        self.balance.usdt_free,
                    )

                signal = self.strategy.generate(candle.ts, closes)
                if signal is None:
                    self.signal_logger.info("no_signal ts=%s", candle.ts.isoformat())
                    continue

                regime_key = f"range={regime.is_range_bound}|vol={regime.volatility:.4f}|trend={regime.trend_strength:.4f}"
                allowed_signal, signal_reason = self.trade_limiter.allow_signal(regime_key)

                if not edge.is_on:
                    self.signal_logger.info(
                        "skip signal reason=edge_off confidence=%.2f detail=%s",
                        edge.confidence,
                        edge.reason,
                    )
                    continue

                if not allowed_signal:
                    self.signal_logger.info("skip signal reason=%s", signal_reason)
                    continue

                if self.broker.position is not None:
                    self.signal_logger.info("skip signal reason=position_open")
                    continue

                qty = self.sizer.size(available_usdt=self.balance.usdt_free, price=signal.ref_price)
                if qty <= 0:
                    self.signal_logger.info("skip signal reason=insufficient_balance")
                    continue

                entry_fill = self.broker.try_open_long(
                    ts=signal.ts,
                    price=signal.ref_price,
                    qty=qty,
                    pair=self.pair,
                    take_profit_pct=self.take_profit_pct,
                    stop_loss_pct=self.stop_loss_pct,
                )
                if entry_fill:
                    cost = (entry_fill.price * entry_fill.qty) + entry_fill.fee
                    self.balance.usdt_free -= cost
                    self.balance.btc_free += entry_fill.qty
                    self.pnl.mark_entry(gross_cost=cost)
                    self.trade_limiter.mark_trade()
                    self.trade_logger.info(
                        "entry qty=%.6f price=%.2f fee=%.4f partial=%s usdt=%.2f",
                        entry_fill.qty,
                        entry_fill.price,
                        entry_fill.fee,
                        entry_fill.is_partial,
                        self.balance.usdt_free,
                    )
                else:
                    self.signal_logger.info("skip signal reason=entry_rejected")

            return summarize_metrics(
                pnl=self.pnl,
                day_start_equity=self.balance.day_start_equity,
                current_equity=self.balance.equity(closes[-1]),
            )
        finally:
            ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await ws_task
