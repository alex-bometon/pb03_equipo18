"""Pruebas del servicio de autenticación de usuarios."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

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
from api.request_context import AuthContext
from api.schemas import (
    ActiveStatusIn,
    AdminApiKeyCreateIn,
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


# =========================================================
# INFRAESTRUCTURA DE ADMINISTRACIÓN
# =========================================================


@pytest.fixture
def admin_context(
    clean_db: Engine,
    admin_settings: ApiSettings,
) -> AuthContext:
    """Aprovisiona un administrador exclusivo de pruebas."""
    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )

    assert admin_settings.API_KEY is not None

    key_hash = hash_secret(
        admin_settings.API_KEY.get_secret_value(),
    )

    with Session(clean_db) as session:
        api_key = db.get_api_key_by_hash(
            session,
            key_hash,
        )

        assert api_key is not None
        assert api_key.user_id is not None

        return AuthContext(
            user_id=api_key.user_id,
            api_key_id=api_key.id,
            role=api_key.role,
        )


def _admin_issue(
    engine: Engine,
    context: AuthContext,
    settings: ApiSettings,
    user_id: UUID | None,
    *,
    role: IssuableApiKeyRole = ApiKeyRole.FREE,
) -> ApiKeyCreatedOut:
    """Emite una credencial mediante el servicio administrativo."""
    return auth_service.issue_admin_api_key(
        engine,
        context,
        AdminApiKeyCreateIn(
            role=role,
            user_id=user_id,
        ),
        settings=settings,
    )


def _assert_invalid_session(
    store: SessionStore,
    token: str,
) -> None:
    """Comprueba que una sesión ha sido invalidada."""
    with pytest.raises(ApiError) as exc_info:
        store.get(token)

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


# =========================================================
# CONSULTA DE CUENTA Y CIERRE DE SESIÓN
# =========================================================


@pytest.mark.integration
def test_get_user_profile(
    clean_db: Engine,
    auth_store: SessionStore,
    registered_user: UserOut,
    registered_token: str,
) -> None:
    """Recupera únicamente los datos públicos de la cuenta."""
    profile = auth_service.get_user_profile(
        clean_db,
        auth_store,
        registered_token,
    )

    assert profile == registered_user
    assert profile.deleted_at is None

    assert "password_hash" not in profile.model_dump()


@pytest.mark.integration
def test_logout_preserves_other_credentials(
    clean_db: Engine,
    auth_store: SessionStore,
    registered_user: UserOut,
    registered_token: str,
    issue_settings: ApiSettings,
) -> None:
    """Invalida únicamente la sesión utilizada para salir."""
    second_token, _ = auth_store.create(registered_user.id)

    api_key = _issue_registered(
        clean_db,
        auth_store,
        second_token,
        issue_settings,
    )

    auth_service.logout_user(
        clean_db,
        auth_store,
        registered_token,
    )

    _assert_invalid_session(auth_store, registered_token)

    assert auth_store.get(second_token).user_id == (
        registered_user.id
    )

    with Session(clean_db) as session:
        key = db.get_api_key_by_id(session, api_key.id)
        user = db.get_user_by_id(
            session,
            registered_user.id,
        )

        assert key is not None
        assert key.is_active is True
        assert user is not None
        assert user.is_active is True


@pytest.mark.parametrize(
    "operation",
    [
        auth_service.get_user_profile,
        auth_service.logout_user,
    ],
)
def test_account_invalid_session(
    auth_store: SessionStore,
    operation,
) -> None:
    """Rechaza las operaciones con un token desconocido."""
    with pytest.raises(ApiError) as exc_info:
        operation(
            Mock(spec=Engine),
            auth_store,
            security.generate_secret(),
        )

    assert exc_info.value.code == ErrorCode.INVALID_SESSION


# =========================================================
# CONSULTAS ADMINISTRATIVAS
# =========================================================


@pytest.mark.integration
def test_admin_user_queries(
    clean_db: Engine,
    admin_context: AuthContext,
    registered_user: UserOut,
) -> None:
    """Recupera todos los usuarios sin revelar hashes."""
    users = auth_service.list_admin_users(
        clean_db,
        admin_context,
    )

    assert {user.id for user in users} == {
        admin_context.user_id,
        registered_user.id,
    }

    user = auth_service.get_admin_user(
        clean_db,
        admin_context,
        registered_user.id,
    )

    assert user == registered_user
    assert "password_hash" not in user.model_dump()


@pytest.mark.integration
def test_admin_key_queries(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
) -> None:
    """Recupera todas las claves sin revelar credenciales."""
    created = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        registered_user.id,
    )

    keys = auth_service.list_admin_api_keys(
        clean_db,
        admin_context,
    )

    assert {key.id for key in keys} == {
        admin_context.api_key_id,
        created.id,
    }

    key = auth_service.get_admin_api_key(
        clean_db,
        admin_context,
        created.id,
    )

    assert key.id == created.id
    assert "key_hash" not in key.model_dump()
    assert "api_key" not in key.model_dump()
    assert created.api_key not in key.model_dump_json()


@pytest.mark.parametrize(
    "role",
    [None, ApiKeyRole.FREE, ApiKeyRole.USER],
)
def test_admin_queries_require_admin(
    role: ApiKeyRole | None,
) -> None:
    """Rechaza identidades sin autorización administrativa."""
    context = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4() if role is not None else None,
        role=role,
    )

    engine = Mock(spec=Engine)

    for operation in (
        auth_service.list_admin_users,
        auth_service.list_admin_api_keys,
    ):
        with pytest.raises(ApiError) as exc_info:
            operation(engine, context)

        assert exc_info.value.code == (
            ErrorCode.INSUFFICIENT_PERMISSIONS
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("operation", "code"),
    [
        (
            auth_service.get_admin_user,
            ErrorCode.USER_NOT_FOUND,
        ),
        (
            auth_service.get_admin_api_key,
            ErrorCode.API_KEY_NOT_FOUND,
        ),
    ],
)
def test_admin_unknown_resource(
    clean_db: Engine,
    admin_context: AuthContext,
    operation,
    code: ErrorCode,
) -> None:
    """Distingue los recursos administrativos inexistentes."""
    with pytest.raises(ApiError) as exc_info:
        operation(
            clean_db,
            admin_context,
            uuid4(),
        )

    assert exc_info.value.code == code


# =========================================================
# EMISIÓN ADMINISTRATIVA
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("role", "registered"),
    [
        (ApiKeyRole.FREE, False),
        (ApiKeyRole.FREE, True),
        (ApiKeyRole.USER, True),
    ],
)
def test_admin_issue_key(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    role: IssuableApiKeyRole,
    registered: bool,
) -> None:
    """Emite las modalidades administrativas autorizadas."""
    user_id = registered_user.id if registered else None

    result = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        user_id,
        role=role,
    )

    assert result.user_id == user_id
    assert result.role == role
    assert result.is_active is True

    with Session(clean_db) as session:
        key = db.get_api_key_by_id(session, result.id)

        assert key is not None
        assert key.key_hash == hash_secret(result.api_key)
        assert key.key_hash != result.api_key


@pytest.mark.integration
def test_admin_issue_does_not_grant_user_tier(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
) -> None:
    """Emitir una clave User no modifica la allowlist."""
    result = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        registered_user.id,
        role=ApiKeyRole.USER,
    )

    assert result.role == ApiKeyRole.USER

    assert registered_user.id not in (
        admin_settings.USER_TIER_ALLOWED_USER_IDS
    )

    with pytest.raises(ApiError) as exc_info:
        _issue_registered(
            clean_db,
            auth_store,
            registered_token,
            admin_settings,
            role=ApiKeyRole.USER,
        )

    assert exc_info.value.code == (
        ErrorCode.USER_TIER_NOT_AUTHORIZED
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("role", "limit"),
    [
        (ApiKeyRole.FREE, 1),
        (ApiKeyRole.USER, 5),
    ],
)
def test_admin_issue_respects_limit(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    role: IssuableApiKeyRole,
    limit: int,
) -> None:
    """Aplica los mismos límites que la emisión ordinaria."""
    for _ in range(limit):
        _admin_issue(
            clean_db,
            admin_context,
            admin_settings,
            registered_user.id,
            role=role,
        )

    with pytest.raises(ApiError) as exc_info:
        _admin_issue(
            clean_db,
            admin_context,
            admin_settings,
            registered_user.id,
            role=role,
        )

    assert exc_info.value.code == ErrorCode.API_KEY_LIMIT_REACHED


@pytest.mark.integration
@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("unknown", ErrorCode.USER_NOT_FOUND),
        ("inactive", ErrorCode.USER_INACTIVE),
        ("deleted", ErrorCode.USER_DELETED),
    ],
)
def test_admin_issue_invalid_recipient(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    state: str,
    code: ErrorCode,
) -> None:
    """Rechaza destinatarios administrativos no autorizados."""
    user_id = registered_user.id

    if state == "unknown":
        user_id = uuid4()

    else:
        with Session(clean_db) as session:
            user = db.get_user_by_id(session, user_id)

            assert user is not None

            if state == "deleted":
                db.delete_user(user)

            else:
                db.set_user_active(user, False)

            session.commit()

    with pytest.raises(ApiError) as exc_info:
        _admin_issue(
            clean_db,
            admin_context,
            admin_settings,
            user_id,
        )

    assert exc_info.value.code == code

    with Session(clean_db) as session:
        assert len(db.list_api_keys(session)) == 1


# =========================================================
# ADMINISTRACIÓN Y REVOCACIÓN DE USUARIOS
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_admin_revoke_user(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    deleted: bool,
) -> None:
    """Revoca las sesiones sin alterar las claves individuales."""
    user_id = registered_user.id

    second_token, _ = auth_store.create(user_id)

    assert admin_context.user_id is not None

    admin_token, _ = auth_store.create(admin_context.user_id)

    free_key = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        user_id,
    )

    user_key = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        user_id,
        role=ApiKeyRole.USER,
    )

    auth_service.update_api_key_status(
        clean_db,
        admin_context,
        user_key.id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    if deleted:
        auth_service.delete_user_account(
            clean_db,
            auth_store,
            admin_context,
            user_id,
            settings=admin_settings,
        )

    else:
        auth_service.update_user_status(
            clean_db,
            auth_store,
            admin_context,
            user_id,
            ActiveStatusIn(is_active=False),
            settings=admin_settings,
        )

    _assert_invalid_session(auth_store, registered_token)
    _assert_invalid_session(auth_store, second_token)

    assert auth_store.get(admin_token).user_id == (
        admin_context.user_id
    )

    result = auth_service.get_admin_user(
        clean_db,
        admin_context,
        user_id,
    )

    assert result.is_active is False
    assert (result.deleted_at is not None) == deleted

    with Session(clean_db) as session:
        free = db.get_api_key_by_id(session, free_key.id)
        user = db.get_api_key_by_id(session, user_key.id)

        assert free is not None
        assert user is not None

        assert free.is_active is True
        assert user.is_active is False

        assert free.deleted_at is None
        assert user.deleted_at is None

        assert free.user_id == user_id
        assert user.user_id == user_id


@pytest.mark.integration
def test_admin_reactivate_user(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    dummy_hash: str,
) -> None:
    """Reactiva la cuenta sin recuperar sesiones invalidadas."""
    user_id = registered_user.id

    key = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        user_id,
    )

    auth_service.update_api_key_status(
        clean_db,
        admin_context,
        key.id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    auth_service.update_user_status(
        clean_db,
        auth_store,
        admin_context,
        user_id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    result = auth_service.update_user_status(
        clean_db,
        auth_store,
        admin_context,
        user_id,
        ActiveStatusIn(is_active=True),
        settings=admin_settings,
    )

    assert result.is_active is True
    assert result.deleted_at is None

    _assert_invalid_session(auth_store, registered_token)

    login = _login(
        clean_db,
        auth_store,
        dummy_hash,
    )

    assert login.user.id == user_id
    assert login.session_token != registered_token

    with Session(clean_db) as session:
        api_key = db.get_api_key_by_id(session, key.id)

        assert api_key is not None
        assert api_key.is_active is False


@pytest.mark.integration
def test_admin_delete_user_idempotent(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
) -> None:
    """Conserva la fecha original de eliminación."""
    user_id = registered_user.id

    for _ in range(2):
        auth_service.delete_user_account(
            clean_db,
            auth_store,
            admin_context,
            user_id,
            settings=admin_settings,
        )

        result = auth_service.get_admin_user(
            clean_db,
            admin_context,
            user_id,
        )

        assert result.deleted_at is not None

        if _ == 0:
            deleted_at = result.deleted_at

        else:
            assert result.deleted_at == deleted_at

    for is_active in (True, False):
        with pytest.raises(ApiError) as exc_info:
            auth_service.update_user_status(
                clean_db,
                auth_store,
                admin_context,
                user_id,
                ActiveStatusIn(is_active=is_active),
                settings=admin_settings,
            )

        assert exc_info.value.code == ErrorCode.USER_DELETED


@pytest.mark.integration
def test_admin_user_status_idempotent(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
) -> None:
    """Permite repetir cambios de estado ya satisfechos."""
    user_id = registered_user.id

    first = auth_service.update_user_status(
        clean_db,
        auth_store,
        admin_context,
        user_id,
        ActiveStatusIn(is_active=True),
        settings=admin_settings,
    )

    assert first == registered_user

    assert auth_store.get(registered_token).user_id == user_id

    inactive = auth_service.update_user_status(
        clean_db,
        auth_store,
        admin_context,
        user_id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    repeated = auth_service.update_user_status(
        clean_db,
        auth_store,
        admin_context,
        user_id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    assert repeated == inactive
    assert repeated.is_active is False

    _assert_invalid_session(auth_store, registered_token)


# =========================================================
# ESTADOS ADMINISTRATIVOS DE API KEYS
# =========================================================


@pytest.mark.integration
def test_admin_key_reactivation_limit(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
) -> None:
    """Impide superar el límite mediante una reactivación."""
    first = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        registered_user.id,
    )

    auth_service.update_api_key_status(
        clean_db,
        admin_context,
        first.id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    second = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        registered_user.id,
    )

    with pytest.raises(ApiError) as exc_info:
        auth_service.update_api_key_status(
            clean_db,
            admin_context,
            first.id,
            ActiveStatusIn(is_active=True),
            settings=admin_settings,
        )

    assert exc_info.value.code == ErrorCode.API_KEY_LIMIT_REACHED

    auth_service.update_api_key_status(
        clean_db,
        admin_context,
        second.id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    result = auth_service.update_api_key_status(
        clean_db,
        admin_context,
        first.id,
        ActiveStatusIn(is_active=True),
        settings=admin_settings,
    )

    repeated = auth_service.update_api_key_status(
        clean_db,
        admin_context,
        first.id,
        ActiveStatusIn(is_active=True),
        settings=admin_settings,
    )

    assert result.is_active is True
    assert repeated == result

    with Session(clean_db) as session:
        key = db.get_api_key_by_id(session, first.id)

        assert key is not None
        assert key.key_hash == hash_secret(first.api_key)

        assert db.count_active_api_keys(
            session,
            registered_user.id,
            ApiKeyRole.FREE,
        ) == 1


@pytest.mark.integration
@pytest.mark.parametrize(
    ("deleted", "code"),
    [
        (False, ErrorCode.USER_INACTIVE),
        (True, ErrorCode.USER_DELETED),
    ],
)
def test_admin_reactivate_key_inactive_owner(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    deleted: bool,
    code: ErrorCode,
) -> None:
    """Exige que el propietario pueda utilizar sus claves."""
    key = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        registered_user.id,
    )

    auth_service.update_api_key_status(
        clean_db,
        admin_context,
        key.id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    with Session(clean_db) as session:
        user = db.get_user_by_id(
            session,
            registered_user.id,
        )

        assert user is not None

        if deleted:
            db.delete_user(user)

        else:
            db.set_user_active(user, False)

        session.commit()

    with pytest.raises(ApiError) as exc_info:
        auth_service.update_api_key_status(
            clean_db,
            admin_context,
            key.id,
            ActiveStatusIn(is_active=True),
            settings=admin_settings,
        )

    assert exc_info.value.code == code


@pytest.mark.integration
def test_admin_delete_key_idempotent(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
) -> None:
    """Elimina una clave sin invalidar la sesión del propietario."""
    created = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        registered_user.id,
    )

    auth_service.delete_api_key_credential(
        clean_db,
        admin_context,
        created.id,
        settings=admin_settings,
    )

    first = auth_service.get_admin_api_key(
        clean_db,
        admin_context,
        created.id,
    )

    auth_service.delete_api_key_credential(
        clean_db,
        admin_context,
        created.id,
        settings=admin_settings,
    )

    second = auth_service.get_admin_api_key(
        clean_db,
        admin_context,
        created.id,
    )

    assert first == second
    assert first.deleted_at is not None
    assert first.is_active is False

    assert auth_store.get(registered_token).user_id == (
        registered_user.id
    )

    for is_active in (True, False):
        with pytest.raises(ApiError) as exc_info:
            auth_service.update_api_key_status(
                clean_db,
                admin_context,
                created.id,
                ActiveStatusIn(is_active=is_active),
                settings=admin_settings,
            )

        assert exc_info.value.code == ErrorCode.API_KEY_DELETED


@pytest.mark.integration
def test_admin_reactivate_anonymous_key(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
) -> None:
    """Reactiva una credencial Free sin propietario registrado."""
    created = _admin_issue(
        clean_db,
        admin_context,
        admin_settings,
        None,
    )

    auth_service.update_api_key_status(
        clean_db,
        admin_context,
        created.id,
        ActiveStatusIn(is_active=False),
        settings=admin_settings,
    )

    result = auth_service.update_api_key_status(
        clean_db,
        admin_context,
        created.id,
        ActiveStatusIn(is_active=True),
        settings=admin_settings,
    )

    assert result.is_active is True
    assert result.user_id is None
    assert result.role == ApiKeyRole.FREE


# =========================================================
# PROTECCIÓN DEL APROVISIONAMIENTO
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    "operation",
    [
        "disable_user",
        "delete_user",
        "disable_key",
        "delete_key",
    ],
)
def test_protect_bootstrap_credentials(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    auth_store: SessionStore,
    operation: str,
) -> None:
    """Impide revocar las credenciales de aprovisionamiento."""
    user_id = admin_context.user_id
    api_key_id = admin_context.api_key_id

    assert user_id is not None
    assert api_key_id is not None

    with pytest.raises(ApiError) as exc_info:
        if operation == "disable_user":
            auth_service.update_user_status(
                clean_db,
                auth_store,
                admin_context,
                user_id,
                ActiveStatusIn(is_active=False),
                settings=admin_settings,
            )

        elif operation == "delete_user":
            auth_service.delete_user_account(
                clean_db,
                auth_store,
                admin_context,
                user_id,
                settings=admin_settings,
            )

        elif operation == "disable_key":
            auth_service.update_api_key_status(
                clean_db,
                admin_context,
                api_key_id,
                ActiveStatusIn(is_active=False),
                settings=admin_settings,
            )

        else:
            auth_service.delete_api_key_credential(
                clean_db,
                admin_context,
                api_key_id,
                settings=admin_settings,
            )

    assert exc_info.value.code == (
        ErrorCode.INSUFFICIENT_PERMISSIONS
    )

    auth_service.bootstrap_admin_api_key(
        clean_db,
        admin_settings,
    )


@pytest.mark.integration
def test_revoke_previous_admin_key_after_rotation(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
) -> None:
    """Permite revocar una clave Admin que ya no está configurada."""
    previous_id = admin_context.api_key_id

    assert previous_id is not None

    new_secret = security.generate_secret()

    new_settings = ApiSettings(
        ADMIN_EMAIL=admin_settings.ADMIN_EMAIL,
        ADMIN_PASSWORD=admin_settings.ADMIN_PASSWORD,
        API_KEY=new_secret,
        BCRYPT_ROUNDS=TEST_ROUNDS,
    )

    auth_service.bootstrap_admin_api_key(
        clean_db,
        new_settings,
    )

    with Session(clean_db) as session:
        key = db.get_api_key_by_hash(
            session,
            hash_secret(new_secret),
        )

        assert key is not None

        new_context = AuthContext(
            user_id=key.user_id,
            api_key_id=key.id,
            role=key.role,
        )

    result = auth_service.update_api_key_status(
        clean_db,
        new_context,
        previous_id,
        ActiveStatusIn(is_active=False),
        settings=new_settings,
    )

    assert result.is_active is False

    auth_service.bootstrap_admin_api_key(
        clean_db,
        new_settings,
    )


# =========================================================
# REVALIDACIÓN DE LA AUTORIDAD ADMINISTRATIVA
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("resource", "code"),
    [
        ("key", ErrorCode.API_KEY_INACTIVE),
        ("user", ErrorCode.USER_INACTIVE),
    ],
)
def test_admin_mutation_revalidates_actor(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    resource: str,
    code: ErrorCode,
) -> None:
    """Rechaza un contexto Admin que ha perdido su validez."""
    with Session(clean_db) as session:
        if resource == "key":
            assert admin_context.api_key_id is not None

            api_key = db.get_api_key_by_id(
                session,
                admin_context.api_key_id,
            )

            assert api_key is not None

            db.set_api_key_active(api_key, False)

        else:
            assert admin_context.user_id is not None

            user = db.get_user_by_id(
                session,
                admin_context.user_id,
            )

            assert user is not None

            db.set_user_active(user, False)

        session.commit()

    with pytest.raises(ApiError) as exc_info:
        _admin_issue(
            clean_db,
            admin_context,
            admin_settings,
            registered_user.id,
        )

    assert exc_info.value.code == code

    with Session(clean_db) as session:
        assert len(db.list_api_keys(session)) == 1


@pytest.mark.integration
def test_admin_cannot_issue_admin_key(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
) -> None:
    """Protege también la emisión ante entradas internas inválidas."""
    body = AdminApiKeyCreateIn.model_construct(
        role=ApiKeyRole.ADMIN,
        user_id=registered_user.id,
    )

    with pytest.raises(ApiError) as exc_info:
        auth_service.issue_admin_api_key(
            clean_db,
            admin_context,
            body,
            settings=admin_settings,
        )

    assert exc_info.value.code == (
        ErrorCode.INSUFFICIENT_PERMISSIONS
    )


# =========================================================
# TRANSACCIONES Y REVOCACIÓN ADMINISTRATIVA
# =========================================================


@pytest.mark.integration
def test_admin_revocation_failure_before_commit(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Conserva las sesiones si se revierte la modificación."""
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
            auth_service.update_user_status(
                clean_db,
                auth_store,
                admin_context,
                registered_user.id,
                ActiveStatusIn(is_active=False),
                settings=admin_settings,
            )

    assert exc_info.value.code == ErrorCode.INTERNAL_SERVER_ERROR

    assert auth_store.get(registered_token).user_id == (
        registered_user.id
    )

    with Session(clean_db) as session:
        user = db.get_user_by_id(
            session,
            registered_user.id,
        )

        assert user is not None
        assert user.is_active is True
        assert user.deleted_at is None


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_admin_revocation_uncertain_commit(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    registered_user: UserOut,
    auth_store: SessionStore,
    registered_token: str,
    monkeypatch: pytest.MonkeyPatch,
    deleted: bool,
) -> None:
    """Invalida sesiones si no puede confirmarse el commit."""
    second_token, _ = auth_store.create(registered_user.id)

    original_commit = Session.commit

    def uncertain_commit(session: Session) -> None:
        """Simula una pérdida de conexión tras confirmar."""
        original_commit(session)

        raise OperationalError(
            None,
            None,
            DriverError("08006"),
            connection_invalidated=True,
        )

    with monkeypatch.context() as patch:
        patch.setattr(
            Session,
            "commit",
            uncertain_commit,
        )

        with pytest.raises(ApiError) as exc_info:
            if deleted:
                auth_service.delete_user_account(
                    clean_db,
                    auth_store,
                    admin_context,
                    registered_user.id,
                    settings=admin_settings,
                )

            else:
                auth_service.update_user_status(
                    clean_db,
                    auth_store,
                    admin_context,
                    registered_user.id,
                    ActiveStatusIn(is_active=False),
                    settings=admin_settings,
                )

    assert exc_info.value.code == ErrorCode.SERVICE_UNAVAILABLE

    _assert_invalid_session(auth_store, registered_token)
    _assert_invalid_session(auth_store, second_token)

    with Session(clean_db) as session:
        user = db.get_user_by_id(
            session,
            registered_user.id,
        )

        assert user is not None
        assert user.is_active is False
        assert (user.deleted_at is not None) == deleted


