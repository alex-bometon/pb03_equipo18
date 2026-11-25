"""Configuración exclusiva del backend HTTP de ReciclaTÍA."""

import os
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    SecretStr,
    ValidationError,
    field_validator,
)
from sqlalchemy.engine import make_url

from config import BASE_DIR, IMAGE_MAX_BYTES, IMAGE_MAX_PIXELS


class ApiSettings(BaseModel):
    """Parámetros de configuración del backend."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
    )

    # Servidor
    PORT: int = Field(default=8000, ge=1, le=65535)
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    CORS_ORIGINS: tuple[str, ...] = ()

    # Credenciales e infraestructura
    DATABASE_URL: SecretStr | None = None
    GEMINI_API_KEY: SecretStr | None = None
    API_KEY: SecretStr | None = None

    # Conexiones PostgreSQL
    DB_POOL_SIZE: PositiveInt = 3
    DB_MAX_OVERFLOW: int = Field(default=0, ge=0)
    DB_POOL_TIMEOUT_SECONDS: PositiveInt = 5
    DB_CONNECT_TIMEOUT_SECONDS: PositiveInt = 5
    DB_STATEMENT_TIMEOUT_SECONDS: PositiveInt = 5
    DB_LOCK_TIMEOUT_SECONDS: PositiveInt = 3

    # Autenticación y autorización
    SESSION_TTL_SECONDS: PositiveInt = 28_800
    BCRYPT_ROUNDS: int = Field(default=12, ge=4, le=31)

    FREE_MAX_ACTIVE_KEYS: PositiveInt = 1
    USER_MAX_ACTIVE_KEYS: PositiveInt = 5

    USER_TIER_ALLOWED_USER_IDS: frozenset[UUID] = frozenset()

    # Rate limiting HTTP
    RATE_LIMIT_PER_MINUTE: PositiveInt = 30

    # Cuotas comerciales Free
    FREE_RATE_LIMIT_PER_MINUTE: PositiveInt = 2
    FREE_RATE_LIMIT_PER_HOUR: PositiveInt = 10
    FREE_RATE_LIMIT_PER_DAY: PositiveInt = 30

    # Cuotas comerciales User
    USER_RATE_LIMIT_PER_MINUTE: PositiveInt = 5
    USER_RATE_LIMIT_PER_HOUR: PositiveInt = 20
    USER_RATE_LIMIT_PER_DAY: PositiveInt = 45

    # Límites de seguridad
    LOGIN_EMAIL_LIMIT_PER_15_MINUTES: PositiveInt = 5
    LOGIN_ORIGIN_LIMIT_PER_15_MINUTES: PositiveInt = 20
    REGISTER_LIMIT_PER_HOUR: PositiveInt = 5

    KEY_ISSUE_LIMIT_PER_HOUR: PositiveInt = 3
    KEY_ISSUE_LIMIT_PER_DAY: PositiveInt = 5

    # Ejecución del asistente
    AGENT_MAX_WORKERS: int = Field(default=1, ge=1, le=1)

    ASK_TIMEOUT_SECONDS: float = Field(
        default=60.0,
        gt=0,
        allow_inf_nan=False,
    )

    # Límites absolutos de recepción multimedia
    IMAGE_UPLOAD_MAX_BYTES: int = Field(
        default=20 * 1024 * 1024,
        ge=IMAGE_MAX_BYTES,
        le=20 * 1024 * 1024,
    )

    IMAGE_UPLOAD_MAX_PIXELS: int = Field(
        default=32_000_000,
        ge=IMAGE_MAX_PIXELS,
        le=32_000_000,
    )

    @field_validator(
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "API_KEY",
        mode="before",
    )
    @classmethod
    def normalize_empty_secrets(cls, value):
        """Representa las credenciales vacías mediante None."""
        if isinstance(value, str) and not value.strip():
            return None

        return value

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value):
        """Normaliza las conexiones PostgreSQL."""
        if isinstance(value, str) and value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://"):]

        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value):
        """Comprueba la estructura y el driver de conexión."""
        if value is None:
            return None

        try:
            url = make_url(value.get_secret_value())
        except Exception:
            raise ValueError("DATABASE_URL inválida.") from None

        if url.drivername not in {
            "postgresql",
            "postgresql+psycopg2",
        }:
            raise ValueError("Se requiere una conexión PostgreSQL.")

        if not url.host or not url.database:
            raise ValueError("DATABASE_URL incompleta.")

        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        """Convierte una cadena CSV en una colección de orígenes."""
        if isinstance(value, str):
            return tuple(
                origin.strip()
                for origin in value.split(",")
                if origin.strip()
            )

        return value

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, origins):
        """Exige orígenes HTTP o HTTPS explícitos."""
        for origin in origins:
            try:
                parsed = urlsplit(origin)
                port = parsed.port
            except ValueError:
                raise ValueError("Origen CORS inválido.") from None

            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or any(char.isspace() for char in origin)
                or port == 0
            ):
                raise ValueError("Origen CORS inválido.")

        return origins

    @field_validator(
        "USER_TIER_ALLOWED_USER_IDS",
        mode="before",
    )
    @classmethod
    def parse_allowed_users(cls, value):
        """Convierte la lista de UUID autorizados."""
        if isinstance(value, str):
            return [
                item.strip()
                for item in value.split(",")
                if item.strip()
            ]

        return value

    def missing_required_settings(self) -> tuple[str, ...]:
        """Identifica configuraciones imprescindibles ausentes."""
        required = (
            "DATABASE_URL",
            "GEMINI_API_KEY",
            "API_KEY",
        )

        return tuple(
            name
            for name in required
            if getattr(self, name) is None
        )


def load_settings() -> ApiSettings:
    """Carga y valida la configuración del entorno."""
    load_dotenv(BASE_DIR / ".env", override=False)

    values = {
        name: os.environ[name]
        for name in ApiSettings.model_fields
        if name in os.environ
    }

    try:
        return ApiSettings.model_validate(values)

    except ValidationError as exc:
        fields = ", ".join(
            sorted({
                ".".join(str(part) for part in error["loc"])
                for error in exc.errors(
                    include_input=False,
                    include_context=False,
                )
            })
        )

        raise ValueError(
            f"Configuración del backend inválida: {fields}"
        ) from None
