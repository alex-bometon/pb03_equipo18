"""Pruebas del middleware HTTP y la observabilidad."""

import json
import logging
import traceback
from collections.abc import AsyncIterator, Iterator
from datetime import datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient

from api.config import ApiSettings
from api.error_catalog import ERROR_CATALOG, ErrorCode
from api.errors import ApiError
from api.exception_handlers import register_exception_handlers
from api.middleware import (
    HTTP_LOGGER,
    RequestMiddleware,
    configure_http_logging,
)
from api.request_context import REQUEST_ID_HEADER


ORIGIN = "http://localhost:8501"
UNAUTHORIZED_ORIGIN = "https://otro.example.com"
SECRET = "secreto-ficticio-no-registrable"


@pytest.fixture
def app() -> FastAPI:
    """Construye una aplicación sin dependencias externas."""
    application = FastAPI()

    application.state.settings = ApiSettings(
        CORS_ORIGINS=(ORIGIN,),
    )

    application.state.calls = 0

    register_exception_handlers(application)
    application.add_middleware(RequestMiddleware)

    @application.get("/items/{item_id}")
    def get_item(item_id: str) -> dict[str, bool]:
        return {"ok": True}

    @application.post("/ask")
    def ask() -> dict[str, bool]:
        application.state.calls += 1
        return {"ok": True}

    @application.get("/test/error/{code}")
    def controlled_error(code: ErrorCode) -> None:
        raise ApiError(code)

    @application.get("/test/internal")
    def internal_error() -> None:
        raise RuntimeError(SECRET)

    @application.get("/test/stream")
    def broken_stream() -> StreamingResponse:
        async def generate() -> AsyncIterator[bytes]:
            yield b"contenido"
            raise RuntimeError(SECRET)

        return StreamingResponse(generate())

    return application


