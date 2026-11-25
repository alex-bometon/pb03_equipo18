"""Pruebas de los contratos de cuentas y credenciales."""

from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from api.base import SecureBaseModel
from api.config import ApiSettings
from api.schemas import (
    ActiveStatusIn,
    AdminApiKeyCreateIn,
    ApiKeyCreatedOut,
    ApiKeyCreateIn,
    ApiKeyOut,
    ApiSchema,
    LoginIn,
    LoginOut,
    PasswordChangeIn,
    RegisterIn,
    UserOut,
)
from src.enums import ApiKeyRole


EMAIL = "usuario@example.com"
PASSWORD = "Password1234"

USER_ID = uuid4()
KEY_ID = uuid4()

CREATED_AT = datetime.now(timezone.utc)


@pytest.fixture
def usuario_valido():
    return {
        "id": USER_ID,
        "email": EMAIL,
        "created_at": CREATED_AT,
        "is_active": True,
    }


@pytest.fixture
def api_key_valida():
    return {
        "id": KEY_ID,
        "role": ApiKeyRole.USER,
        "user_id": USER_ID,
        "is_active": True,
        "created_at": CREATED_AT,
        "last_used_at": None,
        "deleted_at": None,
    }


# =========================================================
# CONFIGURACIÓN COMPARTIDA
# =========================================================

@pytest.mark.parametrize(
    "modelo",
    [SecureBaseModel, ApiSchema, ApiSettings],
)
def test_modelos_comparten_configuracion_segura(modelo):
    assert modelo.model_config["extra"] == "forbid"

    assert modelo.model_config["hide_input_in_errors"] is True


def test_api_settings_conserva_configuracion_especifica():
    assert ApiSettings.model_config["frozen"] is True


def test_api_schema_no_hereda_frozen():
    assert not ApiSchema.model_config.get("frozen", False)


# =========================================================
# EMAIL
# =========================================================

@pytest.mark.parametrize(
    "email, esperado",
    [
        (
            "  USUARIO@EXAMPLE.COM  ",
            "usuario@example.com",
        ),
        (
            "Usuario+Trabajo@example.com",
            "usuario+trabajo@example.com",
        ),
        (
            "Nombre.Apellido@example.com",
            "nombre.apellido@example.com",
        ),
    ],
)
@pytest.mark.parametrize("modelo", [RegisterIn, LoginIn])
def test_normalizacion_email(modelo, email, esperado):
    entrada = modelo(
        email=email,
        password=PASSWORD,
    )

    assert entrada.email == esperado


@pytest.mark.parametrize(
    "email",
    [
        "",
        "   ",
        "usuario",
        "usuario@",
        "@example.com",
        "usuario@@example.com",
        "usuario nombre@example.com",
        "usuario..nombre@example.com",
        "a" * 250 + "@example.com",
        123,
        True,
        None,
    ],
)
@pytest.mark.parametrize("modelo", [RegisterIn, LoginIn])
def test_rechaza_email_invalido(modelo, email):
    with pytest.raises(ValidationError):
        modelo(
            email=email,
            password=PASSWORD,
        )


# =========================================================
# CONTRASEÑAS
# =========================================================

@pytest.mark.parametrize(
    "password",
    [
        "a" * 12,
        "a" * 72,
        "ñ" * 36,
        "A" * 11 + "!",
    ],
)
def test_register_acepta_password_valida(password):
    entrada = RegisterIn(
        email=EMAIL,
        password=password,
    )

    assert entrada.password.get_secret_value() == password


@pytest.mark.parametrize(
    "password",
    [
        "",
        "a" * 11,
        "a" * 73,
        "ñ" * 37,
        "Password 1234",
        "Password1234 ",
        "Password\t1234",
        "Password\n1234",
        123,
        True,
        None,
        b"Password1234",
    ],
)
def test_register_rechaza_password_invalida(password):
    with pytest.raises(ValidationError):
        RegisterIn(
            email=EMAIL,
            password=password,
        )


@pytest.mark.parametrize(
    "password",
    ["", "corta", " password anterior "],
)
def test_login_no_aplica_politica_de_creacion(password):
    entrada = LoginIn(
        email=EMAIL,
        password=password,
    )

    assert entrada.password.get_secret_value() == password


@pytest.mark.parametrize(
    "password",
    ["a" * 73, "ñ" * 37, 123, True, None, b"password"],
)
def test_login_rechaza_password_incompatible(password):
    with pytest.raises(ValidationError):
        LoginIn(
            email=EMAIL,
            password=password,
        )


def test_password_change_aplica_politicas_diferentes():
    entrada = PasswordChangeIn(
        current_password="anterior",
        new_password=PASSWORD,
    )

    assert entrada.current_password.get_secret_value() == "anterior"

    assert entrada.new_password.get_secret_value() == PASSWORD


@pytest.mark.parametrize(
    "password",
    ["corta", "a" * 73, "ñ" * 37, "Password 1234"],
)
def test_password_change_rechaza_nueva_password_invalida(
    password,
):
    with pytest.raises(ValidationError):
        PasswordChangeIn(
            current_password=PASSWORD,
            new_password=password,
        )


