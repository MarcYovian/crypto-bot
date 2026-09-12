"""Comprehensive unit tests for TradeRepository."""

from datetime import datetime, timedelta
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import (
    Exchange,
    TradingAccount,
    Instrument,
    DailyRiskConfig,
    Trade,
    TradeRisk,
    Order,
    Execution,
    TradeEvent,
    TradeSummary,
)
from src.presentation.api.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate
from src.presentation.api.schemas.trade import TradeCreate, TradeStatusUpdate
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository

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
async def base_setup(async_session: AsyncSession):
    """Seed prerequisite Exchange, Account, and Instrument records."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    inst_repo = InstrumentRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Account",
        account_type="FUTURES",
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

    return {"exchange": exchange, "account": account, "instrument": instrument}


@pytest.mark.asyncio
async def test_trade_create_and_active_lookup(async_session: AsyncSession, base_setup: dict):
    """Test creating a trade and checking if an active position exists on the pair."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    # Initially no active trade
    assert await trade_repo.get_active_trade_by_instrument(inst.id) is None

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        sl_price=Decimal("59000"),
        tp1_price=Decimal("61000"),
        tp2_price=Decimal("62000"),
        tp3_price=Decimal("63000"),
        leverage=20,
        margin_mode="ISOLATED",
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1")
    ))

    assert trade.id is not None
    assert trade.status == "WAITING_ENTRY"

    active_trade = await trade_repo.get_active_trade_by_instrument(inst.id)
    assert active_trade is not None
    assert active_trade.id == trade.id


@pytest.mark.asyncio
async def test_trade_active_trade_count_per_account(async_session: AsyncSession, base_setup: dict):
    """Test counting active trades vs closed trades for risk limit checks."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    # 2 OPEN, 1 WAITING_ENTRY, 1 CLOSED
    t1 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="OPEN", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0.1"))
    t2 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="OPEN", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0.1"))
    t3 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="WAITING_ENTRY", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0.1"))
    t4 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0"))

    async_session.add_all([t1, t2, t3, t4])
    await async_session.commit()

    active_count = await trade_repo.count_active_trades(acc.id)
    assert active_count == 3


@pytest.mark.asyncio
async def test_trade_entry_fill_update_avg_price(async_session: AsyncSession, base_setup: dict):
    """Test updating entry execution price and transition to OPEN."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1")
    ))

    # Entry fills at 60050.0
    fill_time = datetime.now()
    updated = await trade_repo.update_entry_fill(
        trade_id=trade.id,
        entry_price=Decimal("60050.0"),
        avg_entry_price=Decimal("60050.0"),
        opened_at=fill_time
    )

    assert updated is not None
    assert updated.status == "OPEN"
    assert updated.entry_price == Decimal("60050.0")
    assert updated.opened_at == fill_time


@pytest.mark.asyncio
async def test_trade_sl_price_update_bep_and_trailing(async_session: AsyncSession, base_setup: dict):
    """Test updating stop-loss price for BEP shift and trailing stop."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        entry_price=Decimal("60000.0"),
        sl_price=Decimal("59000.0"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1")
    ))

    # 1. Shift to BEP (60000.0)
    bep_trade = await trade_repo.update_sl_price(trade.id, Decimal("60000.0"))
    assert bep_trade.sl_price == Decimal("60000.0")

    # 2. Trailing to TP1 (61000.0)
    trailing_trade = await trade_repo.update_sl_price(trade.id, Decimal("61000.0"))
    assert trailing_trade.sl_price == Decimal("61000.0")


@pytest.mark.asyncio
async def test_trade_partial_qty_reduction_and_auto_close(async_session: AsyncSession, base_setup: dict):
    """Test partial lot reduction and automatic CLOSED state when remaining reaches 0."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.10"),
        remaining_qty=Decimal("0.10")
    ))

    # Partial close: deduct 0.05
    step1 = await trade_repo.reduce_position_qty(trade.id, Decimal("0.05"))
    assert step1.remaining_qty == Decimal("0.05")
    assert step1.status == "PARTIAL"
    assert step1.closed_at is None

    # Final close: deduct remaining 0.05
    step2 = await trade_repo.reduce_position_qty(trade.id, Decimal("0.05"))
    assert step2.remaining_qty == Decimal("0.00")
    assert step2.status == "CLOSED"
    assert step2.closed_at is not None


