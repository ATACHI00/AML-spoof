"""AML Monitor — Database engine and session management.

Async SQLAlchemy 2.0 engine with asyncpg driver.
Engine is created lazily to support test-time URL override.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

_engine = None
_async_session_factory = None


def _get_engine():
    """Get or create the async engine (lazy initialization)."""
    global _engine
    if _engine is None:
        url = settings.database_url
        if url.startswith("sqlite"):
            # SQLite requires different settings for async
            _engine = create_async_engine(
                url,
                echo=settings.debug,
                pool_size=1,
                max_overflow=0,
                connect_args={"check_same_thread": False}
            )
        else:
            _engine = create_async_engine(
                url,
                echo=settings.debug,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
            )
    return _engine


def _get_session_factory():
    """Get or create the session factory (lazy initialization)."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields a database session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Expose engine for shutdown cleanup
def get_engine():
    """Get the engine (synchronous, for shutdown)."""
    return _get_engine()