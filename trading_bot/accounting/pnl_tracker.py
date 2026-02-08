"""PnL tracking and performance metrics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PnLTracker:
    """Tracks trading performance statistics."""

    realized_pnl: float = 0.0
    wins: int = 0
    losses: int = 0
    peak_equity: float = 0.0
    max_drawdown: float = 0.0
    trades_closed: int = 0
    edge_off_ticks: int = 0
    total_ticks: int = 0
    daily_trade_count: int = 0
    _entry_value: float | None = field(default=None, repr=False)

    def mark_entry(self, gross_cost: float) -> None:
        """Store entry notional for next close calculation."""
        self._entry_value = gross_cost

    def mark_exit(self, gross_proceeds: float) -> None:
        """Finalize round-trip PnL and win/loss stats."""
        if self._entry_value is None:
            return

        pnl = gross_proceeds - self._entry_value
        self.realized_pnl += pnl
        self.trades_closed += 1
        self.daily_trade_count += 1

        if pnl >= 0:
            self.wins += 1
        else:
            self.losses += 1

        self._entry_value = None

    def update_equity(self, equity: float) -> None:
        """Update peak and drawdown metrics."""
        self.peak_equity = max(self.peak_equity, equity)
        if self.peak_equity > 0:
            dd = (self.peak_equity - equity) / self.peak_equity
            self.max_drawdown = max(self.max_drawdown, dd)

    def mark_edge_state(self, is_edge_on: bool) -> None:
        """Accumulate edge ON/OFF runtime share."""
        self.total_ticks += 1
        if not is_edge_on:
            self.edge_off_ticks += 1

    @property
    def win_rate(self) -> float:
        """Win ratio over closed trades."""
        if self.trades_closed == 0:
            return 0.0
        return self.wins / self.trades_closed

    @property
    def edge_off_ratio(self) -> float:
        """Fraction of ticks where edge gate was OFF."""
        if self.total_ticks == 0:
            return 0.0
        return self.edge_off_ticks / self.total_ticks
