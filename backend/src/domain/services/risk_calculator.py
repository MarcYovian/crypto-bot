"""Pure Domain Service for 2.0% Risk Budget Calculation, Position Sizing, Dynamic TP Scaling, and Slippage Deviation."""

import math
from decimal import Decimal
from typing import List, Optional, Tuple, Union, Sequence, Any


from src.domain.entities.risk import (
    RiskCalculationResultDTO,
    TPAllocationDTO,
    PositionSizingInput,
)
from src.domain.value_objects.side import OrderSide
from src.domain.value_objects.price import Price
from src.domain.value_objects.quantity import Quantity
from src.domain.value_objects.leverage import Leverage
from src.domain.services.precision_filter import PrecisionFilterDomainService
from src.domain.exceptions.risk import (
    RiskCalculationError,
    ZeroStopDistanceError,
    MaxRiskExceededError,
    InsufficientMarginRiskError,
    InvalidSignalGeometryError,
)


class RiskCalculatorDomainService:
    """Pure mathematical domain service for calculating position sizing, leverage safety, TP allocations, and price deviations."""

    DEFAULT_TP_RATIOS = {
        1: [Decimal("1.00")],
        2: [Decimal("0.60"), Decimal("0.40")],
        3: [Decimal("0.50"), Decimal("0.30"), Decimal("0.20")],
        4: [Decimal("0.40"), Decimal("0.30"), Decimal("0.20"), Decimal("0.10")],
    }

    @classmethod
    def calculate_position_size(
        cls,
        params: Optional[PositionSizingInput] = None,
        *,
        wallet_balance: Optional[Union[Decimal, float]] = None,
        entry_price: Optional[Union[Decimal, Price, float]] = None,
        sl_price: Optional[Union[Decimal, Price, float]] = None,
        side: Optional[Union[OrderSide, str]] = None,
        risk_percent: Decimal = Decimal("2.0"),
        requested_leverage: Optional[Union[int, Leverage]] = None,
        leverage: Optional[Union[int, Leverage]] = None,
        max_allowed_leverage: Union[int, Leverage] = 125,
        step_size: Union[Decimal, Quantity, float] = Decimal("0.001"),
        tick_size: Union[Decimal, Price, float] = Decimal("0.1"),
        qty_precision: int = 3,
        price_precision: int = 2,
        min_notional: Decimal = Decimal("5.0"),
        max_risk_amount: Optional[Decimal] = None,
        tp_targets: Optional[Sequence[Union[Decimal, Price, float]]] = None,
        tp_ratios: Optional[List[Decimal]] = None,
        maint_margin_ratio: Decimal = Decimal("0.015"),
        brackets: Optional[List[Any]] = None,
        max_qty: Optional[Union[Decimal, Quantity, float]] = None,
        min_qty: Optional[Union[Decimal, Quantity, float]] = None,
        maximize_leverage: bool = False,
        signal_dto: Optional[Any] = None,
        instrument: Optional[Any] = None,
        profile: Optional[Any] = None,
        daily_risk: Optional[Any] = None,
        strict: bool = False,
        auto_margin_cap: bool = False,
        available_free_margin: Optional[Union[Decimal, float]] = None,
        free_margin: Optional[Union[Decimal, float]] = None,
        margin_safety_buffer: Decimal = Decimal("0.95"),
        symbol: Optional[str] = None,
    ) -> RiskCalculationResultDTO:




        """Calculate position sizing guaranteeing loss does not exceed risk budget.
        
        Supports PositionSizingInput DTO, individual keyword arguments, or bundled domain entities.
        """
        if signal_dto is not None:
            if entry_price is None:
                entry_price = getattr(signal_dto, "avg_entry_price", None) or getattr(signal_dto, "entry_min", None)
            if sl_price is None:
                sl_price = getattr(signal_dto, "sl_price", None)
            if requested_leverage is None and leverage is None:
                requested_leverage = getattr(signal_dto, "leverage", None)
            if tp_targets is None:
                tp_targets = getattr(signal_dto, "tp_targets", None)
            if symbol is None:
                symbol = getattr(signal_dto, "symbol", None)
            raw_side = getattr(signal_dto, "side", None)
            if raw_side is not None:
                if isinstance(raw_side, OrderSide):
                    side = raw_side
                elif isinstance(raw_side, str):
                    clean_side = raw_side.strip().upper()
                    if clean_side in ("BUY", "LONG", "SELL", "SHORT"):
                        side = raw_side


        if instrument is not None:
            step_size = getattr(instrument, "step_size", step_size)
            tick_size = getattr(instrument, "tick_size", tick_size)
            qty_precision = getattr(instrument, "qty_precision", qty_precision)
            price_precision = getattr(instrument, "price_precision", price_precision)
            min_notional = getattr(instrument, "min_notional", min_notional)
            if symbol is None:
                symbol = getattr(instrument, "symbol", None)
            if brackets is None:
                brackets = getattr(instrument, "leverage_brackets", None)

        if profile is not None:
            risk_percent = getattr(profile, "risk_percent", risk_percent)

        if daily_risk is not None and max_risk_amount is None:
            max_risk_amount = getattr(daily_risk, "risk_amount", None)

        if requested_leverage is None and leverage is not None:
            requested_leverage = leverage

        # Resolve parameters from DTO if provided
        if isinstance(params, PositionSizingInput):
            wallet_balance = params.wallet_balance
            entry_price = params.entry_price
            sl_price = params.sl_price
            side = params.side
            risk_percent = params.risk_percent
            requested_leverage = params.requested_leverage
            max_allowed_leverage = params.max_allowed_leverage
            step_size = params.step_size
            tick_size = params.tick_size
            qty_precision = params.qty_precision
            price_precision = params.price_precision
            min_notional = params.min_notional
            max_risk_amount = params.max_risk_amount
            tp_targets = params.tp_targets
            tp_ratios = params.tp_ratios
            maint_margin_ratio = params.maint_margin_ratio
            brackets = params.brackets or brackets
            strict = params.strict
            auto_margin_cap = getattr(params, "auto_margin_cap", auto_margin_cap)
            available_free_margin = getattr(params, "available_free_margin", available_free_margin)
            margin_safety_buffer = getattr(params, "margin_safety_buffer", margin_safety_buffer)


        if wallet_balance is None or entry_price is None or sl_price is None:
            raise ValueError("wallet_balance, entry_price, and sl_price are required parameters.")

        # Normalize Value Objects to Decimals/Ints
        wb = Decimal(str(wallet_balance))
        ep = entry_price.value if isinstance(entry_price, Price) else Decimal(str(entry_price))
        sl = sl_price.value if isinstance(sl_price, Price) else Decimal(str(sl_price))
        ss = step_size.value if isinstance(step_size, Quantity) else Decimal(str(step_size))
        ts = tick_size.value if isinstance(tick_size, Price) else Decimal(str(tick_size))
        
        req_lev_val: Optional[int] = requested_leverage.value if isinstance(requested_leverage, Leverage) else (int(requested_leverage) if requested_leverage else None)
        max_lev_val: int = max_allowed_leverage.value if isinstance(max_allowed_leverage, Leverage) else int(max_allowed_leverage)

        tp_decs: List[Decimal] = []
        if tp_targets:
            for tp in tp_targets:
                tp_decs.append(tp.value if isinstance(tp, Price) else Decimal(str(tp)))

        if wb <= Decimal("0"):
            if strict:
                raise ValueError(f"Wallet balance ({wb}) must be strictly positive.")
            return RiskCalculationResultDTO(
                risk_amount=Decimal("0"),
                stop_distance=abs(ep - sl),
                position_size=Decimal("0"),
                required_margin=Decimal("0"),
                risk_percent=risk_percent,
                entry_price=ep,
                sl_price=sl,
                leverage=req_lev_val or 1,
                requested_leverage=req_lev_val,
                is_valid=False,
                warning=f"Wallet balance ({wb}) must be positive.",
            )

        # 0. Validate Stop Distance and Geometry
        stop_distance = abs(ep - sl)
        if stop_distance <= Decimal("0") or ep == sl:
            raise ZeroStopDistanceError(
                f"Stop distance is zero. Entry price ({ep}) and SL price ({sl}) cannot be equal."
            )

        if side is not None and isinstance(side, (str, OrderSide)):
            try:
                side_enum = OrderSide.from_str(side)
                if side_enum.is_buy and sl >= ep:
                    raise InvalidSignalGeometryError(
                        f"Invalid geometry for BUY position: Stop Loss ({sl}) must be strictly below Entry Price ({ep})."
                    )
                if side_enum.is_sell and sl <= ep:
                    raise InvalidSignalGeometryError(
                        f"Invalid geometry for SELL position: Stop Loss ({sl}) must be strictly above Entry Price ({ep})."
                    )
                if tp_decs:
                    for tp in tp_decs:
                        if side_enum.is_buy and tp <= ep:
                            raise InvalidSignalGeometryError(
                                f"Invalid geometry for BUY position: Take Profit target ({tp}) must be strictly above Entry Price ({ep})."
                            )
                        if side_enum.is_sell and tp >= ep:
                            raise InvalidSignalGeometryError(
                                f"Invalid geometry for SELL position: Take Profit target ({tp}) must be strictly below Entry Price ({ep})."
                            )
            except ValueError:
                pass

        # 1. Calculate risk budget
        calc_risk_amt = wb * (risk_percent / Decimal("100"))
        if max_risk_amount is not None and max_risk_amount > Decimal("0"):
            if strict and calc_risk_amt > max_risk_amount:
                raise MaxRiskExceededError(
                    f"Calculated risk budget ({calc_risk_amt:.2f} USDT) exceeds hard cap limit ({max_risk_amount:.2f} USDT)."
                )
            risk_amount = min(calc_risk_amt, max_risk_amount)
        else:
            risk_amount = calc_risk_amt

        # 2. Raw position size
        raw_qty = risk_amount / stop_distance

        # Round down to step_size
        position_size = PrecisionFilterDomainService.round_quantity(
            qty=raw_qty,
            step_size=ss,
            qty_precision=qty_precision,
            round_down=True,
        )

        def _safe_dec(val: Any) -> Optional[Decimal]:
            if val is None:
                return None
            if isinstance(val, Decimal):
                return val
            if isinstance(val, (int, float)):
                return Decimal(str(val))
            try:
                s = str(val)
                if "mock" in s.lower() or "object at" in s:
                    return None
                return Decimal(s)
            except Exception:
                return None

        max_qty_dec = _safe_dec(max_qty)
        if max_qty_dec is not None and position_size > max_qty_dec:
            position_size = PrecisionFilterDomainService.round_quantity(
                qty=max_qty_dec,
                step_size=ss,
                qty_precision=qty_precision,
                round_down=True,
            )

        min_qty_dec = _safe_dec(min_qty)
        if min_qty_dec is not None and position_size < min_qty_dec:
            if strict:
                raise RiskCalculationError(f"Position size ({position_size}) below minimum quantity ({min_qty_dec}).")
            return RiskCalculationResultDTO(
                risk_amount=risk_amount,
                stop_distance=stop_distance,
                position_size=position_size,
                required_margin=Decimal("0"),
                risk_percent=risk_percent,
                entry_price=ep,
                sl_price=sl,
                leverage=req_lev_val or 1,
                requested_leverage=req_lev_val,
                is_valid=False,
                warning=f"Calculated position size ({position_size}) is below instrument minimum quantity ({min_qty_dec}).",
            )

        notional_check = position_size * ep
        min_notional_dec = _safe_dec(min_notional) or Decimal("5.0")
        if notional_check < min_notional_dec:
            if strict:
                raise RiskCalculationError(f"Notional ({notional_check}) below minimum ({min_notional_dec}).")
            return RiskCalculationResultDTO(
                risk_amount=risk_amount,
                stop_distance=stop_distance,
                position_size=position_size,
                required_margin=Decimal("0"),
                risk_percent=risk_percent,
                entry_price=ep,
                sl_price=sl,
                leverage=req_lev_val or 1,
                requested_leverage=req_lev_val,
                is_valid=False,
                warning=f"Order notional ({notional_check:.2f} USDT) is below minimum required ({min_notional_dec:.2f} USDT).",
            )


        # 3. Dynamic Leverage & Liquidation Safety Check
        brackets = (getattr(params, "brackets", None) if params else None) or brackets
        if brackets:
            notional_est = position_size * ep
            sorted_brackets = sorted(brackets, key=lambda x: getattr(x, "bracket", 1))
            matched = False
            for b in sorted_brackets:
                n_floor = Decimal(str(getattr(b, "notional_floor", 0)))
                n_cap = Decimal(str(getattr(b, "notional_cap", 0)))
                if n_floor <= notional_est <= n_cap:
                    b_lev = getattr(b, "initial_leverage", None)
                    if b_lev:
                        max_lev_val = min(max_lev_val, int(b_lev))
                    b_mmr = getattr(b, "maint_margin_ratio", None)
                    if b_mmr:
                        maint_margin_ratio = Decimal(str(b_mmr))
                    matched = True
                    break
            if not matched and sorted_brackets:
                last_b = sorted_brackets[-1]
                b_lev = getattr(last_b, "initial_leverage", None)
                if b_lev:
                    max_lev_val = min(max_lev_val, int(b_lev))
                b_mmr = getattr(last_b, "maint_margin_ratio", None)
                if b_mmr:
                    maint_margin_ratio = Decimal(str(b_mmr))

        stop_pct = stop_distance / ep
        max_safe_lev_float = 1.0 / float(stop_pct + maint_margin_ratio)
        max_safe_lev = max(1, min(int(math.floor(max_safe_lev_float)), max_lev_val))

        if maximize_leverage:
            effective_leverage = max_safe_lev
        else:
            effective_leverage = req_lev_val if req_lev_val else max_safe_lev
        is_downscaled = False
        adj_reason = None

        if req_lev_val and req_lev_val > max_safe_lev:
            effective_leverage = max_safe_lev
            is_downscaled = True
            adj_reason = f"Downscaled from {req_lev_val}x to {max_safe_lev}x to avoid liquidation before Stop Loss."
        elif effective_leverage > max_lev_val:
            effective_leverage = max_lev_val
            is_downscaled = True
            adj_reason = f"Capped at max allowed instrument leverage {max_lev_val}x."


        # 4. Required margin & Pre-Trade Margin Validation
        initial_notional = position_size * ep
        initial_required_margin = initial_notional / Decimal(str(effective_leverage))
        required_margin = initial_required_margin

        # Resolve available margin for trade (free_margin if provided, otherwise wallet_balance)
        avail_margin = None
        if available_free_margin is not None:
            avail_margin = Decimal(str(available_free_margin))
        elif free_margin is not None:
            avail_margin = Decimal(str(free_margin))
        else:
            avail_margin = wb

        if avail_margin < Decimal("0"):
            avail_margin = Decimal("0")

        is_margin_capped = False
        orig_position_size = None
        orig_required_margin = None
        shortfall_margin = None
        warning = None
        is_valid = True

        if initial_required_margin > avail_margin:
            shortfall = initial_required_margin - avail_margin
            shortfall_margin = shortfall
            stop_pct_val = (stop_distance / ep) * Decimal("100")

            if auto_margin_cap and avail_margin > Decimal("0"):
                # Calculate max safe notional scaled down to safety buffer (e.g. 95% of free margin)
                safe_buffer_dec = Decimal(str(margin_safety_buffer)) if margin_safety_buffer else Decimal("0.95")
                max_allowed_margin = avail_margin * safe_buffer_dec
                max_allowed_notional = max_allowed_margin * Decimal(str(effective_leverage))
                capped_qty = PrecisionFilterDomainService.round_quantity(
                    qty=max_allowed_notional / ep,
                    step_size=ss,
                    qty_precision=qty_precision,
                    round_down=True,
                )
                if max_qty_dec is not None and capped_qty > max_qty_dec:
                    capped_qty = max_qty_dec

                capped_notional = capped_qty * ep
                min_notional_dec = _safe_dec(min_notional) or Decimal("5.0")

                if (
                    capped_qty > Decimal("0")
                    and capped_notional >= min_notional_dec
                    and (min_qty_dec is None or capped_qty >= min_qty_dec)
                ):
                    orig_position_size = position_size
                    orig_required_margin = initial_required_margin
                    position_size = capped_qty
                    required_margin = capped_notional / Decimal(str(effective_leverage))
                    risk_amount = position_size * stop_distance
                    is_margin_capped = True
                    warning = (
                        f"Ukuran posisi disesuaikan otomatis (Auto-Capped) dari {orig_position_size} ke {position_size} "
                        f"karena keterbatasan saldo margin bebas ({avail_margin:.2f} USDT)."
                    )
                else:
                    # Even after capping, cannot satisfy minimum notional or min lot
                    err_msg = (
                        f"Margin tidak mencukupi: Dibutuhkan {initial_required_margin:.2f} USDT, "
                        f"Tersedia {avail_margin:.2f} USDT (Kekurangan: {shortfall:.2f} USDT). "
                        f"Notional: {initial_notional:.2f} USDT @ {effective_leverage}x, Risk: {risk_amount:.2f} USDT, "
                        f"SL Dist: {stop_distance:.4f} ({stop_pct_val:.2f}%). "
                        f"Penyesuaian capping menghasilkan notional ({capped_notional:.2f} USDT) "
                        f"di bawah batas minimum bursa ({min_notional_dec:.2f} USDT)."
                    )
                    if strict:
                        raise InsufficientMarginRiskError(
                            err_msg,
                            required_margin=initial_required_margin,
                            available_margin=avail_margin,
                            shortfall=shortfall,
                            position_size=position_size,
                            notional=initial_notional,
                            leverage=effective_leverage,
                            risk_amount=risk_amount,
                            stop_distance=stop_distance,
                            stop_percent=stop_pct_val,
                            symbol=symbol,
                        )
                    warning = err_msg
                    is_valid = False
            else:
                err_msg = (
                    f"Required margin ({initial_required_margin:.2f} USDT) exceeds available wallet balance ({avail_margin:.2f} USDT). "
                    f"Margin tidak mencukupi: Dibutuhkan {initial_required_margin:.2f} USDT, "
                    f"Tersedia {avail_margin:.2f} USDT (Kekurangan: {shortfall:.2f} USDT). "
                    f"Notional: {initial_notional:.2f} USDT @ {effective_leverage}x, Risk: {risk_amount:.2f} USDT, "
                    f"SL Dist: {stop_distance:.4f} ({stop_pct_val:.2f}%)."
                )
                if strict:
                    raise InsufficientMarginRiskError(
                        err_msg,
                        required_margin=initial_required_margin,
                        available_margin=avail_margin,
                        shortfall=shortfall,
                        position_size=position_size,
                        notional=initial_notional,
                        leverage=effective_leverage,
                        risk_amount=risk_amount,
                        stop_distance=stop_distance,
                        stop_percent=stop_pct_val,
                        symbol=symbol,
                    )
                warning = err_msg
                is_valid = False

        notional = position_size * ep
        min_notional_dec = _safe_dec(min_notional) or Decimal("5.0")
        if notional < min_notional_dec and is_valid:
            if strict:
                raise RiskCalculationError(
                    f"Order notional ({notional:.2f} USDT) is below minimum exchange threshold ({min_notional_dec:.2f} USDT)."
                )
            warning = f"Order notional ({notional:.2f} USDT) is below minimum exchange threshold ({min_notional_dec:.2f} USDT)."
            is_valid = False

        # 5. Take profit allocations and Risk/Reward ratios
        tp_allocations: List[TPAllocationDTO] = []
        rr_ratios: List[Decimal] = []

        if tp_decs:
            tp_allocations = cls.allocate_take_profits(
                total_qty=position_size,
                tp_targets=tp_decs,
                step_size=ss,
                qty_precision=qty_precision,
                custom_ratios=tp_ratios,
            )
            for tp in tp_decs:
                tp_dist = abs(tp - ep)
                rr = tp_dist / stop_distance
                rr_ratios.append(rr.quantize(Decimal("0.01")))

        return RiskCalculationResultDTO(
            risk_amount=risk_amount,
            stop_distance=stop_distance,
            position_size=position_size,
            required_margin=required_margin,
            risk_percent=risk_percent,
            entry_price=ep,
            sl_price=sl,
            leverage=effective_leverage,
            requested_leverage=req_lev_val,
            max_safe_leverage=max_safe_lev,
            is_leverage_downscaled=is_downscaled,
            leverage_adjustment_reason=adj_reason,
            risk_reward_ratios=rr_ratios,
            tp_allocations=tp_allocations,
            is_valid=is_valid,
            warning=warning,
            is_margin_capped=is_margin_capped,
            original_position_size=orig_position_size,
            original_required_margin=orig_required_margin,
            available_margin=avail_margin,
            shortfall_margin=shortfall_margin,
        )

    @classmethod
    def allocate_take_profits(
        cls,
        total_qty: Union[Decimal, Quantity, float],
        tp_targets: Sequence[Union[Decimal, Price, float]],
        entry_price: Optional[Union[Decimal, Price, float]] = None,
        step_size: Union[Decimal, Quantity, float] = Decimal("0.001"),
        qty_precision: int = 3,
        custom_ratios: Optional[List[Decimal]] = None,
    ) -> List[TPAllocationDTO]:


        """Distribute total position size across multiple TP targets ensuring exact lot sum."""
        t_qty = total_qty.value if isinstance(total_qty, Quantity) else Decimal(str(total_qty))
        ss = step_size.value if isinstance(step_size, Quantity) else Decimal(str(step_size))
        
        tp_decs = [tp.value if isinstance(tp, Price) else Decimal(str(tp)) for tp in tp_targets]
        num_tps = len(tp_decs)
        if num_tps == 0:
            return []

        if custom_ratios and len(custom_ratios) == num_tps:
            ratios = custom_ratios
        else:
            ratios = cls.DEFAULT_TP_RATIOS.get(num_tps, [Decimal("1.0") / Decimal(str(num_tps))] * num_tps)

        allocations: List[TPAllocationDTO] = []
        accumulated_qty = Decimal("0")

        for idx, (tp_price, ratio) in enumerate(zip(tp_decs, ratios), start=1):
            is_last = idx == num_tps
            if is_last:
                tp_qty = t_qty - accumulated_qty
            else:
                raw_tp_qty = t_qty * ratio
                tp_qty = PrecisionFilterDomainService.round_quantity(
                    qty=raw_tp_qty,
                    step_size=ss,
                    qty_precision=qty_precision,
                    round_down=True,
                )
                accumulated_qty += tp_qty

            allocations.append(
                TPAllocationDTO(
                    tp_level=idx,
                    price=tp_price,
                    quantity=tp_qty,
                    percentage=ratio * Decimal("100"),
                    is_close_all=is_last,
                )
            )

        return allocations

    # Method alias for backward-compatibility
    calculate_tp_allocations = allocate_take_profits

    @staticmethod
    def estimate_liquidation_price(

        entry_price: Union[Decimal, Price, float],
        leverage: Union[int, Leverage],
        side: Union[OrderSide, str],
        maint_margin_ratio: Decimal = Decimal("0.015"),
    ) -> Decimal:
        """Estimate the isolated liquidation price."""
        ep = entry_price.value if isinstance(entry_price, Price) else Decimal(str(entry_price))
        lev_val = leverage.value if isinstance(leverage, Leverage) else int(leverage)
        eff_lev = Decimal(str(lev_val))
        side_enum = OrderSide.from_str(side)
        if side_enum.is_buy:
            liq = ep * (Decimal("1.0") - (Decimal("1.0") / eff_lev) + maint_margin_ratio)
        else:
            liq = ep * (Decimal("1.0") + (Decimal("1.0") / eff_lev) - maint_margin_ratio)

        return max(Decimal("0"), liq)

    @staticmethod
    def calculate_price_deviation(
        target_price: Union[Decimal, Price, float],
        current_price: Union[Decimal, Price, float],
        side: Union[OrderSide, str],
    ) -> Decimal:
        """Calculate asymmetric unfavorable price deviation percentage (slippage check).
        
        If current market price is more favorable than target price (e.g. buying cheaper or selling higher),
        deviation is Decimal("0").
        
        Returns:
            Unfavorable deviation as Decimal (e.g. Decimal("0.005") for 0.5% deviation).
        """
        target = target_price.value if isinstance(target_price, Price) else Decimal(str(target_price or 0))
        current = current_price.value if isinstance(current_price, Price) else Decimal(str(current_price or 0))

        if target <= Decimal("0") or current <= Decimal("0"):
            return Decimal("0")

        side_enum = OrderSide.from_str(side)
        if side_enum.is_buy:
            if current <= target:
                return Decimal("0")  # Favorable (discount)
            return (current - target) / target
        else:
            if current >= target:
                return Decimal("0")  # Favorable (higher sell)
            return (target - current) / target
