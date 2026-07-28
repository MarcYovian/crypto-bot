import logging
from dataclasses import dataclass
from typing import Optional
from src.services.precision_filter import PrecisionFilterService, SymbolInfo

logger = logging.getLogger(__name__)


@dataclass
class RiskCalculationResult:
    """Result of a risk calculation for a Binance Futures position.

    Attributes:
        is_valid: Whether the calculation succeeded.
        risk_amount: Actual risk amount after recalculations (USDT).
        entry_price: Entry price formatted to symbol precision.
        stop_loss_price: Stop loss price formatted to symbol precision.
        stop_distance: Absolute distance between entry and stop loss.
        stop_distance_percent: Stop distance as a percentage of entry price.
        position_size: Position size (quantity) formatted to Binance LOT_SIZE rules.
        notional_value: Total position notional value (Qty * Entry).
        required_margin: Margin required in USDT given the selected leverage.
        leverage: Leverage used for the position.
        error_message: Error description if is_valid is False.
    """
    is_valid: bool
    risk_amount: float
    entry_price: float
    stop_loss_price: float
    stop_distance: float
    stop_distance_percent: float
    position_size: float         # Formatted lot size (Qty)
    notional_value: float        # Total position value (Qty * Entry)
    required_margin: float       # Used USDT margin
    leverage: int
    error_message: Optional[str] = None


class RiskCalculatorService:
    """Calculate position sizes for Binance Futures using fixed-fractional risk.

    Determines the lot size, margin, and actual risk for a trade based on a
    user-defined daily risk budget, entry/stop-loss prices, and exchange-level
    symbol filters (price precision, LOT_SIZE, min_notional, etc.).
    """

    @classmethod
    def calculate_position(
        cls,
        daily_risk_amount: float,
        entry_price: float,
        stop_loss_price: float,
        side: str,                       # 'BUY' or 'SELL'
        max_leverage: int,
        symbol_info: SymbolInfo
    ) -> RiskCalculationResult:
        """Derive position size from a fixed-fractional risk rule.

        The core formula is::

            Risk Amount = Qty * |Entry - StopLoss|
            Qty = Risk Amount / Stop Distance

        The pipeline:
        1. Format entry and stop-loss to the symbol's tick size / price
           precision.
        2. Compute stop distance and guard against zero-distance (invalid).
        3. Derive raw quantity from ``daily_risk_amount / stop_distance``.
        4. Round the quantity down to the symbol's LOT_SIZE step size.
        5. Clamp to ``max_qty`` if exceeded (with a warning log).
        6. Enforce ``min_qty`` and ``min_notional`` — if either is violated the
           quantity is bumped up to the smallest compliant value.
        7. Compute required margin (``notional / max_leverage``) and the actual
           risk after all adjustments.

        Args:
            daily_risk_amount:
                Maximum acceptable loss in USDT for this trade.
            entry_price:
                Intended entry price.
            stop_loss_price:
                Intended stop-loss price.
            side:
                ``'BUY'`` or ``'SELL'``.
            max_leverage:
                Maximum leverage to apply for margin calculation.
            symbol_info:
                Exchange-level filters for the symbol (price precision,
                LOT_SIZE, min_notional, etc.).

        Returns:
            A ``RiskCalculationResult`` instance.  ``is_valid`` is ``False``
            when the stop distance is zero and an ``error_message`` is
            populated; otherwise ``is_valid`` is ``True`` and all position
            fields are filled.
        """
        # 1. Format Entry & SL to Binance price precision
        clean_entry = PrecisionFilterService.format_price(entry_price, symbol_info)
        clean_sl = PrecisionFilterService.format_price(stop_loss_price, symbol_info)

        # 2. Calculate Stop Distance
        stop_distance = abs(clean_entry - clean_sl)
        if stop_distance <= 0:
            return RiskCalculationResult(
                is_valid=False, risk_amount=daily_risk_amount, entry_price=clean_entry,
                stop_loss_price=clean_sl, stop_distance=0, stop_distance_percent=0,
                position_size=0, notional_value=0, required_margin=0, leverage=1,
                error_message="Entry and Stop Loss prices cannot be identical."
            )

        stop_distance_percent = (stop_distance / clean_entry) * 100

        # 3. Calculate Raw Quantity (Position Size)
        raw_qty = daily_risk_amount / stop_distance

        # 4. Format Quantity per Binance LOT_SIZE & STEP_SIZE
        formatted_qty = PrecisionFilterService.format_qty(raw_qty, symbol_info)

        # 5. Dynamic recalc if above Binance max_qty
        if symbol_info.max_qty > 0 and formatted_qty > symbol_info.max_qty:
            logger.info(f"[{symbol_info.symbol}] Ideal qty ({formatted_qty}) exceeds max_qty ({symbol_info.max_qty}). Recalculating to max_qty.")
            formatted_qty = PrecisionFilterService.format_qty(symbol_info.max_qty, symbol_info)

        # 6. Dynamic recalc if below Binance min_qty or min_notional
        notional_value = formatted_qty * clean_entry
        if formatted_qty < symbol_info.min_qty or notional_value < symbol_info.min_notional:
            # Calculate minimum qty to satisfy both min_qty and min_notional
            required_qty = max(symbol_info.min_qty, symbol_info.min_notional / clean_entry)
            formatted_qty = PrecisionFilterService.format_qty(required_qty, symbol_info)
            if formatted_qty < required_qty:
                formatted_qty += symbol_info.step_size
                formatted_qty = PrecisionFilterService.format_qty(formatted_qty, symbol_info)
            notional_value = formatted_qty * clean_entry

        # 7. Calculate Margin Requirement & Leverage
        leverage = max_leverage
        required_margin = notional_value / leverage

        # Actual risk after recalculation
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