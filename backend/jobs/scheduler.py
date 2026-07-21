import time
import sqlite3
from datetime import datetime, timedelta
from backend.config import client, bot, ALLOWED_USER_ID, DB_NAME, FIXED_LEVERAGE
from backend.db.repository import get_active_trades, deactivate_trade, update_tp_stage, update_trade_orders, record_partial_close, finalize_trade
from backend.db.connection import get_connection
from backend.services.binance_rest import get_symbol_info, place_partial_tps
from backend.core.risk_manager import round_step
from backend.logger import logger
from binance.client import Client

def cron_check_pending_orders():
    """Memantau limit order yang berstatus pending di database. 
    Jika terisi (filled), aktifkan Stop Loss awal dan pasang 3 Limit TP."""
    logger.debug("[CRON PENDING] Mengecek limit order pending...")
    active_trades = get_active_trades()
    
    for trade in active_trades:
        db_id = trade['id']
        symbol = trade['symbol']
        side = trade['side']
        entry = trade['entry_price']
        sl = trade['sl_price']
        tp1 = trade['tp1_price']
        tp2 = trade['tp2_price']
        tp3 = trade['tp3_price']
        tp_stage = trade['tp_stage']
        entry_order_id = trade['entry_order_id']
        sl_order_id = trade['sl_order_id']
        tp1_order_id = trade['tp1_order_id']
        tp2_order_id = trade['tp2_order_id']
        tp3_order_id = trade['tp3_order_id']
        
        try:
            # Cek status order entry menggunakan orderId jika ada (lebih akurat & real-time)
            is_filled = False
            if entry_order_id:
                try:
                    order_status = client.futures_get_order(symbol=symbol, orderId=entry_order_id)
                    if order_status['status'] == 'FILLED':
                        is_filled = True
                    elif order_status['status'] in ['CANCELED', 'EXPIRED']:
                        print(f"[{symbol}] Order entry dibatalkan atau kedaluwarsa di Binance. Menonaktifkan di DB.")
                        deactivate_trade(db_id)
                        continue
                except Exception as e:
                    print(f"[WARN] Gagal mendapatkan detail order entry {symbol}: {e}")
            
            # Cek ukuran posisi di Binance
            pos_info = client.futures_position_information(symbol=symbol)
            position_amt = float(pos_info[0]['positionAmt']) if pos_info else 0
            
            # Jika posisi masih 0
            if position_amt == 0:
                if is_filled:
                    # Kadang posisi masih di-update lambat oleh Binance, tunggu iterasi berikutnya
                    continue
                else:
                    # Verifikasi fallback jika orderId tidak tersedia
                    if not entry_order_id:
                        open_orders = client.futures_get_open_orders(symbol=symbol)
                        has_limit_entry = any(o['type'] == 'LIMIT' and o['side'] == side and not o.get('reduceOnly', False) for o in open_orders)
                        if not has_limit_entry:
                            print(f"[{symbol}] Limit order tidak ditemukan. Menonaktifkan di DB.")
                            deactivate_trade(db_id)
                    continue
            
            # Jika posisi > 0 (artinya limit order baru saja terisi/filled)
            elif abs(position_amt) > 0:
                # Periksa apakah sudah ada Stop Loss aktif (cek open orders reguler & open algo orders)
                has_sl_order = False
                try:
                    open_orders = client.futures_get_open_orders(symbol=symbol)
                    has_sl_order = any(o['type'] == 'STOP_MARKET' for o in open_orders)
                    if not has_sl_order:
                        open_algos = client.futures_get_open_algo_orders(symbol=symbol)
                        has_sl_order = any(algo['orderType'] == 'STOP_MARKET' for algo in open_algos)
                except Exception as err:
                    print(f"[WARN] Gagal mengecek open SL orders untuk {symbol}: {err}")
                
                if not has_sl_order:
                    print(f"[{symbol}] Limit order TERISI! Mengaktifkan Stop Loss & Limit TP...")
                    tick_size, step_size, min_qty, max_qty = get_symbol_info(symbol)
                    
                    # 1. Pasang SL awal
                    sl_side = "BUY" if side == "SELL" else "SELL"
                    sl_price_rounded = round_step(sl, tick_size)
                    sl_res = client.futures_create_order(
                        symbol=symbol, side=sl_side, type='STOP_MARKET', 
                        stopPrice=sl_price_rounded, closePosition=True
                    )
                    sl_id = str(sl_res.get('orderId') or sl_res.get('algoId'))
                    
                    # 2. Pasang 3 Limit TP Parsial (50% TP1, 25% TP2, 25% TP3)
                    qty = abs(position_amt)
                    tp1_id, tp2_id, tp3_id = place_partial_tps(symbol, side, qty, tp1, tp2, tp3, tick_size, step_size)
                    
                    # 3. Update database dengan Order ID yang baru dibuat
                    update_trade_orders(
                        db_id, sl_order_id=sl_id,
                        tp1_order_id=tp1_id, tp2_order_id=tp2_id, tp3_order_id=tp3_id
                    )
                    
                    # Hitung data posisi riil setelah terisi
                    actual_entry = float(pos_info[0]['entryPrice'])
                    if actual_entry <= 0:
                        actual_entry = entry
                        
                    size_usdt = qty * actual_entry
                    margin_used = size_usdt / FIXED_LEVERAGE
                    potential_loss = qty * abs(actual_entry - sl_price_rounded)
                    
                    qty_tp1 = round_step(qty * 0.50, step_size)
                    qty_tp2 = round_step(qty * 0.25, step_size)
                    qty_tp3 = round_step(qty - qty_tp1 - qty_tp2, step_size)

                    tp1_price = round_step(tp1, tick_size)
                    tp2_price = round_step(tp2, tick_size)
                    tp3_price = round_step(tp3, tick_size)

                    pnl_tp1 = qty_tp1 * abs(tp1_price - actual_entry)
                    pnl_tp2 = qty_tp2 * abs(tp2_price - actual_entry)
                    pnl_tp3 = qty_tp3 * abs(tp3_price - actual_entry)
                    total_pnl_tp = pnl_tp1 + pnl_tp2 + pnl_tp3

                    pct1 = (abs(tp1_price - actual_entry) / actual_entry) * 100
                    pct2 = (abs(tp2_price - actual_entry) / actual_entry) * 100
                    pct3 = (abs(tp3_price - actual_entry) / actual_entry) * 100
                    
                    roe1 = pct1 * FIXED_LEVERAGE
                    roe2 = pct2 * FIXED_LEVERAGE
                    roe3 = pct3 * FIXED_LEVERAGE
                    
                    info_msg = (
                        f"\n\n📊 *Rincian Posisi (Terisi):*\n"
                        f"• Entry Price: `{actual_entry}`\n"
                        f"• Size: `{qty} {symbol.replace('USDT', '')}` (`{size_usdt:.2f} USDT`)\n"
                        f"• Margin: `{margin_used:.2f} USDT` (Leverage {FIXED_LEVERAGE}x)\n"
                        f"• Stop Loss: `{sl_price_rounded}`\n"
                        f"• Potensi Kerugian: `-{potential_loss:.2f} USDT`\n\n"
                        f"🎯 *Rincian Target Take Profit:*\n"
                        f"• TP1 (50%): `{tp1_price}` (+{pct1:.2f}% / +{roe1:.2f}% ROE) -> `+{pnl_tp1:.2f} USDT`\n"
                        f"• TP2 (25%): `{tp2_price}` (+{pct2:.2f}% / +{roe2:.2f}% ROE) -> `+{pnl_tp2:.2f} USDT`\n"
                        f"• TP3 (25%): `{tp3_price}` (+{pct3:.2f}% / +{roe3:.2f}% ROE) -> `+{pnl_tp3:.2f} USDT`\n"
                        f"• Total Potensi Profit: `+{total_pnl_tp:.2f} USDT`"
                    )
                    
                    # Kirim notifikasi Telegram
                    bot.send_message(
                        ALLOWED_USER_ID, 
                        f"🛡️ *[{symbol}] Limit Order Terisi!*\n"
                        f"Stop Loss & 3 Limit Take Profit parsial diaktifkan.{info_msg}",
                        parse_mode="Markdown"
                    )
        
        except Exception as e:
            print(f"[CRON PENDING ERROR] Gagal mengecek {symbol}: {e}")

