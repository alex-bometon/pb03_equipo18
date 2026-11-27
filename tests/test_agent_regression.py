"""Pruebas de regresión del sistema multiagente ReciclaTIA.

Se comprueban la orquestación, las herramientas, los límites y el HITL
sin utilizar Gemini, la API municipal ni otros servicios externos.
"""

from __future__ import annotations

from uuid import UUID
import json
from io import BytesIO
from pathlib import Path
from copy import deepcopy
from unittest.mock import Mock
from contextlib import ExitStack
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy.engine import Engine
from sqlmodel import Session

from PIL import Image

from api.dependencies import reservar_hilo_autorizado
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.request_context import AuthContext
from api.schemas import AskOut
from api.security import generate_secret, hash_secret
from api.service import (
    ControlAdmision,
    identificar_entrada_visual,
    validar_decision_hitl,
    validar_nuevo_turno,
    validar_resultado_agente,
)

from config import (
    FUENTES_OFICIALES,
    GEO_DEFAULT_RADIUS_METERS,
    MAX_ITER,
    MAX_TOOL_CALLS_PER_TURN,
    MAX_TURNS_DEFAULT,
)
from src import db
from src.enums import ApiKeyRole
from src.models import ApiKey
from src.agent import (
    aprobar_plan,
    nuevo_thread_id,
    obtener_estado_hilo,
    procesar_turno,
)
from src.agent_routing import (
    requiere_llm_supervisor,
    resolver_enrutamiento,
)
from src.agent_tool_loop import ejecutar_especialista
from src.graph import build_graph
from src.nodes import supervisor
from src.state import crear_estado_grafo, crear_estado_producto
from src.tools import ejecutar_tool_estructurado


# =========================================================
# DOBLES DE PRUEBA
# =========================================================


class ModeloFalso:
    """Emula respuestas de LangChain sin inicializar Gemini."""

    def __init__(self, respuestas: list[AIMessage]) -> None:
        self._respuestas = iter(respuestas)
        self.herramientas: list[str] = []

    def bind_tools(self, herramientas):
        """Registra las herramientas disponibles para el especialista."""
        self.herramientas = [tool.name for tool in herramientas]
        return self

    def invoke(self, mensajes):
        """Devuelve la siguiente respuesta preparada."""
        assert mensajes
        return next(self._respuestas)


def _llamada(
    nombre: str,
    argumentos: dict,
    identificador: str,
) -> AIMessage:
    """Construye una solicitud de herramienta de LangChain."""
    return AIMessage(
        content="",
        tool_calls=[{
            "name": nombre,
            "args": argumentos,
            "id": identificador,
        }],
    )


def _resultado_rag(*, abstencion: bool = False) -> dict:
    """Simula la respuesta estructurada del RAG PB03."""
    if abstencion:
        return {
            "respuesta": "No hay evidencia documental suficiente.",
            "abstencion": True,
            "motivo": "evidencia_insuficiente",
            "fuentes": [],
        }

    return {
        "respuesta": "Los envases van al contenedor amarillo. [C1]",
        "abstencion": False,
        "motivo": None,
        "fuentes": [{
            "chunk_id": "C1",
            "source": "tipos_residuos.csv",
            "path": "data/raw/csv/tipos_residuos.csv",
        }],
    }


def _resultado_geografico() -> dict:
    """Simula la respuesta estructurada de la API geográfica."""
    punto = {
        "id": 123,
        "tipo": "Proximidad",
        "direccion": "Calle de Prueba, 1",
        "latitud": 40.4199,
        "longitud": -3.7038,
        "distancia_metros": 350.0,
        "fuente": "api",
    }

    return {
        "fuente": "api",
        "tipo_solicitado": "proximidad",
        "radio_metros": GEO_DEFAULT_RADIUS_METERS,
        "total_encontrados": 1,
        "puntos": [punto],
        "puntos_candidatos": [deepcopy(punto)],
        "aviso": None,
    }


def _crear_conversacion(
    *,
    max_turns: int = MAX_TURNS_DEFAULT,
):
    """Crea una conversación con identificador independiente."""
    thread_id = nuevo_thread_id()
    estado = crear_estado_producto(
        thread_id,
        max_turns=max_turns,
    )
    return estado, thread_id


