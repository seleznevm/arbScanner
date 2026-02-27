from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_EXCHANGES = [
    "binance",
    "coinbase",
    "kraken",
    "okx",
    "bybit",
    "kucoin",
    "gateio",
    "mexc",
    "bitget",
    "htx",
    "upbit",
    "bingx",
    "bitfinex",
    "xt",
]

DEFAULT_SYMBOLS = ["BTC-USDT", "ETH-USDT", "SOL-USDT"]
DEFAULT_SYMBOL_UNIVERSE = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "XRP-USDT",
    "DAI-USDT",
    "FDUSD-USDT",
    "PYUSD-USDT",
    "ARB-USDT",
    "OP-USDT",
    "MATIC-USDT",
    "POL-USDT",
    "ADA-USDT",
    "DOGE-USDT",
    "AVAX-USDT",
    "DOT-USDT",
    "LINK-USDT",
    "ATOM-USDT",
    "SUI-USDT",
    "SEI-USDT",
    "APT-USDT",
    "TON-USDT",
    "NEAR-USDT",
    "LTC-USDT",
    "BNB-USDT",
    "TRX-USDT",
    "TAO-USDT",
    "FET-USDT",
    "ASI-USDT",
    "RNDR-USDT",
    "RENDER-USDT",
    "HYPE-USDT",
    "ENA-USDT",
    "ONDO-USDT",
    "PEPE-USDT",
    "SHIB-USDT",
    "WIF-USDT",
]


def _csv(raw: str | None, fallback: list[str]) -> list[str]:
    if not raw:
        return fallback
    values = [item.strip() for item in raw.split(",")]
    filtered = [item for item in values if item]
    return filtered if filtered else fallback


@dataclass(slots=True)
class Settings:
    scan_interval_sec: int = 10
    stale_after_sec: int = 30
    trade_notional_usdt: float = 1000.0
    min_spread_diff_pct: float = 5.0
    min_net_edge_pct: float = 0.2
    taker_fee_bps: float = 10.0
    slippage_bps: float = 5.0
    withdraw_cost_usdt: float = 2.0
    broker_mode: str = "auto"
    redis_url: str | None = None
    redis_channel: str = "opportunities_feed"
    run_scanner_in_api: bool = True
    connector_mode: str = "real"
    connector_interval_ms: int = 350
    real_orderbook_depth: int = 20
    real_connector_timeout_ms: int = 10000
    mock_exchange_bias_step: float = 0.0045
    exchanges: list[str] = field(default_factory=lambda: DEFAULT_EXCHANGES.copy())
    symbols: list[str] = field(default_factory=lambda: DEFAULT_SYMBOLS.copy())
    symbol_universe: list[str] = field(
        default_factory=lambda: DEFAULT_SYMBOL_UNIVERSE.copy()
    )
    telegram_bot_token: str | None = None
    telegram_chat_ids: list[str] = field(default_factory=list)
    telegram_min_interval_sec: float = 1.0
    telegram_max_rows: int = 5

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            scan_interval_sec=int(os.getenv("SCAN_INTERVAL_SEC", "10")),
            stale_after_sec=int(os.getenv("STALE_AFTER_SEC", "30")),
            trade_notional_usdt=float(os.getenv("TRADE_NOTIONAL_USDT", "1000")),
            min_spread_diff_pct=float(os.getenv("MIN_SPREAD_DIFF_PCT", "5")),
            min_net_edge_pct=float(os.getenv("MIN_NET_EDGE_PCT", "0.2")),
            taker_fee_bps=float(os.getenv("TAKER_FEE_BPS", "10")),
            slippage_bps=float(os.getenv("SLIPPAGE_BPS", "5")),
            withdraw_cost_usdt=float(os.getenv("WITHDRAW_COST_USDT", "2")),
            broker_mode=os.getenv("BROKER_MODE", "auto").lower(),
            redis_url=os.getenv("REDIS_URL"),
            redis_channel=os.getenv("REDIS_CHANNEL", "opportunities_feed"),
            run_scanner_in_api=os.getenv("RUN_SCANNER_IN_API", "true").lower()
            in {"1", "true", "yes", "on"},
            connector_mode=os.getenv("CONNECTOR_MODE", "real").lower(),
            connector_interval_ms=int(os.getenv("CONNECTOR_INTERVAL_MS", "350")),
            real_orderbook_depth=int(os.getenv("REAL_ORDERBOOK_DEPTH", "20")),
            real_connector_timeout_ms=int(
                os.getenv("REAL_CONNECTOR_TIMEOUT_MS", "10000")
            ),
            mock_exchange_bias_step=float(
                os.getenv("MOCK_EXCHANGE_BIAS_STEP", "0.0045")
            ),
            exchanges=_csv(os.getenv("EXCHANGES"), DEFAULT_EXCHANGES.copy()),
            symbols=_csv(os.getenv("SYMBOLS"), DEFAULT_SYMBOLS.copy()),
            symbol_universe=_csv(
                os.getenv("SYMBOL_UNIVERSE"),
                DEFAULT_SYMBOL_UNIVERSE.copy(),
            ),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            telegram_chat_ids=_csv(os.getenv("TELEGRAM_CHAT_IDS"), []),
            telegram_min_interval_sec=float(
                os.getenv("TELEGRAM_MIN_INTERVAL_SEC", "1.0")
            ),
            telegram_max_rows=int(os.getenv("TELEGRAM_MAX_ROWS", "5")),
        )

    @property
    def use_redis(self) -> bool:
        if self.broker_mode == "redis":
            return True
        if self.broker_mode == "inmemory":
            return False
        return bool(self.redis_url)
