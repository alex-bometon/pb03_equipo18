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
