"""Unit tests for SchedulerService and TelegramService."""

from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Watchlist, Strategy, SignalProvider, RiskProfile, Trade, Order, Execution, TradeSummary, DailyRiskConfig, BotLog, BotSetting
from src.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate, WatchlistCreate, StrategyCreate, SignalProviderCreate, RiskProfileCreate
from src.schemas.trade import TradeCreate
from src.schemas.order import OrderCreate
from src.schemas.event_summary import TradeSummaryCreate
from src.schemas.system import BotLogCreate
from src.domain.entities.signal import ParsedSignalDTO
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.trading_credential_repository import TradingCredentialRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.repository.strategy_repository import StrategyRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.signal_repository import SignalRepository
from src.repository.trade_repository import TradeRepository
from src.repository.trade_risk_repository import TradeRiskRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.bot_log_repository import BotLogRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.services.signal_parser import SignalParserService
from src.services.risk_calculator import RiskCalculatorService
from src.services.trade_service import TradeService
from src.services.position_manager import PositionManager
from src.services.scheduler_service import SchedulerService
from src.services.telegram_service import TelegramService
from src.services.instrument_service import InstrumentService
from src.clients.binance_client import BinanceRestClient

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    """Create a fresh in-memory SQLite database session for testing."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def setup_env(async_session: AsyncSession):
    """Seed base setup."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    strat_repo = StrategyRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    risk_repo = RiskProfileRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(exchange_id=exchange.id, name="Main", environment="MAINNET", is_active=True))
    instrument = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=Decimal("0.1"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=1,
        qty_precision=3,
        is_active=True,
    ))
    watchlist = await watch_repo.create(WatchlistCreate(account_id=account.id, instrument_id=instrument.id, is_enabled=True, max_leverage=20))
    strategy = await strat_repo.create(StrategyCreate(name="Default Strategy", is_active=True))
    provider = await prov_repo.create(SignalProviderCreate(name="VIP Channel", type="TELEGRAM_CHANNEL", is_active=True))
    risk_profile = await risk_repo.create(RiskProfileCreate(name="Conservative 2%", is_active=True))

    return {
        "exchange": exchange,
        "account": account,
        "instrument": instrument,
        "watchlist": watchlist,
        "strategy": strategy,
        "provider": provider,
        "risk_profile": risk_profile,
    }


# =============================================================================
# SCHEDULER SERVICE TESTS (7 JOBS)
# =============================================================================

@pytest.mark.asyncio
async def test_scheduler_daily_risk_snapshot_job_success(async_session: AsyncSession, setup_env: dict):
    """Test 00:00 WIB daily risk snapshot capturing balance and calculating 2% risk."""
    acc = setup_env["account"]

    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("20000.0")})
    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock()

    scheduler = SchedulerService(
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
        binance_client=mock_binance,
        telegram_client=mock_tg,
    )

    snapshot = await scheduler.run_daily_risk_snapshot_job(account_id=acc.id)
    assert snapshot is not None
    assert snapshot.balance == Decimal("20000.0")
    assert snapshot.risk_amount == Decimal("400.0")  # 2% of 20,000
    mock_tg.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_cleanup_orphan_orders_job(async_session: AsyncSession, setup_env: dict):
    """Test cancelling orphan WAITING_ENTRY orders older than 4 hours."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    order_repo = OrderRepository(async_session)

    # Create stale trade
    from datetime import timezone
    stale_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=5)
    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))
    trade.created_at = stale_time
    await async_session.commit()

    await order_repo.create(OrderCreate(
        trade_id=trade.id,
        side="BUY",
        order_type="LIMIT",
        purpose="ENTRY",
        price=Decimal("60000.0"),
        qty=Decimal("0.100"),
        status="NEW",
    ))

    mock_binance = MagicMock()
    mock_binance.cancel_all_orders = AsyncMock()

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=trade_repo,
        order_repo=order_repo,
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        binance_client=mock_binance,
    )

    cleaned = await scheduler.run_cleanup_orphan_orders_job(account_id=acc.id, max_age_hours=4)
    assert cleaned == 1

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CANCELLED"


@pytest.mark.asyncio
async def test_scheduler_failsafe_sync_closes_desynced_trade(async_session: AsyncSession, setup_env: dict):
    """Test failsafe reconciliation closing DB trade when Binance position is 0."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    mock_binance = MagicMock()
    # Return empty positions list
    mock_binance.fetch_positions = AsyncMock(return_value=[])

    pos_manager = PositionManager(
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        position_manager=pos_manager,
        binance_client=mock_binance,
    )

    res = await scheduler.run_failsafe_sync_job(account_id=acc.id)
    assert res["desynced_closed"] == 1

    updated_trade = await trade_repo.get(trade.id)
    assert updated_trade.status == "CLOSED"


