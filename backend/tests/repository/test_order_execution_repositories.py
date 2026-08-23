"""Comprehensive unit tests for OrderRepository and ExecutionRepository."""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.database.connection import Base
from src.database.models import Exchange, TradingAccount, Instrument, Trade, Order, Execution
from src.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate
from src.schemas.trade import TradeCreate
from src.schemas.order import OrderCreate, ExecutionCreate
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.trade_repository import TradeRepository
from src.repository.order_repository import OrderRepository
from src.repository.execution_repository import ExecutionRepository

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
async def base_trade(async_session: AsyncSession):
    """Seed prerequisite Trade entity."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    trade_repo = TradeRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        environment="MAINNET",
        is_active=True
    ))
    instrument = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=Decimal("0.10"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=1,
        qty_precision=3,
        is_active=True
    ))
    trade = await trade_repo.create(TradeCreate(
        account_id=account.id,
        instrument_id=instrument.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("59000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1")
    ))

    return trade


@pytest.mark.asyncio
async def test_order_create_and_fetch_by_exchange_and_client_id(async_session: AsyncSession, base_trade: Trade):
    """Test creating an order and querying via exchange_order_id and client_order_id."""
    order_repo = OrderRepository(async_session)

    order = await order_repo.create(OrderCreate(
        trade_id=base_trade.id,
        exchange_order_id="bin_998811",
        client_order_id="BOT_ENTRY_01",
        purpose="ENTRY",
        order_type="LIMIT",
        side="BUY",
        price=Decimal("60000.0"),
        qty=Decimal("0.1"),
        filled_qty=Decimal("0.0"),
        status="NEW"
    ))

    assert order.id is not None
    assert order.exchange_order_id == "bin_998811"

    by_ex = await order_repo.get_by_exchange_order_id("bin_998811")
    assert by_ex is not None
    assert by_ex.id == order.id

    by_client = await order_repo.get_by_client_order_id("BOT_ENTRY_01")
    assert by_client is not None
    assert by_client.id == order.id


@pytest.mark.asyncio
async def test_order_get_by_purpose(async_session: AsyncSession, base_trade: Trade):
    """Test retrieving orders filtered by specific purpose."""
    order_repo = OrderRepository(async_session)

    await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="ENTRY", order_type="MARKET", side="BUY", qty=Decimal("0.1"), status="FILLED"))
    await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="TP1", order_type="LIMIT", side="SELL", price=Decimal("61000"), qty=Decimal("0.05"), status="NEW"))
    await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="TP2", order_type="LIMIT", side="SELL", price=Decimal("62000"), qty=Decimal("0.05"), status="NEW"))
    await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="SL", order_type="STOP_MARKET", side="SELL", stop_price=Decimal("59000"), qty=Decimal("0.1"), status="NEW"))

    sl_orders = await order_repo.get_orders_by_purpose(base_trade.id, "sl")
    assert len(sl_orders) == 1
    assert sl_orders[0].purpose == "SL"

    tp_orders = await order_repo.get_orders_by_purpose(base_trade.id, "TP1")
    assert len(tp_orders) == 1
    assert tp_orders[0].price == Decimal("61000")


@pytest.mark.asyncio
async def test_order_cancel_all_open_orders_for_trade(async_session: AsyncSession, base_trade: Trade):
    """Test bulk cancellation of open orders on a trade."""
    order_repo = OrderRepository(async_session)

    # 1 FILLED, 2 NEW
    o_filled = await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="ENTRY", order_type="MARKET", side="BUY", qty=Decimal("0.1"), filled_qty=Decimal("0.1"), status="FILLED"))
    o_tp = await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="TP1", order_type="LIMIT", side="SELL", price=Decimal("61000"), qty=Decimal("0.05"), status="NEW"))
    o_sl = await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="SL", order_type="STOP_MARKET", side="SELL", stop_price=Decimal("59000"), qty=Decimal("0.1"), status="NEW"))

    # Cancel all open
    cancelled_count = await order_repo.cancel_all_open_orders_for_trade(base_trade.id)
    assert cancelled_count == 2

    # Verify statuses
    refreshed_filled = await order_repo.get(o_filled.id)
    refreshed_tp = await order_repo.get(o_tp.id)
    refreshed_sl = await order_repo.get(o_sl.id)

    assert refreshed_filled.status == "FILLED"
    assert refreshed_tp.status == "CANCELED"
    assert refreshed_sl.status == "CANCELED"


@pytest.mark.asyncio
async def test_order_update_fill_event(async_session: AsyncSession, base_trade: Trade):
    """Test atomic update of order fill from WebSocket message."""
    order_repo = OrderRepository(async_session)

    order = await order_repo.create(OrderCreate(
        trade_id=base_trade.id,
        exchange_order_id="bin_fill_test",
        purpose="ENTRY",
        order_type="LIMIT",
        side="BUY",
        price=Decimal("60000"),
        qty=Decimal("0.1"),
        filled_qty=Decimal("0.0"),
        status="NEW"
    ))

    updated = await order_repo.update_order_fill(
        exchange_order_id="bin_fill_test",
        status="FILLED",
        filled_qty=Decimal("0.1")
    )

    assert updated is not None
    assert updated.status == "FILLED"
    assert updated.filled_qty == Decimal("0.1")


@pytest.mark.asyncio
async def test_execution_record_and_total_commission_calc(async_session: AsyncSession, base_trade: Trade):
    """Test recording fills and calculating total trade commissions."""
    order_repo = OrderRepository(async_session)
    exec_repo = ExecutionRepository(async_session)

    order = await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="ENTRY", order_type="MARKET", side="BUY", qty=Decimal("0.1"), status="FILLED"))

    # Fill 1: commission 0.50 USDT
    await exec_repo.create(ExecutionCreate(
        order_id=order.id,
        trade_id=base_trade.id,
        price=Decimal("60000.0"),
        qty=Decimal("0.05"),
        commission=Decimal("0.50"),
        commission_asset="USDT",
        realized_pnl=Decimal("0.0")
    ))

    # Fill 2: commission 0.70 USDT
    await exec_repo.create(ExecutionCreate(
        order_id=order.id,
        trade_id=base_trade.id,
        price=Decimal("60000.0"),
        qty=Decimal("0.05"),
        commission=Decimal("0.70"),
        commission_asset="USDT",
        realized_pnl=Decimal("0.0")
    ))

    total_comm = await exec_repo.get_total_commission_by_trade(base_trade.id)
    assert total_comm == Decimal("1.20")


@pytest.mark.asyncio
async def test_execution_total_realized_pnl_calculation(async_session: AsyncSession, base_trade: Trade):
    """Test calculating cumulative realized PnL across multiple exit fills."""
    order_repo = OrderRepository(async_session)
    exec_repo = ExecutionRepository(async_session)

    tp1_order = await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="TP1", order_type="LIMIT", side="SELL", price=Decimal("61000"), qty=Decimal("0.05"), status="FILLED"))
    tp2_order = await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="TP2", order_type="LIMIT", side="SELL", price=Decimal("62000"), qty=Decimal("0.05"), status="FILLED"))

    # TP1 fill: +25.50 USDT
    await exec_repo.create(ExecutionCreate(
        order_id=tp1_order.id,
        trade_id=base_trade.id,
        price=Decimal("61000.0"),
        qty=Decimal("0.05"),
        commission=Decimal("0.60"),
        commission_asset="USDT",
        realized_pnl=Decimal("25.50")
    ))

    # TP2 fill: +35.00 USDT
    await exec_repo.create(ExecutionCreate(
        order_id=tp2_order.id,
        trade_id=base_trade.id,
        price=Decimal("62000.0"),
        qty=Decimal("0.05"),
        commission=Decimal("0.60"),
        commission_asset="USDT",
        realized_pnl=Decimal("35.00")
    ))

    total_pnl = await exec_repo.get_total_realized_pnl_by_trade(base_trade.id)
    assert total_pnl == Decimal("60.50")


@pytest.mark.asyncio
async def test_execution_chronological_ordering(async_session: AsyncSession, base_trade: Trade):
    """Test that executions for a trade are returned in ascending time order."""
    order_repo = OrderRepository(async_session)
    exec_repo = ExecutionRepository(async_session)

    order = await order_repo.create(OrderCreate(trade_id=base_trade.id, purpose="ENTRY", order_type="MARKET", side="BUY", qty=Decimal("0.3"), status="FILLED"))

    now = datetime.now()
    e1 = await exec_repo.create({
        "order_id": order.id,
        "trade_id": base_trade.id,
        "price": Decimal("60000"),
        "qty": Decimal("0.1"),
        "commission": Decimal("0.1"),
        "commission_asset": "USDT",
        "realized_pnl": Decimal("0"),
        "executed_at": now - timedelta(minutes=10)
    })
    e2 = await exec_repo.create({
        "order_id": order.id,
        "trade_id": base_trade.id,
        "price": Decimal("60010"),
        "qty": Decimal("0.1"),
        "commission": Decimal("0.1"),
        "commission_asset": "USDT",
        "realized_pnl": Decimal("0"),
        "executed_at": now - timedelta(minutes=5)
    })
    e3 = await exec_repo.create({
        "order_id": order.id,
        "trade_id": base_trade.id,
        "price": Decimal("60020"),
        "qty": Decimal("0.1"),
        "commission": Decimal("0.1"),
        "commission_asset": "USDT",
        "realized_pnl": Decimal("0"),
        "executed_at": now
    })

    fills = await exec_repo.get_executions_by_trade_id(base_trade.id)
    assert len(fills) == 3
    assert fills[0].id == e1.id
    assert fills[1].id == e2.id
    assert fills[2].id == e3.id
