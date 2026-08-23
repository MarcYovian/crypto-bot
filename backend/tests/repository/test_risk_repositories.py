"""Comprehensive unit tests for DailyRiskRepository and TradeRiskRepository."""

from datetime import date, timedelta
from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.database.connection import Base
from src.database.models import (
    Exchange,
    TradingAccount,
    RiskProfile,
    Instrument,
    DailyRiskConfig,
    Trade,
    TradeRisk,
)
from src.schemas.master import (
    ExchangeCreate,
    TradingAccountCreate,
    RiskProfileCreate,
    InstrumentCreate,
)
from src.schemas.risk import DailyRiskConfigCreate, TradeRiskCreate
from src.repository.exchange_repository import ExchangeRepository
from src.repository.trading_account_repository import TradingAccountRepository
from src.repository.risk_profile_repository import RiskProfileRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.daily_risk_repository import DailyRiskRepository
from src.repository.trade_risk_repository import TradeRiskRepository

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
async def base_entities(async_session: AsyncSession):
    """Seed prerequisite master entities (Exchange, Account, RiskProfile, Instrument)."""
    ex_repo = ExchangeRepository(async_session)
    acc_repo = TradingAccountRepository(async_session)
    rp_repo = RiskProfileRepository(async_session)
    inst_repo = InstrumentRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))
    account = await acc_repo.create(TradingAccountCreate(
        exchange_id=exchange.id,
        name="Main Futures Account",
        account_type="FUTURES",
        environment="MAINNET",
        is_active=True
    ))
    profile = await rp_repo.create(RiskProfileCreate(
        name="Strict 2% Profile",
        risk_percent=Decimal("2.0"),
        max_daily_loss=Decimal("6.0"),
        max_open_trade=3,
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

    return {
        "exchange": exchange,
        "account": account,
        "profile": profile,
        "instrument": instrument,
    }


@pytest.mark.asyncio
async def test_daily_risk_snapshot_create_and_fetch(async_session: AsyncSession, base_entities: dict):
    """Test creating a daily risk snapshot and fetching it by date."""
    daily_repo = DailyRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]

    today = date(2026, 8, 14)
    snapshot = await daily_repo.create(DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=today,
        balance=Decimal("10000.00"),
        risk_amount=Decimal("200.00")
    ))

    assert snapshot.id is not None
    assert snapshot.balance == Decimal("10000.00")
    assert snapshot.risk_amount == Decimal("200.00")

    fetched = await daily_repo.get_by_date(acc.id, today)
    assert fetched is not None
    assert fetched.id == snapshot.id
    assert fetched.date == today


@pytest.mark.asyncio
async def test_daily_risk_idempotency_get_or_create(async_session: AsyncSession, base_entities: dict):
    """Test that get_or_create_daily_snapshot returns the existing record without duplicating."""
    daily_repo = DailyRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]

    target_date = date(2026, 8, 15)
    payload_1 = DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=target_date,
        balance=Decimal("10000.00"),
        risk_amount=Decimal("200.00")
    )

    # First call: creates record
    first = await daily_repo.get_or_create_daily_snapshot(payload_1)
    assert first.id is not None
    assert first.balance == Decimal("10000.00")

    # Second call on same day with different balance
    payload_2 = DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=target_date,
        balance=Decimal("12000.00"),
        risk_amount=Decimal("240.00")
    )
    second = await daily_repo.get_or_create_daily_snapshot(payload_2)

    # Must return original snapshot
    assert second.id == first.id
    assert second.balance == Decimal("10000.00")
    assert await daily_repo.count() == 1


@pytest.mark.asyncio
async def test_daily_risk_history_date_range_query(async_session: AsyncSession, base_entities: dict):
    """Test retrieving daily equity curve history within a date range."""
    daily_repo = DailyRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]

    start = date(2026, 8, 10)
    for i in range(5):
        d = start + timedelta(days=i)
        await daily_repo.create(DailyRiskConfigCreate(
            account_id=acc.id,
            risk_profile_id=prof.id,
            date=d,
            balance=Decimal(str(10000 + i * 500)),
            risk_amount=Decimal(str(200 + i * 10))
        ))

    # Query range of 3 days (Aug 11 to Aug 13)
    history = await daily_repo.get_daily_history(acc.id, start_date=date(2026, 8, 11), end_date=date(2026, 8, 13))
    assert len(history) == 3
    assert history[0].date == date(2026, 8, 11)
    assert history[1].date == date(2026, 8, 12)
    assert history[2].date == date(2026, 8, 13)


@pytest.mark.asyncio
async def test_trade_risk_create_and_get_by_trade_id(async_session: AsyncSession, base_entities: dict):
    """Test creating and querying per-trade risk breakdown."""
    daily_repo = DailyRiskRepository(async_session)
    tr_repo = TradeRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]
    inst = base_entities["instrument"]

    snapshot = await daily_repo.create(DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=date(2026, 8, 14),
        balance=Decimal("10000.00"),
        risk_amount=Decimal("200.00")
    ))

    # Create dummy trade
    trade = Trade(
        account_id=acc.id,
        instrument_id=inst.id,
        side="BUY",
        status="WAITING_ENTRY",
        sl_price=Decimal("59000"),
        leverage=20,
        position_size=Decimal("0.1"),
        remaining_qty=Decimal("0.1")
    )
    async_session.add(trade)
    await async_session.commit()
    await async_session.refresh(trade)

    # Create TradeRisk
    tr = await tr_repo.create(TradeRiskCreate(
        trade_id=trade.id,
        daily_risk_id=snapshot.id,
        entry=Decimal("60000.0"),
        stop=Decimal("59000.0"),
        stop_distance=Decimal("1000.0"),
        qty=Decimal("0.1"),
        margin=Decimal("300.0"),
        risk_amount=Decimal("100.0"),
        leverage=20
    ))

    assert tr.trade_id == trade.id
    assert tr.risk_amount == Decimal("100.0")

    fetched = await tr_repo.get_by_trade_id(trade.id)
    assert fetched is not None
    assert fetched.trade_id == trade.id
    assert fetched.stop_distance == Decimal("1000.0")


