from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

from arbscanner.services.store import MarketDataStore


class BaseConnector(ABC):
    def __init__(self, exchange: str, symbols: list[str]) -> None:
        self.exchange = exchange
        self.symbols = symbols

    @abstractmethod
    async def run(self, store: MarketDataStore, stop_event: asyncio.Event) -> None:
        raise NotImplementedError

