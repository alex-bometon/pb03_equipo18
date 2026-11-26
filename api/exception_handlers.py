"""Tratamiento centralizado de excepciones HTTP."""

from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from api.credential_validation import (
    EmailInvalidoError,
    PasswordInvalidaError,
)
from api.error_catalog import ERROR_CATALOG, ErrorCode
from api.errors import ApiError
from api.request_context import REQUEST_ID_HEADER, get_request_id
from api.schemas import ErrorOut
from src.input_validation import (
    PreguntaDemasiadoLargaError,
    PreguntaInvalidaError,
    PreguntaTipoInvalidoError,
    PreguntaVaciaError,
)


# =========================================================
# CORRESPONDENCIAS DE ERRORES
# =========================================================


QUESTION_ERROR_CODES = {
    PreguntaVaciaError: ErrorCode.EMPTY_QUESTION,
    PreguntaDemasiadoLargaError: ErrorCode.QUESTION_TOO_LONG,
    PreguntaTipoInvalidoError: ErrorCode.VALIDATION_ERROR,
}


PASSWORD_ERROR_CODES = {
    ("POST", "/auth/register", "password"):
        ErrorCode.INVALID_PASSWORD,
    ("POST", "/auth/login", "password"):
        ErrorCode.INVALID_CREDENTIALS,
    ("PATCH", "/auth/password", "current_password"):
        ErrorCode.INVALID_CREDENTIALS,
    ("PATCH", "/auth/password", "new_password"):
        ErrorCode.INVALID_PASSWORD,
}


VALIDATION_ERROR_PRIORITY = (
    ErrorCode.INVALID_CREDENTIALS,
    ErrorCode.INVALID_THREAD_ID,
    ErrorCode.INVALID_EMAIL,
    ErrorCode.INVALID_PASSWORD,
    ErrorCode.EMPTY_QUESTION,
    ErrorCode.QUESTION_TOO_LONG,
    ErrorCode.INVALID_LOCATION,
    ErrorCode.INVALID_MAX_STEPS,
    ErrorCode.VALIDATION_ERROR,
)


FRAMEWORK_ERROR_CODES = {
    ERROR_CATALOG[code].status_code: code
    for code in (
        ErrorCode.BAD_REQUEST,
        ErrorCode.ROUTE_NOT_FOUND,
        ErrorCode.METHOD_NOT_ALLOWED,
    )
}


ASK_ROUTES = frozenset({
    ("POST", "/ask"),
    ("POST", "/ask/image"),
})


THREAD_ROUTES = frozenset({
    ("GET", "/threads/{thread_id}"),
    ("GET", "/threads/{thread_id}/messages"),
    ("GET", "/api-keys/{api_key_id}/threads/{thread_id}"),
    ("GET", "/api-keys/{api_key_id}/threads/{thread_id}/messages"),
})


# =========================================================
# TRADUCCIÓN DE ERRORES DE VALIDACIÓN
# =========================================================


def resolve_question_error_code(
    exc: PreguntaInvalidaError,
) -> ErrorCode:
    """Traduce una excepción de validación de preguntas."""
    return QUESTION_ERROR_CODES.get(
        type(exc),
        ErrorCode.VALIDATION_ERROR,
    )


def _resolve_validation_item(
    error: Mapping[str, Any],
    method: str,
    route: str | None,
) -> ErrorCode:
    """Identifica el código de un error individual."""
    location = tuple(error.get("loc", ()))
    context = error.get("ctx") or {}
    original = context.get("error")

    operation = (method, route)

    if error.get("type") == "extra_forbidden":
        return ErrorCode.VALIDATION_ERROR

    # Validaciones de credenciales.
    if (
        isinstance(original, EmailInvalidoError)
        and location == ("body", "email")
        and operation in {
            ("POST", "/auth/register"),
            ("POST", "/auth/login"),
        }
    ):
        return ErrorCode.INVALID_EMAIL

    if (
        isinstance(original, PasswordInvalidaError)
        and len(location) == 2
        and location[0] == "body"
    ):
        return PASSWORD_ERROR_CODES.get(
            (method, route, location[1]),
            ErrorCode.VALIDATION_ERROR,
        )

    # Validaciones de las consultas al asistente.
    if operation in ASK_ROUTES:
        if (
            location == ("body", "pregunta")
            and isinstance(original, PreguntaInvalidaError)
        ):
            return resolve_question_error_code(original)

        if location == ("body", "thread_id"):
            return ErrorCode.INVALID_THREAD_ID

        if location == ("body", "max_steps"):
            return ErrorCode.INVALID_MAX_STEPS

        if location in {
            ("body", "ubicacion"),
            ("body", "ubicacion", "latitud"),
            ("body", "ubicacion", "longitud"),
            ("body", "latitud"),
            ("body", "longitud"),
        }:
            return ErrorCode.INVALID_LOCATION

    # Validaciones de las aprobaciones HITL.
    if (
        operation == ("POST", "/approve")
        and location == ("body", "thread_id")
    ):
        return ErrorCode.INVALID_THREAD_ID

    # Validaciones de parámetros de ruta.
    if (
        operation in THREAD_ROUTES
        and location == ("path", "thread_id")
    ):
        return ErrorCode.INVALID_THREAD_ID

    return ErrorCode.VALIDATION_ERROR


