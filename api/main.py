
"""Punto de entrada del backend HTTP de ReciclaTÍA."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import load_settings
from api.exception_handlers import register_exception_handlers
from src.db import (
    check_database,
    create_db_engine,
    ensure_schema,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Gestiona el ciclo de vida del backend."""

    settings = load_settings()
    app.state.settings = settings

    if settings.DATABASE_URL is None:
        raise RuntimeError(
            "DATABASE_URL no está configurada."
        )

    engine = None

    try:
        try:
            engine = create_db_engine(
                settings.DATABASE_URL.get_secret_value(),
                pool_size=settings.DB_POOL_SIZE,
                max_overflow=settings.DB_MAX_OVERFLOW,
                pool_timeout=settings.DB_POOL_TIMEOUT_SECONDS,
                connect_timeout=settings.DB_CONNECT_TIMEOUT_SECONDS,
                statement_timeout=settings.DB_STATEMENT_TIMEOUT_SECONDS,
                lock_timeout=settings.DB_LOCK_TIMEOUT_SECONDS,
            )

            check_database(engine)
            ensure_schema(engine)

        except Exception:
            raise RuntimeError(
                "No se ha podido inicializar PostgreSQL."
            ) from None

        app.state.engine = engine

        yield

    finally:
        if engine is not None:
            engine.dispose()


app = FastAPI(
    title="ReciclaTÍA API",
    description="API REST del asistente de gestión de residuos de Madrid.",
    lifespan=lifespan,
)

register_exception_handlers(app)
