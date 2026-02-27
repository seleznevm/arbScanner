from __future__ import annotations

from arbscanner.config import Settings
from arbscanner.connectors.base import BaseConnector
from arbscanner.connectors.mock_connector import MockConnector
from arbscanner.connectors.real_connector import CCXTOrderBookConnector


def build_mock_connectors(
    exchanges: list[str],
    symbols: list[str],
    interval_ms: int,
    bias_step: float = 0.0045,
) -> list[MockConnector]:
    connectors: list[MockConnector] = []
    mid = len(exchanges) / 2.0
    for idx, exchange in enumerate(exchanges):
        # Deterministic bias creates stable inter-exchange spreads in mock mode.
        bias = (idx - mid) * bias_step
        connectors.append(
            MockConnector(
                exchange=exchange,
                symbols=symbols,
                interval_ms=interval_ms,
                exchange_bias=bias,
                rng_seed=1000 + idx,
            )
        )
    return connectors


def build_real_connectors(
    exchanges: list[str],
    symbols: list[str],
    interval_ms: int,
    depth: int,
    timeout_ms: int,
) -> list[BaseConnector]:
    return [
        CCXTOrderBookConnector(
            exchange=exchange,
            symbols=symbols,
            interval_ms=interval_ms,
            depth=depth,
            timeout_ms=timeout_ms,
        )
        for exchange in exchanges
    ]


def build_connectors(settings: Settings) -> list[BaseConnector]:
    mode = settings.connector_mode.lower()
    if mode == "mock":
        return build_mock_connectors(
            exchanges=settings.exchanges,
            symbols=settings.symbol_universe,
            interval_ms=settings.connector_interval_ms,
            bias_step=settings.mock_exchange_bias_step,
        )
    return build_real_connectors(
        exchanges=settings.exchanges,
        symbols=settings.symbol_universe,
        interval_ms=settings.connector_interval_ms,
        depth=settings.real_orderbook_depth,
        timeout_ms=settings.real_connector_timeout_ms,
    )
