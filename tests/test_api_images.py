"""Pruebas de adaptación técnica de imágenes de la API."""

import asyncio
from io import BytesIO
from random import Random
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from fastapi import UploadFile

from api.config import ApiSettings
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.images import (
    adaptar_imagen,
    imagen_temporal,
    recibir_imagen,
)


@pytest.fixture
def settings():
    """Proporciona una configuración aislada del entorno."""
    return ApiSettings()


@pytest.mark.parametrize("formato", ["JPEG", "PNG"])
def test_adapta_imagen_valida(settings, formato):
    """Conserva el formato de las imágenes admitidas."""
    with BytesIO() as salida:
        with Image.new("RGB", (100, 50), "white") as imagen:
            imagen.save(salida, format=formato)

        datos = salida.getvalue()

    adaptada, formato_final = adaptar_imagen(datos, settings=settings)

    assert formato_final == formato

    with Image.open(BytesIO(adaptada)) as imagen:
        assert imagen.size == (100, 50)
        assert imagen.format == formato


def test_adapta_resolucion(settings, monkeypatch):
    """Reduce la resolución conservando la relación de aspecto."""
    monkeypatch.setattr("api.images.IMAGE_MAX_PIXELS", 5000)

    with BytesIO() as salida:
        with Image.new("RGB", (200, 100), "white") as imagen:
            imagen.save(salida, format="PNG")

        datos = salida.getvalue()

    adaptada, _ = adaptar_imagen(datos, settings=settings)

    with Image.open(BytesIO(adaptada)) as imagen:
        assert imagen.size == (100, 50)
        assert imagen.width * imagen.height <= 5000


def test_adapta_peso(settings, monkeypatch):
    """Reduce el peso de una imagen con contenido poco compresible."""
    monkeypatch.setattr("api.images.IMAGE_MAX_BYTES", 2000)

    pixeles = Random(42).randbytes(64 * 64 * 3)

    with BytesIO() as salida:
        with Image.frombytes("RGB", (64, 64), pixeles) as imagen:
            imagen.save(salida, format="PNG")

        datos = salida.getvalue()

    assert len(datos) > 2000

    adaptada, formato = adaptar_imagen(datos, settings=settings)

    assert len(adaptada) <= 2000
    assert formato == "PNG"

    with Image.open(BytesIO(adaptada)) as imagen:
        assert imagen.width < 64
        assert imagen.width == imagen.height


def test_corrige_orientacion_y_elimina_exif(settings):
    """Aplica la orientación EXIF antes de eliminar los metadatos."""
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Metadato privado de prueba"

    with BytesIO() as salida:
        with Image.new("RGB", (100, 50), "white") as imagen:
            imagen.save(salida, format="JPEG", exif=exif)

        datos = salida.getvalue()

    adaptada, _ = adaptar_imagen(datos, settings=settings)

    with Image.open(BytesIO(adaptada)) as imagen:
        assert imagen.size == (50, 100)
        assert len(imagen.getexif()) == 0


def test_conserva_transparencia_y_elimina_metadatos(settings):
    """Conserva la transparencia PNG sin sus textos auxiliares."""
    metadatos = PngInfo()
    metadatos.add_text("Comentario", "Dato privado de prueba")

    with BytesIO() as salida:
        with Image.new("RGBA", (20, 20), (0, 0, 0, 0)) as imagen:
            imagen.save(salida, format="PNG", pnginfo=metadatos)

        datos = salida.getvalue()

    adaptada, _ = adaptar_imagen(datos, settings=settings)

    with Image.open(BytesIO(adaptada)) as imagen:
        assert imagen.mode == "RGBA"
        assert imagen.getpixel((0, 0)) == (0, 0, 0, 0)
        assert "Comentario" not in imagen.info


@pytest.mark.parametrize("datos", [b"", b"imagen corrupta"])
def test_adaptacion_rechaza_archivo_corrupto(settings, datos):
    """Transforma la causa técnica en un error de la API."""
    with pytest.raises(ApiError) as error:
        adaptar_imagen(datos, settings=settings)

    assert error.value.code == ErrorCode.IMAGE_CORRUPTED


def test_adaptacion_rechaza_formato_no_permitido(settings):
    """Rechaza formatos distintos de JPEG y PNG."""
    with BytesIO() as salida:
        with Image.new("RGB", (20, 20)) as imagen:
            imagen.save(salida, format="GIF")

        datos = salida.getvalue()

    with pytest.raises(ApiError) as error:
        adaptar_imagen(datos, settings=settings)

    assert error.value.code == ErrorCode.IMAGE_FORMAT_NOT_ALLOWED


def test_adaptacion_rechaza_peso_absoluto(settings):
    """No intenta adaptar archivos que exceden el límite absoluto."""
    datos = b"x" * (settings.IMAGE_UPLOAD_MAX_BYTES + 1)

    with pytest.raises(ApiError) as error:
        adaptar_imagen(datos, settings=settings)

    assert error.value.code == ErrorCode.IMAGE_FILE_TOO_LARGE


