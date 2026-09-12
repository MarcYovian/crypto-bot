-- =============================================================================
-- SMC CryptoBot Complete Relational Database Schema (DDL)
-- Dialect: PostgreSQL (Primary) / Compatible with SQLAlchemy 2.0 ORM
-- Total Tables: 22 Tables across 7 Functional Domains
-- =============================================================================

-- =============================================================================
-- DOMAIN 1: EXCHANGE & ACCOUNT MANAGEMENT
-- =============================================================================

-- 1. EXCHANGES
CREATE TABLE IF NOT EXISTS exchanges (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    status BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_exchanges_status ON exchanges(status);

-- 2. TRADING ACCOUNTS
CREATE TABLE IF NOT EXISTS trading_accounts (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id) ON DELETE RESTRICT,
    name VARCHAR(100) NOT NULL,
    account_type VARCHAR(20) NOT NULL DEFAULT 'FUTURES',
    environment VARCHAR(20) NOT NULL DEFAULT 'TESTNET',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_trading_account_name UNIQUE (name),
    CONSTRAINT chk_account_type CHECK (account_type IN ('SPOT', 'MARGIN', 'FUTURES')),
    CONSTRAINT chk_account_env CHECK (environment IN ('MAINNET', 'TESTNET', 'SANDBOX'))
);
CREATE INDEX IF NOT EXISTS idx_trading_accounts_exchange ON trading_accounts(exchange_id);
CREATE INDEX IF NOT EXISTS idx_trading_accounts_active ON trading_accounts(is_active);

-- 3. TRADING CREDENTIALS
CREATE TABLE IF NOT EXISTS trading_credentials (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE CASCADE,
    key_name VARCHAR(100) NOT NULL,
    encrypted_api_key TEXT NOT NULL,
    encrypted_secret_key TEXT NOT NULL,
    encrypted_passphrase TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_account_key_name UNIQUE (account_id, key_name)
);
CREATE INDEX IF NOT EXISTS idx_credentials_account ON trading_credentials(account_id);
CREATE INDEX IF NOT EXISTS idx_credentials_active ON trading_credentials(is_active);

-- =============================================================================
-- DOMAIN 2: INSTRUMENT & MARKET DATA
-- =============================================================================

-- 4. INSTRUMENTS
CREATE TABLE IF NOT EXISTS instruments (
    id SERIAL PRIMARY KEY,
    exchange_id INTEGER NOT NULL REFERENCES exchanges(id) ON DELETE RESTRICT,
    symbol VARCHAR(50) NOT NULL,
    base_asset VARCHAR(20) NOT NULL,
    quote_asset VARCHAR(20) NOT NULL,
    tick_size NUMERIC(18, 8) NOT NULL,
    step_size NUMERIC(18, 8) NOT NULL,
    min_qty NUMERIC(18, 8) NOT NULL,
    min_notional NUMERIC(18, 8) NOT NULL,
    price_precision INTEGER NOT NULL,
    qty_precision INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_exchange_symbol UNIQUE (exchange_id, symbol),
    CONSTRAINT chk_instrument_status CHECK (status IN ('ACTIVE', 'INACTIVE', 'DELISTED'))
);
CREATE INDEX IF NOT EXISTS idx_instruments_symbol ON instruments(symbol);
CREATE INDEX IF NOT EXISTS idx_instruments_status ON instruments(status);

-- 5. INSTRUMENT LEVERAGE BRACKETS
CREATE TABLE IF NOT EXISTS instrument_leverage_brackets (
    id SERIAL PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    bracket_level INTEGER NOT NULL,
    max_leverage INTEGER NOT NULL,
    floor_notional NUMERIC(18, 8) NOT NULL,
    cap_notional NUMERIC(18, 8) NOT NULL,
    maintenance_margin_ratio NUMERIC(10, 6) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_instrument_bracket UNIQUE (instrument_id, bracket_level)
);
CREATE INDEX IF NOT EXISTS idx_bracket_instrument ON instrument_leverage_brackets(instrument_id);

