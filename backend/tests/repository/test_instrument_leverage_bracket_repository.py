"""Unit tests for InstrumentLeverageBracketRepository."""

from decimal import Decimal
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.infrastructure.persistence.connection import Base
from src.presentation.api.schemas.master import (
    ExchangeCreate,
    InstrumentCreate,
    InstrumentLeverageBracketCreate,
)
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.instrument_leverage_bracket_repository import (
    InstrumentLeverageBracketRepository,
)

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
async def test_bracket_bulk_upsert_and_queries(async_session: AsyncSession):
    """Test bulk upserting brackets, ordering, and notional matching."""
    ex_repo = ExchangeRepository(async_session)
    inst_repo = InstrumentRepository(async_session)
    bracket_repo = InstrumentLeverageBracketRepository(async_session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance", status=True))
    inst = await inst_repo.create(
        InstrumentCreate(
            exchange_id=exchange.id,
            symbol="AAVEUSDT",
            base_asset="AAVE",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.1"),
            min_qty=Decimal("0.1"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=1,
            is_active=True,
        )
    )

    brackets_payload = [
        InstrumentLeverageBracketCreate(
            instrument_id=inst.id,
            bracket=1,
            initial_leverage=50,
            notional_floor=Decimal("0"),
            notional_cap=Decimal("5000"),
            maint_margin_ratio=Decimal("0.015"),
            cum=Decimal("0.0"),
        ),
        InstrumentLeverageBracketCreate(
            instrument_id=inst.id,
            bracket=2,
            initial_leverage=20,
            notional_floor=Decimal("5000"),
            notional_cap=Decimal("25000"),
            maint_margin_ratio=Decimal("0.025"),
            cum=Decimal("50.0"),
        ),
        InstrumentLeverageBracketCreate(
            instrument_id=inst.id,
            bracket=3,
            initial_leverage=15,
            notional_floor=Decimal("25000"),
            notional_cap=Decimal("100000"),
            maint_margin_ratio=Decimal("0.03"),
            cum=Decimal("175.0"),
        ),
    ]

    # 1. Bulk upsert
    count = await bracket_repo.bulk_upsert_brackets(inst.id, brackets_payload)
    assert count == 3

    # 2. Get all brackets ordered
    all_brackets = await bracket_repo.get_brackets_by_instrument(inst.id)
    assert len(all_brackets) == 3
    assert all_brackets[0].bracket == 1
    assert all_brackets[0].initial_leverage == 50
    assert all_brackets[1].bracket == 2
    assert all_brackets[1].initial_leverage == 20

    # 3. Max leverage query
    max_lev = await bracket_repo.get_max_leverage_for_symbol(inst.id)
    assert max_lev == 50

    # 4. Bracket matching for small notional ($2,000 USDT) -> Bracket 1 (50x)
    b1 = await bracket_repo.get_bracket_for_notional(inst.id, Decimal("2000.0"))
    assert b1 is not None
    assert b1.bracket == 1
    assert b1.initial_leverage == 50
    assert b1.maint_margin_ratio == Decimal("0.015")

    # 5. Bracket matching for medium notional ($12,000 USDT) -> Bracket 2 (20x)
    b2 = await bracket_repo.get_bracket_for_notional(inst.id, Decimal("12000.0"))
    assert b2 is not None
    assert b2.bracket == 2
    assert b2.initial_leverage == 20
    assert b2.maint_margin_ratio == Decimal("0.025")

    # 6. Fallback matching for huge notional exceeding max cap ($500,000 USDT) -> Bracket 3 (15x)
    b3 = await bracket_repo.get_bracket_for_notional(inst.id, Decimal("500000.0"))
    assert b3 is not None
    assert b3.bracket == 3
    assert b3.initial_leverage == 15

    # 7. Upsert update existing bracket (Bracket 1 initial_leverage changed to 75)
    updated_payload = [
        InstrumentLeverageBracketCreate(
            instrument_id=inst.id,
            bracket=1,
            initial_leverage=75,
            notional_floor=Decimal("0"),
            notional_cap=Decimal("5000"),
            maint_margin_ratio=Decimal("0.01"),
            cum=Decimal("0.0"),
        )
    ]
    await bracket_repo.bulk_upsert_brackets(inst.id, updated_payload)
    b1_updated = await bracket_repo.get_bracket_for_notional(inst.id, Decimal("1000.0"))
    assert b1_updated.initial_leverage == 75

    # 8. Delete brackets
    del_count = await bracket_repo.delete_brackets_by_instrument(inst.id)
    assert del_count == 3
    remaining = await bracket_repo.get_brackets_by_instrument(inst.id)
    assert len(remaining) == 0
