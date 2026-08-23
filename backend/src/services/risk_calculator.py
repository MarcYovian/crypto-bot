"""Strict 2.0% Risk Calculator and Position Sizing Service."""

from decimal import Decimal
from typing import Optional, List, Any
from src.domain.entities.risk import RiskCalculationResultDTO, TPAllocationDTO
from src.domain.exceptions.risk import (
    ZeroStopDistanceError,
    MaxRiskExceededError,
    InsufficientMarginRiskError,
)
from src.services.precision_filter import PrecisionFilterService, SymbolInfo

# Backward-compatibility alias
RiskCalculationResult = RiskCalculationResultDTO


class RiskCalculatorService:
    """Service for computing position sizes, margin requirements, and TP lot allocations."""

    @classmethod
    def calculate_position(
        cls,
        daily_risk_amount: Any,
        entry_price: Any,
        stop_loss_price: Any,
        side: str,
        max_leverage: int = 20,
        symbol_info: Any = None,
    ) -> RiskCalculationResultDTO:
        """Compatibility helper for recalculating position sizing from float values."""
        entry_p = float(entry_price)
        sl_p = float(stop_loss_price)
        risk_amt = float(daily_risk_amount)
        stop_dist = abs(entry_p - sl_p)
        if stop_dist <= 0:
            return RiskCalculationResultDTO(
                risk_amount=Decimal("0"),
                stop_distance=Decimal("0"),
                position_size=Decimal("0"),
                required_margin=Decimal("0"),
                risk_percent=Decimal("0"),
                entry_price=Decimal(str(entry_p)),
                sl_price=Decimal(str(sl_p)),
                leverage=max_leverage,
                is_valid=False,
                warning="Zero stop distance",
            )
        raw_qty = risk_amt / stop_dist
        step = getattr(symbol_info, "step_size", Decimal("0.001"))
        step_dec = Decimal(str(step)) if step else Decimal("0.001")
        pos_size = PrecisionFilterService.round_quantity(Decimal(str(raw_qty)), step_size=step_dec, round_down=True)
        margin = Decimal(str((float(pos_size) * entry_p) / max_leverage))
        return RiskCalculationResultDTO(
            risk_amount=Decimal(str(risk_amt)),
            stop_distance=Decimal(str(stop_dist)),
            position_size=pos_size,
            required_margin=margin,
            risk_percent=Decimal("2.0"),
            entry_price=Decimal(str(entry_p)),
            sl_price=Decimal(str(sl_p)),
            leverage=max_leverage,
            is_valid=True,
        )

    DEFAULT_TP_RATIOS = {
        1: [Decimal("1.00")],
        2: [Decimal("0.60"), Decimal("0.40")],
        3: [Decimal("0.50"), Decimal("0.30"), Decimal("0.20")],
        4: [Decimal("0.40"), Decimal("0.30"), Decimal("0.20"), Decimal("0.10")],
    }

    def calculate_position_size(
        self,
        wallet_balance: Decimal,
        risk_percent: Decimal,
        entry_price: Decimal,
        sl_price: Decimal,
        leverage: int,
        tp_targets: Optional[List[Decimal]] = None,
        tick_size: Decimal = Decimal("0.1"),
        step_size: Decimal = Decimal("0.001"),
        price_precision: int = 2,
        qty_precision: int = 3,
        min_notional: Decimal = Decimal("5.0"),
        max_risk_amount: Optional[Decimal] = None,
        tp_ratios: Optional[List[Decimal]] = None,
        brackets: Optional[List[Any]] = None,
    ) -> RiskCalculationResultDTO:
        """Calculate exact lot sizing guaranteeing loss does not exceed risk_percent of balance,
        and dynamically adjusts leverage to prevent early liquidation in ISOLATED margin.
        
        Args:
            wallet_balance: Account USDT wallet balance.
            risk_percent: Maximum percentage of balance to risk (e.g. Decimal("2.0")).
            entry_price: Entry execution price.
            sl_price: Stop loss price.
            leverage: Position leverage multiplier requested by signal.
            tp_targets: Optional list of Take Profit prices.
            tick_size: Instrument minimum tick size.
            step_size: Instrument lot step size.
            price_precision: Decimal places for prices.
            qty_precision: Decimal places for quantities.
            min_notional: Minimum order notional threshold (5.0 USDT).
            max_risk_amount: Optional absolute cap on loss amount.
            tp_ratios: Optional custom ratio distribution for TP orders.
            brackets: Optional list of InstrumentLeverageBracket models/objects for tiered notional & MMR.
            
        Returns:
            RiskCalculationResultDTO containing position size, required margin, effective leverage, and TP orders.
        """
        tp_targets = tp_targets or []
        stop_distance = abs(entry_price - sl_price)
        if stop_distance <= Decimal("0"):
            raise ZeroStopDistanceError(
                f"Invalid stop distance ({stop_distance}): Entry price ({entry_price}) and SL price ({sl_price}) cannot be equal."
            )

        if wallet_balance <= Decimal("0"):
            return RiskCalculationResultDTO(
                risk_amount=Decimal("0"),
                stop_distance=stop_distance,
                position_size=Decimal("0"),
                required_margin=Decimal("0"),
                risk_percent=risk_percent,
                entry_price=entry_price,
                sl_price=sl_price,
                leverage=leverage,
                requested_leverage=leverage,
                max_safe_leverage=1,
                is_leverage_downscaled=False,
                leverage_adjustment_reason=None,
                risk_reward_ratios=[],
                tp_allocations=[],
                is_valid=False,
                warning=f"Wallet balance ({wallet_balance}) must be positive.",
            )

        # 1. Calculate max allowable loss in USDT
        risk_amount = wallet_balance * (risk_percent / Decimal("100"))
        if max_risk_amount is not None and risk_amount > max_risk_amount:
            risk_amount = max_risk_amount

        # 2. Exact position size (Risk Amount / Stop Distance)
        raw_qty = risk_amount / stop_distance
        position_size = PrecisionFilterService.round_quantity(
            raw_qty, step_size=step_size, qty_precision=qty_precision, round_down=True
        )

        notional_value = position_size * entry_price
        sl_distance_pct = stop_distance / entry_price

        # 3. Resolve Tiered Leverage & MMR from Brackets
        mmr = Decimal("0.015")  # Default 1.5% MMR
        bracket_max_leverage = 125

        if brackets:
            matched_bracket = None
            for b in sorted(brackets, key=lambda x: getattr(x, "bracket", 1)):
                n_floor = Decimal(str(getattr(b, "notional_floor", 0)))
                n_cap = Decimal(str(getattr(b, "notional_cap", 0)))
                if n_floor <= notional_value <= n_cap:
                    matched_bracket = b
                    break

            if not matched_bracket and len(brackets) > 0:
                # If notional exceeds highest cap, select the last (most conservative) tier
                matched_bracket = sorted(brackets, key=lambda x: getattr(x, "bracket", 1))[-1]

            if matched_bracket:
                mmr = Decimal(str(getattr(matched_bracket, "maint_margin_ratio", "0.015")))
                bracket_max_leverage = int(getattr(matched_bracket, "initial_leverage", 20))

        # 4. Calculate Max Safe Leverage (Anti-Early Liquidation in ISOLATED mode)
        # Max Safe Leverage = 1 / (SL_Distance_% + MMR)
        total_risk_buffer = sl_distance_pct + mmr
        safe_raw = Decimal("1.0") / total_risk_buffer if total_risk_buffer > Decimal("0") else Decimal("20")
        max_safe_leverage = max(1, int(safe_raw))

        # 5. Determine Final Effective Leverage
        requested_leverage = leverage
        effective_leverage = min(requested_leverage, max_safe_leverage, bracket_max_leverage)

        is_downscaled = effective_leverage < requested_leverage
        downscale_reason = None
        if is_downscaled:
            if effective_leverage == max_safe_leverage:
                downscale_reason = (
                    f"Leverage disesuaikan dari {requested_leverage}x ke {effective_leverage}x "
                    f"agar Margin mencukupi jarak Stop Loss ({float(sl_distance_pct)*100:.1f}%) "
                    f"dan mencegah likuidasi dini."
                )
            else:
                downscale_reason = (
                    f"Leverage disesuaikan dari {requested_leverage}x ke {effective_leverage}x "
                    f"karena batas maksimal bursa untuk ukuran posisi ini adalah {bracket_max_leverage}x."
                )

        # 6. Margin required at effective leverage
        required_margin = (position_size * entry_price) / Decimal(str(effective_leverage))

        # 7. Risk-to-Reward Ratios
        rr_ratios: List[Decimal] = []
        for tp in tp_targets:
            tp_dist = abs(tp - entry_price)
            rr = (tp_dist / stop_distance).quantize(Decimal("0.01"))
            rr_ratios.append(rr)

        # 8. Take Profit Lot Allocations
        tp_allocations = self.calculate_tp_allocations(
            total_qty=position_size,
            tp_targets=tp_targets,
            entry_price=entry_price,
            step_size=step_size,
            qty_precision=qty_precision,
            ratios=tp_ratios,
        )

        # 9. Validations
        is_valid = True
        warning = None
        if not PrecisionFilterService.validate_min_notional(entry_price, position_size, min_notional):
            is_valid = False
            warning = f"Order notional ({position_size * entry_price} USDT) is below minimum required ({min_notional} USDT)."

        if required_margin > wallet_balance:
            is_valid = False
            warning = f"Required margin ({required_margin} USDT) exceeds wallet balance ({wallet_balance} USDT)."

        return RiskCalculationResultDTO(
            risk_amount=risk_amount,
            stop_distance=stop_distance,
            position_size=position_size,
            required_margin=required_margin.quantize(Decimal("0.01")),
            risk_percent=risk_percent,
            entry_price=entry_price,
            sl_price=sl_price,
            leverage=effective_leverage,
            requested_leverage=requested_leverage,
            max_safe_leverage=max_safe_leverage,
            is_leverage_downscaled=is_downscaled,
            leverage_adjustment_reason=downscale_reason,
            risk_reward_ratios=rr_ratios,
            tp_allocations=tp_allocations,
            is_valid=is_valid,
            warning=warning,
        )

    def calculate_tp_allocations(
        self,
        total_qty: Decimal,
        tp_targets: List[Decimal],
        entry_price: Decimal,
        step_size: Decimal = Decimal("0.001"),
        qty_precision: int = 3,
        ratios: Optional[List[Decimal]] = None,
    ) -> List[TPAllocationDTO]:
        """Divide total position lot size across Take Profit levels.
        
        Args:
            total_qty: Total open position quantity.
            tp_targets: List of TP target prices.
            entry_price: Entry price reference.
            step_size: Lot step size.
            qty_precision: Decimal places.
            ratios: Optional custom percentage splits.
            
        Returns:
            List of TPAllocationDTO objects where sum(quantity) == total_qty.
        """
        if not tp_targets or total_qty <= Decimal("0"):
            return []

        n_targets = len(tp_targets)
        if ratios is None:
            ratios = self.DEFAULT_TP_RATIOS.get(
                n_targets, [Decimal("1.0") / Decimal(str(n_targets))] * n_targets
            )

        allocations: List[TPAllocationDTO] = []
        allocated_qty = Decimal("0")

        for i, (price, ratio) in enumerate(zip(tp_targets, ratios)):
            is_last = i == (len(tp_targets) - 1)
            if is_last:
                # Assign exact remainder to the last target to ensure sum == total_qty
                target_qty = total_qty - allocated_qty
            else:
                raw_target_qty = total_qty * ratio
                target_qty = PrecisionFilterService.round_quantity(
                    raw_target_qty, step_size=step_size, qty_precision=qty_precision, round_down=True
                )
                allocated_qty += target_qty

            allocations.append(
                TPAllocationDTO(
                    tp_level=i + 1,
                    price=price,
                    quantity=target_qty,
                    percentage=ratio * Decimal("100"),
                    is_close_all=is_last,
                )
            )

        return allocations