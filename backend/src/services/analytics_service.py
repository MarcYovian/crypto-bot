"""Analytics business service for dashboard indicators and equity performance."""

from datetime import datetime, time, date, timedelta, timezone
from decimal import Decimal
from typing import List, Optional

from src.schemas.analytics import AnalyticsSummaryDTO, EquityPointDTO
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.trade_repository import TradeRepository


class AnalyticsService:
    """Service providing aggregate analytics, real-time risk budget consumption, and equity curves."""

    def __init__(
        self,
        daily_risk_repo: DailyRiskRepository,
        trade_summary_repo: TradeSummaryRepository,
        trade_repo: TradeRepository,
    ) -> None:
        self.daily_risk_repo = daily_risk_repo
        self.trade_summary_repo = trade_summary_repo
        self.trade_repo = trade_repo

    async def get_dashboard_summary(self, account_id: int = 1) -> AnalyticsSummaryDTO:
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

    async def get_equity_curve(self, account_id: int = 1, timeframe: str = "30d") -> List[EquityPointDTO]:
        """Compute historical equity curve points for charting without N+1 query loop."""
        today = datetime.now(timezone.utc).date()
        if timeframe == "7d":
            start_date = today - timedelta(days=7)
        elif timeframe == "30d":
            start_date = today - timedelta(days=30)
        elif timeframe == "90d":
            start_date = today - timedelta(days=90)
        else:  # "all"
            start_date = date(2020, 1, 1)

        history = await self.daily_risk_repo.get_daily_history(account_id, start_date, today)

        start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(today, time.max, tzinfo=timezone.utc)
        pnl_map = await self.trade_summary_repo.get_daily_pnl_map(
            account_id=account_id,
            start_date=start_dt,
            end_date=end_dt,
        )

        points: List[EquityPointDTO] = []
        for snapshot in history:
            point_dt = datetime.combine(snapshot.date, time.min, tzinfo=timezone.utc)
            pnl_day = pnl_map.get(snapshot.date, 0.0)
            points.append(
                EquityPointDTO(
                    timestamp=point_dt,
                    balance=float(snapshot.balance),
                    pnl=pnl_day,
                )
            )

        if not points:
            latest_config = await self.daily_risk_repo.get_latest_snapshot(account_id)
            current_balance = float(latest_config.balance) if latest_config else 10000.0
            now_dt = datetime.now(timezone.utc)
            points.append(
                EquityPointDTO(
                    timestamp=now_dt,
                    balance=current_balance,
                    pnl=0.0,
                )
            )

        return points
