"""Market feed abstractions for deterministic and live paper trading runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import asyncio
import json
import math
import random
from collections import deque
from typing import Deque, List, Optional

import websockets


@dataclass(frozen=True)
class Candle:
    """OHLCV candle."""

    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketFeed:
    """Synthetic deterministic feed suitable for paper strategy validation."""

    def __init__(self, seed: int = 42, start_price: float = 50000.0) -> None:
        self._rng = random.Random(seed)
        self._price = start_price
        self._ts = datetime.utcnow().replace(second=0, microsecond=0)

    def next_candle(self) -> Candle:
        """Generate the next candle with bounded noise around a mild sinusoid."""
        wave = math.sin(self._ts.timestamp() / 2400.0) * 0.0008
        noise = self._rng.uniform(-0.0015, 0.0015)
        drift = wave + noise

        open_price = self._price
        close_price = max(1.0, open_price * (1.0 + drift))
        high = max(open_price, close_price) * (1.0 + abs(self._rng.uniform(0.0, 0.0008)))
        low = min(open_price, close_price) * (1.0 - abs(self._rng.uniform(0.0, 0.0008)))
        volume = self._rng.uniform(0.1, 5.0)

        candle = Candle(ts=self._ts, open=open_price, high=high, low=low, close=close_price, volume=volume)
        self._price = close_price
        self._ts += timedelta(minutes=1)
        return candle

    def warmup(self, n: int) -> List[Candle]:
        """Generate initial candles for indicator warm-up."""
        return [self.next_candle() for _ in range(n)]


class LiveMarketFeed:
    """Live Binance.US trade stream aggregated into candles."""

    BINANCE_WS_URL = "wss://stream.binance.us:9443/ws"

    def __init__(self, symbol: str = "btcusdt", candle_interval: int = 60, max_candles: int = 500) -> None:
        self.symbol = symbol.lower()
        self.candle_interval = candle_interval
        self.candles: Deque[Candle] = deque(maxlen=max_candles)
        self.current_candle: Optional[Candle] = None
        self._candle_queue: asyncio.Queue[Candle] = asyncio.Queue(maxsize=max_candles)

    async def connect(self) -> None:
        """Connect to the trade stream and aggregate ticks into candles."""
        stream = f"{self.symbol}@trade"
        url = f"{self.BINANCE_WS_URL}/{stream}"
        async with websockets.connect(url) as ws:
            async for message in ws:
                self._handle_message(json.loads(message))

    def _handle_message(self, msg: dict) -> None:
        price = float(msg["p"])
        timestamp = int(msg["T"]) // 1000
        self._update_candle(price, timestamp)

    def _update_candle(self, price: float, timestamp: int) -> None:
        candle_start = timestamp - (timestamp % self.candle_interval)

        if self.current_candle is None:
            self.current_candle = self._new_candle(price, candle_start)
            return

        current_start = int(self.current_candle.ts.replace(tzinfo=timezone.utc).timestamp())
        if candle_start > current_start:
            self._enqueue_candle(self.current_candle)
            self.current_candle = self._new_candle(price, candle_start)
        else:
            self.current_candle = Candle(
                ts=self.current_candle.ts,
                open=self.current_candle.open,
                high=max(self.current_candle.high, price),
                low=min(self.current_candle.low, price),
                close=price,
                volume=self.current_candle.volume + 1.0,
            )

    def _new_candle(self, price: float, timestamp: int) -> Candle:
        ts = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return Candle(ts=ts, open=price, high=price, low=price, close=price, volume=1.0)

    def _enqueue_candle(self, candle: Candle) -> None:
        self.candles.append(candle)
        try:
            self._candle_queue.put_nowait(candle)
        except asyncio.QueueFull:
            try:
                _ = self._candle_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self._candle_queue.put_nowait(candle)

    async def next_candle(self) -> Candle:
        """Await the next completed candle."""
        return await self._candle_queue.get()

    def get_candles(self) -> List[Candle]:
        """Return completed candles only."""
        return list(self.candles)

    def get_latest_price(self) -> Optional[float]:
        """Return the latest trade price if available."""
        if self.current_candle:
            return self.current_candle.close
        return None
