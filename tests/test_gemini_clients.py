"""Pruebas de configuración de los clientes de Gemini."""

from unittest.mock import Mock

import pytest

from config import (
    AGENT_MODEL,
    AGENT_TEMPERATURE,
    SUPERVISOR_TEMPERATURE,
)
from src import gemini_client, llm


def test_cliente_nativo_timeout_y_reintentos(monkeypatch):
    """Configura 45 segundos y un único intento en el SDK."""
    monkeypatch.setenv("GEMINI_API_KEY", "clave-ficticia-de-prueba")

    monkeypatch.setattr(gemini_client, "load_dotenv", Mock())

    constructor = Mock()

    monkeypatch.setattr(gemini_client.genai, "Client", constructor)

    cliente = gemini_client.crear_cliente_gemini()

    assert cliente is constructor.return_value

    constructor.assert_called_once()

    opciones = constructor.call_args.kwargs["http_options"]

    assert opciones.timeout == 45000
    assert opciones.retry_options.attempts == 1


@pytest.mark.parametrize("supervisor", [False, True])
def test_cliente_langchain_timeout_y_reintentos(
    monkeypatch,
    supervisor,
):
    """Configura el timeout y desactiva reintentos del modelo."""
    monkeypatch.setattr(llm, "load_dotenv", Mock())

    constructor = Mock()

    monkeypatch.setattr(llm, "ChatGoogleGenerativeAI", constructor)

    modelo = llm.get_llm(supervisor=supervisor)

    assert modelo is constructor.return_value

    temperatura = SUPERVISOR_TEMPERATURE if supervisor else AGENT_TEMPERATURE

    constructor.assert_called_once_with(
        model=AGENT_MODEL,
        temperature=temperatura,
        timeout=45,
        max_retries=1,
    )