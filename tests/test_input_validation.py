"""Pruebas de la validación compartida de preguntas."""

import pytest

from config import MAX_PREGUNTA_CARACTERES
from src.input_validation import (
    PreguntaDemasiadoLargaError,
    PreguntaInvalidaError,
    PreguntaTipoInvalidoError,
    PreguntaVaciaError,
    validar_pregunta,
)


@pytest.mark.parametrize(
    "pregunta",
    [None, True, 42, b"texto", []],
)
def test_rechaza_tipo_invalido(pregunta):
    with pytest.raises(PreguntaTipoInvalidoError):
        validar_pregunta(pregunta)


@pytest.mark.parametrize(
    "pregunta",
    ["", "   ", "\t\n"],
)
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


@pytest.mark.parametrize(
    "espacios",
    ["", "   "],
)
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