"""Transformación de modelos internos en contratos públicos."""

from api.schemas import (
    ApiKeyOut,
    AskOut,
    ConversationOut,
    FuenteOut,
    GeografiaOut,
    MessageOut,
    PuntoLimpioOut,
    UserOut,
)
from config import FUENTES_OFICIALES
from src.agent_schedule import FUENTE_HORARIO_VIDRIO
from src.models import ApiKey, Conversation, Message, User
from src.state import EstadoProducto


def to_user_out(user: User) -> UserOut:
    """Transforma un usuario en su representación pública."""
    return UserOut(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        is_active=user.is_active,
        deleted_at=user.deleted_at,
    )


def to_api_key_out(api_key: ApiKey) -> ApiKeyOut:
    """Transforma una API key sin exponer su credencial."""
    return ApiKeyOut(
        id=api_key.id,
        role=api_key.role,
        user_id=api_key.user_id,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        deleted_at=api_key.deleted_at,
    )


def to_conversation_out(
    conversation: Conversation,
) -> ConversationOut:
    """Transforma una conversación en su representación pública."""
    return ConversationOut(
        thread_id=str(conversation.id),
        api_key_id=str(conversation.api_key_id),
        created_at=conversation.created_at,
    )


def to_message_out(message: Message) -> MessageOut:
    """Transforma un mensaje sin exponer identificadores internos."""
    return MessageOut(
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )

def _fuente_respaldada(
    fuente: dict,
    evidencias: list[dict],
) -> bool:
    """Comprueba la procedencia de una referencia documental."""
    for evidencia in evidencias:
        if evidencia.get("herramienta") != "consultar_rag":
            continue

        if (
            evidencia.get("rol") != fuente.get("rol")
            or evidencia.get("id_llamada") != fuente.get("id_llamada")
        ):
            continue

        datos = evidencia.get("datos")

        if not isinstance(datos, dict):
            continue

        referencias = datos.get("fuentes")

        if not isinstance(referencias, list):
            continue

        for referencia in referencias:
            if isinstance(referencia, dict) and all(
                referencia.get(campo) == fuente.get(campo)
                for campo in ("chunk_id", "source", "path")
            ):
                return True

    return False

def _transformar_fuentes(
    estado: EstadoProducto,
) -> list[FuenteOut]:
    """Transforma las referencias documentales autorizadas."""
    fuentes = []

    for fuente in estado["fuentes"]:
        if not isinstance(fuente, dict):
            raise ValueError("Referencia documental inválida.")

        referencia = FuenteOut(
            chunk_id=fuente["chunk_id"],
            source=fuente["source"],
            rol=fuente.get("rol"),
            id_llamada=fuente.get("id_llamada"),
        )

        if referencia.chunk_id == "NORMA-VIDRIO":
            if (
                referencia.source
                != "Ayuntamiento de Madrid — Recogida de vidrio"
                or fuente.get("path") != FUENTE_HORARIO_VIDRIO
            ):
                raise ValueError("Referencia normativa inválida.")

            url = FUENTE_HORARIO_VIDRIO

        else:
            if not _fuente_respaldada(fuente, estado["evidencias"]):
                raise ValueError("Referencia documental sin respaldo.")

            if "/" in referencia.source or "\\" in referencia.source:
                raise ValueError("Nombre de fuente documental inválido.")

            url = FUENTES_OFICIALES.get(referencia.source)

        fuentes.append(FuenteOut(
            chunk_id=referencia.chunk_id,
            source=referencia.source,
            url=url,
            rol=referencia.rol,
            id_llamada=referencia.id_llamada,
        ))

    return fuentes

def _transformar_punto_limpio(
    punto: dict,
) -> PuntoLimpioOut:
    """Transforma una instalación municipal en su contrato público."""
    return PuntoLimpioOut(
        tipo=punto["tipo"],
        direccion=punto["direccion"],
        distrito=punto.get("distrito"),
        latitud=punto["latitud"],
        longitud=punto["longitud"],
        distancia_metros=punto["distancia_metros"],
        horario_apertura=punto.get("horario_apertura"),
        horario_cierre=punto.get("horario_cierre"),
        dia_semana=punto.get("dia_semana"),
        turno=punto.get("turno"),
        documento_origen=punto.get("documento_origen"),
    )

def _transformar_geografia(
    estado: EstadoProducto,
) -> list[GeografiaOut]:
    """Recupera los resultados geográficos satisfactorios del turno."""
    resultados = []

    for evidencia in estado["evidencias"]:
        if evidencia.get("herramienta") != "buscar_puntos_limpios_cercanos":
            continue

        datos = evidencia.get("datos")

        if not isinstance(datos, dict):
            raise ValueError("Resultado geográfico inválido.")

        puntos = datos.get("puntos")

        if not isinstance(puntos, list):
            raise ValueError("Lista de puntos limpios inválida.")

        if any(not isinstance(punto, dict) for punto in puntos):
            raise ValueError("Registro de punto limpio inválido.")

        resultados.append(GeografiaOut(
            fuente=datos["fuente"],
            tipo_solicitado=datos["tipo_solicitado"],
            radio_metros=datos["radio_metros"],
            total_encontrados=datos["total_encontrados"],
            puntos=[
                _transformar_punto_limpio(punto)
                for punto in puntos
            ],
            aviso=datos.get("aviso"),
        ))

    return resultados

def to_ask_out(estado: EstadoProducto) -> AskOut:
    """Transforma un resultado del agente en su contrato público."""
    if estado["error"] is not None:
        raise RuntimeError("El agente ha devuelto un error técnico.")

    if (
        estado["pendiente_hitl"] is False
        and estado["plan_aprobado"] is None
    ):
        raise RuntimeError("El agente no ha resuelto un turno válido.")

    if not isinstance(estado["fuentes"], list):
        raise ValueError("Lista de fuentes inválida.")

    if not isinstance(estado["evidencias"], list) or any(
        not isinstance(evidencia, dict)
        for evidencia in estado["evidencias"]
    ):
        raise ValueError("Lista de evidencias inválida.")

    return AskOut(
        thread_id=estado["thread_id"],
        respuesta=estado["respuesta"],
        plan=estado["plan"],
        plan_aprobado=estado["plan_aprobado"],
        done=estado["done"],
        pendiente_hitl=estado["pendiente_hitl"],
        fuentes=_transformar_fuentes(estado),
        geografia=_transformar_geografia(estado),
        abstencion=estado["abstencion"],
        motivo=estado["motivo"],
        estado_evidencia=estado["estado_evidencia"],
        limitaciones=estado["limitaciones"],
        turnos_consumidos=estado["turnos_consumidos"],
        error=estado["error"],
        approval_id=estado["approval_id"],
    )