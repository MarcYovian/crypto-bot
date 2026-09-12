"""Tests for InstrumentService: Dynamic symbol synchronization, leverage brackets upsert, and watchlist enrollment."""

import pytest
import pytest_asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, Instrument, Watchlist, InstrumentLeverageBracket
from src.infrastructure.persistence.repositories.exchange_repository import ExchangeRepository
from src.infrastructure.persistence.repositories.instrument_repository import InstrumentRepository
from src.infrastructure.persistence.repositories.instrument_leverage_bracket_repository import InstrumentLeverageBracketRepository
from src.infrastructure.persistence.repositories.watchlist_repository import WatchlistRepository
from src.application.use_cases.instruments.sync_instruments_use_case import SyncInstrumentsUseCase as InstrumentService
from src.domain.ports.gateways import IExchangeGateway


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def inst_env(async_session: AsyncSession):
    exchange = Exchange(code="BINANCE", name="Binance Futures", status=True)
    async_session.add(exchange)
    await async_session.flush()

    existing_inst = Instrument(
        exchange_id=exchange.id, symbol="BTCUSDT", base_asset="BTC", quote_asset="USDT",
        min_qty=Decimal("0.001"), step_size=Decimal("0.001"),
        tick_size=Decimal("0.10"), price_precision=2, qty_precision=3, min_notional=Decimal("5.0"), is_active=True
    )
    async_session.add(existing_inst)
    await async_session.commit()
    await async_session.refresh(existing_inst)

    return {"exchange": exchange, "existing_inst": existing_inst}


@pytest.mark.asyncio
async def test_get_or_sync_instrument_existing(async_session: AsyncSession, inst_env: dict):
    """Test get_or_sync_instrument when instrument already exists in DB."""
    env = inst_env
    inst_repo = InstrumentRepository(async_session)
    bracket_repo = InstrumentLeverageBracketRepository(async_session)
    watch_repo = WatchlistRepository(async_session)

    mock_binance = AsyncMock(spec=IExchangeGateway)
    mock_binance.fetch_leverage_brackets = AsyncMock(return_value=[
        {
            "symbol": "BTCUSDT",
            "brackets": [
                {"bracket": 1, "initialLeverage": 125, "notionalCap": 50000, "maintMarginRatio": 0.004}
            ]
        }
    ])

    service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ExchangeRepository(async_session),
        watchlist_repo=watch_repo,
        bracket_repo=bracket_repo,
        exchange_gateway=mock_binance,
    )

    inst = await service.get_or_sync_instrument("BTCUSDT")
    assert inst is not None
    assert inst.symbol == "BTCUSDT"

    # Check watchlist is enabled
    watch = await watch_repo.get_by_instrument_id(inst.id)
    assert watch is not None
    assert watch.enabled is True

    # Check bracket is saved
    brackets = await bracket_repo.get_brackets_by_instrument(inst.id)
    assert len(brackets) == 1
    assert brackets[0].initial_leverage == 125


@pytest.mark.asyncio
async def test_get_or_sync_instrument_on_demand_new(async_session: AsyncSession, inst_env: dict):
    """Test on-demand sync from Binance for a new symbol not in DB (e.g. SOLUSDT)."""
    env = inst_env
    inst_repo = InstrumentRepository(async_session)
    bracket_repo = InstrumentLeverageBracketRepository(async_session)
    watch_repo = WatchlistRepository(async_session)

    mock_binance = AsyncMock(spec=IExchangeGateway)
    mock_binance.fetch_instruments_metadata = AsyncMock(return_value=[
        {
            "symbol": "SOLUSDT",
            "base_asset": "SOL",
            "quote_asset": "USDT",
            "tick_size": "0.01",
            "step_size": "0.01",
            "min_qty": "0.01",
            "min_notional": "5.0",
            "price_precision": 2,
            "qty_precision": 2,
        }
    ])
    mock_binance.fetch_leverage_brackets = AsyncMock(return_value=[
        {
            "symbol": "SOLUSDT",
            "brackets": [
                {"bracket": 1, "initialLeverage": 50, "notionalCap": 20000, "maintMarginRatio": 0.01}
            ]
        }
    ])

    service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ExchangeRepository(async_session),
        watchlist_repo=watch_repo,
        bracket_repo=bracket_repo,
        exchange_gateway=mock_binance,
    )

    inst = await service.get_or_sync_instrument("SOLUSDT")
    assert inst is not None
    assert inst.symbol == "SOLUSDT"
    assert inst.price_precision == 2
    assert inst.qty_precision == 2

    # Check brackets
    brackets = await bracket_repo.get_brackets_by_instrument(inst.id)
    assert len(brackets) == 1
    assert brackets[0].initial_leverage == 50


@pytest.mark.asyncio
async def test_get_or_sync_instrument_invalid_symbol(async_session: AsyncSession, inst_env: dict):
    """Test get_or_sync_instrument with an invalid/delisted pair."""
    inst_repo = InstrumentRepository(async_session)
    mock_binance = AsyncMock(spec=IExchangeGateway)
    mock_binance.fetch_instruments_metadata = AsyncMock(return_value=[])

    service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ExchangeRepository(async_session),
        exchange_gateway=mock_binance,
    )

    inst = await service.get_or_sync_instrument("FAKECOINUSDT")
    assert inst is None


@pytest.mark.asyncio
async def test_sync_all_instruments_bulk(async_session: AsyncSession, inst_env: dict):
    """Test bulk syncing all Binance instruments and their leverage brackets."""
    inst_repo = InstrumentRepository(async_session)
    bracket_repo = InstrumentLeverageBracketRepository(async_session)
    watch_repo = WatchlistRepository(async_session)

    mock_binance = AsyncMock(spec=IExchangeGateway)
    mock_binance.fetch_instruments_metadata = AsyncMock(return_value=[
        {
            "symbol": "ETHUSDT",
            "base_asset": "ETH",
            "quote_asset": "USDT",
            "tick_size": "0.01",
            "step_size": "0.001",
            "min_qty": "0.001",
            "min_notional": "5.0",
            "price_precision": 2,
            "qty_precision": 3,
        },
        {
            "symbol": "BNBUSDT",
            "base_asset": "BNB",
            "quote_asset": "USDT",
            "tick_size": "0.01",
            "step_size": "0.01",
            "min_qty": "0.01",
            "min_notional": "5.0",
            "price_precision": 2,
            "qty_precision": 2,
        },
    ])
    mock_binance.fetch_leverage_brackets = AsyncMock(return_value=[
        {"symbol": "ETHUSDT", "brackets": [{"bracket": 1, "initialLeverage": 100, "notionalCap": 50000, "maintMarginRatio": 0.005}]},
        {"symbol": "BNBUSDT", "brackets": [{"bracket": 1, "initialLeverage": 50, "notionalCap": 20000, "maintMarginRatio": 0.01}]},
    ])

    service = InstrumentService(
        instrument_repo=inst_repo,
        exchange_repo=ExchangeRepository(async_session),
        watchlist_repo=watch_repo,
        bracket_repo=bracket_repo,
        exchange_gateway=mock_binance,
    )

    count = await service.sync_all_instruments()
    assert count == 2

    eth = await inst_repo.get_by_symbol("ETHUSDT")
    assert eth is not None
    eth_brackets = await bracket_repo.get_brackets_by_instrument(eth.id)
    assert len(eth_brackets) == 1
    assert eth_brackets[0].initial_leverage == 100
