import logging
from dataclasses import dataclass
from typing import Optional
from src.services.precision_filter import PrecisionFilterService, SymbolInfo

logger = logging.getLogger(__name__)


@dataclass
class RiskCalculationResult:
    is_valid: bool
    risk_amount: float
    entry_price: float
    stop_loss_price: float
    stop_distance: float
    stop_distance_percent: float
    position_size: float         # Lot size terformat (Qty)
    notional_value: float        # Total nilai posisi (Qty * Entry)
    required_margin: float       # Margin USDT yang terpakai
    leverage: int
    error_message: Optional[str] = None


class RiskCalculatorService:
    """
    Engine Kalkulasi Risk Management Harian & Penentuan Lot Size Binance Futures.
    """

    @classmethod
    def calculate_position(
        cls,
        daily_risk_amount: float,
        entry_price: float,
        stop_loss_price: float,
        side: str,                       # 'BUY' atau 'SELL'
        max_leverage: int,
        symbol_info: SymbolInfo
    ) -> RiskCalculationResult:
        """
        Menhitung position size berdasarkan formula:
        Risk Amount = Qty * |Entry - StopLoss|
        => Qty = Risk Amount / Jarak StopLoss
        """
        # 1. Format Entry & SL sesuai presisi harga Binance
        clean_entry = PrecisionFilterService.format_price(entry_price, symbol_info)
        clean_sl = PrecisionFilterService.format_price(stop_loss_price, symbol_info)

        # 2. Hitung Jarak Stop Loss (Stop Distance)
        stop_distance = abs(clean_entry - clean_sl)
        if stop_distance <= 0:
            return RiskCalculationResult(
                is_valid=False, risk_amount=daily_risk_amount, entry_price=clean_entry,
                stop_loss_price=clean_sl, stop_distance=0, stop_distance_percent=0,
                position_size=0, notional_value=0, required_margin=0, leverage=1,
                error_message="Entry dan Stop Loss tidak boleh sama."
            )

        stop_distance_percent = (stop_distance / clean_entry) * 100

        # 3. Hitung Raw Quantity (Position Size)
        raw_qty = daily_risk_amount / stop_distance

        # 4. Format Quantity sesuai LOT_SIZE & STEP_SIZE Binance
        formatted_qty = PrecisionFilterService.format_qty(raw_qty, symbol_info)

        # 5. Rekalkulasi Dinamis jika melampaui max_qty Binance
        if symbol_info.max_qty > 0 and formatted_qty > symbol_info.max_qty:
            logger.info(f"[{symbol_info.symbol}] Qty ideal ({formatted_qty}) melampaui max_qty ({symbol_info.max_qty}). Melakukan rekalkulasi ke max_qty.")
            formatted_qty = PrecisionFilterService.format_qty(symbol_info.max_qty, symbol_info)

        # 6. Rekalkulasi Dinamis jika di bawah min_qty atau min_notional Binance
        notional_value = formatted_qty * clean_entry
        if formatted_qty < symbol_info.min_qty or notional_value < symbol_info.min_notional:
            # Hitung Qty minimal yang dibutuhkan agar lolos min_qty dan min_notional
            required_qty = max(symbol_info.min_qty, symbol_info.min_notional / clean_entry)
            formatted_qty = PrecisionFilterService.format_qty(required_qty, symbol_info)
            if formatted_qty < required_qty:
                formatted_qty += symbol_info.step_size
                formatted_qty = PrecisionFilterService.format_qty(formatted_qty, symbol_info)
            notional_value = formatted_qty * clean_entry

        # 7. Hitung Kebutuhan Margin & Leverage
        leverage = max_leverage
        required_margin = notional_value / leverage

        # Hitung risiko aktual hasil rekalkulasi
        actual_risk_amount = formatted_qty * stop_distance

        return RiskCalculationResult(
            is_valid=True,
            risk_amount=actual_risk_amount,
            entry_price=clean_entry,
            stop_loss_price=clean_sl,
            stop_distance=stop_distance,
            stop_distance_percent=stop_distance_percent,
            position_size=formatted_qty,
            notional_value=notional_value,
            required_margin=required_margin,
            leverage=leverage
        )