def _ejecutor_simulado(nombre, args, *, rol):
    """Simula resultados RAG, geográficos y visuales."""
    assert rol in {"residuos", "puntos"}

    if nombre == "consultar_rag":
        assert isinstance(args["pregunta"], str)
        datos = _resultado_rag()

        if rol == "puntos":
            datos["respuesta"] = (
                "Los puntos limpios de proximidad son "
                "instalaciones municipales. [C1]"
            )
            datos["fuentes"][0].update({
                "source": "puntos_limpios_proximidad.csv",
                "path": "data/raw/csv/puntos_limpios_proximidad.csv",
            })

    elif nombre == "buscar_puntos_limpios_cercanos":
        assert isinstance(args["latitud"], float)
        assert isinstance(args["longitud"], float)
        datos = _resultado_geografico()

    elif nombre == "describir_imagen":
        assert args["ruta_imagen"] == "assets/imagen_demo.jpg"
        datos = "Una botella de plástico transparente."
    elif nombre == "hora_actual":
        assert args == {}
        datos = "2026-10-26T10:00:00+01:00"

    else:
        raise AssertionError(f"Herramienta no prevista: {nombre}")

    return {
        "ok": True,
        "nombre": nombre,
        "datos": deepcopy(datos),
        "error": None,
    }


# =========================================================
# AISLAMIENTO DE DEPENDENCIAS
# =========================================================


@pytest.fixture
def aislado(monkeypatch):
    """Aísla MemorySaver y bloquea llamadas externas no simuladas."""
    app = build_graph()

    monkeypatch.setattr("src.agent.get_app", lambda: app)
    monkeypatch.setattr("src.graph.get_app", lambda: app)

    def prohibido(*args, **kwargs):
        raise AssertionError(
            "No se permiten llamadas externas en estos tests."
        )

    monkeypatch.setattr("src.nodes.get_llm", prohibido)
    monkeypatch.setattr("src.agent_tool_loop.get_llm", prohibido)
    monkeypatch.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        prohibido,
    )

    return monkeypatch


# =========================================================
# CLASIFICACIÓN Y HITL
# =========================================================


def test_clasificacion_directa_y_aprobacion(aislado):
    """El RAG directo alcanza HITL sin LLM adicional."""
    herramienta = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramienta,
    )

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿Dónde tiro una botella de plástico?",
        hilo,
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True
    assert estado["done"] is False
    assert estado["respuesta"] == _resultado_rag()["respuesta"]
    assert estado["estado_evidencia"] == "suficiente"

    decisiones_directas = [
        evento
        for evento in estado["log"]
        if evento["accion"] == "ruta_directa"
    ]

    assert len(decisiones_directas) == 3
    herramienta.assert_called_once()
    assert herramienta.call_args.args[0] == "consultar_rag"
    assert len(estado["fuentes"]) == 1

    propuesta = validar_resultado_agente(
        estado,
        thread_id=UUID(hilo),
        turnos_esperados=1,
        aprobado_esperado=None,
    )

    assert isinstance(propuesta, AskOut)
    assert propuesta.pendiente_hitl is True
    assert propuesta.approval_id == estado["approval_id"]
    assert propuesta.geografia == []

    assert len(propuesta.fuentes) == 1

    fuente = propuesta.fuentes[0]

    assert fuente.chunk_id == "C1"
    assert fuente.source == "tipos_residuos.csv"
    assert fuente.rol == "residuos"
    assert fuente.id_llamada

    assert str(fuente.url) == (
        FUENTES_OFICIALES["tipos_residuos.csv"]
    )

    estado = aprobar_plan(hilo, True, approval_id=estado["approval_id"])

    assert estado["done"] is True
    assert estado["pendiente_hitl"] is False
    assert estado["historial_turnos"][-1]["aprobado"] is True

    resultado = validar_resultado_agente(
        estado,
        thread_id=UUID(hilo),
        turnos_esperados=1,
        aprobado_esperado=True,
    )

    assert resultado.done is True
    assert resultado.pendiente_hitl is False
    assert resultado.approval_id is None
    assert resultado.fuentes == propuesta.fuentes
    assert resultado.plan == propuesta.plan
    assert obtener_estado_hilo(hilo) == estado


def test_rechazo_y_reformulacion(aislado):
    """El rechazo permite una nueva consulta en el mismo hilo."""
    herramienta = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramienta,
    )

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿Dónde tiro una botella?",
        hilo,
    )

    estado = aprobar_plan(hilo, False, approval_id=estado["approval_id"])

    assert estado["done"] is False
    assert estado["pendiente_hitl"] is False
    assert estado["plan"] == []
    assert estado["historial_turnos"][-1]["aprobado"] is False

    rechazado = validar_resultado_agente(
        estado,
        thread_id=UUID(hilo),
        turnos_esperados=1,
        aprobado_esperado=False,
    )

    assert rechazado.done is False
    assert rechazado.plan == []
    assert rechazado.fuentes == []
    assert rechazado.geografia == []
    assert rechazado.approval_id is None

    estado = procesar_turno(
        estado,
        "¿Dónde tiro una lata de refresco?",
        hilo,
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True
    assert estado["turnos_consumidos"] == 2
    assert herramienta.call_count == 2

    reformulado = validar_resultado_agente(
        estado,
        thread_id=UUID(hilo),
        turnos_esperados=2,
        aprobado_esperado=None,
    )

    assert reformulado.pendiente_hitl is True
    assert reformulado.approval_id is not None
    assert reformulado.thread_id == hilo
    assert obtener_estado_hilo(hilo) == estado


def test_no_se_admiten_turnos_mientras_hitl(aislado):
    """Impide realizar otra consulta antes de decidir sobre el plan."""
    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        _ejecutor_simulado,
    )

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿Dónde tiro una botella?",
        hilo,
    )

    with pytest.raises(ValueError, match="pendiente"):
        procesar_turno(
            estado,
            "¿Dónde tiro una lata?",
            hilo,
        )


