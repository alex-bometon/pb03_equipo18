"""Pruebas de las dependencias de autenticación HTTP."""

from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from typing import Annotated
from unittest.mock import MagicMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlmodel import Session

import api.dependencies as dependencies
import api.security as security
from api.config import ApiSettings
from api.error_catalog import ERROR_CATALOG, ErrorCode
from api.errors import ApiError
from api.exception_handlers import register_exception_handlers
from api.mappers import (
    to_api_key_out,
    to_conversation_out,
    to_message_out,
)
from api.request_context import AuthContext
from api.schemas import (
    ApiKeyOut,
    ConversationOut,
    MessageOut,
)
from api.security import (
    SessionStore,
    generate_secret,
    hash_password,
    hash_secret,
)
from api.rate_limit import crear_limitador
from src import db
from src.enums import ApiKeyRole
from src.models import ApiKey, User


@pytest.fixture
def app() -> FastAPI:
    """Construye una aplicación aislada para las dependencias."""
    application = FastAPI()

    application.state.settings = ApiSettings()
    application.state.rate_limiter = crear_limitador(application.state.settings)
    application.state.engine = Mock(spec=Engine)
    application.state.session_store = SessionStore(ttl_seconds=28_800)

    register_exception_handlers(application)

    @application.get("/test/context")
    def context(
        auth: Annotated[
            AuthContext,
            Depends(dependencies.get_auth_context),
        ],
    ) -> AuthContext:
        return auth

    @application.get("/test/session")
    def user_session(
        auth: Annotated[
            AuthContext,
            Depends(dependencies.get_current_user),
        ],
    ) -> AuthContext:
        return auth

    @application.get("/test/original")
    def original_key(
        auth: Annotated[
            AuthContext,
            Depends(dependencies.get_current_api_key),
        ],
    ) -> AuthContext:
        return auth

    @application.get("/test/assistant")
    def assistant(
        auth: Annotated[
            AuthContext,
            Depends(dependencies.require_api_key_context),
        ],
    ) -> AuthContext:
        return auth

    @application.get("/test/settings")
    def settings(
        config: Annotated[
            ApiSettings,
            Depends(dependencies.get_settings),
        ],
    ) -> dict[str, int]:
        return {"port": config.PORT}

    @application.get("/test/image")
    def image(
        auth: Annotated[
            AuthContext,
            Depends(
                dependencies.require_roles(
                    ApiKeyRole.USER,
                    ApiKeyRole.ADMIN,
                ),
            ),
        ],
    ) -> AuthContext:
        return auth

    @application.get("/test/admin")
    def admin(
        auth: Annotated[
            AuthContext,
            Depends(dependencies.require_admin),
        ],
    ) -> AuthContext:
        return auth

    @application.get("/test/operation/{thread_id}")
    def operation(
        thread_id: UUID,
        auth: Annotated[
            AuthContext,
            Depends(
                dependencies.require_roles(
                    ApiKeyRole.FREE,
                    ApiKeyRole.USER,
                    ApiKeyRole.ADMIN,
                ),
            ),
        ],
        session: Annotated[
            Session,
            Depends(dependencies.get_session),
        ],
    ) -> ConversationOut:
        conversation = dependencies.require_thread_access(
            session,
            auth,
            thread_id,
        )

        return to_conversation_out(conversation)

    @application.get("/test/threads")
    def threads(
        auth: Annotated[
            AuthContext,
            Depends(
                dependencies.require_roles(
                    ApiKeyRole.USER,
                    ApiKeyRole.ADMIN,
                ),
            ),
        ],
        session: Annotated[
            Session,
            Depends(dependencies.get_session),
        ],
    ) -> list[ConversationOut]:
        conversations = dependencies.list_authorized_threads(
            session,
            auth,
        )

        return [
            to_conversation_out(conversation)
            for conversation in conversations
        ]

    @application.get("/test/threads/{thread_id}/messages")
    def messages(
        thread_id: UUID,
        auth: Annotated[
            AuthContext,
            Depends(
                dependencies.require_roles(
                    ApiKeyRole.USER,
                    ApiKeyRole.ADMIN,
                ),
            ),
        ],
        session: Annotated[
            Session,
            Depends(dependencies.get_session),
        ],
    ) -> list[MessageOut]:
        conversation = dependencies.require_thread_access(
            session,
            auth,
            thread_id,
        )

        return [
            to_message_out(message)
            for message in db.list_messages(
                session,
                conversation.id,
            )
        ]

    @application.get("/test/keys")
    def keys(
        auth: Annotated[
            AuthContext,
            Depends(dependencies.get_current_user),
        ],
        session: Annotated[
            Session,
            Depends(dependencies.get_session),
        ],
    ) -> list[ApiKeyOut]:
        api_keys = dependencies.list_owned_api_keys(
            session,
            auth,
        )

        return [
            to_api_key_out(api_key)
            for api_key in api_keys
        ]

    @application.get("/test/keys/{api_key_id}")
    def key(
        api_key_id: UUID,
        auth: Annotated[
            AuthContext,
            Depends(dependencies.get_current_user),
        ],
        session: Annotated[
            Session,
            Depends(dependencies.get_session),
        ],
    ) -> ApiKeyOut:
        api_key = dependencies.require_session_api_key(
            session,
            auth,
            api_key_id,
        )

        return to_api_key_out(api_key)

    @application.get("/test/keys/{api_key_id}/threads")
    def session_threads(
        api_key_id: UUID,
        auth: Annotated[
            AuthContext,
            Depends(dependencies.get_current_user),
        ],
        session: Annotated[
            Session,
            Depends(dependencies.get_session),
        ],
    ) -> list[ConversationOut]:
        conversations = dependencies.list_session_threads(
            session,
            auth,
            api_key_id,
        )

        return [
            to_conversation_out(conversation)
            for conversation in conversations
        ]

    @application.get(
        "/test/keys/{api_key_id}/threads/{thread_id}/messages",
    )
    def session_messages(
        api_key_id: UUID,
        thread_id: UUID,
        auth: Annotated[
            AuthContext,
            Depends(dependencies.get_current_user),
        ],
        session: Annotated[
            Session,
            Depends(dependencies.get_session),
        ],
    ) -> list[MessageOut]:
        conversation = dependencies.require_session_thread_access(
            session,
            auth,
            api_key_id,
            thread_id,
        )

        return [
            to_message_out(message)
            for message in db.list_messages(
                session,
                conversation.id,
            )
        ]

    return application


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """Proporciona un cliente HTTP sin arrancar el agente."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def no_database(
    monkeypatch: pytest.MonkeyPatch,
) -> Mock:
    """Detecta accesos SQL que deberían haberse evitado."""
    factory = Mock(
        side_effect=AssertionError(
            "No debería abrirse una sesión SQL.",
        ),
    )

    monkeypatch.setattr(
        dependencies,
        "Session",
        factory,
    )

    return factory


def assert_error(
    response: Response,
    code: ErrorCode,
) -> None:
    """Comprueba el contrato HTTP del error esperado."""
    definition = ERROR_CATALOG[code]

    assert response.status_code == definition.status_code

    assert response.json() == {
        "code": code.value,
        "message": definition.message,
        "request_id": response.headers["X-Request-ID"],
    }

    UUID(response.headers["X-Request-ID"])


# =========================================================
# CONTEXTO Y RECURSOS COMPARTIDOS
# =========================================================


def test_auth_context_immutable() -> None:
    """Impide modificar una identidad autenticada."""
    context = AuthContext(
        user_id=uuid4(),
        api_key_id=None,
        role=None,
    )

    with pytest.raises(FrozenInstanceError):
        context.role = ApiKeyRole.ADMIN


def test_settings_dependency(client: TestClient) -> None:
    """Recupera la configuración inicializada."""
    response = client.get("/test/settings")

    assert response.status_code == 200
    assert response.json() == {"port": 8000}


@pytest.mark.parametrize(
    ("resource", "path"),
    [
        ("settings", "/test/settings"),
        ("engine", "/test/context"),
        ("session_store", "/test/context"),
    ],
)
def test_missing_shared_resource(
    app: FastAPI,
    client: TestClient,
    resource: str,
    path: str,
) -> None:
    """Rechaza operaciones sin los recursos imprescindibles."""
    delattr(app.state, resource)

    response = client.get(path)

    assert_error(
        response,
        ErrorCode.SERVICE_NOT_CONFIGURED,
    )


def test_get_session_closes_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cierra la sesión SQL al finalizar la dependencia."""
    engine = Mock(spec=Engine)
    session = Mock(spec=Session)
    manager = MagicMock()

    manager.__enter__.return_value = session

    factory = Mock(return_value=manager)

    monkeypatch.setattr(
        dependencies,
        "Session",
        factory,
    )

    generator = dependencies.get_session(engine)

    assert next(generator) is session

    with pytest.raises(StopIteration):
        next(generator)

    factory.assert_called_once_with(engine)
    manager.__exit__.assert_called_once_with(
        None,
        None,
        None,
    )


