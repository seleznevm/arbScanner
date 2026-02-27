from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse

from arbscanner.config import Settings
from arbscanner.services.broker import BaseOpportunityBroker, build_broker
from arbscanner.services.scanner import ALLOWED_SCAN_INTERVALS_SEC, ScannerRuntime

LOGGER = logging.getLogger(__name__)


class RuntimeSettingsUpdate(BaseModel):
    active_exchanges: list[str] | None = None
    active_symbols: list[str] | None = None
    scan_interval_sec: int | None = Field(default=None)
    trade_notional_usdt: float | None = Field(default=None, gt=0)


def _filter_payload(
    payload: list[dict[str, object]],
    active_exchanges: set[str],
    active_symbols: set[str],
) -> list[dict[str, object]]:
    return [
        row
        for row in payload
        if str(row.get("symbol")) in active_symbols
        and str(row.get("buy_exchange")) in active_exchanges
        and str(row.get("sell_exchange")) in active_exchanges
    ]


def create_app() -> FastAPI:
    settings = Settings.from_env()
    broker = build_broker(settings)
    scanner = (
        ScannerRuntime(settings=settings, broker=broker)
        if settings.run_scanner_in_api
        else None
    )

    app = FastAPI(title="Arbitrage Scanner MVP", version="0.1.0")
    app.state.settings = settings
    app.state.broker = broker
    app.state.scanner = scanner
    app.state.runtime_settings = {
        "scan_interval_sec": settings.scan_interval_sec,
        "allowed_scan_intervals_sec": ALLOWED_SCAN_INTERVALS_SEC,
        "trade_notional_usdt": settings.trade_notional_usdt,
        "active_exchanges": sorted(settings.exchanges),
        "active_symbols": sorted(settings.symbols),
        "available_exchanges": sorted(settings.exchanges),
        "available_symbols": sorted(settings.symbol_universe),
    }

    @app.on_event("startup")
    async def _startup() -> None:
        await broker.start()
        if scanner:
            await scanner.start()
        LOGGER.info("API startup complete")

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        if scanner:
            await scanner.stop()
        await broker.stop()
        LOGGER.info("API shutdown complete")

    @app.get("/health")
    async def health() -> dict[str, object]:
        runtime = app.state.runtime_settings
        return {
            "ok": True,
            "scan_interval_sec": runtime["scan_interval_sec"],
            "broker_mode": "redis" if settings.use_redis else "inmemory",
            "run_scanner_in_api": settings.run_scanner_in_api,
            "symbols": runtime["active_symbols"],
            "exchanges": len(runtime["active_exchanges"]),
        }

    @app.get("/api/settings")
    async def get_settings() -> dict[str, object]:
        if scanner:
            runtime = await scanner.get_runtime_settings()
            app.state.runtime_settings = runtime
            return runtime
        return app.state.runtime_settings

    @app.put("/api/settings")
    async def update_settings(
        update: RuntimeSettingsUpdate = Body(...),
    ) -> dict[str, object]:
        payload = update.model_dump(exclude_none=True)
        if scanner:
            runtime = await scanner.update_runtime_settings(payload)
            app.state.runtime_settings = runtime
            return runtime

        current = dict(app.state.runtime_settings)
        if "active_exchanges" in payload and payload["active_exchanges"]:
            requested = [str(item).lower() for item in payload["active_exchanges"]]
            valid = sorted(
                item for item in requested if item in set(current["available_exchanges"])
            )
            current["active_exchanges"] = valid
        if "active_exchanges" in payload and payload["active_exchanges"] == []:
            current["active_exchanges"] = []
        if "active_symbols" in payload and payload["active_symbols"]:
            requested = [str(item).upper() for item in payload["active_symbols"]]
            valid = sorted(
                item for item in requested if item in set(current["available_symbols"])
            )
            current["active_symbols"] = valid
        if "active_symbols" in payload and payload["active_symbols"] == []:
            current["active_symbols"] = []
        if "scan_interval_sec" in payload:
            value = int(payload["scan_interval_sec"])
            if value in ALLOWED_SCAN_INTERVALS_SEC:
                current["scan_interval_sec"] = value
        if "trade_notional_usdt" in payload:
            value = float(payload["trade_notional_usdt"])
            if value > 0:
                current["trade_notional_usdt"] = value

        app.state.runtime_settings = current
        return current

    @app.get("/api/opportunities")
    async def get_opportunities() -> dict[str, object]:
        payload = broker.get_latest()
        runtime = app.state.runtime_settings
        filtered = _filter_payload(
            payload,
            set(runtime["active_exchanges"]),
            set(runtime["active_symbols"]),
        )
        return {"count": len(filtered), "ts": time.time(), "opportunities": filtered}

    @app.websocket("/ws/opportunities")
    async def ws_opportunities(websocket: WebSocket) -> None:
        await websocket.accept()
        queue = broker.subscribe()
        try:
            snapshot = _filter_payload(
                broker.get_latest(),
                set(app.state.runtime_settings["active_exchanges"]),
                set(app.state.runtime_settings["active_symbols"]),
            )
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "count": len(snapshot),
                    "opportunities": snapshot,
                    "ts": time.time(),
                }
            )
            while True:
                payload = await queue.get()
                filtered = _filter_payload(
                    payload,
                    set(app.state.runtime_settings["active_exchanges"]),
                    set(app.state.runtime_settings["active_symbols"]),
                )
                await websocket.send_json(
                    {
                        "type": "update",
                        "count": len(filtered),
                        "opportunities": filtered,
                        "ts": time.time(),
                    }
                )
        except WebSocketDisconnect:
            return
        finally:
            broker.unsubscribe(queue)

    @app.get("/")
    async def index() -> FileResponse:
        static_path = Path(__file__).with_name("static").joinpath("index.html")
        return FileResponse(static_path)

    return app
