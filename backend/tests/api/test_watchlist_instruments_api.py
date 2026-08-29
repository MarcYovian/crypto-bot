"""Comprehensive API integration test suite for Watchlist and Market Instruments endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import (
    Exchange,
    TradingAccount,
    Instrument,
    InstrumentLeverageBracket,
    Watchlist,
)
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.utils.security import get_password_hash
from src.utils.cache import in_memory_cache
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_client():
    """Create a fully isolated in-memory database and FastAPI TestClient."""
    await in_memory_cache.clear()

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    app = create_app()

    async def override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Seed test dataset
    async with session_factory() as session:
        # 1. Admin User & Viewer User
        user_repo = UserRepository(session)
        await user_repo.create_user(
            username="admin",
            password_hash=get_password_hash("AdminPass123!"),
            role="ADMIN",
            is_active=True,
        )
        await user_repo.create_user(
            username="viewer",
            password_hash=get_password_hash("ViewerPass123!"),
            role="VIEWER",
            is_active=True,
        )

        # 2. Exchange & Trading Account
        exchange = Exchange(id=1, code="BINANCE", name="Binance Futures", status=True)
        session.add(exchange)
        await session.flush()

        account = TradingAccount(
            id=1,
            exchange_id=1,
            name="Main Futures",
            account_type="FUTURES",
            environment="MAINNET",
            is_active=True,
        )
        session.add(account)
        await session.flush()

        # 3. Instruments
        btc = Instrument(
            id=1,
            exchange_id=1,
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.10"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=3,
            is_active=True,
        )
        eth = Instrument(
            id=2,
            exchange_id=1,
            symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            step_size=Decimal("0.01"),
            min_qty=Decimal("0.01"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=2,
            is_active=True,
        )
        session.add_all([btc, eth])
        await session.flush()

        # 4. Leverage Brackets
        b1 = InstrumentLeverageBracket(
            id=1,
            instrument_id=1,
            bracket=1,
            initial_leverage=125,
            notional_cap=Decimal("50000.0"),
            notional_floor=Decimal("0.0"),
            maint_margin_ratio=Decimal("0.004"),
            cum=Decimal("0.0"),
        )
        b2 = InstrumentLeverageBracket(
            id=2,
            instrument_id=2,
            bracket=1,
            initial_leverage=100,
            notional_cap=Decimal("25000.0"),
            notional_floor=Decimal("0.0"),
            maint_margin_ratio=Decimal("0.005"),
            cum=Decimal("0.0"),
        )
        session.add_all([b1, b2])
        await session.flush()

        # 5. Watchlist
        wl1 = Watchlist(id=1, instrument_id=1, enabled=True)
        wl2 = Watchlist(id=2, instrument_id=2, enabled=True)
        session.add_all([wl1, wl2])
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

    await engine.dispose()


async def get_admin_token(client: AsyncClient) -> str:
    """Helper to authenticate and retrieve access token for admin."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminPass123!"},
    )
    return res.json()["access_token"]


async def get_viewer_token(client: AsyncClient) -> str:
    """Helper to authenticate and retrieve access token for viewer."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": "ViewerPass123!"},
    )
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_get_watchlist_success(app_and_client: AsyncClient):
    """Test retrieving active whitelist coin pairs."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 2

    btc_item = next((x for x in data if x["symbol"] == "BTCUSDT"), None)
    assert btc_item is not None
    assert btc_item["enabled"] is True
    assert btc_item["max_leverage"] == 125
    assert btc_item["tick_size"] == 0.10
    assert btc_item["min_qty"] == 0.001

    eth_item = next((x for x in data if x["symbol"] == "ETHUSDT"), None)
    assert eth_item is not None
    assert eth_item["enabled"] is True
    assert eth_item["max_leverage"] == 100
    assert eth_item["tick_size"] == 0.01
    assert eth_item["min_qty"] == 0.01


