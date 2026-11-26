"""Pruebas de configuración del backend HTTP."""

from uuid import UUID

import pytest
from pydantic import ValidationError

import api.config as api_config
from api.config import ApiSettings, load_settings
from api.security import generate_secret


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """Aísla las pruebas de la configuración real del entorno."""

    for name in ApiSettings.model_fields:
        monkeypatch.delenv(name, raising=False)

    monkeypatch.setattr(api_config, "BASE_DIR", tmp_path)

    return tmp_path


def test_default_settings(isolated_env):
    """Comprueba los valores predeterminados."""

    settings = load_settings()

    assert settings.PORT == 8000
    assert settings.LOG_LEVEL == "INFO"
    assert settings.RATE_LIMIT_PER_MINUTE == 30
    assert settings.ASK_TIMEOUT_SECONDS == 60.0
    assert settings.AGENT_MAX_WORKERS == 1

    assert settings.FREE_RATE_LIMIT_PER_MINUTE == 2
    assert settings.FREE_RATE_LIMIT_PER_HOUR == 10
    assert settings.FREE_RATE_LIMIT_PER_DAY == 30

    assert settings.USER_RATE_LIMIT_PER_MINUTE == 5
    assert settings.USER_RATE_LIMIT_PER_HOUR == 20
    assert settings.USER_RATE_LIMIT_PER_DAY == 45


def test_missing_required_settings(isolated_env):
    """Identifica las credenciales imprescindibles ausentes."""
    settings = load_settings()

    assert settings.missing_required_settings() == (
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "API_KEY",
    )


def test_empty_secrets() -> None:
    """Representa las credenciales vacías mediante None."""
    settings = ApiSettings(
        DATABASE_URL="",
        GEMINI_API_KEY="",
        ADMIN_EMAIL="",
        ADMIN_PASSWORD="",
        API_KEY="",
    )

    assert settings.DATABASE_URL is None
    assert settings.GEMINI_API_KEY is None
    assert settings.ADMIN_EMAIL is None
    assert settings.ADMIN_PASSWORD is None
    assert settings.API_KEY is None


def test_database_url_normalization():
    """Normaliza el prefijo postgres://."""

    settings = ApiSettings(
        DATABASE_URL="postgres://test:test@localhost/test_db"
    )

    assert settings.DATABASE_URL.get_secret_value() == (
        "postgresql://test:test@localhost/test_db"
    )


def test_invalid_database_driver():
    """Rechaza motores de bases de datos no autorizados."""

    with pytest.raises(ValidationError):
        ApiSettings(DATABASE_URL="sqlite:///test.db")


def test_secret_representation() -> None:
    """Comprueba que la configuración no representa secretos."""
    email = "admin-ficticio@example.com"
    password = generate_secret()
    secret = generate_secret()

    settings = ApiSettings(
        ADMIN_EMAIL=email,
        ADMIN_PASSWORD=password,
        API_KEY=secret,
    )

    for value in (email, password, secret):
        assert value not in repr(settings)
        assert value not in str(settings)

    assert email not in str(settings.ADMIN_EMAIL)
    assert password not in str(settings.ADMIN_PASSWORD)
    assert secret not in str(settings.API_KEY)


def test_cors_origins():
    """Convierte los orígenes separados por comas."""

    settings = ApiSettings(
        CORS_ORIGINS="http://localhost:8501, https://example.com"
    )

    assert settings.CORS_ORIGINS == (
        "http://localhost:8501",
        "https://example.com",
    )


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "ftp://example.com",
        "https://example.com/path",
        "https://example.com?query=test",
        "https://example.com#fragment",
    ],
)
def test_invalid_cors_origin(origin):
    """Rechaza orígenes CORS incompatibles."""

    with pytest.raises(ValidationError):
        ApiSettings(CORS_ORIGINS=origin)


def test_authorized_user_ids():
    """Convierte los identificadores autorizados a UUID."""

    user_id = "550e8400-e29b-41d4-a716-446655440000"

    settings = ApiSettings(
        USER_TIER_ALLOWED_USER_IDS=user_id
    )

    assert settings.USER_TIER_ALLOWED_USER_IDS == frozenset({
        UUID(user_id),
    })


def test_invalid_authorized_user_id():
    """Rechaza identificadores que no sean UUID."""

    with pytest.raises(ValidationError):
        ApiSettings(
            USER_TIER_ALLOWED_USER_IDS="usuario-invalido"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("PORT", 0),
        ("PORT", 65536),
        ("RATE_LIMIT_PER_MINUTE", -1),
        ("SESSION_TTL_SECONDS", 0),
        ("BCRYPT_ROUNDS", 3),
        ("AGENT_MAX_WORKERS", 2),
        ("ASK_TIMEOUT_SECONDS", 0),
        ("ASK_TIMEOUT_SECONDS", float("inf")),
        ("IMAGE_UPLOAD_MAX_BYTES", 1),
        ("IMAGE_UPLOAD_MAX_BYTES", 21 * 1024 * 1024),
        ("IMAGE_UPLOAD_MAX_PIXELS", 1),
        ("IMAGE_UPLOAD_MAX_PIXELS", 33_000_000),
    ],
)
def test_invalid_settings(field, value):
    """Rechaza parámetros operativos inválidos."""

    with pytest.raises(ValidationError):
        ApiSettings(**{field: value})


