"""Pruebas de integridad y atomicidad relacional."""

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src import db
from src.enums import ApiKeyRole, MessageRole
from src.models import ApiKey, User, Conversation, Message


pytestmark = pytest.mark.integration


@pytest.fixture
def thread_id(db_session):
    key = ApiKey(
        key_hash="a" * 64,
        role=ApiKeyRole.FREE,
    )

    db_session.add(key)
    db_session.commit()

    identifier = uuid4()

    db.create_conversation(
        db_session, identifier, key.id
    )
    db_session.commit()

    return identifier


def test_duplicate_email(db_session):
    db_session.add_all([
        User(
            email="duplicate@example.com",
            password_hash="hash-1",
        ),
        User(
            email="duplicate@example.com",
            password_hash="hash-2",
        ),
    ])

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_duplicate_key_hash(db_session):
    db_session.add_all([
        ApiKey(
            key_hash="a" * 64,
            role=ApiKeyRole.FREE,
        ),
        ApiKey(
            key_hash="a" * 64,
            role=ApiKeyRole.FREE,
        ),
    ])

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


@pytest.mark.parametrize(
    "role",
    [ApiKeyRole.USER, ApiKeyRole.ADMIN],
)
def test_key_requires_owner(db_session, role):
    db_session.add(
        ApiKey(
            key_hash="a" * 64,
            role=role,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_invalid_foreign_key(db_session):
    db_session.add(
        Conversation(
            id=uuid4(),
            api_key_id=uuid4(),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


@pytest.mark.parametrize("turn_number", [0, -1])
def test_invalid_turn_number(
    db_session, thread_id, turn_number
):
    db_session.add(
        Message(
            thread_id=thread_id,
            role=MessageRole.USER,
            content="Consulta de prueba",
            turn_number=turn_number,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


@pytest.mark.parametrize("content", ["", "   "])
def test_empty_message(db_session, thread_id, content):
    db_session.add(
        Message(
            thread_id=thread_id,
            role=MessageRole.USER,
            content=content,
            turn_number=1,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()

    db_session.rollback()


def test_duplicate_turn(db_session, thread_id):
    db.save_turn(
        db_session, thread_id, 1, "Pregunta", "Respuesta"
    )
    db_session.commit()

    with pytest.raises(IntegrityError):
        db.save_turn(
            db_session,
            thread_id,
            1,
            "Otra pregunta",
            "Otra respuesta",
        )

    db_session.rollback()

    assert len(db.list_messages(
        db_session, thread_id
    )) == 2


def test_atomic_turn_rollback(db_session, thread_id):
    # Restricción temporal para provocar un fallo real
    # exclusivamente en la segunda inserción.
    db_session.execute(text("""
        ALTER TABLE public.message
        ADD CONSTRAINT test_reject_assistant
        CHECK (role <> 'assistant')
    """))

    with pytest.raises(IntegrityError):
        db.save_turn(
            db_session,
            thread_id,
            1,
            "Pregunta",
            "Respuesta",
        )

    db_session.rollback()

    assert db.list_messages(
        db_session, thread_id
    ) == []


def test_logical_user_deletion(db_session):
    user = User(
        email="test@example.com",
        password_hash="hash-ficticio",
    )

    db.create_user(db_session, user)
    db_session.commit()

    user_id = user.id

    db.delete_user(user)
    db_session.commit()

    result = db.get_user_by_id(db_session, user_id)

    assert result is not None
    assert result.is_active is False
    assert result.deleted_at is not None

    with pytest.raises(ValueError):
        db.set_user_active(result, True)


def test_logical_key_deletion(db_session):
    key = ApiKey(
        key_hash="a" * 64,
        role=ApiKeyRole.FREE,
    )

    db.create_api_key(db_session, key)
    db_session.commit()

    key_id = key.id

    db.delete_api_key(key)
    db_session.commit()

    result = db.get_api_key_by_id(
        db_session, key_id
    )

    assert result is not None
    assert result.is_active is False
    assert result.deleted_at is not None

    with pytest.raises(ValueError):
        db.set_api_key_active(result, True)
