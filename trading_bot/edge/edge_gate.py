"""Edge gate that controls whether trading is currently allowed."""

from __future__ import annotations

from dataclasses import dataclass

from trading_bot.edge.regime_detector import RegimeState


@dataclass(frozen=True)
class EdgeDecision:
    """Decision returned by edge permission logic."""

    is_on: bool
    confidence: float
    reason: str


class EdgeGate:
    """Central edge ON/OFF evaluator with confidence scoring."""

    def __init__(self, volatility_threshold: float, trend_strength_threshold: float, min_confidence: float) -> None:
        self.volatility_threshold = volatility_threshold
        self.trend_strength_threshold = trend_strength_threshold
        self.min_confidence = min_confidence

    def evaluate(self, regime: RegimeState) -> EdgeDecision:
        """Evaluate whether current market regime supports mean reversion entries."""
        vol_ok = regime.volatility <= self.volatility_threshold
        trend_ok = regime.trend_strength <= self.trend_strength_threshold
        range_ok = regime.is_range_bound

        score = sum([vol_ok, trend_ok, range_ok]) / 3.0
        confidence = max(0.0, min(1.0, score))
        is_on = vol_ok and trend_ok and range_ok and confidence >= self.min_confidence

        reason = "edge_on" if is_on else f"edge_off(vol_ok={vol_ok},trend_ok={trend_ok},range_ok={range_ok})"
        return EdgeDecision(is_on=is_on, confidence=confidence, reason=reason)
