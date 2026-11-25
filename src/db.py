"""Conexiones y persistencia relacional de ReciclaTIA."""

from uuid import UUID

from sqlalchemy import func, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from src.enums import ApiKeyRole, MessageRole
from src.models import ApiKey, Conversation, Message, User, utc_now


def create_db_engine(
    database_url: str,
    *,
    pool_size: int,
    max_overflow: int,
    pool_timeout: int,
    connect_timeout: int,
    statement_timeout: int,
    lock_timeout: int,
) -> Engine:
    """Construye el engine compartido de PostgreSQL."""

    return create_engine(
        database_url,
        echo=False,
        hide_parameters=True,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=pool_timeout,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": connect_timeout,
            "options": (
                f"-c statement_timeout={statement_timeout * 1000} "
                f"-c lock_timeout={lock_timeout * 1000} "
                "-c timezone=UTC"
            ),
        },
    )


def check_database(engine: Engine) -> None:
    """Comprueba la disponibilidad de PostgreSQL."""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))


def ensure_schema(engine: Engine) -> None:
    """Crea las tablas relacionales que todavía no existen."""

    SQLModel.metadata.create_all(engine)


# =========================================================
# USUARIOS
# =========================================================

def create_user(session: Session, user: User) -> User:
    """Incorpora un usuario a la sesión."""
    session.add(user)
    return user


def get_user_by_id(
    session: Session,
    user_id: UUID,
    *,
    for_update: bool = False,
) -> User | None:
    """Recupera un usuario mediante su identificador."""
    statement = select(User).where(User.id == user_id)

    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )

    return session.exec(statement).one_or_none()


def get_user_by_email(
    session: Session,
    email: str,
    *,
    for_update: bool = False,
) -> User | None:
    """Recupera un usuario mediante su email normalizado."""
    statement = select(User).where(User.email == email)

    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )

    return session.exec(statement).one_or_none()


def list_users(session: Session) -> list[User]:
    """Recupera todos los usuarios registrados."""
    statement = select(User).order_by(User.id)

    return list(session.exec(statement).all())


def update_user_password(
    user: User,
    password_hash: str,
) -> User:
    """Actualiza el hash de la contraseña."""
    user.password_hash = password_hash

    return user


def set_user_active(
    user: User,
    is_active: bool,
) -> User:
    """Modifica el estado de un usuario no eliminado."""
    if user.deleted_at is not None:
        raise ValueError("El usuario está eliminado.")

    user.is_active = is_active

    return user


def delete_user(user: User) -> User:
    """Realiza la eliminación lógica del usuario."""
    user.is_active = False

    if user.deleted_at is None:
        user.deleted_at = utc_now()

    return user


# =========================================================
# API KEYS
# =========================================================

def create_api_key(
    session: Session,
    api_key: ApiKey,
) -> ApiKey:
    """Incorpora una API key a la sesión."""
    session.add(api_key)

    return api_key


def get_api_key_by_id(
    session: Session,
    api_key_id: UUID,
    *,
    for_update: bool = False,
) -> ApiKey | None:
    """Recupera una API key mediante su identificador."""
    statement = select(ApiKey).where(
        ApiKey.id == api_key_id
    )

    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )

    return session.exec(statement).one_or_none()


def get_api_key_by_hash(
    session: Session,
    key_hash: str,
    *,
    for_update: bool = False,
) -> ApiKey | None:
    """Recupera una API key mediante su hash."""
    statement = select(ApiKey).where(
        ApiKey.key_hash == key_hash
    )

    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )

    return session.exec(statement).one_or_none()


def list_api_keys(session: Session) -> list[ApiKey]:
    """Recupera todas las API keys."""
    statement = select(ApiKey).order_by(ApiKey.id)

    return list(session.exec(statement).all())


def list_user_api_keys(
    session: Session,
    user_id: UUID,
) -> list[ApiKey]:
    """Recupera las API keys asociadas a un usuario."""
    statement = (
        select(ApiKey)
        .where(ApiKey.user_id == user_id)
        .order_by(ApiKey.id)
    )

    return list(session.exec(statement).all())


