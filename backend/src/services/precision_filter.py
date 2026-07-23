import math
from typing import Dict, Any
from dataclasses import dataclass


@dataclass
class SymbolInfo:
    symbol: str
    price_precision: int      # Jumlah desimal untuk harga
    qty_precision: int        # Jumlah desimal untuk jumlah lot
    tick_size: float          # Minimum perubahan harga (misal: 0.10)
    step_size: float          # Minimum perubahan lot (misal: 0.001)
    min_qty: float            # Minimal kuantitas order
    min_notional: float       # Minimal nilai transaksi USDT (misal: 5.0 USDT)
    max_qty: float = 99999999.0 # Maksimal kuantitas order per request Binance


class PrecisionFilterService:
    """
    Utility untuk menyesuaikan angka presisi harga & lot sesuai aturan Binance Exchange Info.
    """

    @staticmethod
    def format_price(price: float, symbol_info: SymbolInfo) -> float:
        """Membulatkan harga sesuai tick_size dan precision."""
        if symbol_info.tick_size > 0:
            precision = int(round(-math.log10(symbol_info.tick_size)))
            return round(price, precision)
        return round(price, symbol_info.price_precision)

    @staticmethod
    def format_qty(qty: float, symbol_info: SymbolInfo) -> float:
        """
        Membulatkan jumlah lot kebawah (floor) sesuai step_size dan qty_precision.
        """
        step = symbol_info.step_size
        if step > 0:
            precision = int(round(-math.log10(step)))
            factor = 10 ** precision
            return math.floor(qty * factor) / factor
        return round(qty, symbol_info.qty_precision)

    @staticmethod
    def validate_min_notional(qty: float, price: float, symbol_info: SymbolInfo) -> tuple[bool, str]:
        """Validasi apakah nilai order memenuhi syarat MIN_NOTIONAL dan MIN_QTY Binance."""
        if qty < symbol_info.min_qty:
            return False, f"Qty ({qty}) di bawah MIN_QTY Binance ({symbol_info.min_qty})"
        
        notional_value = qty * price
        if notional_value < symbol_info.min_notional:
            return False, f"Nilai Notional (${notional_value:.2f}) di bawah MIN_NOTIONAL (${symbol_info.min_notional})"
        
        return True, ""