def test_password_change_rechaza_password_actual_incompatible():
    with pytest.raises(ValidationError):
        PasswordChangeIn(
            current_password="a" * 73,
            new_password=PASSWORD,
        )


def test_register_rechaza_confirmacion_password():
    with pytest.raises(ValidationError):
        RegisterIn(
            email=EMAIL,
            password=PASSWORD,
            password_confirmation=PASSWORD,
        )


# =========================================================
# PROTECCIÓN DE CREDENCIALES
# =========================================================

@pytest.mark.parametrize("modelo", [RegisterIn, LoginIn])
def test_password_no_aparece_en_representaciones(modelo):
    entrada = modelo(
        email=EMAIL,
        password=PASSWORD,
    )

    assert PASSWORD not in repr(entrada)

    assert PASSWORD not in str(entrada)

    assert PASSWORD not in entrada.model_dump_json()


def test_password_change_oculta_ambas_passwords():
    entrada = PasswordChangeIn(
        current_password="Anterior1234",
        new_password=PASSWORD,
    )

    for representacion in (
        repr(entrada),
        str(entrada),
        entrada.model_dump_json(),
    ):
        assert "Anterior1234" not in representacion

        assert PASSWORD not in representacion


def test_error_validacion_no_muestra_password_original():
    password = "Password invalida 1234"

    with pytest.raises(ValidationError) as exc_info:
        RegisterIn(
            email=EMAIL,
            password=password,
        )

    assert password not in str(exc_info.value)


# =========================================================
# EMISIÓN DE API KEYS
# =========================================================

def test_api_key_create_role_predeterminado():
    entrada = ApiKeyCreateIn()

    assert entrada.role == ApiKeyRole.FREE


@pytest.mark.parametrize("role", ["free", "user"])
def test_api_key_create_acepta_roles_validos(role):
    entrada = ApiKeyCreateIn(role=role)

    assert isinstance(entrada.role, ApiKeyRole)

    assert entrada.role.value == role


@pytest.mark.parametrize(
    "role",
    ["admin", "desconocido", True, None],
)
@pytest.mark.parametrize(
    "modelo",
    [ApiKeyCreateIn, AdminApiKeyCreateIn],
)
def test_rechaza_roles_no_emitibles(modelo, role):
    with pytest.raises(ValidationError):
        modelo(role=role)


def test_api_key_create_rechaza_propietario():
    with pytest.raises(ValidationError):
        ApiKeyCreateIn(
            role="free",
            user_id=USER_ID,
        )


def test_admin_create_free_sin_propietario():
    entrada = AdminApiKeyCreateIn(role="free")

    assert entrada.user_id is None


@pytest.mark.parametrize("role", ["free", "user"])
def test_admin_create_con_propietario(role):
    entrada = AdminApiKeyCreateIn(
        role=role,
        user_id=str(USER_ID),
    )

    assert entrada.user_id == USER_ID

    assert isinstance(entrada.user_id, UUID)


def test_admin_create_user_requiere_propietario():
    with pytest.raises(ValidationError):
        AdminApiKeyCreateIn(role="user")


def test_admin_create_rechaza_uuid_invalido():
    with pytest.raises(ValidationError):
        AdminApiKeyCreateIn(
            role="user",
            user_id="invalido",
        )


def test_admin_create_requiere_role():
    with pytest.raises(ValidationError):
        AdminApiKeyCreateIn()


# =========================================================
# ESTADO DE RECURSOS
# =========================================================


@pytest.mark.parametrize("estado", [True, False])
def test_active_status_acepta_booleanos(estado):
    entrada = ActiveStatusIn(is_active=estado)

    assert entrada.is_active is estado


@pytest.mark.parametrize(
    "estado",
    [0, 1, "true", "false", None],
)
def test_active_status_rechaza_tipos_invalidos(estado):
    with pytest.raises(ValidationError):
        ActiveStatusIn(is_active=estado)


@pytest.mark.parametrize(
    "campo",
    ["role", "email", "password", "user_id", "deleted_at"],
)
def test_active_status_rechaza_campos_adicionales(campo):
    with pytest.raises(ValidationError):
        ActiveStatusIn(
            is_active=True,
            **{campo: "valor"},
        )


# =========================================================
# USER OUT Y LOGIN OUT
# =========================================================

def test_user_out_valido(usuario_valido):
    usuario = UserOut(**usuario_valido)

    assert usuario.id == USER_ID

    assert usuario.email == EMAIL

    assert usuario.is_active is True


@pytest.mark.parametrize(
    "campo",
    ["password", "password_hash", "deleted_at"],
)
def test_user_out_rechaza_campos_no_publicos(
    usuario_valido,
    campo,
):
    usuario_valido[campo] = "dato interno"

    with pytest.raises(ValidationError):
        UserOut(**usuario_valido)