# =========================================================
# CABECERAS Y MODALIDADES
# =========================================================


@pytest.mark.parametrize(
    ("path", "code", "challenge"),
    [
        (
            "/test/context",
            ErrorCode.API_KEY_REQUIRED,
            "APIKey, Bearer",
        ),
        (
            "/test/session",
            ErrorCode.INVALID_SESSION,
            "Bearer",
        ),
        (
            "/test/original",
            ErrorCode.API_KEY_REQUIRED,
            "APIKey",
        ),
        (
            "/test/assistant",
            ErrorCode.API_KEY_REQUIRED,
            "APIKey, Bearer",
        ),
    ],
)
def test_missing_credentials(
    client: TestClient,
    no_database: Mock,
    path: str,
    code: ErrorCode,
    challenge: str,
) -> None:
    """Rechaza peticiones sin la credencial requerida."""
    response = client.get(path)

    assert_error(response, code)

    assert response.headers["WWW-Authenticate"] == challenge

    no_database.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [
        {
            "X-API-Key": "clave-ficticia",
            "Authorization": "Bearer token-ficticio",
        },
        {
            "X-API-Key": "clave-ficticia",
            "X-API-Key-Id": str(UUID(int=1)),
        },
        {
            "X-API-Key": "clave-ficticia",
            "Authorization": "Bearer token-ficticio",
            "X-API-Key-Id": str(UUID(int=1)),
        },
        {
            "X-API-Key": "",
            "Authorization": "Bearer token-ficticio",
        },
    ],
)
@pytest.mark.parametrize(
    "path",
    [
        "/test/context",
        "/test/session",
        "/test/original",
        "/test/assistant",
    ],
)
def test_incompatible_credentials(
    client: TestClient,
    no_database: Mock,
    headers: dict[str, str],
    path: str,
) -> None:
    """Rechaza las combinaciones incompatibles de credenciales."""
    response = client.get(path, headers=headers)

    assert_error(
        response,
        ErrorCode.AMBIGUOUS_CREDENTIALS,
    )

    no_database.assert_not_called()


def test_selected_key_without_session(
    client: TestClient,
    no_database: Mock,
) -> None:
    """Impide seleccionar una clave sin una sesión."""
    response = client.get(
        "/test/context",
        headers={
            "X-API-Key-Id": str(uuid4()),
        },
    )

    assert_error(response, ErrorCode.INVALID_SESSION)

    no_database.assert_not_called()


@pytest.mark.parametrize(
    "header",
    [
        "X-API-Key",
        "Authorization",
        "X-API-Key-Id",
    ],
)
def test_duplicate_credentials(
    client: TestClient,
    no_database: Mock,
    header: str,
) -> None:
    """Rechaza cabeceras duplicadas, incluso con distinta caja."""
    response = client.get(
        "/test/context",
        headers=[
            (header, "valor-ficticio"),
            (header.lower(), "valor-ficticio"),
        ],
    )

    assert_error(
        response,
        ErrorCode.AMBIGUOUS_CREDENTIALS,
    )

    no_database.assert_not_called()


@pytest.mark.parametrize(
    "header",
    [
        "X-API-Key",
        "Authorization",
        "X-API-Key-Id",
    ],
)
def test_combined_header_values(
    client: TestClient,
    no_database: Mock,
    header: str,
) -> None:
    """Rechaza credenciales combinadas por intermediarios."""
    response = client.get(
        "/test/context",
        headers={
            header: "valor-uno, valor-dos",
        },
    )

    assert_error(
        response,
        ErrorCode.AMBIGUOUS_CREDENTIALS,
    )

    no_database.assert_not_called()


@pytest.mark.parametrize(
    "value",
    [
        "",
        "Bearer",
        "Bearer ",
        "Basic token-ficticio",
        "Bearer token adicional",
    ],
)
def test_invalid_authorization(
    client: TestClient,
    no_database: Mock,
    value: str,
) -> None:
    """Rechaza esquemas y formatos de sesión incompatibles."""
    response = client.get(
        "/test/session",
        headers={"Authorization": value},
    )

    assert_error(response, ErrorCode.INVALID_SESSION)

    no_database.assert_not_called()


@pytest.mark.parametrize("value", ["", " ", "clave ficticia"])
def test_invalid_original_key(
    client: TestClient,
    no_database: Mock,
    value: str,
) -> None:
    """Rechaza claves vacías o con espacios."""
    response = client.get(
        "/test/original",
        headers={"X-API-Key": value},
    )

    assert_error(response, ErrorCode.INVALID_API_KEY)

    no_database.assert_not_called()


def test_unknown_session(
    client: TestClient,
    no_database: Mock,
) -> None:
    """Rechaza una sesión que no existe en el almacenamiento."""
    response = client.get(
        "/test/session",
        headers={
            "Authorization": f"Bearer {generate_secret()}",
        },
    )

    assert_error(response, ErrorCode.INVALID_SESSION)

    no_database.assert_not_called()


