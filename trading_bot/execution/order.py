"""Order models for paper broker simulation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class LimitOrder:
    """Simple limit order model."""

    order_id: str
    ts: datetime
    side: str
    price: float
    qty: float
    pair: str


@dataclass
class Fill:
    """Order fill result (possibly partial)."""

    order_id: str
    ts: datetime
    price: float
    qty: float
    fee: float
    is_partial: bool
