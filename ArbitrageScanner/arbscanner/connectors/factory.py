from __future__ import annotations

from arbscanner.connectors.mock_connector import MockConnector


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