def test_revoked_session(
    app: FastAPI,
    client: TestClient,
    no_database: Mock,
) -> None:
    """Rechaza sesiones invalidadas explícitamente."""
    store = app.state.session_store

    token, _ = store.create(uuid4())
    store.revoke(token)

    response = client.get(
        "/test/session",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert_error(response, ErrorCode.INVALID_SESSION)

    no_database.assert_not_called()


def test_expired_session(
    app: FastAPI,
    client: TestClient,
    no_database: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distingue una sesión caducada de una desconocida."""
    clock = Mock(return_value=1000.0)

    monkeypatch.setattr(
        security,
        "monotonic",
        clock,
    )

    store = SessionStore(ttl_seconds=1)
    app.state.session_store = store

    token, _ = store.create(uuid4())

    clock.return_value = 1001.0

    response = client.get(
        "/test/session",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert_error(response, ErrorCode.SESSION_EXPIRED)

    no_database.assert_not_called()


# =========================================================
# ERRORES RELACIONALES
# =========================================================


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (
            OperationalError(
                None,
                None,
                Exception("detalle-sensible-ficticio"),
            ),
            ErrorCode.SERVICE_UNAVAILABLE,
        ),
        (
            SQLAlchemyError("detalle-sensible-ficticio"),
            ErrorCode.INTERNAL_SERVER_ERROR,
        ),
    ],
)
def test_database_authentication_failure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    exception: SQLAlchemyError,
    code: ErrorCode,
) -> None:
    """No confunde los fallos SQL con credenciales incorrectas."""
    factory = Mock(side_effect=exception)

    monkeypatch.setattr(
        dependencies,
        "Session",
        factory,
    )

    secret = generate_secret()

    response = client.get(
        "/test/original",
        headers={"X-API-Key": secret},
    )

    assert_error(response, code)

    assert secret not in response.text
    assert "detalle-sensible-ficticio" not in response.text
    assert "WWW-Authenticate" not in response.headers


# =========================================================
# DOCUMENTACIÓN DE SEGURIDAD OPENAPI
# =========================================================


def test_openapi_security_schemes(
    client: TestClient,
) -> None:
    """Documenta los esquemas de autenticación admitidos."""
    document = client.get("/openapi.json").json()

    schemes = document["components"]["securitySchemes"]

    assert schemes["ApiKeyAuth"]["type"] == "apiKey"
    assert schemes["ApiKeyAuth"]["in"] == "header"
    assert schemes["ApiKeyAuth"]["name"] == "X-API-Key"

    assert schemes["SessionAuth"]["type"] == "http"
    assert schemes["SessionAuth"]["scheme"] == "bearer"


@pytest.mark.parametrize(
    ("path", "schemes"),
    [
        (
            "/test/context",
            {"ApiKeyAuth", "SessionAuth"},
        ),
        (
            "/test/assistant",
            {"ApiKeyAuth", "SessionAuth"},
        ),
        (
            "/test/session",
            {"SessionAuth"},
        ),
        (
            "/test/original",
            {"ApiKeyAuth"},
        ),
    ],
)
def test_openapi_route_security(
    client: TestClient,
    path: str,
    schemes: set[str],
) -> None:
    """Documenta únicamente los esquemas admitidos por ruta."""
    document = client.get("/openapi.json").json()

    requirements = document["paths"][path]["get"]["security"]

    assert all(
        len(requirement) == 1
        for requirement in requirements
    )

    assert {
        name
        for requirement in requirements
        for name in requirement
    } == schemes


def test_openapi_selected_key_header(
    client: TestClient,
) -> None:
    """Documenta la selección opcional de API key."""
    document = client.get("/openapi.json").json()

    operation = document["paths"]["/test/assistant"]["get"]

    parameter = next(
        parameter
        for parameter in operation["parameters"]
        if parameter["name"] == "X-API-Key-Id"
    )

    assert parameter["in"] == "header"
    assert parameter["required"] is False


# =========================================================
# INFRAESTRUCTURA DE INTEGRACIÓN
# =========================================================


@pytest.fixture
def auth_data(
    app: FastAPI,
    clean_db: Engine,
) -> dict[str, str]:
    """Prepara identidades y claves en PostgreSQL de pruebas."""
    app.state.engine = clean_db

    store = app.state.session_store

    data: dict[str, str] = {}

    password_hash = hash_password(
        "PasswordFicticiaSegura2026",
        rounds=4,
    )

    with Session(clean_db) as session:
        user = User(
            email="usuario@example.com",
            password_hash=password_hash,
        )

        other = User(
            email="otro@example.com",
            password_hash=password_hash,
        )

        db.create_user(session, user)
        db.create_user(session, other)
        session.flush()

        data["user_id"] = str(user.id)
        data["other_user_id"] = str(other.id)

        keys = (
            ("anon", ApiKeyRole.FREE, None),
            ("free", ApiKeyRole.FREE, user.id),
            ("user", ApiKeyRole.USER, user.id),
            ("admin", ApiKeyRole.ADMIN, user.id),
            ("other", ApiKeyRole.USER, other.id),
        )

        for name, role, owner_id in keys:
            secret = generate_secret()

            api_key = ApiKey(
                user_id=owner_id,
                role=role,
                key_hash=hash_secret(secret),
            )

            db.create_api_key(session, api_key)
            session.flush()

            data[f"secret_{name}"] = secret
            data[f"id_{name}"] = str(api_key.id)

        session.commit()

    token, _ = store.create(
        UUID(data["user_id"]),
    )

    other_token, _ = store.create(
        UUID(data["other_user_id"]),
    )

    data["token"] = token
    data["other_token"] = other_token

    return data


def _bearer_headers(
    data: dict[str, str],
    key_name: str | None = None,
) -> dict[str, str]:
    """Construye las cabeceras de sesión para las pruebas."""
    headers = {
        "Authorization": f"Bearer {data['token']}",
    }

    if key_name is not None:
        headers["X-API-Key-Id"] = data[f"id_{key_name}"]

    return headers


# =========================================================
# API KEYS ORIGINALES
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "role", "owner"),
    [
        ("anon", "free", None),
        ("free", "free", "user_id"),
        ("user", "user", "user_id"),
        ("admin", "admin", "user_id"),
        ("other", "user", "other_user_id"),
    ],
)
def test_original_key_authentication(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
    role: str,
    owner: str | None,
) -> None:
    """Recupera la identidad persistida de cada tipo de clave."""
    secret = auth_data[f"secret_{name}"]

    response = client.get(
        "/test/original",
        headers={"X-API-Key": secret},
    )

    assert response.status_code == 200

    assert response.json() == {
        "user_id": (
            auth_data[owner] if owner is not None else None
        ),
        "api_key_id": auth_data[f"id_{name}"],
        "role": role,
    }

    assert secret not in response.text
    assert hash_secret(secret) not in response.text


@pytest.mark.integration
def test_unknown_original_key(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Rechaza secretos sin un registro correspondiente."""
    response = client.get(
        "/test/original",
        headers={
            "X-API-Key": generate_secret(),
        },
    )

    assert_error(response, ErrorCode.INVALID_API_KEY)


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_inactive_original_key(
    client: TestClient,
    auth_data: dict[str, str],
    clean_db: Engine,
    deleted: bool,
) -> None:
    """Rechaza claves originales desactivadas o eliminadas."""
    with Session(clean_db) as session:
        api_key = db.get_api_key_by_id(
            session,
            UUID(auth_data["id_user"]),
        )

        assert api_key is not None

        if deleted:
            db.delete_api_key(api_key)
        else:
            db.set_api_key_active(api_key, False)

        session.commit()

    response = client.get(
        "/test/original",
        headers={
            "X-API-Key": auth_data["secret_user"],
        },
    )

    assert_error(response, ErrorCode.API_KEY_INACTIVE)


# =========================================================
# SESIONES DE USUARIO
# =========================================================


@pytest.mark.integration
def test_session_authentication(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Autentica la cuenta sin asignarle permisos de una clave."""
    response = client.get(
        "/test/session",
        headers=_bearer_headers(auth_data),
    )

    assert response.status_code == 200

    assert response.json() == {
        "user_id": auth_data["user_id"],
        "api_key_id": None,
        "role": None,
    }

    assert auth_data["token"] not in response.text


@pytest.mark.integration
def test_bearer_case_insensitive(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Acepta el nombre del esquema sin distinguir mayúsculas."""
    response = client.get(
        "/test/session",
        headers={
            "Authorization": f"bEaReR {auth_data['token']}",
        },
    )

    assert response.status_code == 200


@pytest.mark.integration
def test_session_without_existing_user(
    app: FastAPI,
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Rechaza sesiones cuyo usuario no existe en PostgreSQL."""
    token, _ = app.state.session_store.create(uuid4())

    response = client.get(
        "/test/session",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert_error(response, ErrorCode.INVALID_SESSION)


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_inactive_owner(
    client: TestClient,
    auth_data: dict[str, str],
    clean_db: Engine,
    deleted: bool,
) -> None:
    """Rechaza credenciales cuyo propietario está deshabilitado."""
    with Session(clean_db) as session:
        user = db.get_user_by_id(
            session,
            UUID(auth_data["user_id"]),
        )

        assert user is not None

        if deleted:
            db.delete_user(user)
        else:
            db.set_user_active(user, False)

        session.commit()

    credentials = (
        {
            "X-API-Key": auth_data["secret_free"],
        },
        {
            "X-API-Key": auth_data["secret_user"],
        },
        {
            "X-API-Key": auth_data["secret_admin"],
        },
        _bearer_headers(auth_data),
        _bearer_headers(auth_data, "user"),
    )

    for headers in credentials:
        response = client.get(
            "/test/context",
            headers=headers,
        )

        assert_error(response, ErrorCode.USER_INACTIVE)


# =========================================================
# SELECCIÓN DE API KEY MEDIANTE SESIÓN
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize("name", ["free", "user"])
def test_selected_key_authentication(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
) -> None:
    """Autentica una clave propia sin utilizar su secreto."""
    response = client.get(
        "/test/assistant",
        headers=_bearer_headers(auth_data, name),
    )

    assert response.status_code == 200

    assert response.json() == {
        "user_id": auth_data["user_id"],
        "api_key_id": auth_data[f"id_{name}"],
        "role": name,
    }


@pytest.mark.integration
@pytest.mark.parametrize("name", ["free", "user"])
def test_equivalent_key_identities(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
) -> None:
    """Obtiene la misma identidad con ambas modalidades."""
    original = client.get(
        "/test/assistant",
        headers={
            "X-API-Key": auth_data[f"secret_{name}"],
        },
    )

    selected = client.get(
        "/test/assistant",
        headers=_bearer_headers(auth_data, name),
    )

    assert original.status_code == 200
    assert selected.status_code == 200

    assert original.json() == selected.json()


@pytest.mark.integration
@pytest.mark.parametrize(
    "name",
    [
        "other",
        "anon",
        "admin",
    ],
)
def test_forbidden_selected_key(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
) -> None:
    """Oculta las claves ajenas, anónimas y administrativas."""
    response = client.get(
        "/test/assistant",
        headers=_bearer_headers(auth_data, name),
    )

    assert_error(response, ErrorCode.API_KEY_NOT_FOUND)


@pytest.mark.integration
def test_unknown_selected_key(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Rechaza una clave seleccionada inexistente."""
    headers = _bearer_headers(auth_data)
    headers["X-API-Key-Id"] = str(uuid4())

    response = client.get(
        "/test/assistant",
        headers=headers,
    )

    assert_error(response, ErrorCode.API_KEY_NOT_FOUND)


@pytest.mark.integration
@pytest.mark.parametrize("value", ["", "uuid-invalido"])
def test_invalid_selected_key_id(
    client: TestClient,
    auth_data: dict[str, str],
    value: str,
) -> None:
    """Rechaza identificadores de clave mal formados."""
    headers = _bearer_headers(auth_data)
    headers["X-API-Key-Id"] = value

    response = client.get(
        "/test/assistant",
        headers=headers,
    )

    assert_error(response, ErrorCode.VALIDATION_ERROR)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("deleted", "code"),
    [
        (False, ErrorCode.API_KEY_INACTIVE),
        (True, ErrorCode.API_KEY_NOT_FOUND),
    ],
)
def test_inactive_selected_key(
    client: TestClient,
    auth_data: dict[str, str],
    clean_db: Engine,
    deleted: bool,
    code: ErrorCode,
) -> None:
    """Aplica los estados permitidos para claves seleccionadas."""
    with Session(clean_db) as session:
        api_key = db.get_api_key_by_id(
            session,
            UUID(auth_data["id_user"]),
        )

        assert api_key is not None

        if deleted:
            db.delete_api_key(api_key)
        else:
            db.set_api_key_active(api_key, False)

        session.commit()

    response = client.get(
        "/test/assistant",
        headers=_bearer_headers(auth_data, "user"),
    )

    assert_error(response, code)


# =========================================================
# MODALIDADES REQUERIDAS
# =========================================================


@pytest.mark.integration
def test_assistant_requires_api_key(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Impide utilizar el asistente con una sesión sin clave."""
    response = client.get(
        "/test/assistant",
        headers=_bearer_headers(auth_data),
    )

    assert_error(response, ErrorCode.API_KEY_REQUIRED)

    assert response.headers["WWW-Authenticate"] == (
        "APIKey, Bearer"
    )


@pytest.mark.integration
def test_account_rejects_original_key(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Exige una sesión para las operaciones de cuenta."""
    response = client.get(
        "/test/session",
        headers={
            "X-API-Key": auth_data["secret_admin"],
        },
    )

    assert_error(
        response,
        ErrorCode.INSUFFICIENT_PERMISSIONS,
    )


@pytest.mark.integration
def test_account_rejects_selected_key(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Exige una sesión sin selección para gestionar la cuenta."""
    response = client.get(
        "/test/session",
        headers=_bearer_headers(auth_data, "user"),
    )

    assert_error(
        response,
        ErrorCode.INSUFFICIENT_PERMISSIONS,
    )


@pytest.mark.integration
@pytest.mark.parametrize("name", [None, "user"])
def test_original_key_required(
    client: TestClient,
    auth_data: dict[str, str],
    name: str | None,
) -> None:
    """Impide sustituir una clave original mediante una sesión."""
    response = client.get(
        "/test/original",
        headers=_bearer_headers(auth_data, name),
    )

    assert_error(
        response,
        ErrorCode.INSUFFICIENT_PERMISSIONS,
    )


@pytest.mark.integration
def test_session_revoked_during_authentication(
    app: FastAPI,
    client: TestClient,
    auth_data: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comprueba la vigencia de la sesión tras consultar SQL."""
    original_get_user = db.get_user_by_id

    store = app.state.session_store

    def revoke_after_query(*args, **kwargs) -> User | None:
        user = original_get_user(*args, **kwargs)

        store.revoke(auth_data["token"])

        return user

    monkeypatch.setattr(
        db,
        "get_user_by_id",
        revoke_after_query,
    )

    response = client.get(
        "/test/session",
        headers=_bearer_headers(auth_data),
    )

    assert_error(response, ErrorCode.INVALID_SESSION)


@pytest.mark.integration
def test_authentication_does_not_update_last_used(
    client: TestClient,
    auth_data: dict[str, str],
    clean_db: Engine,
) -> None:
    """No registra utilización antes de autorizar y admitir."""
    response = client.get(
        "/test/assistant",
        headers={
            "X-API-Key": auth_data["secret_user"],
        },
    )

    assert response.status_code == 200

    response = client.get(
        "/test/assistant",
        headers=_bearer_headers(auth_data, "user"),
    )

    assert response.status_code == 200

    with Session(clean_db) as session:
        api_key = db.get_api_key_by_id(
            session,
            UUID(auth_data["id_user"]),
        )

        assert api_key is not None
        assert api_key.last_used_at is None


# =========================================================
# AUTORIZACIÓN POR ROLES
# =========================================================


@pytest.mark.parametrize(
    ("role", "allowed"),
    [
        (ApiKeyRole.FREE, False),
        (ApiKeyRole.USER, True),
        (ApiKeyRole.ADMIN, True),
    ],
)
def test_require_roles(
    role: ApiKeyRole,
    allowed: bool,
) -> None:
    """Comprueba la autorización mediante roles permitidos."""
    context = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=role,
    )

    dependency = dependencies.require_roles(
        ApiKeyRole.USER,
        ApiKeyRole.ADMIN,
    )

    if allowed:
        assert dependency(context) is context

    else:
        with pytest.raises(ApiError) as exc_info:
            dependency(context)

        assert exc_info.value.code == (
            ErrorCode.INSUFFICIENT_PERMISSIONS
        )


def test_require_roles_without_api_key() -> None:
    """Impide autorizar operaciones con una sesión sin clave."""
    context = AuthContext(
        user_id=uuid4(),
        api_key_id=None,
        role=None,
    )

    dependency = dependencies.require_roles(
        ApiKeyRole.USER,
        ApiKeyRole.ADMIN,
    )

    with pytest.raises(ApiError) as exc_info:
        dependency(context)

    assert exc_info.value.code == ErrorCode.API_KEY_REQUIRED


def test_require_roles_without_allowed_roles() -> None:
    """No concede permisos si no se ha autorizado ningún rol."""
    context = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=ApiKeyRole.ADMIN,
    )

    dependency = dependencies.require_roles()

    with pytest.raises(ApiError) as exc_info:
        dependency(context)

    assert exc_info.value.code == (
        ErrorCode.INSUFFICIENT_PERMISSIONS
    )


@pytest.mark.parametrize(
    "role",
    [
        ApiKeyRole.FREE,
        ApiKeyRole.USER,
        ApiKeyRole.ADMIN,
    ],
)
def test_session_history_requires_session(
    role: ApiKeyRole,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No admite una identidad de clave como sesión ordinaria."""
    context = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=role,
    )

    query = Mock()

    monkeypatch.setattr(
        db,
        "get_api_key_by_id",
        query,
    )

    with pytest.raises(ApiError) as exc_info:
        dependencies.require_session_api_key(
            Mock(spec=Session),
            context,
            uuid4(),
        )

    assert exc_info.value.code == (
        ErrorCode.INSUFFICIENT_PERMISSIONS
    )

    query.assert_not_called()


def test_free_cannot_list_threads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rechaza el listado Free antes de consultar conversaciones."""
    context = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=ApiKeyRole.FREE,
    )

    query = Mock()

    monkeypatch.setattr(
        db,
        "list_api_key_conversations",
        query,
    )

    with pytest.raises(ApiError) as exc_info:
        dependencies.list_authorized_threads(
            Mock(spec=Session),
            context,
        )

    assert exc_info.value.code == (
        ErrorCode.INSUFFICIENT_PERMISSIONS
    )

    query.assert_not_called()


# =========================================================
# INFRAESTRUCTURA DE AUTORIZACIÓN
# =========================================================


@pytest.fixture
def thread_data(
    auth_data: dict[str, str],
    clean_db: Engine,
) -> dict[str, str]:
    """Prepara conversaciones de distintas claves y usuarios."""
    data = auth_data.copy()

    with Session(clean_db) as session:
        secret = generate_secret()

        second_key = ApiKey(
            user_id=UUID(data["user_id"]),
            role=ApiKeyRole.USER,
            key_hash=hash_secret(secret),
        )

        db.create_api_key(session, second_key)
        session.flush()

        data["id_user2"] = str(second_key.id)
        data["secret_user2"] = secret

        for name in (
            "anon",
            "free",
            "user",
            "user2",
            "other",
            "admin",
        ):
            thread_id = uuid4()

            db.create_conversation(
                session,
                thread_id,
                UUID(data[f"id_{name}"]),
            )

            session.flush()

            db.save_turn(
                session,
                thread_id,
                1,
                f"Pregunta {name}",
                f"Respuesta {name}",
            )

            data[f"thread_{name}"] = str(thread_id)

        session.commit()

    return data


# =========================================================
# PERMISOS MULTIMODALES Y ADMINISTRATIVOS
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "expected_status"),
    [
        ("anon", 403),
        ("free", 403),
        ("user", 200),
        ("other", 200),
        ("admin", 200),
    ],
)
def test_image_permissions(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
    expected_status: int,
) -> None:
    """Aplica los roles permitidos para consultas multimodales."""
    response = client.get(
        "/test/image",
        headers={
            "X-API-Key": auth_data[f"secret_{name}"],
        },
    )

    assert response.status_code == expected_status

    if expected_status == 403:
        assert_error(
            response,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "expected_status"),
    [
        ("free", 403),
        ("user", 200),
    ],
)
def test_image_permissions_selected_key(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
    expected_status: int,
) -> None:
    """Conserva los permisos al seleccionar una clave propia."""
    response = client.get(
        "/test/image",
        headers=_bearer_headers(auth_data, name),
    )

    assert response.status_code == expected_status

    if expected_status == 403:
        assert_error(
            response,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "expected_status"),
    [
        ("anon", 403),
        ("free", 403),
        ("user", 403),
        ("other", 403),
        ("admin", 200),
    ],
)
def test_admin_permissions(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
    expected_status: int,
) -> None:
    """Restringe la administración a claves Admin originales."""
    response = client.get(
        "/test/admin",
        headers={
            "X-API-Key": auth_data[f"secret_{name}"],
        },
    )

    assert response.status_code == expected_status

    if expected_status == 403:
        assert_error(
            response,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
        )


