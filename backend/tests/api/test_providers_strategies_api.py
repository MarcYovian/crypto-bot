"""Comprehensive API integration test suite for Signal Providers and Strategies endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from src.database.connection import Base
from src.database.models import (
    Exchange,
    TradingAccount,
    Instrument,
    SignalProvider,
    Strategy,
    TradingSignal,
    Trade,
    TradeSummary,
)
from src.repository.user_repository import UserRepository
from src.utils.security import get_password_hash
from src.utils.cache import in_memory_cache
from src.api.app import create_app
from src.api.deps import get_db_session

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
        # 1. Admin & Viewer Users
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

        # 3. Instrument
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
        session.add(btc)
        await session.flush()

        # 4. Signal Providers
        p1 = SignalProvider(
            id=1,
            name="Crypto VIP Signals",
            type="-100123456789",
            is_active=True,
        )
        p2 = SignalProvider(
            id=2,
            name="Empty Channel",
            type="-100999999999",
            is_active=True,
        )
        session.add_all([p1, p2])
        await session.flush()

        # 5. Strategies
        strat1 = Strategy(
            id=1,
            name="Standard 3-Stage TP",
            version="1.0.0",
            description='{"tp1": 50.0, "tp2": 30.0, "tp3": 20.0, "bep": 1, "trailing": 2}',
            is_active=True,
        )
        session.add(strat1)
        await session.flush()

        # 6. Signals and Trades linked to Provider 1 for analytics
        sig1 = TradingSignal(
            id=1,
            provider_id=1,
            instrument_id=1,
            side="BUY",
            sl_price=Decimal("49000.0"),
            status="EXECUTED",
        )
        sig2 = TradingSignal(
            id=2,
            provider_id=1,
            instrument_id=1,
            side="BUY",
            sl_price=Decimal("48000.0"),
            status="EXECUTED",
        )
        session.add_all([sig1, sig2])
        await session.flush()

        trade1 = Trade(
            id=1,
            account_id=1,
            instrument_id=1,
            signal_id=1,
            side="BUY",
            status="CLOSED",
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0.0"),
            sl_price=Decimal("49000.0"),
            leverage=10,
        )
        trade2 = Trade(
            id=2,
            account_id=1,
            instrument_id=1,
            signal_id=2,
            side="BUY",
            status="CLOSED",
            entry_price=Decimal("50000.0"),
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0.0"),
            sl_price=Decimal("48000.0"),
            leverage=10,
        )
        session.add_all([trade1, trade2])
        await session.flush()

        ts1 = TradeSummary(
            trade_id=1,
            result="WIN",
            gross_pnl=Decimal("150.00"),
            net_pnl=Decimal("145.00"),
            commission=Decimal("5.00"),
            roi=Decimal("15.00"),
            rr=Decimal("2.00"),
            duration_seconds=3600,
            close_reason="TP3",
            closed_at=datetime.now(timezone.utc),
        )
        ts2 = TradeSummary(
            trade_id=2,
            result="LOSS",
            gross_pnl=Decimal("-50.00"),
            net_pnl=Decimal("-55.00"),
            commission=Decimal("5.00"),
            roi=Decimal("-5.00"),
            rr=Decimal("-1.00"),
            duration_seconds=1800,
            close_reason="SL",
            closed_at=datetime.now(timezone.utc),
        )
        session.add_all([ts1, ts2])
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
async def test_get_providers_list_success(app_and_client: AsyncClient):
    """Test retrieving list of all configured signal providers."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 2

    p1 = next((x for x in data if x["name"] == "Crypto VIP Signals"), None)
    assert p1 is not None
    assert p1["channel_id"] == "-100123456789"
    assert p1["is_active"] is True
    assert p1["confidence_weight"] == 1.0


