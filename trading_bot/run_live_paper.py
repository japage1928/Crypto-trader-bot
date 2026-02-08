"""Entry point for running the live paper trading engine."""

from __future__ import annotations

import asyncio
from pathlib import Path

from trading_bot.data.market_feed import LiveMarketFeed
from trading_bot.engine import EngineConfig, TradingEngine


def main() -> None:
    """Load config and execute live paper trading session."""
    cfg_path = Path(__file__).parent / "config" / "settings.yaml"
    engine = TradingEngine(EngineConfig.from_yaml(cfg_path))

    feed = LiveMarketFeed(symbol=engine.pair.replace("/", "").lower(), candle_interval=60, max_candles=500)
    metrics = asyncio.run(engine.run_live(feed))

    print("=== LIVE PAPER RUN COMPLETE ===")
    for k, v in metrics.items():
        print(f"{k}: {v:.6f}" if isinstance(v, float) else f"{k}: {v}")


if __name__ == "__main__":
    main()
