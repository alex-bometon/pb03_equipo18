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
import api.security as security
from api.config import ApiSettings
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.schemas import (
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    IssuableApiKeyRole,
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
    hash_secret,
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


# =========================================================
# RECURSOS PARA EMISIÓN DE API KEYS
# =========================================================


@pytest.fixture
def issue_settings(
    registered_user: UserOut,
) -> ApiSettings:
    """Autoriza al usuario de pruebas para emitir claves User."""
    return ApiSettings(
        USER_TIER_ALLOWED_USER_IDS=frozenset({
            registered_user.id,
        }),
    )


@pytest.fixture
def registered_token(
    auth_store: SessionStore,
    registered_user: UserOut,
) -> str:
    """Proporciona una sesión válida para las pruebas."""
    token, _ = auth_store.create(registered_user.id)

    return token


def _issue_registered(
    engine: Engine,
    store: SessionStore,
    token: str,
    settings: ApiSettings,
    *,
    role: IssuableApiKeyRole = ApiKeyRole.FREE,
) -> ApiKeyCreatedOut:
    """Emite una clave registrada con dependencias controladas."""
    return auth_service.issue_user_api_key(
        engine,
        store,
        token,
        ApiKeyCreateIn(role=role),
        settings=settings,
    )

# =========================================================
# VALIDACIÓN PREVIA DE SESIONES
# =========================================================


def test_issue_invalid_session(
    auth_store: SessionStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rechaza una sesión desconocida antes de consultar SQL."""
    session_factory = Mock()

    monkeypatch.setattr(
        auth_service,
        "Session",
        session_factory,
    )

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            Mock(spec=Engine),
            auth_store,
            "token-desconocido",
            ApiSettings(),
        )

    assert exc_info.value.code == ErrorCode.INVALID_SESSION

    session_factory.assert_not_called()


def test_issue_expired_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rechaza una sesión caducada antes de consultar SQL."""
    clock = Mock(return_value=1000.0)

    monkeypatch.setattr(security, "monotonic", clock)

    store = SessionStore(ttl_seconds=10)
    token, _ = store.create(UUID(int=1))

    clock.return_value = 1010.0

    session_factory = Mock()

    monkeypatch.setattr(
        auth_service,
        "Session",
        session_factory,
    )

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            Mock(spec=Engine),
            store,
            token,
            ApiSettings(),
        )

    assert exc_info.value.code == ErrorCode.SESSION_EXPIRED

    session_factory.assert_not_called()


# =========================================================
# EMISIÓN ANÓNIMA
# =========================================================


@pytest.mark.integration
def test_issue_anonymous_api_key(
    clean_db: Engine,
) -> None:
    """Emite una clave Free sin propietario registrado."""
    result = auth_service.issue_anonymous_api_key(clean_db)

    assert isinstance(result, ApiKeyCreatedOut)
    assert result.role == ApiKeyRole.FREE
    assert result.user_id is None
    assert result.is_active is True
    assert result.deleted_at is None
    assert result.last_used_at is None
    assert len(result.api_key) == 43
    assert str(result.id) != result.api_key

    with Session(clean_db) as session:
        stored = db.get_api_key_by_id(session, result.id)

        assert stored is not None
        assert stored.user_id is None
        assert stored.key_hash == hash_secret(result.api_key)
        assert stored.key_hash != result.api_key
        assert stored.role == ApiKeyRole.FREE
        assert db.list_users(session) == []

        public = auth_service.to_api_key_out(stored)

        assert "key_hash" not in public.model_dump()
        assert "api_key" not in public.model_dump()
        assert result.api_key not in public.model_dump_json()

    assert "key_hash" not in result.model_dump()
    assert result.api_key not in repr(result)


@pytest.mark.integration
def test_distinct_anonymous_api_keys(
    clean_db: Engine,
) -> None:
    """Genera credenciales anónimas independientes."""
    first = auth_service.issue_anonymous_api_key(clean_db)
    second = auth_service.issue_anonymous_api_key(clean_db)

    assert first.id != second.id
    assert first.api_key != second.api_key

    with Session(clean_db) as session:
        assert len(db.list_api_keys(session)) == 2


# =========================================================
# EMISIÓN REGISTRADA
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    "role",
    [ApiKeyRole.FREE, ApiKeyRole.USER],
)
def test_issue_registered_api_key(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
    role: IssuableApiKeyRole,
) -> None:
    """Asocia la clave al propietario de la sesión."""
    result = _issue_registered(
        clean_db,
        auth_store,
        registered_token,
        issue_settings,
        role=role,
    )

    assert result.user_id == registered_user.id
    assert result.role == role
    assert result.is_active is True

    with Session(clean_db) as session:
        stored = db.get_api_key_by_id(session, result.id)

        assert stored is not None
        assert stored.user_id == registered_user.id
        assert stored.role == role
        assert stored.key_hash == hash_secret(result.api_key)

    assert auth_store.get(
        registered_token,
    ).user_id == registered_user.id


