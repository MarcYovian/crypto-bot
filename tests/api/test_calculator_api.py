"""Comprehensive API integration test suite for Risk Calculator and Position Sizing Simulator sandbox."""

from decimal import Decimal
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
)
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.utils.security import get_password_hash
from src.utils.cache import in_memory_cache
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_client():
    """Create isolated test database, seed instruments & leverage brackets, and initialize AsyncClient."""
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
            environment="MAINNET",
            is_active=True,
        )
        session.add(account)
        await session.flush()

        # 3. Instruments & Leverage Brackets
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

        b1 = InstrumentLeverageBracket(
            id=1,
            instrument_id=1,
            bracket=1,
            initial_leverage=20,
            notional_floor=Decimal("0.0"),
            notional_cap=Decimal("50000.0"),
            maint_margin_ratio=Decimal("0.005"),
        )
        b2 = InstrumentLeverageBracket(
            id=2,
            instrument_id=2,
            bracket=1,
            initial_leverage=25,
            notional_floor=Decimal("0.0"),
            notional_cap=Decimal("25000.0"),
            maint_margin_ratio=Decimal("0.006"),
        )
        session.add_all([b1, b2])
        await session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        yield client

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
async def test_simulate_risk_buy_position_success(app_and_client: AsyncClient):
    """Test BUY simulation with exact 2% risk, position size, and margin."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 49000.0,
            "wallet_balance": 1000.0,
            "requested_leverage": 20,
            "risk_percent": 2.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["side"] == "BUY"
    assert data["max_allowed_loss_usdt"] == 20.0  # 2% of $1000
    assert data["stop_distance_usdt"] == 1000.0
    assert data["calculated_position_size"] == 0.02  # $20 / $1000
    assert data["required_margin_usdt"] == 50.0  # (0.02 * 50000) / 20 = $50
    assert data["effective_leverage"] == 20
    assert data["is_leverage_downscaled"] is False
    assert data["projected_loss_at_sl_usdt"] == 20.0
    assert data["is_safe"] is True
    assert data["estimated_liquidation_price"] < 49000.0  # Liq below SL


@pytest.mark.asyncio
async def test_simulate_risk_sell_position_success(app_and_client: AsyncClient):
    """Test SELL simulation with exact 2% risk on ETHUSDT."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "ETHUSDT",
            "side": "SELL",
            "entry_price": 3000.0,
            "sl_price": 3100.0,
            "wallet_balance": 2000.0,
            "requested_leverage": 20,
            "risk_percent": 2.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "ETHUSDT"
    assert data["side"] == "SELL"
    assert data["max_allowed_loss_usdt"] == 40.0  # 2% of $2000
    assert data["stop_distance_usdt"] == 100.0
    assert data["calculated_position_size"] == 0.4  # $40 / $100
    assert data["projected_loss_at_sl_usdt"] <= 40.0
    assert data["is_safe"] is True
    assert data["estimated_liquidation_price"] > 3100.0  # Liq above SL for Short


@pytest.mark.asyncio
async def test_simulate_risk_leverage_downscaling_bracket(app_and_client: AsyncClient):
    """Test leverage downscaling when requested leverage exceeds bracket limit."""
    client = app_and_client
    token = await get_admin_token(client)

    # BTC bracket max leverage is 20, request 50x
    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 49000.0,
            "wallet_balance": 1000.0,
            "requested_leverage": 50,
            "risk_percent": 2.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["effective_leverage"] == 20
    assert data["is_leverage_downscaled"] is True


@pytest.mark.asyncio
async def test_simulate_risk_custom_risk_percent(app_and_client: AsyncClient):
    """Test simulation with custom 1.0% risk parameter."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 49000.0,
            "wallet_balance": 1000.0,
            "requested_leverage": 20,
            "risk_percent": 1.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["max_allowed_loss_usdt"] == 10.0  # 1% of $1000
    assert data["calculated_position_size"] == 0.01  # $10 / $1000


@pytest.mark.asyncio
async def test_simulate_risk_zero_stop_distance(app_and_client: AsyncClient):
    """Test that zero stop distance returns 400 Bad Request."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 50000.0,
            "wallet_balance": 1000.0,
        },
    )
    assert res.status_code == 400
    assert "cannot be equal" in res.json()["detail"]


@pytest.mark.asyncio
async def test_simulate_risk_invalid_geometry_buy(app_and_client: AsyncClient):
    """Test that BUY position with SL >= Entry returns 400 Bad Request."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 51000.0,  # Invalid: SL above Entry for BUY
            "wallet_balance": 1000.0,
        },
    )
    assert res.status_code == 400
    assert "Invalid geometry for BUY" in res.json()["detail"]


@pytest.mark.asyncio
async def test_simulate_risk_invalid_geometry_sell(app_and_client: AsyncClient):
    """Test that SELL position with SL <= Entry returns 400 Bad Request."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "SELL",
            "entry_price": 50000.0,
            "sl_price": 49000.0,  # Invalid: SL below Entry for SELL
            "wallet_balance": 1000.0,
        },
    )
    assert res.status_code == 400
    assert "Invalid geometry for SELL" in res.json()["detail"]


@pytest.mark.asyncio
async def test_simulate_risk_insufficient_margin_unsafe(app_and_client: AsyncClient):
    """Test that a setup requiring more margin than wallet balance is flagged is_safe=False."""
    client = app_and_client
    token = await get_admin_token(client)

    # Micro balance of $5 with tight stop distance produces large lot size and margin > balance
    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 49990.0,
            "wallet_balance": 5.0,
            "requested_leverage": 1,
            "risk_percent": 2.0,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["is_safe"] is False


@pytest.mark.asyncio
async def test_simulate_risk_negative_or_zero_balance(app_and_client: AsyncClient):
    """Test that non-positive wallet balance is rejected by validation."""
    client = app_and_client
    token = await get_admin_token(client)

    res = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 49000.0,
            "wallet_balance": 0.0,
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_calculator_unauthorized_rejection(app_and_client: AsyncClient):
    """Test that simulator endpoint without authentication returns 401."""
    client = app_and_client

    res = await client.post(
        "/api/v1/calculator/simulate",
        json={
            "symbol": "BTCUSDT",
            "side": "BUY",
            "entry_price": 50000.0,
            "sl_price": 49000.0,
            "wallet_balance": 1000.0,
        },
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_calculator_accessible_by_viewer_and_admin(app_and_client: AsyncClient):
    """Test that simulator is accessible to both VIEWER and ADMIN roles."""
    client = app_and_client
    admin_token = await get_admin_token(client)
    viewer_token = await get_viewer_token(client)

    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "entry_price": 50000.0,
        "sl_price": 49000.0,
        "wallet_balance": 1000.0,
    }

    res_admin = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=payload,
    )
    assert res_admin.status_code == 200

    res_viewer = await client.post(
        "/api/v1/calculator/simulate",
        headers={"Authorization": f"Bearer {viewer_token}"},
        json=payload,
    )
    assert res_viewer.status_code == 200
