"""Pruebas de las primitivas de seguridad."""

import re

import pytest

from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.security import (
    create_dummy_password_hash,
    generate_secret,
    hash_password,
    hash_secret,
    verify_password,
)
from config import PASSWORD_MAX_BYTES, PASSWORD_MIN_LENGTH


TEST_ROUNDS = 4
PASSWORD = "ContraseñaSegura2026"


# =========================================================
# HASHING DE CONTRASEÑAS
# =========================================================


def test_hash_password() -> None:
    """Genera un hash bcrypt con el coste configurado."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert isinstance(password_hash, str)
    assert len(password_hash) == 60
    assert password_hash.startswith("$2b$04$")
    assert password_hash != PASSWORD


def test_hash_password_random_salt() -> None:
    """Genera hashes diferentes para una misma contraseña."""
    first = hash_password(PASSWORD, TEST_ROUNDS)
    second = hash_password(PASSWORD, TEST_ROUNDS)

    assert first != second
    assert verify_password(PASSWORD, first) is True
    assert verify_password(PASSWORD, second) is True


@pytest.mark.parametrize(
    "password",
    [
        "",
        "a" * (PASSWORD_MIN_LENGTH - 1),
        "a" * (PASSWORD_MAX_BYTES + 1),
        "Contraseña con espacios",
        "Contraseña\tConTabulador",
    ],
)
def test_hash_invalid_password(password: str) -> None:
    """Rechaza contraseñas que incumplen la política."""
    with pytest.raises(ApiError) as exc_info:
        hash_password(password, TEST_ROUNDS)

    assert exc_info.value.code == ErrorCode.INVALID_PASSWORD


def test_hash_password_unicode() -> None:
    """Admite contraseñas Unicode compatibles con bcrypt."""
    password = "ñ" * (PASSWORD_MAX_BYTES // 2)

    password_hash = hash_password(password, TEST_ROUNDS)

    assert verify_password(password, password_hash) is True


def test_hash_password_invalid_rounds() -> None:
    """Identifica una configuración bcrypt inválida."""
    with pytest.raises(ApiError) as exc_info:
        hash_password(PASSWORD, 3)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR


# =========================================================
# VERIFICACIÓN DE CONTRASEÑAS
# =========================================================


def test_verify_correct_password() -> None:
    """Acepta la contraseña asociada al hash."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert verify_password(PASSWORD, password_hash) is True


def test_verify_incorrect_password() -> None:
    """Rechaza una contraseña diferente."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert verify_password("ContraseñaIncorrecta", password_hash) is False


def test_verify_empty_password() -> None:
    """Trata una contraseña vacía como credencial incorrecta."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert verify_password("", password_hash) is False


def test_verify_incompatible_password() -> None:
    """Rechaza contraseñas incompatibles con bcrypt."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    with pytest.raises(ApiError) as exc_info:
        verify_password(
            "a" * (PASSWORD_MAX_BYTES + 1),
            password_hash,
        )

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS


@pytest.mark.parametrize(
    "password_hash",
    [
        "",
        "hash-invalido",
        "informacion-sensible-ficticia",
        "$2b$04$" + "!" * 53,
    ],
)
def test_verify_invalid_hash(password_hash: str) -> None:
    """Diferencia un hash inválido de una contraseña incorrecta."""
    with pytest.raises(ApiError) as exc_info:
        verify_password(PASSWORD, password_hash)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR
    assert password_hash not in str(exc_info.value) or not password_hash


def test_verify_truncated_hash() -> None:
    """Detecta un hash almacenado incompleto."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    with pytest.raises(ApiError) as exc_info:
        verify_password(PASSWORD, password_hash[:-1])

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR


def test_verify_invalid_hash_cost() -> None:
    """Gestiona un coste bcrypt inválido dentro del hash."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)
    invalid_hash = password_hash.replace("$04$", "$03$", 1)

    with pytest.raises(ApiError) as exc_info:
        verify_password(PASSWORD, invalid_hash)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR


# =========================================================
# TOKENS Y API KEYS
# =========================================================


def test_generate_secret() -> None:
    """Genera un secreto compatible con su transmisión HTTP."""
    secret = generate_secret()

    assert len(secret) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]+", secret)


def test_generate_distinct_secrets() -> None:
    """Comprueba que las emisiones no reutilizan secretos."""
    secrets_generated = {
        generate_secret()
        for _ in range(100)
    }

    assert len(secrets_generated) == 100


def test_hash_secret() -> None:
    """Genera un resumen SHA-256 hexadecimal."""
    secret_hash = hash_secret("abc")

    assert secret_hash == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
    assert len(secret_hash) == 64


def test_hash_secret_deterministic() -> None:
    """Obtiene el mismo hash para un mismo secreto."""
    secret = generate_secret()

    assert hash_secret(secret) == hash_secret(secret)


def test_hash_secret_different_values() -> None:
    """Diferencia secretos distintos."""
    assert hash_secret("secret-a") != hash_secret("secret-b")


# =========================================================
# HASH AUXILIAR
# =========================================================


def test_create_dummy_password_hash() -> None:
    """Genera un hash auxiliar válido con el coste solicitado."""
    dummy_hash = create_dummy_password_hash(TEST_ROUNDS)

    assert len(dummy_hash) == 60
    assert dummy_hash.startswith("$2b$04$")
    assert verify_password(PASSWORD, dummy_hash) is False


def test_create_distinct_dummy_hashes() -> None:
    """Evita reutilizar el hash entre inicializaciones."""
    first = create_dummy_password_hash(TEST_ROUNDS)
    second = create_dummy_password_hash(TEST_ROUNDS)

    assert first != second