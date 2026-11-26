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
from api.request_context import AuthContext
from api.schemas import (
    ActiveStatusIn,
    AdminApiKeyCreateIn,
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyOut,
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
    

# =========================================================
# CONSULTA DE CUENTA Y CIERRE DE SESIÓN
# =========================================================


def _get_session_user(
    session: Session,
    session_store: SessionStore,
    token: str,
    *,
    for_update: bool = False,
) -> User:
    """Recupera el usuario asociado a una sesión vigente."""
    record = session_store.get(token)

    user = db.get_user_by_id(
        session,
        record.user_id,
        for_update=for_update,
    )

    if user is None:
        raise ApiError(ErrorCode.INVALID_SESSION)

    require_active_user(user)
    session_store.get(token)

    return user


def get_user_profile(
    engine: Engine,
    session_store: SessionStore,
    token: str,
) -> UserOut:
    """Recupera el perfil de una cuenta autenticada."""
    try:
        with Session(engine) as session:
            user = _get_session_user(
                session,
                session_store,
                token,
            )

            return to_user_out(user)

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def logout_user(
    engine: Engine,
    session_store: SessionStore,
    token: str,
) -> None:
    """Invalida exclusivamente la sesión utilizada."""
    try:
        with Session(engine) as session:
            _get_session_user(
                session,
                session_store,
                token,
                for_update=True,
            )

            session_store.revoke(token)

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

# =========================================================
# VALIDACIÓN ADMINISTRATIVA
# =========================================================


def _require_admin_context(
    context: AuthContext,
) -> tuple[UUID, UUID]:
    """Comprueba la identidad administrativa recibida."""
    if (
        context.role != ApiKeyRole.ADMIN
        or context.user_id is None
        or context.api_key_id is None
    ):
        raise ApiError(
            ErrorCode.INSUFFICIENT_PERMISSIONS,
        )

    return context.user_id, context.api_key_id


def _require_existing_user(
    user: User | None,
) -> User:
    """Exige la existencia de un usuario administrado."""
    if user is None:
        raise ApiError(ErrorCode.USER_NOT_FOUND)

    return user


def _require_existing_api_key(
    api_key: ApiKey | None,
) -> ApiKey:
    """Exige la existencia de una credencial administrada."""
    if api_key is None:
        raise ApiError(ErrorCode.API_KEY_NOT_FOUND)

    return api_key


def _require_enabled_target_user(
    user: User | None,
) -> User:
    """Comprueba el estado del destinatario administrativo."""
    user = _require_existing_user(user)

    if user.deleted_at is not None:
        raise ApiError(ErrorCode.USER_DELETED)

    require_active_user(user)

    return user


def _lock_admin_resources(
    session: Session,
    context: AuthContext,
    *,
    target_user_id: UUID | None = None,
    target_key_id: UUID | None = None,
) -> tuple[User | None, ApiKey | None]:
    """Bloquea los recursos administrativos y valida al actor."""
    admin_user_id, admin_key_id = _require_admin_context(
        context,
    )

    target_owner_id = target_user_id
    target_exists = False

    if target_key_id is not None:
        target_key = db.get_api_key_by_id(
            session,
            target_key_id,
        )

        if target_key is not None:
            target_exists = True
            target_owner_id = target_key.user_id

    user_ids = {admin_user_id}

    if target_owner_id is not None:
        user_ids.add(target_owner_id)

    users = {
        user_id: db.get_user_by_id(
            session,
            user_id,
            for_update=True,
        )
        for user_id in sorted(user_ids)
    }

    key_ids = {admin_key_id}

    if target_key_id is not None and target_exists:
        key_ids.add(target_key_id)

    keys = {
        api_key_id: db.get_api_key_by_id(
            session,
            api_key_id,
            for_update=True,
        )
        for api_key_id in sorted(key_ids)
    }

    admin_key = keys[admin_key_id]
    admin_user = users[admin_user_id]

    if (
        admin_key is None
        or admin_key.user_id != admin_user_id
        or admin_key.role != ApiKeyRole.ADMIN
    ):
        raise ApiError(ErrorCode.INVALID_API_KEY)

    if (
        not admin_key.is_active
        or admin_key.deleted_at is not None
    ):
        raise ApiError(ErrorCode.API_KEY_INACTIVE)

    if admin_user is None:
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR)

    require_active_user(admin_user)

    target_user = users.get(target_owner_id)
    target_key = keys.get(target_key_id)

    if (
        target_key is not None
        and target_key.user_id != target_owner_id
    ):
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR)

    return target_user, target_key


