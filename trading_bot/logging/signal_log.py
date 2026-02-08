"""Signal event logger."""

from __future__ import annotations

import logging


def get_signal_logger() -> logging.Logger:
    """Return configured signal logger instance."""
    logger = logging.getLogger("signal_log")
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s | SIGNAL | %(levelname)s | %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
