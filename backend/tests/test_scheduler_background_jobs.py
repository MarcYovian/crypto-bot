"""Comprehensive unit and integration tests for SchedulerService background jobs."""

import pytest
import pytest_asyncio
from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Strategy, RiskProfile, Trade, Order, BotLog
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.trading_credential_repository import TradingCredentialRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.bot_log_repository import BotLogRepository
from src.infrastructure.persistence.repositories.bot_setting_repository import BotSettingRepository
from src.infrastructure.scheduler.jobs import SchedulerJobs as SchedulerService
from src.application.use_cases.instruments.sync_instruments_use_case import SyncInstrumentsUseCase as InstrumentService
from src.application.use_cases.trades.sync_positions_use_case import SyncPositionsUseCase as PositionManager
from src.domain.ports.gateways import IExchangeGateway, INotificationGateway





TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def sched_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(
        exchange_id=exchange.id, name="Binance TESTNET Account", account_type="FUTURES", environment="TESTNET", is_active=True
    )
    async_session.add(account)
    await async_session.flush()

    strategy = Strategy(name="AI Trend Strategy", version="1.0.0", is_active=True)
    async_session.add(strategy)
    await async_session.flush()

    inst = Instrument(
        exchange_id=exchange.id, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
        min_qty=Decimal("0.001"), step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), is_active=True
    )
    async_session.add(inst)
    await async_session.flush()

    profile = RiskProfile(
        name="Conservative 2%", risk_percent=Decimal("2.0"), max_daily_loss=Decimal("6.0"), max_open_trade=3, is_active=True
    )
    async_session.add(profile)
    await async_session.flush()

    # Old log for purge test
    old_date = datetime.now() - timedelta(days=40)
    old_log = BotLog(level="INFO", module="OldService", message="Ancient log message", created_at=old_date)
    async_session.add(old_log)

    await async_session.commit()
    await async_session.refresh(account)
    await async_session.refresh(inst)
    await async_session.refresh(strategy)

    def create_scheduler(exchange_mock=None, binance_mock=None, tg_mock=None, pos_mgr=None, inst_svc=None):
        mock_gw = exchange_mock or binance_mock
        return SchedulerService(
            daily_risk_repo=DailyRiskRepository(async_session),
            trading_account_repo=TradingAccountRepository(async_session),
            risk_profile_repo=RiskProfileRepository(async_session),
            trade_repo=TradeRepository(async_session),
            order_repo=OrderRepository(async_session),
            instrument_repo=InstrumentRepository(async_session),
            trade_summary_repo=TradeSummaryRepository(async_session),
            trade_event_repo=TradeEventRepository(async_session),
            bot_log_repo=BotLogRepository(async_session),
            bot_setting_repo=BotSettingRepository(async_session),
            position_manager=pos_mgr,
            instrument_service=inst_svc,
            exchange_gateway=mock_gw,
            notification_gateway=tg_mock or AsyncMock(spec=INotificationGateway),
        )




    return {"exchange": exchange, "account": account, "inst": inst, "strategy": strategy, "create_scheduler": create_scheduler}


@pytest.mark.asyncio
async def test_run_daily_risk_snapshot_job(async_session: AsyncSession, sched_env: dict):
    """Test job 1: calculating 2% daily loss budget and saving midnight snapshot."""
    env = sched_env
    mock_gateway = AsyncMock(spec=IExchangeGateway)
    mock_gateway.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0")})
    mock_tg = AsyncMock(spec=INotificationGateway)


    scheduler = env["create_scheduler"](exchange_mock=mock_gateway, tg_mock=mock_tg)

    target_d = date(2026, 8, 24)
    snapshot = await scheduler.run_daily_risk_snapshot_job(account_id=env["account"].id, snapshot_date=target_d)

    assert snapshot is not None
    assert snapshot.balance == Decimal("1000.0")
    # 2% of $1000 = $20
    assert snapshot.risk_amount == Decimal("20.0")
    assert mock_tg.send_message.called


