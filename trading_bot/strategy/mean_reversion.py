"""Long-only mean reversion strategy implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from trading_bot.data.indicators import ema, pct_change
from trading_bot.strategy.signal import Signal


class MeanReversionStrategy:
    """Generates long-entry signals when price undershoots short-term EMA."""

    def __init__(self, ema_period: int, entry_deviation_pct: float) -> None:
        self.ema_period = ema_period
        self.entry_deviation_pct = entry_deviation_pct

    def generate(self, ts: datetime, closes: Sequence[float]) -> Signal | None:
        """Return a BUY signal when close is sufficiently below EMA; else HOLD."""
        if len(closes) < self.ema_period:
            return None

        current = closes[-1]
        baseline = ema(closes[-self.ema_period :], self.ema_period)
        deviation = pct_change(current, baseline)

        if deviation <= -abs(self.entry_deviation_pct):
            confidence = min(1.0, abs(deviation) / max(self.entry_deviation_pct, 1e-9))
            return Signal(
                ts=ts,
                side="BUY",
                action="ENTER",
                confidence=confidence,
                reason=f"mean_revert_deviation={deviation:.5f}",
                ref_price=current,
            )
        return None
