"""Unit tests for InstrumentService (symbol resolution, live Binance metadata sync, and watchlist management)."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from src.database.connection import Base
from src.schemas.master import ExchangeCreate, InstrumentCreate
from src.repository.exchange_repository import ExchangeRepository
from src.repository.instrument_repository import InstrumentRepository
from src.repository.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.repository.watchlist_repository import WatchlistRepository
from src.services.instrument_service import InstrumentService
from src.clients.binance_client import BinanceRestClient

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def session():
    """Create fresh isolated SQLite database session."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as sess:
        yield sess

    await engine.dispose()


@pytest.mark.asyncio
async def test_get_or_sync_instrument_existing_in_db(session: AsyncSession):
    """Test retrieving instrument when it already exists in database."""
    ex_repo = ExchangeRepository(session)
    inst_repo = InstrumentRepository(session)
    watch_repo = WatchlistRepository(session)

    exchange = await ex_repo.create(ExchangeCreate(code="BINANCE", name="Binance Futures", status=True))
    created_inst = await inst_repo.create(
        InstrumentCreate(
            exchange_id=exchange.id,
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.1"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5.0"),
            price_precision=1,
            qty_precision=3,
            is_active=True,
        )
    )

    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ex_repo,
        watchlist_repo=watch_repo,
        binance_client=None,
    )

    res = await inst_service.get_or_sync_instrument("BTCUSDT")
    assert res is not None
    assert res.id == created_inst.id
    assert res.symbol == "BTCUSDT"

    # Verify enabled in watchlist
    is_enabled = await watch_repo.is_symbol_enabled("BTCUSDT")
    assert is_enabled is True


@pytest.mark.asyncio
async def test_get_or_sync_instrument_dynamic_fetch_from_binance(session: AsyncSession):
    """Test dynamic on-demand sync from Binance when symbol is missing in DB."""
    ex_repo = ExchangeRepository(session)
    inst_repo = InstrumentRepository(session)
    watch_repo = WatchlistRepository(session)

    mock_binance = MagicMock(spec=BinanceRestClient)
    mock_binance.fetch_instruments_metadata = AsyncMock(
        return_value=[
            {
                "symbol": "AAVEUSDT",
                "base_asset": "AAVE",
                "quote_asset": "USDT",
                "price_precision": 3,
                "qty_precision": 1,
                "tick_size": Decimal("0.001"),
                "step_size": Decimal("0.1"),
                "min_qty": Decimal("0.1"),
                "min_notional": Decimal("5.0"),
                "is_active": True,
            }
        ]
    )

    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ex_repo,
        watchlist_repo=watch_repo,
        binance_client=mock_binance,
    )

    # AAVEUSDT not in database yet
    db_check = await inst_repo.get_by_symbol("AAVEUSDT")
    assert db_check is None

    res = await inst_service.get_or_sync_instrument("AAVEUSDT")
    assert res is not None
    assert res.symbol == "AAVEUSDT"
    assert res.tick_size == Decimal("0.001")
    assert res.price_precision == 3

    mock_binance.fetch_instruments_metadata.assert_called_once()

    # Verify persisted in database
    persisted = await inst_repo.get_by_symbol("AAVEUSDT")
    assert persisted is not None
    assert persisted.id == res.id

    # Verify added to watchlist
    is_enabled = await watch_repo.is_symbol_enabled("AAVEUSDT")
    assert is_enabled is True


@pytest.mark.asyncio
async def test_get_or_sync_instrument_invalid_symbol_returns_none(session: AsyncSession):
    """Test that an unrecognized/invalid symbol on Binance returns None safely."""
    ex_repo = ExchangeRepository(session)
    inst_repo = InstrumentRepository(session)
    watch_repo = WatchlistRepository(session)

    mock_binance = MagicMock(spec=BinanceRestClient)
    mock_binance.fetch_instruments_metadata = AsyncMock(
        return_value=[
            {
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
            }
        ]
    )

    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ex_repo,
        watchlist_repo=watch_repo,
        binance_client=mock_binance,
    )

    res = await inst_service.get_or_sync_instrument("NONEXISTENTCOIN")
    assert res is None


