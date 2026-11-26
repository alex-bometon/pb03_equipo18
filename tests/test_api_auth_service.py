"""Pruebas del servicio de autenticación de usuarios."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
    TimeoutError as SQLAlchemyTimeoutError,
)
from sqlmodel import Session

import api.auth_service as auth_service
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.schemas import (
    LoginIn,
    LoginOut,
    PasswordChangeIn,
    RegisterIn,
    UserOut,
)
from api.security import (
    SessionRecord,
    SessionStore,
    create_dummy_password_hash,
    verify_password,
)
from src import db
from src.enums import ApiKeyRole
from src.models import ApiKey, User


TEST_ROUNDS = 4
EMAIL = "usuario@example.com"
PASSWORD = "PasswordSegura2026"
NEW_PASSWORD = "NuevaPasswordSegura2026"
OTHER_PASSWORD = "PasswordIncorrecta2026"


class DriverError(Exception):
    """Simula los metadatos de una excepción de PostgreSQL."""

    def __init__(
        self,
        code: str | None,
        constraint: str | None = None,
    ) -> None:
        """Inicializa los metadatos controlados de la excepción."""
        super().__init__("detalle-sensible-ficticio")

        self.pgcode = code
        self.diag = SimpleNamespace(
            constraint_name=constraint,
        )


@pytest.fixture
def auth_store() -> SessionStore:
    """Proporciona un gestor de sesiones independiente."""
    return SessionStore(ttl_seconds=28_800)


@pytest.fixture
def dummy_hash() -> str:
    """Genera un hash auxiliar con coste reducido."""
    return create_dummy_password_hash(TEST_ROUNDS)


@pytest.fixture
def registered_user(clean_db: Engine) -> UserOut:
    """Registra un usuario en PostgreSQL de pruebas."""
    return auth_service.register_user(
        clean_db,
        RegisterIn(
            email=EMAIL,
            password=PASSWORD,
        ),
        rounds=TEST_ROUNDS,
    )


def _login(
    engine: Engine,
    store: SessionStore,
    dummy_hash: str,
    *,
    email: str = EMAIL,
    password: str = PASSWORD,
) -> LoginOut:
    """Realiza un login utilizando las dependencias de prueba."""
    return auth_service.login_user(
        engine,
        store,
        LoginIn(
            email=email,
            password=password,
        ),
        dummy_password_hash=dummy_hash,
    )


def _password_change() -> PasswordChangeIn:
    """Construye una solicitud válida de cambio de contraseña."""
    return PasswordChangeIn(
        current_password=PASSWORD,
        new_password=NEW_PASSWORD,
    )


# =========================================================
# TRADUCCIÓN DE ERRORES RELACIONALES
# =========================================================


@pytest.mark.parametrize(
    "sqlstate",
    [
        "08001",
        "08003",
        "08006",
        "53300",
        "55P03",
        "57014",
        "57P01",
        "57P02",
        "57P03",
        None,
    ],
)
def test_database_unavailable(sqlstate: str | None) -> None:
    """Identifica errores de disponibilidad de PostgreSQL."""
    error = OperationalError(
        None,
        None,
        DriverError(sqlstate),
    )

    result = auth_service.translate_db_error(error)

    assert result.code == ErrorCode.SERVICE_UNAVAILABLE
    assert "detalle-sensible-ficticio" not in str(result)


def test_database_pool_timeout() -> None:
    """Traduce el agotamiento del pool de conexiones."""
    error = SQLAlchemyTimeoutError("detalle-sensible-ficticio")

    result = auth_service.translate_db_error(error)

    assert result.code == ErrorCode.SERVICE_UNAVAILABLE


def test_database_connection_invalidated() -> None:
    """Identifica una conexión invalidada por SQLAlchemy."""
    error = OperationalError(
        None,
        None,
        DriverError(None),
        connection_invalidated=True,
    )

    result = auth_service.translate_db_error(error)

    assert result.code == ErrorCode.SERVICE_UNAVAILABLE


def test_duplicate_email_error() -> None:
    """Identifica específicamente la unicidad del email."""
    error = IntegrityError(
        None,
        None,
        DriverError("23505", "user_email_unique"),
    )

    result = auth_service.translate_db_error(
        error,
        registering=True,
    )

    assert result.code == ErrorCode.EMAIL_ALREADY_EXISTS


def test_other_unique_constraint() -> None:
    """No confunde otras restricciones con emails duplicados."""
    error = IntegrityError(
        None,
        None,
        DriverError("23505", "another_constraint"),
    )

    result = auth_service.translate_db_error(
        error,
        registering=True,
    )

    assert result.code == ErrorCode.INTERNAL_SERVER_ERROR


def test_duplicate_email_outside_registration() -> None:
    """Limita la traducción de duplicados al registro."""
    error = IntegrityError(
        None,
        None,
        DriverError("23505", "user_email_unique"),
    )

    result = auth_service.translate_db_error(error)

    assert result.code == ErrorCode.INTERNAL_SERVER_ERROR


def test_unexpected_sql_error() -> None:
    """Sanitiza un error SQL inesperado."""
    error = OperationalError(
        None,
        None,
        DriverError("42601"),
    )

    result = auth_service.translate_db_error(error)

    assert result.code == ErrorCode.INTERNAL_SERVER_ERROR
    assert "detalle-sensible-ficticio" not in str(result)


def test_generic_sqlalchemy_error() -> None:
    """Gestiona errores no clasificados de SQLAlchemy."""
    error = SQLAlchemyError("detalle-sensible-ficticio")

    result = auth_service.translate_db_error(error)

    assert result.code == ErrorCode.INTERNAL_SERVER_ERROR


# =========================================================
# REGISTRO DE USUARIOS
# =========================================================


@pytest.mark.integration
def test_register_user(clean_db: Engine) -> None:
    """Registra una cuenta activa con contraseña protegida."""
    result = auth_service.register_user(
        clean_db,
        RegisterIn(
            email="  USUARIO@EXAMPLE.COM  ",
            password=PASSWORD,
        ),
        rounds=TEST_ROUNDS,
    )

    assert result.email == EMAIL
    assert result.is_active is True

    with Session(clean_db) as session:
        user = db.get_user_by_id(session, result.id)

        assert user is not None
        assert user.email == EMAIL
        assert user.password_hash != PASSWORD
        assert user.deleted_at is None
        assert verify_password(PASSWORD, user.password_hash)
        assert db.list_api_keys(session) == []

    assert "password" not in result.model_dump()
    assert "password_hash" not in result.model_dump()
    assert PASSWORD not in result.model_dump_json()


@pytest.mark.integration
def test_register_duplicate_email(
    clean_db: Engine,
    registered_user: UserOut,
) -> None:
    """Rechaza un email previamente registrado."""
    with pytest.raises(ApiError) as exc_info:
        auth_service.register_user(
            clean_db,
            RegisterIn(
                email=EMAIL.upper(),
                password=OTHER_PASSWORD,
            ),
            rounds=TEST_ROUNDS,
        )

    assert exc_info.value.code == ErrorCode.EMAIL_ALREADY_EXISTS

    with Session(clean_db) as session:
        users = db.list_users(session)

        assert len(users) == 1
        assert users[0].id == registered_user.id


@pytest.mark.integration
def test_register_deleted_user_email(
    clean_db: Engine,
    registered_user: UserOut,
) -> None:
    """Conserva la unicidad tras la eliminación lógica."""
    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)

        assert user is not None

        db.delete_user(user)
        session.commit()

    with pytest.raises(ApiError) as exc_info:
        auth_service.register_user(
            clean_db,
            RegisterIn(
                email=EMAIL,
                password=PASSWORD,
            ),
            rounds=TEST_ROUNDS,
        )

    assert exc_info.value.code == ErrorCode.EMAIL_ALREADY_EXISTS


@pytest.mark.integration
def test_concurrent_registration(
    clean_db: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Garantiza que solo se registra una cuenta por email."""
    barrier = Barrier(2, timeout=5)
    original_create_user = db.create_user

    def synchronized_create(
        session: Session,
        user: User,
    ) -> User:
        """Sincroniza ambas operaciones antes del INSERT."""
        result = original_create_user(session, user)
        barrier.wait()

        return result

    monkeypatch.setattr(
        db,
        "create_user",
        synchronized_create,
    )

    def register() -> UserOut | ErrorCode:
        """Intenta registrar la misma dirección de email."""
        try:
            return auth_service.register_user(
                clean_db,
                RegisterIn(
                    email=EMAIL,
                    password=PASSWORD,
                ),
                rounds=TEST_ROUNDS,
            )

        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(register)
        second = pool.submit(register)

        results = [
            first.result(timeout=15),
            second.result(timeout=15),
        ]

    successful = [
        result
        for result in results
        if isinstance(result, UserOut)
    ]

    assert len(successful) == 1
    assert ErrorCode.EMAIL_ALREADY_EXISTS in results

    with Session(clean_db) as session:
        users = db.list_users(session)

        assert len(users) == 1
        assert users[0].id == successful[0].id


