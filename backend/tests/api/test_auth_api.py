"""Integration tests for FastAPI Authentication endpoints and JWT protection."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.infrastructure.persistence.connection import Base
from src.infrastructure.persistence.models.users import User
from src.infrastructure.persistence.repositories.user_repository import UserRepository
from src.utils.security import get_password_hash, create_refresh_token
from src.presentation.api.app import create_app
from src.presentation.api.deps import get_db_session

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


# =========================================================================
# SECURITY & EDGE CASE TESTS
# =========================================================================

@pytest.mark.asyncio
async def test_security_token_tampered_signature(app_and_client):
    """Test that a JWT signed with a forged/different secret is rejected."""
    client, _ = app_and_client
    import jwt
    from datetime import datetime, timezone, timedelta

    tampered_token = jwt.encode(
        {"sub": "admin", "role": "ADMIN", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "completely-wrong-fake-secret-key-12345",
        algorithm="HS256",
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})
    assert response.status_code == 401
    assert "Could not validate credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_security_token_type_confusion_access_on_refresh(app_and_client):
    """Test that an access token cannot be used to call /refresh (Token Type Confusion attack)."""
    client, _ = app_and_client
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminPass123!"},
    )
    access_token = login_resp.json()["access_token"]

    # Try calling /refresh with access_token instead of refresh_token
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": access_token})
    assert response.status_code == 401
    assert "Invalid refresh token payload" in response.json()["detail"]


@pytest.mark.asyncio
async def test_security_token_type_confusion_refresh_on_protected_endpoint(app_and_client):
    """Test that a refresh token cannot be used as Bearer token on protected endpoints."""
    client, _ = app_and_client
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "AdminPass123!"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    # Try calling /me with refresh_token
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_token}"})
    assert response.status_code == 401
    assert "Invalid token payload or token type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_security_token_expired(app_and_client):
    """Test that an expired JWT token is rejected with 401."""
    client, _ = app_and_client
    from datetime import timedelta
    from src.utils.security import create_access_token

    expired_token = create_access_token(
        data={"sub": "admin", "role": "ADMIN"},
        expires_delta=timedelta(seconds=-10),  # Expired 10 seconds ago
    )
    response = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert response.status_code == 401
    assert "Token has expired" in response.json()["detail"]


@pytest.mark.asyncio
async def test_edge_case_case_insensitive_and_whitespace_login(app_and_client):
    """Test that usernames with leading/trailing whitespaces and mixed case log in seamlessly."""
    client, _ = app_and_client
    payload = {
        "username": "   AdMiN   ",
        "password": "AdminPass123!",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 200
    assert response.json()["user"]["username"] == "admin"


@pytest.mark.asyncio
async def test_edge_case_malformed_auth_headers(app_and_client):
    """Test various malformed Authorization headers."""
    client, _ = app_and_client
    # 1. Missing Bearer prefix
    resp1 = await client.get("/api/v1/auth/me", headers={"Authorization": "Basic 12345"})
    assert resp1.status_code == 401

    # 2. Empty Authorization header
    resp2 = await client.get("/api/v1/auth/me", headers={"Authorization": ""})
    assert resp2.status_code == 401


@pytest.mark.asyncio
async def test_validation_errors_pydantic_custom_handler(app_and_client):
    """Test that validation errors trigger custom 422 JSON response schema."""
    client, _ = app_and_client
    # Password too short (< 6 chars)
    payload = {
        "username": "admin",
        "password": "123",
    }
    response = await client.post("/api/v1/auth/login", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "password" in data["detail"]

