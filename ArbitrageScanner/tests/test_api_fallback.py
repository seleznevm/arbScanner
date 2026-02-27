from __future__ import annotations

import os
import time
import unittest


def _find_endpoint(app, path: str, method: str = "GET"):
    for route in app.router.routes:
        if getattr(route, "path", None) == path and method in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError(f"Endpoint not found: {method} {path}")


class ApiFallbackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._keys = [
            "BROKER_MODE",
            "RUN_SCANNER_IN_API",
            "CONNECTOR_MODE",
            "SCAN_INTERVAL_SEC",
            "CONNECTOR_INTERVAL_MS",
            "STALE_AFTER_SEC",
            "TRADE_NOTIONAL_USDT",
            "MIN_SPREAD_DIFF_PCT",
            "MIN_NET_EDGE_PCT",
            "EXCHANGES",
            "SYMBOLS",
            "SYMBOL_UNIVERSE",
        ]
        self._prev = {key: os.environ.get(key) for key in self._keys}
        os.environ["BROKER_MODE"] = "inmemory"
        os.environ["RUN_SCANNER_IN_API"] = "false"
        os.environ["CONNECTOR_MODE"] = "mock"
        os.environ["SCAN_INTERVAL_SEC"] = "1"
        os.environ["CONNECTOR_INTERVAL_MS"] = "120"
        os.environ["STALE_AFTER_SEC"] = "30"
        os.environ["TRADE_NOTIONAL_USDT"] = "500"
        os.environ["MIN_SPREAD_DIFF_PCT"] = "0.01"
        os.environ["MIN_NET_EDGE_PCT"] = "-5"
        os.environ["EXCHANGES"] = "binance,okx,bybit,kucoin"
        os.environ["SYMBOLS"] = "BTC-USDT,ETH-USDT,SOL-USDT"
        os.environ["SYMBOL_UNIVERSE"] = "BTC-USDT,ETH-USDT,SOL-USDT"

    def tearDown(self) -> None:
        for key, value in self._prev.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    async def test_fallback_scanner_starts_and_produces_rows(self) -> None:
        from arbscanner.api.app import create_app

        app = create_app()
        await app.router.startup()
        try:
            status_endpoint = _find_endpoint(app, "/api/status")
            opps_endpoint = _find_endpoint(app, "/api/opportunities")

            deadline = time.time() + 12
            status = {}
            while time.time() < deadline:
                status = await status_endpoint()
                connectors_total = int(status.get("counters", {}).get("connectors_total", 0))
                if connectors_total > 0:
                    break
                await self._sleep(0.5)

            self.assertGreater(int(status.get("counters", {}).get("connectors_total", 0)), 0)
            self.assertTrue(bool(status.get("fallback_scanner_started")))

            rows_deadline = time.time() + 8
            count = 0
            while time.time() < rows_deadline:
                payload = await opps_endpoint()
                count = int(payload.get("count", 0))
                if count > 0:
                    break
                await self._sleep(0.5)
            self.assertGreater(count, 0)
        finally:
            await app.router.shutdown()

    @staticmethod
    async def _sleep(seconds: float) -> None:
        import asyncio

        await asyncio.sleep(seconds)


if __name__ == "__main__":
    unittest.main()

