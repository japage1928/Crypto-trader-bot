"""Daily risk caps for hard-stop trading control."""

from __future__ import annotations


class DailyLimits:
    """Enforces mandatory daily profit/loss stop conditions."""

    def __init__(self, daily_profit_cap_pct: float, daily_loss_cap_pct: float) -> None:
        self.daily_profit_cap_pct = daily_profit_cap_pct
        self.daily_loss_cap_pct = daily_loss_cap_pct

    def can_continue(self, start_balance: float, current_equity: float) -> tuple[bool, str]:
        """Return (allowed, reason) based on daily realized+unrealized equity move."""
        if start_balance <= 0:
            return False, "invalid_start_balance"

        pnl_pct = (current_equity - start_balance) / start_balance
        if pnl_pct >= self.daily_profit_cap_pct:
            return False, "daily_profit_cap_hit"
        if pnl_pct <= -abs(self.daily_loss_cap_pct):
            return False, "daily_loss_cap_hit"
        return True, "ok"
