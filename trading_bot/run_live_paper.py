"""Entry point for running the live paper trading engine."""

from __future__ import annotations

import asyncio
from pathlib import Path


import signal
import sys
import asyncio
import time
import threading
import os
import json
from trading_bot.data.market_feed import LiveMarketFeed
from trading_bot.engine import EngineConfig, TradingEngine
from trading_bot.daily_summary import analyze_daily_summary
from trading_bot.emailer import send_email

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

    print("=== Live paper trading main() started ===")

    # --- Daily summary email config ---
    EMAIL_SUMMARY_ENABLED = os.environ.get("EMAIL_SUMMARY_ENABLED", "1") != "0"  # default enabled
    SUMMARY_STATE_PATH = os.path.join(os.path.dirname(__file__), "daily_summary_state.json")
    EMAIL_INTERVAL = 24 * 3600  # 24 hours in seconds

    def get_last_send_time():
        if not os.path.exists(SUMMARY_STATE_PATH):
            return 0
        try:
            with open(SUMMARY_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
                return state.get("last_send", 0)
        except Exception:
            return 0

    def set_last_send_time(ts):
        try:
            with open(SUMMARY_STATE_PATH, "w", encoding="utf-8") as f:
                json.dump({"last_send": ts}, f)
        except Exception:
            pass

    def try_send_daily_summary():
        # Called in a thread to avoid blocking main loop
        import logging
        logger = logging.getLogger("daily_summary")
        if not EMAIL_SUMMARY_ENABLED:
            logger.info("Daily summary email disabled by config.")
            return
        now = int(time.time())
        last_send = get_last_send_time()
        # Only send if 24h passed since last send
        if now - last_send < EMAIL_INTERVAL:
            return
        summary = analyze_daily_summary()
        if summary and "No trades" not in summary:
            sent = send_email(summary)
            if sent:
                set_last_send_time(now)
        else:
            logger.info("No trades today, no email sent.")

    try:
        # Warmup
        for _ in range(60):
            candle = loop.run_until_complete(feed.next_candle())
            if not hasattr(engine, '_closes'):
                engine._closes = []
                engine._highs = []
                engine._lows = []
            engine._closes.append(candle.close)
            engine._highs.append(candle.high)
            engine._lows.append(candle.low)

        while running:
            print("heartbeat: main loop alive")
            candle = loop.run_until_complete(feed.next_candle())
            engine._closes.append(candle.close)
            engine._highs.append(candle.high)
            engine._lows.append(candle.low)
            engine.step_live(candle)
            # --- Daily summary check (non-blocking) ---
            if EMAIL_SUMMARY_ENABLED:
                t = threading.Thread(target=try_send_daily_summary, daemon=True)
                t.start()
            time.sleep(5)
    except Exception as e:
        print(f"Runtime error: {e}")
        time.sleep(5)
    finally:
        engine.shutdown()
        print("Live paper trading stopped cleanly.")

if __name__ == "__main__":
    main()
