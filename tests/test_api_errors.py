"""Pruebas del catálogo y las excepciones de la API."""

import re
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.credential_validation import (
    CredencialInvalidaError,
    EmailInvalidoError,
    PasswordInvalidaError,
    normalizar_email,
    validar_nueva_password,
    validar_password_verificacion,
)
from api.error_catalog import (
    ERROR_CATALOG,
    ErrorCode,
    ErrorDefinition,
)
from api.errors import ApiError
from api.schemas import ErrorOut, LoginIn, RegisterIn
from config import (
    MAX_PREGUNTA_CARACTERES,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN_LENGTH,
)


REQUEST_ID = "550e8400-e29b-41d4-a716-446655440000"
EMAIL = "usuario@example.com"
PASSWORD = "a" * PASSWORD_MIN_LENGTH


# =========================================================
# CATÁLOGO DE ERRORES
# =========================================================

def test_catalogo_contiene_todos_los_codigos() -> None:
    """Comprueba que todos los códigos tienen una definición."""
    assert set(ERROR_CATALOG) == set(ErrorCode)
    assert len(ErrorCode) == 46
    assert len(ERROR_CATALOG) == 46


@pytest.mark.parametrize("code", list(ErrorCode))
def test_definicion_de_error_valida(code: ErrorCode) -> None:
    """Comprueba la estructura de cada definición."""
    definition = ERROR_CATALOG[code]

    assert isinstance(definition, ErrorDefinition)
    assert 400 <= definition.status_code <= 599
    assert isinstance(definition.message, str)
    assert definition.message.strip()


def test_catalogo_coincide_con_especificacion() -> None:
    """Contrasta los códigos y estados con la especificación."""
    root = Path(__file__).resolve().parents[1]
    specification = root / "specs" / "12-contratos-http.md"

    content = specification.read_text(encoding="utf-8")

    section = content.split(
        "## 8. Contrato de errores",
        maxsplit=1,
    )[1].split(
        "\n## 9.",
        maxsplit=1,
    )[0]

    pattern = (
        r"^\|\s*(\d{3})\s*\|"
        r"\s*([A-Z][A-Z0-9_]+)\s*\|"
    )

    entries = re.findall(
        pattern,
        section,
        flags=re.MULTILINE,
    )

    expected = {
        code: int(status)
        for status, code in entries
    }

    actual = {
        code.value: definition.status_code
        for code, definition in ERROR_CATALOG.items()
    }

    assert len(entries) == len(expected)
    assert actual == expected


def test_catalogo_no_permite_modificaciones() -> None:
    """Impide sustituir una definición del catálogo."""
    with pytest.raises(TypeError):
        ERROR_CATALOG[ErrorCode.THREAD_NOT_FOUND] = (
            ErrorDefinition(500, "Mensaje de prueba.")
        )


def test_definicion_no_permite_modificaciones() -> None:
    """Impide modificar una definición existente."""
    definition = ERROR_CATALOG[ErrorCode.THREAD_NOT_FOUND]

    with pytest.raises(FrozenInstanceError):
        definition.status_code = 500


def test_limite_pregunta_procede_de_configuracion() -> None:
    """Comprueba la reutilización del límite de preguntas."""
    definition = ERROR_CATALOG[ErrorCode.QUESTION_TOO_LONG]

    assert str(MAX_PREGUNTA_CARACTERES) in definition.message


# =========================================================
# EXCEPCIÓN BASE
# =========================================================

@pytest.mark.parametrize("code", list(ErrorCode))
def test_api_error_con_codigo_valido(code: ErrorCode) -> None:
    """Comprueba la construcción con cada código autorizado."""
    error = ApiError(code)

    assert isinstance(error, Exception)
    assert error.code is code
    assert error.retry_after is None
    assert str(error) == code.value


def test_api_error_se_puede_propagar() -> None:
    """Comprueba el lanzamiento y captura de la excepción."""
    with pytest.raises(ApiError) as exc_info:
        raise ApiError(ErrorCode.THREAD_NOT_FOUND)

    assert exc_info.value.code is ErrorCode.THREAD_NOT_FOUND


