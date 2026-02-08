"""Metrics summary helpers."""

from __future__ import annotations

from dataclasses import asdict

from trading_bot.accounting.pnl_tracker import PnLTracker


def summarize_metrics(pnl: PnLTracker, day_start_equity: float, current_equity: float) -> dict[str, float]:
    """Build a minimal metrics snapshot for reporting."""
    daily_pnl = current_equity - day_start_equity
    base = {
        "daily_pnl": daily_pnl,
        "win_rate": pnl.win_rate,
        "max_drawdown": pnl.max_drawdown,
        "trades_per_day": float(pnl.daily_trade_count),
        "edge_off_ratio": pnl.edge_off_ratio,
    }
    base.update({f"pnl_{k}": float(v) for k, v in asdict(pnl).items() if isinstance(v, (int, float))})
    return base
