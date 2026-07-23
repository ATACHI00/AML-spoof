"""Rate limiting middleware for FastAPI.

Uses Redis for distributed rate limiting across multiple backend instances.
Supports per-API-key and per-IP limiting.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from redis import asyncio as aioredis

from app.config import settings

# Default rate limits (requests per window)
DEFAULT_LIMITS = {
    "default": {"requests": 100, "window": 60},  # 100 req/min
    "auth": {"requests": 10, "window": 60},       # 10 req/min for auth
    "api": {"requests": 100, "window": 60},       # 100 req/min for API
}


class RateLimiter:
    """Redis-backed rate limiter using sliding window algorithm."""

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or settings.redis_url
        self._redis: aioredis.Redis | None = None
        self._limits = DEFAULT_LIMITS

    async def _get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_timeout=5.0,
            )
        return self._redis

    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    async def is_allowed(
        self,
        key: str,
        limit: int = 100,
        window: int = 60,
    ) -> tuple[bool, int, int]:
        """Check if request is allowed under rate limit.

        Args:
            key: Unique identifier (API key or IP address)
            limit: Maximum requests per window
            window: Time window in seconds

        Returns:
            Tuple of (allowed, remaining_requests, reset_time)
        """
        redis = await self._get_redis()

        now = time.time()
        window_start = now - window

        # Use pipeline for atomic operation
        pipe = redis.pipeline()
        pipe.zremrangebyscore(key, "-inf", window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, window)
        results = await pipe.execute()

        current_count = results[2]
        remaining = max(0, limit - current_count)
        reset_time = int(now + window)

        if current_count >= limit:
            return False, remaining, reset_time
        return True, remaining, reset_time

    async def get_usage(self, key: str, window: int = 60) -> int:
        """Get current request count for a key."""
        redis = await self._get_redis()
        now = time.time()
        window_start = now - window
        return await redis.zcount(key, window_start, now)


# Global rate limiter instance
_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get the global rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


# ------------------------------------------------------------------
# FastAPI middleware
# ------------------------------------------------------------------


async def rate_limit_middleware(request: Request, call_next: Callable) -> Response:
    """FastAPI middleware for rate limiting.

    Applies different limits based on endpoint path.
    """
    # Skip rate limiting for health checks and docs
    if any(
        path in request.url.path
        for path in ["/health", "/docs", "/redoc", "/openapi.json"]
    ):
        return await call_next(request)

    # Get client identifier
    api_key = request.headers.get("X-API-Key")
    client_ip = request.client.host if request.client else "unknown"

    # Determine limit config
    if "/auth" in request.url.path or "/login" in request.url.path:
        limit_config = DEFAULT_LIMITS["auth"]
    elif api_key:
        limit_config = DEFAULT_LIMITS["api"]
    else:
        limit_config = DEFAULT_LIMITS["default"]

    # Use API key for rate limiting if provided, otherwise IP
    rate_limit_key = api_key or f"ip:{client_ip}"
    rate_limit_key = f"rl:{request.url.path}:{rate_limit_key}"

    limiter = get_rate_limiter()

    try:
        allowed, remaining, reset_time = await limiter.is_allowed(
            rate_limit_key,
            limit=limit_config["requests"],
            window=limit_config["window"],
        )
    except Exception:
        # If Redis is unavailable, allow request but log warning
        from logging import getLogger

        logger = getLogger(__name__)
        logger.warning("Redis unavailable, allowing request", exc_info=True)
        return await call_next(request)

    # Add rate limit headers
    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(limit_config["requests"])
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_time)

    if not allowed:
        retry_after = reset_time - int(time.time())
        return JSONResponse(
            status_code=429,
            headers={
                "Retry-After": str(max(1, retry_after)),
                "X-RateLimit-Retry-After": str(max(1, retry_after)),
            },
            content={
                "detail": "Rate limit exceeded",
                "retry_after": max(1, retry_after),
            },
        )

    return response


# ------------------------------------------------------------------
# Utility functions
# ------------------------------------------------------------------


async def check_rate_limit(
    identifier: str,
    path: str,
    limit: int = 100,
    window: int = 60,
) -> tuple[bool, int, int]:
    """Check rate limit for a specific identifier.

    Returns:
        Tuple of (allowed, remaining, reset_time)
    """
    limiter = get_rate_limiter()
    rate_key = f"rl:{path}:{identifier}"
    return await limiter.is_allowed(rate_key, limit, window)


async def get_rate_limit_info(identifier: str, path: str, window: int = 60) -> int:
    """Get current rate limit usage for an identifier."""
    limiter = get_rate_limiter()
    rate_key = f"rl:{path}:{identifier}"
    return await limiter.get_usage(rate_key, window)
