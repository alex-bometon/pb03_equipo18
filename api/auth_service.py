"""Servicios de autenticación de usuarios de ReciclaTIA."""

from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    DBAPIError,
    IntegrityError,
    InterfaceError,
    OperationalError,
    SQLAlchemyError,
    TimeoutError as SQLAlchemyTimeoutError,
)
from sqlmodel import Session

from api.config import ApiSettings
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.mappers import to_api_key_out, to_user_out
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
    SessionStore,
    generate_secret,
    hash_password,
    hash_secret,
    verify_password,
)
from src import db
from src.enums import ApiKeyRole
from src.models import ApiKey, User


# =========================================================
# ERRORES RELACIONALES
# =========================================================


def translate_db_error(
    exc: SQLAlchemyError,
    *,
    registering: bool = False,
) -> ApiError:
    """Traduce errores relacionales sin exponer detalles internos."""
    if isinstance(exc, SQLAlchemyTimeoutError):
        return ApiError(ErrorCode.SERVICE_UNAVAILABLE)

    if isinstance(exc, DBAPIError):
        sqlstate = getattr(exc.orig, "pgcode", None)
        diagnostic = getattr(exc.orig, "diag", None)
        constraint = getattr(
            diagnostic,
            "constraint_name",
            None,
        )

        if (
            registering
            and isinstance(exc, IntegrityError)
            and sqlstate == "23505"
            and constraint == "user_email_unique"
        ):
            return ApiError(ErrorCode.EMAIL_ALREADY_EXISTS)

        if exc.connection_invalidated:
            return ApiError(ErrorCode.SERVICE_UNAVAILABLE)

        if sqlstate and sqlstate.startswith("08"):
            return ApiError(ErrorCode.SERVICE_UNAVAILABLE)

        if sqlstate in {
            "53300",
            "55P03",
            "57014",
            "57P01",
            "57P02",
            "57P03",
        }:
            return ApiError(ErrorCode.SERVICE_UNAVAILABLE)

        if (
            sqlstate is None
            and isinstance(exc, (OperationalError, InterfaceError))
        ):
            return ApiError(ErrorCode.SERVICE_UNAVAILABLE)

    return ApiError(ErrorCode.INTERNAL_SERVER_ERROR)


def require_active_user(user: User) -> None:
    """Comprueba que la cuenta puede realizar operaciones."""
    if not user.is_active or user.deleted_at is not None:
        raise ApiError(ErrorCode.USER_INACTIVE)


# =========================================================
# REGISTRO
# =========================================================


def register_user(
    engine: Engine,
    body: RegisterIn,
    *,
    rounds: int,
) -> UserOut:
    """Registra una cuenta y confirma su persistencia."""
    password_hash = hash_password(
        body.password.get_secret_value(),
        rounds,
    )

    user = User(
        email=body.email,
        password_hash=password_hash,
    )

    try:
        with Session(engine) as session:
            db.create_user(session, user)
            session.flush()

            result = to_user_out(user)

            session.commit()

            return result

    except SQLAlchemyError as exc:
        raise translate_db_error(
            exc,
            registering=True,
        ) from None


# =========================================================
# LOGIN
# =========================================================


def login_user(
    engine: Engine,
    session_store: SessionStore,
    body: LoginIn,
    *,
    dummy_password_hash: str,
) -> LoginOut:
    """Autentica al usuario y genera una sesión temporal."""
    password = body.password.get_secret_value()

    try:
        with Session(engine) as session:
            user = db.get_user_by_email(
                session,
                body.email,
                for_update=True,
            )

            if user is None:
                verify_password(password, dummy_password_hash)

                raise ApiError(ErrorCode.INVALID_CREDENTIALS)

            if not verify_password(password, user.password_hash):
                raise ApiError(ErrorCode.INVALID_CREDENTIALS)

            require_active_user(user)

            user_id = user.id
            user_out = to_user_out(user)

            with session_store.locked():
                session.commit()

                token, record = session_store.create(user_id)

                try:
                    return LoginOut(
                        session_token=token,
                        token_type="Bearer",
                        expires_at=record.expires_at,
                        user=user_out,
                    )

                except Exception:
                    # Evita conservar una sesión que no se entregará.
                    try:
                        session_store.revoke(token)
                    except ApiError:
                        pass

                    raise ApiError(
                        ErrorCode.INTERNAL_SERVER_ERROR,
                    ) from None

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


# =========================================================
# CAMBIO DE CONTRASEÑA
# =========================================================


def change_password(
    engine: Engine,
    session_store: SessionStore,
    token: str,
    body: PasswordChangeIn,
    *,
    rounds: int,
) -> UserOut:
    """Actualiza la contraseña e invalida las sesiones del usuario."""
    record = session_store.get(token)
    user_id = record.user_id

    try:
        with Session(engine) as session:
            user = db.get_user_by_id(
                session,
                user_id,
                for_update=True,
            )

            if user is None:
                raise ApiError(ErrorCode.INVALID_SESSION)

            session_store.get(token)
            require_active_user(user)

            current_password = (
                body.current_password.get_secret_value()
            )

            if not verify_password(
                current_password,
                user.password_hash,
            ):
                raise ApiError(ErrorCode.INVALID_CREDENTIALS)

            new_hash = hash_password(
                body.new_password.get_secret_value(),
                rounds,
            )

            with session_store.locked():
                session_store.get(token)

                db.update_user_password(user, new_hash)
                session.flush()

                result = to_user_out(user)

                try:
                    session.commit()

                except Exception:
                    # El resultado del commit podría ser incierto.
                    session_store.revoke_user(user_id)
                    raise

                session_store.revoke_user(user_id)

                return result

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

