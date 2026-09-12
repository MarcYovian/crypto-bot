"""Tests for Market order slippage recalculation and partial fill position scaling."""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Strategy, Trade, Order
from src.domain.entities.trade import OrderFillDTO
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.order_repository import OrderRepository
from src.infrastructure.persistence.repositories.execution_repository import ExecutionRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository
from src.infrastructure.persistence.repositories.daily_risk_repository import DailyRiskRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.risk_profile_repository import RiskProfileRepository
from src.application.use_cases.trades.handle_order_fill_use_case import HandleOrderFillUseCase
from src.application.use_cases.trades.execute_signal_use_case import ExecuteSignalUseCase
from src.application.dto.trade_commands import ExecuteSignalCommand
from src.domain.entities.signal import ParsedSignalDTO

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


class PositionManager:
    def __init__(
        self,
        trade_repo,
        order_repo,
        execution_repo,
        trade_event_repo,
        trade_summary_repo,
        daily_risk_repo,
        instrument_repo=None,
        exchange_gateway=None,
        event_publisher=None,
    ):
        self.trade_repo = trade_repo
        self.order_repo = order_repo
        self.execution_repo = execution_repo
        self.trade_event_repo = trade_event_repo
        self.trade_summary_repo = trade_summary_repo
        self.daily_risk_repo = daily_risk_repo
        self.instrument_repo = instrument_repo or InstrumentRepository(trade_repo.session)
        self.exchange_gateway = exchange_gateway
        self.event_publisher = event_publisher

        self._fill_uc = HandleOrderFillUseCase(
            trade_repo=self.trade_repo,
            order_repo=self.order_repo,
            execution_repo=self.execution_repo,
            trade_event_repo=self.trade_event_repo,
            trade_risk_repo=None,
            trade_summary_repo=self.trade_summary_repo,
            daily_risk_repo=self.daily_risk_repo,
            instrument_repo=self.instrument_repo,
            exchange_gateway=self.exchange_gateway,
            event_publisher=self.event_publisher,
        )

    async def handle_order_fill(self, fill_event):
        return await self._fill_uc.execute(fill_event)


@pytest.mark.asyncio
async def test_partial_fill_adjusts_trade_position_size(async_session: AsyncSession):
    """Test that a partial entry fill automatically updates remaining_qty and position_size."""
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
        exchange_id=exchange.id, symbol="ETHUSDT", base_asset="ETH", quote_asset="USDT",
        min_qty=Decimal("0.01"), step_size=Decimal("0.01"),
        tick_size=Decimal("0.01"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), is_active=True
    )
    async_session.add(inst)
    await async_session.flush()

    trade = Trade(
        account_id=account.id,
        instrument_id=inst.id,
        strategy_id=strategy.id,
        status="WAITING_ENTRY",
        side="BUY",
        entry_price=Decimal("3000.0"),
        position_size=Decimal("1.00"),  # planned 1.0 ETH
        remaining_qty=Decimal("1.00"),
        sl_price=Decimal("2900.0"),
        leverage=10,
        margin_mode="ISOLATED",
    )
    async_session.add(trade)
    await async_session.flush()

    order = Order(
        trade_id=trade.id,
        exchange_order_id="123456",
        client_order_id="ENTRY_1",
        order_type="LIMIT",
        purpose="ENTRY",
        side="BUY",
        price=Decimal("3000.0"),
        qty=Decimal("1.00"),
        status="NEW",
    )
    async_session.add(order)
    await async_session.commit()

    pos_mgr = PositionManager(
        trade_repo=TradeRepository(async_session),
        order_repo=OrderRepository(async_session),
        execution_repo=ExecutionRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        trade_summary_repo=TradeSummaryRepository(async_session),
        daily_risk_repo=DailyRiskRepository(async_session),
    )

    # Simulate Partial Fill event: only 0.60 ETH filled
    fill_event = OrderFillDTO(
        trade_id=trade.id,
        order_id=order.id,
        exchange_order_id="123456",
        symbol="ETHUSDT",
        side="BUY",
        purpose="ENTRY",
        fill_price=Decimal("3000.0"),
        fill_qty=Decimal("0.60"),
        fee=Decimal("0.05"),
        fee_asset="USDT",
        realized_pnl=Decimal("0.0"),
    )

    await pos_mgr.handle_order_fill(fill_event)

    updated_trade = await pos_mgr.trade_repo.get(trade.id)
    assert updated_trade.status == "OPEN"
    assert updated_trade.position_size == Decimal("0.60")
    assert updated_trade.remaining_qty == Decimal("0.60")


