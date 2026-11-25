"""Pruebas de las operaciones CRUD de persistencia."""

from uuid import uuid4

import pytest

from src import db
from src.enums import ApiKeyRole, MessageRole
from src.models import User, ApiKey


pytestmark = pytest.mark.integration


def test_create_and_get_user(db_session):
    user = User(
        email="test@example.com",
        password_hash="hash-ficticio",
    )

    db.create_user(db_session, user)
    db_session.commit()

    result = db.get_user_by_id(db_session, user.id)

    assert result is not None
    assert result.email == "test@example.com"
    assert result.is_active is True
    assert result.deleted_at is None


def test_get_user_by_email(db_session):
    user = User(
        email="test@example.com",
        password_hash="hash-ficticio",
    )

    db.create_user(db_session, user)
    db_session.commit()

    result = db.get_user_by_email(
        db_session, "test@example.com"
    )

    assert result.id == user.id


def test_nonexistent_user(db_session):
    assert db.get_user_by_id(
        db_session, uuid4()
    ) is None


def test_list_users(db_session):
    for number in range(3):
        db.create_user(
            db_session,
            User(
                email=f"user{number}@example.com",
                password_hash="hash-ficticio",
            ),
        )

    db_session.commit()

    assert len(db.list_users(db_session)) == 3


def test_update_password(db_session):
    user = User(
        email="test@example.com",
        password_hash="hash-anterior",
    )

    db.create_user(db_session, user)
    db_session.commit()

    user_id = user.id

    db.update_user_password(user, "hash-nuevo")
    db_session.commit()
    db_session.expire_all()

    result = db.get_user_by_id(db_session, user_id)

    assert result.password_hash == "hash-nuevo"


def test_anonymous_free_key(db_session):
    key = ApiKey(
        key_hash="a" * 64,
        role=ApiKeyRole.FREE,
    )

    db.create_api_key(db_session, key)
    db_session.commit()

    result = db.get_api_key_by_hash(
        db_session, "a" * 64
    )

    assert result.user_id is None
    assert result.role == ApiKeyRole.FREE


def test_count_active_keys(db_session):
    user = User(
        email="test@example.com",
        password_hash="hash-ficticio",
    )

    db.create_user(db_session, user)
    db_session.flush()

    for number in range(3):
        db.create_api_key(
            db_session,
            ApiKey(
                user_id=user.id,
                key_hash=f"{number:064x}",
                role=ApiKeyRole.USER,
                is_active=number != 2,
            ),
        )

    db_session.commit()

    assert db.count_active_api_keys(
        db_session,
        user.id,
        ApiKeyRole.USER,
    ) == 2


def test_update_last_used(db_session):
    key = ApiKey(
        key_hash="b" * 64,
        role=ApiKeyRole.FREE,
    )

    db.create_api_key(db_session, key)
    db_session.commit()

    assert key.last_used_at is None

    key_id = key.id

    db.update_api_key_last_used(key)
    db_session.commit()
    db_session.expire_all()

    result = db.get_api_key_by_id(db_session, key_id)

    assert result.last_used_at is not None


def test_conversation_ownership(db_session):
    key_a = ApiKey(
        key_hash="a" * 64,
        role=ApiKeyRole.FREE,
    )

    key_b = ApiKey(
        key_hash="b" * 64,
        role=ApiKeyRole.FREE,
    )

    db.create_api_key(db_session, key_a)
    db.create_api_key(db_session, key_b)
    db_session.commit()

    thread_id = uuid4()

    db.create_conversation(
        db_session, thread_id, key_a.id
    )

    db_session.commit()

    assert db.get_conversation_by_owner(
        db_session, thread_id, key_a.id
    ) is not None

    assert db.get_conversation_by_owner(
        db_session, thread_id, key_b.id
    ) is None

    assert len(db.list_api_key_conversations(
        db_session, key_a.id
    )) == 1

    assert db.list_api_key_conversations(
        db_session, key_b.id
    ) == []


def test_save_and_list_turn(db_session):
    key = ApiKey(
        key_hash="a" * 64,
        role=ApiKeyRole.FREE,
    )

    db.create_api_key(db_session, key)
    db_session.commit()

    thread_id = uuid4()

    db.create_conversation(
        db_session, thread_id, key.id
    )
    db_session.commit()

    assert not db.turn_exists(
        db_session, thread_id, 1
    )

    db.save_turn(
        db_session,
        thread_id,
        1,
        "¿Dónde tiro el papel?",
        "En el contenedor azul.",
    )
    db_session.commit()

    messages = db.list_messages(
        db_session, thread_id
    )

    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER
    assert messages[1].role == MessageRole.ASSISTANT
    assert messages[0].id < messages[1].id

    assert all(
        message.turn_number == 1
        for message in messages
    )

    assert db.turn_exists(
        db_session, thread_id, 1
    )