@pytest.mark.integration
def test_issue_free_without_allowlist(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
) -> None:
    """Permite emitir claves Free sin autorización especial."""
    result = _issue_registered(
        clean_db,
        auth_store,
        registered_token,
        ApiSettings(),
    )

    assert result.role == ApiKeyRole.FREE
    assert result.user_id == registered_user.id


@pytest.mark.integration
def test_issue_user_not_authorized(
    clean_db: Engine,
    auth_store: SessionStore,
    registered_token: str,
) -> None:
    """Rechaza la emisión User sin autorización específica."""
    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            ApiSettings(),
            role=ApiKeyRole.USER,
        )

    assert exc_info.value.code == (
        ErrorCode.USER_TIER_NOT_AUTHORIZED
    )

    with Session(clean_db) as session:
        assert db.list_api_keys(session) == []


@pytest.mark.integration
def test_allowlist_removal(
    clean_db: Engine,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
) -> None:
    """Impide nuevas emisiones sin revocar claves existentes."""
    existing = _issue_registered(
        clean_db,
        auth_store,
        registered_token,
        issue_settings,
        role=ApiKeyRole.USER,
    )

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            ApiSettings(),
            role=ApiKeyRole.USER,
        )

    assert exc_info.value.code == (
        ErrorCode.USER_TIER_NOT_AUTHORIZED
    )

    with Session(clean_db) as session:
        stored = db.get_api_key_by_id(session, existing.id)

        assert stored is not None
        assert stored.is_active is True
        assert stored.deleted_at is None


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_issue_inactive_user(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
    deleted: bool,
) -> None:
    """Impide emitir claves para cuentas no habilitadas."""
    with Session(clean_db) as session:
        user = db.get_user_by_id(session, registered_user.id)

        assert user is not None

        if deleted:
            db.delete_user(user)
        else:
            db.set_user_active(user, False)

        session.commit()

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            issue_settings,
        )

    assert exc_info.value.code == ErrorCode.USER_INACTIVE

    with Session(clean_db) as session:
        assert db.list_api_keys(session) == []


# =========================================================
# LÍMITES DE CLAVES ACTIVAS
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("role", "maximum"),
    [
        (ApiKeyRole.FREE, 1),
        (ApiKeyRole.USER, 5),
    ],
)
def test_active_key_limit(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
    role: IssuableApiKeyRole,
    maximum: int,
) -> None:
    """Impide superar el máximo de claves activas por rol."""
    for _ in range(maximum):
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            issue_settings,
            role=role,
        )

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            issue_settings,
            role=role,
        )

    assert exc_info.value.code == ErrorCode.API_KEY_LIMIT_REACHED

    with Session(clean_db) as session:
        assert db.count_active_api_keys(
            session,
            registered_user.id,
            role,
        ) == maximum


