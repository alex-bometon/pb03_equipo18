"""Pruebas de observabilidad de proveedores y bibliotecas."""

import asyncio
import json
import logging
from io import BytesIO
from types import SimpleNamespace
from typing import TypedDict
from unittest.mock import Mock
from uuid import uuid4

import pytest
import requests

from fastapi import UploadFile
from langgraph.graph import START, END, StateGraph

import src.observability as observabilidad
from api.config import ApiSettings
from api.errors import ApiError
from api.images import recibir_imagen
from src import generate
from src.observability import (
    EVENT_LOGGER,
    configurar_logs_externos,
    observar_llamada,
    registrar_evento,
    request_id_context,
)
from src.tools.api_puntos_limpios import (
    buscar_puntos_limpios_cercanos,
)


SECRETO = "dato-privado-no-registrable"


@pytest.fixture
def eventos(caplog, monkeypatch):
    """Captura eventos técnicos sin duplicar registros."""
    monkeypatch.setattr(EVENT_LOGGER, "propagate", False)
    monkeypatch.setattr(EVENT_LOGGER, "handlers", [caplog.handler])

    caplog.set_level(logging.INFO, logger=EVENT_LOGGER.name)

    token = request_id_context.set(str(uuid4()))

    def recuperar():
        return [
            json.loads(registro.getMessage())
            for registro in caplog.records
            if registro.name == EVENT_LOGGER.name
        ]

    try:
        yield recuperar

    finally:
        request_id_context.reset(token)


@pytest.mark.parametrize(
    "uso",
    [
        {"total_tokens": 150},
        SimpleNamespace(total_token_count=150),
    ],
)
def test_observar_llamada_conserva_resultado(uso, eventos):
    """Registra tokens de Gemini nativo y LangChain."""
    respuesta = SimpleNamespace(
        text=SECRETO,
        usage_metadata=uso,
    )

    llamada = Mock(return_value=respuesta)

    resultado = observar_llamada(
        "gemini",
        "prueba",
        llamada,
        SECRETO,
    )

    assert resultado is respuesta

    llamada.assert_called_once_with(SECRETO)

    registros = eventos()

    assert len(registros) == 1
    assert registros[0]["event"] == "provider_completed"
    assert registros[0]["total_tokens"] == 150
    assert registros[0]["duration_ms"] >= 0
    assert SECRETO not in json.dumps(registros)


def test_observar_llamada_propaga_excepcion(eventos):
    """Conserva el error original sin registrar su contenido."""
    error_original = RuntimeError(SECRETO)
    llamada = Mock(side_effect=error_original)

    with pytest.raises(RuntimeError) as error:
        observar_llamada("gemini", "prueba", llamada)

    assert error.value is error_original

    registros = eventos()

    assert len(registros) == 1
    assert registros[0]["event"] == "provider_failed"
    assert registros[0]["level"] == "ERROR"
    assert registros[0]["total_tokens"] is None
    assert SECRETO not in json.dumps(registros)


def test_registra_reintentos_generacion(eventos, monkeypatch):
    """Contabiliza cada intento efectivo de generación."""
    respuesta = SimpleNamespace(
        text="respuesta ficticia",
        usage_metadata=SimpleNamespace(total_token_count=80),
    )

    cliente = Mock()

    cliente.models.generate_content.side_effect = [
        TimeoutError(SECRETO),
        respuesta,
    ]

    monkeypatch.setattr(generate, "GENERATION_MAX_RETRIES", 2)
    monkeypatch.setattr(generate.time, "sleep", Mock())

    resultado = generate._solicitar_generacion(
        cliente,
        "pregunta de prueba",
        "contexto de prueba",
    )

    assert resultado is respuesta
    assert cliente.models.generate_content.call_count == 2

    registros = eventos()

    assert [r["event"] for r in registros] == [
        "provider_failed",
        "provider_completed",
    ]

    assert registros[1]["total_tokens"] == 80
    assert SECRETO not in json.dumps(registros)


def test_observabilidad_fallback_geografico(eventos, monkeypatch):
    """Registra el fallo municipal y la activación del respaldo."""
    monkeypatch.setattr(
        "src.tools.api_puntos_limpios.requests.get",
        Mock(side_effect=requests.Timeout(SECRETO)),
    )

    monkeypatch.setattr(
        "src.tools.api_puntos_limpios.consultar_puntos_limpios_locales",
        Mock(return_value=[]),
    )

    resultado = buscar_puntos_limpios_cercanos.invoke({
        "latitud": 40.4,
        "longitud": -3.7,
        "tipo": "todos",
    })

    assert resultado["fuente"] == "corpus_local"

    registros = eventos()

    assert [r["event"] for r in registros] == [
        "provider_failed",
        "geographic_fallback",
    ]

    assert registros[0]["scopes"] == [
        "arcgis",
        "puntos_limpios",
    ]

    assert SECRETO not in json.dumps(registros)
    assert "40.4" not in registros[0]["scopes"]


def test_observabilidad_imagen_rechazada(eventos):
    """Registra el rechazo sin almacenar datos del archivo."""
    imagen = UploadFile(
        filename=SECRETO,
        file=BytesIO(SECRETO.encode()),
    )

    with pytest.raises(ApiError) as error:
        asyncio.run(
            recibir_imagen(imagen, settings=ApiSettings())
        )

    registros = eventos()

    assert len(registros) == 1
    assert registros[0]["event"] == "image_rejected"
    assert registros[0]["error_code"] == error.value.code.value
    assert SECRETO not in json.dumps(registros)


def test_langgraph_conserva_contexto(eventos):
    """Comprueba la propagación a los nodos reales de LangGraph."""

    class EstadoPrueba(TypedDict):
        valor: int

    def nodo(estado: EstadoPrueba) -> dict:
        registrar_evento("test_graph_context")
        return {"valor": estado["valor"] + 1}

    grafo = StateGraph(EstadoPrueba)

    grafo.add_node("nodo", nodo)
    grafo.add_edge(START, "nodo")
    grafo.add_edge("nodo", END)

    aplicacion = grafo.compile()

    request_id = request_id_context.get()

    resultado = aplicacion.invoke({"valor": 0})

    assert resultado["valor"] == 1

    registros = eventos()

    assert len(registros) == 1
    assert registros[0]["request_id"] == request_id


def test_logs_externos_no_exponen_secretos(
    monkeypatch,
    caplog,
):
    """Bloquea los registros externos y sus descendientes."""
    padre = logging.getLogger("prueba_externa")
    hijo = logging.getLogger("prueba_externa.cliente")

    for logger in (padre, hijo):
        monkeypatch.setattr(logger, "level", logger.level)
        monkeypatch.setattr(logger, "handlers", [caplog.handler])
        monkeypatch.setattr(logger, "propagate", True)

    monkeypatch.setattr(
        observabilidad,
        "LOGGERS_EXTERNOS",
        ("prueba_externa",),
    )

    configurar_logs_externos()

    padre.error(SECRETO)
    hijo.error(SECRETO)

    assert padre.propagate is False
    assert hijo.propagate is False
    assert SECRETO not in caplog.text