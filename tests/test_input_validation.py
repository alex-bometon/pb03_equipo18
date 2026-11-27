"""Pruebas de la validación compartida de preguntas."""

import pytest

from io import BytesIO

from PIL import Image

from config import MAX_PREGUNTA_CARACTERES
from src.input_validation import (
    ImagenInvalidaError,
    PreguntaDemasiadoLargaError,
    PreguntaInvalidaError,
    PreguntaTipoInvalidoError,
    PreguntaVaciaError,
    abrir_imagen_validada,
    validar_pregunta,
)


@pytest.mark.parametrize("pregunta", [None, True, 42, b"texto", []])
def test_rechaza_tipo_invalido(pregunta):
    with pytest.raises(PreguntaTipoInvalidoError):
        validar_pregunta(pregunta)


@pytest.mark.parametrize("pregunta", ["", "   ", "\t\n"])
def test_rechaza_pregunta_vacia(pregunta):
    with pytest.raises(PreguntaVaciaError):
        validar_pregunta(pregunta)


@pytest.mark.parametrize(
    "pregunta, esperado",
    [
        ("¿Dónde reciclo vidrio?", "¿Dónde reciclo vidrio?"),
        ("  BATERÍAS  ", "BATERÍAS"),
        ("  Papel   y cartón  ", "Papel   y cartón"),
    ],
)
def test_normaliza_sin_alterar_contenido(pregunta, esperado):
    assert validar_pregunta(pregunta) == esperado


def test_acepta_longitud_maxima_despues_de_strip():
    texto = "a" * MAX_PREGUNTA_CARACTERES
    pregunta = f"  {texto}  "

    assert validar_pregunta(pregunta) == texto


@pytest.mark.parametrize("espacios", ["", "   "])
def test_rechaza_longitud_excedida(espacios):
    texto = "a" * (MAX_PREGUNTA_CARACTERES + 1)
    pregunta = f"{espacios}{texto}{espacios}"

    with pytest.raises(PreguntaDemasiadoLargaError):
        validar_pregunta(pregunta)


@pytest.mark.parametrize(
    "excepcion",
    [
        PreguntaTipoInvalidoError,
        PreguntaVaciaError,
        PreguntaDemasiadoLargaError,
    ],
)
def test_compatibilidad_jerarquia_excepciones(excepcion):
    assert issubclass(excepcion, PreguntaInvalidaError)
    assert issubclass(excepcion, ValueError)


@pytest.fixture
def datos_imagen():
    """Genera una imagen PNG válida en memoria."""
    with BytesIO() as salida:
        with Image.new("RGB", (20, 20), "white") as imagen:
            imagen.save(salida, format="PNG")
        return salida.getvalue()


def test_abre_imagen_validada(datos_imagen):
    """Permite acceder a los píxeles de una imagen válida."""
    with abrir_imagen_validada(datos_imagen) as imagen:
        assert imagen.format == "PNG"
        assert imagen.size == (20, 20)
        assert imagen.getpixel((0, 0)) == (255, 255, 255)


@pytest.mark.parametrize("datos", [b"", b"contenido invalido"])
def test_rechaza_imagen_corrupta(datos):
    """Distingue archivos vacíos o ilegibles."""
    with pytest.raises(ImagenInvalidaError) as error:
        with abrir_imagen_validada(datos):
            pass

    assert error.value.motivo == "corrupcion"


def test_rechaza_peso_excedido(datos_imagen):
    """Comprueba el límite de peso antes de decodificar."""
    with pytest.raises(ImagenInvalidaError) as error:
        with abrir_imagen_validada(
            datos_imagen,
            max_bytes=len(datos_imagen) - 1,
        ):
            pass

    assert error.value.motivo == "peso"


def test_rechaza_resolucion_excedida(datos_imagen):
    """Comprueba el límite de píxeles antes de decodificar."""
    with pytest.raises(ImagenInvalidaError) as error:
        with abrir_imagen_validada(
            datos_imagen,
            max_pixeles=399,
        ):
            pass

    assert error.value.motivo == "resolucion"


def test_rechaza_formato_no_permitido():
    """Identifica el formato real del contenido."""
    with BytesIO() as salida:
        with Image.new("RGB", (20, 20)) as imagen:
            imagen.save(salida, format="GIF")
        datos = salida.getvalue()

    with pytest.raises(ImagenInvalidaError) as error:
        with abrir_imagen_validada(datos):
            pass

    assert error.value.motivo == "formato"


def test_rechaza_png_animado():
    """Impide admitir imágenes PNG con varios fotogramas."""
    with BytesIO() as salida:
        with Image.new("RGB", (20, 20), "white") as primera:
            with Image.new("RGB", (20, 20), "black") as segunda:
                primera.save(
                    salida,
                    format="PNG",
                    save_all=True,
                    append_images=[segunda],
                    duration=100,
                    loop=0,
                )

        datos = salida.getvalue()

    with pytest.raises(ImagenInvalidaError) as error:
        with abrir_imagen_validada(datos):
            pass

    assert error.value.motivo == "formato"