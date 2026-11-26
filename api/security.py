"""Primitivas de seguridad de ReciclaTIA."""

import hashlib
import re
import secrets

import bcrypt

from api.credential_validation import (
    PasswordInvalidaError,
    validar_nueva_password,
    validar_password_verificacion,
)
from api.error_catalog import ErrorCode
from api.errors import ApiError


# =========================================================
# CONTRASEÑAS
# =========================================================


def hash_password(password: str, rounds: int) -> str:
    """Valida una contraseña nueva y genera su hash bcrypt."""
    try:
        password = validar_nueva_password(password)
    except PasswordInvalidaError:
        raise ApiError(ErrorCode.INVALID_PASSWORD) from None

    try:
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=rounds),
        )
    except ValueError:
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR) from None

    return password_hash.decode("ascii")


def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    """Comprueba una contraseña contra su hash almacenado."""
    try:
        password = validar_password_verificacion(password)
    except PasswordInvalidaError:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS) from None

    if not isinstance(password_hash, str) or not re.fullmatch(
        r"\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}",
        password_hash,
    ):
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR)

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except ValueError:
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR) from None


# =========================================================
# TOKENS Y API KEYS
# =========================================================


def generate_secret() -> str:
    """Genera una credencial opaca de elevada entropía."""
    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    """Calcula el hash hexadecimal SHA-256 de una credencial."""
    return hashlib.sha256(
        secret.encode("utf-8"),
    ).hexdigest()


# =========================================================
# MITIGACIÓN DE ENUMERACIÓN TEMPORAL
# =========================================================


def create_dummy_password_hash(rounds: int) -> str:
    """Genera un hash auxiliar para usuarios inexistentes."""
    return hash_password(
        generate_secret(),
        rounds,
    )