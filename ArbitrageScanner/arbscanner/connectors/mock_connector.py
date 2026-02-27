from __future__ import annotations

import asyncio
import random
import time

from arbscanner.connectors.base import BaseConnector
from arbscanner.models import OrderBookLevel, OrderBookSnapshot
from arbscanner.services.store import MarketDataStore

SYMBOL_BASE = {
    "BTC-USDT": 65000.0,
    "ETH-USDT": 3500.0,
    "SOL-USDT": 165.0,
}


class MockConnector(BaseConnector):
    def __init__(
        self,
        exchange: str,
        symbols: list[str],
        interval_ms: int,
        exchange_bias: float,
        rng_seed: int,
    ) -> None:
        super().__init__(exchange, symbols)
        self.interval_ms = interval_ms
        self.exchange_bias = exchange_bias
        self._rng = random.Random(rng_seed)
        self._mid = {
            symbol: SYMBOL_BASE.get(symbol, 100.0) * (1.0 + exchange_bias)
            for symbol in symbols
        }
        self._seq = 0

    async def run(self, store: MarketDataStore, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            now = time.time()
            for symbol in self.symbols:
                snapshot = self._next_snapshot(symbol, now)
                await store.upsert(snapshot)
            await asyncio.sleep(self.interval_ms / 1000.0)

    def _next_snapshot(self, symbol: str, now: float) -> OrderBookSnapshot:
        self._seq += 1
        mid = self._mid[symbol]
        drift = self._rng.uniform(-0.0006, 0.0006)
        self._mid[symbol] = max(0.1, mid * (1.0 + drift))
        mid = self._mid[symbol]

        top_spread = 0.0004 + self._rng.random() * 0.0008
        step = 0.00025
        depth = 20

        bids: list[OrderBookLevel] = []
        asks: list[OrderBookLevel] = []
        for level in range(depth):
            bid_price = mid * (1.0 - top_spread - level * step)
            ask_price = mid * (1.0 + top_spread + level * step)
            qty = self._rng.uniform(0.4, 2.5)
            bids.append(OrderBookLevel(price=round(bid_price, 6), qty=round(qty, 6)))
            asks.append(OrderBookLevel(price=round(ask_price, 6), qty=round(qty, 6)))

        return OrderBookSnapshot(
            exchange=self.exchange,
            symbol=symbol,
            bids=bids,
            asks=asks,
            ts_event=now,
            ts_ingest=time.time(),
            is_healthy=True,
            meta={
                "seq_id": self._seq,
                "source": "mock",
            },
        )

