import sqlite3
from config import DB_NAME

def init_db():
    """Membuat tabel database jika belum ada, serta melakukan migrasi kolom jika diperlukan."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS active_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    side TEXT,
                    entry REAL,
                    sl REAL,
                    tp1 REAL,
                    tp2 REAL,
                    tp3 REAL,
                    tp_stage INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    entry_order_id TEXT,
                    sl_order_id TEXT,
                    tp1_order_id TEXT,
                    tp2_order_id TEXT,
                    tp3_order_id TEXT
                )''')
    
    # Migrasi kolom secara bertahap jika tabel sudah ada dari bot versi lama
    for col in ['created_at', 'tp3', 'entry_order_id', 'sl_order_id', 'tp1_order_id', 'tp2_order_id', 'tp3_order_id']:
        try:
            # Deteksi tipe kolom
            col_type = "REAL" if col == "tp3" else "DATETIME" if col == "created_at" else "TEXT"
            c.execute(f"ALTER TABLE active_trades ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            # Abaikan jika kolom sudah ada
            pass
        
    conn.commit()
    conn.close()

def add_trade(symbol, side, entry, sl, tp1, tp2, tp3, entry_order_id=None, sl_order_id=None, tp1_order_id=None, tp2_order_id=None, tp3_order_id=None):
    """Menyimpan data trade baru ke database beserta tracking order ID."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''INSERT INTO active_trades (
                    symbol, side, entry, sl, tp1, tp2, tp3, created_at,
                    entry_order_id, sl_order_id, tp1_order_id, tp2_order_id, tp3_order_id
                 ) 
                 VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?, ?, ?, ?, ?)''', 
              (symbol, side, entry, sl, tp1, tp2, tp3, entry_order_id, sl_order_id, tp1_order_id, tp2_order_id, tp3_order_id))
    conn.commit()
    conn.close()

def get_active_trades():
    """Mengambil semua data trade yang berstatus aktif beserta order ID-nya."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''SELECT id, symbol, side, entry, sl, tp1, tp2, tp3, tp_stage, is_active, created_at,
                        entry_order_id, sl_order_id, tp1_order_id, tp2_order_id, tp3_order_id
                 FROM active_trades 
                 WHERE is_active = 1''')
    trades = c.fetchall()
    conn.close()
    return trades

def update_trade_orders(db_id, entry_order_id=None, sl_order_id=None, tp1_order_id=None, tp2_order_id=None, tp3_order_id=None):
    """Memperbarui spesifik order ID di database untuk tracking status."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    updates = []
    params = []
    if entry_order_id is not None:
        updates.append("entry_order_id = ?")
        params.append(entry_order_id)
    if sl_order_id is not None:
        updates.append("sl_order_id = ?")
        params.append(sl_order_id)
    if tp1_order_id is not None:
        updates.append("tp1_order_id = ?")
        params.append(tp1_order_id)
    if tp2_order_id is not None:
        updates.append("tp2_order_id = ?")
        params.append(tp2_order_id)
    if tp3_order_id is not None:
        updates.append("tp3_order_id = ?")
        params.append(tp3_order_id)
        
    if updates:
        params.append(db_id)
        query = f"UPDATE active_trades SET {', '.join(updates)} WHERE id = ?"
        c.execute(query, tuple(params))
        conn.commit()
        
    conn.close()

def deactivate_trade(db_id):
    """Menonaktifkan trade (is_active = 0) ketika posisi ditutup."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE active_trades SET is_active = 0 WHERE id = ?", (db_id,))
    conn.commit()
    conn.close()

def update_tp_stage(db_id, stage):
    """Mengupdate status Take Profit (tp_stage) saat ini."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE active_trades SET tp_stage = ? WHERE id = ?", (stage, db_id))
    conn.commit()
    conn.close()
