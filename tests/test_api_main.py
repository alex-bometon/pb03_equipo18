"""Pruebas de inicialización del backend FastAPI."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

import api.main as api_main
from api.config import ApiSettings


@pytest.fixture
def client(monkeypatch):
    """Inicializa FastAPI con una configuración controlada."""

    settings = ApiSettings()

    monkeypatch.setattr(
        api_main,
        "load_settings",
        lambda: settings,
    )

    with TestClient(api_main.app) as test_client:
        yield test_client


def test_lifespan_settings(client):
    """Lifespan almacena la configuración de la aplicación."""

    assert isinstance(
        client.app.state.settings,
        ApiSettings,
    )


def test_swagger_available(client):
    """Swagger está disponible sin autenticación."""

    response = client.get("/docs")

    assert response.status_code == 200


def test_openapi_available(client):
    """La especificación OpenAPI está disponible."""

    response = client.get("/openapi.json")

    assert response.status_code == 200

    data = response.json()

    assert data["info"]["title"] == "ReciclaTÍA API"
    assert "openapi" in data
    assert "paths" in data


def test_settings_loaded_once(monkeypatch):
    """La configuración se carga una vez por ciclo de vida."""

    loader = Mock(return_value=ApiSettings())

    monkeypatch.setattr(
        api_main,
        "load_settings",
        loader,
    )

    with TestClient(api_main.app) as client:
        client.get("/docs")
        client.get("/openapi.json")

    loader.assert_called_once_with()


def test_invalid_configuration_prevents_startup(monkeypatch):
    """Una configuración inválida impide el arranque."""

    def invalid_settings():
        raise ValueError("Configuración inválida de prueba")

    monkeypatch.setattr(
        api_main,
        "load_settings",
        invalid_settings,
    )

    with pytest.raises(
        ValueError,
        match="Configuración inválida de prueba",
    ):
        with TestClient(api_main.app):
            pass
