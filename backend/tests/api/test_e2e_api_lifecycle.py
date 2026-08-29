"""End-to-End API Lifecycle, Lifespan Hooks, OpenAPI Documentation, and CORS Test Suite."""

import pytest
import pytest_asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator
from decimal import Decimal
from fastapi import FastAPI
from starlette.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models import Exchange, TradingAccount, Instrument
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.utils.security import get_password_hash, create_access_token
from src.utils.cache import in_memory_cache
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session
from main import ApplicationContainer

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def e2e_app_and_db():
    """Create test in-memory DB and test container lifespan."""
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

    test_container = ApplicationContainer()
    test_container.session_maker = session_factory

    @asynccontextmanager
    async def test_lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        await test_container.initialize()
        await test_container.start_background_runners()
        yield
        await test_container.shutdown()

    app = create_app(lifespan=test_lifespan)

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

    yield app, test_container

    await engine.dispose()


def get_auth_headers(role: str = "ADMIN") -> dict:
    """Helper to generate JWT bearer header."""
    token = create_access_token({"sub": "admin" if role == "ADMIN" else "viewer", "role": role, "type": "access"})
    return {"Authorization": f"Bearer {token}"}


def test_healthcheck_endpoint_returns_ok(e2e_app_and_db):
    """Test GET /health returns 200 OK with correct service info."""
    app, _ = e2e_app_and_db
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "crypto-bot-api"
    assert "version" in data


def test_openapi_schema_generation(e2e_app_and_db):
    """Test GET /openapi.json and GET /docs generate complete OpenAPI specifications."""
    app, _ = e2e_app_and_db
    client = TestClient(app)

    # 1. Test Swagger Docs
    docs_resp = client.get("/docs")
    assert docs_resp.status_code == 200
    assert "swagger-ui" in docs_resp.text.lower() or "html" in docs_resp.headers.get("content-type", "")

    # 2. Test OpenAPI JSON schema
    schema_resp = client.get("/openapi.json")
    assert schema_resp.status_code == 200
    schema = schema_resp.json()
    assert schema["info"]["title"] == "SMC CryptoBot Dashboard API"
    assert schema["info"]["version"] == "2.0.0"

    paths = schema.get("paths", {})
    # Verify core HTTP routes are registered in schema
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/analytics/summary" in paths
    assert "/api/v1/trades/active" in paths
    assert "/api/v1/signals" in paths
    assert "/api/v1/watchlist" in paths
    assert "/api/v1/instruments" in paths
    assert "/api/v1/providers" in paths
    assert "/api/v1/strategies" in paths
    assert "/api/v1/calculator/simulate" in paths
    assert "/api/v1/bot/status" in paths
    assert "/api/v1/settings" in paths
    assert "/api/v1/logs" in paths
    assert "/api/v1/reports/export/csv" in paths
    assert "/health" in paths


def test_cors_preflight_headers(e2e_app_and_db):
    """Test CORS preflight OPTIONS request returns correct allow headers."""
    app, _ = e2e_app_and_db
    client = TestClient(app)

    headers = {
        "Origin": "http://localhost:3000",
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization, Content-Type",
    }
    resp = client.options("/api/v1/trades/active", headers=headers)
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") in ("*", "http://localhost:3000")
    assert "GET" in resp.headers.get("access-control-allow-methods", "")


def test_lifespan_startup_initializes_services(e2e_app_and_db):
    """Test that entering lifespan context starts container runners."""
    app, container = e2e_app_and_db

    with TestClient(app) as client:
        # Container should be running
        assert container.running is True
        assert container.scheduler is not None

        # API should respond during active lifespan
        headers = get_auth_headers("ADMIN")
        resp = client.get("/api/v1/bot/status", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_running"] is True


def test_lifespan_graceful_shutdown_cleanup(e2e_app_and_db):
    """Test that exiting lifespan context cleans up container gracefully."""
    app, container = e2e_app_and_db

    with TestClient(app):
        assert container.running is True

    # Exited context manager
    assert container.running is False


def test_concurrent_rest_and_websocket_requests(e2e_app_and_db):
    """Test processing REST requests while WebSocket streaming client is active."""
    app, _ = e2e_app_and_db
    token = create_access_token({"sub": "admin", "role": "ADMIN", "type": "access"})
    client = TestClient(app)

    with client.websocket_connect(f"/api/v1/ws?token={token}") as ws:
        msg = ws.receive_json()
        assert msg["event"] == "CONNECTED"

        # Concurrently perform REST API calls
        headers = {"Authorization": f"Bearer {token}"}
        resp = client.get("/api/v1/analytics/summary", headers=headers)
        assert resp.status_code == 200
        assert "total_balance_usdt" in resp.json()

        resp2 = client.get("/api/v1/watchlist", headers=headers)
        assert resp2.status_code == 200
        assert isinstance(resp2.json(), list)