def test_limite_turnos_tras_rechazo(aislado):
    """El rechazo no permite superar max_turns."""
    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        _ejecutor_simulado,
    )

    estado, hilo = _crear_conversacion(max_turns=1)

    estado = procesar_turno(
        estado,
        "¿Dónde tiro una botella?",
        hilo,
    )

    estado = aprobar_plan(hilo, False, approval_id=estado["approval_id"])

    with pytest.raises(ValueError, match="límite de turnos"):
        procesar_turno(
            estado,
            "¿Dónde tiro una lata?",
            hilo,
        )


# =========================================================
# CONSULTAS DE PUNTOS LIMPIOS
# =========================================================


def test_punto_de_proximidad_documental(aislado):
    """La modalidad 'proximidad' no exige geolocalización."""
    herramienta = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramienta,
    )

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿Qué es un punto limpio de proximidad?",
        hilo,
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True
    assert estado["estado_evidencia"] == "suficiente"
    assert "puntos limpios" in estado["respuesta"].lower()
    assert "latitud" not in estado["respuesta"].lower()

    herramienta.assert_called_once()
    assert herramienta.call_args.args[0] == "consultar_rag"
    assert herramienta.call_args.kwargs["rol"] == "puntos"


def test_punto_cercano_sin_coordenadas(aislado):
    """Solicita coordenadas sin llamar a ninguna herramienta."""
    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "Busca un punto limpio de proximidad cerca de mí",
        hilo,
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True
    assert estado["estado_evidencia"] == "insuficiente"
    assert "latitud" in estado["respuesta"].lower()
    assert "longitud" in estado["respuesta"].lower()
    assert estado["tool_calls_turno"] == 0
    assert estado["evidencias"] == []


def test_punto_cercano_con_coordenadas(aislado):
    """Ejecuta una consulta geográfica con coordenadas aportadas."""
    herramienta = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramienta,
    )

    estado, hilo = _crear_conversacion()

    ubicacion = {
        "latitud": 40.4168,
        "longitud": -3.7038,
    }

    estado = procesar_turno(
        estado,
        "Busca un punto limpio de proximidad cerca de mí",
        hilo,
        ubicacion=ubicacion,
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True
    assert estado["estado_evidencia"] == "suficiente"
    assert "Calle de Prueba, 1" in estado["respuesta"]

    assert herramienta.call_count == 2
    assert herramienta.call_args_list[0].args[0] == (
        "buscar_puntos_limpios_cercanos"
    )
    assert herramienta.call_args_list[1].args[0] == "hora_actual"
    assert "hora_actual" in [e["herramienta"] for e in estado["evidencias"]]
    argumentos = herramienta.call_args_list[0].args[1]

    assert argumentos["latitud"] == 40.4168
    assert argumentos["longitud"] == -3.7038
    assert argumentos["tipo"] == "proximidad"

    resultado = validar_resultado_agente(
        estado,
        thread_id=UUID(hilo),
        turnos_esperados=1,
        aprobado_esperado=None,
    )

    assert len(resultado.geografia) == 1

    geografia = resultado.geografia[0]

    assert geografia.fuente == "api"
    assert geografia.total_encontrados == 1
    assert geografia.tipo_solicitado == "proximidad"

    punto = geografia.puntos[0]

    assert punto.direccion == "Calle de Prueba, 1"
    assert punto.latitud == 40.4199
    assert punto.longitud == -3.7038
    assert punto.distancia_metros == 350.0

    datos = resultado.model_dump(mode="json")

    assert "evidencias" not in datos
    assert "ubicacion" not in datos
    assert "puntos_candidatos" not in datos["geografia"][0]
    assert "id" not in datos["geografia"][0]["puntos"][0]


# =========================================================
# ABSTENCIÓN Y ERRORES
# =========================================================


def test_abstencion_rag_sin_generacion_adicional(aislado):
    """Una abstención del RAG no se convierte en una afirmación."""
    def rag_sin_evidencia(nombre, args, *, rol):
        assert nombre == "consultar_rag"

        return {
            "ok": True,
            "nombre": nombre,
            "datos": _resultado_rag(abstencion=True),
            "error": None,
        }

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        rag_sin_evidencia,
    )

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿Dónde tiro esto?",
        hilo,
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True
    assert estado["abstencion"] is True
    assert estado["estado_evidencia"] == "insuficiente"
    assert estado["fuentes"] == []
    assert "No hay evidencia" in estado["respuesta"]

    resultado = validar_resultado_agente(
        estado,
        thread_id=UUID(hilo),
        turnos_esperados=1,
        aprobado_esperado=None,
    )

    assert resultado.error is None
    assert resultado.abstencion is True
    assert resultado.estado_evidencia == "insuficiente"
    assert resultado.pendiente_hitl is True
    assert resultado.fuentes == []
    assert resultado.geografia == []


