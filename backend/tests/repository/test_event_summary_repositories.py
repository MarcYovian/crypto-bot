"""Comprehensive unit tests for TradeEventRepository and TradeSummaryRepository."""

import json
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument, Trade, TradeEvent, TradeSummary
from src.presentation.api.schemas.master import ExchangeCreate, TradingAccountCreate, InstrumentCreate
from src.presentation.api.schemas.trade import TradeCreate
from src.presentation.api.schemas.event_summary import TradeEventCreate, TradeSummaryCreate
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.trading_account_repository import TradingAccountRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.trade_repository import TradeRepository
from src.infrastructure.persistence.repositories.trade_event_repository import TradeEventRepository
from src.infrastructure.persistence.repositories.trade_summary_repository import TradeSummaryRepository

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

    return {"exchange": exchange, "account": account, "instrument": instrument}


@pytest.mark.asyncio
async def test_trade_event_log_and_order_flow(async_session: AsyncSession, base_setup: dict):
    """Test appending audit events and retrieving them in chronological order."""
    trade_repo = TradeRepository(async_session)
    event_repo = TradeEventRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1")
    ))

    now = datetime.now()
    e1 = await event_repo.log_event(trade.id, "ENTRY", created_at=now - timedelta(minutes=10))
    e2 = await event_repo.log_event(trade.id, "TP1_HIT", created_at=now - timedelta(minutes=5))
    e3 = await event_repo.log_event(trade.id, "SL_MOVED_TO_BEP", created_at=now)

    timeline = await event_repo.get_events_by_trade(trade.id)
    assert len(timeline) == 3
    assert timeline[0].id == e1.id
    assert timeline[1].id == e2.id
    assert timeline[2].id == e3.id


@pytest.mark.asyncio
async def test_trade_event_json_payload_and_latest_lookup(async_session: AsyncSession, base_setup: dict):
    """Test logging events with dictionary payload and fetching latest milestone."""
    trade_repo = TradeRepository(async_session)
    event_repo = TradeEventRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="OPEN",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1")
    ))

    # Log with dict payload
    payload_data = {"price": 61000.0, "tp_level": 1, "closed_qty": 0.05}
    await event_repo.log_event(trade.id, "TP1_HIT", payload=payload_data)

    latest = await event_repo.get_latest_event_by_trade(trade.id)
    assert latest is not None
    assert latest.event_type == "TP1_HIT"
    assert latest.payload_json is not None

    parsed = json.loads(latest.payload_json)
    assert parsed["tp_level"] == 1
    assert parsed["price"] == 61000.0


@pytest.mark.asyncio
async def test_trade_summary_create_and_get_by_trade(async_session: AsyncSession, base_setup: dict):
    """Test creating and retrieving trade performance summary."""
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    trade = await trade_repo.create(TradeCreate(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="CLOSED",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.0")
    ))

    summary = await sum_repo.create(TradeSummaryCreate(
        trade_id=trade.id,
        gross_pnl=Decimal("50.00"),
        net_pnl=Decimal("48.50"),
        commission=Decimal("1.50"),
        funding=Decimal("0.00"),
        roi=Decimal("24.25"),
        rr=Decimal("2.0"),
        result="WIN",
        duration_seconds=3600,
        close_reason="TP2_HIT",
        closed_at=datetime.now()
    ))

    assert summary.trade_id == trade.id
    assert summary.net_pnl == Decimal("48.50")

    fetched = await sum_repo.get_by_trade_id(trade.id)
    assert fetched is not None
    assert fetched.result == "WIN"
    assert fetched.roi == Decimal("24.25")


