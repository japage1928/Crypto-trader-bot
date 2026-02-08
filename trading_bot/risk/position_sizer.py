"""Position sizing logic with conservative safety checks."""

from __future__ import annotations

from math import floor


class PositionSizer:
    """Computes BTC size based on quote balance and fixed risk budget."""

    def __init__(self, risk_per_trade_pct: float, min_notional_usdt: float) -> None:
        self.risk_per_trade_pct = risk_per_trade_pct
        self.min_notional_usdt = min_notional_usdt

    def size(self, available_usdt: float, price: float) -> float:
        """Return size in BTC; 0 means skip due to insufficient capital."""
        if available_usdt <= 0 or price <= 0:
            return 0.0

        notional = available_usdt * self.risk_per_trade_pct
        notional = max(self.min_notional_usdt, notional)
        if notional > available_usdt:
            return 0.0

        qty = notional / price
        # Basic deterministic quantization.
        return floor(qty * 1_000_000) / 1_000_000
