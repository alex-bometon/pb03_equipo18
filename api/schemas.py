"""Contratos públicos HTTP de ReciclaTÍA."""

from typing import Annotated
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
)

from config import MAX_PREGUNTA_CARACTERES
from src.input_validation import validar_pregunta

from api.config import MAX_API_STEPS
from config import MAX_PREGUNTA_CARACTERES
from src.input_validation import validar_pregunta


# =========================================================
# CONFIGURACIÓN COMÚN
# =========================================================


class ApiSchema(BaseModel):
    """Configuración común de los modelos públicos de la API."""

    model_config = ConfigDict(
        extra="forbid",
    )


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


# =========================================================
# CONTRATOS DE ENTRADA DEL ASISTENTE
# =========================================================


class UbicacionIn(ApiSchema):
    """Coordenadas geográficas proporcionadas por el cliente."""

    latitud: float = Field(
        strict=True,
        ge=-90,
        le=90,
        allow_inf_nan=False,
    )

    longitud: float = Field(
        strict=True,
        ge=-180,
        le=180,
        allow_inf_nan=False,
    )


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