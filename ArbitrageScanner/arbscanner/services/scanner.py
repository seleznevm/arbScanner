from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time

from arbscanner.config import Settings
from arbscanner.connectors.base import BaseConnector
from arbscanner.connectors.factory import build_mock_connectors
from arbscanner.services.broker import BaseOpportunityBroker
from arbscanner.services.engine import (
    detect_spatial_opportunities,
    detect_triangular_opportunities,
)
from arbscanner.services.store import MarketDataStore

LOGGER = logging.getLogger(__name__)


ALLOWED_SCAN_INTERVALS_SEC = [5, 10, 15, 30, 60, 300, 600]


@dataclass(slots=True)
class RuntimePreferences:
    active_exchanges: set[str]
    active_symbols: set[str]
    scan_interval_sec: int
    trade_notional_usdt: float

    def to_dict(
        self,
        available_exchanges: list[str],
        available_symbols: list[str],
    ) -> dict[str, object]:
        return {
            "scan_interval_sec": self.scan_interval_sec,
            "allowed_scan_intervals_sec": ALLOWED_SCAN_INTERVALS_SEC,
            "trade_notional_usdt": self.trade_notional_usdt,
            "active_exchanges": sorted(self.active_exchanges),
            "active_symbols": sorted(self.active_symbols),
            "available_exchanges": sorted(available_exchanges),
            "available_symbols": sorted(available_symbols),
        }


class ScannerRuntime:
    def __init__(
        self,
        settings: Settings,
        broker: BaseOpportunityBroker,
        connectors: list[BaseConnector] | None = None,
    ) -> None:
        self.settings = settings
        self.broker = broker
        self.store = MarketDataStore()
        self.available_exchanges = sorted(set(settings.exchanges))
        self.available_symbols = sorted(set(settings.symbol_universe))
        self.connectors = connectors or build_mock_connectors(
            exchanges=settings.exchanges,
            symbols=settings.symbol_universe,
            interval_ms=settings.connector_interval_ms,
        )
        self.preferences = RuntimePreferences(
            active_exchanges=set(settings.exchanges),
            active_symbols=set(settings.symbols),
            scan_interval_sec=settings.scan_interval_sec,
            trade_notional_usdt=settings.trade_notional_usdt,
        )
        self._prefs_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._started = False
        self.latest_scan_count = 0

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._stop_event.clear()
        await self.broker.start()

        for connector in self.connectors:
            self._tasks.append(
                asyncio.create_task(
                    connector.run(self.store, self._stop_event),
                    name=f"connector:{connector.exchange}",
                )
            )
        self._tasks.append(asyncio.create_task(self._scan_loop(), name="scan-loop"))
        LOGGER.info("Scanner runtime started with %s connectors", len(self.connectors))

    async def stop(self) -> None:
        if not self._started:
            return
        self._started = False
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.broker.stop()
        LOGGER.info("Scanner runtime stopped")

    async def get_runtime_settings(self) -> dict[str, object]:
        async with self._prefs_lock:
            return self.preferences.to_dict(
                available_exchanges=self.available_exchanges,
                available_symbols=self.available_symbols,
            )

    async def update_runtime_settings(self, payload: dict[str, object]) -> dict[str, object]:
        async with self._prefs_lock:
            exchanges = payload.get("active_exchanges")
            if exchanges is not None:
                requested = {str(item).lower() for item in exchanges}
                valid = {item for item in requested if item in self.available_exchanges}
                self.preferences.active_exchanges = valid

            symbols = payload.get("active_symbols")
            if symbols is not None:
                requested_symbols = {str(item).upper() for item in symbols}
                valid_symbols = {
                    item for item in requested_symbols if item in self.available_symbols
                }
                self.preferences.active_symbols = valid_symbols

            scan_interval = payload.get("scan_interval_sec")
            if scan_interval is not None:
                value = int(scan_interval)
                if value in ALLOWED_SCAN_INTERVALS_SEC:
                    self.preferences.scan_interval_sec = value

            trade_notional = payload.get("trade_notional_usdt")
            if trade_notional is not None:
                value = float(trade_notional)
                if value > 0:
                    self.preferences.trade_notional_usdt = value

            return self.preferences.to_dict(
                available_exchanges=self.available_exchanges,
                available_symbols=self.available_symbols,
            )

    async def _snapshot_preferences(self) -> RuntimePreferences:
        async with self._prefs_lock:
            return RuntimePreferences(
                active_exchanges=set(self.preferences.active_exchanges),
                active_symbols=set(self.preferences.active_symbols),
                scan_interval_sec=self.preferences.scan_interval_sec,
                trade_notional_usdt=self.preferences.trade_notional_usdt,
            )

    async def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            start_ts = time.time()
            snapshot = await self.store.get_market_snapshot()
            prefs = await self._snapshot_preferences()
            opportunities = []
            for symbol, symbol_books in snapshot.items():
                if symbol not in prefs.active_symbols:
                    continue
                filtered_books = {
                    exchange: book
                    for exchange, book in symbol_books.items()
                    if exchange in prefs.active_exchanges
                }
                if len(filtered_books) < 2:
                    continue
                opportunities.extend(
                    detect_spatial_opportunities(
                        orderbooks=filtered_books,
                        settings=self.settings,
                        trade_notional_usdt=prefs.trade_notional_usdt,
                        now=start_ts,
                    )
                )
                opportunities.extend(
                    detect_triangular_opportunities(
                        orderbooks=filtered_books,
                        settings=self.settings,
                    )
                )
            opportunities.sort(key=lambda item: item.net_edge_pct, reverse=True)
            opportunities = opportunities[:150]
            self.latest_scan_count = len(opportunities)
            await self.broker.publish(opportunities)

            elapsed = time.time() - start_ts
            sleep_for = max(0.05, prefs.scan_interval_sec - elapsed)
            await asyncio.sleep(sleep_for)
