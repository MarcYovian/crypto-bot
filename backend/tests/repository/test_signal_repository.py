"""Unit tests for SignalRepository."""

from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, Instrument, SignalProvider
from src.presentation.api.schemas.master import ExchangeCreate, InstrumentCreate, SignalProviderCreate
from src.presentation.api.schemas.signal import TradingSignalCreate
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.signal_provider_repository import SignalProviderRepository
from src.infrastructure.persistence.repositories.signal_repository import SignalRepository

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


@pytest.mark.asyncio
async def test_signal_create_and_deduplication_lookup(async_session: AsyncSession):
    """Test creating a signal and retrieving via telegram_message_id for dedup."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    sig_repo = SignalRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    inst = await inst_repo.create(InstrumentCreate(
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
    provider = await prov_repo.create(SignalProviderCreate(name="VIP Calls", type="TELEGRAM", is_active=True))

    # Create signal
    signal_in = TradingSignalCreate(
        provider_id=provider.id,
        instrument_id=inst.id,
        telegram_message_id=998811,
        timeframe="15m",
        side="BUY",
        entry_min=Decimal("60000"),
        entry_max=Decimal("60500"),
        sl_price=Decimal("59000"),
        tp1_price=Decimal("61000"),
        confidence=Decimal("0.85"),
        status="RECEIVED",
        confirmation_status="NOT_REQUIRED"
    )
    created = await sig_repo.create(signal_in)

    assert created.id is not None
    assert created.telegram_message_id == 998811

    # Dedup lookup
    fetched = await sig_repo.get_by_telegram_message_id(998811)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.side == "BUY"


@pytest.mark.asyncio
async def test_signal_has_active_signal_check(async_session: AsyncSession):
    """Test checking for active signal on the same pair and side."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    sig_repo = SignalRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="ETHUSDT",
        base_asset="ETH",
        quote_asset="USDT",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.001"),
        min_qty=Decimal("0.001"),
        min_notional=Decimal("5.0"),
        price_precision=2,
        qty_precision=3,
        is_active=True
    ))
    provider = await prov_repo.create(SignalProviderCreate(name="VIP Calls", type="TELEGRAM", is_active=True))

    assert await sig_repo.has_active_signal(inst.id, "BUY") is False

    await sig_repo.create(TradingSignalCreate(
        provider_id=provider.id,
        instrument_id=inst.id,
        telegram_message_id=12345,
        side="BUY",
        sl_price=Decimal("3000"),
        status="RECEIVED"
    ))

    # Now active exists
    assert await sig_repo.has_active_signal(inst.id, "BUY") is True
    assert await sig_repo.has_active_signal(inst.id, "SELL") is False


@pytest.mark.asyncio
async def test_signal_pending_confirmation_flow(async_session: AsyncSession):
    """Test fetching pending confirmation signals and approving them."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    sig_repo = SignalRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="SOLUSDT",
        base_asset="SOL",
        quote_asset="USDT",
        tick_size=Decimal("0.01"),
        step_size=Decimal("0.01"),
        min_qty=Decimal("0.01"),
        min_notional=Decimal("5.0"),
        price_precision=2,
        qty_precision=2,
        is_active=True
    ))
    provider = await prov_repo.create(SignalProviderCreate(name="VIP Calls", type="TELEGRAM", is_active=True))

    created = await sig_repo.create(TradingSignalCreate(
        provider_id=provider.id,
        instrument_id=inst.id,
        telegram_message_id=55555,
        side="BUY",
        sl_price=Decimal("140"),
        confidence=Decimal("0.60"),
        status="RECEIVED",
        confirmation_status="PENDING"
    ))

    pending_list = await sig_repo.get_pending_confirmation_signals()
    assert len(pending_list) == 1
    assert pending_list[0].id == created.id

    # Approve
    approved = await sig_repo.update_confirmation_status(created.id, "APPROVED")
    assert approved is not None
    assert approved.confirmation_status == "APPROVED"

    # Pending list is now empty
    remaining_pending = await sig_repo.get_pending_confirmation_signals()
    assert len(remaining_pending) == 0


@pytest.mark.asyncio
async def test_signal_lifecycle_transition(async_session: AsyncSession):
    """Test transitioning signal lifecycle from RECEIVED to EXECUTED."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    prov_repo = SignalProviderRepository(async_session)
    sig_repo = SignalRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    inst = await inst_repo.create(InstrumentCreate(
        exchange_id=exchange.id,
        symbol="ADAUSDT",
        base_asset="ADA",
        quote_asset="USDT",
        tick_size=Decimal("0.0001"),
        step_size=Decimal("1.0"),
        min_qty=Decimal("1.0"),
        min_notional=Decimal("5.0"),
        price_precision=4,
        qty_precision=0,
        is_active=True
    ))
    provider = await prov_repo.create(SignalProviderCreate(name="VIP Calls", type="TELEGRAM", is_active=True))

    created = await sig_repo.create(TradingSignalCreate(
        provider_id=provider.id,
        instrument_id=inst.id,
        telegram_message_id=77777,
        side="BUY",
        sl_price=Decimal("0.40"),
        status="RECEIVED"
    ))
    assert created.status == "RECEIVED"

    # Transition to EXECUTED
    updated = await sig_repo.update_status(created.id, "EXECUTED")
    assert updated is not None
    assert updated.status == "EXECUTED"