@pytest.mark.asyncio
async def test_active_risk_exposure_calculation_with_trade_status(async_session: AsyncSession, base_entities: dict):
    """Test total active risk calculation across WAITING_ENTRY, OPEN, and CLOSED trades."""
    daily_repo = DailyRiskRepository(async_session)
    tr_repo = TradeRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]
    inst = base_entities["instrument"]

    snapshot = await daily_repo.create(DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=date(2026, 8, 14),
        balance=Decimal("10000.00"),
        risk_amount=Decimal("200.00")
    ))

    # Trade 1: OPEN ($50 risk)
    t1 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="OPEN", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.05"), remaining_qty=Decimal("0.05"))
    # Trade 2: WAITING_ENTRY ($50 risk)
    t2 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="WAITING_ENTRY", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.05"), remaining_qty=Decimal("0.05"))
    # Trade 3: CLOSED ($50 risk - should be excluded from active exposure)
    t3 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="CLOSED", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.05"), remaining_qty=Decimal("0"))

    async_session.add_all([t1, t2, t3])
    await async_session.commit()
    await async_session.refresh(t1)
    await async_session.refresh(t2)
    await async_session.refresh(t3)

    await tr_repo.create(TradeRiskCreate(trade_id=t1.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.05"), margin=Decimal("150"), risk_amount=Decimal("50.0"), leverage=20))
    await tr_repo.create(TradeRiskCreate(trade_id=t2.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.05"), margin=Decimal("150"), risk_amount=Decimal("50.0"), leverage=20))
    await tr_repo.create(TradeRiskCreate(trade_id=t3.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.05"), margin=Decimal("150"), risk_amount=Decimal("50.0"), leverage=20))

    active_risk = await tr_repo.get_total_active_risk_exposure(acc.id)
    assert active_risk == Decimal("100.0")


@pytest.mark.asyncio
async def test_remaining_risk_budget_calculation(async_session: AsyncSession, base_entities: dict):
    """Test remaining risk budget calculation for today's snapshot."""
    daily_repo = DailyRiskRepository(async_session)
    tr_repo = TradeRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]
    inst = base_entities["instrument"]

    snapshot = await daily_repo.create(DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=date(2026, 8, 14),
        balance=Decimal("10000.00"),
        risk_amount=Decimal("200.00")
    ))

    t1 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="OPEN", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.04"), remaining_qty=Decimal("0.04"))
    t2 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="OPEN", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.035"), remaining_qty=Decimal("0.035"))
    async_session.add_all([t1, t2])
    await async_session.commit()
    await async_session.refresh(t1)
    await async_session.refresh(t2)

    # Allocate $40 and $35
    await tr_repo.create(TradeRiskCreate(trade_id=t1.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.04"), margin=Decimal("120"), risk_amount=Decimal("40.0"), leverage=20))
    await tr_repo.create(TradeRiskCreate(trade_id=t2.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.035"), margin=Decimal("105"), risk_amount=Decimal("35.0"), leverage=20))

    remaining = await daily_repo.get_remaining_risk_budget(snapshot.id)
    assert remaining == Decimal("125.0")


@pytest.mark.asyncio
async def test_total_margin_used_active_trades(async_session: AsyncSession, base_entities: dict):
    """Test calculating total locked margin for filled active trades."""
    daily_repo = DailyRiskRepository(async_session)
    tr_repo = TradeRiskRepository(async_session)
    acc = base_entities["account"]
    prof = base_entities["profile"]
    inst = base_entities["instrument"]

    snapshot = await daily_repo.create(DailyRiskConfigCreate(
        account_id=acc.id,
        risk_profile_id=prof.id,
        date=date(2026, 8, 14),
        balance=Decimal("10000.00"),
        risk_amount=Decimal("200.00")
    ))

    t_open1 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="OPEN", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0.1"))
    t_open2 = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="PARTIAL", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0.05"))
    t_waiting = Trade(account_id=acc.id, instrument_id=inst.id, side="BUY", status="WAITING_ENTRY", sl_price=Decimal("59000"), leverage=20, position_size=Decimal("0.1"), remaining_qty=Decimal("0.1"))

    async_session.add_all([t_open1, t_open2, t_waiting])
    await async_session.commit()
    await async_session.refresh(t_open1)
    await async_session.refresh(t_open2)
    await async_session.refresh(t_waiting)

    # Margin: $300 (OPEN), $200 (PARTIAL), $150 (WAITING_ENTRY)
    await tr_repo.create(TradeRiskCreate(trade_id=t_open1.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.1"), margin=Decimal("300.0"), risk_amount=Decimal("50.0"), leverage=20))
    await tr_repo.create(TradeRiskCreate(trade_id=t_open2.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.1"), margin=Decimal("200.0"), risk_amount=Decimal("50.0"), leverage=20))
    await tr_repo.create(TradeRiskCreate(trade_id=t_waiting.id, daily_risk_id=snapshot.id, entry=Decimal("60000"), stop=Decimal("59000"), stop_distance=Decimal("1000"), qty=Decimal("0.1"), margin=Decimal("150.0"), risk_amount=Decimal("50.0"), leverage=20))

    # Total margin used in market (OPEN + PARTIAL = $300 + $200 = $500)
    margin_used = await tr_repo.get_total_margin_used(acc.id)
    assert margin_used == Decimal("500.0")