@pytest.mark.asyncio
async def test_execution_engine_recalculates_risk_for_market_slippage(async_session: AsyncSession):
    """Test that ExecuteSignalUseCase dynamically executes market order and handles price slippage within tolerance."""
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    account = TradingAccount(
        exchange_id=exchange.id, name="Test Account", account_type="FUTURES", environment="TESTNET", is_active=True
    )
    async_session.add(account)
    await async_session.flush()

    inst = Instrument(
        exchange_id=exchange.id, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
        min_qty=Decimal("0.001"), step_size=Decimal("0.001"),
        tick_size=Decimal("0.1"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), is_active=True
    )
    async_session.add(inst)
    await async_session.flush()

    from src.infrastructure.persistence.models.watchlists import Watchlist
    watchlist = Watchlist(instrument_id=inst.id, enabled=True)
    async_session.add(watchlist)

    from src.infrastructure.persistence.models.risk_profiles import RiskProfile
    risk_prof = RiskProfile(name="DEFAULT", risk_percent=Decimal("2.0"), max_daily_loss=Decimal("5.0"), max_open_trade=3, is_active=True)
    async_session.add(risk_prof)
    await async_session.flush()

    from src.infrastructure.persistence.models.daily_risk_configs import DailyRiskConfig
    from datetime import datetime
    daily_risk = DailyRiskConfig(account_id=account.id, risk_profile_id=risk_prof.id, date=datetime.now().date(), balance=Decimal("1000.0"), risk_amount=Decimal("20.0"))
    async_session.add(daily_risk)
    await async_session.commit()

    mock_exchange_gateway = MagicMock()
    mock_exchange_gateway.fetch_balance = AsyncMock(return_value={"free_margin": Decimal("1000.0")})
    mock_exchange_gateway.fetch_ticker_price = AsyncMock(return_value=Decimal("50050.0"))
    mock_exchange_gateway.fetch_ticker = AsyncMock(return_value={"last": Decimal("50050.0")})
    mock_exchange_gateway.has_price_reached_target = AsyncMock(return_value=False)
    mock_exchange_gateway.set_leverage = AsyncMock(return_value={"leverage": 10})
    mock_exchange_gateway.set_margin_mode = AsyncMock(return_value={"margin_mode": "ISOLATED"})
    mock_exchange_gateway.create_order = AsyncMock(return_value={"order_id": "mkt-123", "exchange_order_id": "mkt-123", "status": "FILLED", "average": 50050.0})
    mock_exchange_gateway.create_stop_loss_order = AsyncMock(return_value={"order_id": "sl-123", "exchange_order_id": "sl-123", "status": "NEW"})
    mock_exchange_gateway.create_take_profit_order = AsyncMock(return_value={"order_id": "tp-123", "exchange_order_id": "tp-123", "status": "NEW"})



    use_case = ExecuteSignalUseCase(
        instrument_repo=InstrumentRepository(async_session),
        watchlist_repo=WatchlistRepository(async_session),
        trade_repo=TradeRepository(async_session),
        trade_risk_repo=None,
        daily_risk_repo=DailyRiskRepository(async_session),
        order_repo=OrderRepository(async_session),
        trade_event_repo=TradeEventRepository(async_session),
        risk_profile_repo=RiskProfileRepository(async_session),
        exchange_gateway=mock_exchange_gateway,
    )

    signal = ParsedSignalDTO(
        raw_text="BUY BTCUSDT Entry: 50000 SL: 49000 TP: 51500",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        entry_min=Decimal("50000"),
        entry_max=Decimal("50000"),
        entry_targets=[Decimal("50000")],
        sl_price=Decimal("49000"),
        tp_targets=[Decimal("51500")],
        leverage=10,
    )

    cmd = ExecuteSignalCommand(signal_dto=signal, account_id=account.id)
    resp = await use_case.execute(cmd)

    assert resp.success is True
    assert resp.execution_type == "MARKET"
    assert resp.entry_order_id == "mkt-123"