def cron_monitor_active_positions():
    """Memantau posisi aktif. Menggunakan status order limit TP untuk menggeser SL, 
    serta mengirim notifikasi eksekusi TP."""
    print("[CRON ACTIVE] Mengecek posisi aktif & tracking target profit...")
    active_trades = get_active_trades()
    
    for trade in active_trades:
        db_id = trade['id']
        symbol = trade['symbol']
        side = trade['side']
        entry = trade['entry_price']
        sl = trade['sl_price']
        tp1 = trade['tp1_price']
        tp2 = trade['tp2_price']
        tp3 = trade['tp3_price']
        tp_stage = trade['tp_stage']
        entry_order_id = trade['entry_order_id']
        sl_order_id = trade['sl_order_id']
        tp1_order_id = trade['tp1_order_id']
        tp2_order_id = trade['tp2_order_id']
        tp3_order_id = trade['tp3_order_id']
        
        try:
            # Cek ukuran posisi
            pos_info = client.futures_position_information(symbol=symbol)
            position_amt = float(pos_info[0]['positionAmt']) if pos_info else 0
            
            # Abaikan jika posisi bernilai 0
            if position_amt == 0:
                continue
                
            tick_size, step_size, min_qty, max_qty = get_symbol_info(symbol)
            actual_entry = float(pos_info[0]['entryPrice'])
            qty = abs(position_amt)
            
            # ----------------------------------------------------
            # LOGIKA EVENT-DRIVEN TRACKING (Menggunakan Status Order)
            # ----------------------------------------------------
            
            # 1. Cek TP1 Order status
            if tp_stage < 1 and tp1_order_id:
                try:
                    order = client.futures_get_order(symbol=symbol, orderId=tp1_order_id)
                    if order['status'] == 'FILLED':
                        # Batalkan SL sebelumnya di Binance (mencegah error code=-4130)
                        if sl_order_id:
                            try: client.futures_cancel_order(symbol=symbol, orderId=sl_order_id)
                            except Exception: pass
                            try: client.futures_cancel_algo_order(symbol=symbol, algoId=sl_order_id)
                            except Exception: pass
                        
                        # Pasang SL baru di Breakeven (Entry Price)
                        sl_side = "BUY" if side == "SELL" else "SELL"
                        new_sl_price = round_step(entry, tick_size)
                        new_sl_res = client.futures_create_order(
                            symbol=symbol, side=sl_side, type='STOP_MARKET', 
                            stopPrice=new_sl_price, closePosition=True
                        )
                        new_sl_id = str(new_sl_res.get('orderId') or new_sl_res.get('algoId'))
                        
                        # Hitung profit nominal yang direalisasikan
                        qty_tp1 = round_step(qty * 2.0 * 0.50, step_size)
                        pnl1 = qty_tp1 * abs(float(order['price']) - actual_entry)
                        
                        # Update DB & Record Partial Close (PRD-V2)
                        record_partial_close(
                            trade_id=db_id, event_type='TP1_HIT', exit_price=float(order['price']),
                            qty_closed=qty_tp1, realized_pnl_usd=pnl1
                        )
                        update_trade_orders(db_id, sl_order_id=new_sl_id)
                        
                        # Kirim Notifikasi
                        bot.send_message(
                            ALLOWED_USER_ID,
                            f"🎉 *[{symbol}] Target TP1 Terpenuhi! (50% Posisi Terjual)*\n"
                            f"• Harga TP1: `{order['price']}`\n"
                            f"• Profit Direalisasi: `+{pnl1:.2f} USDT`\n"
                            f"• Stop Loss otomatis dipindahkan ke *Entry Price* (`{new_sl_price}`).\n"
                            f"• Posisi saat ini bebas risiko (Risk-Free).",
                            parse_mode="Markdown"
                        )
                        continue
                except Exception as err:
                    print(f"[WARN] Gagal melacak TP1 order {symbol}: {err}")

            # 2. Cek TP2 Order status
            if tp_stage < 2 and tp2_order_id:
                try:
                    order = client.futures_get_order(symbol=symbol, orderId=tp2_order_id)
                    if order['status'] == 'FILLED':
                        # Batalkan SL sebelumnya
                        if sl_order_id:
                            try: client.futures_cancel_algo_order(symbol=symbol, algoId=sl_order_id)
                            except Exception: pass
                        
                        # Pasang SL baru di TP1 Price
                        sl_side = "BUY" if side == "SELL" else "SELL"
                        new_sl_price = round_step(tp1, tick_size)
                        new_sl_res = client.futures_create_order(
                            symbol=symbol, side=sl_side, type='STOP_MARKET', 
                            stopPrice=new_sl_price, closePosition=True
                        )
                        new_sl_id = str(new_sl_res.get('orderId') or new_sl_res.get('algoId'))
                        
                        # Hitung profit nominal yang direalisasikan
                        qty_tp2 = round_step(qty * 3.0 * 0.25, step_size)
                        pnl2 = qty_tp2 * abs(float(order['price']) - actual_entry)
                        
                        # Update DB & Record Partial Close (PRD-V2)
                        record_partial_close(
                            trade_id=db_id, event_type='TP2_HIT', exit_price=float(order['price']),
                            qty_closed=qty_tp2, realized_pnl_usd=pnl2
                        )
                        update_trade_orders(db_id, sl_order_id=new_sl_id)
                        
                        # Kirim Notifikasi
                        bot.send_message(
                            ALLOWED_USER_ID,
                            f"🎉 *[{symbol}] Target TP2 Terpenuhi! (25% Posisi Terjual)*\n"
                            f"• Harga TP2: `{order['price']}`\n"
                            f"• Profit Direalisasi: `+{pnl2:.2f} USDT`\n"
                            f"• Stop Loss otomatis dipindahkan ke *TP1 Price* (`{new_sl_price}`).",
                            parse_mode="Markdown"
                        )
                        continue
                except Exception as err:
                    print(f"[WARN] Gagal melacak TP2 order {symbol}: {err}")

            # 3. Cek TP3 Order status
            if tp_stage < 3 and tp3_order_id:
                try:
                    order = client.futures_get_order(symbol=symbol, orderId=tp3_order_id)
                    if order['status'] == 'FILLED':
                        qty_tp3 = qty
                        pnl3 = qty_tp3 * abs(float(order['price']) - actual_entry)
                        
                        # Update DB
                        update_tp_stage(db_id, 3)
                        
                        # Kirim Notifikasi
                        bot.send_message(
                            ALLOWED_USER_ID,
                            f"🏁 *[{symbol}] Target TP3 Terpenuhi! (Posisi Ditutup Penuh)*\n"
                            f"• Harga TP3: `{order['price']}`\n"
                            f"• Profit Direalisasi: `+{pnl3:.2f} USDT`\n"
                            f"• Semua sisa order pendukung otomatis dibersihkan.",
                            parse_mode="Markdown"
                        )
                        deactivate_trade(db_id)
                        continue
                except Exception as err:
                    print(f"[WARN] Gagal melacak TP3 order {symbol}: {err}")

            # ----------------------------------------------------
            # FALLBACK LOGIKA HARGA CANDLE (Jika Order ID tidak terlacak)
            # ----------------------------------------------------
            if not tp1_order_id:
                klines = client.futures_klines(symbol=symbol, interval=Client.KLINE_INTERVAL_15MINUTE, limit=2)
                last_candle_high = float(klines[-2][2])
                last_candle_low = float(klines[-2][3])
                
                new_sl = None
                new_stage = tp_stage
                
                if side == "SELL": # SHORT
                    if last_candle_low <= tp2 and tp_stage < 2:
                        new_sl = tp1
                        new_stage = 2
                    elif last_candle_low <= tp1 and tp_stage < 1:
                        new_sl = entry
                        new_stage = 1
                elif side == "BUY": # LONG
                    if last_candle_high >= tp2 and tp_stage < 2:
                        new_sl = tp1
                        new_stage = 2
                    elif last_candle_high >= tp1 and tp_stage < 1:
                        new_sl = entry
                        new_stage = 1
                
                if new_sl:
                    new_sl_rounded = round_step(new_sl, tick_size)
                    sl_side = "BUY" if side == "SELL" else "SELL"
                    
                    try:
                        open_algos = client.futures_get_open_algo_orders(symbol=symbol)
                        for algo in open_algos:
                            if algo['orderType'] == 'STOP_MARKET':
                                client.futures_cancel_algo_order(symbol=symbol, algoId=algo['algoId'])
                    except Exception as err:
                        print(f"[WARN] Gagal membatalkan SL lama via algo fallback: {err}")
                    
                    sl_res = client.futures_create_order(
                        symbol=symbol, side=sl_side, type='STOP_MARKET', 
                        stopPrice=new_sl_rounded, closePosition=True
                    )
                    
                    update_tp_stage(db_id, new_stage)
                    update_trade_orders(db_id, sl_order_id=str(sl_res.get('orderId') or sl_res.get('algoId')))
                    bot.send_message(ALLOWED_USER_ID, f"🔄 [{symbol}] TP{new_stage} Hit! SL dipindah ke {new_sl_rounded}")

        except Exception as e:
            print(f"[CRON ACTIVE ERROR] Gagal mengecek {symbol}: {e}")