def _protect_bootstrap_user(
    user: User,
    settings: ApiSettings,
) -> None:
    """Protege la cuenta administrativa configurada."""
    if settings.ADMIN_EMAIL is None:
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    admin_email = settings.ADMIN_EMAIL.get_secret_value()

    if user.email == admin_email:
        raise ApiError(
            ErrorCode.INSUFFICIENT_PERMISSIONS,
        )


def _protect_bootstrap_api_key(
    api_key: ApiKey,
    settings: ApiSettings,
) -> None:
    """Protege la credencial administrativa configurada."""
    if settings.API_KEY is None:
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    protected_hash = hash_secret(
        settings.API_KEY.get_secret_value(),
    )

    if api_key.key_hash == protected_hash:
        raise ApiError(
            ErrorCode.INSUFFICIENT_PERMISSIONS,
        )
    

# =========================================================
# CONSULTAS ADMINISTRATIVAS
# =========================================================


def list_admin_users(
    engine: Engine,
    context: AuthContext,
) -> list[UserOut]:
    """Recupera todos los usuarios para su administración."""
    _require_admin_context(context)

    try:
        with Session(engine) as session:
            return [
                to_user_out(user)
                for user in db.list_users(session)
            ]

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def get_admin_user(
    engine: Engine,
    context: AuthContext,
    user_id: UUID,
) -> UserOut:
    """Recupera cualquier usuario mediante acceso administrativo."""
    _require_admin_context(context)

    try:
        with Session(engine) as session:
            user = _require_existing_user(
                db.get_user_by_id(session, user_id),
            )

            return to_user_out(user)

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def list_admin_api_keys(
    engine: Engine,
    context: AuthContext,
) -> list[ApiKeyOut]:
    """Recupera todas las API keys para su administración."""
    _require_admin_context(context)

    try:
        with Session(engine) as session:
            return [
                to_api_key_out(api_key)
                for api_key in db.list_api_keys(session)
            ]

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def get_admin_api_key(
    engine: Engine,
    context: AuthContext,
    api_key_id: UUID,
) -> ApiKeyOut:
    """Recupera una API key sin exponer su secreto."""
    _require_admin_context(context)

    try:
        with Session(engine) as session:
            api_key = _require_existing_api_key(
                db.get_api_key_by_id(session, api_key_id),
            )

            return to_api_key_out(api_key)

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

# =========================================================
# ADMINISTRACIÓN DE USUARIOS
# =========================================================


def _commit_user_revocation(
    session: Session,
    session_store: SessionStore,
    user_id: UUID,
) -> None:
    """Confirma la revocación e invalida las sesiones."""
    with session_store.locked():
        try:
            session.commit()

        except Exception:
            # El resultado de la transacción puede ser incierto.
            session_store.revoke_user(user_id)
            raise

        session_store.revoke_user(user_id)


def update_user_status(
    engine: Engine,
    session_store: SessionStore,
    context: AuthContext,
    user_id: UUID,
    body: ActiveStatusIn,
    *,
    settings: ApiSettings,
) -> UserOut:
    """Modifica el estado de una cuenta administrada."""
    try:
        with Session(engine) as session:
            user, _ = _lock_admin_resources(
                session,
                context,
                target_user_id=user_id,
            )

            user = _require_existing_user(user)

            if user.deleted_at is not None:
                raise ApiError(ErrorCode.USER_DELETED)

            if not body.is_active:
                _protect_bootstrap_user(user, settings)

            if user.is_active != body.is_active:
                db.set_user_active(user, body.is_active)

            session.flush()

            result = to_user_out(user)

            if body.is_active:
                session.commit()

            else:
                _commit_user_revocation(
                    session,
                    session_store,
                    user.id,
                )

            return result

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

