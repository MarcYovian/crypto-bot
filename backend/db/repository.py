from backend.db.connection import get_connection
from backend.logger import logger

# ========================================================
# 1. OPERASI POSISI AKTIF (active_trades)
# ========================================================

def add_trade(symbol, side, entry_price, sl_price, tp1_price, tp2_price, tp3_price, initial_qty, remaining_qty=None,
              entry_order_id=None, sl_order_id=None, tp1_order_id=None, tp2_order_id=None, tp3_order_id=None):
    """Menyimpan data trade baru ke active_trades dan mencatat event ENTRY ke trade_events."""
    if remaining_qty is None:
        remaining_qty = initial_qty
        
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO active_trades (
                        symbol, side, entry_price, sl_price, tp1_price, tp2_price, tp3_price,
                        initial_qty, remaining_qty, tp_stage, accumulated_realized_pnl,
                        accumulated_commission, accumulated_funding, is_active,
                        entry_order_id, sl_order_id, tp1_order_id, tp2_order_id, tp3_order_id
                    ) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0.0, 0.0, 0.0, 1, ?, ?, ?, ?, ?)''', 
                (symbol, side, entry_price, sl_price, tp1_price, tp2_price, tp3_price,
                 initial_qty, remaining_qty, entry_order_id, sl_order_id, tp1_order_id, tp2_order_id, tp3_order_id))
        trade_id = c.lastrowid
        
        # Log event ENTRY
        c.execute('''INSERT INTO trade_events (trade_id, event_type, price, qty, realized_pnl_usd, commission_usd)
                    VALUES (?, 'ENTRY', ?, ?, 0.0, 0.0)''', (trade_id, entry_price, initial_qty))
        
        conn.commit()
        conn.close()
        logger.info(f"Trade baru disimpan ke DB (ID: {trade_id}): {symbol} {side} @ Entry {entry_price}, Qty: {initial_qty}")
        return trade_id
    except Exception as e:
        logger.error(f"Gagal menyimpan trade {symbol} ke DB: {e}", exc_info=True)
        return None

def get_active_trades():
    """Mengambil semua data posisi aktif (is_active = 1) dalam bentuk list of dict (siap untuk API & Telegram)."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3_row_factory
        c = conn.cursor()
        c.execute('''SELECT * FROM active_trades WHERE is_active = 1''')
        trades = c.fetchall()
        conn.close()
        
        # Mapping nama kolom lama ke baru jika masih ada yang kosong
        normalized_trades = []
        for t in trades:
            trade_dict = dict(t)
            trade_dict['entry_price'] = trade_dict.get('entry_price') or trade_dict.get('entry', 0.0)
            trade_dict['sl_price'] = trade_dict.get('sl_price') or trade_dict.get('sl', 0.0)
            trade_dict['tp1_price'] = trade_dict.get('tp1_price') or trade_dict.get('tp1', 0.0)
            trade_dict['tp2_price'] = trade_dict.get('tp2_price') or trade_dict.get('tp2', 0.0)
            trade_dict['tp3_price'] = trade_dict.get('tp3_price') or trade_dict.get('tp3', 0.0)
            trade_dict['initial_qty'] = trade_dict.get('initial_qty', 0.0)
            trade_dict['remaining_qty'] = trade_dict.get('remaining_qty', 0.0)
            normalized_trades.append(trade_dict)
            
        return normalized_trades
    except Exception as e:
        logger.error(f"Gagal mengambil active trades dari DB: {e}", exc_info=True)
        return []

def get_trade_by_id(trade_id):
    """Mengambil 1 data trade spesifik berdasarkan ID."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3_row_factory
        c = conn.cursor()
        c.execute("SELECT * FROM active_trades WHERE id = ?", (trade_id,))
        trade = c.fetchone()
        conn.close()
        return trade
    except Exception as e:
        logger.error(f"Gagal mengambil trade ID {trade_id}: {e}", exc_info=True)
        return None

def record_partial_close(trade_id, event_type, exit_price, qty_closed, realized_pnl_usd=0.0, commission_usd=0.0):
    """Mencatat partial TP (TP1/TP2) ke trade_events dan meng-update remaining_qty & akumulasi pnl di active_trades."""
    try:
        conn = get_connection()
        c = conn.cursor()
        
        # 1. Catat event detail
        c.execute('''INSERT INTO trade_events (trade_id, event_type, price, qty, realized_pnl_usd, commission_usd)
                    VALUES (?, ?, ?, ?, ?, ?)''', 
                (trade_id, event_type, exit_price, qty_closed, realized_pnl_usd, commission_usd))
        
        # 2. Update akumulasi active_trades
        stage_num = 1 if event_type == 'TP1_HIT' else 2 if event_type == 'TP2_HIT' else 0
        c.execute('''UPDATE active_trades 
                    SET remaining_qty = MAX(0, remaining_qty - ?),
                        accumulated_realized_pnl = accumulated_realized_pnl + ?,
                        accumulated_commission = accumulated_commission + ?,
                        tp_stage = MAX(tp_stage, ?),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?''', (qty_closed, realized_pnl_usd, commission_usd, stage_num, trade_id))
        
        conn.commit()
        conn.close()
        logger.info(f"Partial Close dicatat [{event_type}] Trade ID {trade_id}: Qty={qty_closed}, PnL=+${realized_pnl_usd:.2f}")
    except Exception as e:
        logger.error(f"Gagal mencatat partial close Trade ID {trade_id}: {e}", exc_info=True)

def update_trade_orders(trade_id, entry_order_id=None, sl_order_id=None, tp1_order_id=None, tp2_order_id=None, tp3_order_id=None):
    """Memperbarui order ID Binance untuk tracking order."""
    try:
        conn = get_connection()
        c = conn.cursor()
        
        updates, params = [], []
        if entry_order_id is not None: updates.append("entry_order_id = ?"); params.append(entry_order_id)
        if sl_order_id is not None: updates.append("sl_order_id = ?"); params.append(sl_order_id)
        if tp1_order_id is not None: updates.append("tp1_order_id = ?"); params.append(tp1_order_id)
        if tp2_order_id is not None: updates.append("tp2_order_id = ?"); params.append(tp2_order_id)
        if tp3_order_id is not None: updates.append("tp3_order_id = ?"); params.append(tp3_order_id)
            
        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(trade_id)
            query = f"UPDATE active_trades SET {', '.join(updates)} WHERE id = ?"
            c.execute(query, tuple(params))
            conn.commit()
            logger.info(f"Order ID trade (DB ID: {trade_id}) diperbarui.")
            
        conn.close()
    except Exception as e:
        logger.error(f"Gagal memperbarui order IDs trade (DB ID: {trade_id}): {e}", exc_info=True)

def update_tp_stage(trade_id, stage):
    """Meng-update tp_stage secara langsung."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("UPDATE active_trades SET tp_stage = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (stage, trade_id))
        conn.commit()
        conn.close()
        logger.info(f"Status TP Trade (DB ID: {trade_id}) diperbarui ke stage {stage}.")
    except Exception as e:
        logger.error(f"Gagal mengupdate tp_stage (DB ID: {trade_id}): {e}", exc_info=True)

# ========================================================
# 2. FINALIZE POSISI & JURNAL PERFORMA (trade_history)
# ========================================================

def finalize_trade(trade_id, close_price, close_reason, final_commission_usd=0.0, total_funding_usd=0.0):
    """Menutup posisi 100%, menghitung Net PnL bersih (dikurangi komisi & funding), 
    memindahkan record ke trade_history, dan menonaktifkan baris active_trades (is_active = 0)."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3_row_factory
        c = conn.cursor()
        
        # 1. Ambil data active trade
        c.execute("SELECT * FROM active_trades WHERE id = ?", (trade_id,))
        trade = c.fetchone()
        if not trade:
            logger.warning(f"finalize_trade dipanggil untuk ID {trade_id} yang tidak ditemukan.")
            conn.close()
            return
            
        # 2. Catat event penutupan akhir ke trade_events
        remaining_qty = trade['remaining_qty']
        side = trade['side']
        entry_price = trade['entry_price']
        
        # Hitung gross PnL sisa kuantitas
        if side == "BUY":
            last_gross_pnl = remaining_qty * (close_price - entry_price)
        else:
            last_gross_pnl = remaining_qty * (entry_price - close_price)
            
        c.execute('''INSERT INTO trade_events (trade_id, event_type, price, qty, realized_pnl_usd, commission_usd)
                    VALUES (?, ?, ?, ?, ?, ?)''', 
                (trade_id, close_reason, close_price, remaining_qty, last_gross_pnl, final_commission_usd))
        
        # 3. Ambil Fee Resmi dari Binance API (jika ada timestamp created_at)
        official_commission = 0.0
        official_funding = 0.0
        try:
            from datetime import datetime
            from backend.services.binance_rest import get_official_trade_fees
            created_str = trade['created_at']
            # Format datetime SQLite
            dt = datetime.strptime(created_str, "%Y-%m-%d %H:%M:%S") if isinstance(created_str, str) else datetime.now()
            start_time_ms = int(dt.timestamp() * 1000)
            official_commission, official_funding = get_official_trade_fees(trade['symbol'], start_time_ms)
        except Exception as err:
            logger.warning(f"Gagal mengambil official fee dari Binance API untuk Trade ID {trade_id}: {err}")
            
        total_gross_pnl = trade['accumulated_realized_pnl'] + last_gross_pnl
        total_commission = max(trade['accumulated_commission'] + final_commission_usd, official_commission)
        total_funding = trade['accumulated_funding'] + total_funding_usd + official_funding
        
        # Net PnL = Gross PnL - Total Komisi + Total Funding Fee (Rumus Resmi PRD-V2)
        net_pnl_usd = total_gross_pnl - total_commission + total_funding
        
        # Persentase profit bersih dari margin modal terpakai
        margin_used = (trade['initial_qty'] * entry_price) / 15.0  # Default 15x leverage
        net_pnl_percent = (net_pnl_usd / margin_used * 100) if margin_used > 0 else 0.0
        
        # Durasi trade dalam menit
        c.execute("SELECT CAST((julianday('now') - julianday(?)) * 1440 AS INTEGER)", (trade['created_at'],))
        duration_res = c.fetchone()
        duration_minutes = list(duration_res.values())[0] if duration_res else 0
        
        # 4. Simpan ke trade_history
        c.execute('''INSERT INTO trade_history (
                        symbol, side, entry_price, close_price, gross_pnl_usd,
                        total_commission_usd, total_funding_usd, net_pnl_usd,
                        net_pnl_percent, close_reason, duration_minutes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (trade['symbol'], side, entry_price, close_price, total_gross_pnl,
                 total_commission, total_funding, net_pnl_usd,
                 net_pnl_percent, close_reason, duration_minutes))
                 
        # 5. Nonaktifkan active_trades
        c.execute("UPDATE active_trades SET is_active = 0, remaining_qty = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (trade_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"Trade (DB ID: {trade_id}) FINALIZED [{close_reason}]: Net PnL = ${net_pnl_usd:+.2f} ({net_pnl_percent:+.2f}%)")
    except Exception as e:
        logger.error(f"Gagal mendefinalisasi trade (DB ID: {trade_id}): {e}", exc_info=True)

def deactivate_trade(trade_id):
    """Menonaktifkan trade secara sederhana tanpa perhitungan komisi."""
    finalize_trade(trade_id, close_price=0.0, close_reason="MANUAL_CLOSE")

# ========================================================
# 3. HELPER ROW FACTORY (Untuk mempermudah API & Telegram)
# ========================================================

def sqlite3_row_factory(cursor, row):
    """Mengubah tuple SQLite menjadi dictionary python yang rapi."""
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

# ========================================================
# 4. KONSUMSI UNTUK WEB DASHBOARD & TELEGRAM (READ-ONLY)
# ========================================================

def get_trade_history(limit=50):
    """Mengambil riwayat jurnal kinerja dari trade_history (dikonsumsi oleh Web API & Telegram)."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3_row_factory
        c = conn.cursor()
        c.execute("SELECT * FROM trade_history ORDER BY closed_at DESC LIMIT ?", (limit,))
        history = c.fetchall()
        conn.close()
        return history
    except Exception as e:
        logger.error(f"Gagal mengambil trade_history dari DB: {e}", exc_info=True)
        return []

def get_performance_summary():
    """Menghitung agregat performa kumulatif (Win Rate, Total Profit Bersih, Total Fee)."""
    try:
        conn = get_connection()
        conn.row_factory = sqlite3_row_factory
        c = conn.cursor()
        c.execute('''SELECT 
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN net_pnl_usd > 0 THEN 1 ELSE 0 END) as winning_trades,
                        SUM(CASE WHEN net_pnl_usd <= 0 THEN 1 ELSE 0 END) as losing_trades,
                        SUM(gross_pnl_usd) as total_gross_pnl,
                        SUM(total_commission_usd) as total_commission,
                        SUM(total_funding_usd) as total_funding,
                        SUM(net_pnl_usd) as total_net_pnl
                    FROM trade_history''')
        summary = c.fetchone()
        conn.close()
        return summary
    except Exception as e:
        logger.error(f"Gagal mengambil summary performa: {e}", exc_info=True)
        return {}

def update_watchlist_symbol(symbol, price, change_24h, ma50_distance_pct, rsi_14, status_signal):
    """Memperbarui data scanner koin di watchlist_scanner (untuk fitur scanner Telegram / Web Dashboard)."""
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute('''INSERT INTO watchlist_scanner (symbol, price, change_24h, ma50_distance_pct, rsi_14, status_signal, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(symbol) DO UPDATE SET
                        price=excluded.price,
                        change_24h=excluded.change_24h,
                        ma50_distance_pct=excluded.ma50_distance_pct,
                        rsi_14=excluded.rsi_14,
                        status_signal=excluded.status_signal,
                        updated_at=CURRENT_TIMESTAMP''', 
                (symbol, price, change_24h, ma50_distance_pct, rsi_14, status_signal))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Gagal meng-update watchlist scanner {symbol}: {e}", exc_info=True)