def test_adaptacion_rechaza_resolucion_absoluta():
    """No adapta imágenes superiores al límite de recepción."""
    settings = ApiSettings(IMAGE_UPLOAD_MAX_PIXELS=16_000_000)

    with BytesIO() as salida:
        with Image.new("1", (4001, 4000)) as imagen:
            imagen.save(salida, format="PNG")

        datos = salida.getvalue()

    with pytest.raises(ApiError) as error:
        adaptar_imagen(datos, settings=settings)

    assert error.value.code == ErrorCode.IMAGE_RESOLUTION_EXCEEDED


def test_adaptacion_rechaza_peso_no_adaptable(settings, monkeypatch):
    """Finaliza los intentos cuando no puede cumplir el límite."""
    monkeypatch.setattr("api.images.IMAGE_MAX_BYTES", 1)

    with BytesIO() as salida:
        with Image.new("RGB", (20, 20)) as imagen:
            imagen.save(salida, format="PNG")

        datos = salida.getvalue()

    with pytest.raises(ApiError) as error:
        adaptar_imagen(datos, settings=settings)

    assert error.value.code == ErrorCode.IMAGE_FILE_TOO_LARGE


def test_recibir_imagen_valida(settings):
    """Reutiliza la adaptación para una imagen recibida por HTTP."""
    with BytesIO() as salida:
        with Image.new("RGB", (20, 20)) as imagen:
            imagen.save(salida, format="PNG")

        datos = salida.getvalue()

    with BytesIO(datos) as archivo:
        subida = UploadFile(file=archivo, filename="prueba.png")

        adaptada, formato = asyncio.run(
            recibir_imagen(subida, settings=settings)
        )

    assert formato == "PNG"
    assert adaptada


def test_recibir_imagen_con_extension_enganosa(settings):
    """No confía en la extensión declarada por el cliente."""
    with BytesIO() as salida:
        with Image.new("RGB", (20, 20)) as imagen:
            imagen.save(salida, format="GIF")

        datos = salida.getvalue()

    with BytesIO(datos) as archivo:
        subida = UploadFile(file=archivo, filename="prueba.jpg")

        with pytest.raises(ApiError) as error:
            asyncio.run(recibir_imagen(subida, settings=settings))

    assert error.value.code == ErrorCode.IMAGE_FORMAT_NOT_ALLOWED


@pytest.fixture
def assets_temporales(tmp_path, monkeypatch):
    """Aísla el almacenamiento de los archivos reales del proyecto."""
    assets = tmp_path / "assets"
    assets.mkdir()

    monkeypatch.setattr("api.images.ASSETS_DIR", assets)

    return assets

@pytest.mark.parametrize("formato, extension", [("JPEG", ".jpg"), ("PNG", ".png")])
def test_imagen_temporal_creacion_y_limpieza(
    assets_temporales,
    formato,
    extension,
):
    """Conserva los datos durante el contexto y luego los elimina."""
    datos = b"contenido de prueba"

    with imagen_temporal(datos, formato) as ruta:
        archivo = Path(ruta)

        assert archivo.is_file()
        assert archivo.suffix == extension
        assert archivo.read_bytes() == datos
        assert archivo.parent == assets_temporales / ".api_temporal"

    assert not archivo.exists()

def test_imagen_temporal_limpia_tras_excepcion(assets_temporales):
    """Elimina el archivo aunque falle la operación que lo utiliza."""
    with pytest.raises(RuntimeError, match="Fallo simulado"):
        with imagen_temporal(b"datos", "PNG") as ruta:
            archivo = Path(ruta)

            assert archivo.exists()

            raise RuntimeError("Fallo simulado")

    assert not archivo.exists()


def test_imagen_temporal_genera_nombres_independientes(assets_temporales):
    """Impide que dos operaciones sobrescriban sus imágenes."""
    with imagen_temporal(b"primera", "JPEG") as primera:
        with imagen_temporal(b"segunda", "JPEG") as segunda:
            assert primera != segunda

            assert Path(primera).read_bytes() == b"primera"
            assert Path(segunda).read_bytes() == b"segunda"

        assert not Path(segunda).exists()
        assert Path(primera).exists()

    assert not Path(primera).exists()


def test_imagen_temporal_rechaza_directorio_simbolico(assets_temporales, tmp_path):
    """Impide almacenar imágenes fuera del directorio autorizado."""
    destino = tmp_path / "externo"
    destino.mkdir()

    directorio = assets_temporales / ".api_temporal"
    directorio.symlink_to(destino, target_is_directory=True)

    with pytest.raises(RuntimeError, match="no autorizado"):
        with imagen_temporal(b"datos", "PNG"):
            pytest.fail("No debe admitirse el directorio.")

    assert not list(destino.iterdir())


def test_imagen_temporal_rechaza_formato_invalido(assets_temporales):
    """No genera archivos con extensiones no autorizadas."""
    with pytest.raises(ValueError, match="Formato"):
        with imagen_temporal(b"datos", "GIF"):
            pytest.fail("No debe admitirse el formato.")

    assert not (assets_temporales / ".api_temporal").exists()