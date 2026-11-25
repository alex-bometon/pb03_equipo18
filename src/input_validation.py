"""Validación compartida de preguntas del núcleo de ReciclaTIA."""

from config import MAX_PREGUNTA_CARACTERES


class PreguntaInvalidaError(ValueError):
    """Excepción base para los errores de validación de preguntas."""


class PreguntaTipoInvalidoError(PreguntaInvalidaError):
    """La pregunta no es una cadena de texto."""


class PreguntaVaciaError(PreguntaInvalidaError):
    """La pregunta no contiene texto después de eliminar espacios."""


class PreguntaDemasiadoLargaError(PreguntaInvalidaError):
    """La pregunta supera la longitud máxima permitida."""


def validar_pregunta(pregunta: str) -> str:
    """Valida y normaliza una pregunta sin alterar su contenido interno."""

    if not isinstance(pregunta, str):
        raise PreguntaTipoInvalidoError(
            "La pregunta debe ser un texto no vacío."
        )

    limpia = pregunta.strip()

    if not limpia:
        raise PreguntaVaciaError(
            "La pregunta debe ser un texto no vacío."
        )

    if len(limpia) > MAX_PREGUNTA_CARACTERES:
        raise PreguntaDemasiadoLargaError(
            "La pregunta no puede superar "
            f"{MAX_PREGUNTA_CARACTERES} caracteres."
        )

    return limpia