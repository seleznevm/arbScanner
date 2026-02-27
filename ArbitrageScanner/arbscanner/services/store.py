from __future__ import annotations

import asyncio
from collections import defaultdict

from arbscanner.models import OrderBookSnapshot


class MarketDataStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._books: dict[tuple[str, str], OrderBookSnapshot] = {}

    async def upsert(self, snapshot: OrderBookSnapshot) -> None:
        key = (snapshot.exchange, snapshot.symbol)
        async with self._lock:
            self._books[key] = snapshot

    async def get_market_snapshot(self) -> dict[str, dict[str, OrderBookSnapshot]]:
        async with self._lock:
            grouped: dict[str, dict[str, OrderBookSnapshot]] = defaultdict(dict)
            for (exchange, symbol), snapshot in self._books.items():
                grouped[symbol][exchange] = snapshot
            return dict(grouped)