def cron_sync_closed_positions():
    """Mendeteksi jika posisi ditutup secara manual di Binance atau terkena SL/TP keras.
    Jika tertutup, bersihkan sisa order menggantung dan nonaktifkan di database."""
    logger.debug("[CRON SYNC] Sinkronisasi posisi tutup...")
    active_trades = get_active_trades()
    if not active_trades:
        return
        
    try:
        all_positions = client.futures_position_information()
        pos_dict = {p['symbol']: float(p['positionAmt']) for p in all_positions}
    except Exception as e:
        logger.error(f"[CRON SYNC ERROR] Gagal mengambil batch position info: {e}")
        return
    
    for trade in active_trades:
        db_id = trade['id']
        symbol = trade['symbol']
        side = trade['side']
        
        try:
            position_amt = pos_dict.get(symbol, 0.0)
            
            if position_amt == 0:
                # Cek apakah masih ada limit order pending yang tersisa
                open_orders = client.futures_get_open_orders(symbol=symbol)
                has_limit_entry = any(o['type'] == 'LIMIT' and o['side'] == side and not o.get('reduceOnly', False) for o in open_orders)
                
                # Jika tidak ada limit order pending AND posisi = 0, berarti posisi telah ditutup!
                if not has_limit_entry:
                    logger.info(f"[{symbol}] Posisi terdeteksi tutup. Membersihkan order gantung...")
                    client.futures_cancel_all_open_orders(symbol=symbol)
                    try: client.futures_cancel_all_algo_open_orders(symbol=symbol)
                    except Exception: pass
                    
                    # Cek keberhasilan deaktivasi database sebelum kirim pesan Telegram
                    try:
                        deactivate_trade(db_id)
                        bot.send_message(
                            ALLOWED_USER_ID, 
                            f"🏁 [{symbol}] Posisi telah ditutup. Semua sisa order berhasil dibersihkan."
                        )
                    except Exception as db_err:
                        logger.error(f"Gagal menonaktifkan trade ID {db_id} di DB: {db_err}")
        
        except Exception as e:
            logger.error(f"[CRON SYNC ERROR] Gagal mensinkronisasikan penutupan {symbol}: {e}")

