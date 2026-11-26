"""Recepción y adaptación técnica de imágenes para la API."""

from io import BytesIO
from math import sqrt
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile

from PIL import Image, ImageOps
from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from api.config import ApiSettings
from api.error_catalog import ErrorCode
from api.errors import ApiError
from config import ASSETS_DIR, IMAGE_MAX_BYTES, IMAGE_MAX_PIXELS
from src.input_validation import (
    ImagenInvalidaError,
    abrir_imagen_validada,
)


def _redimensionar(imagen: Image.Image, factor: float) -> None:
    """Reduce proporcionalmente las dimensiones de una imagen."""
    ancho, alto = imagen.size

    dimensiones = (
        min(IMAGE_MAX_PIXELS, max(1, int(ancho * factor))),
        min(IMAGE_MAX_PIXELS, max(1, int(alto * factor))),
    )

    imagen.thumbnail(dimensiones, Image.Resampling.LANCZOS)


def adaptar_imagen(
    datos: bytes,
    *,
    settings: ApiSettings,
) -> tuple[bytes, str]:
    """Valida y adapta una imagen a los límites finales del núcleo."""
    try:
        with abrir_imagen_validada(
            datos,
            max_bytes=settings.IMAGE_UPLOAD_MAX_BYTES,
            max_pixeles=settings.IMAGE_UPLOAD_MAX_PIXELS,
        ) as original:
            formato = original.format

            with ImageOps.exif_transpose(original) as orientada:
                transparencia = (
                    "A" in orientada.getbands()
                    or "transparency" in orientada.info
                )

                modo = ("RGBA" if formato == "PNG" and transparencia else "RGB")

                with orientada.convert(modo) as imagen:
                    imagen.info.clear()

                    pixeles = imagen.width * imagen.height

                    if pixeles > IMAGE_MAX_PIXELS:
                        factor = sqrt(IMAGE_MAX_PIXELS / pixeles)
                        _redimensionar(imagen, factor)

                    opciones = (
                        {"quality": 85}
                        if formato == "JPEG"
                        else {"compress_level": 6}
                    )

                    for intento in range(5):
                        if intento > 0:
                            _redimensionar(imagen, 0.7)

                        with BytesIO() as salida:
                            imagen.save(salida, format=formato, **opciones)
                            adaptada = salida.getvalue()

                        if len(adaptada) <= IMAGE_MAX_BYTES:
                            break

                    else:
                        raise ApiError(ErrorCode.IMAGE_FILE_TOO_LARGE)

        with abrir_imagen_validada(
            adaptada,
            max_bytes=IMAGE_MAX_BYTES,
            max_pixeles=IMAGE_MAX_PIXELS,
        ) as verificada:
            return adaptada, verificada.format

    except ImagenInvalidaError as exc:
        codigos = {
            "peso": ErrorCode.IMAGE_FILE_TOO_LARGE,
            "formato": ErrorCode.IMAGE_FORMAT_NOT_ALLOWED,
            "resolucion": ErrorCode.IMAGE_RESOLUTION_EXCEEDED,
            "corrupcion": ErrorCode.IMAGE_CORRUPTED,
        }

        raise ApiError(codigos[exc.motivo]) from exc
    

async def recibir_imagen(
    imagen: UploadFile,
    *,
    settings: ApiSettings,
) -> tuple[bytes, str]:
    """Lee de forma limitada y adapta un archivo recibido por HTTP."""
    datos = await imagen.read(settings.IMAGE_UPLOAD_MAX_BYTES + 1)

    return await run_in_threadpool(adaptar_imagen, datos, settings=settings)


@contextmanager
def imagen_temporal(
    datos: bytes,
    formato: str,
) -> Iterator[str]:
    """Almacena una imagen adaptada mientras resulta necesaria."""
    extensiones = {"JPEG": ".jpg", "PNG": ".png"}

    if formato not in extensiones:
        raise ValueError("Formato de imagen adaptada inválido.")

    assets = ASSETS_DIR.resolve()
    directorio = assets / ".api_temporal"

    directorio.mkdir(mode=0o700, exist_ok=True)

    if directorio.is_symlink() or directorio.resolve() != directorio:
        raise RuntimeError("Directorio temporal no autorizado.")

    with NamedTemporaryFile(
        mode="wb",
        suffix=extensiones[formato],
        dir=directorio,
    ) as archivo:
        archivo.write(datos)
        archivo.flush()

        yield str(Path(archivo.name))