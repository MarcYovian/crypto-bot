"""Integration tests for FastAPI Authentication endpoints and JWT protection."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database.connection import Base
from src.database.models.users import User
from src.repository.user_repository import UserRepository
from src.utils.security import get_password_hash, create_refresh_token
from src.api.app import create_app
from src.api.deps import get_db_session

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def app_and_client():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    app = create_app()

    # Override database session dependency for tests
    async def override_get_db_session():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db_session] = override_get_db_session

    # Seed an active admin user and an inactive user
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.create_user(
            username="admin",
            password_hash=get_password_hash("AdminPass123!"),
            role="ADMIN",
            is_active=True,
        )
        await repo.create_user(
            username="disabled_user",
            password_hash=get_password_hash("DisabledPass123!"),
            role="VIEWER",
            is_active=False,
        )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_healthcheck(app_and_client):
    client, _ = app_and_client
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_login_success(app_and_client):
    client, _ = app_and_client
    payload = {
        "username": "admin",
        "password": "AdminPass123!",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "ADMIN"


@pytest.mark.asyncio
async def test_login_invalid_password(app_and_client):
    client, _ = app_and_client
    payload = {
        "username": "admin",
        "password": "WrongPassword123!",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401
    assert "Invalid username or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_non_existent_user(app_and_client):
    client, _ = app_and_client
    payload = {
        "username": "ghost_user",
        "password": "AnyPassword123!",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_disabled_user(app_and_client):
    client, _ = app_and_client
    payload = {
        "username": "disabled_user",
        "password": "DisabledPass123!",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 403
    assert "Account is disabled" in response.json()["detail"]


@pytest.mark.asyncio
async def test_refresh_token_flow(app_and_client):
    client, _ = app_and_client
    # 1. Login first to get refresh token
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminPass123!"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # 2. Call /refresh
    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()
    assert refresh_resp.json()["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_refresh_token_invalid(app_and_client):
    client, _ = app_and_client
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "invalid.jwt.token.string"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_profile(app_and_client):
    client, _ = app_and_client
    # 1. Unauthenticated request should fail (401)
    unauth_resp = await client.get("/api/v1/auth/me")
    assert unauth_resp.status_code == 401

    # 2. Login to get token
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminPass123!"},
    )
    token = login_resp.json()["access_token"]

    # 3. Authenticated request with Bearer token
    headers = {"Authorization": f"Bearer {token}"}
    me_resp = await client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200
    user_data = me_resp.json()
    assert user_data["username"] == "admin"
    assert user_data["role"] == "ADMIN"
    assert user_data["is_active"] is True
