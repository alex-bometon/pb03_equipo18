"""Contratos públicos HTTP de ReciclaTÍA."""

from datetime import datetime, timezone
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    HttpUrl,
    SecretStr,
    StrictBool,
    StrictInt,
    StrictStr,
    model_validator,
)

from api.base import SecureBaseModel
from api.config import MAX_API_STEPS
from api.credential_validation import (
    normalizar_email,
    validar_nueva_password,
    validar_password_verificacion,
)
from config import (
    EMAIL_MAX_LENGTH,
    GEO_MAX_LATITUDE,
    GEO_MAX_LONGITUDE,
    GEO_MAX_RADIUS_METERS,
    GEO_MAX_RESULTS,
    GEO_MIN_LATITUDE,
    GEO_MIN_LONGITUDE,
    GEO_MIN_RADIUS_METERS,
    MAX_PREGUNTA_CARACTERES,
)
from src.enums import ApiKeyRole
from src.input_validation import validar_pregunta


# =========================================================
# CONFIGURACIÓN COMÚN
# =========================================================


class ApiSchema(SecureBaseModel):
    """Configuración común de los modelos públicos de la API."""


# =========================================================
# TIPOS REUTILIZABLES
# =========================================================


def _validar_uuid(value: str) -> str:
    """Valida y devuelve la representación canónica de un UUID."""

    try:
        return str(UUID(value))

    except ValueError:
        raise ValueError("Identificador UUID inválido.") from None


UUIDText = Annotated[
    StrictStr,
    Field(json_schema_extra={"format": "uuid"}),
    AfterValidator(_validar_uuid),
]


def _validar_texto_no_vacio(value: str) -> str:
    """Comprueba que una cadena contiene texto sin modificarla."""

    if not value.strip():
        raise ValueError("El texto no puede estar vacío.")

    return value


NonBlankText = Annotated[
    StrictStr,
    AfterValidator(_validar_texto_no_vacio),
]


Latitude = Annotated[
    float,
    Field(
        strict=True,
        ge=GEO_MIN_LATITUDE,
        le=GEO_MAX_LATITUDE,
        allow_inf_nan=False,
    ),
]


Longitude = Annotated[
    float,
    Field(
        strict=True,
        ge=GEO_MIN_LONGITUDE,
        le=GEO_MAX_LONGITUDE,
        allow_inf_nan=False,
    ),
]


EmailText = Annotated[
    StrictStr,
    Field(json_schema_extra={"format": "email"}),
    AfterValidator(normalizar_email),
]


StrictSecretStr = Annotated[
    SecretStr,
    Field(strict=True),
]


def _validar_password_secret(value: SecretStr) -> SecretStr:
    """Comprueba una contraseña utilizada para autenticación."""

    validar_password_verificacion(value.get_secret_value())

    return value


def _validar_nueva_password_secret(value: SecretStr) -> SecretStr:
    """Comprueba una contraseña de nueva creación."""

    validar_nueva_password(value.get_secret_value())

    return value


PasswordText = Annotated[
    StrictSecretStr,
    AfterValidator(_validar_password_secret),
]


NewPasswordText = Annotated[
    StrictSecretStr,
    AfterValidator(_validar_nueva_password_secret),
]


IssuableApiKeyRole = Literal[
    ApiKeyRole.FREE,
    ApiKeyRole.USER,
]


def _normalizar_fecha_utc(value: datetime) -> datetime:
    """Normaliza una fecha con zona horaria a UTC."""

    return value.astimezone(timezone.utc)


UTCDateTime = Annotated[
    AwareDatetime,
    Field(strict=True),
    AfterValidator(_normalizar_fecha_utc),
]


CredentialOutText = Annotated[
    NonBlankText,
    Field(repr=False),
]

# =========================================================
# CONTRATOS DE ENTRADA DEL ASISTENTE
# =========================================================


class UbicacionIn(ApiSchema):
    """Coordenadas geográficas proporcionadas por el cliente."""

    latitud: Latitude
    longitud: Longitude


class AskIn(ApiSchema):
    """Petición de consulta textual al asistente."""

    pregunta: StrictStr = Field(
        description=(
            "Pregunta no vacía de hasta "
            f"{MAX_PREGUNTA_CARACTERES} caracteres después de strip()."
        ),
    )

    thread_id: UUIDText | None = None

    auto_aprobar: StrictBool = True

    ubicacion: UbicacionIn | None = None

    max_steps: StrictInt | None = Field(
        default=None,
        ge=1,
        le=MAX_API_STEPS,
    )

    def pregunta_validada(self) -> str:
        """Aplica la validación compartida de preguntas del núcleo."""

        return validar_pregunta(self.pregunta)


