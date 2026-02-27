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


def compute_fill_for_budget(
    levels: list[OrderBookLevel],
    budget_usdt: float,
) -> tuple[float, float, float]:
    if budget_usdt <= 0:
        return 0.0, 0.0, 0.0

    remaining_budget = budget_usdt
    total_notional = 0.0
    filled_qty = 0.0
    for level in levels:
        if remaining_budget <= 0:
            break
        if level.price <= 0:
            continue
        max_take_qty = remaining_budget / level.price
        take_qty = min(level.qty, max_take_qty)
        if take_qty <= 0:
            continue
        cost = take_qty * level.price
        total_notional += cost
        filled_qty += take_qty
        remaining_budget -= cost
        if take_qty < level.qty:
            # Budget is exhausted inside this level.
            break

    if filled_qty <= 0:
        return 0.0, 0.0, 0.0
    return total_notional / filled_qty, filled_qty, total_notional


def _sum_qty(levels: list[OrderBookLevel]) -> float:
    return sum(level.qty for level in levels)


def detect_spatial_opportunities(
    orderbooks: dict[str, OrderBookSnapshot],
    settings: Settings,
    trade_notional_usdt: float | None = None,
    min_spread_diff_pct: float | None = None,
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
    min_spread = (
        min_spread_diff_pct
        if min_spread_diff_pct is not None
        else settings.min_spread_diff_pct
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

            if not buy_book.asks or not sell_book.bids:
                continue

            _, buy_qty_by_budget, _ = compute_fill_for_budget(
                buy_book.asks,
                target_notional,
            )
            if buy_qty_by_budget <= 0:
                continue
            qty = min(buy_qty_by_budget, _sum_qty(sell_book.bids))
            if qty <= 0:
                continue

            buy_vwap, buy_filled = compute_vwap(buy_book.asks, qty)
            sell_vwap, sell_filled = compute_vwap(sell_book.bids, qty)
            qty = min(buy_filled, sell_filled)
            if qty <= 0:
                continue

            # Re-evaluate VWAP for final executable qty after both-side depth check.
            buy_vwap, _ = compute_vwap(buy_book.asks, qty)
            sell_vwap, _ = compute_vwap(sell_book.bids, qty)
            if buy_vwap <= 0 or sell_vwap <= 0:
                continue

            buy_notional = buy_vwap * qty
            sell_notional = sell_vwap * qty
            if buy_notional <= 0:
                continue

            gross_profit = sell_notional - buy_notional
            gross_edge_pct = (gross_profit / buy_notional) * 100.0
            if gross_edge_pct < min_spread:
                continue

            taker_fee_rate = settings.taker_fee_bps / 10000.0
            slippage_rate = settings.slippage_bps / 10000.0
            fees_cost = (buy_notional + sell_notional) * taker_fee_rate
            slippage_cost = buy_notional * slippage_rate
            withdraw_cost = settings.withdraw_cost_usdt

            net_profit = gross_profit - fees_cost - slippage_cost - withdraw_cost
            net_edge_pct = (net_profit / buy_notional) * 100.0
            if net_edge_pct < settings.min_net_edge_pct:
                continue

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
                    expected_profit_usdt=net_profit,
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
