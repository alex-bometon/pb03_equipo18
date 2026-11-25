"""Pruebas de concurrencia y bloqueos en PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy.exc import OperationalError
from sqlmodel import Session

from src import db
from src.enums import ApiKeyRole
from src.models import ApiKey, User


pytestmark = pytest.mark.integration


def test_row_lock(clean_db):
    engine = clean_db

    with Session(engine) as session:
        user = User(
            email="lock@example.com",
            password_hash="hash-ficticio",
        )

        user_id = user.id

        db.create_user(session, user)
        session.commit()

    with Session(engine) as session_a:
        with Session(engine) as session_b:

            db.get_user_by_id(
                session_a,
                user_id,
                for_update=True,
            )

            try:
                with pytest.raises(OperationalError) as error:
                    db.get_user_by_id(
                        session_b,
                        user_id,
                        for_update=True,
                    )

                assert error.value.orig.pgcode == "55P03"

            finally:
                session_b.rollback()
                session_a.rollback()

            result = db.get_user_by_id(
                session_b,
                user_id,
                for_update=True,
            )

            assert result is not None


def test_concurrent_key_creation(clean_db):
    engine = clean_db

    with Session(engine) as session:
        user = User(
            email="concurrency@example.com",
            password_hash="hash-ficticio",
        )

        user_id = user.id

        db.create_user(session, user)
        session.commit()

    barrier = Barrier(2, timeout=5)

    def create_free_key(number: int) -> bool:
        with Session(engine) as session:
            barrier.wait()

            with session.begin():
                owner = db.get_user_by_id(
                    session,
                    user_id,
                    for_update=True,
                )

                assert owner is not None

                active_keys = db.count_active_api_keys(
                    session,
                    user_id,
                    ApiKeyRole.FREE,
                )

                if active_keys >= 1:
                    return False

                db.create_api_key(
                    session,
                    ApiKey(
                        user_id=user_id,
                        key_hash=f"{number:064x}",
                        role=ApiKeyRole.FREE,
                    ),
                )

                return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create_free_key, 1)
        second = executor.submit(create_free_key, 2)

        results = [
            first.result(timeout=15),
            second.result(timeout=15),
        ]

    assert sorted(results) == [False, True]

    with Session(engine) as session:
        assert db.count_active_api_keys(
            session,
            user_id,
            ApiKeyRole.FREE,
        ) == 1
