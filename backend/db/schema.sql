-- ========================================================
-- SCHEMA DATABASE CRYPTO BOT (SQLite)
-- File ini digunakan sebagai referensi DDL struktur tabel database.
-- ========================================================

CREATE TABLE IF NOT EXISTS active_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,             -- 'BUY' (LONG) atau 'SELL' (SHORT)
    entry REAL NOT NULL,            -- Harga Entry
    sl REAL NOT NULL,               -- Harga Stop Loss
    tp1 REAL NOT NULL,              -- Harga Take Profit 1 (50%)
    tp2 REAL NOT NULL,              -- Harga Take Profit 2 (25%)
    tp3 REAL NOT NULL,              -- Harga Take Profit 3 (25%)
    tp_stage INTEGER DEFAULT 0,     -- Stage TP: 0 (Belum TP), 1 (TP1 Hit), 2 (TP2 Hit), 3 (TP3 Hit)
    is_active INTEGER DEFAULT 1,    -- Status: 1 (Aktif), 0 (Selesai/Batal)
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP, -- Waktu pembuatan trade
    entry_order_id TEXT,            -- Binance Order ID untuk Entry (Market/Limit)
    sl_order_id TEXT,               -- Binance Order ID untuk Stop Loss
    tp1_order_id TEXT,              -- Binance Order ID untuk Limit TP1
    tp2_order_id TEXT,              -- Binance Order ID untuk Limit TP2
    tp3_order_id TEXT               -- Binance Order ID untuk Limit TP3
);