@pytest.mark.asyncio
async def test_sync_all_instruments(session: AsyncSession):
    """Test bulk syncing all Binance USDT perpetual instruments."""
    ex_repo = ExchangeRepository(session)
    inst_repo = InstrumentRepository(session)
    watch_repo = WatchlistRepository(session)

    mock_binance = MagicMock(spec=BinanceRestClient)
    mock_binance.fetch_instruments_metadata = AsyncMock(
        return_value=[
            {
                "symbol": "BTCUSDT",
                "base_asset": "BTC",
                "quote_asset": "USDT",
                "price_precision": 1,
                "qty_precision": 3,
                "tick_size": Decimal("0.1"),
                "step_size": Decimal("0.001"),
                "min_qty": Decimal("0.001"),
                "min_notional": Decimal("5.0"),
            },
            {
                "symbol": "ETHUSDT",
                "base_asset": "ETH",
                "quote_asset": "USDT",
                "price_precision": 2,
                "qty_precision": 3,
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("0.001"),
                "min_qty": Decimal("0.001"),
                "min_notional": Decimal("5.0"),
            },
        ]
    )

    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ex_repo,
        watchlist_repo=watch_repo,
        binance_client=mock_binance,
    )

    count = await inst_service.sync_all_instruments()
    assert count == 2

    # Verify both in database and watchlist
    assert await inst_repo.get_by_symbol("BTCUSDT") is not None
    assert await inst_repo.get_by_symbol("ETHUSDT") is not None
    assert await watch_repo.is_symbol_enabled("BTCUSDT") is True
    assert await watch_repo.is_symbol_enabled("ETHUSDT") is True


@pytest.mark.asyncio
async def test_get_or_sync_instrument_syncs_leverage_brackets(session: AsyncSession):
    """Test that leverage brackets are automatically fetched and stored on-demand."""
    ex_repo = ExchangeRepository(session)
    inst_repo = InstrumentRepository(session)
    watch_repo = WatchlistRepository(session)
    bracket_repo = InstrumentLeverageBracketRepository(session)

    mock_binance = MagicMock(spec=BinanceRestClient)
    mock_binance.fetch_instruments_metadata = AsyncMock(
        return_value=[
            {
                "symbol": "SOLUSDT",
                "base_asset": "SOL",
                "quote_asset": "USDT",
                "price_precision": 2,
                "qty_precision": 2,
                "tick_size": Decimal("0.01"),
                "step_size": Decimal("0.01"),
                "min_qty": Decimal("0.01"),
                "min_notional": Decimal("5.0"),
            }
        ]
    )
    mock_binance.fetch_leverage_brackets = AsyncMock(
        return_value=[
            {
                "symbol": "SOLUSDT",
                "brackets": [
                    {
                        "bracket": 1,
                        "initial_leverage": 75,
                        "notional_cap": Decimal("5000"),
                        "notional_floor": Decimal("0"),
                        "maint_margin_ratio": Decimal("0.01"),
                        "cum": Decimal("0"),
                    },
                    {
                        "bracket": 2,
                        "initial_leverage": 50,
                        "notional_cap": Decimal("25000"),
                        "notional_floor": Decimal("5000"),
                        "maint_margin_ratio": Decimal("0.02"),
                        "cum": Decimal("50"),
                    },
                ],
            }
        ]
    )

    inst_service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ex_repo,
        watchlist_repo=watch_repo,
        bracket_repo=bracket_repo,
        binance_client=mock_binance,
    )

    inst = await inst_service.get_or_sync_instrument("SOLUSDT")
    assert inst is not None
    assert inst.symbol == "SOLUSDT"

    # Verify brackets saved in database
    brackets = await bracket_repo.get_brackets_by_instrument(inst.id)
    assert len(brackets) == 2
    assert brackets[0].initial_leverage == 75
    assert brackets[0].notional_cap == Decimal("5000")
    assert brackets[1].initial_leverage == 50

