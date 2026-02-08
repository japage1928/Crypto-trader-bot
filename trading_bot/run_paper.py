"""Entry point for running the paper trading engine."""

from __future__ import annotations

from pathlib import Path

from trading_bot.engine import EngineConfig, TradingEngine


def main() -> None:
    """Load config and execute paper trading session."""
    cfg_path = Path(__file__).parent / "config" / "settings.yaml"
    engine = TradingEngine(EngineConfig.from_yaml(cfg_path))
    metrics = engine.run()

    print("=== PAPER RUN COMPLETE ===")
    for k, v in metrics.items():
        print(f"{k}: {v:.6f}" if isinstance(v, float) else f"{k}: {v}")


if __name__ == "__main__":
    main()