-- 6. WATCHLIST
CREATE TABLE IF NOT EXISTS watchlist (
    id SERIAL PRIMARY KEY,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE CASCADE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_watchlist_instrument UNIQUE (instrument_id)
);
CREATE INDEX IF NOT EXISTS idx_watchlist_active ON watchlist(is_active);

-- =============================================================================
-- DOMAIN 3: SIGNAL & STRATEGY
-- =============================================================================

-- 7. SIGNAL PROVIDERS
CREATE TABLE IF NOT EXISTS signal_providers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(50) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_signal_providers_active ON signal_providers(is_active);

-- 8. STRATEGIES
CREATE TABLE IF NOT EXISTS strategies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    version VARCHAR(20) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_strategies_name_version UNIQUE (name, version)
);
CREATE INDEX IF NOT EXISTS idx_strategies_active ON strategies(is_active);

-- 9. TRADING SIGNALS
CREATE TABLE IF NOT EXISTS trading_signals (
    id SERIAL PRIMARY KEY,
    provider_id INTEGER NOT NULL REFERENCES signal_providers(id) ON DELETE RESTRICT,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE RESTRICT,
    telegram_message_id BIGINT,
    timeframe VARCHAR(20),
    side VARCHAR(10) NOT NULL,
    entry_min NUMERIC(18, 8),
    entry_max NUMERIC(18, 8),
    sl_price NUMERIC(18, 8) NOT NULL,
    tp1_price NUMERIC(18, 8),
    tp2_price NUMERIC(18, 8),
    tp3_price NUMERIC(18, 8),
    confidence NUMERIC(5, 4),
    raw_message TEXT,
    parsed_json TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'RECEIVED',
    confirmation_status VARCHAR(20) NOT NULL DEFAULT 'NOT_REQUIRED',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_signal_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT chk_signal_status CHECK (status IN ('RECEIVED', 'PARSED', 'EXECUTED', 'REJECTED', 'EXPIRED', 'CANCELLED')),
    CONSTRAINT chk_signal_confirmation CHECK (confirmation_status IN ('NOT_REQUIRED', 'PENDING', 'APPROVED', 'REJECTED'))
);
CREATE INDEX IF NOT EXISTS idx_signals_provider ON trading_signals(provider_id);
CREATE INDEX IF NOT EXISTS idx_signals_instrument ON trading_signals(instrument_id);
CREATE INDEX IF NOT EXISTS idx_signals_status ON trading_signals(status);
CREATE INDEX IF NOT EXISTS idx_signals_tg_msg_id ON trading_signals(telegram_message_id);

-- =============================================================================
-- DOMAIN 4: RISK MANAGEMENT
-- =============================================================================

-- 10. RISK PROFILES
CREATE TABLE IF NOT EXISTS risk_profiles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE,
    risk_percent NUMERIC(10, 4) NOT NULL,
    max_daily_loss NUMERIC(18, 8) NOT NULL,
    max_open_trade INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_risk_profiles_is_active ON risk_profiles(is_active);

-- 11. DAILY RISK CONFIG
CREATE TABLE IF NOT EXISTS daily_risk_config (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE RESTRICT,
    risk_profile_id INTEGER NOT NULL REFERENCES risk_profiles(id) ON DELETE RESTRICT,
    date DATE NOT NULL,
    balance NUMERIC(18, 8) NOT NULL,
    risk_amount NUMERIC(18, 8) NOT NULL,
    daily_risk_amount NUMERIC(18, 8) NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uk_daily_risk_account_date UNIQUE (account_id, date)
);
CREATE INDEX IF NOT EXISTS idx_daily_risk_date ON daily_risk_config(date);
CREATE INDEX IF NOT EXISTS idx_daily_risk_account ON daily_risk_config(account_id);
CREATE INDEX IF NOT EXISTS idx_daily_risk_profile ON daily_risk_config(risk_profile_id);

-- =============================================================================
-- DOMAIN 5: TRADE LIFECYCLE
-- =============================================================================

