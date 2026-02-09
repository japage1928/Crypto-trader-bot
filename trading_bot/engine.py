import os
import requests
from datetime import datetime, timezone

BINANCE_BASE_URL = "https://api.binance.com/api/v3/klines"

def fetch_market_data(symbol: str, interval: str, limit: int):
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    response = requests.get(BINANCE_BASE_URL, params=params, timeout=10)
    response.raise_for_status()

    return response.json()

def simple_moving_average(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period

def analyze(candles):
    closes = [float(candle[4]) for candle in candles]

    sma_20 = simple_moving_average(closes, 20)
    sma_50 = simple_moving_average(closes, 50)

    if sma_20 is None or sma_50 is None:
        trend = "Not enough data"
    elif sma_20 > sma_50:
        trend = "Bullish"
    elif sma_20 < sma_50:
        trend = "Bearish"
    else:
        trend = "Neutral"

    return {
        "sma_20": sma_20,
        "sma_50": sma_50,
        "trend": trend,
        "last_close": closes[-1],
    }

def main():
    symbol = os.getenv("TB_SYMBOL", "BTCUSDT")
    timeframe = os.getenv("TB_TIMEFRAME", "1h")
    candle_limit = int(os.getenv("TB_CANDLE_LIMIT", "100"))

    print("Trading bot engine online.")
    print(f"Fetching {candle_limit} candles for {symbol} ({timeframe})")

    candles = fetch_market_data(symbol, timeframe, candle_limit)
    analysis = analyze(candles)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print("\n==============================")
    print("MARKET ANALYSIS REPORT")
    print("==============================")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {timeframe}")
    print(f"Candles analyzed: {len(candles)}")
    print(f"Timestamp: {timestamp}")
    print("")
    print(f"Last Close: {analysis['last_close']:.2f}")
    print(f"SMA(20): {analysis['sma_20']:.2f}")
    print(f"SMA(50): {analysis['sma_50']:.2f}")
    print(f"Trend: {analysis['trend']}")
    print("==============================\n")

if __name__ == "__main__":
    main()
