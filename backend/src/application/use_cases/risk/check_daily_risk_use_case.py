"""Use case for evaluating daily risk limits, current drawdown, and circuit breaker status."""

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict

from src.application.dto.risk_commands import CheckDailyRiskCommand
from src.domain.ports.repositories import IDailyRiskRepository, IRiskProfileRepository, ITradeRepository

logger = logging.getLogger(__name__)


class CheckDailyRiskUseCase:
    """Evaluates daily risk budget consumption, open exposure, and circuit breaker."""

    def __init__(
        self,
        daily_risk_repo: IDailyRiskRepository,
        risk_profile_repo: IRiskProfileRepository,
        trade_repo: ITradeRepository,
    ) -> None:
        self.daily_risk_repo = daily_risk_repo
        self.risk_profile_repo = risk_profile_repo
        self.trade_repo = trade_repo

    async def execute(self, cmd: CheckDailyRiskCommand) -> Dict[str, Any]:
        """Check daily risk status."""
        today = cmd.today_date or datetime.now().date()
        daily_risk = await self.daily_risk_repo.get_by_date(cmd.account_id, today)

        profile = await self.risk_profile_repo.get_or_create_default_profile()
        max_open = getattr(profile, "max_open_trade", None) or getattr(profile, "max_open_positions", None) or 3
        active_trades = await self.trade_repo.get_all_active_trades(account_id=cmd.account_id)

        if not daily_risk:
            return {
                "account_id": cmd.account_id,
                "date": str(today),
                "is_circuit_breaker_active": False,
                "remaining_risk_budget": 0.0,
                "allocated_risk": 0.0,
                "active_trades_count": len(active_trades),
                "max_open_trades_limit": max_open,
                "message": "No daily risk snapshot initialized for today yet.",
            }

        daily_budget = float(daily_risk.daily_risk_amount) if (hasattr(daily_risk, "daily_risk_amount") and daily_risk.daily_risk_amount and daily_risk.daily_risk_amount > Decimal("0")) else float(daily_risk.risk_amount)
        per_trade_risk = float(daily_risk.risk_amount) if hasattr(daily_risk, "risk_amount") else 0.0
        remaining_budget = await self.daily_risk_repo.get_remaining_risk_budget(daily_risk.id)
        is_breaker_active = remaining_budget <= Decimal("0") or (Decimal(str(per_trade_risk)) > remaining_budget) or (len(active_trades) >= max_open)

        return {
            "account_id": cmd.account_id,
            "date": str(today),
            "is_circuit_breaker_active": is_breaker_active,
            "starting_balance": float(daily_risk.balance) if hasattr(daily_risk, "balance") else 0.0,
            "daily_risk_amount": daily_budget,
            "per_trade_risk_amount": per_trade_risk,
            "allocated_risk_amount": per_trade_risk,
            "remaining_risk_budget": float(remaining_budget),
            "active_trades_count": len(active_trades),
            "max_open_trades_limit": max_open,
            "reason": "DAILY_RISK_LIMIT_REACHED" if remaining_budget <= Decimal("0") else ("PER_TRADE_RISK_EXCEEDS_BUDGET" if Decimal(str(per_trade_risk)) > remaining_budget else ("MAX_OPEN_TRADES_REACHED" if len(active_trades) >= max_open else "OK")),
        }