@pytest.mark.asyncio
async def test_create_provider_success(app_and_client: AsyncClient):
    """Test creating a new signal provider channel successfully."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "CryptoBull Signals",
            "channel_id": "-100987654321",
            "confidence_weight": 1.2,
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "CryptoBull Signals"
    assert data["channel_id"] == "-100987654321"
    assert data["confidence_weight"] == 1.2

    # Verify listing contains new provider
    list_res = await client.get(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    assert len(list_res.json()) == 3


@pytest.mark.asyncio
async def test_create_provider_duplicate_name(app_and_client: AsyncClient):
    """Test registering a provider with an existing name returns 409 Conflict."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "name": "Crypto VIP Signals",
            "channel_id": "-100111111111",
        },
    )
    assert res.status_code == 409
    assert "already exists" in res.json()["detail"]


@pytest.mark.asyncio
async def test_get_provider_analytics_success(app_and_client: AsyncClient):
    """Test computing financial and execution performance metrics for Provider 1."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/providers/1/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider_id"] == 1
    assert data["provider_name"] == "Crypto VIP Signals"
    assert data["total_signals"] == 2
    assert data["executed_trades"] == 2
    assert data["win_rate"] == 50.0  # 1 win, 1 loss -> 50%
    assert data["total_net_pnl_usdt"] == 90.0  # 145 - 55 = 90.0


@pytest.mark.asyncio
async def test_get_provider_analytics_zero_trades(app_and_client: AsyncClient):
    """Test computing performance metrics for a provider without trades returns zero values."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/providers/2/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["provider_id"] == 2
    assert data["total_signals"] == 0
    assert data["executed_trades"] == 0
    assert data["win_rate"] == 0.0
    assert data["total_net_pnl_usdt"] == 0.0


@pytest.mark.asyncio
async def test_get_provider_analytics_not_found(app_and_client: AsyncClient):
    """Test that requesting analytics for a non-existent provider returns 404."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/providers/999/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


@pytest.mark.asyncio
async def test_get_strategies_list_success(app_and_client: AsyncClient):
    """Test retrieving list of all trading strategies and TP allocation rules."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/strategies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1

    strat = data[0]
    assert strat["name"] == "Standard 3-Stage TP"
    assert len(strat["tp_allocations"]) == 3
    assert strat["tp_allocations"][0]["percentage"] == 50.0
    assert strat["tp_allocations"][1]["percentage"] == 30.0
    assert strat["tp_allocations"][2]["percentage"] == 20.0
    assert strat["bep_trigger_level"] == 1
    assert strat["trailing_trigger_level"] == 2


@pytest.mark.asyncio
async def test_update_strategy_success(app_and_client: AsyncClient):
    """Test updating TP allocations (60/25/15) and trigger levels."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.put(
        "/api/v1/strategies/1",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tp1_percent": 60.0,
            "tp2_percent": 25.0,
            "tp3_percent": 15.0,
            "bep_trigger_level": 1,
            "trailing_trigger_level": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["tp_allocations"][0]["percentage"] == 60.0
    assert data["tp_allocations"][1]["percentage"] == 25.0
    assert data["tp_allocations"][2]["percentage"] == 15.0

    # Verify through GET
    get_res = await client.get(
        "/api/v1/strategies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    strat = get_res.json()[0]
    assert strat["tp_allocations"][0]["percentage"] == 60.0


@pytest.mark.asyncio
async def test_update_strategy_invalid_tp_sum(app_and_client: AsyncClient):
    """Test updating TP allocations with sum not equal to 100% returns 400 Bad Request."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.put(
        "/api/v1/strategies/1",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tp1_percent": 50.0,
            "tp2_percent": 30.0,
            "tp3_percent": 10.0,  # Sum = 90.0%
        },
    )
    assert res.status_code == 400
    assert "must sum up to 100.0%" in res.json()["detail"]