@pytest.mark.asyncio
async def test_performance_summary_comprehensive_metrics(async_session: AsyncSession, base_setup: dict):
    """Test aggregate financial calculations: Win Rate, Total Net PnL, Profit Factor, Fees."""
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    # Create 4 trades
    t1 = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))
    t2 = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))
    t3 = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))
    t4 = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))

    # Summary 1: WIN, Gross +100, Fee 2, Net +98, RR 2.0
    await sum_repo.create(TradeSummaryCreate(trade_id=t1.id, gross_pnl=Decimal("100.00"), net_pnl=Decimal("98.00"), commission=Decimal("2.00"), funding=Decimal("0.00"), roi=Decimal("49.0"), rr=Decimal("2.0"), result="WIN", duration_seconds=1200, close_reason="TP2", closed_at=datetime.now()))
    # Summary 2: WIN, Gross +50, Fee 1, Net +49, RR 1.0
    await sum_repo.create(TradeSummaryCreate(trade_id=t2.id, gross_pnl=Decimal("50.00"), net_pnl=Decimal("49.00"), commission=Decimal("1.00"), funding=Decimal("0.00"), roi=Decimal("24.5"), rr=Decimal("1.0"), result="WIN", duration_seconds=600, close_reason="TP1", closed_at=datetime.now()))
    # Summary 3: LOSS, Gross -40, Fee 1, Net -41, RR -1.0
    await sum_repo.create(TradeSummaryCreate(trade_id=t3.id, gross_pnl=Decimal("-40.00"), net_pnl=Decimal("-41.00"), commission=Decimal("1.00"), funding=Decimal("0.00"), roi=Decimal("-20.5"), rr=Decimal("-1.0"), result="LOSS", duration_seconds=300, close_reason="SL", closed_at=datetime.now()))
    # Summary 4: BREAKEVEN, Gross 0, Fee 1, Net -1, RR 0.0
    await sum_repo.create(TradeSummaryCreate(trade_id=t4.id, gross_pnl=Decimal("0.00"), net_pnl=Decimal("-1.00"), commission=Decimal("1.00"), funding=Decimal("0.00"), roi=Decimal("-0.5"), rr=Decimal("0.0"), result="BREAKEVEN", duration_seconds=400, close_reason="BEP", closed_at=datetime.now()))

    metrics = await sum_repo.get_performance_summary(account_id=acc.id)

    assert metrics["total_trades"] == 4
    assert metrics["winning_trades"] == 2
    assert metrics["losing_trades"] == 1
    assert metrics["breakeven_trades"] == 1
    assert metrics["win_rate"] == 50.0
    assert metrics["total_gross_pnl"] == Decimal("110.00")
    assert metrics["total_net_pnl"] == Decimal("105.00")
    assert metrics["total_commission"] == Decimal("5.00")
    assert metrics["profit_factor"] == 3.75  # (100 + 50) / 40 = 3.75


@pytest.mark.asyncio
async def test_performance_summary_date_filtering(async_session: AsyncSession, base_setup: dict):
    """Test filtering performance summary by date range."""
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    t_old = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))
    t_new = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))

    now = datetime.now()
    await sum_repo.create(TradeSummaryCreate(trade_id=t_old.id, gross_pnl=Decimal("50.00"), net_pnl=Decimal("49.00"), commission=Decimal("1.00"), funding=Decimal("0"), roi=Decimal("24.5"), rr=Decimal("1.0"), result="WIN", duration_seconds=500, close_reason="TP", closed_at=now - timedelta(days=2)))
    await sum_repo.create(TradeSummaryCreate(trade_id=t_new.id, gross_pnl=Decimal("100.00"), net_pnl=Decimal("98.00"), commission=Decimal("2.00"), funding=Decimal("0"), roi=Decimal("49.0"), rr=Decimal("2.0"), result="WIN", duration_seconds=500, close_reason="TP", closed_at=now))

    # Query only today (past 24h)
    filtered = await sum_repo.get_performance_summary(
        account_id=acc.id,
        start_date=now - timedelta(days=1)
    )

    assert filtered["total_trades"] == 1
    assert filtered["total_net_pnl"] == Decimal("98.00")


@pytest.mark.asyncio
async def test_trade_summary_best_and_worst_trades(async_session: AsyncSession, base_setup: dict):
    """Test retrieving best winning trade and worst losing trade."""
    trade_repo = TradeRepository(async_session)
    sum_repo = TradeSummaryRepository(async_session)
    acc = base_setup["account"]
    inst = base_setup["instrument"]

    t_best = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))
    t_mid = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))
    t_worst = await trade_repo.create(TradeCreate(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0")))

    await sum_repo.create(TradeSummaryCreate(trade_id=t_best.id, gross_pnl=Decimal("150.00"), net_pnl=Decimal("148.00"), commission=Decimal("2.00"), funding=Decimal("0"), roi=Decimal("74.0"), rr=Decimal("3.0"), result="WIN", duration_seconds=1000, close_reason="TP3", closed_at=datetime.now()))
    await sum_repo.create(TradeSummaryCreate(trade_id=t_mid.id, gross_pnl=Decimal("50.00"), net_pnl=Decimal("49.00"), commission=Decimal("1.00"), funding=Decimal("0"), roi=Decimal("24.5"), rr=Decimal("1.0"), result="WIN", duration_seconds=500, close_reason="TP1", closed_at=datetime.now()))
    await sum_repo.create(TradeSummaryCreate(trade_id=t_worst.id, gross_pnl=Decimal("-80.00"), net_pnl=Decimal("-82.00"), commission=Decimal("2.00"), funding=Decimal("0"), roi=Decimal("-41.0"), rr=Decimal("-1.5"), result="LOSS", duration_seconds=300, close_reason="SL", closed_at=datetime.now()))

    extreme = await sum_repo.get_best_and_worst_trade(account_id=acc.id)

    assert extreme["best_trade"] is not None
    assert extreme["best_trade"].trade_id == t_best.id
    assert extreme["best_trade"].net_pnl == Decimal("148.00")

    assert extreme["worst_trade"] is not None
    assert extreme["worst_trade"].trade_id == t_worst.id
    assert extreme["worst_trade"].net_pnl == Decimal("-82.00")
