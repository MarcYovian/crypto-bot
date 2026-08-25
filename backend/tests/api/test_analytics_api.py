"""Comprehensive test suite for Analytics and Dashboard Summary API endpoints."""

from datetime import datetime, date, timedelta, timezone
from decimal import Decimal
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sqlalchemy.pool import StaticPool

from src.database.connection import Base
from src.database.models import (
    Exchange,
    TradingAccount,
    TradingCredential,
    Instrument,
    Trade,
    TradeRisk,
    TradeSummary,
    DailyRiskConfig,
    RiskProfile,
    User,
)
from src.repository.user_repository import UserRepository
from src.utils.security import get_password_hash, create_access_token
from src.utils.cache import in_memory_cache
from src.api.app import create_app
from src.api.deps import get_db_session

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

    # Seed initial test data
    async with session_factory() as session:
        # 1. Admin user
        user_repo = UserRepository(session)
        await user_repo.create_user(
            username="admin",
            password_hash=get_password_hash("AdminPass123!"),
            role="ADMIN",
            is_active=True,
        )

        # 2. Exchange & Trading Account
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

        cred = TradingCredential(
            id=1,
            account_id=1,
            key_name="Main Key",
            encrypted_api_key="key",
            encrypted_secret_key="sec",
            is_active=True,
        )
        session.add(cred)
        await session.flush()

        profile = RiskProfile(
            id=1,
            name="Default Profile",
            risk_percent=Decimal("2.0"),
            max_daily_loss=Decimal("6.0"),
            max_open_trade=3,
            is_active=True,
        )
        session.add(profile)
        await session.flush()

        # 3. Instrument
        instrument = Instrument(
            id=1,
            exchange_id=1,
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.1"),
            step_size=Decimal("0.001"),
            min_qty=Decimal("0.001"),
            min_notional=Decimal("5.0"),
            price_precision=2,
            qty_precision=3,
            is_active=True,
        )
        session.add(instrument)
        await session.flush()

        # 4. Daily Risk Config for Today & Historical
        today = datetime.now(timezone.utc).date()
        daily_today = DailyRiskConfig(
            id=1,
            account_id=1,
            risk_profile_id=1,
            date=today,
            balance=Decimal("10500.00"),
            risk_amount=Decimal("630.00"),  # 6% of 10500
        )
        daily_prev = DailyRiskConfig(
            id=2,
            account_id=1,
            risk_profile_id=1,
            date=today - timedelta(days=2),
            balance=Decimal("10424.50"),
            risk_amount=Decimal("625.00"),
        )
        session.add_all([daily_today, daily_prev])
        await session.flush()

        # 5. Trades and Summaries
        trade1 = Trade(
            id=1,
            account_id=1,
            instrument_id=1,
            side="BUY",
            status="CLOSED",
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0.0"),
            entry_price=Decimal("50000.00"),
            sl_price=Decimal("49000.00"),
            leverage=20,
            margin_mode="ISOLATED",
        )
        session.add(trade1)
        await session.flush()

        summary1 = TradeSummary(
            trade_id=1,
            gross_pnl=Decimal("100.00"),
            net_pnl=Decimal("95.00"),
            commission=Decimal("5.00"),
            funding=Decimal("0.00"),
            roi=Decimal("5.0"),
            rr=Decimal("2.5"),
            result="WIN",
            duration_seconds=3600,
            close_reason="TP2",
            closed_at=datetime.now(timezone.utc),
        )
        session.add(summary1)

        trade2 = Trade(
            id=2,
            account_id=1,
            instrument_id=1,
            side="SELL",
            status="CLOSED",
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0.0"),
            entry_price=Decimal("50000.00"),
            sl_price=Decimal("50200.00"),
            leverage=20,
            margin_mode="ISOLATED",
        )
        session.add(trade2)
        await session.flush()

        summary2 = TradeSummary(
            trade_id=2,
            gross_pnl=Decimal("-20.00"),
            net_pnl=Decimal("-22.00"),
            commission=Decimal("2.00"),
            funding=Decimal("0.00"),
            roi=Decimal("-1.0"),
            rr=Decimal("-1.0"),
            result="LOSS",
            duration_seconds=1800,
            close_reason="SL",
            closed_at=datetime.now(timezone.utc),
        )
        session.add(summary2)

        # 6. Active Trade (OPEN) with TradeRisk
        active_trade = Trade(
            id=3,
            account_id=1,
            instrument_id=1,
            side="BUY",
            status="OPEN",
            position_size=Decimal("0.05"),
            remaining_qty=Decimal("0.05"),
            entry_price=Decimal("50500.00"),
            sl_price=Decimal("49500.00"),
            leverage=20,
            margin_mode="ISOLATED",
        )
        session.add(active_trade)
        await session.flush()

        active_risk = TradeRisk(
            trade_id=3,
            daily_risk_id=1,
            entry=Decimal("50500.00"),
            stop=Decimal("49500.00"),
            stop_distance=Decimal("1000.00"),
            qty=Decimal("0.05"),
            margin=Decimal("250.00"),
            risk_amount=Decimal("200.00"),
            leverage=20,
        )
        session.add(active_risk)
        await session.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    await in_memory_cache.clear()
    await engine.dispose()


