"""Servicios de autenticación de usuarios de ReciclaTIA."""

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

from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.mappers import to_user_out
from api.schemas import (
    LoginIn,
    LoginOut,
    PasswordChangeIn,
    RegisterIn,
    UserOut,
)
from api.security import (
    SessionStore,
    hash_password,
    verify_password,
)
from src import db
from src.models import User


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


def _require_active_user(user: User) -> None:
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

            _require_active_user(user)

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
            _require_active_user(user)

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