@pytest.mark.asyncio
async def test_scheduler_sync_instruments_metadata_job(async_session: AsyncSession, setup_env: dict):
    """Test periodic sync of symbol tick/step sizes from Binance."""
    mock_binance = MagicMock()
    mock_binance.fetch_instruments_metadata = AsyncMock(return_value=[
        {
            "symbol": "ETHUSDT",
            "base_asset": "ETH",
            "quote_asset": "USDT",
            "tick_size": "0.01",
            "step_size": "0.001",
            "min_qty": "0.001",
            "min_notional": "5.0",
            "price_precision": 2,
            "qty_precision": 3,
        }
    ])

    inst_repo = InstrumentRepository(async_session)
    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=inst_repo,
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        binance_client=mock_binance,
    )

    count = await scheduler.run_sync_instruments_metadata_job()
    assert count == 1
    eth = await inst_repo.get_by_symbol("ETHUSDT")
    assert eth is not None
    assert eth.tick_size == Decimal("0.01")


@pytest.mark.asyncio
async def test_scheduler_purge_old_logs_job(async_session: AsyncSession, setup_env: dict):
    """Test purging logs older than retention days."""
    log_repo = BotLogRepository(async_session)
    old_time = datetime.now() - timedelta(days=40)
    log = await log_repo.create(BotLogCreate(level="INFO", component="Test", message="Old log"))
    log.created_at = old_time
    await async_session.commit()

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=log_repo,
        bot_setting_repo=BotSettingRepository(async_session),
    )

    purged = await scheduler.run_purge_old_logs_job(days=30)
    assert purged == 1


@pytest.mark.asyncio
async def test_scheduler_daily_performance_report_job(async_session: AsyncSession, setup_env: dict):
    """Test daily performance recap reporting to Telegram."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="CLOSED",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.0"),
    ))

    await sum_repo.create(TradeSummaryCreate(
        trade_id=trade.id,
        gross_pnl=Decimal("150.0"),
        net_pnl=Decimal("148.0"),
        commission=Decimal("2.0"),
        funding=Decimal("0.0"),
        roi=Decimal("74.0"),
        rr=Decimal("1.5"),
        result="WIN",
        duration_seconds=3600,
        close_reason="TP2_HIT",
        closed_at=datetime.now(),
    ))

    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock()

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=TradingAccountRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        trade_summary_repo=sum_repo,
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        telegram_client=mock_tg,
    )

    recap = await scheduler.run_daily_performance_report_job(account_id=acc.id)
    assert recap["total_trades"] == 1
    assert recap["wins"] == 1
    assert recap["net_pnl"] == 148.0
    mock_tg.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_scheduler_heartbeat_health_check_job(async_session: AsyncSession, setup_env: dict):
    """Test hourly heartbeat health audit."""
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={})

    scheduler = SchedulerService(
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
        binance_client=mock_binance,
    )

    status = await scheduler.run_heartbeat_health_check_job()
    assert status["is_healthy"] is True
    assert status["db_healthy"] is True
    assert status["binance_healthy"] is True


# =============================================================================
# TELEGRAM SERVICE TESTS (12 COMMANDS & INTERACTIVE FLOWS)
# =============================================================================

@pytest.mark.asyncio
async def test_telegram_command_balance_response(async_session: AsyncSession, setup_env: dict):
    """Test /balance command returning formatted balance text."""
    mock_binance = MagicMock()
    mock_binance.fetch_balance = AsyncMock(return_value={
        "total_wallet_balance": Decimal("15000.0"),
        "free_margin": Decimal("12000.0"),
        "unrealized_pnl": Decimal("250.0"),
    })

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        binance_client=mock_binance,
    )

    resp = await tg_service.handle_command("/balance")
    assert "$15,000.00 USDT" in resp
    assert "$12,000.00 USDT" in resp
    assert "+$250.00 USDT" in resp


@pytest.mark.asyncio
async def test_telegram_command_status_active_positions(async_session: AsyncSession, setup_env: dict):
    """Test /status listing active trade positions."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/status")
    assert "BTCUSDT" in resp
    assert "LONG 20x" in resp
    assert "$60000" in resp


