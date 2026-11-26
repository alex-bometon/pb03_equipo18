"""Configuración base de los modelos Pydantic del backend."""

from pydantic import BaseModel, ConfigDict


class SecureBaseModel(BaseModel):
    """Políticas comunes de validación y seguridad."""

    model_config = ConfigDict(
        extra="forbid",
        hide_input_in_errors=True,
    )