@pytest.fixture
def client(
    app: FastAPI,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """Proporciona un cliente con captura de registros."""
    monkeypatch.setattr(HTTP_LOGGER, "propagate", True)

    caplog.set_level(
        logging.INFO,
        logger=HTTP_LOGGER.name,
    )

    with TestClient(app) as test_client:
        yield test_client


def get_http_records(
    caplog: pytest.LogCaptureFixture,
) -> list[logging.LogRecord]:
    """Recupera exclusivamente los registros HTTP propios."""
    return [
        record
        for record in caplog.records
        if record.name == HTTP_LOGGER.name
    ]


def test_success_request_id(client: TestClient) -> None:
    """Incluye un identificador en las respuestas satisfactorias."""
    response = client.get("/items/1")

    request_id = response.headers[REQUEST_ID_HEADER]

    assert response.status_code == 200
    assert UUID(request_id).version == 4
    assert str(UUID(request_id)) == request_id


def test_structured_log(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Comprueba la estructura del registro HTTP."""
    response = client.get("/items/1")

    records = get_http_records(caplog)

    assert len(records) == 1

    data = json.loads(records[0].getMessage())

    assert set(data) == {
        "timestamp",
        "request_id",
        "method",
        "path",
        "thread_id",
        "api_key_id",
        "role",
        "duration_ms",
        "status_code",
        "error_code",
    }

    timestamp = datetime.fromisoformat(data["timestamp"])

    assert timestamp.utcoffset() == timedelta(0)
    assert data["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert data["method"] == "GET"
    assert data["path"] == "/items/{item_id}"
    assert data["status_code"] == response.status_code
    assert data["duration_ms"] >= 0
    assert data["thread_id"] is None
    assert data["api_key_id"] is None
    assert data["role"] is None
    assert data["error_code"] is None


def test_client_request_id_ignored(client: TestClient) -> None:
    """No confía en identificadores proporcionados por el cliente."""
    response = client.get(
        "/items/1",
        headers={REQUEST_ID_HEADER: SECRET},
    )

    assert response.headers[REQUEST_ID_HEADER] != SECRET


def test_request_ids_are_unique(client: TestClient) -> None:
    """Genera identificadores independientes para cada petición."""
    first = client.get("/items/1")
    second = client.get("/items/1")

    assert (
        first.headers[REQUEST_ID_HEADER]
        != second.headers[REQUEST_ID_HEADER]
    )


@pytest.mark.parametrize(
    "code, expected_level",
    [
        (ErrorCode.THREAD_NOT_FOUND, logging.WARNING),
        (ErrorCode.VALIDATION_ERROR, logging.WARNING),
        (ErrorCode.RATE_LIMIT_EXCEEDED, logging.WARNING),
        (ErrorCode.SERVICE_UNAVAILABLE, logging.ERROR),
        (ErrorCode.INTERNAL_SERVER_ERROR, logging.ERROR),
    ],
)
def test_error_logging(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    code: ErrorCode,
    expected_level: int,
) -> None:
    """Registra el estado y código efectivos de cada error."""
    response = client.get(f"/test/error/{code.value}")

    records = get_http_records(caplog)

    assert len(records) == 1
    assert records[0].levelno == expected_level

    data = json.loads(records[0].getMessage())

    assert response.status_code == ERROR_CATALOG[code].status_code
    assert data["status_code"] == response.status_code
    assert data["error_code"] == code.value
    assert data["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert data["request_id"] == response.json()["request_id"]


def test_success_logging_level(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Registra las operaciones satisfactorias en nivel INFO."""
    client.get("/items/1")

    records = get_http_records(caplog)

    assert len(records) == 1
    assert records[0].levelno == logging.INFO


def test_unexpected_error(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Controla los fallos internos sin propagar secretos."""
    response = client.get("/test/internal")

    assert response.status_code == 500

    data = response.json()

    assert data["code"] == ErrorCode.INTERNAL_SERVER_ERROR.value
    assert data["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert SECRET not in response.text
    assert SECRET not in caplog.text

    records = get_http_records(caplog)

    assert len(records) == 1
    assert records[0].levelno == logging.ERROR
    assert records[0].exc_info is None


def test_failure_after_response_start(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Evita una segunda respuesta y sanitiza el fallo tardío."""
    with pytest.raises(RuntimeError) as captured:
        client.get("/test/stream")

    formatted = "".join(
        traceback.format_exception(captured.value)
    )

    assert SECRET not in formatted
    assert SECRET not in caplog.text

    records = get_http_records(caplog)

    assert len(records) == 1
    assert records[0].levelno == logging.ERROR

    data = json.loads(records[0].getMessage())

    assert data["status_code"] == 200
    assert data["error_code"] == (
        ErrorCode.INTERNAL_SERVER_ERROR.value
    )


def test_sensitive_information_not_logged(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Excluye parámetros, cabeceras y cuerpos sensibles."""
    client.get(
        f"/items/{SECRET}",
        params={"token": SECRET},
        headers={
            "Authorization": f"Bearer {SECRET}",
            "X-API-Key": SECRET,
        },
    )

    client.post(
        "/ask",
        json={"pregunta": SECRET},
    )

    client.get(f"/unknown/{SECRET}")

    records = get_http_records(caplog)

    assert len(records) == 3
    assert SECRET not in caplog.text

    paths = [
        json.loads(record.getMessage())["path"]
        for record in records
    ]

    assert paths == [
        "/items/{item_id}",
        "/ask",
        "UNMATCHED",
    ]


@pytest.mark.parametrize(
    "path, status",
    [
        ("/items/1", 200),
        ("/ruta-inexistente", 404),
        ("/test/internal", 500),
    ],
)
def test_cors_allowed_origin(
    client: TestClient,
    path: str,
    status: int,
) -> None:
    """Conserva CORS en respuestas satisfactorias y errores."""
    response = client.get(
        path,
        headers={"Origin": ORIGIN},
    )

    assert response.status_code == status
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN

    exposed = {
        name.strip().lower()
        for name in response.headers[
            "Access-Control-Expose-Headers"
        ].split(",")
    }

    assert REQUEST_ID_HEADER.lower() in exposed
    assert "retry-after" in exposed
    assert REQUEST_ID_HEADER in response.headers

    assert (
        "Access-Control-Allow-Credentials"
        not in response.headers
    )


def test_cors_unauthorized_origin(
    client: TestClient,
) -> None:
    """No autoriza el acceso desde un origen no permitido."""
    response = client.get(
        "/items/1",
        headers={"Origin": UNAUTHORIZED_ORIGIN},
    )

    assert "Access-Control-Allow-Origin" not in response.headers
    assert REQUEST_ID_HEADER in response.headers


def test_preflight_allowed(
    client: TestClient,
    app: FastAPI,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Gestiona preflight sin ejecutar el endpoint."""
    response = client.options(
        "/ask",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (
                "content-type,x-api-key"
            ),
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert REQUEST_ID_HEADER in response.headers
    assert app.state.calls == 0

    records = get_http_records(caplog)

    assert len(records) == 1

    data = json.loads(records[0].getMessage())

    assert data["path"] == "PREFLIGHT"
    assert data["status_code"] == 200
    assert data["error_code"] is None


@pytest.mark.parametrize(
    "origin, method, headers",
    [
        (UNAUTHORIZED_ORIGIN, "POST", "content-type"),
        (ORIGIN, "PUT", "content-type"),
        (ORIGIN, "POST", "x-unauthorized-header"),
    ],
)
def test_preflight_rejected(
    client: TestClient,
    app: FastAPI,
    caplog: pytest.LogCaptureFixture,
    origin: str,
    method: str,
    headers: str,
) -> None:
    """Conserva el rechazo nativo de CORS y su trazabilidad."""
    response = client.options(
        "/ask",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )

    assert response.status_code == 400
    assert response.headers["content-type"].startswith(
        "text/plain"
    )
    assert REQUEST_ID_HEADER in response.headers
    assert app.state.calls == 0

    records = get_http_records(caplog)

    assert len(records) == 1
    assert records[0].levelno == logging.WARNING

    data = json.loads(records[0].getMessage())

    assert data["path"] == "PREFLIGHT"
    assert data["status_code"] == 400
    assert data["error_code"] is None


def test_logging_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Aplica el nivel configurado sin duplicar manejadores."""
    monkeypatch.setattr(HTTP_LOGGER, "handlers", [])
    monkeypatch.setattr(HTTP_LOGGER, "level", HTTP_LOGGER.level)
    monkeypatch.setattr(
        HTTP_LOGGER,
        "propagate",
        HTTP_LOGGER.propagate,
    )

    configure_http_logging("DEBUG")
    configure_http_logging("WARNING")

    assert HTTP_LOGGER.level == logging.WARNING
    assert len(HTTP_LOGGER.handlers) == 1
    assert HTTP_LOGGER.propagate is False

    HTTP_LOGGER.handlers[0].close()