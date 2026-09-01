"""Comprehensive API integration test suite for Bot Operations, Circuit Breaker, and Settings."""

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
    TradingCredential,
    RiskProfile,
    Instrument,
    Trade,
    Order,
    BotSetting,
)
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.infrastructure.gateways.binance import BinanceExchangeAdapter
from src.utils.security import get_password_hash


from src.utils.cache import in_memory_cache
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_client():
    """Create isolated test database, seed users, master configs, and initialize AsyncClient."""
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
            environment="TESTNET",
            is_active=True,
        )
        session.add(account)
        await session.flush()

        # Instrument
        inst = Instrument(
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
        session.add(inst)
        await session.flush()

        # 3. Active Risk Profile
        risk_profile = RiskProfile(
            id=1,
            name="DEFAULT_RISK",
            risk_percent=Decimal("2.0"),
            max_daily_loss=Decimal("6.0"),
            max_open_trade=3,
            is_active=True,
        )
        session.add(risk_profile)

        # 4. Bot Settings
        setting_pause = BotSetting(key="is_paused", value="false", category="SYSTEM", type="BOOL")
        setting_lev = BotSetting(key="default_leverage", value="20", category="TRADING", type="INT")
        setting_conf = BotSetting(key="confidence_threshold", value="0.70", category="TRADING", type="FLOAT")
        session.add_all([setting_pause, setting_lev, setting_conf])

        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client, session_factory

    await engine.dispose()


async def get_admin_token(client: AsyncClient) -> str:
    """Helper to authenticate admin user."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminPass123!"},
    )
    return res.json()["access_token"]


async def get_viewer_token(client: AsyncClient) -> str:
    """Helper to authenticate viewer user."""
    res = await client.post(
        "/api/v1/auth/login",
        json={"username": "viewer", "password": "ViewerPass123!"},
    )
    return res.json()["access_token"]


@pytest.mark.asyncio
async def test_get_bot_status_success(app_and_client):
    """Test retrieving active bot runtime and health status."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/bot/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_running"] is True
    assert data["is_paused"] is False
    assert data["trading_status"] == "ACTIVE"
    assert data["binance_ws_connected"] is True
    assert data["scheduler_jobs_count"] == 8
    assert "last_heartbeat" in data



@pytest.mark.asyncio
async def test_pause_and_resume_bot_lifecycle(app_and_client):
    """Test pausing and subsequently resuming the bot trading engine."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    # 1. Pause Bot
    res_pause = await client.post(
        "/api/v1/bot/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_pause.status_code == 200
    assert res_pause.json()["success"] is True

    # Check status is PAUSED
    res_status = await client.get(
        "/api/v1/bot/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_status.json()["is_paused"] is True
    assert res_status.json()["trading_status"] == "PAUSED"

    # 2. Resume Bot
    res_resume = await client.post(
        "/api/v1/bot/resume",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_resume.status_code == 200
    assert res_resume.json()["success"] is True

    # Check status is ACTIVE
    res_status_after = await client.get(
        "/api/v1/bot/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_status_after.json()["is_paused"] is False
    assert res_status_after.json()["trading_status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_panic_close_all_positions_and_cancel_orders(app_and_client):
    """Test emergency panic close closes open trades and cancels pending orders."""
    client, session_factory = app_and_client
    token = await get_admin_token(client)

    # Seed 2 open trades and 3 orders
    async with session_factory() as session:
        t1 = Trade(
            id=101,
            account_id=1,
            instrument_id=1,
            side="BUY",
            entry_price=Decimal("50000.0"),
            sl_price=Decimal("49000.0"),
            position_size=Decimal("0.02"),
            remaining_qty=Decimal("0.02"),
            leverage=20,
            status="OPEN",
        )
        t2 = Trade(
            id=102,
            account_id=1,
            instrument_id=1,
            side="SELL",
            entry_price=Decimal("3000.0"),
            sl_price=Decimal("3100.0"),
            position_size=Decimal("0.5"),
            remaining_qty=Decimal("0.5"),
            leverage=20,
            status="WAITING_ENTRY",
        )
        session.add_all([t1, t2])
        await session.flush()

        o1 = Order(
            trade_id=101,
            client_order_id="TP1_ORD",
            purpose="TP1",
            order_type="LIMIT",
            side="SELL",
            price=Decimal("51000.0"),
            qty=Decimal("0.01"),
            status="NEW",
        )
        o2 = Order(
            trade_id=101,
            client_order_id="SL_ORD",
            purpose="SL",
            order_type="STOP_MARKET",
            side="SELL",
            price=Decimal("49000.0"),
            qty=Decimal("0.02"),
            status="NEW",
        )
        o3 = Order(
            trade_id=102,
            client_order_id="ENTRY_ORD",
            purpose="ENTRY",
            order_type="LIMIT",
            side="SELL",
            price=Decimal("3000.0"),
            qty=Decimal("0.5"),
            status="PARTIALLY_FILLED",
        )
        session.add_all([o1, o2, o3])
        await session.commit()

    # Trigger panic close
    res = await client.post(
        "/api/v1/bot/panic",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirmation": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["closed_trades_count"] == 2
    assert data["canceled_orders_count"] == 3

    # Bot should now be paused
    res_status = await client.get(
        "/api/v1/bot/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_status.json()["is_paused"] is True


@pytest.mark.asyncio
async def test_get_settings_success(app_and_client):
    """Test fetching active bot configuration and risk profile."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["default_leverage"] == 20
    assert data["confidence_threshold"] == 0.70
    assert data["risk_percent_per_trade"] == 2.0
    assert data["max_daily_loss_percent"] == 6.0
    assert data["max_open_trades"] == 3
    assert data["is_paused"] is False


