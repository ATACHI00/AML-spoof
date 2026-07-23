"""AML Monitor — API authentication dependency.

Simple API-key based auth for MVP.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(
    api_key: str | None = Security(api_key_header),
) -> str | None:
    """Verify the API key from the X-API-Key header.

    Returns the API key if valid, raises 401 if not.
    If DEBUG mode and no key provided, allows access for development.
    """
    if api_key and api_key in settings.api_keys_list:
        return api_key

    if settings.debug and api_key is None:
        return "dev-access"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing API key",
        headers={"WWW-Authenticate": "API-Key"},
    )