@pytest.mark.asyncio
async def test_trade_eager_load_all_children(async_session: AsyncSession, base_setup: dict):
    """Test eager loading all 5 child relationships (risk, orders, executions, events, summary)."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    # Seed daily risk
    daily_snapshot = DailyRiskConfig(account_id=acc.id, risk_profile_id=1, date=datetime.now().date(), balance=Decimal("10000"), risk_amount=Decimal("200"))
    async_session.add(daily_snapshot)
    await async_session.commit()
    await async_session.refresh(daily_snapshot)

    # Seed trade
    trade = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0"))
    async_session.add(trade)
    await async_session.commit()
    await async_session.refresh(trade)

    # Seed children
    t_risk = TradeRisk(trade_id=trade.id, daily_risk_id=daily_snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.1"), margin=Decimal("300"), risk_amount=Decimal("100"), leverage=20)
    order = Order(trade_id=trade.id, purpose="ENTRY", order_type="MARKET", side="BUY", qty=Decimal("0.1"), filled_qty=Decimal("0.1"), status="FILLED")
    async_session.add_all([t_risk, order])
    await async_session.commit()
    await async_session.refresh(order)

    exec_record = Execution(order_id=order.id, trade_id=trade.id, price=Decimal("60000"), qty=Decimal("0.1"), commission=Decimal("1.2"), commission_asset="USDT", realized_pnl=Decimal("0"))
    event = TradeEvent(trade_id=trade.id, event_type="TP1_HIT", payload_json='{"price": 61000}')
    summary = TradeSummary(trade_id=trade.id, gross_pnl=Decimal("50"), net_pnl=Decimal("48.8"), commission=Decimal("1.2"), funding=Decimal("0"), roi=Decimal("16.2"), rr=Decimal("1.0"), result="WIN", duration_seconds=1200, close_reason="TP1", closed_at=datetime.now())

    async_session.add_all([exec_record, event, summary])
    await async_session.commit()

    # Query with get_detail
    detail = await trade_repo.get_detail(trade.id)
    assert detail is not None
    assert detail.trade_risk.risk_amount == Decimal("100")
    assert len(detail.orders) == 1
    assert len(detail.executions) == 1
    assert len(detail.events) == 1
    assert detail.summary.result == "WIN"


@pytest.mark.asyncio
async def test_trade_expired_waiting_filter(async_session: AsyncSession, base_setup: dict):
    """Test finding expired WAITING_ENTRY trades older than max_hours."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    from datetime import timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    # Fresh trade (created now)
    t_fresh = Trade(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
        created_at=now
    )
    # Old trade (created 5 hours ago)
    t_old = Trade(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1"),
        created_at=now - timedelta(hours=5)
    )

    async_session.add_all([t_fresh, t_old])
    await async_session.commit()

    expired_list = await trade_repo.get_expired_waiting_trades(max_hours=4)
    assert len(expired_list) == 1
    assert expired_list[0].id == t_old.id


@pytest.mark.asyncio
async def test_trade_closed_history_pagination_and_date_filter(async_session: AsyncSession, base_setup: dict):
    """Test pagination and date filtering of closed trade history."""
    trade_repo = TradeRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    for i in range(1, 6):
        t = Trade(
            account_id=acc.id,
            instrument_id=inst.id,
            side="BUY",
            status="CLOSED",
            sl_price=Decimal("59000"),
            leverage=20,
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0"),
            closed_at=datetime.now() - timedelta(days=i)
        )
        async_session.add(t)
    await async_session.commit()

    # Pagination: skip 1, limit 2
    page = await trade_repo.get_closed_trades_history(acc.id, skip=1, limit=2)
    assert len(page) == 2
