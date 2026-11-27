"""Coordina la admisión y ejecución del asistente desde la API."""

from api.schemas import AskOut, UbicacionIn
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.images import imagen_temporal
from src.state import IdentificacionImagen
from src.tools.describir_imagen import identificar_imagen
from src.domain import es_consulta_programacion, evaluar_ambito
from src.generation_validation import MENSAJE_ABSTENCION
from src.rag_intents import (
    MENSAJE_ACLARACION_CONTEXTO,
    MENSAJE_ACLARACION_HORARIO_MOVIL,
    MENSAJE_ACLARACION_PROXIMIDAD,
    consulta_proximidad,
    es_consulta_reparacion_telefonos,
    es_horario_movil_sin_ubicacion,
    requiere_antecedente,
)
from src.text_utils import normalizar_texto


def _respuesta_previa(
    respuesta: str,
    motivo: str,
    *,
    thread_id: str | None,
    turnos_consumidos: int,
) -> AskOut:
    """Construye una respuesta anterior a la ejecución del agente."""
    return AskOut(
        thread_id=thread_id,
        respuesta=respuesta,
        plan=[],
        plan_aprobado=None,
        done=False,
        pendiente_hitl=False,
        fuentes=[],
        geografia=[],
        abstencion=True,
        motivo=motivo,
        estado_evidencia="insuficiente",
        limitaciones=[],
        turnos_consumidos=turnos_consumidos,
        error=None,
        approval_id=None,
    )


def filtrar_entrada(
    pregunta: str,
    *,
    contexto_revision: str = "",
    ubicacion: UbicacionIn | None = None,
    hay_imagen: bool = False,
    thread_id: str | None = None,
    turnos_consumidos: int = 0,
) -> AskOut | None:
    """Resuelve consultas inequívocas antes de ejecutar el agente."""
    normalizada = normalizar_texto(pregunta)

    if requiere_antecedente(normalizada):
        if contexto_revision or hay_imagen:
            return None

        return _respuesta_previa(
            MENSAJE_ACLARACION_CONTEXTO,
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if (
        es_consulta_reparacion_telefonos(normalizada)
        or es_consulta_programacion(normalizada)
        or evaluar_ambito(normalizada) == "fuera_de_dominio"
    ):
        return _respuesta_previa(
            MENSAJE_ABSTENCION,
            "fuera_de_dominio",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if hay_imagen:
        return None

    if (
        not contexto_revision
        and es_horario_movil_sin_ubicacion(normalizada)
    ):
        return _respuesta_previa(
            MENSAJE_ACLARACION_HORARIO_MOVIL,
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if ubicacion is None and consulta_proximidad(normalizada, exclusiva=True):
        return _respuesta_previa(
            MENSAJE_ACLARACION_PROXIMIDAD,
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    return None


def identificar_entrada_visual(
    datos: bytes,
    formato: str,
    *,
    thread_id: str | None = None,
    turnos_consumidos: int = 0,
) -> IdentificacionImagen | AskOut:
    """Identifica una imagen y resuelve su admisibilidad."""
    with imagen_temporal(datos, formato) as ruta:
        identificacion = identificar_imagen(ruta)

    estado = identificacion["estado"]

    if estado == "allowed":
        return identificacion

    if estado == "policy_violation":
        raise ApiError(ErrorCode.IMAGE_CONTENT_NOT_ALLOWED)

    if estado == "out_of_domain":
        return _respuesta_previa(
            MENSAJE_ABSTENCION,
            "fuera_de_dominio",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if estado == "uncertain":
        return _respuesta_previa(
            "No puedo identificar suficientemente el residuo. "
            "Proporciona otra imagen en la que se vea con claridad.",
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    raise RuntimeError("Estado de identificación visual inválido.")