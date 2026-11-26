"""Pruebas de las primitivas de seguridad."""

import re

import pytest

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from threading import Event
from unittest.mock import Mock
from uuid import uuid4

from api.error_catalog import ErrorCode
from api.errors import ApiError
import api.security as security
from api.security import (
    SessionRecord,
    SessionStore,
    create_dummy_password_hash,
    generate_secret,
    hash_password,
    hash_secret,
    verify_password,
)
from config import PASSWORD_MAX_BYTES, PASSWORD_MIN_LENGTH


TEST_ROUNDS = 4
PASSWORD = "ContraseñaSegura2026"


# =========================================================
# HASHING DE CONTRASEÑAS
# =========================================================


def test_hash_password() -> None:
    """Genera un hash bcrypt con el coste configurado."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert isinstance(password_hash, str)
    assert len(password_hash) == 60
    assert password_hash.startswith("$2b$04$")
    assert password_hash != PASSWORD


def test_hash_password_random_salt() -> None:
    """Genera hashes diferentes para una misma contraseña."""
    first = hash_password(PASSWORD, TEST_ROUNDS)
    second = hash_password(PASSWORD, TEST_ROUNDS)

    assert first != second
    assert verify_password(PASSWORD, first) is True
    assert verify_password(PASSWORD, second) is True


@pytest.mark.parametrize(
    "password",
    [
        "",
        "a" * (PASSWORD_MIN_LENGTH - 1),
        "a" * (PASSWORD_MAX_BYTES + 1),
        "Contraseña con espacios",
        "Contraseña\tConTabulador",
    ],
)
def test_hash_invalid_password(password: str) -> None:
    """Rechaza contraseñas que incumplen la política."""
    with pytest.raises(ApiError) as exc_info:
        hash_password(password, TEST_ROUNDS)

    assert exc_info.value.code == ErrorCode.INVALID_PASSWORD


def test_hash_password_unicode() -> None:
    """Admite contraseñas Unicode compatibles con bcrypt."""
    password = "ñ" * (PASSWORD_MAX_BYTES // 2)

    password_hash = hash_password(password, TEST_ROUNDS)

    assert verify_password(password, password_hash) is True


def test_hash_password_invalid_rounds() -> None:
    """Identifica una configuración bcrypt inválida."""
    with pytest.raises(ApiError) as exc_info:
        hash_password(PASSWORD, 3)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR


# =========================================================
# VERIFICACIÓN DE CONTRASEÑAS
# =========================================================


def test_verify_correct_password() -> None:
    """Acepta la contraseña asociada al hash."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert verify_password(PASSWORD, password_hash) is True


def test_verify_incorrect_password() -> None:
    """Rechaza una contraseña diferente."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert verify_password("ContraseñaIncorrecta", password_hash) is False


def test_verify_empty_password() -> None:
    """Trata una contraseña vacía como credencial incorrecta."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    assert verify_password("", password_hash) is False


def test_verify_incompatible_password() -> None:
    """Rechaza contraseñas incompatibles con bcrypt."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    with pytest.raises(ApiError) as exc_info:
        verify_password(
            "a" * (PASSWORD_MAX_BYTES + 1),
            password_hash,
        )

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS


@pytest.mark.parametrize(
    "password_hash",
    [
        "",
        "hash-invalido",
        "informacion-sensible-ficticia",
        "$2b$04$" + "!" * 53,
    ],
)
def test_verify_invalid_hash(password_hash: str) -> None:
    """Diferencia un hash inválido de una contraseña incorrecta."""
    with pytest.raises(ApiError) as exc_info:
        verify_password(PASSWORD, password_hash)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR
    assert password_hash not in str(exc_info.value) or not password_hash


def test_verify_truncated_hash() -> None:
    """Detecta un hash almacenado incompleto."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)

    with pytest.raises(ApiError) as exc_info:
        verify_password(PASSWORD, password_hash[:-1])

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR


def test_verify_invalid_hash_cost() -> None:
    """Gestiona un coste bcrypt inválido dentro del hash."""
    password_hash = hash_password(PASSWORD, TEST_ROUNDS)
    invalid_hash = password_hash.replace("$04$", "$03$", 1)

    with pytest.raises(ApiError) as exc_info:
        verify_password(PASSWORD, invalid_hash)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR


# =========================================================
# TOKENS Y API KEYS
# =========================================================


def test_generate_secret() -> None:
    """Genera un secreto compatible con su transmisión HTTP."""
    secret = generate_secret()

    assert len(secret) == 43
    assert re.fullmatch(r"[A-Za-z0-9_-]+", secret)


def test_generate_distinct_secrets() -> None:
    """Comprueba que las emisiones no reutilizan secretos."""
    secrets_generated = {
        generate_secret()
        for _ in range(100)
    }

    assert len(secrets_generated) == 100


def test_hash_secret() -> None:
    """Genera un resumen SHA-256 hexadecimal."""
    secret_hash = hash_secret("abc")

    assert secret_hash == (
        "ba7816bf8f01cfea414140de5dae2223"
        "b00361a396177a9cb410ff61f20015ad"
    )
    assert len(secret_hash) == 64


