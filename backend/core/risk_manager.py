from backend.config import client, MAX_RISK_PERCENT
from backend.db.repository import get_config, set_config
from backend.logger import logger

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
    """Menghitung ukuran posisi (kuantitas) berdasarkan Daily Anchor Balance & konfigurasi risiko."""
    try:
        account_info = client.futures_account()
        avail_balance = float([a['availableBalance'] for a in account_info['assets'] if a['asset'] == 'USDT'][0])
        
        # Hitung Total Account Equity = Available Balance + Total Initial Margin Terikat di Posisi Aktif
        pos_info = client.futures_position_information()
        total_initial_margin = sum(abs(float(p['positionAmt'])) * float(p['entryPrice']) / 15.0 for p in pos_info if float(p['positionAmt']) != 0)
        total_equity = avail_balance + total_initial_margin

        # Ambil konfigurasi dari database bot_config
        db_mode = get_config("risk_mode", "DAILY_ANCHOR")
        db_risk_pct = float(get_config("risk_pct", str(MAX_RISK_PERCENT)))
        anchor_val = float(get_config("daily_anchor_balance", "0.0"))

        actual_risk_pct = risk_pct if risk_pct is not None else db_risk_pct

        # Inisialisasi daily_anchor_balance jika belum terisi / bernilai 0.0
        if anchor_val <= 0:
            anchor_val = total_equity
            set_config("daily_anchor_balance", anchor_val)
            logger.info(f"Daily Anchor Balance diinisialisasi: ${anchor_val:.2f} USDT")

        # Hitung Risk Amount berdasarkan mode
        if db_mode == "FIXED_USD":
            risk_amount = float(get_config("fixed_risk_usd", "2.0"))
        else:
            # Mode DAILY_ANCHOR (Default): Berpatokan pada Anchor Balance Harian
            risk_amount = anchor_val * actual_risk_pct

        sl_distance_pct = abs(entry_price - sl_price) / entry_price
        if sl_distance_pct == 0:
            logger.warning(f"Jarak Stop Loss 0 untuk {symbol}. Mengabaikan kalkulasi.")
            return 0.0

        position_size_usd = risk_amount / sl_distance_pct
        qty = position_size_usd / entry_price
        rounded_qty = round_step(qty, step_size)
        
        logger.info(
            f"Kalkulasi Risk Manager [{symbol}]: Mode={db_mode}, AnchorBalance=${anchor_val:.2f} USDT, "
            f"AvailBalance=${avail_balance:.2f} USDT, TotalEquity=${total_equity:.2f} USDT, "
            f"RiskPct={actual_risk_pct*100:.1f}%, RiskAmount=${risk_amount:.2f} USDT, CalculatedQty={rounded_qty}"
        )
        return rounded_qty
    except Exception as e:
        logger.error(f"Gagal menghitung posisi size untuk {symbol}: {e}", exc_info=True)
        return 0.0