@pytest.mark.integration
@pytest.mark.parametrize("name", [None, "free", "user"])
def test_admin_rejects_session(
    client: TestClient,
    auth_data: dict[str, str],
    name: str | None,
) -> None:
    """No concede privilegios Admin mediante sesión."""
    response = client.get(
        "/test/admin",
        headers=_bearer_headers(auth_data, name),
    )

    assert_error(
        response,
        ErrorCode.INSUFFICIENT_PERMISSIONS,
    )


@pytest.mark.integration
def test_admin_key_cannot_be_selected(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Impide seleccionar una clave Admin mediante sesión."""
    response = client.get(
        "/test/admin",
        headers=_bearer_headers(auth_data, "admin"),
    )

    assert_error(response, ErrorCode.API_KEY_NOT_FOUND)


def test_admin_openapi_security(
    client: TestClient,
) -> None:
    """Documenta exclusivamente la autenticación por API key."""
    document = client.get("/openapi.json").json()

    operation = document["paths"]["/test/admin"]["get"]

    assert operation["security"] == [
        {"ApiKeyAuth": []},
    ]


# =========================================================
# PROPIEDAD DE CONVERSACIONES
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("credential", "target", "allowed"),
    [
        ("anon", "anon", True),
        ("anon", "free", False),
        ("free", "free", True),
        ("free", "anon", False),
        ("free", "user", False),
        ("user", "user", True),
        ("user", "free", False),
        ("user", "user2", False),
        ("user2", "user", False),
        ("user2", "user2", True),
        ("user", "other", False),
        ("other", "user", False),
        ("other", "other", True),
        ("admin", "anon", True),
        ("admin", "free", True),
        ("admin", "user", True),
        ("admin", "user2", True),
        ("admin", "other", True),
        ("admin", "admin", True),
    ],
)
def test_thread_access(
    client: TestClient,
    thread_data: dict[str, str],
    credential: str,
    target: str,
    allowed: bool,
) -> None:
    """Comprueba el aislamiento operativo de las conversaciones."""
    thread_id = thread_data[f"thread_{target}"]

    response = client.get(
        f"/test/operation/{thread_id}",
        headers={
            "X-API-Key": thread_data[f"secret_{credential}"],
        },
    )

    if allowed:
        assert response.status_code == 200
        assert response.json()["thread_id"] == thread_id

        assert response.json()["api_key_id"] == (
            thread_data[f"id_{target}"]
        )

    else:
        assert_error(response, ErrorCode.THREAD_NOT_FOUND)


@pytest.mark.integration
@pytest.mark.parametrize(
    ("credential", "target", "allowed"),
    [
        ("free", "free", True),
        ("free", "user", False),
        ("user", "user", True),
        ("user", "user2", False),
        ("user2", "user2", True),
        ("user2", "other", False),
    ],
)
def test_selected_key_thread_access(
    client: TestClient,
    thread_data: dict[str, str],
    credential: str,
    target: str,
    allowed: bool,
) -> None:
    """Conserva el aislamiento mediante una clave seleccionada."""
    thread_id = thread_data[f"thread_{target}"]

    response = client.get(
        f"/test/operation/{thread_id}",
        headers=_bearer_headers(
            thread_data,
            credential,
        ),
    )

    if allowed:
        assert response.status_code == 200
        assert response.json()["thread_id"] == thread_id

    else:
        assert_error(response, ErrorCode.THREAD_NOT_FOUND)


@pytest.mark.integration
@pytest.mark.parametrize(
    "credential",
    [
        "anon",
        "free",
        "user",
        "admin",
    ],
)
def test_unknown_thread(
    client: TestClient,
    auth_data: dict[str, str],
    credential: str,
) -> None:
    """Aplica el mismo error a conversaciones inexistentes."""
    response = client.get(
        f"/test/operation/{uuid4()}",
        headers={
            "X-API-Key": auth_data[f"secret_{credential}"],
        },
    )

    assert_error(response, ErrorCode.THREAD_NOT_FOUND)


# =========================================================
# HISTORIAL MEDIANTE API KEY
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("credential", "expected"),
    [
        ("user", {"user"}),
        ("user2", {"user2"}),
        ("other", {"other"}),
        (
            "admin",
            {
                "anon",
                "free",
                "user",
                "user2",
                "other",
                "admin",
            },
        ),
    ],
)
def test_authorized_thread_listing(
    client: TestClient,
    thread_data: dict[str, str],
    credential: str,
    expected: set[str],
) -> None:
    """Lista exclusivamente las conversaciones autorizadas."""
    response = client.get(
        "/test/threads",
        headers={
            "X-API-Key": thread_data[f"secret_{credential}"],
        },
    )

    assert response.status_code == 200

    thread_ids = [
        item["thread_id"]
        for item in response.json()
    ]

    expected_ids = {
        thread_data[f"thread_{name}"]
        for name in expected
    }

    assert set(thread_ids) == expected_ids
    assert len(thread_ids) == len(expected_ids)


@pytest.mark.integration
def test_selected_user_thread_listing(
    client: TestClient,
    thread_data: dict[str, str],
) -> None:
    """Limita el listado a la clave User seleccionada."""
    response = client.get(
        "/test/threads",
        headers=_bearer_headers(
            thread_data,
            "user",
        ),
    )

    assert response.status_code == 200

    assert [
        item["thread_id"]
        for item in response.json()
    ] == [
        thread_data["thread_user"],
    ]


@pytest.mark.integration
@pytest.mark.parametrize(
    "credential",
    [
        "anon",
        "free",
        "selected_free",
    ],
)
def test_free_history_denied(
    client: TestClient,
    thread_data: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    credential: str,
) -> None:
    """Deniega el historial Free antes de consultar sus datos."""
    queries = {
        name: Mock()
        for name in (
            "list_api_key_conversations",
            "list_conversations",
            "get_conversation_by_id",
            "get_conversation_by_owner",
            "list_messages",
        )
    }

    for name, query in queries.items():
        monkeypatch.setattr(db, name, query)

    if credential == "selected_free":
        headers = _bearer_headers(
            thread_data,
            "free",
        )

    else:
        headers = {
            "X-API-Key": thread_data[f"secret_{credential}"],
        }

    thread_id = thread_data["thread_free"]

    for path in (
        "/test/threads",
        f"/test/threads/{thread_id}/messages",
    ):
        response = client.get(
            path,
            headers=headers,
        )

        assert_error(
            response,
            ErrorCode.INSUFFICIENT_PERMISSIONS,
        )

    for query in queries.values():
        query.assert_not_called()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("credential", "target", "allowed"),
    [
        ("user", "user", True),
        ("user", "user2", False),
        ("user", "free", False),
        ("user", "other", False),
        ("admin", "anon", True),
        ("admin", "other", True),
    ],
)
def test_authorized_messages(
    client: TestClient,
    thread_data: dict[str, str],
    credential: str,
    target: str,
    allowed: bool,
) -> None:
    """Protege el contenido de las conversaciones ajenas."""
    thread_id = thread_data[f"thread_{target}"]

    response = client.get(
        f"/test/threads/{thread_id}/messages",
        headers={
            "X-API-Key": thread_data[f"secret_{credential}"],
        },
    )

    if not allowed:
        assert_error(response, ErrorCode.THREAD_NOT_FOUND)
        return

    assert response.status_code == 200

    messages = response.json()

    assert len(messages) == 2

    assert [
        message["role"]
        for message in messages
    ] == ["user", "assistant"]

    assert [
        message["content"]
        for message in messages
    ] == [
        f"Pregunta {target}",
        f"Respuesta {target}",
    ]


# =========================================================
# API KEYS PROPIAS MEDIANTE SESIÓN
# =========================================================


@pytest.mark.integration
def test_owned_key_listing(
    client: TestClient,
    thread_data: dict[str, str],
) -> None:
    """Excluye claves ajenas, anónimas y administrativas."""
    response = client.get(
        "/test/keys",
        headers=_bearer_headers(thread_data),
    )

    assert response.status_code == 200

    api_keys = response.json()

    assert {
        item["id"]
        for item in api_keys
    } == {
        thread_data["id_free"],
        thread_data["id_user"],
        thread_data["id_user2"],
    }

    assert len(api_keys) == 3

    for api_key in api_keys:
        assert api_key["user_id"] == thread_data["user_id"]
        assert api_key["role"] in {"free", "user"}
        assert "key_hash" not in api_key
        assert "api_key" not in api_key


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "allowed"),
    [
        ("free", True),
        ("user", True),
        ("admin", False),
        ("anon", False),
        ("other", False),
    ],
)
def test_owned_key_detail(
    client: TestClient,
    auth_data: dict[str, str],
    name: str,
    allowed: bool,
) -> None:
    """Protege la consulta individual de API keys."""
    api_key_id = auth_data[f"id_{name}"]

    response = client.get(
        f"/test/keys/{api_key_id}",
        headers=_bearer_headers(auth_data),
    )

    if allowed:
        assert response.status_code == 200

        data = response.json()

        assert data["id"] == api_key_id
        assert data["user_id"] == auth_data["user_id"]
        assert "key_hash" not in data
        assert "api_key" not in data

    else:
        assert_error(response, ErrorCode.API_KEY_NOT_FOUND)


# =========================================================
# HISTORIAL MEDIANTE SESIÓN
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    "name",
    [
        "free",
        "user",
        "user2",
    ],
)
def test_session_thread_listing(
    client: TestClient,
    thread_data: dict[str, str],
    name: str,
) -> None:
    """Permite consultar el historial de cada clave propia."""
    api_key_id = thread_data[f"id_{name}"]

    response = client.get(
        f"/test/keys/{api_key_id}/threads",
        headers=_bearer_headers(thread_data),
    )

    assert response.status_code == 200

    conversations = response.json()

    assert len(conversations) == 1

    assert conversations[0]["thread_id"] == (
        thread_data[f"thread_{name}"]
    )

    assert conversations[0]["api_key_id"] == api_key_id


@pytest.mark.integration
@pytest.mark.parametrize(
    ("key_name", "target", "expected_error"),
    [
        ("free", "free", None),
        ("user", "user", None),
        ("user2", "user2", None),
        ("free", "user", ErrorCode.THREAD_NOT_FOUND),
        ("user", "user2", ErrorCode.THREAD_NOT_FOUND),
        ("user", "other", ErrorCode.THREAD_NOT_FOUND),
        ("other", "other", ErrorCode.API_KEY_NOT_FOUND),
        ("anon", "anon", ErrorCode.API_KEY_NOT_FOUND),
        ("admin", "admin", ErrorCode.API_KEY_NOT_FOUND),
    ],
)
def test_session_messages_access(
    client: TestClient,
    thread_data: dict[str, str],
    key_name: str,
    target: str,
    expected_error: ErrorCode | None,
) -> None:
    """Comprueba tanto la propiedad de la clave como del hilo."""
    api_key_id = thread_data[f"id_{key_name}"]
    thread_id = thread_data[f"thread_{target}"]

    path = (
        f"/test/keys/{api_key_id}"
        f"/threads/{thread_id}/messages"
    )

    response = client.get(
        path,
        headers=_bearer_headers(thread_data),
    )

    if expected_error is not None:
        assert_error(response, expected_error)
        return

    assert response.status_code == 200

    assert [
        message["content"]
        for message in response.json()
    ] == [
        f"Pregunta {target}",
        f"Respuesta {target}",
    ]


@pytest.mark.integration
@pytest.mark.parametrize(
    "name",
    [
        "anon",
        "other",
        "admin",
    ],
)
def test_session_history_checks_key_first(
    client: TestClient,
    thread_data: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
) -> None:
    """No consulta conversaciones de claves no autorizadas."""
    query = Mock()

    monkeypatch.setattr(
        db,
        "get_conversation_by_owner",
        query,
    )

    api_key_id = thread_data[f"id_{name}"]
    thread_id = thread_data[f"thread_{name}"]

    path = (
        f"/test/keys/{api_key_id}"
        f"/threads/{thread_id}/messages"
    )

    response = client.get(
        path,
        headers=_bearer_headers(thread_data),
    )

    assert_error(response, ErrorCode.API_KEY_NOT_FOUND)

    query.assert_not_called()


@pytest.mark.integration
def test_session_unknown_key(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Oculta las claves inexistentes en consultas ordinarias."""
    response = client.get(
        f"/test/keys/{uuid4()}/threads",
        headers=_bearer_headers(auth_data),
    )

    assert_error(response, ErrorCode.API_KEY_NOT_FOUND)


@pytest.mark.integration
def test_session_unknown_thread(
    client: TestClient,
    auth_data: dict[str, str],
) -> None:
    """Rechaza hilos inexistentes de una clave autorizada."""
    api_key_id = auth_data["id_user"]

    path = (
        f"/test/keys/{api_key_id}"
        f"/threads/{uuid4()}/messages"
    )

    response = client.get(
        path,
        headers=_bearer_headers(auth_data),
    )

    assert_error(response, ErrorCode.THREAD_NOT_FOUND)


@pytest.mark.integration
def test_empty_authorized_history(
    client: TestClient,
    auth_data: dict[str, str],
    clean_db: Engine,
) -> None:
    """Distingue un historial vacío de un recurso inexistente."""
    api_key_id = auth_data["id_user"]
    thread_id = uuid4()

    with Session(clean_db) as session:
        db.create_conversation(
            session,
            thread_id,
            UUID(api_key_id),
        )

        session.commit()

    response = client.get(
        f"/test/threads/{thread_id}/messages",
        headers={
            "X-API-Key": auth_data["secret_user"],
        },
    )

    assert response.status_code == 200
    assert response.json() == []


# =========================================================
# ESTADOS DE CREDENCIALES E HISTORIAL
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize("name", ["free", "user"])
@pytest.mark.parametrize("deleted", [False, True])
def test_session_history_key_states(
    client: TestClient,
    thread_data: dict[str, str],
    clean_db: Engine,
    name: str,
    deleted: bool,
) -> None:
    """Aplica las restricciones de historial según el estado."""
    api_key_id = thread_data[f"id_{name}"]
    thread_id = thread_data[f"thread_{name}"]

    with Session(clean_db) as session:
        api_key = db.get_api_key_by_id(
            session,
            UUID(api_key_id),
        )

        assert api_key is not None

        if deleted:
            db.delete_api_key(api_key)
        else:
            db.set_api_key_active(api_key, False)

        session.commit()

    headers = _bearer_headers(thread_data)

    key_path = f"/test/keys/{api_key_id}"
    threads_path = f"{key_path}/threads"
    messages_path = f"{threads_path}/{thread_id}/messages"

    for path in (
        key_path,
        threads_path,
        messages_path,
    ):
        response = client.get(
            path,
            headers=headers,
        )

        if deleted:
            assert_error(
                response,
                ErrorCode.API_KEY_NOT_FOUND,
            )

        else:
            assert response.status_code == 200

    response = client.get(
        "/test/keys",
        headers=headers,
    )

    assert response.status_code == 200

    visible_ids = {
        item["id"]
        for item in response.json()
    }

    assert (api_key_id in visible_ids) == (not deleted)


@pytest.mark.integration
@pytest.mark.parametrize("deleted", [False, True])
def test_admin_history_revoked_key(
    client: TestClient,
    thread_data: dict[str, str],
    clean_db: Engine,
    deleted: bool,
) -> None:
    """Conserva el acceso global al historial de claves revocadas."""
    api_key_id = thread_data["id_other"]
    thread_id = thread_data["thread_other"]

    with Session(clean_db) as session:
        api_key = db.get_api_key_by_id(
            session,
            UUID(api_key_id),
        )

        assert api_key is not None

        if deleted:
            db.delete_api_key(api_key)
        else:
            db.set_api_key_active(api_key, False)

        session.commit()

    headers = {
        "X-API-Key": thread_data["secret_admin"],
    }

    listing = client.get(
        "/test/threads",
        headers=headers,
    )

    assert listing.status_code == 200

    assert thread_id in {
        item["thread_id"]
        for item in listing.json()
    }

    response = client.get(
        f"/test/threads/{thread_id}/messages",
        headers=headers,
    )

    assert response.status_code == 200

    assert len(response.json()) == 2

    with Session(clean_db) as session:
        conversation = db.get_conversation_by_id(
            session,
            UUID(thread_id),
        )

        api_key = db.get_api_key_by_id(
            session,
            UUID(api_key_id),
        )

        assert conversation is not None
        assert api_key is not None

        assert conversation.api_key_id == UUID(api_key_id)
        assert api_key.is_active is False
        assert (api_key.deleted_at is not None) == deleted


# =========================================================
# ROBUSTEZ DE LA AUTORIZACIÓN
# =========================================================


@pytest.mark.integration
@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (
            OperationalError(
                None,
                None,
                Exception("detalle-sensible-ficticio"),
            ),
            ErrorCode.SERVICE_UNAVAILABLE,
        ),
        (
            SQLAlchemyError("detalle-sensible-ficticio"),
            ErrorCode.INTERNAL_SERVER_ERROR,
        ),
    ],
)
def test_authorization_database_failure(
    client: TestClient,
    thread_data: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    exception: SQLAlchemyError,
    code: ErrorCode,
) -> None:
    """No confunde fallos relacionales con recursos inexistentes."""
    query = Mock(side_effect=exception)

    monkeypatch.setattr(
        db,
        "get_conversation_by_owner",
        query,
    )

    secret = thread_data["secret_user"]
    thread_id = thread_data["thread_user"]

    response = client.get(
        f"/test/operation/{thread_id}",
        headers={
            "X-API-Key": secret,
        },
    )

    assert_error(response, code)

    query.assert_called_once()

    assert secret not in response.text
    assert "detalle-sensible-ficticio" not in response.text