class ApproveIn(ApiSchema):
    """Decisión humana sobre una propuesta pendiente de HITL."""

    thread_id: UUIDText

    approval_id: UUIDText

    aprobado: StrictBool


# =========================================================
# CONTRATOS DE SALIDA DEL ASISTENTE
# =========================================================

class FuenteOut(ApiSchema):
    """Referencia documental pública utilizada por el asistente."""

    chunk_id: NonBlankText

    source: NonBlankText

    url: HttpUrl | None = None

    rol: Literal["residuos", "puntos"] | None = None

    id_llamada: StrictStr | None = None


class PuntoLimpioOut(ApiSchema):
    """Representación pública de una instalación municipal."""

    tipo: NonBlankText

    direccion: NonBlankText

    distrito: StrictStr | None = None

    latitud: Latitude

    longitud: Longitude

    distancia_metros: float = Field(
        strict=True,
        ge=0,
        allow_inf_nan=False,
    )

    horario_apertura: StrictStr | None = None

    horario_cierre: StrictStr | None = None

    dia_semana: StrictStr | None = None

    turno: StrictStr | None = None

    documento_origen: StrictStr | None = None


class GeografiaOut(ApiSchema):
    """Resultado público de una búsqueda geográfica."""

    fuente: Literal["api", "corpus_local"]

    tipo_solicitado: Literal[
        "todos",
        "fijo",
        "movil",
        "proximidad",
    ]

    radio_metros: StrictInt = Field(
        ge=GEO_MIN_RADIUS_METERS,
        le=GEO_MAX_RADIUS_METERS,
    )

    total_encontrados: StrictInt = Field(ge=0)

    puntos: list[PuntoLimpioOut] = Field(
        max_length=GEO_MAX_RESULTS,
    )

    aviso: StrictStr | None = None

    @model_validator(mode="after")
    def validar_coherencia_geografica(self) -> Self:
        """Comprueba la coherencia del resultado geográfico."""

        cantidad_esperada = min(
            self.total_encontrados,
            GEO_MAX_RESULTS,
        )

        if len(self.puntos) != cantidad_esperada:
            raise ValueError(
                "El número de puntos no coincide con el total esperado."
            )

        distancias = [
            punto.distancia_metros
            for punto in self.puntos
        ]

        if distancias != sorted(distancias):
            raise ValueError(
                "Los puntos deben estar ordenados por distancia."
            )

        if any(
            distancia > self.radio_metros
            for distancia in distancias
        ):
            raise ValueError(
                "Existen puntos fuera del radio consultado."
            )

        if self.fuente == "corpus_local" and (
            self.aviso is None or not self.aviso.strip()
        ):
            raise ValueError(
                "El respaldo local requiere un aviso."
            )

        return self

    
