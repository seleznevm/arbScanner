from __future__ import annotations

import time

from arbscanner.config import Settings
from arbscanner.models import Opportunity, OrderBookLevel, OrderBookSnapshot


def compute_vwap(levels: list[OrderBookLevel], qty: float) -> tuple[float, float]:
    if qty <= 0:
        return 0.0, 0.0
    remaining = qty
    notional = 0.0
    filled = 0.0
    for level in levels:
        if remaining <= 0:
            break
        take = min(level.qty, remaining)
        if take <= 0:
            continue
        notional += level.price * take
        filled += take
        remaining -= take
    if filled <= 0:
        return 0.0, 0.0
    return notional / filled, filled


def _sum_qty(levels: list[OrderBookLevel]) -> float:
    return sum(level.qty for level in levels)


def detect_spatial_opportunities(
    orderbooks: dict[str, OrderBookSnapshot],
    settings: Settings,
    trade_notional_usdt: float | None = None,
    now: float | None = None,
) -> list[Opportunity]:
    now_ts = now or time.time()
    opportunities: list[Opportunity] = []
    exchanges = sorted(orderbooks.keys())

    target_notional = (
        trade_notional_usdt
        if trade_notional_usdt is not None
        else settings.trade_notional_usdt
    )

    for buy_exchange in exchanges:
        buy_book = orderbooks[buy_exchange]
        if not buy_book.is_healthy:
            continue
        if now_ts - buy_book.ts_ingest > settings.stale_after_sec:
            continue
        for sell_exchange in exchanges:
            if sell_exchange == buy_exchange:
                continue
            sell_book = orderbooks[sell_exchange]
            if not sell_book.is_healthy:
                continue
            if now_ts - sell_book.ts_ingest > settings.stale_after_sec:
                continue

            if not buy_book.asks:
                continue
            best_ask = buy_book.asks[0].price
            if best_ask <= 0:
                continue
            target_qty = target_notional / best_ask
            max_fill_qty = min(_sum_qty(buy_book.asks), _sum_qty(sell_book.bids))
            max_qty = min(target_qty, max_fill_qty)
            if max_qty <= 0.0:
                continue

            buy_vwap, buy_filled = compute_vwap(buy_book.asks, max_qty)
            sell_vwap, sell_filled = compute_vwap(sell_book.bids, max_qty)
            qty = min(buy_filled, sell_filled)
            if qty <= 0:
                continue

            if buy_vwap <= 0 or sell_vwap <= 0:
                continue
            gross_edge_pct = ((sell_vwap - buy_vwap) / buy_vwap) * 100.0
            fees_pct = 2.0 * settings.taker_fee_bps / 100.0
            slippage_pct = settings.slippage_bps / 100.0
            withdraw_pct = settings.withdraw_cost_usdt / (buy_vwap * qty) * 100.0
            net_edge_pct = gross_edge_pct - fees_pct - slippage_pct - withdraw_pct

            if net_edge_pct < settings.min_net_edge_pct:
                continue

            expected_profit = buy_vwap * qty * (net_edge_pct / 100.0)
            opportunities.append(
                Opportunity(
                    opportunity_type="spatial",
                    symbol=buy_book.symbol,
                    buy_exchange=buy_exchange,
                    sell_exchange=sell_exchange,
                    buy_vwap=buy_vwap,
                    sell_vwap=sell_vwap,
                    gross_edge_pct=gross_edge_pct,
                    net_edge_pct=net_edge_pct,
                    expected_profit_usdt=expected_profit,
                    available_qty=qty,
                    risk_flag=_risk_flag(net_edge_pct),
                    ts_detected=now_ts,
                )
            )

    opportunities.sort(key=lambda item: item.net_edge_pct, reverse=True)
    return opportunities


def detect_triangular_opportunities(
    orderbooks: dict[str, OrderBookSnapshot], settings: Settings
) -> list[Opportunity]:
    # Placeholder for the next milestone: graph-based Bellman-Ford cycles.
    _ = (orderbooks, settings)
    return []


def _risk_flag(net_edge_pct: float) -> str:
    if net_edge_pct >= 0.75:
        return "green"
    if net_edge_pct >= 0.3:
        return "yellow"
    return "red"