-- 12. TRADES
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES trading_accounts(id) ON DELETE RESTRICT,
    strategy_id INTEGER REFERENCES strategies(id) ON DELETE SET NULL,
    signal_id INTEGER REFERENCES trading_signals(id) ON DELETE SET NULL,
    instrument_id INTEGER NOT NULL REFERENCES instruments(id) ON DELETE RESTRICT,
    side VARCHAR(10) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'WAITING_ENTRY',
    entry_price NUMERIC(18, 8),
    avg_entry_price NUMERIC(18, 8),
    sl_price NUMERIC(18, 8) NOT NULL,
    tp1_price NUMERIC(18, 8),
    tp2_price NUMERIC(18, 8),
    tp3_price NUMERIC(18, 8),
    leverage INTEGER NOT NULL,
    margin_mode VARCHAR(20) NOT NULL DEFAULT 'ISOLATED',
    position_size NUMERIC(18, 8) NOT NULL,
    remaining_qty NUMERIC(18, 8) NOT NULL,
    opened_at TIMESTAMP WITH TIME ZONE,
    closed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_trade_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT chk_trade_status CHECK (status IN ('WAITING_ENTRY', 'OPEN', 'PARTIAL', 'CLOSED', 'CANCELLED'))
);
CREATE INDEX IF NOT EXISTS idx_trades_account ON trades(account_id);
CREATE INDEX IF NOT EXISTS idx_trades_instrument ON trades(instrument_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at);

-- 13. TRADE RISK
CREATE TABLE IF NOT EXISTS trade_risk (
    trade_id INTEGER PRIMARY KEY REFERENCES trades(id) ON DELETE CASCADE,
    daily_risk_id INTEGER NOT NULL REFERENCES daily_risk_config(id) ON DELETE RESTRICT,
    entry NUMERIC(18, 8) NOT NULL,
    stop NUMERIC(18, 8) NOT NULL,
    stop_distance NUMERIC(18, 8) NOT NULL,
    risk_per_unit NUMERIC(18, 8) NOT NULL,
    risk_amount NUMERIC(18, 8) NOT NULL,
    qty NUMERIC(18, 8) NOT NULL,
    margin_used NUMERIC(18, 8) NOT NULL,
    leverage INTEGER NOT NULL,
    liq_price_est NUMERIC(18, 8),
    risk_status VARCHAR(20) NOT NULL DEFAULT 'ACCEPTABLE'
);
CREATE INDEX IF NOT EXISTS idx_trade_risk_daily ON trade_risk(daily_risk_id);

