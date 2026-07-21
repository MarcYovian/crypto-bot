from backend.config import client, MAX_RISK_PERCENT
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
    """Menghitung ukuran posisi (kuantitas) berdasarkan persentase risiko akun."""
    try:
        account_info = client.futures_account()
        usdt_balance = float([a['availableBalance'] for a in account_info['assets'] if a['asset'] == 'USDT'][0])
        
        # Gunakan kustom risk_pct jika tersedia, jika tidak default ke MAX_RISK_PERCENT (2%)
        actual_risk_pct = risk_pct if risk_pct is not None else MAX_RISK_PERCENT
        risk_amount = usdt_balance * actual_risk_pct
        sl_distance_pct = abs(entry_price - sl_price) / entry_price
        position_size_usd = risk_amount / sl_distance_pct
        qty = position_size_usd / entry_price
        rounded_qty = round_step(qty, step_size)
        
        logger.info(
            f"Kalkulasi Risk Manager [{symbol}]: Balance={usdt_balance:.2f} USDT, "
            f"RiskPct={actual_risk_pct*100:.1f}%, RiskAmount={risk_amount:.2f} USDT, "
            f"CalculatedQty={rounded_qty}"
        )
        return rounded_qty
    except Exception as e:
        logger.error(f"Gagal menghitung posisi size untuk {symbol}: {e}", exc_info=True)
        return 0.0
