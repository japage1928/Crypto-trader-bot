"""Entry point for running the live paper trading engine."""

from __future__ import annotations

import asyncio
from pathlib import Path

import signal
import sys
import asyncio
import time
from trading_bot.data.market_feed import LiveMarketFeed
from trading_bot.engine import EngineConfig, TradingEngine

running = True

def shutdown_handler(sig, frame):
    global running
    print("\nGraceful shutdown initiated...")
    running = False

signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

def main():
    cfg_path = Path(__file__).parent / "config" / "settings.yaml"
    engine = TradingEngine(EngineConfig.from_yaml(cfg_path))
    feed = LiveMarketFeed(symbol=engine.pair.replace("/", "").lower(), candle_interval=60, max_candles=500)

    loop = asyncio.get_event_loop()
    loop.create_task(feed.connect())

    print("Live paper trading started. Press CTRL+C to stop.")
    try:
        # Warmup
        for _ in range(60):
            candle = loop.run_until_complete(feed.next_candle())
            # Optionally, pass to engine if needed for indicators
            if not hasattr(engine, '_closes'):
                engine._closes = []
                engine._highs = []
                engine._lows = []
            engine._closes.append(candle.close)
            engine._highs.append(candle.high)
            engine._lows.append(candle.low)

        while running:
            candle = loop.run_until_complete(feed.next_candle())
            engine._closes.append(candle.close)
            engine._highs.append(candle.high)
            engine._lows.append(candle.low)
            engine.step_live(candle)
    except Exception as e:
        print(f"Runtime error: {e}")
        time.sleep(5)
    finally:
        engine.shutdown()
        print("Live paper trading stopped cleanly.")

if __name__ == "__main__":
    main()