-- 14. ORDERS
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    exchange_order_id VARCHAR(100) UNIQUE,
    client_order_id VARCHAR(100) UNIQUE,
    purpose VARCHAR(30) NOT NULL,
    order_type VARCHAR(30) NOT NULL,
    side VARCHAR(10) NOT NULL,
    reduce_only BOOLEAN NOT NULL DEFAULT FALSE,
    close_position BOOLEAN NOT NULL DEFAULT FALSE,
    time_in_force VARCHAR(20),
    price NUMERIC(18, 8),
    qty NUMERIC(18, 8) NOT NULL,
    filled_qty NUMERIC(18, 8) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'NEW',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_order_purpose CHECK (purpose IN ('ENTRY', 'TP1', 'TP2', 'TP3', 'SL', 'BEP_SL', 'TRAILING_SL', 'MANUAL_CLOSE')),
    CONSTRAINT chk_order_type CHECK (order_type IN ('MARKET', 'LIMIT', 'STOP_MARKET', 'TAKE_PROFIT_MARKET', 'TRAILING_STOP_MARKET')),
    CONSTRAINT chk_order_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT chk_order_status CHECK (status IN ('NEW', 'PARTIALLY_FILLED', 'FILLED', 'CANCELED', 'EXPIRED', 'REJECTED'))
);
CREATE INDEX IF NOT EXISTS idx_orders_trade ON orders(trade_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_purpose ON orders(purpose);
CREATE INDEX IF NOT EXISTS idx_orders_exchange_order_id ON orders(exchange_order_id);

-- 15. EXECUTIONS
CREATE TABLE IF NOT EXISTS executions (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    exchange_execution_id VARCHAR(100) UNIQUE,
    price NUMERIC(18, 8) NOT NULL,
    qty NUMERIC(18, 8) NOT NULL,
    commission NUMERIC(18, 8) NOT NULL DEFAULT 0,
    commission_asset VARCHAR(20),
    is_maker BOOLEAN NOT NULL DEFAULT FALSE,
    executed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_executions_order ON executions(order_id);
CREATE INDEX IF NOT EXISTS idx_executions_trade ON executions(trade_id);
CREATE INDEX IF NOT EXISTS idx_executions_executed_at ON executions(executed_at);

-- 16. TRADE EVENTS
CREATE TABLE IF NOT EXISTS trade_events (
    id SERIAL PRIMARY KEY,
    trade_id INTEGER NOT NULL REFERENCES trades(id) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,
    payload_json TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trade_events_trade ON trade_events(trade_id);
CREATE INDEX IF NOT EXISTS idx_trade_events_type ON trade_events(event_type);

-- 17. TRADE SUMMARY
CREATE TABLE IF NOT EXISTS trade_summary (
    trade_id INTEGER PRIMARY KEY REFERENCES trades(id) ON DELETE CASCADE,
    entry_price NUMERIC(18, 8) NOT NULL,
    exit_price NUMERIC(18, 8) NOT NULL,
    total_qty NUMERIC(18, 8) NOT NULL,
    gross_pnl NUMERIC(18, 8) NOT NULL,
    net_pnl NUMERIC(18, 8) NOT NULL,
    fee_total NUMERIC(18, 8) NOT NULL,
    r_multiple NUMERIC(10, 4),
    exit_reason VARCHAR(50) NOT NULL,
    hold_duration_sec INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- DOMAIN 6: SYSTEM & OPERATIONS
-- =============================================================================

-- 18. USERS
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'ADMIN',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

-- 19. BOT SETTINGS
CREATE TABLE IF NOT EXISTS bot_settings (
    key VARCHAR(100) PRIMARY KEY,
    category VARCHAR(50),
    type VARCHAR(20),
    value TEXT NOT NULL,
    description TEXT,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bot_settings_category ON bot_settings(category);

-- 20. BOT LOGS
CREATE TABLE IF NOT EXISTS bot_logs (
    id SERIAL PRIMARY KEY,
    module VARCHAR(50),
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    context_json TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_bot_log_level CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'))
);
CREATE INDEX IF NOT EXISTS idx_bot_logs_level ON bot_logs(level);
CREATE INDEX IF NOT EXISTS idx_bot_logs_module ON bot_logs(module);
CREATE INDEX IF NOT EXISTS idx_bot_logs_level_created ON bot_logs(level, created_at);

-- =============================================================================
-- DOMAIN 7: TASK SCHEDULING & BACKGROUND JOBS
-- =============================================================================

-- 21. SCHEDULER TASKS
CREATE TABLE IF NOT EXISTS scheduler_tasks (
    id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    cron_expr VARCHAR(50) NOT NULL,
    timezone VARCHAR(50) NOT NULL DEFAULT 'Asia/Jakarta',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    misfire_policy VARCHAR(30) NOT NULL DEFAULT 'RUN_LATEST_ONCE',
    last_run_at TIMESTAMP WITH TIME ZONE,
    next_run_at TIMESTAMP WITH TIME ZONE NOT NULL,
    last_status VARCHAR(20) NOT NULL DEFAULT 'IDLE',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scheduler_next_run ON scheduler_tasks(is_active, next_run_at);

-- 22. SCHEDULER TASK RUNS
CREATE TABLE IF NOT EXISTS scheduler_task_runs (
    id SERIAL PRIMARY KEY,
    task_id VARCHAR(50) NOT NULL REFERENCES scheduler_tasks(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING',
    started_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_task_started ON scheduler_task_runs(task_id, started_at);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_status ON scheduler_task_runs(status);