@pytest.mark.asyncio
async def test_update_settings_success(app_and_client):
    """Test updating bot settings and risk profile."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.put(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "default_leverage": 25,
            "confidence_threshold": 0.80,
            "risk_percent_per_trade": 1.5,
            "max_daily_loss_percent": 5.0,
            "max_open_trades": 4,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["default_leverage"] == 25
    assert data["confidence_threshold"] == 0.80
    assert data["risk_percent_per_trade"] == 1.5
    assert data["max_daily_loss_percent"] == 5.0
    assert data["max_open_trades"] == 4


@pytest.mark.asyncio
async def test_credentials_handshake_success(app_and_client):
    """Test saving credentials with successful Binance handshake."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    mock_info = {
        "total_wallet_balance": Decimal("1500.75"),
        "free_margin": Decimal("1200.00"),
        "used_margin": Decimal("300.75"),
        "unrealized_pnl": Decimal("0.0"),
    }

    with patch.object(BinanceExchangeAdapter, "get_balance", new_callable=AsyncMock) as mock_get_acc:
        mock_get_acc.return_value = mock_info


        res = await client.post(
            "/api/v1/settings/credentials",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "api_key": "valid_binance_api_key_123456",
                "secret_key": "valid_binance_secret_key_654321",
                "environment": "TESTNET",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["success"] is True
        assert data["wallet_balance_usdt"] == 1500.75
        assert data["environment"] == "TESTNET"


@pytest.mark.asyncio
async def test_panic_without_confirmation(app_and_client):
    """Test that panic close without confirmation=True returns 400 Bad Request."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/bot/panic",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirmation": False},
    )
    assert res.status_code == 400
    assert "requires confirmation=true" in res.json()["detail"]


@pytest.mark.asyncio
async def test_update_settings_invalid_ranges(app_and_client):
    """Test that setting values outside acceptable ranges are rejected."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    # Leverage > 125 rejected by Pydantic (422)
    res_lev = await client.put(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"default_leverage": 150},
    )
    assert res_lev.status_code == 422

    # Risk > 10% rejected by Pydantic (422)
    res_risk = await client.put(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"risk_percent_per_trade": 50.0},
    )
    assert res_risk.status_code == 422


@pytest.mark.asyncio
async def test_credentials_handshake_failed(app_and_client):
    """Test that failed Binance handshake returns 400 Bad Request."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    with patch.object(BinanceExchangeAdapter, "get_balance", new_callable=AsyncMock) as mock_get_acc:
        mock_get_acc.side_effect = Exception("API-key format invalid or IP not whitelisted")


        res = await client.post(
            "/api/v1/settings/credentials",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "api_key": "invalid_api_key_format_here",
                "secret_key": "invalid_secret_key_format_here",
                "environment": "TESTNET",
            },
        )
        assert res.status_code == 400
        assert "handshake authentication failed" in res.json()["detail"]



@pytest.mark.asyncio
async def test_bot_operations_unauthorized_rejection(app_and_client):
    """Test that requests without JWT Bearer token return 401 Unauthorized."""
    client, _ = app_and_client

    res1 = await client.get("/api/v1/bot/status")
    assert res1.status_code == 401

    res2 = await client.post("/api/v1/bot/pause")
    assert res2.status_code == 401

    res3 = await client.get("/api/v1/settings")
    assert res3.status_code == 401


@pytest.mark.asyncio
async def test_settings_mutation_forbidden_for_viewer(app_and_client):
    """Test that VIEWER role is forbidden from mutating bot operations & settings."""
    client, _ = app_and_client
    token = await get_viewer_token(client)

    # Status & Get Settings are allowed for Viewer
    res_status = await client.get(
        "/api/v1/bot/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_status.status_code == 200

    res_settings = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_settings.status_code == 200

    # Mutations are 403 Forbidden
    res_pause = await client.post(
        "/api/v1/bot/pause",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_pause.status_code == 403

    res_panic = await client.post(
        "/api/v1/bot/panic",
        headers={"Authorization": f"Bearer {token}"},
        json={"confirmation": True},
    )
    assert res_panic.status_code == 403

    res_put_settings = await client.put(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"default_leverage": 10},
    )
    assert res_put_settings.status_code == 403


@pytest.mark.asyncio
async def test_settings_caching_and_write_through_invalidation(app_and_client):
    """Test caching of settings and invalidation upon PUT update."""
    client, _ = app_and_client
    token = await get_admin_token(client)

    # 1. Warm cache
    res1 = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 200
    assert res1.json()["default_leverage"] == 20

    # 2. Update settings -> invalidates cache
    res2 = await client.put(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
        json={"default_leverage": 50},
    )
    assert res2.status_code == 200
    assert res2.json()["default_leverage"] == 50

    # 3. GET retrieves updated value
    res3 = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res3.status_code == 200
    assert res3.json()["default_leverage"] == 50
