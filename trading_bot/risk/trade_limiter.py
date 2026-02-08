"""Signal/trade attempt limiter to avoid overtrading."""

from __future__ import annotations


class TradeLimiter:
    """Limits attempts by regime and total trades per day."""

    def __init__(self, max_signals_per_regime: int, max_trades_per_day: int) -> None:
        self.max_signals_per_regime = max_signals_per_regime
        self.max_trades_per_day = max_trades_per_day
        self._regime_attempts = 0
        self._trade_count = 0
        self._last_regime_key = None

    def allow_signal(self, regime_key: str) -> tuple[bool, str]:
        """Gate signals when current regime has been over-attempted."""
        if self._last_regime_key != regime_key:
            self._last_regime_key = regime_key
            self._regime_attempts = 0

        if self._regime_attempts >= self.max_signals_per_regime:
            return False, "regime_attempt_limit"
        if self._trade_count >= self.max_trades_per_day:
            return False, "daily_trade_limit"

        self._regime_attempts += 1
        return True, "ok"

    def mark_trade(self) -> None:
        """Record a completed entry trade."""
        self._trade_count += 1

    @property
    def trade_count(self) -> int:
        return self._trade_count