@pytest.mark.integration
def test_configurable_active_key_limit(
    clean_db: Engine,
    auth_store: SessionStore,
    registered_token: str,
) -> None:
    """Respeta los límites establecidos mediante configuración."""
    settings = ApiSettings(FREE_MAX_ACTIVE_KEYS=2)

    for _ in range(2):
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            settings,
        )

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            settings,
        )

    assert exc_info.value.code == ErrorCode.API_KEY_LIMIT_REACHED


@pytest.mark.integration
def test_independent_role_limits(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
) -> None:
    """Mantiene límites independientes para Free y User."""
    _issue_registered(
        clean_db,
        auth_store,
        registered_token,
        issue_settings,
    )

    for _ in range(5):
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            issue_settings,
            role=ApiKeyRole.USER,
        )

    with Session(clean_db) as session:
        assert db.count_active_api_keys(
            session,
            registered_user.id,
            ApiKeyRole.FREE,
        ) == 1

        assert db.count_active_api_keys(
            session,
            registered_user.id,
            ApiKeyRole.USER,
        ) == 5


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_inactive_key_frees_capacity(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
    deleted: bool,
) -> None:
    """Excluye claves desactivadas y eliminadas del límite."""
    first = _issue_registered(
        clean_db,
        auth_store,
        registered_token,
        issue_settings,
    )

    with Session(clean_db) as session:
        stored = db.get_api_key_by_id(session, first.id)

        assert stored is not None

        if deleted:
            db.delete_api_key(stored)
        else:
            db.set_api_key_active(stored, False)

        session.commit()

    second = _issue_registered(
        clean_db,
        auth_store,
        registered_token,
        issue_settings,
    )

    assert first.id != second.id

    with Session(clean_db) as session:
        assert len(
            db.list_user_api_keys(
                session,
                registered_user.id,
            )
        ) == 2

        assert db.count_active_api_keys(
            session,
            registered_user.id,
            ApiKeyRole.FREE,
        ) == 1


# =========================================================
# COLISIONES Y TRANSACCIONES
# =========================================================


