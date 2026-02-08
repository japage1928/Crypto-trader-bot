"""Project-wide constants for the paper trading bot."""

from __future__ import annotations

DEFAULT_PAIR = "BTC/USDT"
DEFAULT_BASE_ASSET = "BTC"
DEFAULT_QUOTE_ASSET = "USDT"
DEFAULT_TIMEFRAME = "1m"

# Engine behavior
DEFAULT_LOOP_SLEEP_SECONDS = 1.0
DEFAULT_MAX_CANDLES = 500

# Precision controls for paper simulation
PRICE_DECIMALS = 2
QTY_DECIMALS = 6
