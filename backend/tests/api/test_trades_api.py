"""Comprehensive test suite for Trades and Positions Management API endpoints."""

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
    Order,
    Execution,
    TradeEvent,
    TradeSummary,
    RiskProfile,
    DailyRiskConfig,
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

        # 2. Exchange, Account, RiskProfile, DailyRisk
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

        daily_config = DailyRiskConfig(
            id=1,
            account_id=1,
            risk_profile_id=1,
            date=datetime.now(timezone.utc).date(),
            balance=Decimal("10000.00"),
            risk_amount=Decimal("600.00"),
        )
        session.add(daily_config)
        await session.flush()

        # 3. Instruments
        inst_btc = Instrument(
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
        inst_eth = Instrument(
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
        session.add_all([inst_btc, inst_eth])
        await session.flush()

        # 4. Open Long Position with TP1 Hit
        trade_open = Trade(
            id=101,
            account_id=1,
            instrument_id=1,
            side="BUY",
            status="OPEN",
            entry_price=Decimal("50000.00"),
            sl_price=Decimal("49000.00"),
            tp1_price=Decimal("51000.00"),
            tp2_price=Decimal("52000.00"),
            tp3_price=Decimal("53000.00"),
            position_size=Decimal("0.1"),
            remaining_qty=Decimal("0.1"),
            leverage=20,
            margin_mode="ISOLATED",
            opened_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        session.add(trade_open)
        await session.flush()

        risk_101 = TradeRisk(
            trade_id=101,
            daily_risk_id=1,
            entry=Decimal("50000.00"),
            stop=Decimal("49000.00"),
            stop_distance=Decimal("1000.00"),
            qty=Decimal("0.1"),
            margin=Decimal("250.00"),
            risk_amount=Decimal("100.00"),
            leverage=20,
        )
        order_entry = Order(
            id=1,
            trade_id=101,
            exchange_order_id="binance-111",
            client_order_id="ENTRY_101_111",
            purpose="ENTRY",
            order_type="LIMIT",
            side="BUY",
            price=Decimal("50000.00"),
            qty=Decimal("0.1"),
            status="FILLED",
        )
        exec_entry = Execution(
            id=1,
            order_id=1,
            trade_id=101,
            price=Decimal("50000.00"),
            qty=Decimal("0.1"),
            commission=Decimal("2.50"),
            realized_pnl=Decimal("0.00"),
            executed_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
        event_tp1 = TradeEvent(
            trade_id=101,
            event_type="TP1_HIT",
            payload_json='{"level": 1, "price": 51000.0}',
        )
        session.add_all([risk_101, order_entry, exec_entry, event_tp1])
        await session.flush()

        # 5. Closed Trade (WIN)
        trade_win = Trade(
            id=102,
            account_id=1,
            instrument_id=2,
            side="SELL",
            status="CLOSED",
            entry_price=Decimal("3000.00"),
            avg_entry_price=Decimal("2900.00"),
            sl_price=Decimal("3100.00"),
            position_size=Decimal("1.0"),
            remaining_qty=Decimal("0.0"),
            leverage=10,
            margin_mode="ISOLATED",
            opened_at=datetime.now(timezone.utc) - timedelta(days=1),
            closed_at=datetime.now(timezone.utc) - timedelta(hours=12),
        )
        session.add(trade_win)
        await session.flush()

        summary_win = TradeSummary(
            trade_id=102,
            gross_pnl=Decimal("100.00"),
            net_pnl=Decimal("94.00"),
            commission=Decimal("6.00"),
            funding=Decimal("0.00"),
            roi=Decimal("31.33"),
            rr=Decimal("2.0"),
            result="WIN",
            duration_seconds=43200,
            close_reason="TP2_HIT",
            closed_at=datetime.now(timezone.utc) - timedelta(hours=12),
        )
        session.add(summary_win)

        # 6. Cancelled Trade (Without summary)
        trade_cancel = Trade(
            id=103,
            account_id=1,
            instrument_id=1,
            side="BUY",
            status="CANCELLED",
            sl_price=Decimal("49000.00"),
            position_size=Decimal("0.05"),
            remaining_qty=Decimal("0.0"),
            leverage=20,
            margin_mode="ISOLATED",
            created_at=datetime.now(timezone.utc) - timedelta(hours=5),
            closed_at=datetime.now(timezone.utc) - timedelta(hours=4),
        )
        session.add(trade_cancel)
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
# 1. POSITIVE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_get_active_trades(app_and_client, auth_headers):
    """Test retrieving active open positions with live calculated Unrealized PnL and TP status."""
    client, _ = app_and_client

    # Set mock current price in cache for BTCUSDT: 50,600 USDT (entry was 50,000)
    await in_memory_cache.set("ticker:BTCUSDT", 50600.00)

    response = await client.get("/api/v1/trades/active?account_id=1", headers=auth_headers)
    assert response.status_code == 200
    trades = response.json()
    assert len(trades) == 1

    t = trades[0]
    assert t["trade_id"] == 101
    assert t["symbol"] == "BTCUSDT"
    assert t["side"] == "BUY"
    assert t["status"] == "OPEN"
    assert t["entry_price"] == 50000.00
    assert t["current_price"] == 50600.00
    # Unrealized PnL = (50,600 - 50,000) * 0.1 = +60.00 USDT
    assert t["unrealized_pnl"] == 60.00
    assert t["unrealized_pnl_percent"] > 0

    # TP levels: TP1 was hit, TP2 and TP3 are pending
    assert len(t["tp_levels"]) == 3
    assert t["tp_levels"][0]["level"] == 1
    assert t["tp_levels"][0]["is_hit"] is True
    assert t["tp_levels"][1]["level"] == 2
    assert t["tp_levels"][1]["is_hit"] is False


@pytest.mark.asyncio
async def test_get_trade_history_pagination_and_filters(app_and_client, auth_headers):
    """Test paginated trade history retrieval with result and symbol filters."""
    client, _ = app_and_client

    # 1. All history (should contain 2 items: 102 CLOSED WIN, 103 CANCELLED)
    resp_all = await client.get("/api/v1/trades/history?account_id=1", headers=auth_headers)
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["total"] == 2
    assert len(data_all["items"]) == 2

    # 2. Filter by result=WIN
    resp_win = await client.get("/api/v1/trades/history?account_id=1&result=WIN", headers=auth_headers)
    assert resp_win.status_code == 200
    data_win = resp_win.json()
    assert data_win["total"] == 1
    assert data_win["items"][0]["id"] == 102
    assert data_win["items"][0]["result"] == "WIN"
    assert data_win["items"][0]["net_pnl"] == 94.00

    # 3. Filter by result=CANCELLED
    resp_cancel = await client.get("/api/v1/trades/history?account_id=1&result=CANCELLED", headers=auth_headers)
    assert resp_cancel.status_code == 200
    data_cancel = resp_cancel.json()
    assert data_cancel["total"] == 1
    assert data_cancel["items"][0]["id"] == 103
    assert data_cancel["items"][0]["result"] == "CANCELLED"

    # 4. Filter by symbol=ETHUSDT
    resp_sym = await client.get("/api/v1/trades/history?account_id=1&symbol=ETHUSDT", headers=auth_headers)
    assert resp_sym.status_code == 200
    assert resp_sym.json()["total"] == 1
    assert resp_sym.json()["items"][0]["symbol"] == "ETHUSDT"


@pytest.mark.asyncio
async def test_get_trade_detail_5_level_tree(app_and_client, auth_headers):
    """Test deep relational tree retrieval for trade detail view."""
    client, _ = app_and_client
    response = await client.get("/api/v1/trades/101", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()

    assert data["trade_id"] == 101
    assert data["symbol"] == "BTCUSDT"

    # 1. Risk details
    assert data["risk_details"] is not None
    assert data["risk_details"]["risk_amount_usdt"] == 100.00
    assert data["risk_details"]["required_margin"] == 250.00

    # 2. Orders
    assert len(data["orders"]) == 1
    assert data["orders"][0]["purpose"] == "ENTRY"
    assert data["orders"][0]["status"] == "FILLED"

    # 3. Executions
    assert len(data["executions"]) == 1
    assert data["executions"][0]["commission"] == 2.50

    # 4. Events
    assert len(data["events"]) == 1
    assert data["events"][0]["event_type"] == "TP1_HIT"


@pytest.mark.asyncio
async def test_manual_close_trade_success(app_and_client, auth_headers):
    """Test manual position closure via market order endpoint."""
    client, session_factory = app_and_client

    payload = {"reason": "UI_MANUAL_CLOSE"}
    response = await client.post("/api/v1/trades/101/close", json=payload, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "closed successfully" in data["message"]

    # Verify trade in database is now CLOSED
    async with session_factory() as session:
        trade_repo = UserRepository(session)  # test session verify
        trade_obj = await session.get(Trade, 101)
        assert trade_obj.status == "CLOSED"


# =========================================================================
# 2. NEGATIVE & EDGE CASE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_trades_unauthorized_rejection(app_and_client):
    """Test that all trades endpoints require authentication."""
    client, _ = app_and_client
    assert (await client.get("/api/v1/trades/active")).status_code == 401
    assert (await client.get("/api/v1/trades/history")).status_code == 401
    assert (await client.get("/api/v1/trades/101")).status_code == 401
    assert (await client.post("/api/v1/trades/101/close")).status_code == 401


@pytest.mark.asyncio
async def test_trade_detail_not_found(app_and_client, auth_headers):
    """Test 404 response when querying non-existent trade."""
    client, _ = app_and_client
    response = await client.get("/api/v1/trades/99999", headers=auth_headers)
    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_close_already_closed_trade(app_and_client, auth_headers):
    """Test 400 rejection when attempting to close an already CLOSED trade."""
    client, _ = app_and_client
    response = await client.post(
        "/api/v1/trades/102/close",
        json={"reason": "UI_MANUAL_CLOSE"},
        headers=auth_headers,
    )
    assert response.status_code == 400
    assert "cannot be closed because it is already CLOSED" in response.json()["detail"]


@pytest.mark.asyncio
async def test_manual_close_non_existent_trade(app_and_client, auth_headers):
    """Test 404 rejection when closing a non-existent trade."""
    client, _ = app_and_client
    response = await client.post(
        "/api/v1/trades/99999/close",
        json={"reason": "UI_MANUAL_CLOSE"},
        headers=auth_headers,
    )
    assert response.status_code == 404
