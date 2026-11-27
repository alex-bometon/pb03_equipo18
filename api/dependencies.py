"""Dependencias de autenticación HTTP de ReciclaTIA."""

import re
from collections.abc import Callable, Iterator
from typing import Annotated
from uuid import UUID
from ipaddress import ip_address
from contextlib import ExitStack

from fastapi import Depends, Header, Request, Security
from fastapi.security import (
    APIKeyHeader,
    HTTPAuthorizationCredentials,
    HTTPBearer,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from api.auth_service import (
    require_active_user,
    translate_db_error,
)
from api.config import ApiSettings
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.request_context import (
    API_KEY_CHALLENGE,
    COMBINED_AUTH_CHALLENGE,
    SESSION_CHALLENGE,
    AuthContext,
)
from api.security import SessionStore, hash_secret
from api.service import (
    ControlAdmision,
    EjecutorAsistente,
    recuperar_estado_operativo,
)
from api.rate_limit import SlidingWindowLog, limitar_http
from src import db
from src.enums import ApiKeyRole
from src.models import ApiKey, Conversation
from src.state import EstadoProducto


# =========================================================
# ESQUEMAS DE SEGURIDAD HTTP
# =========================================================


API_KEY_HEADER = "X-API-Key"
AUTHORIZATION_HEADER = "Authorization"
API_KEY_ID_HEADER = "X-API-Key-Id"

api_key_scheme = APIKeyHeader(
    name=API_KEY_HEADER,
    scheme_name="ApiKeyAuth",
    description="API key original de ReciclaTÍA.",
    auto_error=False,
)

session_scheme = HTTPBearer(
    scheme_name="SessionAuth",
    description="Token de sesión de usuario.",
    auto_error=False,
)


# =========================================================
# RECURSOS COMPARTIDOS
# =========================================================


def get_settings(request: Request) -> ApiSettings:
    """Recupera la configuración compartida del backend."""
    settings = getattr(request.app.state, "settings", None)

    if not isinstance(settings, ApiSettings):
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    return settings


def get_engine(request: Request) -> Engine:
    """Recupera el engine inicializado durante el lifespan."""
    engine = getattr(request.app.state, "engine", None)

    if not isinstance(engine, Engine):
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    return engine


def get_session_store(request: Request) -> SessionStore:
    """Recupera el gestor compartido de sesiones de usuario."""
    store = getattr(request.app.state, "session_store", None)

    if not isinstance(store, SessionStore):
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    return store

def get_rate_limiter(request: Request) -> SlidingWindowLog:
    """Recupera el limitador compartido del backend."""
    limitador = getattr(request.app.state, "rate_limiter", None)

    if not isinstance(limitador, SlidingWindowLog):
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    return limitador

def get_admision(request: Request) -> ControlAdmision:
    """Recupera el control compartido de admisión."""
    admision = getattr(request.app.state, "admision", None)

    if not isinstance(admision, ControlAdmision):
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    return admision

def get_ejecutor(request: Request) -> EjecutorAsistente:
    """Recupera el executor compartido del backend."""
    ejecutor = getattr(request.app.state, "ejecutor", None)

    if not isinstance(ejecutor, EjecutorAsistente):
        raise ApiError(ErrorCode.SERVICE_NOT_CONFIGURED)

    return ejecutor

def obtener_origen(request: Request) -> str:
    """Obtiene el origen comunicado por el servidor ASGI."""
    if request.client is not None:
        try:
            return str(ip_address(request.client.host))

        except ValueError:
            pass

    return "origen_no_identificado"

def get_session(
    engine: Annotated[Engine, Depends(get_engine)],
) -> Iterator[Session]:
    """Proporciona una sesión SQL y garantiza su cierre."""
    try:
        with Session(engine) as session:
            yield session

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


# =========================================================
# VALIDACIÓN DE CABECERAS
# =========================================================


def _read_header(
    request: Request,
    name: str,
) -> str | None:
    """Recupera una cabecera sin admitir valores duplicados."""
    values = request.headers.getlist(name)

    if len(values) > 1:
        raise ApiError(ErrorCode.AMBIGUOUS_CREDENTIALS)

    if not values:
        return None

    value = values[0]

    # Rechaza valores combinados por intermediarios HTTP.
    if "," in value:
        raise ApiError(ErrorCode.AMBIGUOUS_CREDENTIALS)

    return value


def _read_credentials(
    request: Request,
) -> tuple[str | None, str | None, str | None]:
    """Comprueba la compatibilidad de las modalidades HTTP."""
    api_key = _read_header(request, API_KEY_HEADER)

    authorization = _read_header(
        request,
        AUTHORIZATION_HEADER,
    )

    api_key_id = _read_header(
        request,
        API_KEY_ID_HEADER,
    )

    if api_key is not None and (
        authorization is not None
        or api_key_id is not None
    ):
        raise ApiError(ErrorCode.AMBIGUOUS_CREDENTIALS)

    if api_key_id is not None and authorization is None:
        raise ApiError(ErrorCode.INVALID_SESSION)

    return api_key, authorization, api_key_id


def _parse_bearer(authorization: str) -> str:
    """Extrae el token de una cabecera Bearer válida."""
    match = re.fullmatch(
        r"(?i:Bearer) +(\S+)",
        authorization,
    )

    if match is None:
        raise ApiError(ErrorCode.INVALID_SESSION)

    return match.group(1)


# =========================================================
# AUTENTICACIÓN MEDIANTE API KEY ORIGINAL
# =========================================================


def _authenticate_original_key(
    engine: Engine,
    secret: str,
) -> AuthContext:
    """Autentica una API key original mediante PostgreSQL."""
    if not secret or any(char.isspace() for char in secret):
        raise ApiError(ErrorCode.INVALID_API_KEY)

    try:
        key_hash = hash_secret(secret)

    except UnicodeEncodeError:
        raise ApiError(ErrorCode.INVALID_API_KEY) from None

    try:
        with Session(engine) as session:
            api_key = db.get_api_key_by_hash(
                session,
                key_hash,
            )

            if api_key is None:
                raise ApiError(ErrorCode.INVALID_API_KEY)

            if (
                not api_key.is_active
                or api_key.deleted_at is not None
            ):
                raise ApiError(ErrorCode.API_KEY_INACTIVE)

            if api_key.user_id is not None:
                user = db.get_user_by_id(
                    session,
                    api_key.user_id,
                )

                if user is None:
                    raise ApiError(
                        ErrorCode.INTERNAL_SERVER_ERROR,
                    )

                require_active_user(user)

            elif api_key.role != ApiKeyRole.FREE:
                raise ApiError(
                    ErrorCode.INTERNAL_SERVER_ERROR,
                )

            return AuthContext(
                user_id=api_key.user_id,
                api_key_id=api_key.id,
                role=api_key.role,
            )

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


# =========================================================
# AUTENTICACIÓN MEDIANTE SESIÓN
# =========================================================


def _authenticate_user_session(
    engine: Engine,
    store: SessionStore,
    token: str,
    selected_key_id: str | None,
) -> AuthContext:
    """Autentica una sesión y, opcionalmente, una clave propia."""
    record = store.get(token)

    try:
        with Session(engine) as session:
            user = db.get_user_by_id(
                session,
                record.user_id,
            )

            if user is None:
                raise ApiError(ErrorCode.INVALID_SESSION)

            require_active_user(user)

            if selected_key_id is None:
                context = AuthContext(
                    user_id=user.id,
                    api_key_id=None,
                    role=None,
                )

            else:
                context = _authenticate_selected_key(
                    session,
                    user.id,
                    selected_key_id,
                )

            # Comprueba que la sesión sigue vigente.
            store.get(token)

            return context

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None


def _is_owned_ordinary_key(
    api_key: ApiKey,
    user_id: UUID,
) -> bool:
    """Comprueba si una clave pertenece al ámbito del usuario."""
    return (
        api_key.user_id == user_id
        and api_key.role in (
            ApiKeyRole.FREE,
            ApiKeyRole.USER,
        )
        and api_key.deleted_at is None
    )


def require_owned_api_key(
    session: Session,
    user_id: UUID,
    api_key_id: UUID,
    *,
    require_active: bool = True,
) -> ApiKey:
    """Recupera una clave ordinaria autorizada para su dueño."""
    api_key = db.get_api_key_by_id(
        session,
        api_key_id,
    )

    if api_key is None or not _is_owned_ordinary_key(
        api_key,
        user_id,
    ):
        raise ApiError(ErrorCode.API_KEY_NOT_FOUND)

    if require_active and not api_key.is_active:
        raise ApiError(ErrorCode.API_KEY_INACTIVE)

    return api_key


def _authenticate_selected_key(
    session: Session,
    user_id: UUID,
    selected_key_id: str,
) -> AuthContext:
    """Comprueba la propiedad y disponibilidad de una clave."""
    try:
        api_key_id = UUID(selected_key_id)

    except ValueError:
        raise ApiError(ErrorCode.VALIDATION_ERROR) from None

    api_key = require_owned_api_key(
        session,
        user_id,
        api_key_id,
    )

    return AuthContext(
        user_id=user_id,
        api_key_id=api_key.id,
        role=api_key.role,
    )


# =========================================================
# RESOLUCIÓN DE LA IDENTIDAD
# =========================================================


def _resolve_authentication(
    request: Request,
    engine: Engine,
    store: SessionStore,
    missing_code: ErrorCode,
) -> AuthContext:
    """Autentica la identidad y aplica su límite HTTP."""
    api_key, authorization, selected_key_id = _read_credentials(request)

    if api_key is not None:
        contexto = _authenticate_original_key(engine, api_key)

    elif authorization is not None:
        token = _parse_bearer(authorization)

        contexto = _authenticate_user_session(
            engine,
            store,
            token,
            selected_key_id,
        )

    else:
        raise ApiError(missing_code)

    limitar_http(get_rate_limiter(request), contexto)

    return contexto


# =========================================================
# DEPENDENCIAS PÚBLICAS DE AUTENTICACIÓN
# =========================================================


def get_auth_context(
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    _api_key: Annotated[str | None, Security(api_key_scheme)],
    _bearer: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(session_scheme),
    ],
    _selected_key_id: Annotated[
        str | None,
        Header(
            alias=API_KEY_ID_HEADER,
            description="UUID de una API key propia seleccionada.",
        ),
    ] = None,
) -> AuthContext:
    """Resuelve cualquiera de las modalidades de autenticación."""
    request.state.auth_challenge = COMBINED_AUTH_CHALLENGE

    return _resolve_authentication(
        request,
        engine,
        store,
        ErrorCode.API_KEY_REQUIRED,
    )