def test_settings_are_immutable():
    """Impide modificar la configuración después de cargarla."""

    settings = ApiSettings()

    with pytest.raises(ValidationError):
        settings.RATE_LIMIT_PER_MINUTE = 100


def test_dotenv_loading(isolated_env):
    """Carga los parámetros desde un archivo .env aislado."""

    dotenv_path = isolated_env / ".env"

    dotenv_path.write_text(
        "RATE_LIMIT_PER_MINUTE=20\n",
        encoding="utf-8",
    )

    settings = load_settings()

    assert settings.RATE_LIMIT_PER_MINUTE == 20


def test_environment_priority(isolated_env, monkeypatch):
    """Las variables del entorno prevalecen sobre .env."""

    dotenv_path = isolated_env / ".env"

    dotenv_path.write_text(
        "RATE_LIMIT_PER_MINUTE=20\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "40")

    settings = load_settings()

    assert settings.RATE_LIMIT_PER_MINUTE == 40


def test_invalid_environment_setting(isolated_env, monkeypatch):
    """Comunica errores de configuración de forma controlada."""

    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "-1")

    with pytest.raises(ValueError, match="RATE_LIMIT_PER_MINUTE"):
        load_settings()


def test_invalid_secret_is_not_exposed(isolated_env, monkeypatch):
    """Los errores de configuración no exponen credenciales."""

    secret = "credencial-ficticia-no-valida"

    monkeypatch.setenv("DATABASE_URL", secret)

    with pytest.raises(ValueError) as exc_info:
        load_settings()

    assert "DATABASE_URL" in str(exc_info.value)
    assert secret not in str(exc_info.value)


# =========================================================
# CONFIGURACIÓN ADMINISTRATIVA
# =========================================================


def test_admin_settings() -> None:
    """Acepta credenciales administrativas válidas."""
    password = generate_secret()
    api_key = generate_secret()

    settings = ApiSettings(
        ADMIN_EMAIL="  ADMIN-FICTICIO@EXAMPLE.COM  ",
        ADMIN_PASSWORD=password,
        API_KEY=api_key,
    )

    assert settings.missing_admin_settings() == ()

    assert settings.ADMIN_EMAIL is not None
    assert settings.ADMIN_PASSWORD is not None
    assert settings.API_KEY is not None

    assert settings.ADMIN_EMAIL.get_secret_value() == (
        "admin-ficticio@example.com"
    )

    assert settings.ADMIN_PASSWORD.get_secret_value() == password
    assert settings.API_KEY.get_secret_value() == api_key


def test_missing_admin_settings() -> None:
    """Identifica las credenciales administrativas ausentes."""
    settings = ApiSettings()

    assert settings.missing_admin_settings() == (
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "API_KEY",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ADMIN_EMAIL", "email-invalido"),
        ("ADMIN_PASSWORD", "corta"),
        ("ADMIN_PASSWORD", "Password con espacios"),
        ("ADMIN_PASSWORD", "a" * 73),
        ("API_KEY", "clave-corta"),
        ("API_KEY", "A" * 42),
        ("API_KEY", "A" * 44),
        ("API_KEY", "A" * 42 + "B"),
        ("API_KEY", "A" * 42 + "="),
        ("API_KEY", "A" * 42 + " "),
        ("API_KEY", "+" + "A" * 42),
    ],
)
def test_invalid_admin_credentials(
    field: str,
    value: str,
) -> None:
    """Rechaza credenciales administrativas incompatibles."""
    with pytest.raises(ValidationError):
        ApiSettings(**{field: value})


def test_generated_admin_credentials() -> None:
    """Acepta el formato producido por el generador de secretos."""
    for _ in range(100):
        settings = ApiSettings(
            ADMIN_EMAIL="admin-ficticio@example.com",
            ADMIN_PASSWORD=generate_secret(),
            API_KEY=generate_secret(),
        )

        assert settings.missing_admin_settings() == ()


def test_admin_environment_loading(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Carga las credenciales desde un entorno aislado."""
    email = "admin-ficticio@example.com"
    password = generate_secret()
    api_key = generate_secret()

    monkeypatch.setenv("ADMIN_EMAIL", email)
    monkeypatch.setenv("ADMIN_PASSWORD", password)
    monkeypatch.setenv("API_KEY", api_key)

    settings = load_settings()

    assert settings.missing_admin_settings() == ()

    assert settings.ADMIN_EMAIL is not None
    assert settings.ADMIN_PASSWORD is not None
    assert settings.API_KEY is not None

    assert settings.ADMIN_EMAIL.get_secret_value() == email
    assert settings.ADMIN_PASSWORD.get_secret_value() == password
    assert settings.API_KEY.get_secret_value() == api_key


def test_invalid_admin_secret_not_exposed(
    isolated_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Impide exponer una credencial inválida al diagnosticar."""
    secret = "credencial-administrativa-ficticia-invalida"

    monkeypatch.setenv("API_KEY", secret)

    with pytest.raises(ValueError) as exc_info:
        load_settings()

    assert "API_KEY" in str(exc_info.value)
    assert secret not in str(exc_info.value)