def test_hash_secret_deterministic() -> None:
    """Obtiene el mismo hash para un mismo secreto."""
    secret = generate_secret()

    assert hash_secret(secret) == hash_secret(secret)


def test_hash_secret_different_values() -> None:
    """Diferencia secretos distintos."""
    assert hash_secret("secret-a") != hash_secret("secret-b")


# =========================================================
# HASH AUXILIAR
# =========================================================


def test_create_dummy_password_hash() -> None:
    """Genera un hash auxiliar válido con el coste solicitado."""
    dummy_hash = create_dummy_password_hash(TEST_ROUNDS)

    assert len(dummy_hash) == 60
    assert dummy_hash.startswith("$2b$04$")
    assert verify_password(PASSWORD, dummy_hash) is False


def test_create_distinct_dummy_hashes() -> None:
    """Evita reutilizar el hash entre inicializaciones."""
    first = create_dummy_password_hash(TEST_ROUNDS)
    second = create_dummy_password_hash(TEST_ROUNDS)

    assert first != second


# =========================================================
# GESTIÓN DE SESIONES
# =========================================================


@pytest.fixture
def session_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> list[float]:
    """Proporciona un reloj monotónico controlado."""
    clock = [1000.0]

    monkeypatch.setattr(
        security,
        "monotonic",
        lambda: clock[0],
    )

    return clock


@pytest.fixture
def session_store(
    session_clock: list[float],
) -> SessionStore:
    """Crea un gestor aislado con una duración de ocho horas."""
    return SessionStore(ttl_seconds=28_800)


def test_create_session(session_store: SessionStore) -> None:
    """Crea una sesión con los datos internos esperados."""
    user_id = uuid4()

    token, session = session_store.create(user_id)

    assert isinstance(session, SessionRecord)
    assert session.user_id == user_id
    assert session.token_hash == hash_secret(token)
    assert session.token_hash != token
    assert len(token) == 43
    assert session.created_at.tzinfo == timezone.utc
    assert session.expires_at - session.created_at == timedelta(
        hours=8,
    )
    assert session.deadline == 1000.0 + 28_800


def test_session_record_immutable(
    session_store: SessionStore,
) -> None:
    """Impide modificar los atributos de una sesión."""
    _, session = session_store.create(uuid4())

    with pytest.raises(FrozenInstanceError):
        session.user_id = uuid4()


def test_session_repr(
    session_store: SessionStore,
) -> None:
    """Excluye el secreto y su hash de la representación."""
    token, session = session_store.create(uuid4())

    assert token not in repr(session)
    assert session.token_hash not in repr(session)


def test_get_session(session_store: SessionStore) -> None:
    """Recupera el registro asociado al token original."""
    token, session = session_store.create(uuid4())

    assert session_store.get(token) == session


def test_invalid_session(session_store: SessionStore) -> None:
    """Rechaza tokens desconocidos."""
    with pytest.raises(ApiError) as exc_info:
        session_store.get(generate_secret())

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


def test_invalid_session_encoding(
    session_store: SessionStore,
) -> None:
    """Gestiona una credencial que no puede codificarse."""
    with pytest.raises(ApiError) as exc_info:
        session_store.get("\ud800")

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


def test_multiple_user_sessions(
    session_store: SessionStore,
) -> None:
    """Permite varias sesiones independientes por usuario."""
    user_id = uuid4()

    first_token, first = session_store.create(user_id)
    second_token, second = session_store.create(user_id)

    assert first_token != second_token
    assert first.token_hash != second.token_hash
    assert first.user_id == second.user_id


