
"""Pruebas de inicialización del backend FastAPI."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

import api.main as api_main
from api.config import ApiSettings


@pytest.fixture
def mock_db(monkeypatch):
    """Simula PostgreSQL sin establecer conexiones reales."""

    settings = ApiSettings(
        DATABASE_URL="postgresql://test:test@localhost/test_db"
    )

    engine = Mock(spec=Engine)
    loader = Mock(return_value=settings)
    creator = Mock(return_value=engine)
    checker = Mock()
    initializer = Mock()

    monkeypatch.setattr(api_main, "load_settings", loader)
    monkeypatch.setattr(api_main, "create_db_engine", creator)
    monkeypatch.setattr(api_main, "check_database", checker)
    monkeypatch.setattr(api_main, "ensure_schema", initializer)

    return {
        "settings": settings,
        "engine": engine,
        "loader": loader,
        "creator": creator,
        "checker": checker,
        "initializer": initializer,
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