@pytest.mark.asyncio
async def test_telegram_command_pending_orders(async_session: AsyncSession, setup_env: dict):
    """Test /pending listing pending entry limit orders."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        entry_price=Decimal("59000.0"),
        sl_price=Decimal("57000.0"),
        leverage=20,
        position_size=Decimal("0.100"),
        remaining_qty=Decimal("0.100"),
    ))

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/pending")
    assert "BTCUSDT" in resp
    assert "$59000" in resp


@pytest.mark.asyncio
async def test_telegram_command_summary_performance(async_session: AsyncSession, setup_env: dict):
    """Test /summary returning trading statistics."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="CLOSED",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.0"),
    ))

    await sum_repo.create(TradeSummaryCreate(
        trade_id=trade.id,
        gross_pnl=Decimal("200.0"),
        net_pnl=Decimal("195.0"),
        commission=Decimal("5.0"),
        funding=Decimal("0.0"),
        roi=Decimal("97.5"),
        rr=Decimal("2.0"),
        result="WIN",
        duration_seconds=7200,
        close_reason="TP3_HIT",
        closed_at=datetime.now(),
    ))

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=sum_repo,
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/summary")
    assert "Win Rate: <b>100.0%</b>" in resp
    assert "195.00 USDT" in resp


@pytest.mark.asyncio
async def test_telegram_command_close_manual_trade(async_session: AsyncSession, setup_env: dict):
    """Test /close <trade_id> closing an open trade."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    mock_trade_service = MagicMock()
    mock_trade_service.close_trade_manually = AsyncMock(return_value=True)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command(f"/close {trade.id}")
    assert f"Berhasil menutup posisi Trade <b>#{trade.id}</b>" in resp
    mock_trade_service.close_trade_manually.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_command_panic_close_all(async_session: AsyncSession, setup_env: dict):
    """Test /panic emergency closure of all open trades."""
    acc = setup_env["account"]
    inst = setup_env["instrument"]
    trade_repo = TradeRepository(async_session)

    await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
    ))

    mock_trade_service = MagicMock()
    mock_trade_service.close_trade_manually = AsyncMock(return_value=True)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=SignalRepository(async_session),
        trade_repo=trade_repo,
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    resp = await tg_service.handle_command("/panic")
    assert "EMERGENCY PANIC CLOSE ALL" in resp
    assert "1/1 posisi" in resp


@pytest.mark.asyncio
async def test_telegram_command_pause_and_resume(async_session: AsyncSession, setup_env: dict):
    """Test /pause and /resume toggling bot execution state."""
    setting_repo = BotSettingRepository(async_session)
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=setting_repo,
    )

    # Pause
    pause_resp = await tg_service.handle_command("/pause")
    assert "PAUSED" in pause_resp
    is_paused = await setting_repo.get_bool("is_trading_paused")
    assert is_paused is True

    # Resume
    resume_resp = await tg_service.handle_command("/resume")
    assert "RESUMED" in resume_resp
    is_paused = await setting_repo.get_bool("is_trading_paused")
    assert is_paused is False


@pytest.mark.asyncio
async def test_telegram_command_watchlist_management(async_session: AsyncSession, setup_env: dict):
    """Test /watchlist commands enabling and disabling pairs."""
    inst = setup_env["instrument"]
    watch_repo = WatchlistRepository(async_session)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=watch_repo,
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    # Disable
    dis_resp = await tg_service.handle_command("/watchlist disable BTCUSDT")
    assert "DINONAKTIFKAN" in dis_resp
    is_active = await watch_repo.is_symbol_enabled("BTCUSDT")
    assert is_active is False

    # Enable
    en_resp = await tg_service.handle_command("/watchlist enable BTCUSDT")
    assert "DIAKTIFKAN" in en_resp
    is_active = await watch_repo.is_symbol_enabled("BTCUSDT")
    assert is_active is True


@pytest.mark.asyncio
async def test_telegram_interactive_signal_approval_callback(async_session: AsyncSession, setup_env: dict):
    """Test approving a signal via inline callback button executing a live trade."""
    inst = setup_env["instrument"]
    signal_repo = SignalRepository(async_session)

    from src.schemas.signal import TradingSignalCreate
    signal = await signal_repo.create(TradingSignalCreate(
        provider_id=1,
        instrument_id=inst.id,
        raw_message="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        side="BUY",
        entry_min=Decimal("60000.0"),
        entry_max=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        tp1_price=Decimal("62000.0"),
        confidence=Decimal("0.9"),
        status="RECEIVED",
        confirmation_status="PENDING",
    ))

    mock_trade_service = MagicMock()
    mock_res = MagicMock()
    mock_res.trade_id = 99
    mock_trade_service.execute_signal = AsyncMock(return_value=mock_res)

    mock_tg = MagicMock()
    mock_tg.edit_message_text = AsyncMock()

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=signal_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        telegram_client=mock_tg,
    )

    cb_res = await tg_service.handle_callback_query(f"APPROVE_{signal.id}", message_id=123)
    assert cb_res["status"] == "APPROVED"
    assert cb_res["trade_id"] == 99

    updated_signal = await signal_repo.get(signal.id)
    assert updated_signal.confirmation_status == "APPROVED"
    assert updated_signal.status == "EXECUTED"
    mock_trade_service.execute_signal.assert_called_once()
    mock_tg.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_interactive_signal_rejection_callback(async_session: AsyncSession, setup_env: dict):
    """Test rejecting a signal via inline button."""
    inst = setup_env["instrument"]
    signal_repo = SignalRepository(async_session)

    from src.schemas.signal import TradingSignalCreate
    signal = await signal_repo.create(TradingSignalCreate(
        provider_id=1,
        instrument_id=inst.id,
        raw_message="BUY BTCUSDT Entry: 60000 SL: 58000 TP: 62000",
        side="BUY",
        entry_min=Decimal("60000.0"),
        entry_max=Decimal("60000.0"),
        sl_price=Decimal("58000.0"),
        tp1_price=Decimal("62000.0"),
        confidence=Decimal("0.9"),
        status="RECEIVED",
        confirmation_status="PENDING",
    ))

    mock_trade_service = MagicMock()
    mock_tg = MagicMock()
    mock_tg.edit_message_text = AsyncMock()

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=mock_trade_service,
        signal_repo=signal_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        telegram_client=mock_tg,
    )

    cb_res = await tg_service.handle_callback_query(f"REJECT_{signal.id}", message_id=123)
    assert cb_res["status"] == "REJECTED"

    updated_signal = await signal_repo.get(signal.id)
    assert updated_signal.confirmation_status == "REJECTED"
    assert updated_signal.status == "REJECTED"
    mock_trade_service.execute_signal.assert_not_called()
    mock_tg.edit_message_text.assert_called_once()


@pytest.mark.asyncio
async def test_telegram_command_account_info(async_session: AsyncSession, setup_env: dict):
    """Test /account displaying active account, environment, and masked API key."""
    acc = setup_env["account"]
    ex = setup_env["exchange"]
    cred_repo = TradingCredentialRepository(async_session)

    from src.database.models.trading_credentials import TradingCredential
    cred = TradingCredential(
        account_id=acc.id,
        key_name="Test API Key",
        encrypted_api_key="apiKeySample123456789",
        encrypted_secret_key="secretKeySample987654321",
        key_version=1,
        is_active=True,
    )
    async_session.add(cred)
    await async_session.commit()

    mock_binance = MagicMock()
    mock_binance.testnet = True
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("10500.0")})

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        trading_credential_repo=cred_repo,
        binance_client=mock_binance,
    )

    resp = await tg_service.handle_command("/account", account_id=acc.id)
    assert "INFORMASI AKUN & KREDENSIAL AKTIF" in resp
    assert "Binance Futures" in resp
    assert "apiK****6789" in resp
    assert "$10,500.00 USDT" in resp


@pytest.mark.asyncio
async def test_telegram_setup_account_wizard_full_flow_success(async_session: AsyncSession, setup_env: dict):
    """Test full interactive credential setup wizard via Telegram with auto-delete and validation handshake."""
    acc = setup_env["account"]
    ex = setup_env["exchange"]
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    cred_repo = TradingCredentialRepository(async_session)

    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock()
    mock_tg.edit_message_text = AsyncMock()
    mock_tg.delete_message = AsyncMock(return_value=True)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        exchange_repo=ex_repo,
        trading_account_repo=acc_repo,
        trading_credential_repo=cred_repo,
        telegram_client=mock_tg,
        binance_client=BinanceRestClient(testnet=True),
    )

    # Step 1: User runs /setup_account
    res_cmd = await tg_service.handle_user_message("/setup_account", chat_id=999)
    assert "WIZARD SETUP AKUN & KREDENSIAL BINANCE" in res_cmd
    mock_tg.send_message.assert_called_once()

    # Step 2: User clicks [ 🧪 Binance Testnet ]
    cb_res = await tg_service.handle_callback_query("WIZ_ENV_TESTNET", message_id=501, chat_id=999)
    assert cb_res["status"] == "WIZARD_STARTED"
    assert cb_res["env"] == "TESTNET"

    # Step 3: User sends API Key
    res_step1 = await tg_service.handle_user_message("my_valid_binance_api_key_12345", chat_id=999)
    assert "API Key Diterima!" in res_step1
    assert "Binance SECRET Key" in res_step1

    # Step 4: User sends Secret Key (Mocking handshake inside test)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            BinanceRestClient,
            "fetch_balance",
            AsyncMock(return_value={"total_wallet_balance": Decimal("15000.0"), "free_margin": Decimal("15000.0")}),
        )
        mp.setattr(BinanceRestClient, "close", AsyncMock())

        res_step2 = await tg_service.handle_user_message(
            "my_valid_binance_secret_key_98765",
            chat_id=999,
            message_id=888,
            account_id=acc.id,
        )

        # Assert secret message auto-delete was triggered!
        mock_tg.delete_message.assert_called_once_with(chat_id=999, message_id=888)

        # Assert success response
        assert "AKUN BINANCE BERHASIL DIHUBUNGKAN!" in res_step2
        assert "TESTNET" in res_step2
        assert "$15,000.00 USDT" in res_step2
        assert "my_v****2345" in res_step2

        # Assert credential was persisted to database
        active_cred = await cred_repo.get_active_credential(acc.id)
        assert active_cred is not None
        assert active_cred.encrypted_api_key == "my_valid_binance_api_key_12345"


@pytest.mark.asyncio
async def test_telegram_setup_account_wizard_cancel(async_session: AsyncSession, setup_env: dict):
    """Test cancelling the setup wizard at any point."""
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
    )

    # Start wizard
    await tg_service.handle_callback_query("WIZ_ENV_MAINNET", message_id=1, chat_id=111)
    assert 111 in tg_service._wizard_state

    # Cancel via text
    cancel_res = await tg_service.handle_user_message("/cancel", chat_id=111)
    assert "Setup akun dibatalkan" in cancel_res
    assert 111 not in tg_service._wizard_state


@pytest.mark.asyncio
async def test_telegram_resolve_signal_provider_auto_creation(async_session: AsyncSession):
    """Test resolving or auto-creating SignalProvider in TelegramService without breaking FK constraints."""
    prov_repo = SignalProviderRepository(async_session)
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=prov_repo,
    )

    # 1. On empty table, should auto-create provider
    provider_id = await tg_service._resolve_signal_provider_id(
        name="AI Telegram Channel", provider_type="TELEGRAM"
    )
    assert provider_id is not None
    assert provider_id > 0

    # 2. On second call, should reuse existing provider
    second_id = await tg_service._resolve_signal_provider_id(
        name="AI Telegram Channel", provider_type="TELEGRAM"
    )
    assert second_id == provider_id


@pytest.mark.asyncio
async def test_telegram_handle_incoming_signal_with_dynamic_instrument(async_session: AsyncSession):
    """Test full incoming raw signal processing with dynamic on-demand provider and instrument provisioning."""
    inst_repo = InstrumentRepository(async_session)
    ex_repo = ExchangeRepository(async_session)
    watch_repo = WatchlistRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    sig_repo = SignalRepository(async_session)

    mock_binance = MagicMock(spec=BinanceRestClient)
    mock_binance.fetch_instruments_metadata = AsyncMock(
        return_value=[
            {
                "symbol": "AAVEUSDT",
                "base_asset": "AAVE",
                "quote_asset": "USDT",
                "price_precision": 3,
                "qty_precision": 1,
                "tick_size": Decimal("0.001"),
                "step_size": Decimal("0.1"),
                "min_qty": Decimal("0.1"),
                "min_notional": Decimal("5.0"),
            }
        ]
    )

    mock_tg = MagicMock()
    mock_tg.send_message = AsyncMock(return_value={"ok": True})

    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ex_repo,
        watchlist_repo=watch_repo,
        binance_client=mock_binance,
    )

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=sig_repo,
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=watch_repo,
        instrument_repo=inst_repo,
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=prov_repo,
        instrument_service=inst_service,
        exchange_repo=ex_repo,
        telegram_client=mock_tg,
    )

    raw_signal = (
        "🤖 AI Agent Detect Chart Pattern\n\n"
        "🚨 Symbol: AAVEUSDT 🔴 Short\n"
        "⏱ Timeframe: 1H\n"
        "📈 Leverage: 75x\n"
        "🔷 Pattern: Falling Wedge(Expanding)\n\n"
        "💰 Entry: 86.568\n"
        "🛡 SL: 87.0955 (-45.70%)\n"
        "🎯 TP1: 86.146 (+36.56%)\n"
        "⚡️ TP2: 85.302 (+109.68%)\n"
        "🔥 TP3: 84.449 (+183.58%)\n\n"
        "🧠 Confidence Score (AI): 70%\n"
    )

    # Process signal message
    res = await tg_service.handle_incoming_signal_message(raw_signal)

    # Verify no Foreign Key violation and signal card was created
    assert res is not None
    mock_tg.send_message.assert_called_once()

    # Verify signal in database
    recent_signals = await sig_repo.get_pending_confirmation_signals()
    assert len(recent_signals) == 1
    signal_in_db = recent_signals[0]
    assert signal_in_db.side == "SELL"
    assert signal_in_db.sl_price == Decimal("87.0955")
    assert signal_in_db.tp1_price == Decimal("86.146")

    # Verify Instrument in database
    inst = await inst_repo.get(signal_in_db.instrument_id)
    assert inst is not None
    assert inst.symbol == "AAVEUSDT"
    assert inst.price_precision == 3

    # Verify Provider in database
    provider = await prov_repo.get(signal_in_db.provider_id)
    assert provider is not None
    assert provider.name == "AI Telegram Channel"


@pytest.mark.asyncio
async def test_telegram_signal_rejected_if_no_account_connected(async_session: AsyncSession):
    """Test that incoming signals are safely intercepted if no active trading account is configured."""
    acc_repo = TradingAccountRepository(async_session)
    cred_repo = TradingCredentialRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)

    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=prov_repo,
        trading_account_repo=acc_repo,
        trading_credential_repo=cred_repo,
        binance_client=None,
    )

    raw_signal = (
        "🚨 Symbol: BTCUSDT 🟢 Long\n"
        "💰 Entry: 65000\n"
        "🛡 SL: 64000\n"
        "🎯 TP1: 67000\n"
    )

    # When sent by user, should return warning prompting /setup_account
    response = await tg_service.handle_user_message(raw_signal, chat_id=123)
    assert "Akun Binance Belum Terhubung!" in response
    assert "/setup_account" in response


@pytest.mark.asyncio
async def test_telegram_circuit_breaker_command(async_session: AsyncSession):
    """Test /circuit_breaker command execution and on-demand risk snapshot provisioning."""
    tg_service = TelegramService(
        signal_parser=SignalParserService(),
        risk_calculator=RiskCalculatorService(),
        trade_service=MagicMock(),
        signal_repo=SignalRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        instrument_repo=InstrumentRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        bot_log_repo=BotLogRepository(async_session),
        bot_setting_repo=BotSettingRepository(async_session),
        signal_provider_repo=SignalProviderRepository(async_session),
    )

    response = await tg_service.handle_command("/circuit_breaker", account_id=1)
    assert "STATUS CIRCUIT BREAKER & RISK" in response
    assert "Status Proteksi: <b>🟢 NORMAL</b>" in response
    assert "Batas Risiko Harian" in response