@pytest.mark.asyncio
async def test_update_strategy_not_found(app_and_client: AsyncClient):
    """Test updating a non-existent strategy returns 404 Not Found."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.put(
        "/api/v1/strategies/999",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "tp1_percent": 50.0,
            "tp2_percent": 30.0,
            "tp3_percent": 20.0,
        },
    )
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


@pytest.mark.asyncio
async def test_providers_unauthorized_rejection(app_and_client: AsyncClient):
    """Test that unauthorized requests to providers endpoints are rejected with 401."""
    client = app_and_client

    res_get = await client.get("/api/v1/providers")
    assert res_get.status_code == 401

    res_post = await client.post(
        "/api/v1/providers",
        json={"name": "Test", "channel_id": "-123"},
    )
    assert res_post.status_code == 401

    res_analytics = await client.get("/api/v1/providers/1/analytics")
    assert res_analytics.status_code == 401


@pytest.mark.asyncio
async def test_strategies_unauthorized_rejection(app_and_client: AsyncClient):
    """Test that unauthorized requests to strategies endpoints are rejected with 401."""
    client = app_and_client

    res_get = await client.get("/api/v1/strategies")
    assert res_get.status_code == 401

    res_put = await client.put(
        "/api/v1/strategies/1",
        json={"tp1_percent": 50.0, "tp2_percent": 30.0, "tp3_percent": 20.0},
    )
    assert res_put.status_code == 401


@pytest.mark.asyncio
async def test_provider_create_and_strategy_update_forbidden_for_viewer(app_and_client: AsyncClient):
    """Test that VIEWER role is forbidden (403) from creating providers or updating strategies."""
    client = app_and_client
    token = await get_viewer_token(client)

    # 1. POST /providers -> 403
    res_post = await client.post(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "New Provider", "channel_id": "-100"},
    )
    assert res_post.status_code == 403

    # 2. PUT /strategies/1 -> 403
    res_put = await client.put(
        "/api/v1/strategies/1",
        headers={"Authorization": f"Bearer {token}"},
        json={"tp1_percent": 50.0, "tp2_percent": 30.0, "tp3_percent": 20.0},
    )
    assert res_put.status_code == 403


@pytest.mark.asyncio
async def test_providers_cache_and_invalidation_on_create(app_and_client: AsyncClient):
    """Test that GET /providers is cached in memory and invalidated upon POST."""
    client = app_and_client
    token = await get_admin_token(client)

    # 1. Initial GET -> cache populated
    res1 = await client.get(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    assert await in_memory_cache.get("providers:all") is not None

    # 2. POST provider -> invalidates cache
    res_create = await client.post(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Cache Test Provider", "channel_id": "-100999"},
    )
    assert res_create.status_code == 201
    assert await in_memory_cache.get("providers:all") is None

    # 3. Next GET -> reads fresh state
    res2 = await client.get(
        "/api/v1/providers",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 200
    assert len(res2.json()) == 3
    assert await in_memory_cache.get("providers:all") is not None


@pytest.mark.asyncio
async def test_provider_analytics_30s_caching(app_and_client: AsyncClient):
    """Test that GET /providers/{id}/analytics is cached for 30 seconds."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/providers/1/analytics",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert await in_memory_cache.get("providers:analytics:1") is not None


@pytest.mark.asyncio
async def test_strategies_cache_and_invalidation_on_update(app_and_client: AsyncClient):
    """Test that GET /strategies is cached and invalidated upon PUT."""
    client = app_and_client
    token = await get_admin_token(client)

    # 1. GET strategies -> cache populated
    res1 = await client.get(
        "/api/v1/strategies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    assert await in_memory_cache.get("strategies:all") is not None

    # 2. PUT strategy -> invalidates cache
    res_update = await client.put(
        "/api/v1/strategies/1",
        headers={"Authorization": f"Bearer {token}"},
        json={"tp1_percent": 40.0, "tp2_percent": 30.0, "tp3_percent": 30.0},
    )
    assert res_update.status_code == 200
    assert await in_memory_cache.get("strategies:all") is None
