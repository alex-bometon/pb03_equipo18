"""Pruebas unitarias de la herramienta multimodal de ReciclaTIA."""

from unittest.mock import Mock, patch

import json
import pytest
from PIL import Image

from src.tools.describir_imagen import (
    ImagenNoAdmitidaError,
    describir_imagen,
    identificar_imagen,
)


@pytest.fixture
def imagen_prueba(tmp_path, monkeypatch):
    """Crea una imagen JPEG temporal dentro de assets/."""

    directorio = tmp_path / "assets"
    directorio.mkdir()

    ruta = directorio / "jamon.jpg"

    Image.new("RGB", (100, 100), "white").save(ruta, format="JPEG")

    # Aislar los tests de los archivos reales del proyecto.
    monkeypatch.setattr("src.tools.describir_imagen.BASE_DIR", tmp_path)

    monkeypatch.setattr("src.tools.describir_imagen.ASSETS_DIR", directorio)

    return ruta


def test_describir_imagen_registro():
    """Comprueba que LangChain reconoce la herramienta."""

    assert describir_imagen.name == "describir_imagen"
    assert describir_imagen.args["ruta_imagen"]["type"] == "string"


def test_describir_imagen_correcta(imagen_prueba):
    """Comprueba el envío de imagen y la respuesta de Gemini."""

    cliente = Mock()
    cliente.models.generate_content.return_value.text = json.dumps({
        "estado": "allowed",
        "descripcion": "Se observa una bandeja de plástico.",
    })

    with patch(
        "src.tools.describir_imagen.crear_cliente_gemini",
        return_value=cliente,
    ) as mock_crear_cliente:

        resultado = describir_imagen.invoke({"ruta_imagen": "assets/jamon.jpg"})

    assert resultado == "Se observa una bandeja de plástico."

    mock_crear_cliente.assert_called_once_with()
    cliente.models.generate_content.assert_called_once()
    cliente.close.assert_called_once()

    # Comprobar que se enviaron los bytes de la imagen.
    argumentos = cliente.models.generate_content.call_args.kwargs
    contenido_imagen = argumentos["contents"][0]

    assert contenido_imagen.inline_data.mime_type == "image/jpeg"
    assert contenido_imagen.inline_data.data == imagen_prueba.read_bytes()


def test_describir_imagen_ruta_no_permitida(imagen_prueba):
    """Impide acceder a archivos fuera de assets/."""

    with patch("src.tools.describir_imagen.crear_cliente_gemini") as mock_cliente:

        with pytest.raises(ValueError, match="dentro de assets"):
            describir_imagen.invoke({"ruta_imagen": "../archivo.jpeg"})

    mock_cliente.assert_not_called()


def test_describir_imagen_formato_invalido(imagen_prueba):
    """Rechaza archivos cuyo contenido no es JPEG ni PNG."""

    # Sobrescribir con contenido GIF, manteniendo el nombre .jpeg.
    Image.new("RGB", (100, 100), "white").save(imagen_prueba, format="GIF")

    with patch(
        "src.tools.describir_imagen.crear_cliente_gemini"
    ) as mock_cliente:

        with pytest.raises(ValueError, match="contenido no es JPEG ni PNG"):
            describir_imagen.invoke({"ruta_imagen": "assets/jamon.jpg"})

    mock_cliente.assert_not_called()


def test_describir_imagen_respuesta_vacia(imagen_prueba):
    """Comprueba que Gemini no puede devolver una descripción vacía."""

    cliente = Mock()
    cliente.models.generate_content.return_value.text = ""

    with patch(
        "src.tools.describir_imagen.crear_cliente_gemini",
        return_value=cliente,
    ):

        with pytest.raises(RuntimeError, match="descripción"):
            describir_imagen.invoke({"ruta_imagen": "assets/jamon.jpg"})

    cliente.close.assert_called_once()


@pytest.mark.parametrize(
    "estado",
    [
        "allowed",
        "out_of_domain",
        "policy_violation",
        "uncertain",
    ],
)
def test_identificar_imagen_estados(imagen_prueba, estado):
    """Conserva los estados semánticos reconocidos."""
    cliente = Mock()
    esperado = {
        "estado": estado,
        "descripcion": "Identificación visual de prueba.",
    }

    cliente.models.generate_content.return_value.text = json.dumps(esperado)

    with patch(
        "src.tools.describir_imagen.crear_cliente_gemini",
        return_value=cliente,
    ):
        resultado = identificar_imagen(str(imagen_prueba))

    assert resultado == esperado

    cliente.models.generate_content.assert_called_once()
    cliente.close.assert_called_once()


@pytest.mark.parametrize(
    "datos",
    [
        {},
        [],
        None,
        {"estado": "allowed"},
        {"estado": "desconocido", "descripcion": "Objeto"},
        {"estado": "allowed", "descripcion": ""},
        {"estado": "allowed", "descripcion": "   "},
        {"estado": "allowed", "descripcion": 123},
        {"estado": [], "descripcion": "Objeto"},
        {"estado": "allowed", "descripcion": "a" * 501},
        {
            "estado": "allowed",
            "descripcion": "Objeto",
            "confianza": 90,
        },
    ],
)
def test_identificacion_rechaza_contrato_invalido(imagen_prueba, datos):
    """No convierte una salida inválida en incertidumbre semántica."""
    cliente = Mock()
    cliente.models.generate_content.return_value.text = json.dumps(datos)

    with patch(
        "src.tools.describir_imagen.crear_cliente_gemini",
        return_value=cliente,
    ):
        with pytest.raises(RuntimeError, match="descripción válida"):
            identificar_imagen(str(imagen_prueba))

    cliente.close.assert_called_once()


def test_identificacion_rechaza_json_malformado(imagen_prueba):
    """Distingue una respuesta inválida de una imagen incierta."""
    cliente = Mock()
    cliente.models.generate_content.return_value.text = "{invalido"

    with patch(
        "src.tools.describir_imagen.crear_cliente_gemini",
        return_value=cliente,
    ):
        with pytest.raises(RuntimeError):
            identificar_imagen(str(imagen_prueba))

    cliente.close.assert_called_once()


def test_identificacion_propaga_fallo_proveedor(imagen_prueba):
    """Libera el cliente incluso si falla la petición multimodal."""
    cliente = Mock()
    cliente.models.generate_content.side_effect = RuntimeError(
        "Fallo simulado del proveedor"
    )

    with patch(
        "src.tools.describir_imagen.crear_cliente_gemini",
        return_value=cliente,
    ):
        with pytest.raises(RuntimeError, match="Fallo simulado"):
            identificar_imagen(str(imagen_prueba))

    cliente.close.assert_called_once()


@pytest.mark.parametrize(
    "estado",
    ["out_of_domain", "policy_violation", "uncertain"],
)
def test_describir_imagen_no_admite_rechazos(estado):
    """No devuelve una identificación rechazada como descripción."""
    identificacion = {
        "estado": estado,
        "descripcion": "Identificación no admitida.",
    }

    with patch(
        "src.tools.describir_imagen.identificar_imagen",
        return_value=identificacion,
    ):
        with pytest.raises(ImagenNoAdmitidaError) as error:
            describir_imagen.invoke({"ruta_imagen": "assets/prueba.jpg"})

    assert error.value.identificacion == identificacion
