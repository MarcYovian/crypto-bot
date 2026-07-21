import sqlite3
import os
from backend.config import DB_NAME
from backend.logger import logger

def get_connection():
    """Membuat dan mengembalikan koneksi SQLite dengan mode WAL (Write-Ahead Logging)."""
    os.makedirs(os.path.dirname(DB_NAME), exist_ok=True)
    conn = sqlite3.connect(DB_NAME)
    # Aktifkan WAL mode untuk performa & concurrency antara Bot dan Web API
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn

def init_db():
    """Membuat tabel-tabel database sesuai PRD-V2.md jika belum ada."""
    logger.info("Inisialisasi database SQLite (PRD-V2)...")
    conn = get_connection()
    c = conn.cursor()

    # 1. TABEL POSISI AKTIF (active_trades)
    c.execute('''CREATE TABLE IF NOT EXISTS active_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    sl_price REAL NOT NULL,
                    tp1_price REAL NOT NULL,
                    tp2_price REAL NOT NULL,
                    tp3_price REAL,
                    initial_qty REAL NOT NULL,
                    remaining_qty REAL NOT NULL,
                    tp_stage INTEGER DEFAULT 0,
                    accumulated_realized_pnl REAL DEFAULT 0.0,
                    accumulated_commission REAL DEFAULT 0.0,
                    accumulated_funding REAL DEFAULT 0.0,
                    is_active INTEGER DEFAULT 1,
                    entry_order_id TEXT,
                    sl_order_id TEXT,
                    tp1_order_id TEXT,
                    tp2_order_id TEXT,
                    tp3_order_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    # 2. TABEL JURNAL PERFORMA (trade_history)
    c.execute('''CREATE TABLE IF NOT EXISTS trade_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    gross_pnl_usd REAL NOT NULL,
                    total_commission_usd REAL NOT NULL,
                    total_funding_usd REAL NOT NULL,
                    net_pnl_usd REAL NOT NULL,
                    net_pnl_percent REAL NOT NULL,
                    close_reason TEXT NOT NULL,
                    duration_minutes INTEGER,
                    closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    # 3. TABEL EVENT & PARSIAL CLOSE (trade_events)
    c.execute('''CREATE TABLE IF NOT EXISTS trade_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    price REAL NOT NULL,
                    qty REAL NOT NULL,
                    realized_pnl_usd REAL DEFAULT 0.0,
                    commission_usd REAL DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (trade_id) REFERENCES active_trades(id)
                )''')

    # 4. TABEL WATCHLIST & SCANNER MARKET (watchlist_scanner)
    c.execute('''CREATE TABLE IF NOT EXISTS watchlist_scanner (
                    symbol TEXT PRIMARY KEY,
                    price REAL,
                    change_24h REAL,
                    ma50_distance_pct REAL,
                    rsi_14 REAL,
                    status_signal TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    # 5. TABEL KONFIGURASI DINAMIS BOT (bot_config)
    c.execute('''CREATE TABLE IF NOT EXISTS bot_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')

    # Seed default config jika belum ada
    default_configs = [
        ("risk_mode", "DAILY_ANCHOR"),
        ("risk_pct", "0.02"),
        ("daily_anchor_balance", "0.0")
    ]
    for k, v in default_configs:
        c.execute("INSERT OR IGNORE INTO bot_config (key, value) VALUES (?, ?)", (k, v))

    # Auto-migration jika tabel lama sudah ada
    migrations = [
        ("active_trades", "entry_price", "REAL DEFAULT 0.0"),
        ("active_trades", "sl_price", "REAL DEFAULT 0.0"),
        ("active_trades", "tp1_price", "REAL DEFAULT 0.0"),
        ("active_trades", "tp2_price", "REAL DEFAULT 0.0"),
        ("active_trades", "tp3_price", "REAL DEFAULT 0.0"),
        ("active_trades", "initial_qty", "REAL DEFAULT 0.0"),
        ("active_trades", "remaining_qty", "REAL DEFAULT 0.0"),
        ("active_trades", "accumulated_realized_pnl", "REAL DEFAULT 0.0"),
        ("active_trades", "accumulated_commission", "REAL DEFAULT 0.0"),
        ("active_trades", "accumulated_funding", "REAL DEFAULT 0.0"),
        ("active_trades", "updated_at", "TIMESTAMP")
    ]
    for table, col, col_def in migrations:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}")
            logger.info(f"Migrasi database: menambahkan kolom '{col}' ke tabel {table}.")
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()
    logger.info("Inisialisasi database SQLite (PRD-V2) selesai.")