@pytest.mark.asyncio
async def test_run_cleanup_orphan_orders_job(async_session: AsyncSession, sched_env: dict):
    """Test job 2: finding and cancelling WAITING_ENTRY trades older than threshold."""
    env = sched_env
    trade_repo = TradeRepository(async_session)

    # Create stale trade
    stale_trade = Trade(
        account_id=env["account"].id,
        instrument_id=env["inst"].id,
        strategy_id=env["strategy"].id,
        status="WAITING_ENTRY",
        side="BUY",
        entry_price=Decimal("50000.0"),
        position_size=Decimal("0.01"),
        remaining_qty=Decimal("0.01"),
        sl_price=Decimal("48000.0"),
        tp1_price=Decimal("54000.0"),
        leverage=10,
        margin_mode="ISOLATED",
        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5),
    )
    async_session.add(stale_trade)
    await async_session.flush()

    order = Order(
        trade_id=stale_trade.id,
        purpose="ENTRY",
        order_type="LIMIT",
        side="BUY",
        qty=Decimal("0.01"),
        price=Decimal("50000.0"),
        status="NEW",
    )
    async_session.add(order)
    await async_session.commit()

    mock_gateway = AsyncMock(spec=IExchangeGateway)
    mock_gateway.cancel_all_orders = AsyncMock()

    scheduler = env["create_scheduler"](exchange_mock=mock_gateway)
    cleaned = await scheduler.run_cleanup_orphan_orders_job(account_id=env["account"].id, max_age_hours=4)

    assert cleaned == 1
    await async_session.refresh(stale_trade)
    assert stale_trade.status == "CANCELLED"
    assert mock_gateway.cancel_all_orders.called


@pytest.mark.asyncio
async def test_run_failsafe_sync_job(async_session: AsyncSession, sched_env: dict):
    """Test job 3: reconciling DB active trades against live Exchange open positions."""
    env = sched_env

    # Active DB trade
    active_trade = Trade(
        account_id=env["account"].id,
        instrument_id=env["inst"].id,
        strategy_id=env["strategy"].id,
        status="OPEN",
        side="BUY",
        entry_price=Decimal("50000.0"),
        position_size=Decimal("0.01"),
        remaining_qty=Decimal("0.01"),
        sl_price=Decimal("48000.0"),
        tp1_price=Decimal("54000.0"),
        leverage=10,
        margin_mode="ISOLATED",
    )
    async_session.add(active_trade)
    await async_session.commit()

    # Exchange has NO open positions for BTCUSDT (position closed externally)
    mock_gateway = AsyncMock(spec=IExchangeGateway)
    mock_gateway.fetch_positions = AsyncMock(return_value=[])

    mock_pos_mgr = AsyncMock(spec=PositionManager)
    mock_pos_mgr.finalize_trade_closure = AsyncMock()

    scheduler = env["create_scheduler"](exchange_mock=mock_gateway, pos_mgr=mock_pos_mgr)
    sync_res = await scheduler.run_failsafe_sync_job(account_id=env["account"].id)

    assert sync_res["total_checked"] == 1
    assert sync_res["desynced_closed"] == 1
    mock_pos_mgr.finalize_trade_closure.assert_called_once_with(trade_id=active_trade.id, close_reason="FAILSAFE_SYNC")



@pytest.mark.asyncio
async def test_run_sync_instruments_and_purge_logs(async_session: AsyncSession, sched_env: dict):
    """Test job 4 (sync metadata) and job 5 (purge old logs)."""
    env = sched_env
    mock_inst_svc = AsyncMock(spec=InstrumentService)
    mock_inst_svc.sync_all_instruments = AsyncMock(return_value=45)

    scheduler = env["create_scheduler"](inst_svc=mock_inst_svc)

    # Job 4: Sync instruments
    synced_count = await scheduler.run_sync_instruments_metadata_job(exchange_id=env["exchange"].id)
    assert synced_count == 45
    mock_inst_svc.sync_all_instruments.assert_called_once_with(exchange_id=env["exchange"].id)

    # Job 5: Purge logs
    purged_count = await scheduler.run_purge_old_logs_job(days=30)
    assert purged_count == 1


@pytest.mark.asyncio
async def test_run_daily_report_and_heartbeat(async_session: AsyncSession, sched_env: dict):
    """Test job 6 (daily performance report) and job 7 (heartbeat health check)."""
    env = sched_env
    mock_tg = AsyncMock(spec=INotificationGateway)
    mock_gateway = AsyncMock(spec=IExchangeGateway)
    mock_gateway.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0")})

    scheduler = env["create_scheduler"](exchange_mock=mock_gateway, tg_mock=mock_tg)


    # Job 6: Daily performance report
    perf_res = await scheduler.run_daily_performance_report_job(account_id=env["account"].id)
    assert "total_trades" in perf_res
    assert mock_tg.send_message.called

    # Job 7: Heartbeat
    hb_res = await scheduler.run_heartbeat_health_check_job()
    assert hb_res["is_healthy"] is True
    assert hb_res["db_healthy"] is True
    assert hb_res["exchange_healthy"] is True

