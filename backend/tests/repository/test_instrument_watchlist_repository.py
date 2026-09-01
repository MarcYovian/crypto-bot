"""Unit tests for InstrumentRepository and WatchlistRepository."""

from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, Instrument, Watchlist
from src.presentation.api.schemas.master import ExchangeCreate, InstrumentCreate
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository

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
async def test_instrument_create_and_get_by_symbol(async_session: AsyncSession):
    """Test creating an instrument and fetching metadata by symbol."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)

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

    assert inst.id is not None
    assert inst.symbol == "BTCUSDT"

    # Query with lowercase
    fetched = await inst_repo.get_by_symbol("btcusdt")
    assert fetched is not None
    assert fetched.id == inst.id
    assert fetched.tick_size == Decimal("0.10")
    assert fetched.step_size == Decimal("0.001")


@pytest.mark.asyncio
async def test_watchlist_add_and_is_symbol_enabled(async_session: AsyncSession):
    """Test adding an instrument to watchlist and checking enabled status."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    wl_repo = WatchlistRepository(async_session)

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

    # Add to watchlist
    wl_entry = await wl_repo.set_symbol_enabled(inst.id, enabled=True)
    assert wl_entry.enabled is True

    # Check is_symbol_enabled
    assert await wl_repo.is_symbol_enabled("ETHUSDT") is True
    assert await wl_repo.is_symbol_enabled("ethusdt") is True


@pytest.mark.asyncio
async def test_watchlist_disabled_symbol_check(async_session: AsyncSession):
    """Test that disabled watchlist entries or non-existing pairs return False."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    wl_repo = WatchlistRepository(async_session)

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

    # Set disabled
    await wl_repo.set_symbol_enabled(inst.id, enabled=False)

    assert await wl_repo.is_symbol_enabled("SOLUSDT") is False
    assert await wl_repo.is_symbol_enabled("NONEXISTENTUSDT") is False


@pytest.mark.asyncio
async def test_watchlist_eager_load_instrument(async_session: AsyncSession):
    """Test retrieving enabled watchlist with eagerly loaded Instrument."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    wl_repo = WatchlistRepository(async_session)

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

    await wl_repo.set_symbol_enabled(inst.id, enabled=True)

    items = await wl_repo.get_enabled_watchlist_with_instruments()
    assert len(items) == 1
    assert items[0].instrument is not None
    assert items[0].instrument.symbol == "ADAUSDT"


@pytest.mark.asyncio
async def test_instrument_bulk_upsert(async_session: AsyncSession):
    """Test bulk syncing and updating instruments."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))

    instruments_data = [
        InstrumentCreate(
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
        ),
        InstrumentCreate(
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
        )
    ]

    count = await inst_repo.bulk_upsert_instruments(instruments_data)
    assert count == 2

    # Verify both exist
    btc = await inst_repo.get_by_symbol("BTCUSDT")
    eth = await inst_repo.get_by_symbol("ETHUSDT")
    assert btc is not None
    assert eth is not None
