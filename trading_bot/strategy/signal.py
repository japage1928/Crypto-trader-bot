"""Signal models shared between strategy and engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Signal:
    """Trading signal emitted by the strategy."""

    ts: datetime
    side: str
    action: str
    confidence: float
    reason: str
    ref_price: float