@pytest.mark.parametrize(
    "code",
    ["THREAD_NOT_FOUND", "DESCONOCIDO", None, 404, True],
)
def test_api_error_rechaza_codigo_invalido(
    code: object,
) -> None:
    """Rechaza códigos que no pertenecen al enumerado."""
    with pytest.raises(TypeError):
        ApiError(code)


def test_api_error_rechaza_mensaje_personalizado() -> None:
    """Impide incorporar mensajes públicos arbitrarios."""
    with pytest.raises(TypeError):
        ApiError(
            ErrorCode.INTERNAL_SERVER_ERROR,
            message="Información interna.",
        )


@pytest.mark.parametrize("retry_after", [0, 1, 27, 3600])
def test_api_error_acepta_retry_after(
    retry_after: int,
) -> None:
    """Admite tiempos de espera enteros no negativos."""
    error = ApiError(
        ErrorCode.RATE_LIMIT_EXCEEDED,
        retry_after=retry_after,
    )

    assert error.retry_after == retry_after


@pytest.mark.parametrize(
    "retry_after",
    [True, False, 2.5, "27", [], {}],
)
def test_api_error_rechaza_tipo_retry_after(
    retry_after: object,
) -> None:
    """Rechaza tipos incompatibles para el tiempo de espera."""
    with pytest.raises(TypeError):
        ApiError(
            ErrorCode.RATE_LIMIT_EXCEEDED,
            retry_after=retry_after,
        )


@pytest.mark.parametrize("retry_after", [-1, -27])
def test_api_error_rechaza_retry_after_negativo(
    retry_after: int,
) -> None:
    """Rechaza tiempos de espera negativos."""
    with pytest.raises(ValueError):
        ApiError(
            ErrorCode.RATE_LIMIT_EXCEEDED,
            retry_after=retry_after,
        )


@pytest.mark.parametrize(
    "code",
    [
        code
        for code in ErrorCode
        if code is not ErrorCode.RATE_LIMIT_EXCEEDED
    ],
)
def test_api_error_restringe_retry_after(code: ErrorCode) -> None:
    """Impide utilizar Retry-After en otros errores."""
    with pytest.raises(ValueError):
        ApiError(code, retry_after=27)


# =========================================================
# EXCEPCIONES DE CREDENCIALES
# =========================================================

@pytest.mark.parametrize(
    "exception",
    [EmailInvalidoError, PasswordInvalidaError],
)
def test_jerarquia_excepciones_credenciales(
    exception: type[CredencialInvalidaError],
) -> None:
    """Comprueba la compatibilidad con ValueError."""
    assert issubclass(exception, CredencialInvalidaError)
    assert issubclass(exception, ValueError)


@pytest.mark.parametrize(
    "email",
    ["", "   ", "invalido", "usuario@", None, 123],
)
def test_normalizar_email_lanza_excepcion_especifica(
    email: object,
) -> None:
    """Identifica los errores de validación de email."""
    with pytest.raises(EmailInvalidoError):
        normalizar_email(email)