def cron_cancel_expired_orders():
    """Membatalkan limit order pending yang berumur lebih dari 4 jam (unfilled)."""
    print("[CRON EXPIRED] Memeriksa limit order kedaluwarsa...")
    active_trades = get_active_trades()
    
    for trade in active_trades:
        db_id = trade['id']
        symbol = trade['symbol']
        created_at = trade['created_at']
        entry_order_id = trade['entry_order_id']
        
        try:
            created_dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
            time_limit = datetime.utcnow() - timedelta(hours=4)
            
            if created_dt < time_limit:
                pos_info = client.futures_position_information(symbol=symbol)
                position_amt = float(pos_info[0]['positionAmt']) if pos_info else 0
                
                if position_amt == 0:
                    open_orders = client.futures_get_open_orders(symbol=symbol)
                    has_limit_entry = any(o['type'] == 'LIMIT' and o['side'] == side and not o.get('reduceOnly', False) for o in open_orders)
                    
                    if has_limit_entry:
                        print(f"[{symbol}] Order kedaluwarsa (4 jam tanpa terisi). Membatalkan order di Binance...")
                        client.futures_cancel_all_open_orders(symbol=symbol)
                        deactivate_trade(db_id)
                        
                        bot.send_message(
                            ALLOWED_USER_ID, 
                            f"⏰ [{symbol}] Limit Order kedaluwarsa (4 jam tanpa terisi) dan telah dibatalkan."
                        )
        except Exception as e:
            print(f"[CRON EXPIRED ERROR] Gagal memproses kedaluwarsa {symbol}: {e}")

