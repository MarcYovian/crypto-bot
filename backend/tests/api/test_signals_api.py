"""Comprehensive test suite for Telegram Signals Feed & Manual Signal Execution API endpoints."""

from datetime import datetime, timezone
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import (
    Exchange,
    TradingAccount,
    Instrument,
    SignalProvider,
    TradingSignal,
    Watchlist,
    RiskProfile,
    DailyRiskConfig,
    Trade,
    TradeRisk,
    Order,
    Execution,
    User,
)
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.utils.security import get_password_hash, create_access_token
from src.utils.cache import in_memory_cache
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_client():
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
        # 1. Admin User
        user_repo = UserRepository(session)
        await user_repo.create_user(
            username="admin",
            password_hash=get_password_hash("AdminPass123!"),
            role="ADMIN",
            is_active=True,
        )

        # 2. Exchange & Account
        exchange = Exchange(id=1, code="BINANCE", name="Binance", status=True)
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

        # 3. Risk Profile & Daily Risk Budget
        profile = RiskProfile(
            id=1,
            name="Default Profile",
            risk_percent=Decimal("2.0"),
            max_daily_loss=Decimal("6.0"),
            max_open_trade=5,
            is_active=True,
        )
        session.add(profile)
        await session.flush()

        today = datetime.now(timezone.utc).date()
        daily_risk = DailyRiskConfig(
            id=1,
            account_id=1,
            risk_profile_id=1,
            date=today,
            balance=Decimal("10000.00"),
            risk_amount=Decimal("600.00"),
        )
        session.add(daily_risk)
        await session.flush()

        # 4. Signal Provider
        provider = SignalProvider(
            id=1,
            name="CryptoVIP Channel",
            type="TELEGRAM",
            is_active=True,
        )
        session.add(provider)
        await session.flush()

        # 5. Instruments & Watchlists
        btc = Instrument(
            id=1,
            exchange_id=1,
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            min_qty=Decimal("0.001"),
            step_size=Decimal("0.001"),
            tick_size=Decimal("0.10"),
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
            min_qty=Decimal("0.01"),
            step_size=Decimal("0.01"),
            tick_size=Decimal("0.01"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=2,
            is_active=True,
        )
        session.add_all([btc, eth])
        await session.flush()

        wl1 = Watchlist(id=1, instrument_id=1, enabled=True)
        wl2 = Watchlist(id=2, instrument_id=2, enabled=True)
        session.add_all([wl1, wl2])
        await session.flush()

        # 6. Seed Signals Feed
        sig1 = TradingSignal(
            id=1,
            provider_id=1,
            instrument_id=1,
            telegram_message_id=101,
            timeframe="15m",
            side="BUY",
            entry_min=Decimal("50000.00"),
            entry_max=Decimal("50200.00"),
            sl_price=Decimal("49000.00"),
            tp1_price=Decimal("51000.00"),
            tp2_price=Decimal("52000.00"),
            tp3_price=Decimal("53000.00"),
            confidence=Decimal("0.9500"),
            raw_message="#BTCUSDT BUY 50000 - 50200 SL: 49000 TP: 51000, 52000, 53000",
            status="RECEIVED",
            confirmation_status="NOT_REQUIRED",
        )
        sig2 = TradingSignal(
            id=2,
            provider_id=1,
            instrument_id=2,
            telegram_message_id=102,
            timeframe="1h",
            side="SELL",
            entry_min=Decimal("3000.00"),
            entry_max=Decimal("3020.00"),
            sl_price=Decimal("3100.00"),
            tp1_price=Decimal("2900.00"),
            tp2_price=Decimal("2800.00"),
            confidence=Decimal("0.8800"),
            raw_message="#ETHUSDT SELL 3000 SL: 3100 TP: 2900, 2800",
            status="EXECUTED",
            confirmation_status="APPROVED",
        )
        sig3 = TradingSignal(
            id=3,
            provider_id=1,
            instrument_id=1,
            telegram_message_id=103,
            timeframe="4h",
            side="BUY",
            entry_min=Decimal("48000.00"),
            entry_max=Decimal("48500.00"),
            sl_price=Decimal("47000.00"),
            tp1_price=Decimal("50000.00"),
            confidence=Decimal("0.6500"),
            raw_message="#BTCUSDT BUY 48000 SL: 47000 TP: 50000",
            status="REJECTED",
            confirmation_status="REJECTED",
        )
        session.add_all([sig1, sig2, sig3])
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    await engine.dispose()


@pytest.fixture
def auth_headers() -> dict:
    token = create_access_token(data={"sub": "admin", "role": "ADMIN", "user_id": 1})
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# TEST SUITE: Signals Feed & Manual Execution Endpoints
# =========================================================================

@pytest.mark.asyncio
async def test_get_signals_feed_success(app_and_client, auth_headers):
    """Test retrieving paginated Telegram signals feed."""
    client, _ = app_and_client
    response = await client.get("/api/v1/signals?page=1&page_size=20", headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["items"]) == 3

    item = data["items"][0]
    assert "id" in item
    assert "trace_id" in item
    assert "symbol" in item
    assert "side" in item
    assert "entry_price" in item
    assert "sl_price" in item
    assert "tp_targets" in item
    assert "confidence_score" in item
    assert "status" in item
    assert "created_at" in item


@pytest.mark.asyncio
async def test_get_signals_feed_pagination_and_status_filter(app_and_client, auth_headers):
    """Test pagination limit and status filtering on signals feed."""
    client, _ = app_and_client

    # Test pagination limit
    resp_paged = await client.get("/api/v1/signals?page=1&page_size=2", headers=auth_headers)
    assert resp_paged.status_code == 200
    paged_data = resp_paged.json()
    assert paged_data["total"] == 3
    assert len(paged_data["items"]) == 2

    # Test status filter: EXECUTED
    resp_executed = await client.get("/api/v1/signals?status=EXECUTED", headers=auth_headers)
    assert resp_executed.status_code == 200
    exec_data = resp_executed.json()
    assert exec_data["total"] == 1
    assert exec_data["items"][0]["status"] == "EXECUTED"
    assert exec_data["items"][0]["symbol"] == "ETHUSDT"

    # Test status filter: PENDING (maps to RECEIVED)
    resp_pending = await client.get("/api/v1/signals?status=PENDING", headers=auth_headers)
    assert resp_pending.status_code == 200
    pend_data = resp_pending.json()
    assert pend_data["total"] == 1
    assert pend_data["items"][0]["status"] == "RECEIVED"


@pytest.mark.asyncio
async def test_manual_execute_signal_buy_success(app_and_client, auth_headers):
    """Test executing a valid BUY manual signal with 2% risk management."""
    client, session_factory = app_and_client

    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "entry_price": 50000.00,
        "sl_price": 49000.00,
        "tp_targets": [51000.00, 52000.00, 53000.00],
        "leverage": 20,
        "auto_tp_sl": True,
    }

    response = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["is_success"] is True
    assert data["symbol"] == "BTCUSDT"
    assert data["side"] == "BUY"
    assert data["trade_id"] is not None
    assert data["position_size"] > 0.0

    # Verify trade was saved to database
    async with session_factory() as session:
        trade = await session.get(Trade, data["trade_id"])
        assert trade is not None
        assert trade.side == "BUY"
        assert trade.status in ("OPEN", "WAITING_ENTRY")


