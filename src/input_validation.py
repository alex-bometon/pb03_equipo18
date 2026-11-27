"""Validación compartida de entradas del núcleo de ReciclaTIA."""

from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from typing import Literal

from PIL import Image

from config import (
    IMAGE_ALLOWED_FORMATS,
    IMAGE_MAX_BYTES,
    IMAGE_MAX_PIXELS,
    MAX_PREGUNTA_CARACTERES,
)


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
        raise PreguntaTipoInvalidoError("La pregunta debe ser un texto no vacío.")

    limpia = pregunta.strip()

    if not limpia:
        raise PreguntaVaciaError("La pregunta debe ser un texto no vacío.")

    if len(limpia) > MAX_PREGUNTA_CARACTERES:
        raise PreguntaDemasiadoLargaError(
            "La pregunta no puede superar "
            f"{MAX_PREGUNTA_CARACTERES} caracteres."
        )

    return limpia


class ImagenInvalidaError(ValueError):
    """Representa una imagen que incumple los límites técnicos."""

    def __init__(
        self,
        motivo: Literal["peso", "formato", "resolucion", "corrupcion"],
        mensaje: str,
    ) -> None:
        """Conserva la causa técnica de la validación fallida."""
        self.motivo = motivo
        super().__init__(mensaje)


@contextmanager
def abrir_imagen_validada(
    datos: bytes,
    *,
    max_bytes: int = IMAGE_MAX_BYTES,
    max_pixeles: int = IMAGE_MAX_PIXELS,
) -> Iterator[Image.Image]:
    """Valida, decodifica y libera una imagen de forma controlada."""
    if not datos:
        raise ImagenInvalidaError("corrupcion", "La imagen está vacía.")

    if len(datos) > max_bytes:
        raise ImagenInvalidaError("peso", "La imagen supera el tamaño permitido.")

    with BytesIO(datos) as origen:
        imagen = None

        try:
            try:
                with Image.open(origen) as inspeccion:
                    if inspeccion.format not in IMAGE_ALLOWED_FORMATS:
                        raise ImagenInvalidaError(
                            "formato",
                            "El contenido no es JPEG ni PNG.",
                        )

                    if getattr(inspeccion, "is_animated", False):
                        raise ImagenInvalidaError(
                            "formato",
                            "No se admiten imágenes animadas.",
                        )

                    if inspeccion.width * inspeccion.height > max_pixeles:
                        raise ImagenInvalidaError(
                            "resolucion",
                            "La imagen supera la resolución permitida.",
                        )

                    inspeccion.verify()

                origen.seek(0)
                imagen = Image.open(origen)
                imagen.load()

            except ImagenInvalidaError:
                raise

            except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
                raise ImagenInvalidaError(
                    "resolucion",
                    "La imagen supera los límites de descompresión.",
                ) from exc

            except (OSError, SyntaxError, ValueError, EOFError) as exc:
                raise ImagenInvalidaError(
                    "corrupcion",
                    "No se ha podido interpretar la imagen.",
                ) from exc

            yield imagen

        finally:
            if imagen is not None:
                imagen.close()