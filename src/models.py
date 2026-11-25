"""Modelos relacionales de ReciclaTÍA."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from config import EMAIL_MAX_LENGTH

from sqlalchemy import (
    BigInteger,
    CHAR,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    Identity,
    Index,
    Text,
    UniqueConstraint,
    true,
)
from sqlmodel import Field, SQLModel

from src.enums import ApiKeyRole, MessageRole


def utc_now() -> datetime:
    """Devuelve la fecha y hora actual en UTC."""
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    """Usuario registrado."""

    __tablename__ = "user"

    __table_args__ = (
        UniqueConstraint(
            "email",
            name="user_email_unique",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR NOT is_active",
            name="user_deleted_inactive",
        ),
    )

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
    )

    email: str = Field(
        max_length=EMAIL_MAX_LENGTH,
        nullable=False,
    )

    password_hash: str = Field(
        max_length=255,
        nullable=False,
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    is_active: bool = Field(
        default=True,
        nullable=False,
        sa_column_kwargs={"server_default": true()},
    )

    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )


class ApiKey(SQLModel, table=True):
    """Credencial de acceso al asistente."""

    __tablename__ = "api_key"

    __table_args__ = (
        UniqueConstraint(
            "key_hash",
            name="api_key_hash_unique",
        ),
        CheckConstraint(
            "role = 'free' OR user_id IS NOT NULL",
            name="api_key_role_owner",
        ),
        CheckConstraint(
            "deleted_at IS NULL OR NOT is_active",
            name="api_key_deleted_inactive",
        ),
        Index(
            "api_key_user_id_index",
            "user_id",
        ),
    )

    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
    )

    user_id: UUID | None = Field(
        default=None,
        foreign_key="user.id",
        nullable=True,
    )

    key_hash: str = Field(
        sa_type=CHAR(64),
        nullable=False,
    )

    role: ApiKeyRole = Field(
        sa_type=SAEnum(
            ApiKeyRole,
            name="api_key_role",
            native_enum=True,
            values_callable=lambda enum: [
                member.value for member in enum
            ],
            validate_strings=True,
        ),
        nullable=False,
    )

    is_active: bool = Field(
        default=True,
        nullable=False,
        sa_column_kwargs={"server_default": true()},
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    last_used_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )

    deleted_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),
        nullable=True,
    )


class Conversation(SQLModel, table=True):
    """Conversación asociada a una API key."""

    __tablename__ = "conversation"

    __table_args__ = (
        Index(
            "conversation_api_key_id_index",
            "api_key_id",
        ),
    )

    id: UUID = Field(primary_key=True)

    api_key_id: UUID = Field(
        foreign_key="api_key.id",
        nullable=False,
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )


class Message(SQLModel, table=True):
    """Mensaje perteneciente a un turno resuelto."""

    __tablename__ = "message"

    __table_args__ = (
        CheckConstraint(
            "turn_number > 0",
            name="message_positive_turn",
        ),
        CheckConstraint(
            "length(btrim(content)) > 0",
            name="message_nonempty_content",
        ),
        UniqueConstraint(
            "thread_id",
            "turn_number",
            "role",
            name="message_thread_turn_role_unique",
        ),
        Index(
            "message_thread_id_id_index",
            "thread_id",
            "id",
        ),
    )

    id: int | None = Field(
        default=None,
        sa_column=Column(
            BigInteger,
            Identity(),
            primary_key=True,
        ),
    )

    thread_id: UUID = Field(
        foreign_key="conversation.id",
        nullable=False,
    )

    role: MessageRole = Field(
        sa_type=SAEnum(
            MessageRole,
            name="message_role",
            native_enum=True,
            values_callable=lambda enum: [
                member.value for member in enum
            ],
            validate_strings=True,
        ),
        nullable=False,
    )

    content: str = Field(
        sa_type=Text,
        nullable=False,
    )

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_type=DateTime(timezone=True),
        nullable=False,
    )

    turn_number: int = Field(nullable=False)