@pytest.mark.asyncio
async def test_manual_execute_signal_sell_success(app_and_client, auth_headers):
    """Test executing a valid SELL manual signal."""
    client, session_factory = app_and_client

    payload = {
        "symbol": "ETHUSDT",
        "side": "SELL",
        "entry_price": 3000.00,
        "sl_price": 3100.00,
        "tp_targets": [2900.00, 2800.00],
        "leverage": 10,
        "auto_tp_sl": True,
    }

    response = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert response.status_code == 200

    data = response.json()
    assert data["is_success"] is True
    assert data["symbol"] == "ETHUSDT"
    assert data["side"] == "SELL"
    assert data["trade_id"] is not None


@pytest.mark.asyncio
async def test_manual_execute_invalid_price_geometry_buy(app_and_client, auth_headers):
    """Test rejection when BUY Stop Loss is at or above Entry price."""
    client, _ = app_and_client

    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "entry_price": 50000.00,
        "sl_price": 51000.00,  # Invalid: SL > Entry for BUY
        "tp_targets": [52000.00],
    }

    response = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "Stop Loss" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_execute_invalid_price_geometry_sell(app_and_client, auth_headers):
    """Test rejection when SELL Stop Loss is at or below Entry price."""
    client, _ = app_and_client

    payload = {
        "symbol": "BTCUSDT",
        "side": "SELL",
        "entry_price": 50000.00,
        "sl_price": 49000.00,  # Invalid: SL < Entry for SELL
        "tp_targets": [48000.00],
    }

    response = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "Stop Loss" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_execute_tp_geometry_invalid(app_and_client, auth_headers):
    """Test rejection when Take Profit is not higher than Entry for BUY."""
    client, _ = app_and_client

    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "entry_price": 50000.00,
        "sl_price": 49000.00,
        "tp_targets": [49500.00],  # Invalid: TP < Entry for BUY
    }

    response = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "Take Profit" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_execute_symbol_not_in_watchlist(app_and_client, auth_headers):
    """Test rejection when symbol is not registered in watchlist."""
    client, _ = app_and_client

    payload = {
        "symbol": "SOLUSDT",  # Not in watchlist
        "side": "BUY",
        "entry_price": 150.00,
        "sl_price": 140.00,
        "tp_targets": [160.00],
    }

    response = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert response.status_code == 400
    assert "Symbol rejected" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_execute_duplicate_active_pair(app_and_client, auth_headers):
    """Test rejection when attempting to open a second active position on the same pair."""
    client, _ = app_and_client

    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "entry_price": 50000.00,
        "sl_price": 49000.00,
        "tp_targets": [51000.00],
    }

    # 1. First execution succeeds
    resp1 = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert resp1.status_code == 200

    # 2. Second execution on same pair is rejected
    resp2 = await client.post("/api/v1/signals/manual-execute", json=payload, headers=auth_headers)
    assert resp2.status_code == 400
    assert "Pair already active" in resp2.json()["detail"]


