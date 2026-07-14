from config import client, FIXED_LEVERAGE, MAX_RISK_PERCENT
from database import add_trade
from binance.exceptions import BinanceAPIException
from binance.enums import *

def get_symbol_info(symbol):
    """Mendapatkan tickSize dan stepSize dari filter Futures exchange info Binance."""
    info = client.futures_exchange_info()
    tick_size = 0.01
    step_size = 1.0
    for item in info['symbols']:
        if item['symbol'] == symbol:
            for f in item['filters']:
                if f['filterType'] == 'PRICE_FILTER':
                    tick_size = float(f['tickSize'])
                elif f['filterType'] == 'LOT_SIZE':
                    step_size = float(f['stepSize'])
            return tick_size, step_size
    return tick_size, step_size

def round_step(value, step_size):
    """Membulatkan nilai sesuai tickSize/stepSize untuk menghindari error API Binance."""
    if not step_size:
        return value
    # Format ke string dengan presisi tinggi untuk menghindari floating point issues
    step_str = f"{step_size:.10f}".rstrip('0')
    if '.' in step_str:
        decimals = len(step_str.split('.')[1])
    else:
        decimals = 0
    return round(round(value / step_size) * step_size, decimals)

def calculate_position_size(symbol, entry_price, sl_price, step_size, risk_pct=None):
    """Menghitung ukuran posisi (kuantitas) berdasarkan persentase risiko akun."""
    account_info = client.futures_account()
    usdt_balance = float([a['availableBalance'] for a in account_info['assets'] if a['asset'] == 'USDT'][0])
    
    # Gunakan kustom risk_pct jika tersedia, jika tidak default ke MAX_RISK_PERCENT (2%)
    actual_risk_pct = risk_pct if risk_pct is not None else MAX_RISK_PERCENT
    risk_amount = usdt_balance * actual_risk_pct
    sl_distance_pct = abs(entry_price - sl_price) / entry_price
    position_size_usd = risk_amount / sl_distance_pct
    qty = position_size_usd / entry_price
    return round_step(qty, step_size)

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
    
    if qty_tp1 > 0:
        o1 = client.futures_create_order(
            symbol=symbol, side=tp_side, type=ORDER_TYPE_LIMIT,
            price=round_step(tp1, tick_size), quantity=qty_tp1,
            timeInForce=TIME_IN_FORCE_GTC, reduceOnly=True
        )
        tp1_order_id = str(o1['orderId'])
        
    if qty_tp2 > 0:
        o2 = client.futures_create_order(
            symbol=symbol, side=tp_side, type=ORDER_TYPE_LIMIT,
            price=round_step(tp2, tick_size), quantity=qty_tp2,
            timeInForce=TIME_IN_FORCE_GTC, reduceOnly=True
        )
        tp2_order_id = str(o2['orderId'])
        
    if qty_tp3 > 0:
        o3 = client.futures_create_order(
            symbol=symbol, side=tp_side, type=ORDER_TYPE_LIMIT,
            price=round_step(tp3, tick_size), quantity=qty_tp3,
            timeInForce=TIME_IN_FORCE_GTC, reduceOnly=True
        )
        tp3_order_id = str(o3['orderId'])
        
    return tp1_order_id, tp2_order_id, tp3_order_id