# =========================================================
# LOGIN
# =========================================================


@pytest.mark.integration
def test_login_user(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
) -> None:
    """Autentica un usuario activo y crea su sesión."""
    result = _login(
        clean_db,
        auth_store,
        dummy_hash,
    )

    record = auth_store.get(result.session_token)

    assert result.user == registered_user
    assert result.token_type == "Bearer"
    assert result.expires_at == record.expires_at
    assert record.user_id == registered_user.id
    assert PASSWORD not in result.model_dump_json()
    assert result.session_token not in repr(result)


@pytest.mark.integration
def test_login_incorrect_password(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
) -> None:
    """Rechaza una contraseña incorrecta."""
    with pytest.raises(ApiError) as exc_info:
        _login(
            clean_db,
            auth_store,
            dummy_hash,
            password=OTHER_PASSWORD,
        )

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS


@pytest.mark.integration
def test_login_unknown_user(
    clean_db: Engine,
    auth_store: SessionStore,
    dummy_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ejecuta bcrypt aunque el usuario no exista."""
    verifier = Mock(wraps=auth_service.verify_password)

    monkeypatch.setattr(
        auth_service,
        "verify_password",
        verifier,
    )

    with pytest.raises(ApiError) as exc_info:
        _login(
            clean_db,
            auth_store,
            dummy_hash,
        )

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS

    verifier.assert_called_once_with(
        PASSWORD,
        dummy_hash,
    )


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("correct_password", [False, True])
def test_login_inactive_user(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
    deleted: bool,
    correct_password: bool,
) -> None:
    """Protege el estado de las cuentas no habilitadas."""
    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)

        assert user is not None

        if deleted:
            db.delete_user(user)
        else:
            db.set_user_active(user, False)

        session.commit()

    password = PASSWORD if correct_password else OTHER_PASSWORD

    expected = (
        ErrorCode.USER_INACTIVE
        if correct_password
        else ErrorCode.INVALID_CREDENTIALS
    )

    with pytest.raises(ApiError) as exc_info:
        _login(
            clean_db,
            auth_store,
            dummy_hash,
            password=password,
        )

    assert exc_info.value.code == expected


@pytest.mark.integration
def test_login_corrupted_password_hash(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
) -> None:
    """Diferencia la corrupción interna de un login incorrecto."""
    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)

        assert user is not None

        db.update_user_password(user, "hash-corrupto")
        session.commit()

    with pytest.raises(ApiError) as exc_info:
        _login(
            clean_db,
            auth_store,
            dummy_hash,
        )

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR


# =========================================================
# CAMBIO DE CONTRASEÑA
# =========================================================


@pytest.mark.integration
def test_change_password(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
) -> None:
    """Actualiza la contraseña y revoca las sesiones existentes."""
    first = _login(clean_db, auth_store, dummy_hash)
    second = _login(clean_db, auth_store, dummy_hash)

    other_user = auth_service.register_user(
        clean_db,
        RegisterIn(
            email="otro@example.com",
            password=PASSWORD,
        ),
        rounds=TEST_ROUNDS,
    )

    other_token, _ = auth_store.create(other_user.id)

    with Session(clean_db) as session:
        api_key = ApiKey(
            user_id=registered_user.id,
            key_hash="a" * 64,
            role=ApiKeyRole.FREE,
        )

        api_key_id = api_key.id

        db.create_api_key(session, api_key)
        session.commit()

    result = auth_service.change_password(
        clean_db,
        auth_store,
        first.session_token,
        _password_change(),
        rounds=TEST_ROUNDS,
    )

    assert result == registered_user

    for token in (first.session_token, second.session_token):
        with pytest.raises(ApiError) as exc_info:
            auth_store.get(token)

        assert exc_info.value.code == ErrorCode.INVALID_SESSION

    assert auth_store.get(other_token).user_id == other_user.id

    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)
        api_key = db.get_api_key_by_id(session, api_key_id)

        assert user is not None
        assert not verify_password(PASSWORD, user.password_hash)
        assert verify_password(NEW_PASSWORD, user.password_hash)

        assert api_key is not None
        assert api_key.is_active is True
        assert api_key.deleted_at is None

    with pytest.raises(ApiError) as exc_info:
        _login(clean_db, auth_store, dummy_hash)

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS

    new_login = _login(
        clean_db,
        auth_store,
        dummy_hash,
        password=NEW_PASSWORD,
    )

    assert new_login.user.id == registered_user.id


@pytest.mark.integration
def test_change_incorrect_current_password(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
) -> None:
    """Rechaza el cambio si la contraseña actual es incorrecta."""
    login = _login(clean_db, auth_store, dummy_hash)

    with pytest.raises(ApiError) as exc_info:
        auth_service.change_password(
            clean_db,
            auth_store,
            login.session_token,
            PasswordChangeIn(
                current_password=OTHER_PASSWORD,
                new_password=NEW_PASSWORD,
            ),
            rounds=TEST_ROUNDS,
        )

    assert exc_info.value.code == ErrorCode.INVALID_CREDENTIALS

    assert auth_store.get(
        login.session_token,
    ).user_id == registered_user.id

    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)

        assert user is not None
        assert verify_password(PASSWORD, user.password_hash)


@pytest.mark.integration
def test_change_password_revoked_session(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
) -> None:
    """Impide cambiar la contraseña con una sesión revocada."""
    login = _login(clean_db, auth_store, dummy_hash)

    auth_store.revoke(login.session_token)

    with pytest.raises(ApiError) as exc_info:
        auth_service.change_password(
            clean_db,
            auth_store,
            login.session_token,
            _password_change(),
            rounds=TEST_ROUNDS,
        )

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


# =========================================================
# TRANSACCIONES E INVALIDACIÓN CONSERVADORA
# =========================================================


@pytest.mark.integration
def test_password_change_failure_before_commit(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revierte el cambio si falla antes de confirmar."""
    login = _login(clean_db, auth_store, dummy_hash)

    with monkeypatch.context() as patch:
        patch.setattr(
            auth_service,
            "to_user_out",
            Mock(
                side_effect=ApiError(
                    ErrorCode.INTERNAL_SERVER_ERROR,
                ),
            ),
        )

        with pytest.raises(ApiError) as exc_info:
            auth_service.change_password(
                clean_db,
                auth_store,
                login.session_token,
                _password_change(),
                rounds=TEST_ROUNDS,
            )

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR

    assert auth_store.get(
        login.session_token,
    ).user_id == registered_user.id

    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)

        assert user is not None
        assert verify_password(PASSWORD, user.password_hash)