@pytest.mark.asyncio
async def test_signals_unauthorized_rejection(app_and_client):
    """Test rejection with 401 when calling signals endpoints without valid authentication."""
    client, _ = app_and_client

    # 1. Feed endpoint
    resp1 = await client.get("/api/v1/signals")
    assert resp1.status_code == 401

    # 2. Manual execute endpoint
    resp2 = await client.post("/api/v1/signals/manual-execute", json={})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_signals_feed_caching_and_invalidation(app_and_client, auth_headers):
    """Test 5-second in-memory caching of signals feed and auto-invalidation on manual execution."""
    client, session_factory = app_and_client

    # 1. First request fills cache
    resp1 = await client.get("/api/v1/signals?page=1&page_size=20", headers=auth_headers)
    assert resp1.status_code == 200
    assert resp1.json()["total"] == 3

    # 2. Insert new signal directly into database
    async with session_factory() as session:
        new_sig = TradingSignal(
            id=99,
            provider_id=1,
            instrument_id=1,
            timeframe="15m",
            side="BUY",
            entry_min=Decimal("50000.00"),
            sl_price=Decimal("49000.00"),
            tp1_price=Decimal("51000.00"),
            status="RECEIVED",
            confirmation_status="NOT_REQUIRED",
        )
        session.add(new_sig)
        await session.commit()

    # 3. Second request hits cache (total still 3)
    resp2 = await client.get("/api/v1/signals?page=1&page_size=20", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 3

    # 4. Manual execution invalidates cache
    exec_payload = {
        "symbol": "ETHUSDT",
        "side": "BUY",
        "entry_price": 3000.00,
        "sl_price": 2900.00,
        "tp_targets": [3100.00],
    }
    exec_resp = await client.post("/api/v1/signals/manual-execute", json=exec_payload, headers=auth_headers)
    assert exec_resp.status_code == 200

    # 5. Third request fetches fresh data (total is now 4)
    resp3 = await client.get("/api/v1/signals?page=1&page_size=20", headers=auth_headers)
    assert resp3.status_code == 200
    assert resp3.json()["total"] == 4