def test_fallo_tecnico_no_inventa_resultado(aislado):
    """Un fallo externo no produce una clasificación inventada."""
    def herramienta_fallida(nombre, args, *, rol):
        return {
            "ok": False,
            "nombre": nombre,
            "datos": None,
            "error": "Error: servicio no disponible.",
        }

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramienta_fallida,
    )

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿Dónde tiro una botella?",
        hilo,
    )

    assert estado["error"] is not None
    assert estado["pendiente_hitl"] is False
    assert estado["plan"] == []
    assert estado["done"] is False

    with pytest.raises(ApiError) as error:
        validar_resultado_agente(
            estado,
            thread_id=UUID(hilo),
            turnos_esperados=1,
            aprobado_esperado=None,
        )

    assert error.value.code == ErrorCode.INTERNAL_SERVER_ERROR


# =========================================================
# CONSULTA COMPUESTA
# =========================================================


def test_consulta_compuesta_con_dos_especialistas(aislado):
    """Ejecuta ambos especialistas en secuencia y conserva pruebas."""
    herramientas = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramientas,
    )

    modelos = [
        ModeloFalso([
            _llamada(
                "consultar_rag",
                {"pregunta": "¿Dónde tiro una batería?"},
                "residuo-1",
            ),
        ]),
        ModeloFalso([
            _llamada(
                "buscar_puntos_limpios_cercanos",
                {"tipo": "todos"},
                "puntos-1",
            ),
        ]),
    ]

    creador = Mock(side_effect=modelos)

    aislado.setattr(
        "src.agent_tool_loop.get_llm",
        creador,
    )

    sintesis = Mock(return_value={
        "respuesta": (
            "Clasificación documentada [C1] y punto encontrado."
        ),
        "plan": [
            "Consultar las fuentes.",
            "Comprobar los datos del punto limpio.",
        ],
    })

    aislado.setattr("src.nodes._generar_json", sintesis)

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿Dónde tiro una batería y qué punto limpio tengo cerca?",
        hilo,
        ubicacion={
            "latitud": 40.4168,
            "longitud": -3.7038,
        },
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True
    assert estado["necesita_residuos"] is True
    assert estado["necesita_puntos"] is True
    assert estado["residuos_completado"] is True
    assert estado["puntos_completado"] is True

    nombres_ejecutados = [
        llamada.args[0]
        for llamada in herramientas.call_args_list
    ]

    assert nombres_ejecutados == [
        "consultar_rag",
        "buscar_puntos_limpios_cercanos",
        "hora_actual",
    ]

    assert creador.call_count == 0  # Ruta determinista, sin LLM de selección.
    sintesis.assert_not_called()
    assert "No se ha verificado" in estado["respuesta"]
    assert len(estado["evidencias"]) == 3
    assert estado["tool_calls_turno"] == 3
    assert estado["fuentes"]


# =========================================================
# MULTIMODALIDAD
# =========================================================


def test_identificacion_y_agente_sin_duplicar_gemini(
    aislado,
    tmp_path,
):
    """Integra la identificación real con el grafo sin repetirla."""
    assets = tmp_path / "assets"
    assets.mkdir()

    aislado.setattr("api.images.ASSETS_DIR", assets)
    aislado.setattr("src.tools.describir_imagen.ASSETS_DIR", assets)

    descripcion = "Una botella de plástico transparente."

    cliente = Mock()
    cliente.models.generate_content.return_value.text = json.dumps({
        "estado": "allowed",
        "descripcion": descripcion,
    })

    crear_cliente = Mock(return_value=cliente)

    aislado.setattr(
        "src.tools.describir_imagen.crear_cliente_gemini",
        crear_cliente,
    )

    with BytesIO() as salida:
        with Image.new("RGB", (20, 20)) as imagen:
            imagen.save(salida, format="PNG")

        datos = salida.getvalue()

    identificacion = identificar_entrada_visual(datos, "PNG")

    assert identificacion == {"estado": "allowed", "descripcion": descripcion}

    directorio = assets / ".api_temporal"

    assert directorio.is_dir()
    assert not list(directorio.iterdir())

    estado, hilo = _crear_conversacion()

    resultado = procesar_turno(
        estado,
        "Describe esta imagen.",
        hilo,
        identificacion_imagen=identificacion,
    )

    assert resultado["error"] is None
    assert resultado["respuesta"] == descripcion
    assert resultado["pendiente_hitl"] is True
    assert resultado["estado_evidencia"] == "suficiente"
    assert resultado["tool_calls_turno"] == 0
    assert resultado["turnos_consumidos"] == 1
    assert resultado["ruta_imagen"] is None

    crear_cliente.assert_called_once()
    cliente.models.generate_content.assert_called_once()
    cliente.close.assert_called_once()

    assert not list(directorio.iterdir())

