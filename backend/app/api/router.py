"""AML Monitor — Main API router.

Aggregates all versioned API routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.health import router as health_router
from app.api.v1 import router as v1_router

api_router = APIRouter()

# Healthcheck (no auth required)
api_router.include_router(health_router)

# Versioned API routes
api_router.include_router(v1_router, prefix="/api/v1")