@pytest.mark.integration
def test_password_change_uncertain_commit(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revoca sesiones ante un commit de resultado incierto."""
    first = _login(clean_db, auth_store, dummy_hash)
    second = _login(clean_db, auth_store, dummy_hash)

    original_commit = Session.commit

    def uncertain_commit(session: Session) -> None:
        """Simula la pérdida de confirmación tras el commit."""
        original_commit(session)

        raise OperationalError(
            None,
            None,
            DriverError("08006"),
            connection_invalidated=True,
        )

    with monkeypatch.context() as patch:
        patch.setattr(Session, "commit", uncertain_commit)

        with pytest.raises(ApiError) as exc_info:
            auth_service.change_password(
                clean_db,
                auth_store,
                first.session_token,
                _password_change(),
                rounds=TEST_ROUNDS,
            )

    assert exc_info.value.code == ErrorCode.SERVICE_UNAVAILABLE

    for token in (first.session_token, second.session_token):
        with pytest.raises(ApiError) as exc_info:
            auth_store.get(token)

        assert exc_info.value.code == ErrorCode.INVALID_SESSION

    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)

        assert user is not None
        assert verify_password(NEW_PASSWORD, user.password_hash)


@pytest.mark.integration
def test_login_output_failure_revokes_session(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revoca una sesión cuyo resultado no puede entregarse."""
    original_create = auth_store.create
    generated_tokens: list[str] = []

    def capture_session(user_id: UUID) -> tuple[str, SessionRecord]:
        """Captura el token para comprobar su revocación."""
        token, record = original_create(user_id)
        generated_tokens.append(token)

        return token, record

    monkeypatch.setattr(
        auth_store,
        "create",
        capture_session,
    )

    monkeypatch.setattr(
        auth_service,
        "LoginOut",
        Mock(side_effect=ValueError("detalle-sensible-ficticio")),
    )

    with pytest.raises(ApiError) as exc_info:
        _login(clean_db, auth_store, dummy_hash)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR
    assert len(generated_tokens) == 1

    with pytest.raises(ApiError) as exc_info:
        auth_store.get(generated_tokens[0])

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


# =========================================================
# CONCURRENCIA DE AUTENTICACIÓN
# =========================================================


@pytest.mark.integration
def test_concurrent_login_and_password_change(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    dummy_hash: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coordina un login concurrente con el cambio de clave."""
    previous_login = _login(
        clean_db,
        auth_store,
        dummy_hash,
    )

    login_locked = Event()
    change_started = Event()
    continue_login = Event()

    original_by_email = db.get_user_by_email
    original_by_id = db.get_user_by_id

    def locked_lookup(
        session: Session,
        email: str,
        *,
        for_update: bool = False,
    ) -> User | None:
        """Detiene el login tras adquirir el bloqueo relacional."""
        user = original_by_email(
            session,
            email,
            for_update=for_update,
        )

        if for_update:
            login_locked.set()

            assert continue_login.wait(timeout=5)

        return user

    def change_lookup(
        session: Session,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> User | None:
        """Comunica que el cambio intenta bloquear al usuario."""
        if for_update:
            change_started.set()

        return original_by_id(
            session,
            user_id,
            for_update=for_update,
        )

    monkeypatch.setattr(
        db,
        "get_user_by_email",
        locked_lookup,
    )

    monkeypatch.setattr(
        db,
        "get_user_by_id",
        change_lookup,
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        login_future = pool.submit(
            _login,
            clean_db,
            auth_store,
            dummy_hash,
        )

        try:
            assert login_locked.wait(timeout=5)

            change_future = pool.submit(
                auth_service.change_password,
                clean_db,
                auth_store,
                previous_login.session_token,
                _password_change(),
                rounds=TEST_ROUNDS,
            )

            assert change_started.wait(timeout=5)

        finally:
            continue_login.set()

        concurrent_login = login_future.result(timeout=15)
        changed_user = change_future.result(timeout=15)

    assert changed_user.id == registered_user.id

    for token in (
        previous_login.session_token,
        concurrent_login.session_token,
    ):
        with pytest.raises(ApiError) as exc_info:
            auth_store.get(token)

        assert exc_info.value.code == ErrorCode.INVALID_SESSION