def test_session_collision(
    session_store: SessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Impide sobrescribir una sesión ante una colisión."""
    token, session = session_store.create(uuid4())

    monkeypatch.setattr(
        security,
        "generate_secret",
        lambda: token,
    )

    with pytest.raises(ApiError) as exc_info:
        session_store.create(uuid4())

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR
    assert session_store.get(token) == session


def test_session_before_expiration(
    session_store: SessionStore,
    session_clock: list[float],
) -> None:
    """Conserva la sesión hasta su instante de caducidad."""
    token, session = session_store.create(uuid4())

    session_clock[0] += 28_799.999

    assert session_store.get(token) == session


def test_session_exact_expiration(
    session_store: SessionStore,
    session_clock: list[float],
) -> None:
    """Rechaza la sesión exactamente al alcanzar su límite."""
    token, _ = session_store.create(uuid4())

    session_clock[0] += 28_800

    with pytest.raises(ApiError) as exc_info:
        session_store.get(token)

    assert exc_info.value.code == ErrorCode.SESSION_EXPIRED


def test_expired_session_removed(
    session_store: SessionStore,
    session_clock: list[float],
) -> None:
    """Elimina la sesión después de detectar su caducidad."""
    token, _ = session_store.create(uuid4())

    session_clock[0] += 28_800

    with pytest.raises(ApiError) as exc_info:
        session_store.get(token)

    assert exc_info.value.code == ErrorCode.SESSION_EXPIRED

    with pytest.raises(ApiError) as exc_info:
        session_store.get(token)

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


def test_session_periodic_cleanup(
    session_store: SessionStore,
    session_clock: list[float],
) -> None:
    """Elimina registros caducados durante otra operación."""
    expired_token, _ = session_store.create(uuid4())

    session_clock[0] += 28_800

    valid_token, valid = session_store.create(uuid4())

    with pytest.raises(ApiError) as exc_info:
        session_store.get(expired_token)

    assert exc_info.value.code == ErrorCode.INVALID_SESSION
    assert session_store.get(valid_token) == valid


def test_cleanup_interval(
    session_clock: list[float],
) -> None:
    """Respeta el intervalo mínimo entre limpiezas generales."""
    store = SessionStore(ttl_seconds=10)
    expired_token, _ = store.create(uuid4())

    session_clock[0] += 20

    store.create(uuid4())

    with pytest.raises(ApiError) as exc_info:
        store.get(expired_token)

    assert exc_info.value.code == ErrorCode.SESSION_EXPIRED


def test_session_utc_clock_change(
    session_store: SessionStore,
    session_clock: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Utiliza el reloj monotónico aunque cambie el reloj UTC."""
    token, session = session_store.create(uuid4())

    clock = Mock(wraps=datetime)
    clock.now.return_value = session.created_at + timedelta(
        days=365,
    )

    monkeypatch.setattr(security, "datetime", clock)

    session_clock[0] += 60

    assert session_store.get(token) == session

    session_clock[0] += 28_740

    with pytest.raises(ApiError) as exc_info:
        session_store.get(token)

    assert exc_info.value.code == ErrorCode.SESSION_EXPIRED


def test_revoke_session(session_store: SessionStore) -> None:
    """Impide utilizar una sesión revocada."""
    token, _ = session_store.create(uuid4())

    session_store.revoke(token)

    with pytest.raises(ApiError) as exc_info:
        session_store.get(token)

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


def test_revoke_only_current_session(
    session_store: SessionStore,
) -> None:
    """Conserva otras sesiones del mismo usuario."""
    user_id = uuid4()

    first_token, _ = session_store.create(user_id)
    second_token, second = session_store.create(user_id)

    session_store.revoke(first_token)

    assert session_store.get(second_token) == second


def test_revoke_user_sessions(
    session_store: SessionStore,
) -> None:
    """Invalida todas las sesiones del usuario indicado."""
    user_id = uuid4()

    first_token, _ = session_store.create(user_id)
    second_token, _ = session_store.create(user_id)

    session_store.revoke_user(user_id)

    for token in (first_token, second_token):
        with pytest.raises(ApiError) as exc_info:
            session_store.get(token)

        assert exc_info.value.code == ErrorCode.INVALID_SESSION


def test_revoke_user_preserves_other_users(
    session_store: SessionStore,
) -> None:
    """No afecta a las sesiones pertenecientes a otros usuarios."""
    first_user = uuid4()
    second_user = uuid4()

    session_store.create(first_user)

    token, session = session_store.create(second_user)

    session_store.revoke_user(first_user)

    assert session_store.get(token) == session


def test_revoke_unknown_user(
    session_store: SessionStore,
) -> None:
    """Permite invalidar las sesiones de un usuario sin sesiones."""
    token, session = session_store.create(uuid4())

    session_store.revoke_user(uuid4())

    assert session_store.get(token) == session


# =========================================================
# CONCURRENCIA DE SESIONES
# =========================================================


def test_concurrent_session_creation(
    session_store: SessionStore,
) -> None:
    """Permite crear sesiones concurrentes sin perder registros."""
    user_id = uuid4()

    with ThreadPoolExecutor(max_workers=4) as pool:
        sessions = list(
            pool.map(
                session_store.create,
                [user_id] * 50,
            )
        )

    tokens = {
        token
        for token, _ in sessions
    }

    assert len(tokens) == 50

    for token, session in sessions:
        assert session_store.get(token) == session


def test_nested_session_lock(
    session_store: SessionStore,
) -> None:
    """Permite adquisiciones anidadas desde el mismo hilo."""
    with session_store.locked():
        token, session = session_store.create(uuid4())

        assert session_store.get(token) == session

        session_store.revoke(token)

    with pytest.raises(ApiError) as exc_info:
        session_store.get(token)

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


def test_session_revocation_waits_for_lock(
    session_store: SessionStore,
) -> None:
    """Coordina la revocación con otra operación protegida."""
    token, session = session_store.create(uuid4())
    started = Event()

    def revoke_session() -> None:
        """Intenta revocar la sesión desde otro hilo."""
        started.set()
        session_store.revoke(token)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with session_store.locked():
            future = pool.submit(revoke_session)

            assert started.wait(timeout=2)
            assert not future.done()
            assert session_store.get(token) == session

        future.result(timeout=2)

    with pytest.raises(ApiError) as exc_info:
        session_store.get(token)

    assert exc_info.value.code == ErrorCode.INVALID_SESSION