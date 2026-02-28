from __future__ import annotations

import unittest

from arbscanner.config import Settings
from arbscanner.models import OrderBookLevel, OrderBookSnapshot
from arbscanner.services.engine import compute_vwap, detect_spatial_opportunities


class EngineTests(unittest.TestCase):
    def test_compute_vwap_partial_fill(self) -> None:
        levels = [
            OrderBookLevel(price=100.0, qty=1.0),
            OrderBookLevel(price=101.0, qty=1.0),
        ]
        vwap, filled = compute_vwap(levels, 1.5)
        self.assertAlmostEqual(filled, 1.5)
        self.assertAlmostEqual(vwap, (100.0 * 1.0 + 101.0 * 0.5) / 1.5)

    def test_detect_spatial_opportunity(self) -> None:
        settings = Settings(
            min_net_edge_pct=0.01,
            min_spread_diff_pct=0.01,
            trade_notional_usdt=100.0,
            taker_fee_bps=1.0,
            slippage_bps=1.0,
            withdraw_cost_usdt=0.0,
        )
        buy_book = OrderBookSnapshot(
            exchange="a",
            symbol="BTC-USDT",
            bids=[OrderBookLevel(price=99.0, qty=3.0)],
            asks=[OrderBookLevel(price=100.0, qty=3.0)],
            ts_event=1.0,
            ts_ingest=10.0,
        )
        sell_book = OrderBookSnapshot(
            exchange="b",
            symbol="BTC-USDT",
            bids=[OrderBookLevel(price=102.0, qty=3.0)],
            asks=[OrderBookLevel(price=103.0, qty=3.0)],
            ts_event=1.0,
            ts_ingest=10.0,
        )
        opportunities = detect_spatial_opportunities(
            {"a": buy_book, "b": sell_book},
            settings=settings,
            now=10.0,
        )
        self.assertEqual(len(opportunities), 1)
        best = opportunities[0]
        self.assertEqual(best.buy_exchange, "a")
        self.assertEqual(best.sell_exchange, "b")
        self.assertAlmostEqual(best.levtsov_spread_pct, (1.0 - 100.0 / 102.0) * 100.0, places=6)
        self.assertGreater(best.net_edge_pct, 0.0)
        self.assertLessEqual(best.buy_vwap * best.available_qty, settings.trade_notional_usdt + 1e-8)


if __name__ == "__main__":
    unittest.main()