def test_rate_limit_modalidades_compartidas(
    app,
    client,
    monkeypatch,
):
    """Comparte el límite HTTP entre modalidades de una clave."""
    settings = ApiSettings(RATE_LIMIT_PER_MINUTE=1)

    app.state.settings = settings
    app.state.rate_limiter = crear_limitador(settings)

    contexto = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=ApiKeyRole.USER,
    )

    monkeypatch.setattr(
        dependencies,
        "_authenticate_original_key",
        Mock(return_value=contexto),
    )

    monkeypatch.setattr(
        dependencies,
        "_authenticate_user_session",
        Mock(return_value=contexto),
    )

    primera = client.get(
        "/test/context",
        headers={"X-API-Key": "clave-ficticia"},
    )

    assert primera.status_code == 200

    segunda = client.get(
        "/test/context",
        headers={
            "Authorization": "Bearer token-ficticio",
            "X-API-Key-Id": str(contexto.api_key_id),
        },
    )

    assert_error(segunda, ErrorCode.RATE_LIMIT_EXCEEDED)

    assert int(segunda.headers["Retry-After"]) > 0


def test_autenticacion_invalida_no_consume_rate_limit(
    app,
    client,
    monkeypatch,
):
    """Solo registra peticiones cuya autenticación es válida."""
    settings = ApiSettings(RATE_LIMIT_PER_MINUTE=1)

    app.state.settings = settings
    app.state.rate_limiter = crear_limitador(settings)

    contexto = AuthContext(
        user_id=None,
        api_key_id=uuid4(),
        role=ApiKeyRole.FREE,
    )

    autenticacion = Mock(
        side_effect=[
            ApiError(ErrorCode.INVALID_API_KEY),
            contexto,
            contexto,
        ],
    )

    monkeypatch.setattr(
        dependencies,
        "_authenticate_original_key",
        autenticacion,
    )

    headers = {"X-API-Key": "clave-ficticia"}

    primera = client.get("/test/context", headers=headers)
    assert_error(primera, ErrorCode.INVALID_API_KEY)

    segunda = client.get("/test/context", headers=headers)
    assert segunda.status_code == 200

    tercera = client.get("/test/context", headers=headers)
    assert_error(tercera, ErrorCode.RATE_LIMIT_EXCEEDED)