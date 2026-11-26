"""Dependencias de autenticación HTTP de ReciclaTIA."""

import re
from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

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
from src import db
from src.enums import ApiKeyRole


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

    api_key = db.get_api_key_by_id(
        session,
        api_key_id,
    )

    if (
        api_key is None
        or api_key.user_id != user_id
        or api_key.role not in (
            ApiKeyRole.FREE,
            ApiKeyRole.USER,
        )
        or api_key.deleted_at is not None
    ):
        raise ApiError(ErrorCode.API_KEY_NOT_FOUND)

    if not api_key.is_active:
        raise ApiError(ErrorCode.API_KEY_INACTIVE)

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
    """Selecciona y ejecuta la modalidad de autenticación."""
    api_key, authorization, selected_key_id = (
        _read_credentials(request)
    )

    if api_key is not None:
        return _authenticate_original_key(
            engine,
            api_key,
        )

    if authorization is not None:
        token = _parse_bearer(authorization)

        return _authenticate_user_session(
            engine,
            store,
            token,
            selected_key_id,
        )

    raise ApiError(missing_code)


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