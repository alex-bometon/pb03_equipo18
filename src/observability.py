"""Observabilidad estructurada compartida por el núcleo y la API."""

import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import UUID
from collections.abc import Callable, Mapping
from time import perf_counter
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

EVENT_LOGGER = logging.getLogger("reciclatia.events")

LOGGERS_EXTERNOS = (
    "google",
    "google_genai",
    "httpx",
    "httpcore",
    "urllib3",
    "requests",
    "langchain",
    "langchain_core",
    "langchain_google_genai",
    "langgraph",
    "langsmith",
    "sqlalchemy",
    "psycopg",
    "psycopg2",
    "chromadb",
    "multipart",
    "python_multipart",
    "PIL",
    "uvicorn.access",
)

request_id_context: ContextVar[str | None] = ContextVar("request_id", default=None)


def configurar_logger(logger: logging.Logger, level: str) -> None:
    """Configura un logger JSON sin duplicar manejadores."""
    logger.setLevel(level)
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)


def registrar_evento(
    evento: str,
    *,
    nivel: int = logging.INFO,
    thread_id: UUID | None = None,
    duration_ms: float | None = None,
    error_code: str | None = None,
    ambitos: tuple[str, ...] = (),
    retry_after: int | None = None,
    tokens_totales: int | None = None,
) -> None:
    """Registra exclusivamente metadatos técnicos autorizados."""
    registro = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id_context.get(),
        "event": evento,
        "level": logging.getLevelName(nivel),
        "thread_id": str(thread_id) if thread_id else None,
        "duration_ms": (
            round(duration_ms, 3)
            if duration_ms is not None
            else None
        ),
        "error_code": error_code,
        "scopes": list(ambitos),
        "retry_after": retry_after,
        "total_tokens": tokens_totales,
    }

    EVENT_LOGGER.log(nivel, json.dumps(registro, ensure_ascii=False))


def observar_llamada(
    proveedor: str,
    operacion: str,
    llamada: Callable[P, T],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """Ejecuta una llamada y registra su duración y resultado."""
    inicio = perf_counter()

    try:
        resultado = llamada(*args, **kwargs)

    except Exception:
        registrar_evento(
            "provider_failed",
            nivel=logging.ERROR,
            ambitos=(proveedor, operacion),
            duration_ms=(perf_counter() - inicio) * 1000,
        )

        raise

    duracion = (perf_counter() - inicio) * 1000

    uso = getattr(resultado, "usage_metadata", None)

    if isinstance(uso, Mapping):
        tokens = uso.get("total_tokens")
    else:
        tokens = getattr(uso, "total_token_count", None)

    if type(tokens) is not int or tokens < 0:
        tokens = None

    registrar_evento(
        "provider_completed",
        ambitos=(proveedor, operacion),
        duration_ms=duracion,
        tokens_totales=tokens,
    )

    return resultado


def configurar_logs_externos() -> None:
    """Impide emitir registros externos sin sanitizar."""
    pendientes = [
        logging.getLogger(nombre)
        for nombre in LOGGERS_EXTERNOS
    ]

    while pendientes:
        logger = pendientes.pop()

        pendientes.extend(logger.getChildren())

        logger.setLevel(logging.CRITICAL + 1)
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False