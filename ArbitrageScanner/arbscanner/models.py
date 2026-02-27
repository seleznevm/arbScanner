from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class OrderBookLevel:
    price: float
    qty: float

    def to_dict(self) -> dict[str, float]:
        return {"price": self.price, "qty": self.qty}


@dataclass(slots=True)
class OrderBookSnapshot:
    exchange: str
    symbol: str
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]
    ts_event: float
    ts_ingest: float
    is_healthy: bool = True
    meta: dict[str, str | float | int | bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "exchange": self.exchange,
            "symbol": self.symbol,
            "bids": [level.to_dict() for level in self.bids],
            "asks": [level.to_dict() for level in self.asks],
            "ts_event": self.ts_event,
            "ts_ingest": self.ts_ingest,
            "is_healthy": self.is_healthy,
            "meta": self.meta,
        }


@dataclass(slots=True)
class Opportunity:
    opportunity_type: str
    symbol: str
    buy_exchange: str
    sell_exchange: str
    buy_vwap: float
    sell_vwap: float
    gross_edge_pct: float
    net_edge_pct: float
    expected_profit_usdt: float
    available_qty: float
    risk_flag: str
    ts_detected: float

    @property
    def fingerprint(self) -> str:
        return (
            f"{self.opportunity_type}:{self.symbol}:{self.buy_exchange}:"
            f"{self.sell_exchange}"
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["id"] = self.fingerprint
        return payload

