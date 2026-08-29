"""Unit tests for Generic BaseRepository."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange
from src.presentation.api.schemas.master import ExchangeCreate, ExchangeUpdate
from src.infrastructure.persistence.repositories.base import BaseRepository

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
async def test_base_repo_create_and_get(async_session: AsyncSession):
    """Test creating a record via BaseRepository and fetching it by ID."""
    repo = BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate](Exchange, async_session)

    # 1. Create with Pydantic Schema
    create_schema = ExchangeCreate(code="BINANCE", name="Binance Futures", status=True)
    created = await repo.create(create_schema)

    assert created.id is not None
    assert created.code == "BINANCE"
    assert created.name == "Binance Futures"
    assert created.status is True

    # 2. Get by ID
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.code == "BINANCE"


@pytest.mark.asyncio
async def test_base_repo_get_multi_pagination(async_session: AsyncSession):
    """Test pagination using skip and limit in BaseRepository."""
    repo = BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate](Exchange, async_session)

    # Insert 5 records
    for i in range(1, 6):
        await repo.create(ExchangeCreate(code=f"EX_{i}", name=f"Exchange {i}", status=True))

    # Fetch page 2 (skip 2, limit 2)
    page = await repo.get_multi(skip=2, limit=2)
    assert len(page) == 2
    assert page[0].code == "EX_3"
    assert page[1].code == "EX_4"


@pytest.mark.asyncio
async def test_base_repo_update_with_schema_and_dict(async_session: AsyncSession):
    """Test updating existing records using both Pydantic schema and raw dict."""
    repo = BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate](Exchange, async_session)

    created = await repo.create(ExchangeCreate(code="BYBIT", name="Bybit Global", status=True))

    # Update with Schema
    update_schema = ExchangeUpdate(name="Bybit Pro", status=False)
    updated = await repo.update(created, update_schema)

    assert updated.name == "Bybit Pro"
    assert updated.status is False

    # Update with Dict
    updated_dict = await repo.update(created, {"name": "Bybit Enterprise"})
    assert updated_dict.name == "Bybit Enterprise"
    assert updated_dict.status is False


@pytest.mark.asyncio
async def test_base_repo_delete(async_session: AsyncSession):
    """Test deleting records and ensuring get returns None."""
    repo = BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate](Exchange, async_session)

    created = await repo.create(ExchangeCreate(code="OKX", name="OKX Exchange", status=True))
    record_id = created.id

    # Delete existing
    deleted = await repo.delete(record_id)
    assert deleted is True

    # Confirm it no longer exists
    assert await repo.get(record_id) is None

    # Delete non-existing ID
    assert await repo.delete(99999) is False


@pytest.mark.asyncio
async def test_base_repo_count(async_session: AsyncSession):
    """Test total row count calculation."""
    repo = BaseRepository[Exchange, ExchangeCreate, ExchangeUpdate](Exchange, async_session)

    assert await repo.count() == 0

    await repo.create(ExchangeCreate(code="EX_A", name="Exchange A", status=True))
    await repo.create(ExchangeCreate(code="EX_B", name="Exchange B", status=True))

    assert await repo.count() == 2