def test_imagen_y_rag_en_el_mismo_especialista(aislado):
    """Describe una imagen antes de solicitar su clasificación RAG."""
    herramientas = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramientas,
    )

    modelo = ModeloFalso([
        _llamada("describir_imagen", {}, "imagen-1"),
        _llamada(
            "consultar_rag",
            {"pregunta": "Botella de plástico transparente"},
            "rag-1",
        ),
    ])

    aislado.setattr("src.agent_tool_loop.get_llm", Mock(return_value=modelo))

    aislado.setattr(
        "src.nodes._generar_json",
        Mock(return_value={
            "respuesta": "Según el RAG, envase amarillo. [C1]",
            "plan": [
                "Comprobar el material.",
                "Seguir el destino documentado.",
            ],
        }),
    )

    estado, hilo = _crear_conversacion()

    estado = procesar_turno(
        estado,
        "¿En qué contenedor va lo que aparece en esta foto?",
        hilo,
        ruta_imagen="assets/imagen_demo.jpg",
    )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True

    herramientas_ejecutadas = [
        evidencia["herramienta"]
        for evidencia in estado["evidencias"]
    ]

    assert herramientas_ejecutadas == [
        "describir_imagen",
        "consultar_rag",
    ]

    assert len(estado["fuentes"]) == 1
    assert estado["tool_calls_turno"] == 2

    assert modelo.herramientas == [
        "consultar_rag",
        "describir_imagen",
        "hora_actual",
    ]


def test_descripcion_visual_previa_sin_llamadas_adicionales(aislado):
    """Utiliza la identificación previa y alcanza HITL."""
    estado, hilo = _crear_conversacion()

    descripcion = "Una botella de plástico transparente."

    resultado = procesar_turno(
        estado,
        "Describe esta imagen.",
        hilo,
        identificacion_imagen={"estado": "allowed", "descripcion": descripcion},
    )

    assert resultado["error"] is None
    assert resultado["respuesta"] == descripcion
    assert resultado["estado_evidencia"] == "suficiente"
    assert resultado["pendiente_hitl"] is True
    assert resultado["done"] is False
    assert resultado["turnos_consumidos"] == 1
    assert resultado["tool_calls_turno"] == 0
    assert resultado["ruta_imagen"] is None

    assert resultado["evidencias"] == [{
        "rol": "residuos",
        "herramienta": "describir_imagen",
        "datos": descripcion,
        "origen": "identificacion_previa",
    }]


def test_clasificacion_visual_reutiliza_identificacion(aislado):
    """Reutiliza la descripción y ejecuta únicamente el RAG."""
    herramientas = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramientas,
    )

    modelo = ModeloFalso([
        _llamada("describir_imagen", {}, "imagen-1"),
        _llamada(
            "consultar_rag",
            {"pregunta": "Botella de plástico transparente"},
            "rag-1",
        ),
    ])

    aislado.setattr("src.agent_tool_loop.get_llm", Mock(return_value=modelo))

    aislado.setattr(
        "src.nodes._generar_json",
        Mock(return_value={
            "respuesta": "Según el RAG, envase amarillo. [C1]",
            "plan": [
                "Comprobar el material.",
                "Seguir el destino documentado.",
            ],
        }),
    )

    estado, hilo = _crear_conversacion()

    resultado = procesar_turno(
        estado,
        "¿En qué contenedor va lo que aparece en esta foto?",
        hilo,
        identificacion_imagen={
            "estado": "allowed",
            "descripcion": "Una botella de plástico transparente.",
        },
    )

    assert resultado["error"] is None
    assert resultado["pendiente_hitl"] is True
    assert resultado["tool_calls_turno"] == 1
    assert resultado["estado_evidencia"] == "suficiente"
    assert resultado["ruta_imagen"] is None

    herramientas.assert_called_once()

    assert herramientas.call_args.args[0] == "consultar_rag"

    assert len(resultado["evidencias"]) == 2

    visual = resultado["evidencias"][0]

    assert visual["herramienta"] == "describir_imagen"
    assert visual["origen"] == "identificacion_previa"
    assert "id_llamada" not in visual

    assert [
        traza["status"]
        for traza in resultado["traza_tools"]
    ] == ["cache", "ok"]

    respuesta = validar_resultado_agente(
        resultado,
        thread_id=UUID(hilo),
        turnos_esperados=1,
        aprobado_esperado=None,
    )

    datos = respuesta.model_dump(mode="json")

    assert respuesta.pendiente_hitl is True
    assert respuesta.estado_evidencia == "suficiente"
    assert respuesta.fuentes

    assert "ruta_imagen" not in datos
    assert "identificacion_imagen" not in datos
    assert "evidencias" not in datos
    assert "traza_tools" not in datos


