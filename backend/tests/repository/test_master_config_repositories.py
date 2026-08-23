"""Unit tests for Strategy, SignalProvider, and RiskProfile repositories."""

from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.database.connection import Base
from src.schemas.master import StrategyCreate, SignalProviderCreate, RiskProfileCreate
from src.repository.strategy_repository import StrategyRepository
from src.repository.signal_provider_repository import SignalProviderRepository
from src.repository.risk_profile_repository import RiskProfileRepository

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
async def test_strategy_create_and_get_by_name(async_session: AsyncSession):
    """Test creating a strategy and querying via case-insensitive name."""
    repo = StrategyRepository(async_session)

    strat = await repo.create(StrategyCreate(
        name="SMC Liquidity Sweep",
        version="1.0.0",
        description="Smart Money Concept strategy",
        is_active=True
    ))

    assert strat.id is not None
    assert strat.name == "SMC Liquidity Sweep"

    # Query with lowercase
    fetched = await repo.get_by_name("smc liquidity sweep")
    assert fetched is not None
    assert fetched.id == strat.id
    assert fetched.version == "1.0.0"


@pytest.mark.asyncio
async def test_signal_provider_filter_by_type(async_session: AsyncSession):
    """Test creating signal providers and filtering by provider type."""
    repo = SignalProviderRepository(async_session)

    await repo.create(SignalProviderCreate(name="VIP Calls 1", type="TELEGRAM", is_active=True))
    await repo.create(SignalProviderCreate(name="VIP Calls 2", type="TELEGRAM", is_active=True))
    await repo.create(SignalProviderCreate(name="TradingView Webhook", type="WEBHOOK", is_active=True))

    tg_providers = await repo.get_by_type("telegram")
    assert len(tg_providers) == 2
    names = {p.name for p in tg_providers}
    assert names == {"VIP Calls 1", "VIP Calls 2"}

    wh_providers = await repo.get_by_type("webhook")
    assert len(wh_providers) == 1
    assert wh_providers[0].name == "TradingView Webhook"


@pytest.mark.asyncio
async def test_risk_profile_get_and_switch_active(async_session: AsyncSession):
    """Test managing risk profiles and switching active profile."""
    repo = RiskProfileRepository(async_session)

    p1 = await repo.create(RiskProfileCreate(
        name="Conservative 1%",
        risk_percent=Decimal("1.0"),
        max_daily_loss=Decimal("3.0"),
        max_open_trade=2,
        is_active=True
    ))

    p2 = await repo.create(RiskProfileCreate(
        name="Moderate 2%",
        risk_percent=Decimal("2.0"),
        max_daily_loss=Decimal("6.0"),
        max_open_trade=3,
        is_active=False
    ))

    # Initial active is p1
    active = await repo.get_active_profile()
    assert active is not None
    assert active.id == p1.id
    assert active.risk_percent == Decimal("1.0")

    # Switch active to p2
    switched = await repo.set_active_profile(p2.id)
    assert switched is not None
    assert switched.id == p2.id
    assert switched.is_active is True

    # Confirm p1 is deactivated and p2 is current active
    current_active = await repo.get_active_profile()
    assert current_active is not None
    assert current_active.id == p2.id
    assert current_active.risk_percent == Decimal("2.0")
