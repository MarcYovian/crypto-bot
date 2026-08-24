```sql
PRAGMA foreign_keys = ON;

-- =========================================================
-- 1. BOT SETTINGS
-- Menyimpan konfigurasi global bot
-- =========================================================
CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 2. DAILY RISK CONFIG
-- Snapshot risk harian (00:00 WIB)
-- =========================================================
CREATE TABLE IF NOT EXISTS daily_risk_config (
    date TEXT PRIMARY KEY,                 -- YYYY-MM-DD

    balance REAL NOT NULL,
    risk_percent REAL NOT NULL,
    risk_amount REAL NOT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 3. TRADING SIGNALS
-- =========================================================
CREATE TABLE IF NOT EXISTS trading_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    telegram_message_id INTEGER,
    source TEXT NOT NULL,

    symbol TEXT NOT NULL,

    side TEXT NOT NULL
        CHECK(side IN ('BUY','SELL')),

    entry_min REAL,
    entry_max REAL,

    sl_price REAL NOT NULL,

    tp1_price REAL,
    tp2_price REAL,
    tp3_price REAL,

    confidence REAL,

    status TEXT NOT NULL DEFAULT 'RECEIVED'
        CHECK(status IN (
            'RECEIVED',
            'EXECUTED',
            'REJECTED',
            'CANCELLED',
            'EXPIRED'
        )),

    confirmation_status TEXT NOT NULL DEFAULT 'NOT_REQUIRED'
        CHECK(confirmation_status IN (
            'NOT_REQUIRED',
            'PENDING',
            'APPROVED',
            'REJECTED'
        )),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 4. TRADES
-- =========================================================
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    signal_id INTEGER,

    symbol TEXT NOT NULL,

    side TEXT NOT NULL
        CHECK(side IN ('BUY','SELL')),

    status TEXT NOT NULL DEFAULT 'WAITING_ENTRY'
        CHECK(status IN (
            'WAITING_ENTRY',
            'OPEN',
            'PARTIAL',
            'CLOSED',
            'CANCELLED'
        )),

    entry_price REAL,
    avg_entry_price REAL,

    sl_price REAL NOT NULL,

    tp1_price REAL,
    tp2_price REAL,
    tp3_price REAL,

    leverage INTEGER NOT NULL,

    margin_mode TEXT NOT NULL DEFAULT 'ISOLATED'
        CHECK(margin_mode IN ('ISOLATED','CROSSED')),

    position_size REAL NOT NULL,
    remaining_qty REAL NOT NULL,

    opened_at DATETIME,
    closed_at DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(signal_id)
        REFERENCES trading_signals(id)
        ON DELETE SET NULL
);

-- =========================================================
-- 5. TRADE RISK
-- =========================================================
CREATE TABLE IF NOT EXISTS trade_risk (

    trade_id INTEGER PRIMARY KEY,

    risk_date TEXT NOT NULL,

    entry REAL NOT NULL,

    stop REAL NOT NULL,

    stop_distance REAL NOT NULL,

    qty REAL NOT NULL,

    margin REAL NOT NULL,

    leverage INTEGER NOT NULL,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(trade_id)
        REFERENCES trades(id)
        ON DELETE CASCADE,

    FOREIGN KEY(risk_date)
        REFERENCES daily_risk_config(date)
);

-- =========================================================
-- 6. ORDERS
-- =========================================================
CREATE TABLE IF NOT EXISTS orders (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    trade_id INTEGER NOT NULL,

    binance_order_id TEXT UNIQUE,
    client_order_id TEXT UNIQUE,

    purpose TEXT NOT NULL
        CHECK(purpose IN (
            'ENTRY',
            'TP1',
            'TP2',
            'TP3',
            'SL',
            'BEP_SL',
            'TRAILING_SL',
            'MANUAL_CLOSE'
        )),

    type TEXT NOT NULL
        CHECK(type IN (
            'MARKET',
            'LIMIT',
            'STOP_MARKET',
            'TAKE_PROFIT_MARKET',
            'TRAILING_STOP_MARKET'
        )),

    side TEXT NOT NULL
        CHECK(side IN ('BUY','SELL')),

    price REAL,

    qty REAL NOT NULL,

    filled_qty REAL DEFAULT 0,

    status TEXT NOT NULL DEFAULT 'NEW'
        CHECK(status IN (
            'NEW',
            'PARTIALLY_FILLED',
            'FILLED',
            'CANCELED',
            'EXPIRED',
            'REJECTED'
        )),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(trade_id)
        REFERENCES trades(id)
        ON DELETE CASCADE
);

-- =========================================================
-- 7. EXECUTIONS
-- =========================================================
CREATE TABLE IF NOT EXISTS executions (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    order_id INTEGER NOT NULL,

    trade_id INTEGER NOT NULL,

    price REAL NOT NULL,

    qty REAL NOT NULL,

    commission REAL DEFAULT 0,

    commission_asset TEXT DEFAULT 'USDT',

    realized_pnl REAL DEFAULT 0,

    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(order_id)
        REFERENCES orders(id)
        ON DELETE CASCADE,

    FOREIGN KEY(trade_id)
        REFERENCES trades(id)
        ON DELETE CASCADE
);

-- =========================================================
-- 8. TRADE EVENTS
-- =========================================================
CREATE TABLE IF NOT EXISTS trade_events (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    trade_id INTEGER NOT NULL,

    event_type TEXT NOT NULL
        CHECK(event_type IN (
            'ENTRY',
            'TP1',
            'TP2',
            'TP3',
            'SL',
            'SL_MOVED_TO_BEP',
            'TRAILING_ENABLED',
            'MANUAL_CLOSE',
            'FORCE_CLOSE',
            'FUNDING'
        )),

    payload_json TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY(trade_id)
        REFERENCES trades(id)
        ON DELETE CASCADE
);

-- =========================================================
-- 9. TRADE SUMMARY
-- =========================================================
CREATE TABLE IF NOT EXISTS trade_summary (

    trade_id INTEGER PRIMARY KEY,

    gross_pnl REAL NOT NULL,

    net_pnl REAL NOT NULL,

    commission REAL NOT NULL,

    funding REAL DEFAULT 0,

    roi REAL NOT NULL,

    rr REAL NOT NULL,

    win INTEGER NOT NULL
        CHECK(win IN (0,1)),

    duration_seconds INTEGER NOT NULL,

    close_reason TEXT NOT NULL,

    closed_at DATETIME NOT NULL,

    FOREIGN KEY(trade_id)
        REFERENCES trades(id)
        ON DELETE CASCADE
);

-- =========================================================
-- 10. WATCHLIST
-- =========================================================
CREATE TABLE IF NOT EXISTS watchlist (

    symbol TEXT PRIMARY KEY,

    enabled INTEGER DEFAULT 1
        CHECK(enabled IN (0,1)),

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- 11. BOT LOGS
-- =========================================================
CREATE TABLE IF NOT EXISTS bot_logs (

    id INTEGER PRIMARY KEY AUTOINCREMENT,

    level TEXT NOT NULL
        CHECK(level IN (
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL'
        )),

    message TEXT NOT NULL,

    context_json TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- =========================================================
-- INDEX
-- =========================================================

CREATE INDEX IF NOT EXISTS idx_signal_status
ON trading_signals(status);

CREATE INDEX IF NOT EXISTS idx_signal_symbol
ON trading_signals(symbol);

CREATE INDEX IF NOT EXISTS idx_trade_status
ON trades(status);

CREATE INDEX IF NOT EXISTS idx_trade_symbol
ON trades(symbol);

CREATE INDEX IF NOT EXISTS idx_trade_signal
ON trades(signal_id);

CREATE INDEX IF NOT EXISTS idx_trade_risk_date
ON trade_risk(risk_date);

CREATE INDEX IF NOT EXISTS idx_orders_trade
ON orders(trade_id);

CREATE INDEX IF NOT EXISTS idx_orders_status
ON orders(status);

CREATE INDEX IF NOT EXISTS idx_orders_binance_id 
ON orders(binance_order_id);
CREATE INDEX IF NOT EXISTS idx_orders_purpose 
ON orders(purpose);

CREATE INDEX IF NOT EXISTS idx_executions_trade
ON executions(trade_id);

CREATE INDEX IF NOT EXISTS idx_trade_events_trade
ON trade_events(trade_id);

CREATE INDEX IF NOT EXISTS idx_bot_logs_level
ON bot_logs(level);
```