"""Tests for Daily Loss Hard Circuit Breaker auto-pause and midnight reset."""

import pytest
import pytest_asyncio
from decimal import Decimal
from datetime import datetime, date
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Strategy, RiskProfile, Trade, DailyRiskConfig, BotSetting
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.bot_setting_repository import BotSettingRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.services.position_manager import PositionManager
from src.services.scheduler_service import SchedulerService
from src.clients.binance_client import BinanceRestClient
from src.clients.telegram_client import TelegramNotifierClient

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
async def cb_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(
        exchange_id=exchange.id, name="Test Account", account_type="FUTURES", environment="TESTNET", is_active=True
    )
    async_session.add(account)
    await async_session.flush()

    strategy = Strategy(name="Strategy 1", version="1.0.0", is_active=True)
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
        name="Conservative", risk_percent=Decimal("2.0"), max_daily_loss=Decimal("6.0"), max_open_trade=3, is_active=True
    )
    async_session.add(profile)
    await async_session.flush()

    today = datetime.now().date()
    snapshot = DailyRiskConfig(
        account_id=account.id, risk_profile_id=profile.id, date=today, balance=Decimal("1000.0"), risk_amount=Decimal("20.0")
    )
    async_session.add(snapshot)

    setting = BotSetting(key="is_paused", value="false", description="Bot pause status")
    async_session.add(setting)

    await async_session.commit()
    await async_session.refresh(account)
    await async_session.refresh(inst)
    await async_session.refresh(strategy)

    return {"exchange": exchange, "account": account, "inst": inst, "strategy": strategy, "snapshot": snapshot}


@pytest.mark.asyncio
async def test_circuit_breaker_triggers_auto_pause_on_loss_limit(async_session: AsyncSession, cb_env: dict):
    """Test that consecutive losses reaching 3x standard risk ($60) automatically pauses the bot."""
    env = cb_env
    mock_tg = AsyncMock(spec=TelegramNotifierClient)
    mock_binance = AsyncMock(spec=BinanceRestClient)

    setting_repo = BotSettingRepository(async_session)
    pos_mgr = PositionManager(
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
        bot_setting_repo=setting_repo,
        risk_profile_repo=RiskProfileRepository(async_session),
        binance_client=mock_binance,
        telegram_client=mock_tg,
    )

    # Create and close losing trade with -$65.00 PnL
    trade = Trade(
        account_id=env["account"].id,
        instrument_id=env["inst"].id,
        strategy_id=env["strategy"].id,
        status="OPEN",
        side="BUY",
        entry_price=Decimal("50000.0"),
        position_size=Decimal("0.03"),
        remaining_qty=Decimal("0.03"),
        sl_price=Decimal("48000.0"),
        leverage=10,
        margin_mode="ISOLATED",
    )
    async_session.add(trade)
    await async_session.commit()

    with patch.object(pos_mgr.execution_repo, "get_total_realized_pnl_by_trade", AsyncMock(return_value=Decimal("-65.0"))), \
         patch.object(pos_mgr.execution_repo, "get_total_commission_by_trade", AsyncMock(return_value=Decimal("0.0"))), \
         patch.object(pos_mgr.trade_summary_repo, "get_performance_summary", AsyncMock(return_value={"total_net_pnl": Decimal("-65.0")})):

        summary = await pos_mgr.finalize_trade_closure(trade.id, close_reason="STOP_LOSS")

    assert summary.result == "LOSS"
    paused_val = await setting_repo.get_value("is_paused")
    assert paused_val == "true"
    assert mock_tg.send_message.called


@pytest.mark.asyncio
async def test_scheduler_unpauses_bot_at_midnight_reset(async_session: AsyncSession, cb_env: dict):
    """Test that 00:00 WIB midnight job unpauses the bot for the new trading day."""
    env = cb_env
    setting_repo = BotSettingRepository(async_session)
    await setting_repo.set_value("is_paused", "true")

    mock_binance = AsyncMock(spec=BinanceRestClient)
    mock_binance.fetch_balance = AsyncMock(return_value={"total_wallet_balance": Decimal("1000.0")})
    mock_tg = AsyncMock(spec=TelegramNotifierClient)

    scheduler = SchedulerService(
        daily_risk_repo=DailyRiskRepository(async_session),
        trading_account_repo=None,
        risk_profile_repo=RiskProfileRepository(async_session),
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        instrument_repo=None,
        trade_summary_repo=TradeSummaryRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        bot_log_repo=None,
        bot_setting_repo=setting_repo,
        binance_client=mock_binance,
        telegram_client=mock_tg,
    )

    await scheduler.run_daily_risk_snapshot_job(account_id=env["account"].id, snapshot_date=date(2026, 8, 25))

    unpaused_val = await setting_repo.get_value("is_paused")
    assert unpaused_val == "false"
