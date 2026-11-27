"""Pruebas de inicialización del backend FastAPI."""

from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from starlette.exceptions import HTTPException

import api.main as api_main
from api.config import ApiSettings
from api.error_catalog import ERROR_CATALOG, ErrorCode
from api.errors import ApiError
from api.rate_limit import SlidingWindowLog
from api.request_context import REQUEST_ID_HEADER
from api.service import ControlAdmision, EjecutorAsistente
from api.security import SessionStore, generate_secret


@pytest.fixture
def mock_db(monkeypatch):
    """Simula PostgreSQL sin establecer conexiones reales."""
    settings = ApiSettings(
        DATABASE_URL="postgresql://test:test@localhost/test_db",
        ADMIN_EMAIL="admin-ficticio@example.com",
        ADMIN_PASSWORD=generate_secret(),
        API_KEY=generate_secret(),
    )

    engine = Mock(spec=Engine)
    loader = Mock(return_value=settings)
    creator = Mock(return_value=engine)
    checker = Mock()
    initializer = Mock()
    admin_bootstrap = Mock()

    dummy_hash_creator = Mock(
        return_value="hash-ficticio-de-prueba",
    )

    monkeypatch.setattr(api_main, "load_settings", loader)
    monkeypatch.setattr(api_main, "create_db_engine", creator)
    monkeypatch.setattr(api_main, "check_database", checker)
    monkeypatch.setattr(api_main, "ensure_schema", initializer)

    monkeypatch.setattr(
        api_main,
        "bootstrap_admin_api_key",
        admin_bootstrap,
    )

    monkeypatch.setattr(
        api_main,
        "create_dummy_password_hash",
        dummy_hash_creator,
    )

    return {
        "settings": settings,
        "engine": engine,
        "loader": loader,
        "creator": creator,
        "checker": checker,
        "initializer": initializer,
        "admin_bootstrap": admin_bootstrap,
        "dummy_hash_creator": dummy_hash_creator,
    }


@pytest.fixture
def client(mock_db):
    """Inicializa FastAPI con una infraestructura simulada."""

    with TestClient(api_main.app) as test_client:
        yield test_client


def test_lifespan_settings(client, mock_db):
    assert client.app.state.settings is mock_db["settings"]


def test_swagger_available(client):
    assert client.get("/docs").status_code == 200