def execute_trade(data):
    """Membuka posisi Futures di Binance dan memasang SL awal."""
    symbol = data['symbol']
    side = data['side']
    risk_pct = data.get('risk') # Risiko kustom jika diekstrak dari sinyal
    
    try:
        tick_size, step_size = get_symbol_info(symbol)
        
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
        
        # Setup Leverage & Margin
        client.futures_change_leverage(symbol=symbol, leverage=FIXED_LEVERAGE)
        try:
            client.futures_change_margin_type(symbol=symbol, marginType='ISOLATED')
        except BinanceAPIException as e:
            if e.code != -4046: raise e # Abaikan jika sudah isolated
            
        qty = calculate_position_size(symbol, data['entry'], data['sl'], step_size, risk_pct)
        if qty <= 0: return "Gagal: Kuantitas terlalu kecil."

        entry_price_rounded = round_step(data['entry'], tick_size)
        sl_price = round_step(data['sl'], tick_size)
        
        entry_order_id = None
        sl_order_id = None
        tp1_order_id = None
        tp2_order_id = None
        tp3_order_id = None
        
        if use_market_order:
            # Open Position via Market Order
            order_res = client.futures_create_order(symbol=symbol, side=side, type=ORDER_TYPE_MARKET, quantity=qty)
            entry_order_id = str(order_res['orderId'])
            
            # Beri jeda 500ms agar engine Binance memperbarui info posisi
            import time
            time.sleep(0.5)
            
            # Ambil entry price riil dari detail posisi aktif
            actual_entry = entry_price_rounded
            try:
                pos_info = client.futures_position_information(symbol=symbol)
                for pos in pos_info:
                    if float(pos['positionAmt']) != 0:
                        actual_entry = float(pos['entryPrice'])
                        break
            except Exception as e:
                print(f"[WARN] Gagal mendapatkan real entry price: {e}")
                
            if actual_entry <= 0:
                actual_entry = entry_price_rounded
                
            # Rekalkulasi metrik posisi berdasarkan harga eksekusi aktual (mencegah selisih akibat slippage)
            size_usdt = qty * actual_entry
            margin_used = size_usdt / FIXED_LEVERAGE
            potential_loss = qty * abs(actual_entry - sl_price)
            
            msg = f"✅ *Berhasil Entry Market {side} {symbol}* (dalam batas toleransi 0.2%)"
            
            # Initial SL (Hanya untuk Market Order karena posisi langsung terbuka)
            sl_side = "BUY" if side == "SELL" else "SELL"
            sl_res = client.futures_create_order(
                symbol=symbol, side=sl_side, type='STOP_MARKET', stopPrice=sl_price, closePosition=True
            )
            sl_order_id = str(sl_res.get('orderId') or sl_res.get('algoId'))
            
            # Pasang Limit Take Profit Parsial (50% TP1, 25% TP2, 25% TP3)
            tp1_order_id, tp2_order_id, tp3_order_id = place_partial_tps(
                symbol, side, qty, data['tp1'], data['tp2'], data['tp3'], tick_size, step_size
            )
            
            sl_msg = f"\n🛡️ Stop Loss & 3 Limit TP Aktif."
            entry_price_display = actual_entry
        else:
            # Open Position via Limit Order
            order_res = client.futures_create_order(
                symbol=symbol, side=side, type=ORDER_TYPE_LIMIT, 
                price=entry_price_rounded, quantity=qty, timeInForce=TIME_IN_FORCE_GTC
            )
            entry_order_id = str(order_res['orderId'])
            
            # Untuk Limit Order, harga eksekusi sama dengan harga limit
            size_usdt = qty * entry_price_rounded
            margin_used = size_usdt / FIXED_LEVERAGE
            potential_loss = qty * abs(entry_price_rounded - sl_price)
            
            msg = f"⏳ *Memasang LIMIT Order {side} {symbol}* di harga `{entry_price_rounded}` (di luar toleransi)"
            sl_msg = f"\n🛡️ Stop Loss & Limit TP akan diaktifkan otomatis saat terisi."
            entry_price_display = entry_price_rounded

        # Hitung pembagian kuantitas TP parsial untuk estimasi profit
        qty_tp1 = round_step(qty * 0.50, step_size)
        qty_tp2 = round_step(qty * 0.25, step_size)
        qty_tp3 = round_step(qty - qty_tp1 - qty_tp2, step_size)

        tp1_price = round_step(data['tp1'], tick_size)
        tp2_price = round_step(data['tp2'], tick_size)
        tp3_price = round_step(data['tp3'], tick_size)

        # Hitung PnL estimasi
        pnl_tp1 = qty_tp1 * abs(tp1_price - entry_price_display)
        pnl_tp2 = qty_tp2 * abs(tp2_price - entry_price_display)
        pnl_tp3 = qty_tp3 * abs(tp3_price - entry_price_display)
        total_pnl_tp = pnl_tp1 + pnl_tp2 + pnl_tp3

        # Hitung persentase kenaikan harga & ROE (leveraged)
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
        
        # Simpan ke Database beserta order ID
        add_trade(
            symbol, side, data['entry'], data['sl'], data['tp1'], data['tp2'], data['tp3'],
            entry_order_id, sl_order_id, tp1_order_id, tp2_order_id, tp3_order_id
        )
        
        return f"{msg}{sl_msg}{info_msg}"
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"❌ Error eksekusi: {e}"