@pytest.mark.asyncio
async def test_toggle_watchlist_disable_and_enable(app_and_client: AsyncClient):
    """Test disabling a coin pair in the watchlist, and re-enabling it."""
    client = app_and_client
    token = await get_admin_token(client)

    # 1. Disable BTCUSDT
    res = await client.post(
        "/api/v1/watchlist/toggle",
        headers={"Authorization": f"Bearer {token}"},
        json={"symbol": "BTCUSDT", "enabled": False},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["enabled"] is False

    # Verify via GET
    get_res = await client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    btc = next(x for x in get_res.json() if x["symbol"] == "BTCUSDT")
    assert btc["enabled"] is False

    # 2. Re-enable BTCUSDT
    res2 = await client.post(
        "/api/v1/watchlist/toggle",
        headers={"Authorization": f"Bearer {token}"},
        json={"symbol": "BTCUSDT", "enabled": True},
    )
    assert res2.status_code == 200
    assert res2.json()["enabled"] is True


@pytest.mark.asyncio
async def test_toggle_watchlist_new_symbol_on_demand(app_and_client: AsyncClient):
    """Test toggling a new symbol not yet stored in DB via Binance on-demand resolution."""
    client = app_and_client
    token = await get_admin_token(client)

    mock_metadata = [
        {
            "symbol": "SOLUSDT",
            "base_asset": "SOL",
            "quote_asset": "USDT",
            "tick_size": "0.001",
            "step_size": "0.01",
            "min_qty": "0.01",
            "min_notional": "5.0",
            "price_precision": 3,
            "qty_precision": 2,
        }
    ]
    mock_brackets = [
        {
            "symbol": "SOLUSDT",
            "brackets": [
                {
                    "bracket": 1,
                    "initialLeverage": 50,
                    "notionalCap": 10000,
                    "notionalFloor": 0,
                    "maintMarginRatio": 0.01,
                    "cum": 0,
                }
            ],
        }
    ]

    with patch(
        "src.infrastructure.gateways.binance.binance_adapter.BinanceExchangeAdapter.fetch_instruments_metadata",
        new_callable=AsyncMock,
        return_value=mock_metadata,
    ), patch(
        "src.infrastructure.gateways.binance.binance_adapter.BinanceExchangeAdapter.fetch_leverage_brackets",
        new_callable=AsyncMock,
        return_value=mock_brackets,
    ):

        res = await client.post(
            "/api/v1/watchlist/toggle",
            headers={"Authorization": f"Bearer {token}"},
            json={"symbol": "SOLUSDT", "enabled": True},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["symbol"] == "SOLUSDT"
        assert data["enabled"] is True
        assert data["max_leverage"] == 50
        assert data["tick_size"] == 0.001


@pytest.mark.asyncio
async def test_toggle_watchlist_invalid_symbol(app_and_client: AsyncClient):
    """Test toggling an invalid coin pair returns 400 Bad Request."""
    client = app_and_client
    token = await get_admin_token(client)

    with patch(
        "src.infrastructure.gateways.binance.binance_adapter.BinanceExchangeAdapter.fetch_instruments_metadata",
        new_callable=AsyncMock,
        return_value=[],
    ):

        res = await client.post(
            "/api/v1/watchlist/toggle",
            headers={"Authorization": f"Bearer {token}"},
            json={"symbol": "NONEXISTENT999", "enabled": True},
        )
        assert res.status_code == 400
        assert "not a valid active USDT contract" in res.json()["detail"]


@pytest.mark.asyncio
async def test_toggle_watchlist_missing_parameters(app_and_client: AsyncClient):
    """Test validation errors when missing mandatory fields in toggle request."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/watchlist/toggle",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_get_instruments_list_success(app_and_client: AsyncClient):
    """Test retrieving all synced Binance Futures instrument specifications."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/instruments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 2

    btc = next(x for x in data if x["symbol"] == "BTCUSDT")
    assert btc["base_asset"] == "BTC"
    assert btc["quote_asset"] == "USDT"
    assert btc["price_precision"] == 2
    assert btc["qty_precision"] == 3
    assert btc["tick_size"] == 0.10
    assert btc["step_size"] == 0.001
    assert btc["min_notional"] == 5.0
    assert btc["max_leverage"] == 125


@pytest.mark.asyncio
async def test_sync_instruments_from_exchange_success(app_and_client: AsyncClient):
    """Test manual on-demand sync of Binance exchange metadata and leverage brackets."""
    client = app_and_client
    token = await get_admin_token(client)

    mock_metadata = [
        {
            "symbol": "BTCUSDT",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "tick_size": "0.10",
            "step_size": "0.001",
            "min_qty": "0.001",
            "min_notional": "5.0",
            "price_precision": 2,
            "qty_precision": 3,
        },
        {
            "symbol": "ETHUSDT",
            "base_asset": "ETH",
            "quote_asset": "USDT",
            "tick_size": "0.01",
            "step_size": "0.01",
            "min_qty": "0.01",
            "min_notional": "5.0",
            "price_precision": 2,
            "qty_precision": 2,
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
    ]
    mock_brackets = [
        {
            "symbol": "BTCUSDT",
            "brackets": [
                {
                    "bracket": 1,
                    "initialLeverage": 125,
                    "notionalCap": 50000,
                    "notionalFloor": 0,
                    "maintMarginRatio": 0.004,
                    "cum": 0,
                }
            ],
        },
        {
            "symbol": "ETHUSDT",
            "brackets": [
                {
                    "bracket": 1,
                    "initialLeverage": 100,
                    "notionalCap": 25000,
                    "notionalFloor": 0,
                    "maintMarginRatio": 0.005,
                    "cum": 0,
                }
            ],
        },
        {
            "symbol": "BNBUSDT",
            "brackets": [
                {
                    "bracket": 1,
                    "initialLeverage": 75,
                    "notionalCap": 10000,
                    "notionalFloor": 0,
                    "maintMarginRatio": 0.01,
                    "cum": 0,
                }
            ],
        },
    ]

    with patch(
        "src.infrastructure.gateways.binance.binance_adapter.BinanceExchangeAdapter.fetch_instruments_metadata",
        new_callable=AsyncMock,
        return_value=mock_metadata,
    ), patch(
        "src.infrastructure.gateways.binance.binance_adapter.BinanceExchangeAdapter.fetch_leverage_brackets",
        new_callable=AsyncMock,
        return_value=mock_brackets,
    ):

        res = await client.post(
            "/api/v1/instruments/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["synced_instruments"] == 3
        assert data["synced_brackets"] == 3
        assert "timestamp" in data


@pytest.mark.asyncio
async def test_watchlist_unauthorized_rejection(app_and_client: AsyncClient):
    """Test that unauthorized requests to watchlist endpoints are rejected with 401."""
    client = app_and_client

    res_get = await client.get("/api/v1/watchlist")
    assert res_get.status_code == 401

    res_post = await client.post(
        "/api/v1/watchlist/toggle",
        json={"symbol": "BTCUSDT", "enabled": False},
    )
    assert res_post.status_code == 401


@pytest.mark.asyncio
async def test_instruments_unauthorized_rejection(app_and_client: AsyncClient):
    """Test that unauthorized requests to instruments endpoints are rejected with 401."""
    client = app_and_client

    res_get = await client.get("/api/v1/instruments")
    assert res_get.status_code == 401

    res_post = await client.post("/api/v1/instruments/sync")
    assert res_post.status_code == 401


@pytest.mark.asyncio
async def test_watchlist_cache_and_write_through_invalidation(app_and_client: AsyncClient):
    """Test that GET /watchlist is cached in memory and invalidated upon toggle."""
    client = app_and_client
    token = await get_admin_token(client)

    # 1. First fetch -> cache miss
    res1 = await client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    assert await in_memory_cache.get("watchlist:all") is not None

    # 2. Toggle symbol -> invalidates cache
    res_toggle = await client.post(
        "/api/v1/watchlist/toggle",
        headers={"Authorization": f"Bearer {token}"},
        json={"symbol": "BTCUSDT", "enabled": False},
    )
    assert res_toggle.status_code == 200
    assert await in_memory_cache.get("watchlist:all") is None

    # 3. Next GET -> reads fresh state and repopulates cache
    res2 = await client.get(
        "/api/v1/watchlist",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200
    btc = next(x for x in res2.json() if x["symbol"] == "BTCUSDT")
    assert btc["enabled"] is False
    assert await in_memory_cache.get("watchlist:all") is not None


@pytest.mark.asyncio
async def test_instruments_30m_caching_and_sync_invalidation(app_and_client: AsyncClient):
    """Test that GET /instruments is cached with TTL and invalidated on /instruments/sync."""
    client = app_and_client
    token = await get_admin_token(client)

    # 1. Fetch instruments -> cache populated
    res1 = await client.get(
        "/api/v1/instruments",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    assert await in_memory_cache.get("instruments:all") is not None

    # 2. Sync instruments -> invalidates cache
    with patch(
        "src.infrastructure.gateways.binance.binance_adapter.BinanceExchangeAdapter.fetch_instruments_metadata",
        new_callable=AsyncMock,
        return_value=[],
    ):

        sync_res = await client.post(
            "/api/v1/instruments/sync",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert sync_res.status_code == 200
        assert await in_memory_cache.get("instruments:all") is None
