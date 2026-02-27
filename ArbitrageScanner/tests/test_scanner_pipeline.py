from __future__ import annotations

import asyncio
import unittest

from arbscanner.config import Settings
from arbscanner.services.broker import InMemoryOpportunityBroker
from arbscanner.services.scanner import ScannerRuntime


class ScannerPipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_scanner_produces_rows(self) -> None:
        settings = Settings(
            connector_mode="mock",
            connector_interval_ms=120,
            scan_interval_sec=1,
            trade_notional_usdt=500.0,
            min_spread_diff_pct=0.01,
            min_net_edge_pct=-5.0,
            stale_after_sec=30,
            symbols=["BTC-USDT", "ETH-USDT", "SOL-USDT"],
        )
        broker = InMemoryOpportunityBroker()
        runtime = ScannerRuntime(settings=settings, broker=broker)

        await runtime.start()
        try:
            for _ in range(10):
                await asyncio.sleep(0.6)
                if broker.get_latest():
                    break
            self.assertGreater(len(broker.get_latest()), 0)
        finally:
            await runtime.stop()


if __name__ == "__main__":
    unittest.main()