def get_current_user(
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    _bearer: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(session_scheme),
    ],
) -> AuthContext:
    """Exige una sesión de usuario sin selección de API key."""
    request.state.auth_challenge = SESSION_CHALLENGE

    context = _resolve_authentication(
        request,
        engine,
        store,
        ErrorCode.INVALID_SESSION,
    )

    if context.api_key_id is not None:
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    return context


def get_current_api_key(
    request: Request,
    engine: Annotated[Engine, Depends(get_engine)],
    store: Annotated[SessionStore, Depends(get_session_store)],
    _api_key: Annotated[str | None, Security(api_key_scheme)],
) -> AuthContext:
    """Exige autenticación mediante una API key original."""
    request.state.auth_challenge = API_KEY_CHALLENGE

    context = _resolve_authentication(
        request,
        engine,
        store,
        ErrorCode.API_KEY_REQUIRED,
    )

    if request.headers.getlist(AUTHORIZATION_HEADER):
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    return context


def require_api_key_context(
    context: Annotated[AuthContext, Depends(get_auth_context)],
) -> AuthContext:
    """Exige una identidad asociada a una API key activa."""
    if context.api_key_id is None:
        raise ApiError(ErrorCode.API_KEY_REQUIRED)

    return context


# =========================================================
# AUTORIZACIÓN POR ROLES
# =========================================================


