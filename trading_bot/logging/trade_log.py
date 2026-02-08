"""Trade event logger."""

from __future__ import annotations

import logging


def get_trade_logger() -> logging.Logger:
    """Return configured trade logger instance."""
    logger = logging.getLogger("trade_log")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s | TRADE | %(levelname)s | %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
