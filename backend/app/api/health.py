"""AML Monitor — Healthcheck endpoint.

Returns status of database, Redis, and Celery connections.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
async def healthcheck(db: AsyncSession = Depends(get_db)):
    """Healthcheck endpoint — verifies DB, Redis, and Celery connectivity."""
    health = {
        "status": "ok",
        "version": settings.app_version,
        "app": settings.app_name,
    }

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        health["database"] = "connected"
    except Exception as e:
        health["database"] = f"error: {str(e)}"
        health["status"] = "degraded"

    # Redis check
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        health["redis"] = "connected"
    except Exception as e:
        health["redis"] = f"error: {str(e)}"
        health["status"] = "degraded"

    # Celery check (ping the worker)
    try:
        from app.workers.celery_app import celery_app

        ping = celery_app.control.ping(timeout=2.0)
        if ping:
            health["celery"] = "connected"
        else:
            health["celery"] = "no workers"
            health["status"] = "degraded"
    except Exception as e:
        health["celery"] = f"error: {str(e)}"
        health["status"] = "degraded"

    return health