# =========================================================
# PRESUPUESTOS Y DEDUPLICACIÓN
# =========================================================


def test_presupuesto_de_tools_aplicado_en_modo_directo(aislado):
    """Un presupuesto agotado bloquea rutas deterministas."""
    estado = crear_estado_grafo(
        "¿Dónde tiro una botella?"
    )

    estado["tool_calls_turno"] = MAX_TOOL_CALLS_PER_TURN

    resultado = ejecutar_especialista(
        estado,
        rol="residuos",
    )

    assert (
        resultado["tool_calls_turno"]
        == MAX_TOOL_CALLS_PER_TURN
    )
    assert resultado["evidencias"] == []
    assert resultado["traza_tools"][-1]["status"] == "error"
    assert "presupuesto" in resultado["limitaciones"][-1]


def test_deduplicacion_de_herramientas(aislado):
    """Dos llamadas idénticas ejecutan realmente la tool una vez."""
    herramienta = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramienta,
    )

    mensaje = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "consultar_rag",
                "args": {"pregunta": "botella de plástico"},
                "id": "primera",
            },
            {
                "name": "consultar_rag",
                "args": {"pregunta": "botella de plástico"},
                "id": "segunda",
            },
        ],
    )

    modelo = ModeloFalso([mensaje])

    aislado.setattr(
        "src.agent_tool_loop.get_llm",
        Mock(return_value=modelo),
    )

    estado = crear_estado_grafo(
        "¿Dónde tiro una botella?"
    )

    estado["contexto_revision"] = "Plan rechazado previamente."

    resultado = ejecutar_especialista(
        estado,
        rol="residuos",
    )

    herramienta.assert_called_once()
    assert resultado["tool_calls_turno"] == 1
    assert len(resultado["evidencias"]) == 1

    estados_traza = [
        traza["status"]
        for traza in resultado["traza_tools"]
    ]

    assert estados_traza == ["ok", "cache"]


def test_limite_de_rondas_del_especialista(aislado):
    """El bucle agente no rebasa max_steps."""
    herramienta = Mock(side_effect=_ejecutor_simulado)

    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        herramienta,
    )

    modelo = ModeloFalso([
        _llamada(
            "describir_imagen",
            {},
            "imagen-unica",
        ),
    ])

    aislado.setattr(
        "src.agent_tool_loop.get_llm",
        Mock(return_value=modelo),
    )

    estado = crear_estado_grafo(
        "¿En qué contenedor va lo que aparece en esta foto?",
        max_steps=1,
        ruta_imagen="assets/imagen_demo.jpg",
    )

    resultado = ejecutar_especialista(
        estado,
        rol="residuos",
    )

    assert resultado["tool_calls_turno"] == 1
    assert resultado["evidencias"][0]["herramienta"] == (
        "describir_imagen"
    )
    assert "Límite de rondas" in resultado["limitaciones"][-1]

    herramienta.assert_called_once()


def test_allowlist_rol_residuos():
    """El especialista de residuos no puede utilizar la API de puntos."""
    resultado = ejecutar_tool_estructurado(
        "buscar_puntos_limpios_cercanos",
        {
            "latitud": 40.4168,
            "longitud": -3.7038,
        },
        rol="residuos",
    )

    assert resultado["ok"] is False
    assert "no permitida" in resultado["error"]


# =========================================================
# SUPERVISOR Y LÍMITES DEL GRAFO
# =========================================================


def test_supervisor_ambiguo_consulta_modelo_una_vez(aislado):
    """Una intención desconocida admite una propuesta del modelo."""
    estado = crear_estado_grafo(
        "¿Dónde llevo mis pilas?"
    )

    assert requiere_llm_supervisor(estado) is True

    propuesta = Mock(return_value={
        "necesita_residuos": True,
        "necesita_puntos": False,
        "siguiente": "residuos",
    })

    aislado.setattr(
        "src.nodes._generar_json",
        propuesta,
    )

    resultado = supervisor(estado)

    assert resultado["siguiente"] == "residuos"
    assert resultado["necesita_residuos"] is True

    propuesta.assert_called_once()


def test_max_iter_bloquea_nuevas_decisiones():
    """El supervisor respeta MAX_ITER configurado en Python."""
    estado = crear_estado_grafo(
        "¿Dónde tiro una botella?"
    )

    estado["iteracion"] = MAX_ITER

    with pytest.raises(RuntimeError, match="MAX_ITER"):
        resolver_enrutamiento(estado)


