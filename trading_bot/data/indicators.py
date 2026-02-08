"""Indicator helpers used by strategy and edge modules."""

from __future__ import annotations

from statistics import mean, pstdev
from typing import Iterable, Mapping, Sequence


def ema(values: Sequence[float], period: int) -> float:
    """Return EMA of the full series using the last value as current signal."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if not values:
        raise ValueError("values cannot be empty")

    k = 2.0 / (period + 1.0)
    acc = values[0]
    for v in values[1:]:
        acc = (v * k) + (acc * (1.0 - k))
    return acc


def pct_change(new_value: float, old_value: float) -> float:
    """Safe percentage change."""
    if old_value == 0:
        return 0.0
    return (new_value - old_value) / old_value


def realized_volatility(closes: Sequence[float], window: int) -> float:
    """Simple absolute-return based volatility estimate."""
    if len(closes) < window + 1:
        return 0.0
    rets = [abs(pct_change(closes[i], closes[i - 1])) for i in range(len(closes) - window, len(closes))]
    return mean(rets) if rets else 0.0


def trend_strength(closes: Sequence[float], window: int) -> float:
    """Magnitude of linearized trend proxy over a lookback window."""
    if len(closes) < window:
        return 0.0
    start = closes[-window]
    end = closes[-1]
    return abs(pct_change(end, start))


def range_bound_ratio(highs: Iterable[float], lows: Iterable[float], closes: Iterable[float]) -> float:
    """Return ratio of net move to total range; lower values imply more ranging behavior."""
    highs_list = list(highs)
    lows_list = list(lows)
    closes_list = list(closes)
    if not highs_list or not lows_list or not closes_list:
        return 1.0

    price_range = max(highs_list) - min(lows_list)
    net_move = abs(closes_list[-1] - closes_list[0])
    if price_range <= 0:
        return 1.0
    return net_move / price_range


def rsi(closes: Sequence[float], period: int) -> float:
    """Compute RSI using simple average gains/losses."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(closes) < period + 1:
        return 50.0

    gains = 0.0
    losses = 0.0
    for i in range(len(closes) - period, len(closes)):
        delta = closes[i] - closes[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta

    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int) -> float:
    """Compute Average True Range (ATR) using simple average."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(closes) < period + 1:
        return 0.0

    trs = []
    for i in range(len(closes) - period, len(closes)):
        prev_close = closes[i - 1]
        tr = max(highs[i] - lows[i], abs(highs[i] - prev_close), abs(lows[i] - prev_close))
        trs.append(tr)
    return mean(trs) if trs else 0.0


def bollinger_bands(closes: Sequence[float], period: int, stddevs: float = 2.0) -> tuple[float, float, float]:
    """Return (lower, middle, upper) Bollinger Bands."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(closes) < period:
        mid = closes[-1] if closes else 0.0
        return mid, mid, mid

    window = closes[-period:]
    mid = mean(window)
    std = pstdev(window)
    upper = mid + (stddevs * std)
    lower = mid - (stddevs * std)
    return lower, mid, upper


def z_score(closes: Sequence[float], period: int) -> float:
    """Return Z-score of the latest close over the lookback window."""
    if period <= 0:
        raise ValueError("period must be > 0")
    if len(closes) < period:
        return 0.0
    window = closes[-period:]
    std = pstdev(window)
    if std == 0:
        return 0.0
    return (closes[-1] - mean(window)) / std


def _bucket_volatility(vol: float) -> str:
    """Bucket volatility into low/medium/high based on absolute magnitude."""
    if vol < 0.001:
        return "low"
    if vol < 0.003:
        return "medium"
    return "high"


def _bucket_trend(trend: float) -> str:
    """Bucket trend strength into flat/weak/strong."""
    if trend < 0.001:
        return "flat"
    if trend < 0.003:
        return "weak"
    return "strong"


def compute_features(
    candles: Sequence[object],
    ema_period: int = 20,
    rsi_period: int = 14,
    atr_period: int = 14,
    bb_period: int = 20,
    z_period: int = 20,
    vol_window: int = 30,
    trend_window: int = 50,
) -> Mapping[str, float | str]:
    """Compute indicators and discrete feature buckets from candle data."""
    if not candles:
        return {
            "ema": 0.0,
            "rsi": 50.0,
            "atr": 0.0,
            "bb_lower": 0.0,
            "bb_mid": 0.0,
            "bb_upper": 0.0,
            "z_score": 0.0,
            "volatility": 0.0,
            "trend": 0.0,
            "vol_bucket": "low",
            "trend_bucket": "flat",
        }

    closes = [c.close for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]

    ema_value = ema(closes[-ema_period:] if len(closes) >= ema_period else closes, max(1, min(ema_period, len(closes))))
    rsi_value = rsi(closes, rsi_period)
    atr_value = atr(highs, lows, closes, atr_period)
    bb_lower, bb_mid, bb_upper = bollinger_bands(closes, bb_period)
    z_value = z_score(closes, z_period)

    vol = realized_volatility(closes, vol_window)
    trend = trend_strength(closes, trend_window)

    return {
        "ema": ema_value,
        "rsi": rsi_value,
        "atr": atr_value,
        "bb_lower": bb_lower,
        "bb_mid": bb_mid,
        "bb_upper": bb_upper,
        "z_score": z_value,
        "volatility": vol,
        "trend": trend,
        "vol_bucket": _bucket_volatility(vol),
        "trend_bucket": _bucket_trend(trend),
    }
