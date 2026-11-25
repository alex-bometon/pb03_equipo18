"""Normalización y validación de credenciales."""

from email_validator import EmailNotValidError, validate_email

from config import (
    EMAIL_MAX_LENGTH,
    PASSWORD_MAX_BYTES,
    PASSWORD_MIN_LENGTH,
)


def normalizar_email(email: str) -> str:
    """Normaliza y comprueba la estructura de un email."""

    if not isinstance(email, str):
        raise ValueError("El email debe ser una cadena.")

    normalizado = email.strip().lower()

    if not normalizado or len(normalizado) > EMAIL_MAX_LENGTH:
        raise ValueError("Longitud de email inválida.")

    try:
        validate_email(
            normalizado,
            check_deliverability=False,
        )

    except EmailNotValidError:
        raise ValueError("Email inválido.") from None

    return normalizado


def validar_password_verificacion(password: str) -> str:
    """Comprueba la compatibilidad de una contraseña con bcrypt."""

    if not isinstance(password, str):
        raise ValueError("La contraseña debe ser una cadena.")

    try:
        longitud_bytes = len(password.encode("utf-8"))

    except UnicodeEncodeError:
        raise ValueError(
            "Codificación de contraseña inválida."
        ) from None

    if longitud_bytes > PASSWORD_MAX_BYTES:
        raise ValueError(
            f"La contraseña no puede superar {PASSWORD_MAX_BYTES} bytes."
        )

    return password


def validar_nueva_password(password: str) -> str:
    """Aplica la política de creación de contraseñas."""

    password = validar_password_verificacion(password)

    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(
            "La contraseña debe contener al menos "
            f"{PASSWORD_MIN_LENGTH} caracteres."
        )

    if any(caracter.isspace() for caracter in password):
        raise ValueError(
            "La contraseña no puede contener espacios en blanco."
        )

    return password