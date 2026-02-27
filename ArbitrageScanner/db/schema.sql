CREATE TABLE IF NOT EXISTS users (
    user_id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    totp_secret TEXT,
    role TEXT NOT NULL DEFAULT 'trader',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_credentials (
    key_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    exchange_name TEXT NOT NULL,
    encrypted_key TEXT NOT NULL,
    encrypted_secret TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS strategy_config (
    config_id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    min_net_edge DOUBLE PRECISION NOT NULL DEFAULT 0.2,
    blacklisted_venues JSONB NOT NULL DEFAULT '[]'::JSONB,
    max_notional DOUBLE PRECISION NOT NULL DEFAULT 1000.0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS instruments_dict (
    symbol TEXT PRIMARY KEY,
    base_asset TEXT NOT NULL,
    quote_asset TEXT NOT NULL,
    tick_size DOUBLE PRECISION NOT NULL,
    min_qty DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arbitrage_log (
    id BIGSERIAL PRIMARY KEY,
    ts_detected TIMESTAMPTZ NOT NULL,
    opportunity_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    buy_exchange TEXT NOT NULL,
    sell_exchange TEXT NOT NULL,
    gross_edge DOUBLE PRECISION NOT NULL,
    net_edge DOUBLE PRECISION NOT NULL,
    available_qty DOUBLE PRECISION NOT NULL,
    expected_profit_usdt DOUBLE PRECISION NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_arbitrage_log_ts ON arbitrage_log (ts_detected DESC);
CREATE INDEX IF NOT EXISTS idx_arbitrage_log_symbol ON arbitrage_log (symbol);
