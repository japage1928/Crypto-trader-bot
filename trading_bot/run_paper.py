"""Entry point for running the paper trading engine."""

from __future__ import annotations

from pathlib import Path

from trading_bot.engine import EngineConfig, TradingEngine



import time
import signal
import sys

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

    print("Paper trading started. Press CTRL+C to stop.")

    while running:
        try:
            engine.step()   # one market cycle
            time.sleep(1)   # throttle (adjust if needed)
        except Exception as e:
            print(f"Runtime error: {e}")
            time.sleep(5)

    engine.shutdown()
    print("Paper trading stopped cleanly.")

if __name__ == "__main__":
    main()
