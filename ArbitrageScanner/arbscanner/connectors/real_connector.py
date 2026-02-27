from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from arbscanner.connectors.base import BaseConnector
from arbscanner.models import OrderBookLevel, OrderBookSnapshot
from arbscanner.services.store import MarketDataStore

LOGGER = logging.getLogger(__name__)

EXCHANGE_ALIASES = {
    # Keep canonical IDs from settings but resolve to the implementation available in ccxt.
    "htx": ["htx", "huobi"],
}


class CCXTOrderBookConnector(BaseConnector):
    def __init__(
        self,
        exchange: str,
        symbols: list[str],
        interval_ms: int,
        depth: int,
        timeout_ms: int,
    ) -> None:
        super().__init__(exchange, symbols)
        self.interval_ms = interval_ms
        self.depth = depth
        self.timeout_ms = timeout_ms
        self._client: Any | None = None
        self._symbol_map: dict[str, str] = {}
        self._symbol_key: tuple[str, ...] = tuple()
        self._ccxt_module: Any | None = None
        self._initialized = False

    async def run(self, store: MarketDataStore, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            try:
                await self._ensure_initialized()
                self._refresh_symbol_map()
                if not self._symbol_map:
                    await asyncio.sleep(5.0)
                    continue

                for canonical_symbol, ccxt_symbol in self._symbol_map.items():
                    if stop_event.is_set():
                        break
                    snapshot = await self._fetch_snapshot(canonical_symbol, ccxt_symbol)
                    if snapshot is not None:
                        await store.upsert(snapshot)
                await asyncio.sleep(max(0.1, self.interval_ms / 1000.0))
            except asyncio.CancelledError:
                break
            except Exception:
                LOGGER.exception("Real connector loop failure for %s", self.exchange)
                await self._reset_client()
                await asyncio.sleep(3.0)

        await self._reset_client()

    def get_status(self) -> dict[str, object]:
        status = super().get_status()
        status.update(
            {
                "mode": "real",
                "initialized": self._initialized,
                "mapped_symbols": len(self._symbol_map),
                "requested_symbols": len(self.symbols),
            }
        )
        return status

    async def _ensure_initialized(self) -> None:
        if self._initialized and self._client is not None:
            return

        ccxt_async = await self._import_ccxt_async()
        exchange_class = self._resolve_exchange_class(ccxt_async, self.exchange)
        if exchange_class is None:
            raise RuntimeError(
                f"Exchange '{self.exchange}' is not supported by installed ccxt build"
            )

        self._client = exchange_class(
            {
                "enableRateLimit": True,
                "timeout": self.timeout_ms,
            }
        )
        await self._client.load_markets()
        self._symbol_map = {}
        self._symbol_key = tuple()
        self._refresh_symbol_map()
        self._initialized = True

        LOGGER.info(
            "Real connector initialized: %s (%s symbols mapped)",
            self.exchange,
            len(self._symbol_map),
        )

    def _refresh_symbol_map(self) -> None:
        if self._client is None:
            return
        key = tuple(sorted(set(self.symbols)))
        if key == self._symbol_key:
            return
        self._symbol_map = self._build_symbol_map(list(key), self._client.symbols)
        self._symbol_key = key
        LOGGER.info(
            "Connector %s symbols refreshed: %s mapped",
            self.exchange,
            len(self._symbol_map),
        )

    async def _import_ccxt_async(self) -> Any:
        if self._ccxt_module is not None:
            return self._ccxt_module
        try:
            import ccxt.async_support as ccxt_async  # type: ignore
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "ccxt is required for real connectors. Install dependencies from requirements.txt"
            ) from exc
        self._ccxt_module = ccxt_async
        return ccxt_async

    @staticmethod
    def _resolve_exchange_class(ccxt_async: Any, exchange_id: str) -> Any | None:
        candidates = EXCHANGE_ALIASES.get(exchange_id, [exchange_id])
        for candidate in candidates:
            if hasattr(ccxt_async, candidate):
                return getattr(ccxt_async, candidate)
        return None

    def _build_symbol_map(
        self,
        canonical_symbols: list[str],
        ccxt_symbols: list[str] | None,
    ) -> dict[str, str]:
        available = list(ccxt_symbols or [])
        mapped: dict[str, str] = {}
        for canonical in canonical_symbols:
            resolved = self._resolve_symbol(canonical, available)
            if resolved:
                mapped[canonical] = resolved
        missing = [symbol for symbol in canonical_symbols if symbol not in mapped]
        if missing:
            LOGGER.debug(
                "Connector %s: %s symbols unavailable (examples: %s)",
                self.exchange,
                len(missing),
                ", ".join(missing[:5]),
            )
        return mapped

    @staticmethod
    def _resolve_symbol(canonical_symbol: str, available_symbols: list[str]) -> str | None:
        if "-" not in canonical_symbol:
            return None
        base, quote = canonical_symbol.split("-", 1)
        unified = f"{base}/{quote}"

        if unified in available_symbols:
            return unified
        prefixed = [symbol for symbol in available_symbols if symbol.startswith(unified + ":")]
        if prefixed:
            return prefixed[0]

        # Fallback fuzzy lookup when exchange uses alternate quote suffixes.
        for symbol in available_symbols:
            normalized = symbol.replace("/", "-").split(":")[0]
            if normalized == canonical_symbol:
                return symbol
        return None

    async def _fetch_snapshot(
        self,
        canonical_symbol: str,
        ccxt_symbol: str,
    ) -> OrderBookSnapshot | None:
        if self._client is None:
            return None
        try:
            orderbook = await self._client.fetch_order_book(ccxt_symbol, limit=self.depth)
        except Exception as exc:
            LOGGER.debug(
                "Orderbook fetch failed %s %s (%s): %s",
                self.exchange,
                canonical_symbol,
                ccxt_symbol,
                exc,
            )
            return None

        bids_raw = orderbook.get("bids") or []
        asks_raw = orderbook.get("asks") or []
        bids = [
            OrderBookLevel(price=float(level[0]), qty=float(level[1]))
            for level in bids_raw[: self.depth]
            if len(level) >= 2 and float(level[0]) > 0 and float(level[1]) > 0
        ]
        asks = [
            OrderBookLevel(price=float(level[0]), qty=float(level[1]))
            for level in asks_raw[: self.depth]
            if len(level) >= 2 and float(level[0]) > 0 and float(level[1]) > 0
        ]
        if not bids or not asks:
            return None

        ts_ms = orderbook.get("timestamp")
        now = time.time()
        ts_event = float(ts_ms) / 1000.0 if ts_ms else now
        return OrderBookSnapshot(
            exchange=self.exchange,
            symbol=canonical_symbol,
            bids=bids,
            asks=asks,
            ts_event=ts_event,
            ts_ingest=now,
            is_healthy=True,
            meta={
                "source": "real",
                "connector": "ccxt",
                "ccxt_symbol": ccxt_symbol,
            },
        )

    async def _reset_client(self) -> None:
        if self._client is not None:
            try:
                await self._client.close()
            except Exception:
                pass
        self._client = None
        self._initialized = False
        self._symbol_map = {}
        self._symbol_key = tuple()