# =========================================================
# LECTURA DEL CHECKPOINT
# =========================================================

def test_obtener_estado_hilo_inexistente(aislado):
    """Un hilo sin checkpoint no genera un estado artificial."""
    assert obtener_estado_hilo(nuevo_thread_id()) is None


@pytest.mark.parametrize("aprobado", [True, False])
def test_obtener_estado_hilo_resuelto(aislado, aprobado):
    """Recupera el estado pendiente y la decisión posterior."""
    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        _ejecutor_simulado,
    )

    estado, hilo = _crear_conversacion()

    resultado = procesar_turno(
        estado,
        "¿Dónde tiro una botella de plástico?",
        hilo,
    )

    pendiente = obtener_estado_hilo(hilo)

    assert pendiente == resultado
    assert pendiente["pendiente_hitl"] is True

    resuelto = aprobar_plan(
        hilo,
        aprobado,
        approval_id=pendiente["approval_id"],
    )

    assert obtener_estado_hilo(hilo) == resuelto


def test_obtener_estado_hilo_copia_independiente(aislado):
    """Modificar el estado devuelto no altera el checkpoint."""
    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        _ejecutor_simulado,
    )

    estado, hilo = _crear_conversacion()

    resultado = procesar_turno(
        estado,
        "¿Dónde tiro una botella de plástico?",
        hilo,
    )

    recuperado = obtener_estado_hilo(hilo)
    recuperado["plan"].clear()
    recuperado["fuentes"].clear()

    assert obtener_estado_hilo(hilo) == resultado


@pytest.mark.parametrize(
    "caso, mensaje",
    [
        ("vacio", "Checkpoint incompleto"),
        ("incompleto", "Checkpoint incompleto"),
        ("invalido", "Checkpoint inválido"),
        ("interrumpido", "ejecución anterior está incompleta"),
        ("hitl_invalido", "Propuesta HITL inválida"),
        ("inconsistente", "Checkpoint inconsistente"),
    ],
)
def test_obtener_estado_hilo_invalido(aislado, caso, mensaje):
    """Rechaza checkpoints incompletos o inconsistentes."""
    datos = crear_estado_grafo()
    siguientes = ()

    if caso == "vacio":
        datos = {}

    elif caso == "incompleto":
        del datos["turnos_consumidos"]

    elif caso == "invalido":
        datos = None

    elif caso == "interrumpido":
        siguientes = ("supervisor",)

    elif caso == "hitl_invalido":
        siguientes = ("aplicar",)

    elif caso == "inconsistente":
        datos["pendiente_hitl"] = True

    app = Mock()
    app.get_state.return_value = Mock(
        values=datos,
        next=siguientes,
        created_at="2026-11-27T10:00:00+00:00",
    )

    aislado.setattr("src.agent.get_app", lambda: app)

    with pytest.raises(RuntimeError, match=mensaje):
        obtener_estado_hilo(nuevo_thread_id())

    app.get_state.assert_called_once()
    app.invoke.assert_not_called()
    app.update_state.assert_not_called()

# =========================================================
# INTEGRACIÓN DE AUTORIZACIÓN Y ESTADO OPERATIVO
# =========================================================

@pytest.fixture
def hilo_persistido(
    clean_db: Engine,
) -> tuple[UUID, AuthContext, AuthContext]:
    """Prepara una conversación y dos credenciales independientes."""
    thread_id = uuid4()

    with Session(clean_db) as session:
        propietaria = ApiKey(
            key_hash=hash_secret(generate_secret()),
            role=ApiKeyRole.FREE,
        )

        ajena = ApiKey(
            key_hash=hash_secret(generate_secret()),
            role=ApiKeyRole.FREE,
        )

        db.create_api_key(session, propietaria)
        db.create_api_key(session, ajena)
        session.flush()

        contexto = AuthContext(
            user_id=None,
            api_key_id=propietaria.id,
            role=ApiKeyRole.FREE,
        )

        contexto_ajeno = AuthContext(
            user_id=None,
            api_key_id=ajena.id,
            role=ApiKeyRole.FREE,
        )

        db.create_conversation(
            session,
            thread_id,
            propietaria.id,
        )

        session.commit()

    return thread_id, contexto, contexto_ajeno