def _check_roles(
    context: AuthContext,
    *allowed_roles: ApiKeyRole,
) -> AuthContext:
    """Comprueba que la identidad dispone de un rol autorizado."""
    if context.api_key_id is None:
        raise ApiError(ErrorCode.API_KEY_REQUIRED)

    if context.role not in allowed_roles:
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    return context


def require_roles(
    *allowed_roles: ApiKeyRole,
) -> Callable[[AuthContext], AuthContext]:
    """Construye una dependencia de autorización por roles."""

    def dependency(
        context: Annotated[
            AuthContext,
            Depends(require_api_key_context),
        ],
    ) -> AuthContext:
        """Comprueba los permisos de la identidad autenticada."""
        return _check_roles(
            context,
            *allowed_roles,
        )

    return dependency


def require_admin(
    context: Annotated[
        AuthContext,
        Depends(get_current_api_key),
    ],
) -> AuthContext:
    """Exige una API key administrativa original y activa."""
    return _check_roles(
        context,
        ApiKeyRole.ADMIN,
    )


# =========================================================
# AUTORIZACIÓN SOBRE CONVERSACIONES
# =========================================================


def _require_owned_thread(
    session: Session,
    api_key_id: UUID,
    thread_id: UUID,
) -> Conversation:
    """Recupera una conversación perteneciente a una clave."""
    conversation = db.get_conversation_by_owner(
        session,
        thread_id,
        api_key_id,
    )

    if conversation is None:
        raise ApiError(ErrorCode.THREAD_NOT_FOUND)

    return conversation


