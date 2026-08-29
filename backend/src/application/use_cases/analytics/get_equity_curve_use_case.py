"""Use case for computing historical equity curve data points for charting."""

from datetime import datetime, time, date, timedelta, timezone
from typing import List

from src.domain.ports.repositories import IDailyRiskRepository, ITradeSummaryRepository
from src.presentation.api.schemas.analytics import EquityPointDTO


class GetEquityCurveUseCase:
    """Use case to compute historical equity curve points for charting without N+1 query loop."""

    def __init__(
        self,
        daily_risk_repo: IDailyRiskRepository,
        trade_summary_repo: ITradeSummaryRepository,
    ) -> None:
        self.daily_risk_repo = daily_risk_repo
        self.trade_summary_repo = trade_summary_repo

    async def execute(self, account_id: int = 1, timeframe: str = "30d") -> List[EquityPointDTO]:
        """Compute historical equity curve points for charting."""
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