@pytest.mark.integration
@pytest.mark.parametrize(
    ("operation", "code"),
    [
        ("update_user", ErrorCode.USER_NOT_FOUND),
        ("delete_user", ErrorCode.USER_NOT_FOUND),
        ("update_key", ErrorCode.API_KEY_NOT_FOUND),
        ("delete_key", ErrorCode.API_KEY_NOT_FOUND),
    ],
)
def test_admin_modify_unknown_resource(
    clean_db: Engine,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    auth_store: SessionStore,
    operation: str,
    code: ErrorCode,
) -> None:
    """Rechaza modificaciones de recursos inexistentes."""
    resource_id = uuid4()

    with pytest.raises(ApiError) as exc_info:
        if operation == "update_user":
            auth_service.update_user_status(
                clean_db,
                auth_store,
                admin_context,
                resource_id,
                ActiveStatusIn(is_active=False),
                settings=admin_settings,
            )

        elif operation == "delete_user":
            auth_service.delete_user_account(
                clean_db,
                auth_store,
                admin_context,
                resource_id,
                settings=admin_settings,
            )

        elif operation == "update_key":
            auth_service.update_api_key_status(
                clean_db,
                admin_context,
                resource_id,
                ActiveStatusIn(is_active=False),
                settings=admin_settings,
            )

        else:
            auth_service.delete_api_key_credential(
                clean_db,
                admin_context,
                resource_id,
                settings=admin_settings,
            )

    assert exc_info.value.code == code


