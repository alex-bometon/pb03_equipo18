"""Middleware HTTP y observabilidad de ReciclaTÍA."""

import json
import logging
from datetime import datetime, timezone
from time import perf_counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from tempfile import SpooledTemporaryFile

from fastapi import Request
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.config import IMAGE_MULTIPART_OVERHEAD_BYTES
from api.errors import ApiError
from api.error_catalog import ErrorCode
from api.exception_handlers import (
    handle_api_error,
    handle_unexpected_error,
)
from api.request_context import REQUEST_ID_HEADER, get_request_id


HTTP_LOGGER = logging.getLogger("reciclatia.http")

HTTP_METHODS = frozenset({
    "GET", "POST", "PUT", "PATCH", "DELETE",
    "HEAD", "OPTIONS", "CONNECT", "TRACE",
})


def configure_http_logging(level: str) -> None:
    """Configura los registros HTTP sin duplicar manejadores."""
    HTTP_LOGGER.setLevel(level)
    HTTP_LOGGER.propagate = False

    if not HTTP_LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        HTTP_LOGGER.addHandler(handler)


def _get_route_pattern(request: Request) -> str:
    """Obtiene el patrón de ruta sin registrar parámetros."""
    if (
        request.method == "OPTIONS"
        and "origin" in request.headers
        and "access-control-request-method" in request.headers
    ):
        return "PREFLIGHT"

    route = request.scope.get("route")
    pattern = getattr(route, "path", None)

    if isinstance(pattern, str):
        return pattern

    endpoint = request.scope.get("endpoint")

    if endpoint is not None:
        for registered_route in request.app.routes:
            if getattr(registered_route, "endpoint", None) is endpoint:
                return registered_route.path

    return "UNMATCHED"


def log_http_request(
    request: Request,
    status_code: int | None,
    duration_ms: float,
) -> None:
    """Registra exclusivamente los campos HTTP autorizados."""
    state = request.state
    error_code = getattr(state, "error_code", None)
    thread_id = getattr(state, "thread_id", None)
    api_key_id = getattr(state, "api_key_id", None)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": get_request_id(request),
        "method": (
            request.method
            if request.method in HTTP_METHODS
            else "OTHER"
        ),
        "path": _get_route_pattern(request),
        "thread_id": (
            str(thread_id) if thread_id is not None else None
        ),
        "api_key_id": (
            str(api_key_id) if api_key_id is not None else None
        ),
        "role": getattr(state, "role", None),
        "duration_ms": round(duration_ms, 3),
        "status_code": status_code,
        "error_code": error_code,
    }

    if (
        error_code == ErrorCode.INTERNAL_SERVER_ERROR.value
        or (status_code is not None and status_code >= 500)
    ):
        level = logging.ERROR
    elif status_code is None or status_code >= 400:
        level = logging.WARNING
    else:
        level = logging.INFO

    HTTP_LOGGER.log(
        level,
        json.dumps(record, ensure_ascii=False),
    )


@asynccontextmanager
async def _cuerpo_limitado(
    receive: Receive,
    max_bytes: int,
) -> AsyncIterator[Receive | None]:
    """Recibe y reproduce un cuerpo HTTP de tamaño limitado."""
    tamano_bloque = 64 * 1024

    with SpooledTemporaryFile(max_size=tamano_bloque, mode="w+b") as temporal:
        total = 0

        while True:
            mensaje = await receive()

            if mensaje["type"] == "http.disconnect":
                yield None
                return

            bloque = mensaje.get("body", b"")
            total += len(bloque)

            if total > max_bytes:
                raise ApiError(ErrorCode.IMAGE_FILE_TOO_LARGE)

            if bloque:
                await run_in_threadpool(temporal.write, bloque)

            if not mensaje.get("more_body", False):
                break

        await run_in_threadpool(temporal.seek, 0)
        pendiente = total

        async def reproducir() -> Message:
            """Entrega el cuerpo validado a la aplicación interna."""
            nonlocal pendiente

            if pendiente is None:
                return await receive()

            bloque = await run_in_threadpool(
                temporal.read,
                min(pendiente, tamano_bloque),
            )

            pendiente -= len(bloque)
            more_body = pendiente > 0

            if not more_body:
                pendiente = None
                await run_in_threadpool(temporal.close)

            return {
                "type": "http.request",
                "body": bloque,
                "more_body": more_body,
            }

        yield reproducir


class RequestMiddleware:
    """Gestiona la trazabilidad y las respuestas HTTP."""

    def __init__(self, app: ASGIApp) -> None:
        """Conserva la aplicación ASGI interna."""
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        """Procesa una petición y registra su resultado."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        request = Request(scope, receive)
        request_id = get_request_id(request)

        status_code: int | None = None
        response_started = False

        async def send_with_context(message: Message) -> None:
            """Añade trazabilidad al inicio de la respuesta."""
            nonlocal status_code, response_started

            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID_HEADER] = request_id

                response_started = True

                await send(message)

                status_code = message["status"]
                return

            await send(message)

        async def safe_app(
            inner_scope: Scope,
            inner_receive: Receive,
            inner_send: Send,
        ) -> None:
            """Controla la recepción y los fallos de la aplicación."""
            try:
                if (
                    request.method == "POST"
                    and inner_scope["path"] in {"/ask/image", "/ask/image/"}
                ):
                    max_bytes = (
                        settings.IMAGE_UPLOAD_MAX_BYTES
                        + IMAGE_MULTIPART_OVERHEAD_BYTES
                    )

                    longitud = request.headers.get("content-length")

                    if longitud is not None:
                        try:
                            declarada = int(longitud)
                        except ValueError:
                            raise ApiError(ErrorCode.BAD_REQUEST) from None

                        if declarada < 0:
                            raise ApiError(ErrorCode.BAD_REQUEST)

                        if declarada > max_bytes:
                            raise ApiError(ErrorCode.IMAGE_FILE_TOO_LARGE)

                    async with _cuerpo_limitado(
                        inner_receive,
                        max_bytes,
                    ) as receptor:
                        if receptor is None:
                            return

                        await self.app(inner_scope, receptor, inner_send)

                    return

                await self.app(
                    inner_scope,
                    inner_receive,
                    inner_send,
                )

            except ApiError as exc:
                if response_started:
                    raise

                response = await handle_api_error(request, exc)

                await response(inner_scope, inner_receive, inner_send)

            except Exception as exc:
                if response_started:
                    raise

                response = await handle_unexpected_error(
                    request,
                    exc,
                )

                await response(inner_scope, inner_receive, inner_send)

        try:
            settings = request.app.state.settings

            cors = CORSMiddleware(
                safe_app,
                allow_origins=settings.CORS_ORIGINS,
                allow_methods=["GET", "POST", "PATCH", "DELETE"],
                allow_headers=[
                    "Content-Type",
                    "X-API-Key",
                    "Authorization",
                    "X-API-Key-Id",
                ],
                expose_headers=[REQUEST_ID_HEADER, "Retry-After"],
                allow_credentials=False,
            )

            await cors(scope, receive, send_with_context)

        except Exception as exc:
            request.state.error_code = (
                ErrorCode.INTERNAL_SERVER_ERROR.value
            )

            if response_started:
                raise RuntimeError(
                    "Fallo durante la transmisión de la respuesta."
                ) from None

            try:
                response = await handle_unexpected_error(
                    request,
                    exc,
                )

                await response(scope, receive, send_with_context)

            except Exception:
                raise RuntimeError(
                    "No se ha podido generar la respuesta de error."
                ) from None

        finally:
            duration_ms = (perf_counter() - started_at) * 1000

            log_http_request(request, status_code, duration_ms)