@pytest.fixture
def auth_headers() -> dict:
    token = create_access_token(data={"sub": "admin", "role": "ADMIN"})
    return {"Authorization": f"Bearer {token}"}


# =========================================================================
# 1. POSITIVE & BUSINESS TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_get_analytics_summary_success(app_and_client, auth_headers):
    """Test full dashboard summary calculation with trades, win rate, and risk budget."""
    client, _ = app_and_client
    response = await client.get("/api/v1/analytics/summary?account_id=1", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Balance & Margin (10,500 total - 250 margin used in active trade = 10,250 free margin)
    assert data["total_balance_usdt"] == 10500.00
    assert data["free_margin_usdt"] == 10250.00

    # Risk limits: daily budget = 630.00, remaining budget = 630 - 200 = 430.00
    assert data["daily_risk_budget"] == 630.00
    assert data["remaining_risk_budget"] == 430.00

    # Performance metrics: 1 Win ($95 net), 1 Loss ($-22 net)
    assert data["total_trades_count"] == 2
    assert data["winning_trades_count"] == 1
    assert data["losing_trades_count"] == 1
    assert data["win_rate"] == 50.0  # 1/2 = 50%
    assert data["profit_factor"] == 5.0  # $100 gross win / $20 gross loss = 5.0

    # Active trades count: 1 OPEN trade
    assert data["active_trades_count"] == 1

    # Daily PnL: $95 - $22 = $73 net today
    assert data["daily_realized_pnl"] == 73.00
    assert data["daily_pnl_percent"] > 0


@pytest.mark.asyncio
async def test_get_equity_curve_chart_data(app_and_client, auth_headers):
    """Test equity growth points retrieval for charts across timeframes."""
    client, _ = app_and_client
    # 1. Default 30d
    response_30d = await client.get("/api/v1/analytics/equity-curve?account_id=1&timeframe=30d", headers=auth_headers)
    assert response_30d.status_code == 200
    points = response_30d.json()
    assert len(points) == 2
    assert points[0]["balance"] == 10424.50
    assert points[1]["balance"] == 10500.00

    # 2. All timeframe
    response_all = await client.get("/api/v1/analytics/equity-curve?account_id=1&timeframe=all", headers=auth_headers)
    assert response_all.status_code == 200
    assert len(response_all.json()) == 2


# =========================================================================
# 2. CACHING EFFICIENCY TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_analytics_in_memory_caching(app_and_client, auth_headers):
    """Test that repeat requests hit the in-memory cache directly."""
    client, _ = app_and_client

    # 1. Initial request (populates cache)
    resp1 = await client.get("/api/v1/analytics/summary?account_id=1", headers=auth_headers)
    assert resp1.status_code == 200

    # Verify cache contains key
    cached_val = await in_memory_cache.get("analytics:summary:1")
    assert cached_val is not None
    assert cached_val["total_balance_usdt"] == 10500.00

    # 2. Second request should hit cache
    resp2 = await client.get("/api/v1/analytics/summary?account_id=1", headers=auth_headers)
    assert resp2.status_code == 200
    assert resp2.json()["total_balance_usdt"] == 10500.00


# =========================================================================
# 3. NEGATIVE & EDGE CASE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_analytics_unauthorized_rejection(app_and_client):
    """Test that requests without JWT Bearer token are rejected."""
    client, _ = app_and_client
    resp_sum = await client.get("/api/v1/analytics/summary")
    assert resp_sum.status_code == 401

    resp_eq = await client.get("/api/v1/analytics/equity-curve")
    assert resp_eq.status_code == 401


@pytest.mark.asyncio
async def test_analytics_invalid_parameters_validation(app_and_client, auth_headers):
    """Test validation errors on invalid timeframe and account_id values."""
    client, _ = app_and_client

    # Invalid timeframe (must be 7d, 30d, 90d, or all)
    resp_bad_tf = await client.get(
        "/api/v1/analytics/equity-curve?timeframe=500days",
        headers=auth_headers,
    )
    assert resp_bad_tf.status_code == 422
    assert resp_bad_tf.json()["code"] == "VALIDATION_ERROR"

    # Invalid account_id (must be >= 1)
    resp_bad_acc = await client.get(
        "/api/v1/analytics/summary?account_id=0",
        headers=auth_headers,
    )
    assert resp_bad_acc.status_code == 422


@pytest.mark.asyncio
async def test_analytics_empty_database_edge_case(auth_headers):
    """Test analytics calculations when account has no trades or snapshots."""
    await in_memory_cache.clear()
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    app = create_app()

    async def override_session():
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_session

    async with session_factory() as s:
        user_repo = UserRepository(s)
        await user_repo.create_user(
            username="admin",
            password_hash=get_password_hash("AdminPass123!"),
            role="ADMIN",
            is_active=True,
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Summary with no data
        resp = await client.get("/api/v1/analytics/summary?account_id=99", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["win_rate"] == 0.0
        assert data["total_trades_count"] == 0
        assert data["profit_factor"] == 0.0
        assert data["active_trades_count"] == 0

        # Equity curve with no history
        resp_eq = await client.get("/api/v1/analytics/equity-curve?account_id=99", headers=auth_headers)
        assert resp_eq.status_code == 200
        points = resp_eq.json()
        assert len(points) == 1  # Single baseline point
        assert points[0]["balance"] == 10000.0

    await engine.dispose()