def require_thread_access(
    session: Session,
    context: AuthContext,
    thread_id: UUID,
) -> Conversation:
    """Comprueba el acceso operativo a una conversación."""
    _check_roles(
        context,
        ApiKeyRole.FREE,
        ApiKeyRole.USER,
        ApiKeyRole.ADMIN,
    )

    if context.role == ApiKeyRole.ADMIN:
        conversation = db.get_conversation_by_id(
            session,
            thread_id,
        )

        if conversation is None:
            raise ApiError(ErrorCode.THREAD_NOT_FOUND)

        return conversation

    api_key_id = context.api_key_id

    if api_key_id is None:
        raise ApiError(ErrorCode.API_KEY_REQUIRED)

    return _require_owned_thread(
        session,
        api_key_id,
        thread_id,
    )


def reservar_hilo_autorizado(
    engine: Engine,
    context: AuthContext,
    thread_id: UUID,
    admision: ControlAdmision,
    recursos: ExitStack,
) -> EstadoProducto:
    """Reserva y recupera una conversación previamente autorizada."""
    try:
        with Session(engine) as session:
            require_thread_access(
                session,
                context,
                thread_id,
            )

    except SQLAlchemyError as exc:
        raise translate_db_error(exc) from None

    recursos.enter_context(
        admision.reservar_hilo(thread_id),
    )

    return recuperar_estado_operativo(
        thread_id,
        admision,
    )


def list_authorized_threads(
    session: Session,
    context: AuthContext,
) -> list[Conversation]:
    """Recupera las conversaciones visibles mediante API key."""
    _check_roles(
        context,
        ApiKeyRole.USER,
        ApiKeyRole.ADMIN,
    )

    if context.role == ApiKeyRole.ADMIN:
        return db.list_conversations(session)

    api_key_id = context.api_key_id

    if api_key_id is None:
        raise ApiError(ErrorCode.API_KEY_REQUIRED)

    return db.list_api_key_conversations(
        session,
        api_key_id,
    )


# =========================================================
# RECURSOS PROPIOS MEDIANTE SESIÓN
# =========================================================


def _require_session_user_id(
    context: AuthContext,
) -> UUID:
    """Exige una identidad de sesión sin selección de clave."""
    if (
        context.user_id is None
        or context.api_key_id is not None
        or context.role is not None
    ):
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    return context.user_id


def require_session_api_key(
    session: Session,
    context: AuthContext,
    api_key_id: UUID,
) -> ApiKey:
    """Recupera una clave ordinaria visible para su propietario."""
    user_id = _require_session_user_id(context)

    return require_owned_api_key(
        session,
        user_id,
        api_key_id,
        require_active=False,
    )


def list_owned_api_keys(
    session: Session,
    context: AuthContext,
) -> list[ApiKey]:
    """Lista las claves ordinarias no eliminadas del usuario."""
    user_id = _require_session_user_id(context)

    api_keys = db.list_user_api_keys(
        session,
        user_id,
    )

    return [
        api_key
        for api_key in api_keys
        if _is_owned_ordinary_key(
            api_key,
            user_id,
        )
    ]


def list_session_threads(
    session: Session,
    context: AuthContext,
    api_key_id: UUID,
) -> list[Conversation]:
    """Lista el historial de una clave propia no eliminada."""
    api_key = require_session_api_key(
        session,
        context,
        api_key_id,
    )

    return db.list_api_key_conversations(
        session,
        api_key.id,
    )


def require_session_thread_access(
    session: Session,
    context: AuthContext,
    api_key_id: UUID,
    thread_id: UUID,
) -> Conversation:
    """Comprueba el acceso al historial mediante una sesión."""
    api_key = require_session_api_key(
        session,
        context,
        api_key_id,
    )

    return _require_owned_thread(
        session,
        api_key.id,
        thread_id,
    )