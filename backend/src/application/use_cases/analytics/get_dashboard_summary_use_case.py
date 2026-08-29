"""Use case for computing dashboard summary KPIs, risk budget consumption, and win rates."""

from datetime import datetime, time, timezone
from src.domain.ports.repositories import (
    IDailyRiskRepository,
    ITradeSummaryRepository,
    ITradeRepository,
)
from src.presentation.api.schemas.analytics import AnalyticsSummaryDTO


class GetDashboardSummaryUseCase:
    """Use case to compute high-level performance KPIs and real-time risk budget utilization."""

    def __init__(
        self,
        daily_risk_repo: IDailyRiskRepository,
        trade_summary_repo: ITradeSummaryRepository,
        trade_repo: ITradeRepository,
    ) -> None:
        self.daily_risk_repo = daily_risk_repo
        self.trade_summary_repo = trade_summary_repo
        self.trade_repo = trade_repo

    async def execute(self, account_id: int = 1) -> AnalyticsSummaryDTO:
        """Compute high-level summary KPIs for the active account."""
        now_utc = datetime.now(timezone.utc)
        today = now_utc.date()
        daily_config = await self.daily_risk_repo.get_by_date(account_id, today)

        if daily_config:
            total_balance = float(daily_config.balance)
            daily_risk_budget = float(daily_config.risk_amount)
            remaining_risk_budget = float(await self.daily_risk_repo.get_remaining_risk_budget(daily_config.id))
            margin_used = float(await self.daily_risk_repo.get_total_margin_used(daily_config.id))
            free_margin = max(0.0, total_balance - margin_used)
        else:
            latest_config = await self.daily_risk_repo.get_latest_snapshot(account_id)
            if latest_config:
                total_balance = float(latest_config.balance)
                daily_risk_budget = float(latest_config.risk_amount)
                remaining_risk_budget = float(await self.daily_risk_repo.get_remaining_risk_budget(latest_config.id))
                margin_used = float(await self.daily_risk_repo.get_total_margin_used(latest_config.id))
                free_margin = max(0.0, total_balance - margin_used)
            else:
                total_balance = 10000.0
                daily_risk_budget = round(total_balance * 0.06, 2)
                remaining_risk_budget = daily_risk_budget
                free_margin = total_balance

        # Today's realized PnL
        start_of_day = datetime.combine(today, time.min, tzinfo=timezone.utc)
        end_of_day = datetime.combine(today, time.max, tzinfo=timezone.utc)
        today_summary = await self.trade_summary_repo.get_performance_summary(
            account_id=account_id,
            start_date=start_of_day,
            end_date=end_of_day,
        )
        daily_realized_pnl = float(today_summary.get("total_net_pnl", 0.0))
        daily_pnl_percent = (
            round((daily_realized_pnl / total_balance) * 100, 2) if total_balance > 0 else 0.0
        )

        # Lifetime Aggregations
        overall_perf = await self.trade_summary_repo.get_performance_summary(account_id=account_id)
        win_rate = float(overall_perf.get("win_rate", 0.0))
        total_trades_count = int(overall_perf.get("total_trades", 0))
        winning_trades_count = int(overall_perf.get("winning_trades", 0))
        losing_trades_count = int(overall_perf.get("losing_trades", 0))
        profit_factor = float(overall_perf.get("profit_factor", 0.0))
        if profit_factor == float("inf"):
            profit_factor = 99.99

        active_trades_count = await self.trade_repo.count_active_trades(account_id)

        return AnalyticsSummaryDTO(
            total_balance_usdt=round(total_balance, 2),
            free_margin_usdt=round(free_margin, 2),
            daily_realized_pnl=round(daily_realized_pnl, 2),
            daily_pnl_percent=daily_pnl_percent,
            daily_risk_budget=round(daily_risk_budget, 2),
            remaining_risk_budget=round(remaining_risk_budget, 2),
            win_rate=win_rate,
            total_trades_count=total_trades_count,
            winning_trades_count=winning_trades_count,
            losing_trades_count=losing_trades_count,
            profit_factor=profit_factor,
            active_trades_count=active_trades_count,
        )
