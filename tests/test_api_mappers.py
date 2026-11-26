"""Pruebas de transformación de modelos relacionales."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from api.mappers import (
    to_api_key_out,
    to_conversation_out,
    to_message_out,
    to_user_out,
)
from api.schemas import (
    ApiKeyOut,
    ConversationOut,
    MessageOut,
    UserOut,
)
from src.enums import ApiKeyRole, MessageRole
from src.models import ApiKey, Conversation, Message, User


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


