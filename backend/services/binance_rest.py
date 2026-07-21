from backend.config import client, FIXED_LEVERAGE, MAX_RISK_PERCENT
from backend.db.repository import add_trade
from backend.core.risk_manager import calculate_position_size, round_step
from backend.logger import logger
from binance.exceptions import BinanceAPIException
from binance.enums import *

def get_symbol_info(symbol):
    """Mendapatkan tickSize, stepSize, minQty, dan maxQty dari filter Futures exchange info Binance."""
    try:
        info = client.futures_exchange_info()
        tick_size = 0.01
        step_size = 1.0
        min_qty = 0.001
        max_qty = 1000000.0
        for item in info['symbols']:
            if item['symbol'] == symbol:
                for f in item['filters']:
                    if f['filterType'] == 'PRICE_FILTER':
                        tick_size = float(f['tickSize'])
                    elif f['filterType'] == 'MARKET_LOT_SIZE':
                        step_size = float(f['stepSize'])
                        min_qty = float(f['minQty'])
                        max_qty = float(f['maxQty'])
                    elif f['filterType'] == 'LOT_SIZE' and max_qty == 1000000.0:
                        step_size = float(f['stepSize'])
                        min_qty = float(f['minQty'])
                        max_qty = float(f['maxQty'])
                logger.info(f"Symbol Info [{symbol}]: tickSize={tick_size}, stepSize={step_size}, minQty={min_qty}, maxQty={max_qty}")
                return tick_size, step_size, min_qty, max_qty
        return tick_size, step_size, min_qty, max_qty
    except Exception as e:
        logger.error(f"Gagal mengambil exchange info untuk {symbol}: {e}", exc_info=True)
        return 0.01, 1.0, 0.001, 1000000.0

def place_partial_tps(symbol, side, qty, tp1, tp2, tp3, tick_size, step_size):
    """Memasang 3 Limit Order TP secara parsial: 50% di TP1, 25% di TP2, 25% di TP3.
    Mengembalikan order ID masing-masing TP."""
    tp_side = "BUY" if side == "SELL" else "SELL"
    
    qty_tp1 = round_step(qty * 0.50, step_size)
    qty_tp2 = round_step(qty * 0.25, step_size)
    qty_tp3 = round_step(qty - qty_tp1 - qty_tp2, step_size)
    
    tp1_order_id = None
    tp2_order_id = None
    tp3_order_id = None
    
    try:
        if qty_tp1 > 0:
            o1 = client.futures_create_order(
                symbol=symbol, side=tp_side, type=ORDER_TYPE_LIMIT,
                price=round_step(tp1, tick_size), quantity=qty_tp1,
                timeInForce=TIME_IN_FORCE_GTC, reduceOnly=True
            )
            tp1_order_id = str(o1['orderId'])
            logger.info(f"Limit TP1 dipasang [{symbol}]: OrderID={tp1_order_id}, Qty={qty_tp1}, Price={tp1}")
            
        if qty_tp2 > 0:
            o2 = client.futures_create_order(
                symbol=symbol, side=tp_side, type=ORDER_TYPE_LIMIT,
                price=round_step(tp2, tick_size), quantity=qty_tp2,
                timeInForce=TIME_IN_FORCE_GTC, reduceOnly=True
            )
            tp2_order_id = str(o2['orderId'])
            logger.info(f"Limit TP2 dipasang [{symbol}]: OrderID={tp2_order_id}, Qty={qty_tp2}, Price={tp2}")
            
        if qty_tp3 > 0:
            o3 = client.futures_create_order(
                symbol=symbol, side=tp_side, type=ORDER_TYPE_LIMIT,
                price=round_step(tp3, tick_size), quantity=qty_tp3,
                timeInForce=TIME_IN_FORCE_GTC, reduceOnly=True
            )
            tp3_order_id = str(o3['orderId'])
            logger.info(f"Limit TP3 dipasang [{symbol}]: OrderID={tp3_order_id}, Qty={qty_tp3}, Price={tp3}")
    except Exception as e:
        logger.error(f"Gagal memasang partial TP order untuk {symbol}: {e}", exc_info=True)
        
    return tp1_order_id, tp2_order_id, tp3_order_id
def get_official_trade_fees(symbol, start_time_ms):
    """Mengambil total komisi transaksi & funding fee resmi langsung dari API Binance 
    sejak posisi pertama kali opened (start_time_ms)."""
    try:
        # 1. Ambil Komisi Transaksi
        user_trades = client.futures_account_trades(symbol=symbol, startTime=start_time_ms)
        total_commission = sum(float(t['commission']) for t in user_trades)
        
        # 2. Ambil History Funding Fee khusus koin ini
        income_history = client.futures_income_history(
            symbol=symbol, 
            incomeType="FUNDING_FEE", 
            startTime=start_time_ms
        )
        total_funding = sum(float(item['income']) for item in income_history)
        
        return total_commission, total_funding
    except Exception as e:
        logger.error(f"Gagal mengambil data komisi/funding resmi untuk {symbol}: {e}")
        return 0.0, 0.0