def test_openapi_available(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200

    data = response.json()

    assert data["info"]["title"] == "ReciclaTÍA API"
    assert "openapi" in data
    assert "paths" in data


def test_settings_loaded_once(mock_db):
    with TestClient(api_main.app) as client:
        client.get("/docs")
        client.get("/openapi.json")

    mock_db["loader"].assert_called_once_with()


def test_invalid_configuration_prevents_startup(mock_db):
    mock_db["loader"].side_effect = ValueError(
        "Configuración inválida de prueba"
    )

    with pytest.raises(ValueError):
        with TestClient(api_main.app):
            pass

    mock_db["creator"].assert_not_called()


def test_missing_database_url_prevents_startup(mock_db):
    mock_db["loader"].return_value = ApiSettings()

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        with TestClient(api_main.app):
            pass

    mock_db["creator"].assert_not_called()


def test_database_initialization(mock_db):
    with TestClient(api_main.app) as client:
        assert client.app.state.engine is mock_db["engine"]

    mock_db["creator"].assert_called_once()
    mock_db["checker"].assert_called_once_with(mock_db["engine"])
    mock_db["initializer"].assert_called_once_with(
        mock_db["engine"]
    )


def test_database_failure_prevents_startup(mock_db):
    mock_db["checker"].side_effect = RuntimeError(
        "PostgreSQL no disponible"
    )

    with pytest.raises(
        RuntimeError,
        match="No se ha podido inicializar PostgreSQL",
    ):
        with TestClient(api_main.app):
            pass

    mock_db["initializer"].assert_not_called()
    mock_db["engine"].dispose.assert_called_once()


def test_schema_failure_prevents_startup(mock_db):
    mock_db["initializer"].side_effect = RuntimeError(
        "Error creando tablas"
    )

    with pytest.raises(RuntimeError):
        with TestClient(api_main.app):
            pass

    mock_db["engine"].dispose.assert_called_once()


def test_engine_disposed_on_shutdown(mock_db):
    with TestClient(api_main.app):
        mock_db["engine"].dispose.assert_not_called()

    mock_db["engine"].dispose.assert_called_once()

def test_exception_handlers_registered() -> None:
    """Comprueba el registro de los manejadores."""
    expected = {
        ApiError,
        RequestValidationError,
        HTTPException,
        Exception,
    }

    registered = set(api_main.app.exception_handlers)

    assert expected.issubset(registered)


def test_application_error_response(client: TestClient) -> None:
    """Comprueba el contrato de error de la aplicación real."""
    response = client.get("/ruta-inexistente")

    code = ErrorCode.ROUTE_NOT_FOUND
    definition = ERROR_CATALOG[code]
    request_id = response.headers[REQUEST_ID_HEADER]

    assert response.status_code == definition.status_code

    assert response.json() == {
        "code": code.value,
        "message": definition.message,
        "request_id": request_id,
    }

    assert str(UUID(request_id)) == request_id


@pytest.mark.parametrize(
    "path",
    ["/docs", "/openapi.json", "/ruta-inexistente"],
)
def test_application_request_id(
    client: TestClient,
    path: str,
) -> None:
    """Comprueba la trazabilidad de la aplicación real."""
    response = client.get(path)

    request_id = response.headers[REQUEST_ID_HEADER]

    assert UUID(request_id).version == 4
    assert str(UUID(request_id)) == request_id


# =========================================================
# INICIALIZACIÓN DE SEGURIDAD
# =========================================================


def test_dummy_hash_initialized(mock_db) -> None:
    """Genera el hash auxiliar durante la inicialización."""
    with TestClient(api_main.app) as client:
        assert client.app.state.dummy_password_hash == (
            "hash-ficticio-de-prueba"
        )

        client.get("/docs")
        client.get("/openapi.json")

    mock_db["dummy_hash_creator"].assert_called_once_with(
        mock_db["settings"].BCRYPT_ROUNDS,
    )


def test_security_failure_prevents_startup(mock_db) -> None:
    """Impide arrancar si falla la inicialización de seguridad."""
    mock_db["dummy_hash_creator"].side_effect = RuntimeError(
        "informacion-sensible-ficticia",
    )

    with pytest.raises(RuntimeError) as exc_info:
        with TestClient(api_main.app):
            pass

    assert str(exc_info.value) == (
        "No se ha podido inicializar la seguridad."
    )

    mock_db["engine"].dispose.assert_called_once()


# =========================================================
# CICLO DE VIDA DE LAS SESIONES
# =========================================================


def test_session_store_initialized(
    client: TestClient,
) -> None:
    """Inicializa el gestor de sesiones durante el arranque."""
    store = client.app.state.session_store

    assert isinstance(store, SessionStore)


def test_session_store_ttl(
    client: TestClient,
) -> None:
    """Utiliza la duración configurada para las sesiones."""
    store = client.app.state.session_store
    settings = client.app.state.settings

    _, session = store.create(uuid4())

    duration = session.expires_at - session.created_at

    assert duration.total_seconds() == settings.SESSION_TTL_SECONDS


def test_session_store_restart(mock_db) -> None:
    """Descarta las sesiones anteriores al reiniciar el backend."""
    with TestClient(api_main.app) as client:
        first_store = client.app.state.session_store
        token, _ = first_store.create(uuid4())

    with TestClient(api_main.app) as client:
        second_store = client.app.state.session_store

        assert first_store is not second_store

        with pytest.raises(ApiError) as exc_info:
            second_store.get(token)

        assert exc_info.value.code == ErrorCode.INVALID_SESSION


# =========================================================
# INICIALIZACIÓN ADMINISTRATIVA
# =========================================================


def test_admin_bootstrap_initialized(mock_db) -> None:
    """Ejecuta el aprovisionamiento una vez por arranque."""
    with TestClient(api_main.app) as client:
        client.get("/docs")
        client.get("/openapi.json")

    mock_db["admin_bootstrap"].assert_called_once_with(
        mock_db["engine"],
        mock_db["settings"],
    )


def test_admin_bootstrap_initialization_order(mock_db) -> None:
    """Aprovisiona la administración después de crear las tablas."""
    sequence = Mock()

    sequence.attach_mock(
        mock_db["checker"],
        "check_database",
    )

    sequence.attach_mock(
        mock_db["initializer"],
        "ensure_schema",
    )

    sequence.attach_mock(
        mock_db["admin_bootstrap"],
        "bootstrap_admin",
    )

    sequence.attach_mock(
        mock_db["dummy_hash_creator"],
        "create_dummy_hash",
    )

    with TestClient(api_main.app):
        pass

    methods = [
        call[0]
        for call in sequence.mock_calls
    ]

    assert methods == [
        "check_database",
        "ensure_schema",
        "bootstrap_admin",
        "create_dummy_hash",
    ]


@pytest.mark.parametrize(
    "field",
    [
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "API_KEY",
    ],
)
def test_missing_admin_settings_prevent_startup(
    mock_db,
    field: str,
) -> None:
    """Impide arrancar si falta una credencial administrativa."""
    settings = mock_db["settings"].model_copy(
        update={field: None},
    )

    mock_db["loader"].return_value = settings

    with pytest.raises(RuntimeError) as exc_info:
        with TestClient(api_main.app):
            pass

    assert field in str(exc_info.value)

    mock_db["creator"].assert_not_called()
    mock_db["admin_bootstrap"].assert_not_called()


def test_admin_bootstrap_failure_prevents_startup(
    mock_db,
) -> None:
    """Impide arrancar si falla el aprovisionamiento."""
    mock_db["admin_bootstrap"].side_effect = RuntimeError(
        "informacion-sensible-ficticia",
    )

    with pytest.raises(RuntimeError) as exc_info:
        with TestClient(api_main.app):
            pass

    assert str(exc_info.value) == "No se ha podido aprovisionar la administración."

    mock_db["dummy_hash_creator"].assert_not_called()
    mock_db["engine"].dispose.assert_called_once()


def test_admin_bootstrap_on_restart(mock_db) -> None:
    """Comprueba las credenciales en cada arranque."""
    with TestClient(api_main.app):
        pass

    with TestClient(api_main.app):
        pass

    assert mock_db["admin_bootstrap"].call_count == 2


def test_rate_limiter_initialized(client):
    """Inicializa el limitador durante el arranque."""
    assert isinstance(client.app.state.rate_limiter, SlidingWindowLog)


def test_rate_limiter_restart(mock_db):
    """Reinicia los contadores junto con el backend."""
    with TestClient(api_main.app) as client:
        primero = client.app.state.rate_limiter

    with TestClient(api_main.app) as client:
        segundo = client.app.state.rate_limiter

    assert primero is not segundo

def test_admision_initialized(client):
    """Inicializa los controles compartidos de admisión."""
    assert isinstance(client.app.state.admision, ControlAdmision)


def test_executor_initialized(client):
    """Inicializa el executor compartido durante el arranque."""
    assert isinstance(
        client.app.state.ejecutor,
        EjecutorAsistente,
    )


def test_executor_shutdown(mock_db, monkeypatch):
    """Cierra el executor antes de disponer el engine."""
    sequence = Mock()

    sequence.attach_mock(
        mock_db["engine"].dispose,
        "dispose_engine",
    )

    cierre = Mock()
    sequence.attach_mock(cierre, "cerrar_executor")

    with TestClient(api_main.app) as client:
        monkeypatch.setattr(
            client.app.state.ejecutor,
            "cerrar",
            cierre,
        )

    assert [call[0] for call in sequence.mock_calls] == [
        "cerrar_executor",
        "dispose_engine",
    ]