@pytest.mark.parametrize(
    "password",
    [
        "a" * (PASSWORD_MAX_BYTES + 1),
        "ñ" * (PASSWORD_MAX_BYTES // 2 + 1),
        None,
        True,
        123,
        "\ud800",
    ],
)
def test_password_verificacion_lanza_excepcion_especifica(
    password: object,
) -> None:
    """Identifica contraseñas incompatibles con bcrypt."""
    with pytest.raises(PasswordInvalidaError):
        validar_password_verificacion(password)


@pytest.mark.parametrize(
    "password",
    [
        "",
        "a" * (PASSWORD_MIN_LENGTH - 1),
        PASSWORD + " ",
        PASSWORD + "\t",
        PASSWORD + "\n",
    ],
)
def test_nueva_password_lanza_excepcion_especifica(
    password: str,
) -> None:
    """Identifica incumplimientos de la política de creación."""
    with pytest.raises(PasswordInvalidaError):
        validar_nueva_password(password)

def test_pydantic_conserva_error_email() -> None:
    """Comprueba la identificación del error de email."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterIn(
            email="invalido",
            password=PASSWORD,
        )

    errors = exc_info.value.errors(include_input=False)

    assert len(errors) == 1
    assert errors[0]["loc"] == ("email",)
    assert isinstance(
        errors[0]["ctx"]["error"],
        EmailInvalidoError,
    )


def test_pydantic_conserva_error_nueva_password() -> None:
    """Comprueba el error de creación de contraseña."""
    with pytest.raises(ValidationError) as exc_info:
        RegisterIn(
            email=EMAIL,
            password="corta",
        )

    errors = exc_info.value.errors(include_input=False)

    assert len(errors) == 1
    assert errors[0]["loc"] == ("password",)
    assert isinstance(
        errors[0]["ctx"]["error"],
        PasswordInvalidaError,
    )


def test_pydantic_conserva_error_password_login() -> None:
    """Comprueba el error de compatibilidad de contraseña."""
    with pytest.raises(ValidationError) as exc_info:
        LoginIn(
            email=EMAIL,
            password="a" * (PASSWORD_MAX_BYTES + 1),
        )

    errors = exc_info.value.errors(include_input=False)

    assert len(errors) == 1
    assert errors[0]["loc"] == ("password",)
    assert isinstance(
        errors[0]["ctx"]["error"],
        PasswordInvalidaError,
    )


# =========================================================
# CONTRATO PÚBLICO DE ERRORES
# =========================================================

@pytest.fixture
def error_valido() -> dict[str, object]:
    """Proporciona los datos de un error público válido."""
    code = ErrorCode.THREAD_NOT_FOUND

    return {
        "code": code,
        "message": ERROR_CATALOG[code].message,
        "request_id": REQUEST_ID,
    }


@pytest.mark.parametrize("code", list(ErrorCode))
def test_error_out_acepta_codigos_validos(
    code: ErrorCode,
) -> None:
    """Comprueba la representación pública de cada código."""
    definition = ERROR_CATALOG[code]

    error = ErrorOut(
        code=code,
        message=definition.message,
        request_id=REQUEST_ID,
    )

    assert error.model_dump(mode="json") == {
        "code": code.value,
        "message": definition.message,
        "request_id": REQUEST_ID,
    }


@pytest.mark.parametrize(
    "code",
    ["DESCONOCIDO", "", 404, True, None],
)
def test_error_out_rechaza_codigo_invalido(
    error_valido: dict[str, object],
    code: object,
) -> None:
    """Impide utilizar códigos no reconocidos."""
    error_valido["code"] = code

    with pytest.raises(ValidationError):
        ErrorOut(**error_valido)


@pytest.mark.parametrize(
    "message",
    ["", "   ", "\t\n", None, True, 123],
)
def test_error_out_rechaza_mensaje_invalido(
    error_valido: dict[str, object],
    message: object,
) -> None:
    """Impide utilizar mensajes vacíos o incompatibles."""
    error_valido["message"] = message

    with pytest.raises(ValidationError):
        ErrorOut(**error_valido)


@pytest.mark.parametrize(
    "request_id",
    ["", "invalido", None, True, 123],
)
def test_error_out_rechaza_request_id_invalido(
    error_valido: dict[str, object],
    request_id: object,
) -> None:
    """Impide utilizar identificadores incompatibles."""
    error_valido["request_id"] = request_id

    with pytest.raises(ValidationError):
        ErrorOut(**error_valido)


def test_error_out_normaliza_request_id(
    error_valido: dict[str, object],
) -> None:
    """Comprueba la representación canónica del UUID."""
    error_valido["request_id"] = REQUEST_ID.upper()

    error = ErrorOut(**error_valido)

    assert error.request_id == REQUEST_ID


@pytest.mark.parametrize(
    "field",
    ["detail", "stack_trace", "status_code", "retry_after"],
)
def test_error_out_rechaza_campos_adicionales(
    error_valido: dict[str, object],
    field: str,
) -> None:
    """Impide exponer campos no autorizados."""
    error_valido[field] = "Información adicional."

    with pytest.raises(ValidationError):
        ErrorOut(**error_valido)


@pytest.mark.parametrize(
    "field",
    list(ErrorOut.model_fields),
)
def test_error_out_requiere_todos_los_campos(
    error_valido: dict[str, object],
    field: str,
) -> None:
    """Comprueba la obligatoriedad de todos los campos."""
    del error_valido[field]

    with pytest.raises(ValidationError):
        ErrorOut(**error_valido)