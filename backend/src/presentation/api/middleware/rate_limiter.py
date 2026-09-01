"""IP-based sliding-window rate limiting middleware for FastAPI REST API endpoints."""

import time
import asyncio
from collections import defaultdict, deque
from typing import Dict, Deque, Set, Optional, Callable, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from config.settings import settings


class InMemoryRateLimiter:
    """Sliding-window in-memory rate limiter per IP address."""

    def __init__(self, requests_per_minute: int = 120, window_seconds: int = 60) -> None:
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._history: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def is_allowed(self, client_ip: str) -> Tuple[bool, int, int]:
        """Check whether a request from client_ip is allowed.

        Returns:
            Tuple of (is_allowed: bool, remaining_requests: int, retry_after_seconds: int)
        """
        now = time.time()
        window_start = now - self.window_seconds

        async with self._lock:
            timestamps = self._history[client_ip]

            # Evict timestamps outside current sliding window
            while timestamps and timestamps[0] <= window_start:
                timestamps.popleft()

            if len(timestamps) >= self.requests_per_minute:
                oldest = timestamps[0]
                retry_after = max(1, int(oldest + self.window_seconds - now))
                return False, 0, retry_after

            # Record this request timestamp
            timestamps.append(now)
            remaining = max(0, self.requests_per_minute - len(timestamps))
            return True, remaining, 0

    async def reset(self) -> None:
        """Clear all rate limit history."""
        async with self._lock:
            self._history.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Starlette middleware enforcing IP-based sliding window rate limits."""

    EXEMPT_PATHS: Set[str] = {
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
    }

    def __init__(
        self,
        app,
        limiter: Optional[InMemoryRateLimiter] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        super().__init__(app)
        rpm = getattr(settings, "RATE_LIMIT_PER_MINUTE", 120)
        self.limiter = limiter or InMemoryRateLimiter(requests_per_minute=rpm)
        self.enabled = enabled if enabled is not None else getattr(settings, "RATE_LIMIT_ENABLED", True)

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP address, checking proxy forwarding headers first."""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            # First IP in comma-separated list is the client IP
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip WebSockets and exempted health/docs paths
        if request.scope.get("type") == "websocket" or request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        if not self.enabled:
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        is_allowed, remaining, retry_after = await self.limiter.is_allowed(client_ip)

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Rate limit exceeded. Try again in {retry_after} seconds.",
                    "code": "RATE_LIMIT_EXCEEDED",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(self.limiter.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response: Response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