def execute_trade(data):
    """Membuka posisi Futures di Binance dan memasang SL awal."""
    symbol = data['symbol']
    side = data['side']
    risk_pct = data.get('risk') # Risiko kustom jika diekstrak dari sinyal
    logger.info(f"Memulai eksekusi trade [{symbol}] {side}...")
    
    try:
        tick_size, step_size, min_qty, max_qty = get_symbol_info(symbol)
        
        # Cek harga market saat ini sebelum entry
        ticker = client.futures_symbol_ticker(symbol=symbol)
        current_price = float(ticker['price'])
        
        TOLERANCE_PCT = 0.002  # 0.2% toleransi harga
        tolerance_price = data['entry'] * TOLERANCE_PCT
        
        use_market_order = False
        if side == "BUY":  # LONG
            if current_price <= data['entry'] + tolerance_price:
                use_market_order = True
        elif side == "SELL":  # SHORT
            if current_price >= data['entry'] - tolerance_price:
                use_market_order = True
        
        # Setup Leverage & Margin (Abaikan error -4046 'No need to change margin type' & -4067 'Position side cannot be changed if open orders exist')
        try:
            client.futures_change_leverage(symbol=symbol, leverage=FIXED_LEVERAGE)
        except BinanceAPIException as e:
            if e.code not in (-4046, -4067): logger.warning(f"Leverage change warning [{symbol}]: {e}")
        try:
            client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
        except BinanceAPIException as e:
            if e.code not in (-4046, -4067): logger.warning(f"Margin type change warning [{symbol}]: {e}")

        qty = calculate_position_size(symbol, data['entry'], data['sl'], step_size, risk_pct)
        
        # Override kuantitas jika ada kustom qty dari konfirmasi tombol Telegram
        if data.get('override_qty') is not None:
            qty = data['override_qty']
            logger.info(f"Menggunakan override quantity [{symbol}]: {qty}")
        else:
            # Pengecekan batas minimal dan maksimal quantity Binance
            if qty < min_qty:
                logger.warning(f"Quantity [{symbol}] dibawah minimum: calculated={qty}, min={min_qty}")
                return f"QTY_UNDER_MIN:{qty}:{min_qty}"
            elif qty > max_qty:
                logger.warning(f"Quantity [{symbol}] diatas maksimum: calculated={qty}, max={max_qty}")
                return f"QTY_OVER_MAX:{qty}:{max_qty}"
                
        if qty <= 0: 
            logger.warning(f"Gagal eksekusi [{symbol}]: kuantitas <= 0 ({qty})")
            return "Gagal: Kuantitas terlalu kecil."

        entry_price_rounded = round_step(data['entry'], tick_size)
        sl_price = round_step(data['sl'], tick_size)
        
        # Pengecekan Kecukupan Margin Terkini vs Available Balance
        if not data.get('override_qty'):
            account_info = client.futures_account()
            avail_balance = float([a['availableBalance'] for a in account_info['assets'] if a['asset'] == 'USDT'][0])
            required_margin = (qty * entry_price_rounded) / FIXED_LEVERAGE
            
            if required_margin > avail_balance:
                logger.warning(f"Margin [{symbol}] dibutuhkan (${required_margin:.2f}) > Avail Balance (${avail_balance:.2f}). Mengirim alert ke Telegram...")
                # Hitung ulang Qty maksimal yang muat di sisa saldo bebas
                max_possible_qty = round_step((avail_balance * FIXED_LEVERAGE) / entry_price_rounded, step_size)
                return f"MARGIN_EXCEEDS_AVAILABLE:{required_margin:.2f}:{avail_balance:.2f}:{max_possible_qty}"
        
        entry_order_id = None
        sl_order_id = None
        tp1_order_id = None
        tp2_order_id = None
        tp3_order_id = None
        
        if use_market_order:
            logger.info(f"Mengeksekusi MARKET order [{symbol}] {side} Qty={qty}...")
            # Open Position via Market Order
            order_res = client.futures_create_order(symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=qty)
            entry_order_id = str(order_res['orderId'])
            
            # Verifikasi & tunggu posisi aktif terbuka di Binance sebelum memasang SL (mencegah error code=-4509)
            import time
            position_active = False
            actual_entry = entry_price_rounded
            for attempt in range(5):
                time.sleep(0.5)
                try:
                    pos_info = client.futures_position_information(symbol=symbol)
                    for pos in pos_info:
                        if float(pos['positionAmt']) != 0:
                            position_active = True
                            actual_entry = float(pos['entryPrice'])
                            break
                except Exception as e:
                    logger.warning(f"Percobaan {attempt+1} verifikasi posisi [{symbol}]: {e}")
                if position_active:
                    break
                    
            if not position_active:
                logger.warning(f"Posisi [{symbol}] belum terdeteksi aktif setelah 2.5 detik. Tetap melanjutkan pemasangan SL...")
                
            if actual_entry <= 0:
                actual_entry = entry_price_rounded
                
            size_usdt = qty * actual_entry
            margin_used = size_usdt / FIXED_LEVERAGE
            potential_loss = qty * abs(actual_entry - sl_price)
            
            msg = f"✅ *Berhasil Entry Market {side} {symbol}* (dalam batas toleransi 0.2%)"
            
            sl_side = "BUY" if side == "SELL" else "SELL"
            sl_res = client.futures_create_order(
                symbol=symbol, side=sl_side, type='STOP_MARKET', stopPrice=sl_price, closePosition=True
            )
            sl_order_id = str(sl_res.get('orderId') or sl_res.get('algoId'))
            logger.info(f"Stop Loss awal dipasang [{symbol}]: OrderID={sl_order_id}, Price={sl_price}")
            
            tp1_order_id, tp2_order_id, tp3_order_id = place_partial_tps(
                symbol, side, qty, data['tp1'], data['tp2'], data['tp3'], tick_size, step_size
            )
            
            sl_msg = f"\n🛡️ Stop Loss & 3 Limit TP Aktif."
            entry_price_display = actual_entry
        else:
            logger.info(f"Mengeksekusi LIMIT order [{symbol}] {side} Price={entry_price_rounded} Qty={qty}...")
            order_res = client.futures_create_order(
                symbol=symbol, side=side, type=ORDER_TYPE_LIMIT, 
                price=entry_price_rounded, quantity=qty, timeInForce=TIME_IN_FORCE_GTC
            )
            entry_order_id = str(order_res['orderId'])
            
            size_usdt = qty * entry_price_rounded
            margin_used = size_usdt / FIXED_LEVERAGE
            potential_loss = qty * abs(entry_price_rounded - sl_price)
            
            msg = f"⏳ *Memasang LIMIT Order {side} {symbol}* di harga `{entry_price_rounded}` (di luar toleransi)"
            sl_msg = f"\n🛡️ Stop Loss & Limit TP akan diaktifkan otomatis saat terisi."
            entry_price_display = entry_price_rounded

        qty_tp1 = round_step(qty * 0.50, step_size)
        qty_tp2 = round_step(qty * 0.25, step_size)
        qty_tp3 = round_step(qty - qty_tp1 - qty_tp2, step_size)

        tp1_price = round_step(data['tp1'], tick_size)
        tp2_price = round_step(data['tp2'], tick_size)
        tp3_price = round_step(data['tp3'], tick_size)

        pnl_tp1 = qty_tp1 * abs(tp1_price - entry_price_display)
        pnl_tp2 = qty_tp2 * abs(tp2_price - entry_price_display)
        pnl_tp3 = qty_tp3 * abs(tp3_price - entry_price_display)
        total_pnl_tp = pnl_tp1 + pnl_tp2 + pnl_tp3

        pct1 = (abs(tp1_price - entry_price_display) / entry_price_display) * 100
        pct2 = (abs(tp2_price - entry_price_display) / entry_price_display) * 100
        pct3 = (abs(tp3_price - entry_price_display) / entry_price_display) * 100
        
        roe1 = pct1 * FIXED_LEVERAGE
        roe2 = pct2 * FIXED_LEVERAGE
        roe3 = pct3 * FIXED_LEVERAGE
        
        risk_display = f"{risk_pct * 100:.1f}%" if risk_pct is not None else f"{MAX_RISK_PERCENT * 100:.1f}%"
            
        info_msg = (
            f"\n\n📊 *Rincian Posisi:*\n"
            f"• Entry Price: `{entry_price_display}`\n"
            f"• Size: `{qty} {symbol.replace('USDT', '')}` (`{size_usdt:.2f} USDT`)\n"
            f"• Margin: `{margin_used:.2f} USDT` (Leverage {FIXED_LEVERAGE}x)\n"
            f"• Stop Loss: `{sl_price}`\n"
            f"• Target Risiko: `{risk_display}`\n"
            f"• Potensi Kerugian: `-{potential_loss:.2f} USDT`\n\n"
            f"🎯 *Rincian Target Take Profit:*\n"
            f"• TP1 (50%): `{tp1_price}` (+{pct1:.2f}% / +{roe1:.2f}% ROE) -> `+{pnl_tp1:.2f} USDT`\n"
            f"• TP2 (25%): `{tp2_price}` (+{pct2:.2f}% / +{roe2:.2f}% ROE) -> `+{pnl_tp2:.2f} USDT`\n"
            f"• TP3 (25%): `{tp3_price}` (+{pct3:.2f}% / +{roe3:.2f}% ROE) -> `+{pnl_tp3:.2f} USDT`\n"
            f"• Total Potensi Profit: `+{total_pnl_tp:.2f} USDT`"
        )
        
        add_trade(
            symbol, side, entry_price_display, data['sl'], data['tp1'], data['tp2'], data['tp3'],
            initial_qty=qty, remaining_qty=qty,
            entry_order_id=entry_order_id, sl_order_id=sl_order_id,
            tp1_order_id=tp1_order_id, tp2_order_id=tp2_order_id, tp3_order_id=tp3_order_id
        )
        
        logger.info(f"Eksekusi trade [{symbol}] selesai dengan sukses.")
        return f"{msg}{sl_msg}{info_msg}"
    except Exception as e:
        logger.error(f"Error eksekusi trade [{symbol}]: {e}", exc_info=True)
        return f"❌ Error eksekusi: {e}"
