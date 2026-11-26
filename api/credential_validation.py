"""Normalización y validación de credenciales."""

from email_validator import EmailNotValidError, validate_email

from config import (
    EMAIL_MAX_LENGTH,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN_LENGTH,
)


class CredencialInvalidaError(ValueError):
    """Excepción base para la validación de credenciales."""


class EmailInvalidoError(CredencialInvalidaError):
    """El email incumple las restricciones establecidas."""


class PasswordInvalidaError(CredencialInvalidaError):
    """La contraseña incumple las restricciones establecidas."""


def normalizar_email(email: str) -> str:
    """Normaliza y comprueba la estructura de un email."""
    if not isinstance(email, str):
        raise EmailInvalidoError(
            "El email debe ser una cadena."
        )

    normalizado = email.strip().lower()

    if not normalizado or len(normalizado) > EMAIL_MAX_LENGTH:
        raise EmailInvalidoError(
            "Longitud de email inválida."
        )

    try:
        validate_email(
            normalizado,
            check_deliverability=False,
        )
    except EmailNotValidError:
        raise EmailInvalidoError("Email inválido.") from None

    return normalizado


def validar_password_verificacion(password: str) -> str:
    """Comprueba la compatibilidad de una contraseña con bcrypt."""
    if not isinstance(password, str):
        raise PasswordInvalidaError(
            "La contraseña debe ser una cadena."
        )

    try:
        longitud_bytes = len(password.encode("utf-8"))
    except UnicodeEncodeError:
        raise PasswordInvalidaError(
            "Codificación de contraseña inválida."
        ) from None

    if longitud_bytes > PASSWORD_MAX_BYTES:
        raise PasswordInvalidaError(
            "La contraseña no puede superar "
            f"{PASSWORD_MAX_BYTES} bytes."
        )

    return password


def validar_nueva_password(password: str) -> str:
    """Aplica la política de creación de contraseñas."""
    password = validar_password_verificacion(password)

    if len(password) < PASSWORD_MIN_LENGTH:
        raise PasswordInvalidaError(
            "La contraseña debe contener al menos "
            f"{PASSWORD_MIN_LENGTH} caracteres."
        )

    if any(caracter.isspace() for caracter in password):
        raise PasswordInvalidaError(
            "La contraseña no puede contener espacios en blanco."
        )

    return password