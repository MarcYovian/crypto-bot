"""Tests for Market order slippage recalculation and partial fill position scaling."""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Strategy, Trade, Order
from src.domain.entities.trade import OrderFillDTO
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository
from src.repository.trade_event_repository import TradeEventRepository
from src.repository.trade_summary_repository import TradeSummaryRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.services.position_manager import PositionManager
from src.services.risk_calculator import RiskCalculatorService, RiskCalculationResult
from src.services.precision_filter import SymbolInfo
from src.services.execution_engine import BinanceExecutionEngine

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
async def test_execution_engine_recalculates_risk_for_market_slippage():
    """Test that BinanceExecutionEngine dynamically recalculates risk on market price."""
    engine = BinanceExecutionEngine(trade_repo=None, api_key="dummy", secret_key="dummy", testnet=True)
    engine.exchange = AsyncMock()
    engine.exchange.fetch_ticker = AsyncMock(return_value={"last": 50050.0})
    engine.exchange.set_margin_mode = AsyncMock()
    engine.exchange.set_leverage = AsyncMock()
    engine.exchange.create_order = AsyncMock(return_value={"id": "mkt-123"})
    engine.exchange.create_orders = AsyncMock(return_value=[{"id": "sl-1"}, {"id": "tp-1"}])
    engine.exchange.fetch_positions = AsyncMock(return_value=[{"contracts": 0.02, "entryPrice": 50050.0, "initialMargin": 100.1}])

    risk_res = RiskCalculationResult(
        risk_amount=Decimal("20.0"),
        stop_distance=Decimal("1000.0"),
        position_size=Decimal("0.02"),
        required_margin=Decimal("100.0"),
        risk_percent=Decimal("2.0"),
        entry_price=Decimal("50000.0"),
        sl_price=Decimal("49000.0"),
        leverage=10,
        is_valid=True,
    )

    symbol_info = SymbolInfo(
        symbol="BTCUSDT", price_precision=2, qty_precision=3, tick_size=0.1, min_qty=0.001, max_qty=100.0, step_size=0.001, min_notional=5.0
    )

    resp = await engine.execute_trade_pipeline(
        trade_id=99,
        symbol="BTCUSDT",
        side="BUY",
        risk_res=risk_res,
        tp_prices=[51500.0],
        leverage=10,
        symbol_info=symbol_info,
    )

    assert resp.success is True
    assert resp.execution_type == "MARKET"
    assert resp.entry_order_id == "mkt-123"