@pytest.mark.integration
def test_api_key_collision(
    clean_db: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Impide sobrescribir una clave ante una colisión."""
    first = auth_service.issue_anonymous_api_key(clean_db)

    generator = Mock(return_value=first.api_key)

    monkeypatch.setattr(
        auth_service,
        "generate_secret",
        generator,
    )

    with pytest.raises(ApiError) as exc_info:
        auth_service.issue_anonymous_api_key(clean_db)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR
    assert first.api_key not in str(exc_info.value)

    generator.assert_called_once_with()

    with Session(clean_db) as session:
        keys = db.list_api_keys(session)

        assert len(keys) == 1
        assert keys[0].id == first.id
        assert keys[0].key_hash == hash_secret(first.api_key)


@pytest.mark.integration
def test_api_key_output_failure(
    clean_db: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revierte la emisión si no puede validar su resultado."""
    secret = "secreto-ficticio-de-prueba"

    monkeypatch.setattr(
        auth_service,
        "generate_secret",
        Mock(return_value=secret),
    )

    invalid_output = SimpleNamespace(
        model_dump=lambda: {},
    )

    monkeypatch.setattr(
        auth_service,
        "to_api_key_out",
        Mock(return_value=invalid_output),
    )

    with pytest.raises(ApiError) as exc_info:
        auth_service.issue_anonymous_api_key(clean_db)

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR
    assert secret not in str(exc_info.value)

    with Session(clean_db) as session:
        assert db.list_api_keys(session) == []


@pytest.mark.integration
@pytest.mark.parametrize("committed", [False, True])
def test_api_key_uncertain_commit(
    clean_db: Engine,
    monkeypatch: pytest.MonkeyPatch,
    committed: bool,
) -> None:
    """No entrega ni repite una emisión de resultado incierto."""
    original_commit = Session.commit
    attempts = 0
    secret = "secreto-ficticio-de-prueba"

    generator = Mock(return_value=secret)

    def uncertain_commit(session: Session) -> None:
        """Simula un fallo con resultado relacional incierto."""
        nonlocal attempts

        attempts += 1

        if committed:
            original_commit(session)

        raise OperationalError(
            None,
            None,
            DriverError("08006"),
            connection_invalidated=True,
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            auth_service,
            "generate_secret",
            generator,
        )

        patch.setattr(Session, "commit", uncertain_commit)

        with pytest.raises(ApiError) as exc_info:
            auth_service.issue_anonymous_api_key(clean_db)

    assert exc_info.value.code == ErrorCode.SERVICE_UNAVAILABLE
    assert secret not in str(exc_info.value)
    assert attempts == 1

    generator.assert_called_once_with()

    with Session(clean_db) as session:
        keys = db.list_api_keys(session)

        if committed:
            assert len(keys) == 1
            assert keys[0].key_hash == hash_secret(secret)
        else:
            assert keys == []


# =========================================================
# REVOCACIÓN DURANTE LA EMISIÓN
# =========================================================


@pytest.mark.integration
def test_session_revoked_during_key_issue(
    clean_db: Engine,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Detecta una revocación anterior a la escritura."""
    original_count = db.count_active_api_keys

    def count_and_revoke(
        session: Session,
        user_id: UUID,
        role: ApiKeyRole,
    ) -> int:
        """Revoca la sesión tras comprobar las claves activas."""
        count = original_count(
            session,
            user_id,
            role,
        )

        auth_store.revoke(registered_token)

        return count

    monkeypatch.setattr(
        db,
        "count_active_api_keys",
        count_and_revoke,
    )

    generator = Mock()

    monkeypatch.setattr(
        auth_service,
        "generate_secret",
        generator,
    )

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            issue_settings,
        )

    assert exc_info.value.code == ErrorCode.INVALID_SESSION

    generator.assert_not_called()

    with Session(clean_db) as session:
        assert db.list_api_keys(session) == []


# =========================================================
# CONCURRENCIA DE EMISIÓN
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("role", "maximum"),
    [
        (ApiKeyRole.FREE, 1),
        (ApiKeyRole.USER, 5),
    ],
)
def test_concurrent_api_key_issue(
    clean_db: Engine,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    issue_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
    role: IssuableApiKeyRole,
    maximum: int,
) -> None:
    """Impide superar el límite mediante emisiones concurrentes."""
    for _ in range(maximum - 1):
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            issue_settings,
            role=role,
        )

    barrier = Barrier(2, timeout=5)
    original_lookup = db.get_user_by_id

    def synchronized_lookup(
        session: Session,
        user_id: UUID,
        *,
        for_update: bool = False,
    ) -> User | None:
        """Sincroniza las peticiones antes del bloqueo SQL."""
        if for_update:
            barrier.wait()

        return original_lookup(
            session,
            user_id,
            for_update=for_update,
        )

    monkeypatch.setattr(
        db,
        "get_user_by_id",
        synchronized_lookup,
    )

    def issue() -> ApiKeyCreatedOut | ErrorCode:
        """Intenta ocupar la última plaza disponible."""
        try:
            return _issue_registered(
                clean_db,
                auth_store,
                registered_token,
                issue_settings,
                role=role,
            )

        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(issue)
        second = pool.submit(issue)

        results = [
            first.result(timeout=15),
            second.result(timeout=15),
        ]

    successful = [
        result
        for result in results
        if isinstance(result, ApiKeyCreatedOut)
    ]

    assert len(successful) == 1
    assert ErrorCode.API_KEY_LIMIT_REACHED in results

    with Session(clean_db) as session:
        assert db.count_active_api_keys(
            session,
            registered_user.id,
            role,
        ) == maximum


# =========================================================
# APROVISIONAMIENTO ADMINISTRATIVO
# =========================================================


ADMIN_TEST_EMAIL = "admin-ficticio@example.com"


@pytest.fixture
def admin_settings() -> ApiSettings:
    """Genera credenciales administrativas exclusivas de pruebas."""
    return ApiSettings(
        ADMIN_EMAIL=ADMIN_TEST_EMAIL,
        ADMIN_PASSWORD=security.generate_secret(),
        API_KEY=security.generate_secret(),
        BCRYPT_ROUNDS=TEST_ROUNDS,
    )

@pytest.mark.integration
def test_admin_bootstrap(
    clean_db: Engine,
    admin_settings: ApiSettings,
) -> None:
    """Crea una cuenta y una credencial administrativa."""
    result = auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    assert result is None

    assert admin_settings.ADMIN_PASSWORD is not None
    assert admin_settings.API_KEY is not None

    password = admin_settings.ADMIN_PASSWORD.get_secret_value()
    secret = admin_settings.API_KEY.get_secret_value()

    with Session(clean_db) as session:
        users = db.list_users(session)
        keys = db.list_api_keys(session)

        assert len(users) == 1
        assert len(keys) == 1

        user = users[0]
        api_key = keys[0]

        assert user.email == ADMIN_TEST_EMAIL
        assert user.is_active is True
        assert user.deleted_at is None
        assert user.password_hash != password
        assert verify_password(password, user.password_hash)

        assert api_key.role == ApiKeyRole.ADMIN
        assert api_key.user_id == user.id
        assert api_key.is_active is True
        assert api_key.deleted_at is None
        assert api_key.key_hash == hash_secret(secret)
        assert api_key.key_hash != secret


@pytest.mark.integration
def test_admin_bootstrap_idempotent(
    clean_db: Engine,
    admin_settings: ApiSettings,
) -> None:
    """Conserva los registros originales entre reinicios."""
    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    with Session(clean_db) as session:
        user = db.list_users(session)[0]
        api_key = db.list_api_keys(session)[0]

        user_before = user.model_dump()
        key_before = api_key.model_dump()

    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    with Session(clean_db) as session:
        users = db.list_users(session)
        keys = db.list_api_keys(session)

        assert len(users) == 1
        assert len(keys) == 1

        assert users[0].model_dump() == user_before
        assert keys[0].model_dump() == key_before


@pytest.mark.parametrize(
    "field",
    [
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "API_KEY",
    ],
)
def test_admin_bootstrap_missing_configuration(
    admin_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    """Rechaza configuraciones administrativas incompletas."""
    settings = admin_settings.model_copy(
        update={field: None},
    )

    session_factory = Mock()

    monkeypatch.setattr(
        auth_service,
        "Session",
        session_factory,
    )

    with pytest.raises(ApiError) as exc_info:
        auth_service.bootstrap_admin_api_key(
            Mock(spec=Engine),
            settings,
        )

    assert exc_info.value.code == ErrorCode.SERVICE_NOT_CONFIGURED

    session_factory.assert_not_called()


@pytest.mark.integration
def test_admin_bootstrap_existing_ordinary_user(
    clean_db: Engine,
    admin_settings: ApiSettings,
) -> None:
    """Impide convertir una cuenta ordinaria en administrativa."""
    assert admin_settings.ADMIN_PASSWORD is not None

    password = admin_settings.ADMIN_PASSWORD.get_secret_value()

    ordinary_user = auth_service.register_user(
        clean_db,
        RegisterIn(
            email=ADMIN_TEST_EMAIL,
            password=password,
        ),
        rounds=TEST_ROUNDS,
    )

    with pytest.raises(
        RuntimeError,
        match="La cuenta existente no es administrativa",
    ):
        auth_service.bootstrap_admin_api_key(
            clean_db,
            admin_settings,
        )

    with Session(clean_db) as session:
        users = db.list_users(session)

        assert len(users) == 1
        assert users[0].id == ordinary_user.id
        assert db.list_api_keys(session) == []


@pytest.mark.integration
@pytest.mark.parametrize(
    "role",
    [
        ApiKeyRole.FREE,
        ApiKeyRole.USER,
    ],
)
def test_admin_bootstrap_key_role_conflict(
    clean_db: Engine,
    admin_settings: ApiSettings,
    role: ApiKeyRole,
) -> None:
    """Impide reutilizar una credencial con otro rol."""
    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    with Session(clean_db) as session:
        api_key = db.list_api_keys(session)[0]
        api_key.role = role

        session.commit()

    with pytest.raises(
        RuntimeError,
        match="Conflicto de credencial administrativa",
    ):
        auth_service.bootstrap_admin_api_key(
            clean_db,
            admin_settings,
        )

    with Session(clean_db) as session:
        keys = db.list_api_keys(session)

        assert len(keys) == 1
        assert keys[0].role == role


@pytest.mark.integration
def test_admin_bootstrap_key_owner_conflict(
    clean_db: Engine,
    admin_settings: ApiSettings,
    registered_user: UserOut,
) -> None:
    """Impide reasignar una credencial de otro propietario."""
    assert admin_settings.API_KEY is not None

    secret = admin_settings.API_KEY.get_secret_value()

    with Session(clean_db) as session:
        api_key = ApiKey(
            user_id=registered_user.id,
            key_hash=hash_secret(secret),
            role=ApiKeyRole.ADMIN,
        )

        db.create_api_key(session, api_key)
        session.commit()

    with pytest.raises(
        RuntimeError,
        match="Conflicto de credencial administrativa",
    ):
        auth_service.bootstrap_admin_api_key(
            clean_db,
            admin_settings,
        )

    with Session(clean_db) as session:
        users = db.list_users(session)
        keys = db.list_api_keys(session)

        assert len(users) == 1
        assert len(keys) == 1
        assert keys[0].user_id == registered_user.id


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_admin_bootstrap_inactive_user(
    clean_db: Engine,
    admin_settings: ApiSettings,
    deleted: bool,
) -> None:
    """No reactiva cuentas administrativas deshabilitadas."""
    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    with Session(clean_db) as session:
        user = db.list_users(session)[0]

        if deleted:
            db.delete_user(user)
        else:
            db.set_user_active(user, False)

        session.commit()

    with pytest.raises(ApiError) as exc_info:
        auth_service.bootstrap_admin_api_key(
            clean_db,
            admin_settings,
        )

    assert exc_info.value.code == ErrorCode.USER_INACTIVE

    with Session(clean_db) as session:
        users = db.list_users(session)

        assert len(users) == 1
        assert users[0].is_active is False
        assert (users[0].deleted_at is not None) == deleted


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_admin_bootstrap_inactive_key(
    clean_db: Engine,
    admin_settings: ApiSettings,
    deleted: bool,
) -> None:
    """No reactiva credenciales administrativas deshabilitadas."""
    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    with Session(clean_db) as session:
        api_key = db.list_api_keys(session)[0]

        if deleted:
            db.delete_api_key(api_key)
        else:
            db.set_api_key_active(api_key, False)

        session.commit()

    with pytest.raises(
        RuntimeError,
        match="La credencial administrativa no está activa",
    ):
        auth_service.bootstrap_admin_api_key(
            clean_db,
            admin_settings,
        )

    with Session(clean_db) as session:
        keys = db.list_api_keys(session)

        assert len(keys) == 1
        assert keys[0].is_active is False
        assert (keys[0].deleted_at is not None) == deleted


@pytest.mark.integration
@pytest.mark.parametrize("revoked", [False, True])
def test_admin_bootstrap_key_rotation(
    clean_db: Engine,
    admin_settings: ApiSettings,
    revoked: bool,
) -> None:
    """Permite sustituir una credencial mediante el entorno."""
    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    with Session(clean_db) as session:
        original = db.list_api_keys(session)[0]

        original_id = original.id
        owner_id = original.user_id

        if revoked:
            db.set_api_key_active(original, False)

        session.commit()

    new_secret = security.generate_secret()

    assert admin_settings.ADMIN_PASSWORD is not None

    new_settings = ApiSettings(
        ADMIN_EMAIL=ADMIN_TEST_EMAIL,
        ADMIN_PASSWORD=(
            admin_settings.ADMIN_PASSWORD.get_secret_value()
        ),
        API_KEY=new_secret,
        BCRYPT_ROUNDS=TEST_ROUNDS,
    )

    auth_service.bootstrap_admin_api_key(
        clean_db,
        new_settings,
    )

    with Session(clean_db) as session:
        original = db.get_api_key_by_id(
            session,
            original_id,
        )

        replacement = db.get_api_key_by_hash(
            session,
            hash_secret(new_secret),
        )

        assert original is not None
        assert replacement is not None

        assert len(db.list_users(session)) == 1
        assert len(db.list_api_keys(session)) == 2

        assert original.is_active == (not revoked)
        assert replacement.id != original_id
        assert replacement.user_id == owner_id
        assert replacement.role == ApiKeyRole.ADMIN
        assert replacement.is_active is True


@pytest.mark.integration
def test_admin_password_synchronization(
    clean_db: Engine,
    admin_settings: ApiSettings,
    auth_store: SessionStore,
    dummy_hash: str,
) -> None:
    """Exige sincronizar la contraseña con el secreto del entorno."""
    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    assert admin_settings.ADMIN_PASSWORD is not None
    assert admin_settings.API_KEY is not None

    old_password = (
        admin_settings.ADMIN_PASSWORD.get_secret_value()
    )

    new_password = security.generate_secret()

    login = _login(
        clean_db,
        auth_store,
        dummy_hash,
        email=ADMIN_TEST_EMAIL,
        password=old_password,
    )

    auth_service.change_password(
        clean_db,
        auth_store,
        login.session_token,
        PasswordChangeIn(
            current_password=old_password,
            new_password=new_password,
        ),
        rounds=TEST_ROUNDS,
    )

    with pytest.raises(
        RuntimeError,
        match="Contraseña administrativa incoherente",
    ):
        auth_service.bootstrap_admin_api_key(
            clean_db,
            admin_settings,
        )

    synchronized_settings = ApiSettings(
        ADMIN_EMAIL=ADMIN_TEST_EMAIL,
        ADMIN_PASSWORD=new_password,
        API_KEY=admin_settings.API_KEY.get_secret_value(),
        BCRYPT_ROUNDS=TEST_ROUNDS,
    )

    auth_service.bootstrap_admin_api_key(
        clean_db,
        synchronized_settings,
    )

    with Session(clean_db) as session:
        user = db.list_users(session)[0]

        assert verify_password(
            new_password,
            user.password_hash,
        )

        assert not verify_password(
            old_password,
            user.password_hash,
        )

        assert len(db.list_users(session)) == 1
        assert len(db.list_api_keys(session)) == 1


@pytest.mark.integration
def test_admin_bootstrap_rollback(
    clean_db: Engine,
    admin_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revierte la cuenta si falla la creación de su clave."""
    monkeypatch.setattr(
        db,
        "create_api_key",
        Mock(
            side_effect=IntegrityError(
                None,
                None,
                DriverError(
                    "23505",
                    "api_key_hash_unique",
                ),
            ),
        ),
    )

    with pytest.raises(ApiError) as exc_info:
        auth_service.bootstrap_admin_api_key(
            clean_db,
            admin_settings,
        )

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR

    with Session(clean_db) as session:
        assert db.list_users(session) == []
        assert db.list_api_keys(session) == []