# =========================================================
# GENERACIÓN Y EMISIÓN DE API KEYS
# =========================================================


def _check_active_key_limit(
    session: Session,
    user_id: UUID,
    role: IssuableApiKeyRole,
    settings: ApiSettings,
) -> None:
    """Comprueba el límite de claves activas del propietario."""
    if role == ApiKeyRole.FREE:
        limit = settings.FREE_MAX_ACTIVE_KEYS

    elif role == ApiKeyRole.USER:
        limit = settings.USER_MAX_ACTIVE_KEYS

    else:
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    active_keys = db.count_active_api_keys(
        session,
        user_id,
        role,
    )

    if active_keys >= limit:
        raise ApiError(ErrorCode.API_KEY_LIMIT_REACHED)


def _create_issued_api_key(
    session: Session,
    role: IssuableApiKeyRole,
    user_id: UUID | None,
) -> ApiKeyCreatedOut:
    """Prepara una nueva credencial sin confirmar la transacción."""
    if role not in (ApiKeyRole.FREE, ApiKeyRole.USER):
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    secret = generate_secret()

    api_key = ApiKey(
        user_id=user_id,
        role=role,
        key_hash=hash_secret(secret),
    )

    db.create_api_key(session, api_key)
    session.flush()

    try:
        public_data = to_api_key_out(api_key)

        return ApiKeyCreatedOut(
            **public_data.model_dump(),
            api_key=secret,
        )

    except ValidationError:
        raise ApiError(
            ErrorCode.INTERNAL_SERVER_ERROR,
        ) from None


def issue_anonymous_api_key(
    engine: Engine,
) -> ApiKeyCreatedOut:
    """Emite una API key Free sin propietario registrado."""
    try:
        with Session(engine) as session:
            result = _create_issued_api_key(
                session,
                ApiKeyRole.FREE,
                user_id=None,
            )

            session.commit()

            return result

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def issue_user_api_key(
    engine: Engine,
    session_store: SessionStore,
    token: str,
    body: ApiKeyCreateIn,
    *,
    settings: ApiSettings,
) -> ApiKeyCreatedOut:
    """Emite una clave ordinaria para un usuario autenticado."""
    record = session_store.get(token)
    user_id = record.user_id

    try:
        with Session(engine) as session:
            user = db.get_user_by_id(
                session,
                user_id,
                for_update=True,
            )

            if user is None:
                raise ApiError(ErrorCode.INVALID_SESSION)

            session_store.get(token)
            require_active_user(user)

            if (
                body.role == ApiKeyRole.USER
                and user_id not in (
                    settings.USER_TIER_ALLOWED_USER_IDS
                )
            ):
                raise ApiError(
                    ErrorCode.USER_TIER_NOT_AUTHORIZED,
                )

            _check_active_key_limit(
                session,
                user_id,
                body.role,
                settings,
            )

            with session_store.locked():
                session_store.get(token)

                result = _create_issued_api_key(
                    session,
                    body.role,
                    user_id,
                )

                session.commit()

                return result

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

# =========================================================
# APROVISIONAMIENTO ADMINISTRATIVO
# =========================================================


def bootstrap_admin_api_key(
    engine: Engine,
    settings: ApiSettings,
) -> None:
    """Aprovisiona y comprueba las credenciales administrativas."""
    if (
        settings.ADMIN_EMAIL is None
        or settings.ADMIN_PASSWORD is None
        or settings.API_KEY is None
    ):
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    email = settings.ADMIN_EMAIL.get_secret_value()
    password = settings.ADMIN_PASSWORD.get_secret_value()
    key_hash = hash_secret(
        settings.API_KEY.get_secret_value(),
    )

    try:
        with Session(engine) as session:
            user = db.get_user_by_email(
                session,
                email,
                for_update=True,
            )

            api_key = db.get_api_key_by_hash(
                session,
                key_hash,
                for_update=True,
            )

            if user is None:
                if api_key is not None:
                    raise RuntimeError(
                        "Conflicto de credencial administrativa."
                    )

                user = User(
                    email=email,
                    password_hash=hash_password(
                        password,
                        settings.BCRYPT_ROUNDS,
                    ),
                )

                db.create_user(session, user)
                session.flush()

            else:
                require_active_user(user)

                if not verify_password(
                    password,
                    user.password_hash,
                ):
                    raise RuntimeError(
                        "Contraseña administrativa incoherente."
                    )

                if api_key is None:
                    previous_keys = db.list_user_api_keys(
                        session,
                        user.id,
                    )

                    if not any(
                        key.role == ApiKeyRole.ADMIN
                        for key in previous_keys
                    ):
                        raise RuntimeError(
                            "La cuenta existente no es administrativa."
                        )

            if api_key is None:
                api_key = ApiKey(
                    user_id=user.id,
                    key_hash=key_hash,
                    role=ApiKeyRole.ADMIN,
                )

                db.create_api_key(session, api_key)
                session.flush()

            else:
                if (
                    api_key.user_id != user.id
                    or api_key.role != ApiKeyRole.ADMIN
                ):
                    raise RuntimeError(
                        "Conflicto de credencial administrativa."
                    )

                if (
                    not api_key.is_active
                    or api_key.deleted_at is not None
                ):
                    raise RuntimeError(
                        "La credencial administrativa no está activa."
                    )

            session.commit()

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None