@pytest.mark.integration
def test_integracion_estado_operativo_continuidad(
    aislado: pytest.MonkeyPatch,
    clean_db: Engine,
    hilo_persistido: tuple[UUID, AuthContext, AuthContext],
) -> None:
    """Integra propiedad, exclusión, continuidad y resolución HITL."""
    aislado.setattr(
        "src.agent_tool_loop.ejecutar_tool_estructurado",
        _ejecutor_simulado,
    )

    thread_id, contexto, contexto_ajeno = hilo_persistido
    hilo = str(thread_id)
    admision = ControlAdmision(max_workers=1)

    estado = crear_estado_producto(
        thread_id=hilo,
        max_turns=2,
    )

    with admision.reservar_hilo(thread_id):
        estado = procesar_turno(
            estado,
            "¿Dónde tiro una botella de plástico?",
            hilo,
        )

    assert estado["error"] is None
    assert estado["pendiente_hitl"] is True

    primera_aprobacion = estado["approval_id"]
    assert primera_aprobacion is not None

    with ExitStack() as recursos:
        recuperado = reservar_hilo_autorizado(
            clean_db,
            contexto,
            thread_id,
            admision,
            recursos,
        )

        assert recuperado == estado

        # No revela la ocupación a una credencial ajena.
        with pytest.raises(ApiError) as error:
            with ExitStack() as otros_recursos:
                reservar_hilo_autorizado(
                    clean_db,
                    contexto_ajeno,
                    thread_id,
                    admision,
                    otros_recursos,
                )

        assert error.value.code == ErrorCode.THREAD_NOT_FOUND

        # Impide operaciones concurrentes del propietario.
        with pytest.raises(ApiError) as error:
            with ExitStack() as otros_recursos:
                reservar_hilo_autorizado(
                    clean_db,
                    contexto,
                    thread_id,
                    admision,
                    otros_recursos,
                )

        assert error.value.code == ErrorCode.THREAD_BUSY

        with pytest.raises(ApiError) as error:
            validar_nuevo_turno(recuperado)

        assert error.value.code == ErrorCode.PENDING_APPROVAL

        validar_decision_hitl(
            recuperado,
            primera_aprobacion,
        )

        estado = aprobar_plan(
            hilo,
            False,
            approval_id=primera_aprobacion,
        )

        assert estado["error"] is None
        assert estado["turnos_consumidos"] == 1

    with ExitStack() as recursos:
        recuperado = reservar_hilo_autorizado(
            clean_db,
            contexto,
            thread_id,
            admision,
            recursos,
        )

        validar_nuevo_turno(recuperado)

        estado = procesar_turno(
            recuperado,
            "¿Dónde tiro una lata de refresco?",
            hilo,
        )

        assert estado["error"] is None
        assert estado["turnos_consumidos"] == 2

    with ExitStack() as recursos:
        recuperado = reservar_hilo_autorizado(
            clean_db,
            contexto,
            thread_id,
            admision,
            recursos,
        )

        segunda_aprobacion = recuperado["approval_id"]

        assert segunda_aprobacion is not None
        assert segunda_aprobacion != primera_aprobacion

        with pytest.raises(ApiError) as error:
            validar_decision_hitl(
                recuperado,
                primera_aprobacion,
            )

        assert error.value.code == ErrorCode.STALE_APPROVAL

        validar_decision_hitl(
            recuperado,
            segunda_aprobacion,
        )

        estado = aprobar_plan(
            hilo,
            True,
            approval_id=segunda_aprobacion,
        )

        resultado = validar_resultado_agente(
            estado,
            thread_id=thread_id,
            turnos_esperados=2,
            aprobado_esperado=True,
        )

        assert resultado.done is True
        assert resultado.pendiente_hitl is False

    with ExitStack() as recursos:
        recuperado = reservar_hilo_autorizado(
            clean_db,
            contexto,
            thread_id,
            admision,
            recursos,
        )

        with pytest.raises(ApiError) as error:
            validar_nuevo_turno(recuperado)

        assert error.value.code == ErrorCode.THREAD_CLOSED

        with pytest.raises(ApiError) as error:
            validar_decision_hitl(
                recuperado,
                segunda_aprobacion,
            )

        assert error.value.code == ErrorCode.NO_PENDING_APPROVAL

@pytest.mark.integration
def test_integracion_estado_operativo_perdido(
    aislado: pytest.MonkeyPatch,
    clean_db: Engine,
    hilo_persistido: tuple[UUID, AuthContext, AuthContext],
) -> None:
    """Impide reconstruir una conversación sin checkpoint."""
    thread_id, contexto, _ = hilo_persistido
    admision = ControlAdmision(max_workers=1)

    assert obtener_estado_hilo(str(thread_id)) is None

    with pytest.raises(ApiError) as error:
        with ExitStack() as recursos:
            reservar_hilo_autorizado(
                clean_db,
                contexto,
                thread_id,
                admision,
                recursos,
            )

    assert error.value.code == ErrorCode.THREAD_STATE_LOST

    with pytest.raises(ApiError) as error:
        with admision.reservar_hilo(thread_id):
            pytest.fail("No debe reutilizarse un hilo invalidado.")

    assert error.value.code == ErrorCode.THREAD_STATE_LOST

    with Session(clean_db) as session:
        conversation = db.get_conversation_by_id(
            session,
            thread_id,
        )

        assert conversation is not None
        assert conversation.api_key_id == contexto.api_key_id

    assert obtener_estado_hilo(str(thread_id)) is None