def delete_user_account(
    engine: Engine,
    session_store: SessionStore,
    context: AuthContext,
    user_id: UUID,
    *,
    settings: ApiSettings,
) -> None:
    """Elimina lógicamente una cuenta e invalida sus sesiones."""
    try:
        with Session(engine) as session:
            user, _ = _lock_admin_resources(
                session,
                context,
                target_user_id=user_id,
            )

            user = _require_existing_user(user)

            _protect_bootstrap_user(user, settings)

            db.delete_user(user)
            session.flush()

            _commit_user_revocation(
                session,
                session_store,
                user.id,
            )

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

# =========================================================
# ADMINISTRACIÓN DE API KEYS
# =========================================================


def issue_admin_api_key(
    engine: Engine,
    context: AuthContext,
    body: AdminApiKeyCreateIn,
    *,
    settings: ApiSettings,
) -> ApiKeyCreatedOut:
    """Emite una clave ordinaria por autorización administrativa."""
    if body.role not in (
        ApiKeyRole.FREE,
        ApiKeyRole.USER,
    ):
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    if (
        body.role == ApiKeyRole.USER
        and body.user_id is None
    ):
        raise ApiError(ErrorCode.VALIDATION_ERROR)

    try:
        with Session(engine) as session:
            user, _ = _lock_admin_resources(
                session,
                context,
                target_user_id=body.user_id,
            )

            if body.user_id is not None:
                user = _require_enabled_target_user(user)

                _check_active_key_limit(
                    session,
                    user.id,
                    body.role,
                    settings,
                )

            result = _create_issued_api_key(
                session,
                body.role,
                body.user_id,
            )

            session.commit()

            return result

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

def update_api_key_status(
    engine: Engine,
    context: AuthContext,
    api_key_id: UUID,
    body: ActiveStatusIn,
    *,
    settings: ApiSettings,
) -> ApiKeyOut:
    """Modifica el estado de una API key no eliminada."""
    try:
        with Session(engine) as session:
            owner, api_key = _lock_admin_resources(
                session,
                context,
                target_key_id=api_key_id,
            )

            api_key = _require_existing_api_key(api_key)

            if api_key.deleted_at is not None:
                raise ApiError(ErrorCode.API_KEY_DELETED)

            if not body.is_active:
                _protect_bootstrap_api_key(
                    api_key,
                    settings,
                )

            if api_key.is_active == body.is_active:
                return to_api_key_out(api_key)

            if body.is_active and api_key.user_id is not None:
                owner = _require_enabled_target_user(owner)

                if api_key.role in (
                    ApiKeyRole.FREE,
                    ApiKeyRole.USER,
                ):
                    _check_active_key_limit(
                        session,
                        owner.id,
                        api_key.role,
                        settings,
                    )

            db.set_api_key_active(
                api_key,
                body.is_active,
            )

            session.flush()

            result = to_api_key_out(api_key)

            session.commit()

            return result

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None
    

def delete_api_key_credential(
    engine: Engine,
    context: AuthContext,
    api_key_id: UUID,
    *,
    settings: ApiSettings,
) -> None:
    """Elimina lógicamente una credencial administrada."""
    try:
        with Session(engine) as session:
            _, api_key = _lock_admin_resources(
                session,
                context,
                target_key_id=api_key_id,
            )

            api_key = _require_existing_api_key(api_key)

            _protect_bootstrap_api_key(
                api_key,
                settings,
            )

            db.delete_api_key(api_key)
            session.flush()
            session.commit()

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None