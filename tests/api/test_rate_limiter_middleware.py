"""Unit and integration tests for Rate Limiting middleware."""

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.presentation.api.middleware.rate_limiter import RateLimitMiddleware, InMemoryRateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_allows_requests_within_limit():
    """Verify that requests within the allowed threshold succeed with rate limit headers."""
    app = FastAPI()
    limiter = InMemoryRateLimiter(requests_per_minute=5, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter, enabled=True)

    @app.get("/api/v1/test")
    async def test_endpoint():
        return {"status": "ok"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request 1
        res1 = await client.get("/api/v1/test")
        assert res1.status_code == 200
        assert res1.headers.get("X-RateLimit-Limit") == "5"
        assert res1.headers.get("X-RateLimit-Remaining") == "4"

        # Request 2
        res2 = await client.get("/api/v1/test")
        assert res2.status_code == 200
        assert res2.headers.get("X-RateLimit-Remaining") == "3"


@pytest.mark.asyncio
async def test_rate_limiter_blocks_and_returns_429_on_exceed():
    """Verify that exceeding the rate limit returns 429 Too Many Requests."""
    app = FastAPI()
    limiter = InMemoryRateLimiter(requests_per_minute=3, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter, enabled=True)

    @app.get("/api/v1/data")
    async def data_endpoint():
        return {"data": 123}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Send 3 requests (exhaust limit)
        for _ in range(3):
            res = await client.get("/api/v1/data")
            assert res.status_code == 200

        # 4th request must be blocked
        res_blocked = await client.get("/api/v1/data")
        assert res_blocked.status_code == 429
        data = res_blocked.json()
        assert data["code"] == "RATE_LIMIT_EXCEEDED"
        assert "Retry-After" in res_blocked.headers
        assert res_blocked.headers.get("X-RateLimit-Remaining") == "0"


@pytest.mark.asyncio
async def test_rate_limiter_exempts_health_and_docs():
    """Verify that health check and documentation endpoints are exempted from rate limits."""
    app = FastAPI()
    limiter = InMemoryRateLimiter(requests_per_minute=1, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter, enabled=True)

    @app.get("/health")
    async def health_endpoint():
        return {"status": "ok"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Request health check multiple times beyond the limit of 1
        for _ in range(5):
            res = await client.get("/health")
            assert res.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiter_respects_x_forwarded_for():
    """Verify that rate limiter isolates limits per IP using the X-Forwarded-For header."""
    app = FastAPI()
    limiter = InMemoryRateLimiter(requests_per_minute=2, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter, enabled=True)

    @app.get("/api/v1/profile")
    async def profile_endpoint():
        return {"profile": "user"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # IP 1: exhaust limit (2 requests)
        for _ in range(2):
            res = await client.get("/api/v1/profile", headers={"X-Forwarded-For": "203.0.113.195, 10.0.0.1"})
            assert res.status_code == 200

        # IP 1: 3rd request blocked
        res_blocked = await client.get("/api/v1/profile", headers={"X-Forwarded-For": "203.0.113.195, 10.0.0.1"})
        assert res_blocked.status_code == 429

        # IP 2: distinct IP is still allowed!
        res_ip2 = await client.get("/api/v1/profile", headers={"X-Forwarded-For": "198.51.100.42"})
        assert res_ip2.status_code == 200


@pytest.mark.asyncio
async def test_rate_limiter_disabled_flag():
    """Verify that setting enabled=False disables throttling completely."""
    app = FastAPI()
    limiter = InMemoryRateLimiter(requests_per_minute=1, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter, enabled=False)

    @app.get("/api/v1/unlimited")
    async def unlimited_endpoint():
        return {"status": "ok"}

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for _ in range(5):
            res = await client.get("/api/v1/unlimited")
            assert res.status_code == 200
