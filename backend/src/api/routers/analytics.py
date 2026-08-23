"""FastAPI router for high-level analytics, dashboard summary, and equity growth metrics."""

from datetime import datetime, time, date, timedelta, timezone
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import get_current_user, get_db_session, get_cache
from src.database.models.users import User
from src.schemas.analytics import AnalyticsSummaryDTO, EquityPointDTO
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.trade_repository import TradeRepository
from src.utils.cache import AsyncInMemoryCache

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/summary", response_model=AnalyticsSummaryDTO, summary="Get high-level dashboard metrics")
async def get_analytics_summary(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> AnalyticsSummaryDTO:
    """Retrieve summarized performance indicators, real-time balance, win rate, profit factor,

    and remaining daily risk budget for the dashboard.
    Cached for 10 seconds to avoid repeating heavy aggregate database queries.
    """
    cache_key = f"analytics:summary:{account_id}"
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return AnalyticsSummaryDTO(**cached_data)

    daily_risk_repo = DailyRiskRepository(session)
    trade_summary_repo = TradeSummaryRepository(session)
    trade_repo = TradeRepository(session)

    # 1. Fetch Daily Risk Snapshot & Balance
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    daily_config = await daily_risk_repo.get_by_date(account_id, today)

    if daily_config:
        total_balance = float(daily_config.balance)
        daily_risk_budget = float(daily_config.risk_amount)
        remaining_risk_budget = float(await daily_risk_repo.get_remaining_risk_budget(daily_config.id))
        margin_used = float(await daily_risk_repo.get_total_margin_used(daily_config.id))
        free_margin = max(0.0, total_balance - margin_used)
    else:
        latest_config = await daily_risk_repo.get_latest_snapshot(account_id)
        if latest_config:
            total_balance = float(latest_config.balance)
            daily_risk_budget = float(latest_config.risk_amount)
            remaining_risk_budget = float(await daily_risk_repo.get_remaining_risk_budget(latest_config.id))
            margin_used = float(await daily_risk_repo.get_total_margin_used(latest_config.id))
            free_margin = max(0.0, total_balance - margin_used)
        else:
            total_balance = 10000.0
            daily_risk_budget = round(total_balance * 0.06, 2)
            remaining_risk_budget = daily_risk_budget
            free_margin = total_balance

    # 2. Today's Realized PnL
    start_of_day = datetime.combine(today, time.min, tzinfo=timezone.utc)
    end_of_day = datetime.combine(today, time.max, tzinfo=timezone.utc)
    today_summary = await trade_summary_repo.get_performance_summary(
        account_id=account_id,
        start_date=start_of_day,
        end_date=end_of_day,
    )
    daily_realized_pnl = float(today_summary.get("total_net_pnl", 0.0))
    daily_pnl_percent = (
        round((daily_realized_pnl / total_balance) * 100, 2) if total_balance > 0 else 0.0
    )

    # 3. Overall Lifetime Performance Aggregation
    overall_perf = await trade_summary_repo.get_performance_summary(account_id=account_id)
    win_rate = float(overall_perf.get("win_rate", 0.0))
    total_trades_count = int(overall_perf.get("total_trades", 0))
    winning_trades_count = int(overall_perf.get("winning_trades", 0))
    losing_trades_count = int(overall_perf.get("losing_trades", 0))
    profit_factor = float(overall_perf.get("profit_factor", 0.0))
    if profit_factor == float("inf"):
        profit_factor = 99.99  # Cap infinity for clean JSON serialization

    # 4. Active Trades Count
    active_trades_count = await trade_repo.count_active_trades(account_id)

    response_dto = AnalyticsSummaryDTO(
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

    # Save to Cache with 10s TTL
    await cache.set(cache_key, response_dto.model_dump(), ttl_seconds=10)

    return response_dto


@router.get("/equity-curve", response_model=List[EquityPointDTO], summary="Get equity growth curve chart data")
async def get_equity_curve(
    account_id: int = Query(default=1, ge=1, description="Trading Account ID"),
    timeframe: str = Query(default="30d", pattern="^(7d|30d|90d|all)$", description="Chart timeframe filter"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
    cache: AsyncInMemoryCache = Depends(get_cache),
) -> List[EquityPointDTO]:
    """Retrieve historical daily equity balance snapshots and realized PnL points for charting.

    Cached for 60 seconds per timeframe filter.
    """
    cache_key = f"analytics:equity:{account_id}:{timeframe}"
    cached_data = await cache.get(cache_key)
    if cached_data is not None:
        return [EquityPointDTO(**item) for item in cached_data]

    daily_risk_repo = DailyRiskRepository(session)
    trade_summary_repo = TradeSummaryRepository(session)

    today = datetime.now(timezone.utc).date()
    if timeframe == "7d":
        start_date = today - timedelta(days=7)
    elif timeframe == "30d":
        start_date = today - timedelta(days=30)
    elif timeframe == "90d":
        start_date = today - timedelta(days=90)
    else:  # "all"
        start_date = date(2020, 1, 1)

    history = await daily_risk_repo.get_daily_history(account_id, start_date, today)

    points: List[EquityPointDTO] = []
    for snapshot in history:
        point_dt = datetime.combine(snapshot.date, time.min, tzinfo=timezone.utc)
        start_snap = datetime.combine(snapshot.date, time.min, tzinfo=timezone.utc)
        end_snap = datetime.combine(snapshot.date, time.max, tzinfo=timezone.utc)
        snap_perf = await trade_summary_repo.get_performance_summary(
            account_id=account_id,
            start_date=start_snap,
            end_date=end_snap,
        )
        pnl_day = float(snap_perf.get("total_net_pnl", 0.0))
        points.append(
            EquityPointDTO(
                timestamp=point_dt,
                balance=float(snapshot.balance),
                pnl=pnl_day,
            )
        )

    # If no historical snapshots found, return baseline point
    if not points:
        latest_config = await daily_risk_repo.get_latest_snapshot(account_id)
        current_balance = float(latest_config.balance) if latest_config else 10000.0
        now_dt = datetime.now(timezone.utc)
        points.append(
            EquityPointDTO(
                timestamp=now_dt,
                balance=current_balance,
                pnl=0.0,
            )
        )

    # Save to Cache with 60s TTL
    await cache.set(cache_key, [p.model_dump(mode="json") for p in points], ttl_seconds=60)

    return points