# Concurrencia entre operaciones ordinarias y administrativas


@pytest.mark.integration
@pytest.mark.parametrize("reactivate", [False, True])
def test_concurrent_key_management(
    clean_db: Engine,
    registered_user: UserOut,
    registered_token: str,
    auth_store: SessionStore,
    issue_settings: ApiSettings,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
    reactivate: bool,
) -> None:
    """Impide superar el límite mediante operaciones concurrentes."""
    user_id = registered_user.id
    key_id: UUID | None = None

    if reactivate:
        key = _admin_issue(
            clean_db, admin_context, admin_settings, user_id,
        )
        key_id = key.id
        auth_service.update_api_key_status(
            clean_db, admin_context, key_id,
            ActiveStatusIn(is_active=False), settings=admin_settings,
        )

    barrier = Barrier(2, timeout=5)
    original_lookup = db.get_user_by_id

    def synchronized_lookup(
        session: Session, target_id: UUID, *, for_update: bool = False,
    ) -> User | None:
        """Sincroniza los intentos de bloquear al propietario."""
        if for_update and target_id == user_id:
            barrier.wait()
        return original_lookup(session, target_id, for_update=for_update)

    monkeypatch.setattr(db, "get_user_by_id", synchronized_lookup)

    def compete(administrative: bool) -> ErrorCode | None:
        """Intenta ocupar la última plaza disponible."""
        try:
            if not administrative:
                _issue_registered(
                    clean_db, auth_store, registered_token, issue_settings,
                )
            elif key_id is not None:
                auth_service.update_api_key_status(
                    clean_db, admin_context, key_id,
                    ActiveStatusIn(is_active=True), settings=admin_settings,
                )
            else:
                _admin_issue(
                    clean_db, admin_context, admin_settings, user_id,
                )
        except ApiError as exc:
            return exc.code
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        ordinary = pool.submit(compete, False)
        administrative = pool.submit(compete, True)
        results = [ordinary.result(timeout=15),
                   administrative.result(timeout=15)]

    assert results.count(None) == 1
    assert results.count(ErrorCode.API_KEY_LIMIT_REACHED) == 1

    with Session(clean_db) as session:
        assert db.count_active_api_keys(
            session, user_id, ApiKeyRole.FREE,
        ) == 1


