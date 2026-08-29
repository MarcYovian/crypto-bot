"""Comprehensive API test suite for WebSocket Real-time Event Streaming."""

import pytest
import pytest_asyncio
from decimal import Decimal
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.utils.security import get_password_hash, create_access_token
from src.utils.cache import in_memory_cache
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session
from src.presentation.websocket.ws_manager import ws_manager

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_db():
    """Create in-memory SQLite database, app instance, and seed users."""
    await in_memory_cache.clear()

    engine = create_async_engine(
        TEST_DB_URL,
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
        await session.commit()

    yield app

    await engine.dispose()


def get_token_for(username: str = "admin") -> str:
    """Helper to generate a valid access token."""
    return create_access_token({"sub": username, "role": "ADMIN", "type": "access"})


def test_ws_connection_authorized_success(app_and_db):
    """Test successful WebSocket handshake and connection with valid token."""
    app = app_and_db
    token = get_token_for("admin")
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        msg = websocket.receive_json()
        assert msg["event"] == "CONNECTED"
        assert "user" in msg["data"]
        assert msg["data"]["user"] == "admin"


def test_ws_connection_missing_token_rejected(app_and_db):
    """Test that connection without token is immediately rejected with 1008."""
    app = app_and_db
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/ws"):
            pass
    assert exc_info.value.code == 1008


def test_ws_connection_invalid_token_rejected(app_and_db):
    """Test that connection with forged/invalid token is rejected with 1008."""
    app = app_and_db
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/ws?token=invalid.tampered.signature"):
            pass
    assert exc_info.value.code == 1008


@pytest.mark.asyncio
async def test_ws_broadcast_trade_opened_event(app_and_db):
    """Test broadcasting TRADE_OPENED event to connected client."""
    app = app_and_db
    token = get_token_for("admin")
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        # Initial connected message
        init_msg = websocket.receive_json()
        assert init_msg["event"] == "CONNECTED"

        # Trigger broadcast
        await ws_manager.broadcast(
            "TRADE_OPENED",
            {
                "trade_id": 101,
                "symbol": "BTCUSDT",
                "side": "BUY",
                "entry_price": 50000.0,
                "position_size": 0.02,
                "leverage": 20,
            },
        )

        event_msg = websocket.receive_json()
        assert event_msg["event"] == "TRADE_OPENED"
        assert event_msg["data"]["trade_id"] == 101
        assert event_msg["data"]["symbol"] == "BTCUSDT"
        assert event_msg["data"]["side"] == "BUY"
        assert event_msg["data"]["entry_price"] == 50000.0


@pytest.mark.asyncio
async def test_ws_broadcast_tp_sl_hit_events(app_and_db):
    """Test broadcasting TP_HIT and SL_HIT events."""
    app = app_and_db
    token = get_token_for("admin")
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        websocket.receive_json()  # Consume CONNECTED

        # Broadcast TP_HIT
        await ws_manager.broadcast(
            "TP_HIT",
            {
                "trade_id": 101,
                "symbol": "BTCUSDT",
                "tp_level": 1,
                "fill_price": 51000.0,
                "realized_pnl": 20.0,
            },
        )
        tp_msg = websocket.receive_json()
        assert tp_msg["event"] == "TP_HIT"
        assert tp_msg["data"]["tp_level"] == 1
        assert tp_msg["data"]["realized_pnl"] == 20.0

        # Broadcast SL_HIT
        await ws_manager.broadcast(
            "SL_HIT",
            {
                "trade_id": 101,
                "symbol": "BTCUSDT",
                "fill_price": 49000.0,
                "realized_pnl": -20.0,
            },
        )
        sl_msg = websocket.receive_json()
        assert sl_msg["event"] == "SL_HIT"
        assert sl_msg["data"]["realized_pnl"] == -20.0


@pytest.mark.asyncio
async def test_ws_broadcast_circuit_breaker_event(app_and_db):
    """Test broadcasting CIRCUIT_BREAKER_TRIGGERED and BOT_STATUS_CHANGED events."""
    app = app_and_db
    token = get_token_for("viewer")
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        websocket.receive_json()  # Consume CONNECTED

        await ws_manager.broadcast(
            "CIRCUIT_BREAKER_TRIGGERED",
            {
                "reason": "Daily loss limit reached",
                "daily_loss": 6.5,
                "max_limit": 6.0,
            },
        )
        cb_msg = websocket.receive_json()
        assert cb_msg["event"] == "CIRCUIT_BREAKER_TRIGGERED"
        assert cb_msg["data"]["daily_loss"] == 6.5

        await ws_manager.broadcast(
            "BOT_STATUS_CHANGED",
            {"is_paused": True, "trading_status": "PAUSED", "action": "PAUSE"},
        )
        status_msg = websocket.receive_json()
        assert status_msg["event"] == "BOT_STATUS_CHANGED"
        assert status_msg["data"]["is_paused"] is True


@pytest.mark.asyncio
async def test_ws_multi_client_broadcast(app_and_db):
    """Test broadcasting event simultaneously to multiple connected clients."""
    app = app_and_db
    token1 = get_token_for("admin")
    token2 = get_token_for("viewer")
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/ws?token={token1}") as ws1:
        with client.websocket_connect(f"/api/v1/ws?token={token2}") as ws2:
            ws1.receive_json()  # Consume CONNECTED
            ws2.receive_json()  # Consume CONNECTED

            await ws_manager.broadcast(
                "TICKER_UPDATE",
                {"symbol": "BTCUSDT", "mark_price": 50500.25},
            )

            msg1 = ws1.receive_json()
            msg2 = ws2.receive_json()

            assert msg1["event"] == "TICKER_UPDATE"
            assert msg1["data"]["mark_price"] == 50500.25
            assert msg2["event"] == "TICKER_UPDATE"
            assert msg2["data"]["mark_price"] == 50500.25


def test_ws_client_graceful_disconnect(app_and_db):
    """Test client disconnect gracefully removes socket from active connections."""
    app = app_and_db
    token = get_token_for("admin")
    client = TestClient(app)

    initial_conns = len(ws_manager.active_connections)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        websocket.receive_json()
        assert len(ws_manager.active_connections) == initial_conns + 1

    # After exit context, connection is disconnected
    assert len(ws_manager.active_connections) == initial_conns


def test_ws_ping_pong_keepalive(app_and_db):
    """Test keep-alive ping/pong protocol over WebSocket."""
    app = app_and_db
    token = get_token_for("admin")
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as websocket:
        websocket.receive_json()  # Consume CONNECTED

        websocket.send_text("ping")
        resp = websocket.receive_json()
        assert resp["event"] == "PONG"
        assert resp["data"]["status"] == "alive"