class AskOut(ApiSchema):
    """Respuesta pública satisfactoria del asistente."""

    thread_id: UUIDText | None

    respuesta: NonBlankText

    plan: list[NonBlankText]

    plan_aprobado: StrictBool | None

    done: StrictBool

    pendiente_hitl: StrictBool

    fuentes: list[FuenteOut]

    geografia: list[GeografiaOut]

    abstencion: StrictBool

    motivo: StrictStr | None

    estado_evidencia: Literal[
        "suficiente",
        "parcial",
        "insuficiente",
    ]

    limitaciones: list[StrictStr]

    turnos_consumidos: StrictInt = Field(ge=0)

    error: StrictStr | None

    approval_id: UUIDText | None

    @model_validator(mode="after")
    def validar_estado_respuesta(self) -> Self:
        """Comprueba las invariantes públicas del asistente."""

        if self.error is not None:
            raise ValueError(
                "Una respuesta satisfactoria no puede contener errores."
            )

        if self.thread_id is None and self.turnos_consumidos != 0:
            raise ValueError(
                "No pueden existir turnos sin conversación."
            )

        if self.pendiente_hitl:
            self._validar_propuesta_pendiente()

        elif self.plan_aprobado is True:
            self._validar_plan_aprobado()

        elif self.plan_aprobado is False:
            self._validar_plan_rechazado()

        else:
            self._validar_respuesta_previa()

        return self

    def _validar_turno_ejecutado(self) -> None:
        """Comprueba los datos comunes de una ejecución de LangGraph."""

        if self.thread_id is None:
            raise ValueError(
                "Un turno ejecutado requiere una conversación."
            )

        if self.turnos_consumidos < 1:
            raise ValueError(
                "Un turno ejecutado debe estar contabilizado."
            )

    def _validar_propuesta_pendiente(self) -> None:
        """Comprueba una propuesta pendiente de aprobación."""

        self._validar_turno_ejecutado()

        if (
            self.plan_aprobado is not None
            or self.done
            or self.approval_id is None
            or len(self.plan) < 2
        ):
            raise ValueError(
                "La propuesta pendiente es inconsistente."
            )

    def _validar_plan_aprobado(self) -> None:
        """Comprueba una propuesta aprobada."""

        self._validar_turno_ejecutado()

        if (
            not self.done
            or self.approval_id is not None
            or len(self.plan) < 2
        ):
            raise ValueError(
                "El plan aprobado es inconsistente."
            )

    def _validar_plan_rechazado(self) -> None:
        """Comprueba una propuesta rechazada."""

        self._validar_turno_ejecutado()

        if (
            self.done
            or self.approval_id is not None
            or self.plan
        ):
            raise ValueError(
                "El plan rechazado es inconsistente."
            )

    def _validar_respuesta_previa(self) -> None:
        """Comprueba una respuesta anterior a LangGraph."""

        if (
            self.done
            or self.approval_id is not None
            or self.plan
            or self.fuentes
            or self.geografia
            or not self.abstencion
            or self.estado_evidencia != "insuficiente"
        ):
            raise ValueError(
                "La respuesta previa al agente es inconsistente."
            )


# =========================================================
# CONTRATOS DE ENTRADA DE CUENTAS Y CREDENCIALES
# =========================================================

class RegisterIn(ApiSchema):
    """Solicitud de registro de una cuenta."""

    email: EmailText

    password: NewPasswordText


class LoginIn(ApiSchema):
    """Credenciales de inicio de sesión."""

    email: EmailText

    password: PasswordText


class PasswordChangeIn(ApiSchema):
    """Solicitud de cambio de contraseña."""

    current_password: PasswordText

    new_password: NewPasswordText


class ApiKeyCreateIn(ApiSchema):
    """Solicitud ordinaria de emisión de una API key."""

    role: IssuableApiKeyRole = ApiKeyRole.FREE


class AdminApiKeyCreateIn(ApiSchema):
    """Solicitud administrativa de emisión de una API key."""

    role: IssuableApiKeyRole

    user_id: UUID | None = None

    @model_validator(mode="after")
    def validar_propietario(self) -> Self:
        """Exige un propietario para las claves User."""

        if (
            self.role == ApiKeyRole.USER
            and self.user_id is None
        ):
            raise ValueError(
                "Una API key User requiere un propietario."
            )

        return self


class ActiveStatusIn(ApiSchema):
    """Solicitud de modificación del estado de un recurso."""

    is_active: StrictBool


# =========================================================
# CONTRATOS DE SALIDA DE CUENTAS Y CREDENCIALES
# =========================================================

class UserOut(ApiSchema):
    """Representación pública de un usuario."""

    id: UUID

    email: NonBlankText = Field(
        max_length=EMAIL_MAX_LENGTH,
    )

    created_at: UTCDateTime

    is_active: StrictBool


class LoginOut(ApiSchema):
    """Resultado de una autenticación satisfactoria."""

    session_token: CredentialOutText

    token_type: Literal["Bearer"]

    expires_at: UTCDateTime

    user: UserOut


class ApiKeyOut(ApiSchema):
    """Representación pública de una API key."""

    id: UUID

    role: ApiKeyRole

    user_id: UUID | None

    is_active: StrictBool

    created_at: UTCDateTime

    last_used_at: UTCDateTime | None

    deleted_at: UTCDateTime | None

    @model_validator(mode="after")
    def validar_estado_credencial(self) -> Self:
        """Comprueba las invariantes de una credencial."""

        if (
            self.role != ApiKeyRole.FREE
            and self.user_id is None
        ):
            raise ValueError(
                "La API key requiere un propietario."
            )

        if self.deleted_at is not None and self.is_active:
            raise ValueError(
                "Una API key eliminada no puede estar activa."
            )

        return self


class ApiKeyCreatedOut(ApiKeyOut):
    """Resultado de la emisión de una API key."""

    role: IssuableApiKeyRole

    api_key: CredentialOutText