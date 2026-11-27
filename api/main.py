"""Punto de entrada del backend HTTP de ReciclaTÍA."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool

from api.auth_service import bootstrap_admin_api_key
from api.config import load_settings
from api.exception_handlers import register_exception_handlers
from api.middleware import (
    RequestMiddleware,
    configure_http_logging,
)
from api.security import (
    SessionStore,
    create_dummy_password_hash,
)
from api.rate_limit import crear_limitador
from api.service import ControlAdmision, EjecutorAsistente
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
        raise RuntimeError("DATABASE_URL no está configurada.")

    missing_admin = settings.missing_admin_settings()

    if missing_admin:
        fields = ", ".join(missing_admin)

        raise RuntimeError(f"Configuración administrativa incompleta: {fields}")

    engine = None
    ejecutor = None

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
            raise RuntimeError("No se ha podido inicializar PostgreSQL.") from None

        app.state.engine = engine

        try:
            bootstrap_admin_api_key(engine, settings)

        except Exception:
            raise RuntimeError(
                "No se ha podido aprovisionar la administración."
            ) from None

        try:
            app.state.dummy_password_hash = (
                create_dummy_password_hash(settings.BCRYPT_ROUNDS)
            )

            app.state.session_store = SessionStore(
                ttl_seconds=settings.SESSION_TTL_SECONDS,
            )

            app.state.rate_limiter = crear_limitador(settings)

        except Exception:
            raise RuntimeError(
                "No se ha podido inicializar la seguridad."
            ) from None
        
        app.state.admision = ControlAdmision(settings.AGENT_MAX_WORKERS)

        ejecutor = EjecutorAsistente(
            settings,
            app.state.admision,
            app.state.rate_limiter,
        )

        app.state.ejecutor = ejecutor

        configure_http_logging(settings.LOG_LEVEL)

        yield

    finally:
        try:
            if ejecutor is not None:
                await run_in_threadpool(ejecutor.cerrar)

        finally:
            if engine is not None:
                engine.dispose()


app = FastAPI(
    title="ReciclaTÍA API",
    description="API REST del asistente de gestión de residuos de Madrid.",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(RequestMiddleware)