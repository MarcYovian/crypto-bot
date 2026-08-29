"""Unit tests for ExchangeRepository."""

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange
from src.presentation.api.schemas.master import ExchangeCreate
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository

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
async def test_exchange_create_and_get_by_code(async_session: AsyncSession):
    """Test creating an exchange and fetching via case-insensitive code search."""
    repo = ExchangeRepository(async_session)

    created = await repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))
    assert created.id is not None
    assert created.code == "BINANCE"

    # Fetch with lowercase input
    fetched = await repo.get_by_code("binance")
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.name == "Binance Futures"


@pytest.mark.asyncio
async def test_exchange_duplicate_code_handling(async_session: AsyncSession):
    """Test that creating duplicate exchange codes raises IntegrityError."""
    repo = ExchangeRepository(async_session)

    await repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))

    with pytest.raises(IntegrityError):
        await repo.create(ExchangeCreate(code="BINANCE", name="Binance Spot", status=True))


@pytest.mark.asyncio
async def test_exchange_get_active_exchanges(async_session: AsyncSession):
    """Test retrieving only active exchanges."""
    repo = ExchangeRepository(async_session)

    await repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    await repo.create(ExchangeCreate(code="BYBIT", name="Bybit", status=False))
    await repo.create(ExchangeCreate(code="OKX", name="OKX", status=True))

    active_list = await repo.get_active_exchanges()
    assert len(active_list) == 2
    active_codes = {ex.code for ex in active_list}
    assert active_codes == {"BINANCE", "OKX"}


@pytest.mark.asyncio
async def test_exchange_toggle_status(async_session: AsyncSession):
    """Test toggling exchange status on and off."""
    repo = ExchangeRepository(async_session)

    created = await repo.create(ExchangeCreate(code="KUCOIN", name="KuCoin", status=True))
    assert created.status is True

    # Disable
    updated = await repo.toggle_status(created.id, False)
    assert updated is not None
    assert updated.status is False

    # Re-enable
    updated_again = await repo.toggle_status(created.id, True)
    assert updated_again is not None
    assert updated_again.status is True

    # Non-existing ID
    assert await repo.toggle_status(9999, False) is None
