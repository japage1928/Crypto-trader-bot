"""Paper execution layer with deterministic simulated fills."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import random
from typing import Optional
from uuid import uuid4

from trading_bot.execution.order import Fill, LimitOrder


@dataclass
class Position:
    """Long-only open position state."""

    entry_ts: datetime
    entry_price: float
    qty: float
    tp_price: float
    sl_price: float


class PaperBroker:
    """Simulates limit order placement/fills and position exits."""

    def __init__(
        self,
        fee_rate: float,
        partial_fill_probability: float,
        min_partial_fill_ratio: float,
        max_partial_fill_ratio: float,
        slippage_bps: float,
        seed: int = 42,
    ) -> None:
        self.fee_rate = fee_rate
        self.partial_fill_probability = partial_fill_probability
        self.min_partial_fill_ratio = min_partial_fill_ratio
        self.max_partial_fill_ratio = max_partial_fill_ratio
        self.slippage_bps = slippage_bps
        self._rng = random.Random(seed)
        self.position: Optional[Position] = None

    def build_limit_order(self, ts: datetime, side: str, price: float, qty: float, pair: str) -> LimitOrder:
        """Create a limit order object."""
        return LimitOrder(order_id=str(uuid4()), ts=ts, side=side, price=price, qty=qty, pair=pair)

    def simulate_fill(self, order: LimitOrder) -> Fill:
        """Simulate limit fill, including partials and tiny slippage."""
        is_partial = self._rng.random() < self.partial_fill_probability
        ratio = self._rng.uniform(self.min_partial_fill_ratio, self.max_partial_fill_ratio) if is_partial else 1.0
        fill_qty = order.qty * ratio

        slip = self.slippage_bps / 10_000.0
        slipped_price = order.price * (1.0 + slip if order.side == "BUY" else 1.0 - slip)
        fee = (slipped_price * fill_qty) * self.fee_rate

        return Fill(
            order_id=order.order_id,
            ts=order.ts,
            price=slipped_price,
            qty=fill_qty,
            fee=fee,
            is_partial=is_partial,
        )

    def try_open_long(self, ts: datetime, price: float, qty: float, pair: str, take_profit_pct: float, stop_loss_pct: float) -> Fill | None:
        """Open a long position if no position is currently open."""
        if self.position is not None or qty <= 0:
            return None

        order = self.build_limit_order(ts=ts, side="BUY", price=price, qty=qty, pair=pair)
        fill = self.simulate_fill(order)

        self.position = Position(
            entry_ts=ts,
            entry_price=fill.price,
            qty=fill.qty,
            tp_price=fill.price * (1.0 + take_profit_pct),
            sl_price=fill.price * (1.0 - stop_loss_pct),
        )
        return fill

    def check_exit(self, ts: datetime, market_price: float) -> tuple[Fill | None, str | None]:
        """Close position when TP or SL is reached."""
        if self.position is None:
            return None, None

        if market_price >= self.position.tp_price:
            reason = "take_profit"
        elif market_price <= self.position.sl_price:
            reason = "stop_loss"
        else:
            return None, None

        order = self.build_limit_order(ts=ts, side="SELL", price=market_price, qty=self.position.qty, pair="BTC/USDT")
        fill = self.simulate_fill(order)
        self.position = None
        return fill, reason