def cron_send_daily_report():
    """Mengambil PnL realisasi, komisi, funding fee, dan info akun Binance Futures selama 24 jam terakhir dan mengirimkannya ke Telegram."""
    print("[CRON REPORT] Mengirim laporan performa harian...")
    try:
        account_info = client.futures_account()
        wallet_balance = float(account_info['totalWalletBalance'])
        
        start_time = int((time.time() - 24 * 3600) * 1000)
        incomes = client.futures_income_history(startTime=start_time)
        
        pnl_incomes = [i for i in incomes if i['incomeType'] == 'REALIZED_PNL']
        commission_incomes = [i for i in incomes if i['incomeType'] == 'COMMISSION']
        funding_incomes = [i for i in incomes if i['incomeType'] == 'FUNDING_FEE']
        
        total_pnl = sum(float(i['income']) for i in pnl_incomes)
        total_commission = sum(float(i['income']) for i in commission_incomes)
        total_funding = sum(float(i['income']) for i in funding_incomes)
        
        symbol_pnls = {}
        for i in pnl_incomes:
            sym = i['symbol']
            val = float(i['income'])
            symbol_pnls[sym] = symbol_pnls.get(sym, 0.0) + val
            
        win_trades = 0
        loss_trades = 0
        gross_profit = 0.0
        gross_loss = 0.0
        best_symbol = "Tidak Ada"
        best_pnl = 0.0
        worst_symbol = "Tidak Ada"
        worst_pnl = 0.0
        
        for sym, pnl_val in symbol_pnls.items():
            if pnl_val > 0:
                win_trades += 1
                gross_profit += pnl_val
                if pnl_val > best_pnl:
                    best_pnl = pnl_val
                    best_symbol = sym
            elif pnl_val < 0:
                loss_trades += 1
                gross_loss += pnl_val
                if pnl_val < worst_pnl:
                    worst_pnl = pnl_val
                    worst_symbol = sym
                    
        total_trades = win_trades + loss_trades
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        net_income = total_pnl + total_commission + total_funding
        
        emoji_net = "📈" if net_income >= 0 else "📉"
        
        report_msg = (
            f"📊 *LAPORAN PERFORMA HARIAN BINANCE FUTURES*\n"
            f"📅 _24 Jam Terakhir_\n\n"
            f"💰 *IKHTISAR SALDO:*\n"
            f"• Saldo Wallet: `{wallet_balance:.2f} USDT`\n\n"
            f"📈 *STATISTIK TRADING:*\n"
            f"• Total Koin Ditransaksikan: `{total_trades}`\n"
            f"• Win Rate: `{win_rate:.1f}%` (`{win_trades}` Untung / `{loss_trades}` Rugi)\n"
            f"• Gross Profit: `+{gross_profit:.2f} USDT`\n"
            f"• Gross Loss: `{gross_loss:.2f} USDT`\n\n"
            f"💸 *BIAYA & PENDAPATAN LAIN:*\n"
            f"• Biaya Komisi (Fee): `{total_commission:.2f} USDT`\n"
            f"• Pendapatan Funding: `{total_funding:+.2f} USDT`\n\n"
            f"🏆 *SOROTAN KINERJA (HIGHLIGHT):*\n"
            f"• Best Trade: *{best_symbol}* (`{best_pnl:+.2f} USDT`)\n"
            f"• Worst Trade: *{worst_symbol}* (`{worst_pnl:+.2f} USDT`)\n\n"
            f"⚖️ *HASIL AKHIR BERSIH (NET INCOME):*\n"
            f"• Realized PnL Murni: `{total_pnl:+.2f} USDT`\n"
            f"• {emoji_net} *Net Profit Bersih:* `{net_income:+.2f} USDT` _(PnL + Fee + Funding)_"
        )
        
        bot.send_message(ALLOWED_USER_ID, report_msg, parse_mode="Markdown")
        print(f"[CRON REPORT] Laporan harian terkirim. Net Hasil Bersih: {net_income:+.2f} USDT")
    except Exception as e:
        print(f"[CRON REPORT ERROR] Gagal mengirim laporan harian: {e}")