@pytest.mark.integration
def test_concurrent_login_and_user_deactivation(
    clean_db: Engine,
    registered_user: UserOut,
    registered_token: str,
    auth_store: SessionStore,
    dummy_hash: str,
    admin_context: AuthContext,
    admin_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalida las sesiones creadas durante una desactivación."""
    user_id = registered_user.id
    barrier = Barrier(2, timeout=5)
    original_by_email = db.get_user_by_email
    original_by_id = db.get_user_by_id

    def login_lookup(
        session: Session, email: str, *, for_update: bool = False,
    ) -> User | None:
        """Detiene el login después de bloquear al usuario."""
        user = original_by_email(session, email, for_update=for_update)
        if for_update and email == registered_user.email:
            barrier.wait()
        return user

    def admin_lookup(
        session: Session, target_id: UUID, *, for_update: bool = False,
    ) -> User | None:
        """Sincroniza la desactivación antes de adquirir el bloqueo."""
        if for_update and target_id == user_id:
            barrier.wait()
        return original_by_id(session, target_id, for_update=for_update)

    monkeypatch.setattr(db, "get_user_by_email", login_lookup)
    monkeypatch.setattr(db, "get_user_by_id", admin_lookup)

    with ThreadPoolExecutor(max_workers=2) as pool:
        login = pool.submit(_login, clean_db, auth_store, dummy_hash)
        deactivation = pool.submit(
            auth_service.update_user_status,
            clean_db, auth_store, admin_context, user_id,
            ActiveStatusIn(is_active=False), settings=admin_settings,
        )
        login_result = login.result(timeout=15)
        user_result = deactivation.result(timeout=15)

    assert user_result.is_active is False
    _assert_invalid_session(auth_store, registered_token)
    _assert_invalid_session(auth_store, login_result.session_token)