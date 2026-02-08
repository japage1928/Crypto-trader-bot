"""Regime detection for edge gating."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from trading_bot.data.indicators import range_bound_ratio, realized_volatility, trend_strength


@dataclass(frozen=True)
class RegimeState:
    """Market regime classification snapshot."""

    is_range_bound: bool
    volatility: float
    trend_strength: float
    range_ratio: float


class RegimeDetector:
    """Classifies market conditions into range/trend buckets."""

    def __init__(
        self,
        volatility_window: int,
        volatility_threshold: float,
        trend_window: int,
        trend_strength_threshold: float,
        range_ratio_threshold: float,
    ) -> None:
        self.volatility_window = volatility_window
        self.volatility_threshold = volatility_threshold
        self.trend_window = trend_window
        self.trend_strength_threshold = trend_strength_threshold
        self.range_ratio_threshold = range_ratio_threshold

    def classify(self, highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> RegimeState:
        """Return regime information used by the edge gate."""
        vol = realized_volatility(closes, self.volatility_window)
        tr = trend_strength(closes, self.trend_window)
        rr = range_bound_ratio(highs[-self.trend_window :], lows[-self.trend_window :], closes[-self.trend_window :])

        # Lower net-move-to-range ratio implies more sideways behavior.
        is_range = rr <= self.range_ratio_threshold
        return RegimeState(
            is_range_bound=is_range,
            volatility=vol,
            trend_strength=tr,
            range_ratio=rr,
        )
