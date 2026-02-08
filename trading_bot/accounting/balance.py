"""Balance and equity state for the paper account."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccountBalance:
    """Tracks quote/base balances plus start-of-day reference equity."""

    usdt_free: float
    btc_free: float
    day_start_equity: float

    def equity(self, mark_price: float) -> float:
        """Total equity marked to current price."""
        return self.usdt_free + (self.btc_free * mark_price)