def cron_db_housekeeping():
    """Membersihkan data trade tidak aktif yang sudah berusia lebih dari 30 hari di DB."""
    print("[CRON CLEANUP] Menjalankan pembersihan database...")
    try:
        conn = get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM active_trades WHERE is_active = 0 AND created_at < datetime('now', '-30 days')")
        conn.commit()
        deleted_rows = c.rowcount
        conn.close()
        print(f"[CRON CLEANUP] Berhasil menghapus {deleted_rows} baris trade lama dari database.")
    except Exception as e:
        print(f"[CRON CLEANUP ERROR] Gagal membersihkan database: {e}")

def cron_check_api_health():
    """Memeriksa kesehatan koneksi dan API Key Binance."""
    print("[CRON HEALTH] Memeriksa koneksi API Binance...")
    try:
        client.futures_ping()
    except Exception as e:
        print(f"[CRON HEALTH ERROR] API Binance terganggu: {e}")
        bot.send_message(
            ALLOWED_USER_ID,
            f"⚠️ *PERINGATAN KONEKSI API*\n\n"
            f"Koneksi API Binance terganggu atau diblokir. Detail error:\n`{e}`",
            parse_mode="Markdown"
        )

def cron_check_margin_level():
    """Memantau level margin akun Binance Futures dan mengirimkan peringatan jika saldo bebas < 15%."""
    print("[CRON MARGIN] Memeriksa saldo dan tingkat margin...")
    try:
        account_info = client.futures_account()
        wallet_balance = float(account_info['totalWalletBalance'])
        available_balance = float(account_info['availableBalance'])
        
        if wallet_balance > 0:
            free_margin_pct = (available_balance / wallet_balance) * 100
            
            if free_margin_pct < 15.0:
                bot.send_message(
                    ALLOWED_USER_ID,
                    f"⚠️ *PERINGATAN MARGIN TIPIS!*\n\n"
                    f"Saldo Tersedia (Available Balance) Anda saat ini kritis:\n"
                    f"• Total Wallet: `{wallet_balance:.2f} USDT`\n"
                    f"• Tersedia: `{available_balance:.2f} USDT` (`{free_margin_pct:.1f}%`)\n\n"
                    f"Harap berhati-hati, disarankan untuk tidak membuka posisi baru atau menambah margin.",
                    parse_mode="Markdown"
                )
    except Exception as e:
        print(f"[CRON MARGIN ERROR] Gagal memeriksa tingkat margin: {e}")