def test_user_out_normaliza_fecha_utc(usuario_valido):
    fecha = datetime(
        2026,
        11,
        25,
        16,
        tzinfo=timezone(timedelta(hours=1)),
    )

    usuario_valido["created_at"] = fecha

    usuario = UserOut(**usuario_valido)

    assert usuario.created_at.hour == 15

    assert usuario.created_at.utcoffset() == timedelta(0)


def test_user_out_rechaza_fecha_sin_zona(usuario_valido):
    usuario_valido["created_at"] = datetime(2026, 11, 25)

    with pytest.raises(ValidationError):
        UserOut(**usuario_valido)


def test_login_out_devuelve_token(usuario_valido):
    respuesta = LoginOut(
        session_token="token-de-prueba",
        token_type="Bearer",
        expires_at=CREATED_AT + timedelta(hours=8),
        user=usuario_valido,
    )

    datos = respuesta.model_dump(mode="json")

    assert datos["session_token"] == "token-de-prueba"

    assert datos["token_type"] == "Bearer"

    assert datos["user"]["id"] == str(USER_ID)

    assert "token-de-prueba" not in repr(respuesta)


@pytest.mark.parametrize("token", ["", "   ", None])
def test_login_out_rechaza_token_invalido(
    usuario_valido,
    token,
):
    with pytest.raises(ValidationError):
        LoginOut(
            session_token=token,
            token_type="Bearer",
            expires_at=CREATED_AT + timedelta(hours=8),
            user=usuario_valido,
        )


def test_login_out_rechaza_token_type_invalido(
    usuario_valido,
):
    with pytest.raises(ValidationError):
        LoginOut(
            session_token="token-de-prueba",
            token_type="Basic",
            expires_at=CREATED_AT + timedelta(hours=8),
            user=usuario_valido,
        )


# =========================================================
# API KEY OUT Y API KEY CREATED OUT
# =========================================================


@pytest.mark.parametrize("role", list(ApiKeyRole))
def test_api_key_out_acepta_roles(api_key_valida, role):
    api_key_valida["role"] = role

    resultado = ApiKeyOut(**api_key_valida)

    assert resultado.role == role


def test_api_key_out_acepta_free_anonima(api_key_valida):
    api_key_valida.update(
        role=ApiKeyRole.FREE,
        user_id=None,
    )

    resultado = ApiKeyOut(**api_key_valida)

    assert resultado.user_id is None


@pytest.mark.parametrize(
    "role",
    [ApiKeyRole.USER, ApiKeyRole.ADMIN],
)
def test_api_key_out_requiere_propietario(
    api_key_valida,
    role,
):
    api_key_valida.update(
        role=role,
        user_id=None,
    )

    with pytest.raises(ValidationError):
        ApiKeyOut(**api_key_valida)


def test_api_key_out_rechaza_eliminada_activa(api_key_valida):
    api_key_valida["deleted_at"] = CREATED_AT

    with pytest.raises(ValidationError):
        ApiKeyOut(**api_key_valida)


def test_api_key_out_acepta_eliminada_inactiva(
    api_key_valida,
):
    api_key_valida.update(
        deleted_at=CREATED_AT,
        is_active=False,
    )

    resultado = ApiKeyOut(**api_key_valida)

    assert resultado.is_active is False


@pytest.mark.parametrize("campo", ["key_hash", "api_key"])
def test_api_key_out_rechaza_secretos(
    api_key_valida,
    campo,
):
    api_key_valida[campo] = "secreto"

    with pytest.raises(ValidationError):
        ApiKeyOut(**api_key_valida)


@pytest.mark.parametrize(
    "role",
    [ApiKeyRole.FREE, ApiKeyRole.USER],
)
def test_api_key_created_out_devuelve_credencial(
    api_key_valida,
    role,
):
    api_key_valida["role"] = role

    resultado = ApiKeyCreatedOut(
        **api_key_valida,
        api_key="clave-de-prueba",
    )

    datos = resultado.model_dump(mode="json")

    assert datos["api_key"] == "clave-de-prueba"

    assert "clave-de-prueba" not in repr(resultado)

    assert "key_hash" not in datos


def test_api_key_created_out_rechaza_admin(api_key_valida):
    api_key_valida["role"] = ApiKeyRole.ADMIN

    with pytest.raises(ValidationError):
        ApiKeyCreatedOut(
            **api_key_valida,
            api_key="clave-de-prueba",
        )


def test_api_key_created_out_hereda_validacion_propietario(
    api_key_valida,
):
    api_key_valida["user_id"] = None

    with pytest.raises(ValidationError):
        ApiKeyCreatedOut(
            **api_key_valida,
            api_key="clave-de-prueba",
        )


@pytest.mark.parametrize("api_key", ["", "   ", None])
def test_api_key_created_out_rechaza_credencial_invalida(
    api_key_valida,
    api_key,
):
    with pytest.raises(ValidationError):
        ApiKeyCreatedOut(
            **api_key_valida,
            api_key=api_key,
        )