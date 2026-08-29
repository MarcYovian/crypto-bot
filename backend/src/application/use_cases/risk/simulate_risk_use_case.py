"""Use case for simulating position sizing, leverage, and TP allocations for UI dashboard."""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional

from src.application.dto.risk_commands import SimulateRiskCommand
from src.domain.entities.risk import PositionSizingInput
from src.domain.exceptions import SymbolNotWhitelistedError
from src.domain.ports.gateways import IExchangeGateway
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    IInstrumentLeverageBracketRepository,
    IInstrumentRepository,
    IRiskProfileRepository,
)
from src.domain.services.risk_calculator import RiskCalculatorDomainService
from src.domain.value_objects.symbol import Symbol

logger = logging.getLogger(__name__)


class SimulateRiskUseCase:
    """Calculates position sizing simulation without committing any trade or orders."""

    def __init__(
        self,
        instrument_repo: IInstrumentRepository,
        risk_profile_repo: IRiskProfileRepository,
        daily_risk_repo: IDailyRiskRepository,
        bracket_repo: Optional[IInstrumentLeverageBracketRepository] = None,
        exchange_gateway: Optional[IExchangeGateway] = None,
        risk_calculator: Optional[RiskCalculatorDomainService] = None,
    ) -> None:
        self.instrument_repo = instrument_repo
        self.risk_profile_repo = risk_profile_repo
        self.daily_risk_repo = daily_risk_repo
        self.bracket_repo = bracket_repo
        self.exchange_gateway = exchange_gateway
        self.risk_calc = risk_calculator or RiskCalculatorDomainService()

    async def execute(self, cmd: SimulateRiskCommand) -> Dict[str, Any]:
        """Perform simulation calculation."""
        clean_symbol = Symbol.normalize(cmd.symbol)
        instrument = await self.instrument_repo.get_by_symbol(clean_symbol)
        if not instrument:
            raise SymbolNotWhitelistedError(f"Symbol '{clean_symbol}' not found in instruments.")

        # Determine balance
        balance = cmd.custom_balance
        if balance is None or balance <= Decimal("0"):
            if self.exchange_gateway:
                try:
                    bal_data = await self.exchange_gateway.fetch_balance()
                    raw_bal = bal_data.get("free_margin") or bal_data.get("total_wallet_balance")
                    if raw_bal:
                        balance = Decimal(str(raw_bal))
                except Exception as exc:
                    logger.warning("Failed to fetch balance for simulation: %s", exc)
            if balance is None or balance <= Decimal("0"):
                balance = Decimal("10000.0")

        profile = await self.risk_profile_repo.get_or_create_default_profile()
        risk_pct = cmd.risk_percent or (profile.risk_percent if profile else Decimal("2.0"))

        brackets = None
        if self.bracket_repo and instrument:
            try:
                brackets = await self.bracket_repo.get_brackets_by_instrument(instrument.id)
            except Exception:
                pass
        if not brackets and instrument:
            brackets = getattr(instrument, "leverage_brackets", None)

        risk_input = PositionSizingInput(
            wallet_balance=balance,
            entry_price=cmd.entry_price,
            sl_price=cmd.sl_price,
            side=cmd.side,
            tp_targets=cmd.tp_targets,
            requested_leverage=cmd.leverage,
            risk_percent=risk_pct,
            tick_size=getattr(instrument, "tick_size", Decimal("0.1")) or Decimal("0.1"),
            step_size=getattr(instrument, "step_size", Decimal("0.001")) or Decimal("0.001"),
            min_notional=getattr(instrument, "min_notional", Decimal("5.0")) or Decimal("5.0"),
            price_precision=getattr(instrument, "price_precision", 2) or 2,
            qty_precision=getattr(instrument, "qty_precision", 3) or 3,
            brackets=brackets,
            strict=False,
        )


        calc_result = self.risk_calc.calculate_position_size(risk_input)

        stop_dist = float(calc_result.stop_distance) if hasattr(calc_result, "stop_distance") else abs(float(cmd.entry_price - cmd.sl_price))
        pos_size = float(calc_result.position_size)
        risk_amt = float(calc_result.risk_amount)
        req_margin = float(calc_result.margin_required)
        eff_lev = calc_result.leverage

        # Accurate side-aware liquidation price
        mmr = Decimal("0.015")
        if brackets:
            notional = calc_result.position_size * cmd.entry_price
            for b in sorted(brackets, key=lambda x: getattr(x, "bracket", 1)):
                n_floor = Decimal(str(getattr(b, "notional_floor", 0)))
                n_cap = Decimal(str(getattr(b, "notional_cap", 0)))
                if n_floor <= notional <= n_cap:
                    mmr = Decimal(str(getattr(b, "maint_margin_ratio", "0.015")))
                    break

        eff_lev_dec = Decimal(str(eff_lev))
        if cmd.side.upper() == "BUY":
            liq_calc = cmd.entry_price * (Decimal("1.0") - (Decimal("1.0") / eff_lev_dec) + mmr)
            liq_safe = liq_calc < cmd.sl_price
        else:
            liq_calc = cmd.entry_price * (Decimal("1.0") + (Decimal("1.0") / eff_lev_dec) - mmr)
            liq_safe = liq_calc > cmd.sl_price

        if liq_calc < Decimal("0"):
            liq_calc = Decimal("0")
        liq_price = float(liq_calc)

        projected_loss = round(pos_size * stop_dist, 2)
        margin_safe = req_margin <= float(balance)
        min_not = float(getattr(instrument, "min_notional", Decimal("5.0")) or Decimal("5.0"))
        notional_safe = (pos_size * float(cmd.entry_price)) >= min_not
        is_safe = bool(calc_result.is_valid and liq_safe and margin_safe and notional_safe and pos_size > 0)


        return {
            "symbol": clean_symbol,
            "side": cmd.side.upper(),
            "wallet_balance": float(balance),
            "position_size": pos_size,
            "calculated_position_size": pos_size,
            "leverage": eff_lev,
            "effective_leverage": eff_lev,
            "margin_required": req_margin,
            "required_margin_usdt": req_margin,
            "notional_value": float(calc_result.notional_value),
            "risk_amount": risk_amt,
            "max_allowed_loss_usdt": risk_amt,
            "risk_percent": float(calc_result.risk_percent),
            "stop_distance_usdt": stop_dist,
            "projected_loss_at_sl_usdt": projected_loss,
            "estimated_liquidation_price": liq_price,
            "is_safe": is_safe,
            "tp_allocations": [
                {
                    "tp_number": tp.tp_number,
                    "target_price": float(tp.target_price),
                    "percentage": float(tp.percentage),
                    "quantity": float(tp.quantity),
                }
                for tp in calc_result.tp_allocations
            ],
            "risk_reward_ratios": [float(r) for r in calc_result.risk_reward_ratios],
            "is_valid": calc_result.is_valid,
            "warning": calc_result.warning,
            "is_leverage_downscaled": calc_result.is_leverage_downscaled,
            "leverage_adjustment_reason": calc_result.leverage_adjustment_reason,
        }

