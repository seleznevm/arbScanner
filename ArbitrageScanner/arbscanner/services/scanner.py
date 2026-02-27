from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import time

from arbscanner.config import Settings
from arbscanner.connectors.base import BaseConnector
from arbscanner.connectors.factory import build_connectors
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
    min_spread_diff_pct: float

    def to_dict(
        self,
        available_exchanges: list[str],
        available_symbols: list[str],
    ) -> dict[str, object]:
        return {
            "scan_interval_sec": self.scan_interval_sec,
            "allowed_scan_intervals_sec": ALLOWED_SCAN_INTERVALS_SEC,
            "trade_notional_usdt": self.trade_notional_usdt,
            "min_spread_diff_pct": self.min_spread_diff_pct,
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
        initial_symbols = (
            settings.symbols
            if settings.connector_mode.lower() == "real"
            else settings.symbol_universe
        )
        self.connectors = connectors or build_connectors(settings, symbols=initial_symbols)
        self.preferences = RuntimePreferences(
            active_exchanges=set(settings.exchanges),
            active_symbols=set(settings.symbols),
            scan_interval_sec=settings.scan_interval_sec,
            trade_notional_usdt=settings.trade_notional_usdt,
            min_spread_diff_pct=settings.min_spread_diff_pct,
        )
        self._prefs_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._started = False
        self.latest_scan_count = 0
        self.scan_iterations = 0
        self.last_scan_started_at = 0.0
        self.last_scan_finished_at = 0.0
        self.last_scan_elapsed_ms = 0.0

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

    async def get_status_snapshot(self) -> dict[str, object]:
        now = time.time()
        prefs = await self._snapshot_preferences()
        market = await self.store.get_market_snapshot()

        per_exchange: dict[str, dict[str, object]] = {
            exchange: {
                "exchange": exchange,
                "books_total": 0,
                "books_fresh": 0,
                "books_stale": 0,
                "newest_age_ms": None,
            }
            for exchange in self.available_exchanges
        }

        for symbol_books in market.values():
            for exchange, snapshot in symbol_books.items():
                entry = per_exchange.setdefault(
                    exchange,
                    {
                        "exchange": exchange,
                        "books_total": 0,
                        "books_fresh": 0,
                        "books_stale": 0,
                        "newest_age_ms": None,
                    },
                )
                age_ms = max(0.0, (now - snapshot.ts_ingest) * 1000.0)
                entry["books_total"] = int(entry["books_total"]) + 1
                if age_ms <= self.settings.stale_after_sec * 1000.0:
                    entry["books_fresh"] = int(entry["books_fresh"]) + 1
                else:
                    entry["books_stale"] = int(entry["books_stale"]) + 1
                prev_age = entry["newest_age_ms"]
                if prev_age is None or age_ms < float(prev_age):
                    entry["newest_age_ms"] = round(age_ms, 1)

        connector_status = {item.exchange: item.get_status() for item in self.connectors}
        exchange_rows: list[dict[str, object]] = []
        for exchange in sorted(per_exchange.keys()):
            row = dict(per_exchange[exchange])
            row.update(connector_status.get(exchange, {}))
            exchange_rows.append(row)

        books_total = sum(int(row["books_total"]) for row in exchange_rows)
        books_fresh = sum(int(row["books_fresh"]) for row in exchange_rows)
        books_stale = sum(int(row["books_stale"]) for row in exchange_rows)

        return {
            "started": self._started,
            "connector_mode": self.settings.connector_mode,
            "scan_interval_sec": prefs.scan_interval_sec,
            "stale_after_sec": self.settings.stale_after_sec,
            "active_exchanges": sorted(prefs.active_exchanges),
            "active_symbols": sorted(prefs.active_symbols),
            "counters": {
                "connectors_total": len(self.connectors),
                "symbols_active_count": len(prefs.active_symbols),
                "books_total": books_total,
                "books_fresh": books_fresh,
                "books_stale": books_stale,
                "opportunities_last_scan": self.latest_scan_count,
                "scan_iterations": self.scan_iterations,
                "last_scan_elapsed_ms": round(self.last_scan_elapsed_ms, 2),
                "last_scan_age_ms": round(
                    max(0.0, (now - self.last_scan_finished_at) * 1000.0), 1
                )
                if self.last_scan_finished_at
                else None,
            },
            "exchanges": exchange_rows,
        }

    async def update_runtime_settings(self, payload: dict[str, object]) -> dict[str, object]:
        updated_symbols = False
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
                updated_symbols = True

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

            min_spread = payload.get("min_spread_diff_pct")
            if min_spread is not None:
                value = float(min_spread)
                if value >= 0:
                    self.preferences.min_spread_diff_pct = value

            data = self.preferences.to_dict(
                available_exchanges=self.available_exchanges,
                available_symbols=self.available_symbols,
            )
        if updated_symbols:
            await self._sync_connector_symbols()
        return data

    async def _sync_connector_symbols(self) -> None:
        async with self._prefs_lock:
            symbols = sorted(self.preferences.active_symbols)
        for connector in self.connectors:
            connector.set_symbols(symbols)

    async def _snapshot_preferences(self) -> RuntimePreferences:
        async with self._prefs_lock:
            return RuntimePreferences(
                active_exchanges=set(self.preferences.active_exchanges),
                active_symbols=set(self.preferences.active_symbols),
                scan_interval_sec=self.preferences.scan_interval_sec,
                trade_notional_usdt=self.preferences.trade_notional_usdt,
                min_spread_diff_pct=self.preferences.min_spread_diff_pct,
            )

    async def _scan_loop(self) -> None:
        while not self._stop_event.is_set():
            start_ts = time.time()
            self.last_scan_started_at = start_ts
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
                        min_spread_diff_pct=prefs.min_spread_diff_pct,
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
            self.last_scan_elapsed_ms = elapsed * 1000.0
            self.last_scan_finished_at = time.time()
            self.scan_iterations += 1
            sleep_for = max(0.05, prefs.scan_interval_sec - elapsed)
            await asyncio.sleep(sleep_for)
