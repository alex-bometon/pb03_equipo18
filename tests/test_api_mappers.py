"""Pruebas de transformación de modelos relacionales."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError
from urllib.parse import urlsplit

from api.mappers import (
    to_ask_out,
    to_api_key_out,
    to_conversation_out,
    to_message_out,
    to_user_out,
)
from api.schemas import (
    AskOut,
    FuenteOut,
    GeografiaOut,
    ApiKeyOut,
    ConversationOut,
    MessageOut,
    UserOut,
)
from config import CSV_DIR, FUENTES_OFICIALES, HTML_DIR
from src.enums import ApiKeyRole, MessageRole
from src.models import ApiKey, Conversation, Message, User
from src.agent_schedule import FUENTE_HORARIO_VIDRIO
from src.state import EstadoProducto, crear_estado_producto


USER_ID = UUID("550e8400-e29b-41d4-a716-446655440000")
API_KEY_ID = UUID("550e8400-e29b-41d4-a716-446655440001")
THREAD_ID = UUID("550e8400-e29b-41d4-a716-446655440002")

CREATED_AT = datetime(
    2026,
    11,
    25,
    16,
    30,
    tzinfo=timezone(timedelta(hours=1)),
)

CREATED_AT_UTC = "2026-11-25T15:30:00Z"


@pytest.fixture
def usuario() -> User:
    """Proporciona un usuario con datos ficticios."""
    return User(
        id=USER_ID,
        email="usuario@example.com",
        password_hash="hash-ficticio",
        created_at=CREATED_AT,
        is_active=True,
    )


@pytest.fixture
def clave() -> ApiKey:
    """Proporciona una API key con datos ficticios."""
    return ApiKey(
        id=API_KEY_ID,
        user_id=USER_ID,
        role=ApiKeyRole.USER,
        key_hash="a" * 64,
        created_at=CREATED_AT,
        is_active=True,
    )


@pytest.fixture
def conversacion() -> Conversation:
    """Proporciona una conversación ficticia."""
    return Conversation(
        id=THREAD_ID,
        api_key_id=API_KEY_ID,
        created_at=CREATED_AT,
    )


@pytest.fixture
def mensaje() -> Message:
    """Proporciona un mensaje ficticio."""
    return Message(
        id=1,
        thread_id=THREAD_ID,
        role=MessageRole.USER,
        content="¿Dónde debo reciclar una pila?",
        created_at=CREATED_AT,
        turn_number=1,
    )


# =========================================================
# USUARIOS
# =========================================================

def test_to_user_out(usuario: User) -> None:
    """Comprueba el contrato público de un usuario."""
    resultado = to_user_out(usuario)

    assert isinstance(resultado, UserOut)

    assert resultado.model_dump(mode="json") == {
        "id": str(USER_ID),
        "email": usuario.email,
        "created_at": CREATED_AT_UTC,
        "is_active": True,
        "deleted_at": None,
    }


def test_to_user_out_usuario_inactivo(usuario: User) -> None:
    """Conserva el estado de un usuario inactivo."""
    usuario.is_active = False

    resultado = to_user_out(usuario)

    assert resultado.is_active is False


def test_to_user_out_no_modifica_original(usuario: User) -> None:
    """Comprueba que la transformación no altera el usuario."""
    original = usuario.model_dump()

    to_user_out(usuario)

    assert usuario.model_dump() == original


def test_to_user_out_rechaza_email_vacio(usuario: User) -> None:
    """Propaga los errores del contrato público."""
    usuario.email = ""

    with pytest.raises(ValidationError):
        to_user_out(usuario)


# =========================================================
# API KEYS
# =========================================================

@pytest.mark.parametrize("role", list(ApiKeyRole))
def test_to_api_key_out(
    clave: ApiKey,
    role: ApiKeyRole,
) -> None:
    """Comprueba la transformación de todos los roles."""
    clave.role = role

    resultado = to_api_key_out(clave)

    assert isinstance(resultado, ApiKeyOut)

    assert resultado.model_dump(mode="json") == {
        "id": str(API_KEY_ID),
        "role": role.value,
        "user_id": str(USER_ID),
        "is_active": True,
        "created_at": CREATED_AT_UTC,
        "last_used_at": None,
        "deleted_at": None,
    }


def test_to_api_key_out_free_anonima(clave: ApiKey) -> None:
    """Conserva la ausencia de propietario de una clave Free."""
    clave.role = ApiKeyRole.FREE
    clave.user_id = None

    resultado = to_api_key_out(clave)

    assert resultado.user_id is None
    assert resultado.role == ApiKeyRole.FREE


def test_to_api_key_out_eliminada(clave: ApiKey) -> None:
    """Conserva la información de eliminación lógica."""
    clave.is_active = False
    clave.deleted_at = CREATED_AT

    resultado = to_api_key_out(clave)

    assert resultado.is_active is False
    assert resultado.deleted_at is not None

    assert resultado.model_dump(mode="json")[
        "deleted_at"
    ] == CREATED_AT_UTC


def test_to_api_key_out_ultimo_uso(clave: ApiKey) -> None:
    """Conserva la fecha del último uso en UTC."""
    clave.last_used_at = CREATED_AT

    resultado = to_api_key_out(clave)

    assert resultado.model_dump(mode="json")[
        "last_used_at"
    ] == CREATED_AT_UTC


def test_to_api_key_out_no_modifica_original(
    clave: ApiKey,
) -> None:
    """Comprueba que la transformación no altera la clave."""
    original = clave.model_dump()

    to_api_key_out(clave)

    assert clave.model_dump() == original


def test_to_api_key_out_rechaza_estado_invalido(
    clave: ApiKey,
) -> None:
    """Rechaza una clave eliminada que continúa activa."""
    clave.deleted_at = CREATED_AT

    with pytest.raises(ValidationError):
        to_api_key_out(clave)


@pytest.mark.parametrize(
    "role",
    [ApiKeyRole.USER, ApiKeyRole.ADMIN],
)
def test_to_api_key_out_rechaza_ausencia_propietario(
    clave: ApiKey,
    role: ApiKeyRole,
) -> None:
    """Rechaza claves User y Admin sin propietario."""
    clave.role = role
    clave.user_id = None

    with pytest.raises(ValidationError):
        to_api_key_out(clave)


# =========================================================
# CONVERSACIONES
# =========================================================

def test_to_conversation_out(
    conversacion: Conversation,
) -> None:
    """Comprueba el contrato público de una conversación."""
    resultado = to_conversation_out(conversacion)

    assert isinstance(resultado, ConversationOut)
    assert isinstance(resultado.thread_id, str)
    assert isinstance(resultado.api_key_id, str)

    assert resultado.model_dump(mode="json") == {
        "thread_id": str(THREAD_ID),
        "api_key_id": str(API_KEY_ID),
        "created_at": CREATED_AT_UTC,
    }


def test_to_conversation_out_no_modifica_original(
    conversacion: Conversation,
) -> None:
    """Comprueba que la transformación no altera la entidad."""
    original = conversacion.model_dump()

    to_conversation_out(conversacion)

    assert conversacion.model_dump() == original


def test_to_conversation_out_rechaza_fecha_sin_zona(
    conversacion: Conversation,
) -> None:
    """Rechaza fechas que no identifican un instante inequívoco."""
    conversacion.created_at = datetime(2026, 11, 25)

    with pytest.raises(ValidationError):
        to_conversation_out(conversacion)


# =========================================================
# MENSAJES
# =========================================================

@pytest.mark.parametrize("role", list(MessageRole))
def test_to_message_out(
    mensaje: Message,
    role: MessageRole,
) -> None:
    """Comprueba la transformación de los roles de mensaje."""
    mensaje.role = role

    resultado = to_message_out(mensaje)

    assert isinstance(resultado, MessageOut)

    assert resultado.model_dump(mode="json") == {
        "role": role.value,
        "content": mensaje.content,
        "created_at": CREATED_AT_UTC,
    }


def test_to_message_out_conserva_contenido(
    mensaje: Message,
) -> None:
    """Conserva el contenido y su formato original."""
    mensaje.content = "  Primera línea.\nSegunda línea.  "

    resultado = to_message_out(mensaje)

    assert resultado.content == mensaje.content


def test_to_message_out_no_modifica_original(
    mensaje: Message,
) -> None:
    """Comprueba que la transformación no altera el mensaje."""
    original = mensaje.model_dump()

    to_message_out(mensaje)

    assert mensaje.model_dump() == original


@pytest.mark.parametrize("content", ["", "   ", "\t\n"])
def test_to_message_out_rechaza_contenido_vacio(
    mensaje: Message,
    content: str,
) -> None:
    """Propaga los errores de validación del contenido."""
    mensaje.content = content

    with pytest.raises(ValidationError):
        to_message_out(mensaje)


def test_to_user_out_usuario_eliminado(
    usuario: User,
) -> None:
    """Conserva la información de eliminación lógica."""
    usuario.is_active = False
    usuario.deleted_at = CREATED_AT

    resultado = to_user_out(usuario)

    assert resultado.is_active is False

    assert resultado.model_dump(mode="json")[
        "deleted_at"
    ] == CREATED_AT_UTC


def test_to_user_out_rechaza_estado_invalido(
    usuario: User,
) -> None:
    """Rechaza usuarios eliminados que permanecen activos."""
    usuario.deleted_at = CREATED_AT

    with pytest.raises(ValidationError):
        to_user_out(usuario)


# =========================================================
# FUENTES DOCUMENTALES
# =========================================================

def test_catalogo_cubre_corpus():
    """Comprueba la correspondencia entre el corpus y el catálogo."""
    documentos = {
        archivo.name
        for directorio, patron in (
            (CSV_DIR, "*.csv"),
            (HTML_DIR, "*.html"),
        )
        for archivo in directorio.glob(patron)
    }

    assert len(documentos) == 15
    assert set(FUENTES_OFICIALES) == documentos


@pytest.mark.parametrize("url", FUENTES_OFICIALES.values())
def test_catalogo_url_municipal(url):
    """Comprueba que cada URL pertenece a un dominio autorizado."""
    componentes = urlsplit(url)

    assert componentes.scheme == "https"
    assert componentes.hostname in {
        "www.madrid.es",
        "datos.madrid.es",
        "sede.madrid.es",
    }
    assert componentes.path
    assert componentes.username is None
    assert componentes.password is None


def test_catalogo_urls_unicas():
    """Comprueba que cada documento tiene su propia referencia."""
    urls = FUENTES_OFICIALES.values()

    assert len(set(urls)) == len(FUENTES_OFICIALES)


# =========================================================
# RESULTADOS DEL ASISTENTE
# =========================================================

@pytest.fixture
def estado_agente() -> EstadoProducto:
    """Proporciona una propuesta válida pendiente de HITL."""
    estado = crear_estado_producto(thread_id=str(THREAD_ID))

    estado.update({
        "pedido_original": "¿Dónde tiro una botella de plástico?",
        "respuesta": "Deposita el envase en el contenedor amarillo.",
        "plan": [
            "Identificar el tipo de residuo.",
            "Depositarlo en el contenedor correspondiente.",
        ],
        "pendiente_hitl": True,
        "approval_id": str(
            UUID("550e8400-e29b-41d4-a716-446655440003")
        ),
        "turnos_consumidos": 1,
        "abstencion": False,
        "estado_evidencia": "suficiente",
    })

    return estado


def _agregar_fuente_rag(
    estado: EstadoProducto,
    *,
    source: str = "tipos_residuos.csv",
    chunk_id: str = "C1",
    id_llamada: str = "llamada-1",
    rol: str = "residuos",
) -> None:
    """Incorpora una referencia y su evidencia documental."""
    referencia = {
        "chunk_id": chunk_id,
        "source": source,
        "path": f"data/raw/csv/{source}",
    }

    estado["evidencias"].append({
        "rol": rol,
        "herramienta": "consultar_rag",
        "id_llamada": id_llamada,
        "datos": {
            "fuentes": [referencia],
        },
    })

    estado["fuentes"].append({
        **referencia,
        "rol": rol,
        "herramienta": "consultar_rag",
        "id_llamada": id_llamada,
    })


@pytest.mark.parametrize("aprobado", [None, True, False])
def test_to_ask_out_estados_validos(
    estado_agente: EstadoProducto,
    aprobado: bool | None,
) -> None:
    """Transforma propuestas pendientes, aprobadas y rechazadas."""
    if aprobado is not None:
        estado_agente.update({
            "pendiente_hitl": False,
            "approval_id": None,
            "plan_aprobado": aprobado,
            "done": aprobado,
        })

    if aprobado is False:
        estado_agente.update({
            "plan": [],
            "respuesta": "Plan rechazado.",
            "abstencion": True,
            "estado_evidencia": "insuficiente",
        })

    original = deepcopy(estado_agente)

    resultado = to_ask_out(estado_agente)

    assert isinstance(resultado, AskOut)

    assert resultado.model_dump(mode="json") == {
        "thread_id": estado_agente["thread_id"],
        "respuesta": estado_agente["respuesta"],
        "plan": estado_agente["plan"],
        "plan_aprobado": aprobado,
        "done": aprobado is True,
        "pendiente_hitl": aprobado is None,
        "fuentes": [],
        "geografia": [],
        "abstencion": estado_agente["abstencion"],
        "motivo": estado_agente["motivo"],
        "estado_evidencia": estado_agente["estado_evidencia"],
        "limitaciones": estado_agente["limitaciones"],
        "turnos_consumidos": 1,
        "error": None,
        "approval_id": estado_agente["approval_id"],
    }

    assert estado_agente == original


def test_to_ask_out_conserva_referencias(
    estado_agente: EstadoProducto,
) -> None:
    """Conserva fuentes y geografía sin exponer campos internos."""
    _agregar_fuente_rag(estado_agente)
    _agregar_geografia(estado_agente)

    original = deepcopy(estado_agente)
    resultado = to_ask_out(estado_agente)
    datos = resultado.model_dump(mode="json")

    assert len(datos["fuentes"]) == 1
    assert len(datos["geografia"]) == 1

    geografia = datos["geografia"][0]
    punto = geografia["puntos"][0]

    assert geografia["total_encontrados"] == 1
    assert punto["distancia_metros"] == 350.0
    assert punto["direccion"] == "Calle de Prueba, 1"

    assert "puntos_candidatos" not in geografia
    assert "id" not in punto
    assert "residuos_url" not in punto
    assert "fuente" not in punto
    assert "path" not in datos["fuentes"][0]

    assert estado_agente == original


def test_to_ask_out_rechaza_error_tecnico(
    estado_agente: EstadoProducto,
) -> None:
    """Impide transformar un fallo técnico en un resultado válido."""
    estado_agente["error"] = "Error durante la ejecución."

    with pytest.raises(RuntimeError, match="error técnico"):
        to_ask_out(estado_agente)


def test_to_ask_out_rechaza_turno_sin_hitl(
    estado_agente: EstadoProducto,
) -> None:
    """Impide aceptar una ejecución sin decisión ni propuesta."""
    estado_agente["pendiente_hitl"] = False
    estado_agente["approval_id"] = None

    with pytest.raises(RuntimeError, match="turno válido"):
        to_ask_out(estado_agente)


def test_to_ask_out_rechaza_respuesta_invalida(
    estado_agente: EstadoProducto,
) -> None:
    """Propaga los errores de validación del contrato público."""
    estado_agente["respuesta"] = ""

    with pytest.raises(ValidationError):
        to_ask_out(estado_agente)


@pytest.mark.parametrize(
    "source",
    [
        "tipos_residuos.csv",
        "documento_no_catalogado.csv",
    ],
)
def test_to_ask_out_resuelve_url_documental(
    estado_agente: EstadoProducto,
    source: str,
) -> None:
    """Resuelve únicamente URL autorizadas por el catálogo."""
    _agregar_fuente_rag(estado_agente, source=source)

    estado_agente["fuentes"][0]["url"] = "https://example.com"

    resultado = to_ask_out(estado_agente)

    assert len(resultado.fuentes) == 1

    assert resultado.model_dump(mode="json")["fuentes"] == [{
        "chunk_id": "C1",
        "source": source,
        "url": FUENTES_OFICIALES.get(source),
        "rol": "residuos",
        "id_llamada": "llamada-1",
    }]

def test_to_ask_out_conserva_citas_de_distintas_llamadas(
    estado_agente: EstadoProducto,
) -> None:
    """Conserva citas locales aunque coincidan sus identificadores."""
    _agregar_fuente_rag(estado_agente)

    _agregar_fuente_rag(
        estado_agente,
        source="puntos_limpios_fijos.csv",
        id_llamada="llamada-2",
        rol="puntos",
    )

    resultado = to_ask_out(estado_agente)

    assert len(resultado.fuentes) == 2

    assert [
        fuente.chunk_id for fuente in resultado.fuentes
    ] == ["C1", "C1"]

    assert [
        fuente.id_llamada for fuente in resultado.fuentes
    ] == ["llamada-1", "llamada-2"]


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("chunk_id", "C99"),
        ("source", "puntos_limpios_fijos.csv"),
        ("path", "ruta_inventada.csv"),
        ("rol", "puntos"),
        ("id_llamada", "llamada-inexistente"),
    ],
)
def test_to_ask_out_rechaza_fuente_sin_respaldo(
    estado_agente: EstadoProducto,
    campo: str,
    valor: str,
) -> None:
    """Rechaza referencias que no corresponden a su evidencia."""
    _agregar_fuente_rag(estado_agente)
    estado_agente["fuentes"][0][campo] = valor

    with pytest.raises(ValueError, match="sin respaldo"):
        to_ask_out(estado_agente)


def test_to_ask_out_referencia_normativa(
    estado_agente: EstadoProducto,
) -> None:
    """Resuelve la referencia normativa sin ejecutar el RAG."""
    estado_agente["fuentes"].append({
        "chunk_id": "NORMA-VIDRIO",
        "source": "Ayuntamiento de Madrid — Recogida de vidrio",
        "path": FUENTE_HORARIO_VIDRIO,
    })

    resultado = to_ask_out(estado_agente)

    assert resultado.model_dump(mode="json")["fuentes"] == [{
        "chunk_id": "NORMA-VIDRIO",
        "source": "Ayuntamiento de Madrid — Recogida de vidrio",
        "url": FUENTE_HORARIO_VIDRIO,
        "rol": None,
        "id_llamada": None,
    }]

def test_to_ask_out_rechaza_referencia_normativa_invalida(
    estado_agente: EstadoProducto,
) -> None:
    """Rechaza una referencia normativa con procedencia incorrecta."""
    estado_agente["fuentes"].append({
        "chunk_id": "NORMA-VIDRIO",
        "source": "Ayuntamiento de Madrid — Recogida de vidrio",
        "path": "https://example.com",
    })

    with pytest.raises(ValueError, match="normativa inválida"):
        to_ask_out(estado_agente)


def _agregar_geografia(
    estado: EstadoProducto,
    *,
    vacio: bool = False,
) -> dict:
    """Incorpora un resultado de la herramienta geográfica."""
    punto = {
        "id": 123,
        "tipo": "Fijo",
        "direccion": "Calle de Prueba, 1",
        "distrito": "Centro",
        "latitud": 40.4168,
        "longitud": -3.7038,
        "distancia_metros": 350.0,
        "fuente": "api",
        "residuos_url": "https://example.com",
    }

    datos = {
        "fuente": "api",
        "tipo_solicitado": "todos",
        "radio_metros": 2000,
        "total_encontrados": 0 if vacio else 1,
        "puntos": [] if vacio else [punto],
        "puntos_candidatos": [] if vacio else [deepcopy(punto)],
        "aviso": None,
    }

    estado["evidencias"].append({
        "rol": "puntos",
        "herramienta": "buscar_puntos_limpios_cercanos",
        "id_llamada": "geo-1",
        "datos": datos,
    })

    return datos


def test_to_ask_out_geografia_vacia(
    estado_agente: EstadoProducto,
) -> None:
    """Conserva una búsqueda válida sin instalaciones encontradas."""
    _agregar_geografia(estado_agente, vacio=True)

    resultado = to_ask_out(estado_agente)

    assert len(resultado.geografia) == 1
    assert resultado.geografia[0].total_encontrados == 0
    assert resultado.geografia[0].puntos == []


def test_to_ask_out_geografia_respaldo_local(
    estado_agente: EstadoProducto,
) -> None:
    """Conserva la procedencia y el aviso del respaldo local."""
    datos = _agregar_geografia(estado_agente)

    datos["fuente"] = "corpus_local"
    datos["aviso"] = "Los datos pueden estar desactualizados."
    datos["puntos"][0]["fuente"] = "corpus_local"
    datos["puntos"][0]["documento_origen"] = (
        "puntos_limpios_fijos.csv"
    )

    resultado = to_ask_out(estado_agente)
    geografia = resultado.geografia[0]

    assert geografia.fuente == "corpus_local"
    assert geografia.aviso == datos["aviso"]
    assert geografia.puntos[0].documento_origen == (
        "puntos_limpios_fijos.csv"
    )


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("total_encontrados", 2),
        ("fuente", "desconocida"),
        ("radio_metros", 100),
    ],
)
def test_to_ask_out_rechaza_geografia_invalida(
    estado_agente: EstadoProducto,
    campo: str,
    valor,
) -> None:
    """Propaga las incoherencias del contrato geográfico."""
    datos = _agregar_geografia(estado_agente)
    datos[campo] = valor

    with pytest.raises(ValidationError):
        to_ask_out(estado_agente)


def test_to_ask_out_no_descarta_puntos_invalidos(
    estado_agente: EstadoProducto,
) -> None:
    """Impide ocultar registros geográficos estructuralmente inválidos."""
    datos = _agregar_geografia(estado_agente)
    datos["puntos"] = [None]

    with pytest.raises(ValueError, match="Registro de punto limpio"):
        to_ask_out(estado_agente)