def resolve_validation_error_code(
    request: Request,
    errors: Sequence[Mapping[str, Any]],
) -> ErrorCode:
    """Selecciona el código prioritario de la validación."""
    route = getattr(request.scope.get("route"), "path", None)

    codes = {
        _resolve_validation_item(
            error,
            request.method,
            route,
        )
        for error in errors
    }

    return next(
        (
            code
            for code in VALIDATION_ERROR_PRIORITY
            if code in codes
        ),
        ErrorCode.VALIDATION_ERROR,
    )


# =========================================================
# CONSTRUCCIÓN DE RESPUESTAS
# =========================================================


def build_error_response(
    request: Request,
    code: ErrorCode,
    *,
    retry_after: int | None = None,
    allow: str | None = None,
) -> JSONResponse:
    """Construye una respuesta de error desde el catálogo."""
    definition = ERROR_CATALOG[code]
    request_id = get_request_id(request)

    error = ErrorOut(
        code=code,
        message=definition.message,
        request_id=request_id,
    )

    headers = {
        REQUEST_ID_HEADER: request_id,
    }

    if (
        code == ErrorCode.RATE_LIMIT_EXCEEDED
        and retry_after is not None
    ):
        headers["Retry-After"] = str(retry_after)

    if (
        code == ErrorCode.METHOD_NOT_ALLOWED
        and allow is not None
    ):
        headers["Allow"] = allow

    request.state.error_code = code.value

    return JSONResponse(
        status_code=definition.status_code,
        content=error.model_dump(mode="json"),
        headers=headers,
    )


# =========================================================
# MANEJADORES DE EXCEPCIONES
# =========================================================


async def handle_api_error(
    request: Request,
    exc: ApiError,
) -> JSONResponse:
    """Gestiona los errores controlados de la API."""
    return build_error_response(
        request,
        exc.code,
        retry_after=exc.retry_after,
    )


async def handle_request_validation_error(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Gestiona los incumplimientos del contrato de entrada."""
    code = resolve_validation_error_code(
        request,
        exc.errors(),
    )

    return build_error_response(request, code)


async def handle_http_exception(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Gestiona las excepciones HTTP del framework."""
    code = FRAMEWORK_ERROR_CODES.get(
        exc.status_code,
        ErrorCode.INTERNAL_SERVER_ERROR,
    )

    allow = None

    if code == ErrorCode.METHOD_NOT_ALLOWED:
        allow = next(
            (
                value
                for name, value in (exc.headers or {}).items()
                if name.lower() == "allow"
            ),
            None,
        )

    return build_error_response(
        request,
        code,
        allow=allow,
    )


async def handle_unexpected_error(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Gestiona los fallos internos inesperados."""
    return build_error_response(
        request,
        ErrorCode.INTERNAL_SERVER_ERROR,
    )


# =========================================================
# REGISTRO DE MANEJADORES
# =========================================================


def register_exception_handlers(app: FastAPI) -> None:
    """Registra los manejadores de excepciones de la API."""
    app.add_exception_handler(
        ApiError,
        handle_api_error,
    )

    app.add_exception_handler(
        RequestValidationError,
        handle_request_validation_error,
    )

    app.add_exception_handler(
        HTTPException,
        handle_http_exception,
    )

    app.add_exception_handler(
        Exception,
        handle_unexpected_error,
    )