def count_active_api_keys(
    session: Session,
    user_id: UUID,
    role: ApiKeyRole,
) -> int:
    """Cuenta las API keys activas de un usuario y rol."""
    statement = (
        select(func.count())
        .select_from(ApiKey)
        .where(
            ApiKey.user_id == user_id,
            ApiKey.role == role,
            ApiKey.is_active.is_(True),
            ApiKey.deleted_at.is_(None),
        )
    )

    return session.exec(statement).one()


def update_api_key_last_used(api_key: ApiKey) -> ApiKey:
    """Registra el último uso autorizado de una API key."""
    api_key.last_used_at = utc_now()

    return api_key


def set_api_key_active(
    api_key: ApiKey,
    is_active: bool,
) -> ApiKey:
    """Modifica el estado de una API key no eliminada."""
    if api_key.deleted_at is not None:
        raise ValueError("La API key está eliminada.")

    api_key.is_active = is_active

    return api_key


def delete_api_key(api_key: ApiKey) -> ApiKey:
    """Realiza la eliminación lógica de una API key."""
    api_key.is_active = False

    if api_key.deleted_at is None:
        api_key.deleted_at = utc_now()

    return api_key


# =========================================================
# CONVERSACIONES
# =========================================================

def create_conversation(
    session: Session,
    thread_id: UUID,
    api_key_id: UUID,
) -> Conversation:
    """Incorpora una conversación a la sesión."""
    conversation = Conversation(
        id=thread_id,
        api_key_id=api_key_id,
    )

    session.add(conversation)

    return conversation


def get_conversation_by_id(
    session: Session,
    thread_id: UUID,
    *,
    for_update: bool = False,
) -> Conversation | None:
    """Recupera una conversación mediante su identificador."""
    statement = select(Conversation).where(
        Conversation.id == thread_id
    )

    if for_update:
        statement = statement.with_for_update().execution_options(
            populate_existing=True
        )

    return session.exec(statement).one_or_none()


def get_conversation_by_owner(
    session: Session,
    thread_id: UUID,
    api_key_id: UUID,
) -> Conversation | None:
    """Recupera una conversación perteneciente a una API key."""
    statement = select(Conversation).where(
        Conversation.id == thread_id,
        Conversation.api_key_id == api_key_id,
    )

    return session.exec(statement).one_or_none()


def list_conversations(
    session: Session,
) -> list[Conversation]:
    """Recupera todas las conversaciones."""
    statement = select(Conversation).order_by(
        Conversation.created_at,
        Conversation.id,
    )

    return list(session.exec(statement).all())


def list_api_key_conversations(
    session: Session,
    api_key_id: UUID,
) -> list[Conversation]:
    """Recupera las conversaciones de una API key."""
    statement = (
        select(Conversation)
        .where(Conversation.api_key_id == api_key_id)
        .order_by(
            Conversation.created_at,
            Conversation.id,
        )
    )

    return list(session.exec(statement).all())


# =========================================================
# MENSAJES
# =========================================================

def save_turn(
    session: Session,
    thread_id: UUID,
    turn_number: int,
    question: str,
    answer: str,
) -> tuple[Message, Message]:
    """Incorpora los dos mensajes de un turno resuelto."""

    if (
        isinstance(turn_number, bool)
        or not isinstance(turn_number, int)
        or turn_number <= 0
    ):
        raise ValueError("Número de turno inválido.")

    if not question.strip() or not answer.strip():
        raise ValueError("Los mensajes no pueden estar vacíos.")

    user_message = Message(
        thread_id=thread_id,
        turn_number=turn_number,
        role=MessageRole.USER,
        content=question,
    )

    session.add(user_message)
    session.flush()

    assistant_message = Message(
        thread_id=thread_id,
        turn_number=turn_number,
        role=MessageRole.ASSISTANT,
        content=answer,
    )

    session.add(assistant_message)
    session.flush()

    return user_message, assistant_message


def list_messages(
    session: Session,
    thread_id: UUID,
) -> list[Message]:
    """Recupera los mensajes de una conversación en orden."""
    statement = (
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.id)
    )

    return list(session.exec(statement).all())


def turn_exists(
    session: Session,
    thread_id: UUID,
    turn_number: int,
) -> bool:
    """Comprueba si existen mensajes asociados al turno."""
    statement = (
        select(Message.id)
        .where(
            Message.thread_id == thread_id,
            Message.turn_number == turn_number,
        )
        .limit(1)
    )

    return session.exec(statement).first() is not None
