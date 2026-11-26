"""Pruebas del tratamiento centralizado de excepciones HTTP."""

from collections.abc import Iterator
from itertools import permutations
from types import SimpleNamespace
from typing import Annotated
from uuid import UUID

import pytest
from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.testclient import TestClient
from httpx import Response
from starlette.exceptions import HTTPException

from api.error_catalog import ERROR_CATALOG, ErrorCode
from api.errors import ApiError
from api.exception_handlers import (
    register_exception_handlers,
    resolve_question_error_code,
    resolve_validation_error_code,
)
from api.request_context import REQUEST_ID_HEADER, get_request_id
from api.schemas import (
    ApproveIn,
    AskIn,
    ErrorOut,
    HealthOut,
    LoginIn,
    PasswordChangeIn,
    RegisterIn,
    UUIDText,
)
from config import (
    MAX_PREGUNTA_CARACTERES,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN_LENGTH,
)
from src.input_validation import PreguntaInvalidaError


EMAIL = "usuario@example.com"
PASSWORD = "a" * PASSWORD_MIN_LENGTH
SECRET = "informacion-sensible-ficticia"
VALID_QUESTION = "¿Dónde debo reciclar una pila?"


@pytest.fixture
def app() -> FastAPI:
    """Crea una aplicación aislada para probar los manejadores."""
    application = FastAPI()

    register_exception_handlers(application)

    @application.get("/test/error/{code}")
    def controlled_error(
        code: ErrorCode,
        retry_after: int | None = None,
    ) -> None:
        raise ApiError(code, retry_after=retry_after)

    @application.get("/test/context")
    def context_error(request: Request) -> None:
        get_request_id(request)
        raise ApiError(ErrorCode.THREAD_NOT_FOUND)

    @application.get("/test/http/{status_code}")
    def framework_error(status_code: int) -> None:
        raise HTTPException(
            status_code=status_code,
            detail=SECRET,
            headers={
                "aLLoW": "POST",
                "X-Private": SECRET,
            },
        )

    @application.post("/ask")
    def ask(data: AskIn) -> dict[str, str]:
        try:
            question = data.pregunta_validada()
        except PreguntaInvalidaError as exc:
            code = resolve_question_error_code(exc)
            raise ApiError(code) from None

        return {"pregunta": question}

    @application.post("/approve")
    def approve(data: ApproveIn) -> dict[str, bool]:
        return {"aprobado": data.aprobado}

    @application.post("/auth/register")
    def register(data: RegisterIn) -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/auth/login")
    def login(data: LoginIn) -> dict[str, str]:
        return {"status": "ok"}

    @application.patch("/auth/password")
    def change_password(
        data: PasswordChangeIn,
    ) -> dict[str, str]:
        return {"status": "ok"}

    @application.get("/threads/{thread_id}")
    def thread(thread_id: UUIDText) -> dict[str, str]:
        return {"thread_id": thread_id}

    @application.get("/test/internal/{kind}")
    def internal_error(kind: str) -> None:
        if kind == "runtime":
            raise RuntimeError(SECRET)

        if kind == "value":
            raise ValueError(SECRET)

        if kind == "type":
            raise TypeError(SECRET)

        ErrorOut(
            code=ErrorCode.INTERNAL_SERVER_ERROR,
            message=SECRET,
            request_id=SECRET,
        )

    @application.get(
        "/test/response",
        response_model=HealthOut,
    )
    def invalid_response() -> dict[str, str]:
        return {
            "status": SECRET,
            "storage": "postgres",
        }

    @application.post("/ask/image")
    def ask_image(
        imagen: UploadFile,
        pregunta: Annotated[str, Form()],
        latitud: Annotated[float | None, Form()] = None,
        longitud: Annotated[float | None, Form()] = None,
    ) -> dict[str, str]:
        return {"status": "ok"}

    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Proporciona un cliente sin infraestructura externa."""
    with TestClient(
        app,
        raise_server_exceptions=False,
    ) as test_client:
        yield test_client


def assert_error_response(
    response: Response,
    code: ErrorCode,
) -> None:
    """Comprueba la respuesta HTTP y el contrato de error."""
    definition = ERROR_CATALOG[code]
    data = response.json()

    assert response.status_code == definition.status_code
    assert response.headers["content-type"].startswith(
        "application/json"
    )

    assert data == {
        "code": code.value,
        "message": definition.message,
        "request_id": response.headers[REQUEST_ID_HEADER],
    }

    request_id = data["request_id"]

    assert str(UUID(request_id)) == request_id
    assert UUID(request_id).version == 4

    assert SECRET not in response.text


# =========================================================
# ERRORES CONTROLADOS
# =========================================================


@pytest.mark.parametrize("code", list(ErrorCode))
def test_controlled_error(
    client: TestClient,
    code: ErrorCode,
) -> None:
    """Comprueba la respuesta HTTP de todos los códigos."""
    response = client.get(f"/test/error/{code.value}")

    assert_error_response(response, code)


@pytest.mark.parametrize("retry_after", [0, 1, 27])
def test_rate_limit_retry_after(
    client: TestClient,
    retry_after: int,
) -> None:
    """Conserva el tiempo de espera de un error 429."""
    code = ErrorCode.RATE_LIMIT_EXCEEDED

    response = client.get(
        f"/test/error/{code.value}",
        params={"retry_after": retry_after},
    )

    assert_error_response(response, code)
    assert response.headers["Retry-After"] == str(retry_after)


def test_rate_limit_without_retry_after(
    client: TestClient,
) -> None:
    """Omite Retry-After si no se conoce el tiempo de espera."""
    code = ErrorCode.RATE_LIMIT_EXCEEDED
    response = client.get(f"/test/error/{code.value}")

    assert_error_response(response, code)
    assert "Retry-After" not in response.headers


# =========================================================
# VALIDACIÓN DE CONSULTAS
# =========================================================


@pytest.mark.parametrize(
    "data, code",
    [
        (
            {"pregunta": ""},
            ErrorCode.EMPTY_QUESTION,
        ),
        (
            {"pregunta": "   "},
            ErrorCode.EMPTY_QUESTION,
        ),
        (
            {"pregunta": "a" * (MAX_PREGUNTA_CARACTERES + 1)},
            ErrorCode.QUESTION_TOO_LONG,
        ),
        (
            {"pregunta": 123},
            ErrorCode.VALIDATION_ERROR,
        ),
        (
            {"pregunta": VALID_QUESTION, "thread_id": "invalido"},
            ErrorCode.INVALID_THREAD_ID,
        ),
        (
            {"pregunta": VALID_QUESTION, "max_steps": 0},
            ErrorCode.INVALID_MAX_STEPS,
        ),
        (
            {
                "pregunta": VALID_QUESTION,
                "ubicacion": {"latitud": 150, "longitud": 0},
            },
            ErrorCode.INVALID_LOCATION,
        ),
        (
            {
                "pregunta": VALID_QUESTION,
                "ubicacion": {"latitud": 40},
            },
            ErrorCode.INVALID_LOCATION,
        ),
        (
            {"pregunta": VALID_QUESTION, "latitud": 40},
            ErrorCode.VALIDATION_ERROR,
        ),
        (
            {},
            ErrorCode.VALIDATION_ERROR,
        ),
        (
            {"pregunta": VALID_QUESTION, "extra": SECRET},
            ErrorCode.VALIDATION_ERROR,
        ),
    ],
)
def test_ask_validation(
    client: TestClient,
    data: dict[str, object],
    code: ErrorCode,
) -> None:
    """Comprueba la traducción de errores de entrada."""
    response = client.post("/ask", json=data)

    assert_error_response(response, code)


def test_malformed_json(client: TestClient) -> None:
    """Gestiona un documento JSON no interpretable."""
    response = client.post(
        "/ask",
        content='{"pregunta":',
        headers={"Content-Type": "application/json"},
    )

    assert_error_response(
        response,
        ErrorCode.VALIDATION_ERROR,
    )


def test_invalid_thread_path(client: TestClient) -> None:
    """Identifica un UUID inválido en un parámetro de ruta."""
    response = client.get("/threads/invalido")

    assert_error_response(
        response,
        ErrorCode.INVALID_THREAD_ID,
    )


def test_invalid_approval_id(client: TestClient) -> None:
    """Trata approval_id como un error general de validación."""
    response = client.post(
        "/approve",
        json={
            "thread_id": str(UUID(int=1)),
            "approval_id": "invalido",
            "aprobado": True,
        },
    )

    assert_error_response(
        response,
        ErrorCode.VALIDATION_ERROR,
    )


# =========================================================
# VALIDACIÓN DE CREDENCIALES
# =========================================================


@pytest.mark.parametrize(
    "method, path, data, code",
    [
        (
            "POST",
            "/auth/register",
            {"email": "invalido", "password": PASSWORD},
            ErrorCode.INVALID_EMAIL,
        ),
        (
            "POST",
            "/auth/login",
            {"email": "invalido", "password": PASSWORD},
            ErrorCode.INVALID_EMAIL,
        ),
        (
            "POST",
            "/auth/register",
            {"email": EMAIL, "password": "corta"},
            ErrorCode.INVALID_PASSWORD,
        ),
        (
            "POST",
            "/auth/login",
            {
                "email": EMAIL,
                "password": "a" * (PASSWORD_MAX_BYTES + 1),
            },
            ErrorCode.INVALID_CREDENTIALS,
        ),
        (
            "PATCH",
            "/auth/password",
            {
                "current_password": "a" * (PASSWORD_MAX_BYTES + 1),
                "new_password": PASSWORD,
            },
            ErrorCode.INVALID_CREDENTIALS,
        ),
        (
            "PATCH",
            "/auth/password",
            {
                "current_password": PASSWORD,
                "new_password": "corta",
            },
            ErrorCode.INVALID_PASSWORD,
        ),
        (
            "POST",
            "/auth/login",
            {"email": EMAIL, "password": 123},
            ErrorCode.VALIDATION_ERROR,
        ),
    ],
)
def test_credentials_validation(
    client: TestClient,
    method: str,
    path: str,
    data: dict[str, object],
    code: ErrorCode,
) -> None:
    """Comprueba la traducción contextual de credenciales."""
    response = client.request(
        method,
        path,
        json=data,
    )

    assert_error_response(response, code)


def test_credentials_error_does_not_expose_password(
    client: TestClient,
) -> None:
    """Impide exponer una contraseña rechazada."""
    invalid_password = SECRET + " con espacios"

    response = client.post(
        "/auth/register",
        json={
            "email": EMAIL,
            "password": invalid_password,
        },
    )

    assert_error_response(
        response,
        ErrorCode.INVALID_PASSWORD,
    )

    assert invalid_password not in response.text


# =========================================================
# PRIORIDAD DE ERRORES
# =========================================================


def test_validation_error_priority(
    client: TestClient,
) -> None:
    """Selecciona el error prioritario de una petición."""
    response = client.post(
        "/ask",
        json={
            "pregunta": VALID_QUESTION,
            "thread_id": "invalido",
            "max_steps": -1,
            "ubicacion": {
                "latitud": 150,
                "longitud": 200,
            },
        },
    )

    assert_error_response(
        response,
        ErrorCode.INVALID_THREAD_ID,
    )


def test_validation_priority_independent_of_order() -> None:
    """Comprueba todas las permutaciones de los errores."""
    request = Request({
        "type": "http",
        "method": "POST",
        "route": SimpleNamespace(path="/ask"),
        "headers": [],
    })

    errors = (
        {"loc": ("body", "thread_id")},
        {"loc": ("body", "ubicacion", "latitud")},
        {"loc": ("body", "max_steps")},
    )

    for ordered_errors in permutations(errors):
        result = resolve_validation_error_code(
            request,
            ordered_errors,
        )

        assert result is ErrorCode.INVALID_THREAD_ID


def test_validation_priority_credentials(
    client: TestClient,
) -> None:
    """Prioriza la incompatibilidad de autenticación."""
    response = client.post(
        "/auth/login",
        json={
            "email": "invalido",
            "password": "a" * (PASSWORD_MAX_BYTES + 1),
        },
    )

    assert_error_response(
        response,
        ErrorCode.INVALID_CREDENTIALS,
    )


# =========================================================
# ERRORES DEL FRAMEWORK
# =========================================================


def test_route_not_found(client: TestClient) -> None:
    """Comprueba una ruta que no existe."""
    response = client.get("/ruta-inexistente")

    assert_error_response(
        response,
        ErrorCode.ROUTE_NOT_FOUND,
    )


def test_method_not_allowed(client: TestClient) -> None:
    """Comprueba un método no autorizado por el enrutador."""
    response = client.get("/ask")

    assert_error_response(
        response,
        ErrorCode.METHOD_NOT_ALLOWED,
    )

    assert "POST" in response.headers["Allow"]


@pytest.mark.parametrize(
    "status, code",
    [
        (400, ErrorCode.BAD_REQUEST),
        (404, ErrorCode.ROUTE_NOT_FOUND),
        (405, ErrorCode.METHOD_NOT_ALLOWED),
        (401, ErrorCode.INTERNAL_SERVER_ERROR),
        (403, ErrorCode.INTERNAL_SERVER_ERROR),
        (418, ErrorCode.INTERNAL_SERVER_ERROR),
    ],
)
def test_framework_exception(
    client: TestClient,
    status: int,
    code: ErrorCode,
) -> None:
    """Comprueba la traducción de las excepciones HTTP."""
    response = client.get(f"/test/http/{status}")

    assert_error_response(response, code)
    assert "X-Private" not in response.headers

    if code == ErrorCode.METHOD_NOT_ALLOWED:
        assert response.headers["Allow"] == "POST"
    else:
        assert "Allow" not in response.headers


# =========================================================
# FALLOS INTERNOS
# =========================================================


@pytest.mark.parametrize(
    "kind",
    ["runtime", "value", "type", "pydantic"],
)
def test_unexpected_internal_error(
    client: TestClient,
    kind: str,
) -> None:
    """Protege la información de las excepciones internas."""
    response = client.get(f"/test/internal/{kind}")

    assert_error_response(
        response,
        ErrorCode.INTERNAL_SERVER_ERROR,
    )

    assert "Traceback" not in response.text


def test_invalid_response_model(client: TestClient) -> None:
    """Trata una respuesta incompatible como fallo interno."""
    response = client.get("/test/response")

    assert_error_response(
        response,
        ErrorCode.INTERNAL_SERVER_ERROR,
    )


# =========================================================
# TRAZABILIDAD
# =========================================================


def test_request_id_in_error_response(
    client: TestClient,
) -> None:
    """Comprueba la coherencia del identificador público."""
    response = client.get("/test/context")

    assert_error_response(
        response,
        ErrorCode.THREAD_NOT_FOUND,
    )


def test_request_ids_are_different(
    client: TestClient,
) -> None:
    """Comprueba el aislamiento de dos peticiones HTTP."""
    first = client.get("/ruta-inexistente")
    second = client.get("/ruta-inexistente")

    assert (
        first.headers[REQUEST_ID_HEADER]
        != second.headers[REQUEST_ID_HEADER]
    )


def test_client_request_id_is_ignored(
    client: TestClient,
) -> None:
    """Impide utilizar un identificador enviado por el cliente."""
    provided = "550e8400-e29b-41d4-a716-446655440000"

    response = client.get(
        "/ruta-inexistente",
        headers={REQUEST_ID_HEADER: provided},
    )

    assert_error_response(
        response,
        ErrorCode.ROUTE_NOT_FOUND,
    )

    assert response.headers[REQUEST_ID_HEADER] != provided


# =========================================================
# VALIDACIÓN MULTIPART
# =========================================================


def test_multipart_invalid_location(
    client: TestClient,
) -> None:
    """Traduce errores de campos geográficos multipart."""
    response = client.post(
        "/ask/image",
        data={
            "pregunta": VALID_QUESTION,
            "latitud": "invalida",
            "longitud": "0",
        },
        files={
            "imagen": (
                "prueba.png",
                b"contenido-ficticio",
                "image/png",
            ),
        },
    )

    assert_error_response(
        response,
        ErrorCode.INVALID_LOCATION,
    )


def test_malformed_multipart(client: TestClient) -> None:
    """Gestiona un cuerpo multipart no interpretable."""
    response = client.post(
        "/ask/image",
        content=b"contenido-invalido",
        headers={
            "Content-Type": "multipart/form-data",
        },
    )

    assert_error_response(
        response,
        ErrorCode.BAD_REQUEST,
    )