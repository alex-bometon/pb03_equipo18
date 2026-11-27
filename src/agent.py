"""Orquestador público del sistema multiagente ReciclaTIA.

Centraliza la ejecución de turnos y la decisión humana sobre el plan.

CLI y Streamlit deben utilizar estas funciones, sin invocar
directamente los nodos ni manipular checkpoints por su cuenta.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from src.graph import (
    config_hilo,
    get_app,
    hay_hitl_pendiente,
)
from src.input_validation import validar_pregunta
from src.state import (
    EstadoGrafo,
    EstadoProducto,
    IdentificacionImagen,
    Ubicacion,
    crear_estado_producto,
    estado_desde_grafo,
    preparar_nuevo_turno,
    registrar_turno,
    validar_identificacion_imagen
)


# =========================================================
# IDENTIFICADOR DE CONVERSACIÓN
# =========================================================

def nuevo_thread_id() -> str:
    """Genera un identificador único para una conversación."""

    return str(uuid4())


# =========================================================
# VALIDACIÓN DEL HILO
# =========================================================

def _validar_hilo(
    estado: EstadoProducto,
    thread_id: str,
) -> dict[str, Any]:
    """Valida la asociación entre el estado y la conversación."""

    configuracion = config_hilo(thread_id)

    if not isinstance(estado, dict):
        raise ValueError("Estado de conversación inválido.")

    identificador = estado.get("thread_id", "")

    if identificador and identificador != thread_id:
        raise ValueError(
            "El estado pertenece a otra conversación."
        )

    return configuracion


# =========================================================
# LECTURA DEL CHECKPOINT
# =========================================================

def _valores_checkpoint(snapshot: Any) -> Mapping[str, Any]:
    """Extrae los valores guardados sin asumir que existe un hilo."""

    if snapshot is None:
        return {}

    valores = getattr(snapshot, "values", None)

    return valores if isinstance(valores, Mapping) else {}


def _estado_actual(
    thread_id: str,
    base: EstadoProducto | None = None,
) -> EstadoProducto:
    """Construye el estado público desde el checkpoint real."""

    app = get_app()
    snapshot = app.get_state(config_hilo(thread_id))

    return estado_desde_grafo(
        _valores_checkpoint(snapshot),
        base,
        thread_id=thread_id,
        pendiente_hitl=hay_hitl_pendiente(thread_id),
    )


def _propuesta_valida(datos: Mapping[str, Any]) -> bool:
    """Comprueba que el checkpoint contiene una propuesta válida."""
    if EstadoGrafo.__annotations__.keys() - datos.keys():
        return False

    respuesta = datos["respuesta"]
    plan = datos["plan"]
    approval_id = datos["approval_id"]

    if (
        not isinstance(respuesta, str)
        or not respuesta.strip()
        or not isinstance(plan, list)
        or len(plan) < 2
        or any(
            not isinstance(paso, str) or not paso.strip()
            for paso in plan
        )
        or not isinstance(approval_id, str)
        or datos["plan_aprobado"] is not None
        or datos["pendiente_hitl"] is not True
        or datos["done"] is not False
        or datos["error"] is not None
    ):
        return False

    try:
        UUID(approval_id)
    except ValueError:
        return False

    return True

# =========================================================
# PROCESAMIENTO DE TURNOS
# =========================================================

def procesar_turno(
    estado: EstadoProducto,
    mensaje: str,
    thread_id: str,
    *,
    max_steps: int | None = None,
    ubicacion: Ubicacion | None = None,
    ruta_imagen: str | None = None,
    identificacion_imagen: IdentificacionImagen | None = None,
) -> EstadoProducto:
    """Ejecuta una consulta hasta el HITL o un fallo técnico.

    Los turnos se contabilizan por mensajes válidos del usuario.
    No se permite iniciar otro turno mientras hay una pausa.
    """

    configuracion = _validar_hilo(estado, thread_id)

    # Reutilizamos la validación existente del RAG.
    # Una entrada vacía o inválida no ejecuta el grafo.
    mensaje = validar_pregunta(mensaje)

    if ruta_imagen is not None and identificacion_imagen is not None:
        raise ValueError(
            "No se puede proporcionar una ruta y una identificación."
        )

    if identificacion_imagen is not None:
        identificacion_imagen = validar_identificacion_imagen(
            identificacion_imagen
        )

        if identificacion_imagen["estado"] != "allowed":
            raise ValueError("Identificación visual inválida.")

    app = get_app()
    snapshot = app.get_state(configuracion)

    # -----------------------------------------------------
    # COMPROBAR EL ESTADO PERSISTIDO DEL HILO
    # -----------------------------------------------------

    if snapshot is not None:
        if tuple(snapshot.next) == ("aplicar",):
            raise ValueError("Hay un plan pendiente de aprobación o rechazo.")

        if snapshot.next:
            raise RuntimeError("La ejecución anterior está incompleta.")

    datos = _valores_checkpoint(snapshot)

    if datos and EstadoGrafo.__annotations__.keys() - datos.keys():
        raise RuntimeError("Checkpoint incompleto.")

    if not datos and estado["turnos_consumidos"] > 0:
        raise RuntimeError("No se encuentra el checkpoint del hilo.")

    estado_base = estado_desde_grafo(
        datos,
        None if datos else estado,
        thread_id=thread_id,
    )

    if estado_base["done"]:
        raise ValueError(
            "La conversación ha finalizado. "
            "Inicia una nueva para realizar otra consulta."
        )

    # -----------------------------------------------------
    # PREPARAR UN TURNO INDEPENDIENTE
    # -----------------------------------------------------

    nuevo_estado = preparar_nuevo_turno(
        estado_base,
        mensaje,
        max_steps=max_steps,
        ubicacion=ubicacion,
        ruta_imagen=ruta_imagen,
        identificacion_imagen=identificacion_imagen,
    )

    # -----------------------------------------------------
    # EJECUTAR LANGGRAPH
    # -----------------------------------------------------

    try:
        app.invoke(nuevo_estado, config=configuracion)

    except Exception:
        resultado = _estado_actual(thread_id, nuevo_estado)

        resultado["error"] = (
            "Error técnico durante la ejecución del agente. "
            "No se ha completado el turno. "
            "Revisa la traza o inicia una nueva conversación."
        )
        resultado["plan"] = []
        resultado["approval_id"] = None
        resultado["pendiente_hitl"] = False
        resultado["done"] = False

        snapshot = app.get_state(configuracion)

        if snapshot is not None and tuple(snapshot.next) == ("aplicar",):
            app.update_state(
                configuracion,
                {
                    "error": resultado["error"],
                    "approval_id": None,
                },
                as_node="supervisor",
            )

        return resultado

    # -----------------------------------------------------
    # CONFIRMAR LA PAUSA REAL
    # -----------------------------------------------------

    snapshot = app.get_state(configuracion)
    datos = _valores_checkpoint(snapshot)
    resultado = estado_desde_grafo(datos, thread_id=thread_id)

    if (
        snapshot is None
        or tuple(snapshot.next) != ("aplicar",)
        or not _propuesta_valida(datos)
    ):
        resultado["error"] = "El grafo no ha alcanzado una interrupción HITL válida."
        resultado["plan"] = []
        resultado["approval_id"] = None
        resultado["pendiente_hitl"] = False
        resultado["done"] = False

    return resultado


# =========================================================
# APROBACIÓN O RECHAZO HUMANO
# =========================================================

def aprobar_plan(
    thread_id: str,
    aprobado: bool,
    *,
    approval_id: str,
) -> EstadoProducto:
    """Registra la decisión humana y reanuda el checkpoint real."""
    configuracion = config_hilo(thread_id)

    if type(aprobado) is not bool:
        raise ValueError("La decisión debe ser True o False.")

    if not isinstance(approval_id, str):
        raise ValueError("Identificador de aprobación inválido.")

    try:
        UUID(approval_id)
    except ValueError as exc:
        raise ValueError("Identificador de aprobación inválido.") from exc

    app = get_app()
    snapshot = app.get_state(configuracion)
    datos = _valores_checkpoint(snapshot)

    if snapshot is None or tuple(snapshot.next) != ("aplicar",):
        raise ValueError("No existe un plan pendiente de decisión humana.")

    if not _propuesta_valida(datos):
        raise RuntimeError("El checkpoint no contiene una propuesta válida.")

    if datos["approval_id"] != approval_id:
        raise ValueError("La aprobación no corresponde a la propuesta pendiente.")

    estado = estado_desde_grafo(datos, thread_id=thread_id)
    historial_esperado = registrar_turno(estado, aprobado=aprobado)

    try:
        app.update_state(configuracion, {"plan_aprobado": aprobado})
        app.invoke(None, config=configuracion)

    except Exception as exc:
        raise RuntimeError("No se pudo reanudar LangGraph tras la decisión humana.") from exc

    snapshot_final = app.get_state(configuracion)
    datos_finales = _valores_checkpoint(snapshot_final)

    if EstadoGrafo.__annotations__.keys() - datos_finales.keys():
        raise RuntimeError("Checkpoint final incompleto.")

    resultado = estado_desde_grafo(datos_finales, thread_id=thread_id)

    if (
        snapshot_final is None
        or snapshot_final.next
        or resultado["pendiente_hitl"] is not False
        or resultado["approval_id"] is not None
        or resultado["plan_aprobado"] is not aprobado
        or resultado["done"] is not aprobado
        or resultado["error"] is not None
        or resultado["turnos_consumidos"] != estado["turnos_consumidos"]
        or resultado["historial_turnos"] != historial_esperado
    ):
        resultado["error"] = "No se pudo confirmar la aplicación de la decisión humana."

    return resultado

# =========================================================
# DEMOSTRACIÓN
# =========================================================

def run_demo(
    mensaje: str = "¿Dónde tiro una botella de plástico?",
    *,
    auto_aprobar: bool = True,
    ubicacion: Ubicacion | None = None,
    ruta_imagen: str | None = None,
) -> EstadoProducto:
    """Ejecuta una demostración usando la API pública del agente.

    Con auto_aprobar=False devuelve el plan pendiente de HITL.
    Con auto_aprobar=True registra una aprobación explícita
    solicitada por el modo demo.
    """

    if type(auto_aprobar) is not bool:
        raise ValueError("auto_aprobar debe ser True o False.")

    thread_id = nuevo_thread_id()

    estado = crear_estado_producto(thread_id=thread_id)

    resultado = procesar_turno(
        estado,
        mensaje,
        thread_id,
        ubicacion=ubicacion,
        ruta_imagen=ruta_imagen,
    )

    approval_id = resultado["approval_id"]

    if (
        auto_aprobar
        and resultado["pendiente_hitl"]
        and resultado["error"] is None
        and approval_id is not None
    ):
        resultado = aprobar_plan(
            thread_id=thread_id,
            aprobado=True,
            approval_id=approval_id,
        )

    return resultado
