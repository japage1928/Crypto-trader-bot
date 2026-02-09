"""Daily trading summary analyzer for the crypto trading bot."""
import os
import datetime
from trading_bot.logging.metrics import summarize_metrics

TRADE_LOG_PATH = os.path.join(os.path.dirname(__file__), 'logging', 'trade_log.txt')
METRICS_PATH = os.path.join(os.path.dirname(__file__), 'logging', 'metrics.json')


def analyze_daily_summary():
    """
    Reads today's trade log and metrics, computes a summary, and returns a formatted string.
    If no trades occurred, returns a clear message.
    """
    today = datetime.datetime.utcnow().date()
    trades = []
    first_ts = last_ts = None
    win_count = 0
    total_pnl = 0.0
    max_drawdown = None
    try:
        if not os.path.exists(TRADE_LOG_PATH):
            return "No trades today (no trade log found)."
        with open(TRADE_LOG_PATH, 'r', encoding='utf-8') as f:
            for line in f:
                if f"{today}" not in line:
                    continue
                # Example log: 2026-02-08T12:34:56 | TRADE | INFO | entry qty=... pnl=...
                parts = line.strip().split('|')
                if len(parts) < 4:
                    continue
                ts_str = parts[0].strip()
                try:
                    ts = datetime.datetime.fromisoformat(ts_str)
                except Exception:
                    continue
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
                msg = parts[-1]
                if 'pnl=' in msg:
                    try:
                        pnl = float(msg.split('pnl=')[1].split()[0])
                        total_pnl += pnl
                        if pnl > 0:
                            win_count += 1
                    except Exception:
                        pass
                trades.append(msg)
        if not trades:
            return "No trades today."
        avg_pnl = total_pnl / len(trades) if trades else 0.0
        # Try to get max drawdown from metrics if available
        max_drawdown = None
        if os.path.exists(METRICS_PATH):
            import json
            with open(METRICS_PATH, 'r', encoding='utf-8') as mf:
                try:
                    metrics = json.load(mf)
                    max_drawdown = metrics.get('max_drawdown')
                except Exception:
                    pass
        summary = [
            f"Trader Bot Daily Summary for {today}",
            f"Time range: {first_ts} to {last_ts}",
            f"Total trades: {len(trades)}",
            f"Win rate: {win_count / len(trades) * 100:.1f}%",
            f"Total PnL: {total_pnl:.2f}",
            f"Average PnL per trade: {avg_pnl:.2f}",
        ]
        if max_drawdown is not None:
            summary.append(f"Max drawdown: {max_drawdown:.2f}")
        return '\n'.join(summary)
    except Exception as e:
        return f"Error generating summary: {e}"
