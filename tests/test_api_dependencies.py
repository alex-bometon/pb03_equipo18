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
from api.exception_handlers import register_exception_handlers
from api.request_context import AuthContext
from api.security import (
    SessionStore,
    generate_secret,
    hash_password,
    hash_secret,
)
from src import db
from src.enums import ApiKeyRole
from src.models import ApiKey, User


@pytest.fixture
def app() -> FastAPI:
    """Construye una aplicación aislada para las dependencias."""
    application = FastAPI()

    application.state.settings = ApiSettings()
    application.state.engine = Mock(spec=Engine)
    application.state.session_store = SessionStore(
        ttl_seconds=28_800,
    )

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