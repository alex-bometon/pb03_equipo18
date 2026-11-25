"""Pruebas de los contratos públicos HTTP."""

import pytest
from pydantic import ValidationError

from api.schemas import (
    ApiSchema,
    ApproveIn,
    AskIn,
    UbicacionIn,
)
from config import MAX_PREGUNTA_CARACTERES
from src.input_validation import (
    PreguntaDemasiadoLargaError,
    PreguntaVaciaError,
)


class ExampleSchema(ApiSchema):
    """Modelo auxiliar para comprobar la configuración común."""

    value: str


def test_schema_accepts_valid_fields():
    schema = ExampleSchema(value="correcto")

    assert schema.value == "correcto"


def test_schema_rejects_extra_fields():
    with pytest.raises(ValidationError) as exc_info:
        ExampleSchema(
            value="correcto",
            unexpected=True,
        )

    errors = exc_info.value.errors()

    assert len(errors) == 1
    assert errors[0]["type"] == "extra_forbidden"
    assert errors[0]["loc"] == ("unexpected",)


def test_schema_preserves_whitespace():
    schema = ExampleSchema(value="  contenido  ")

    assert schema.value == "  contenido  "


def test_schema_openapi_constraints():
    schema = ExampleSchema.model_json_schema()

    assert schema["additionalProperties"] is False


# =========================================================
# UBICACION IN
# =========================================================

@pytest.mark.parametrize(
    "latitud, longitud",
    [
        (40.4168, -3.7038),
        (40, -3),
        (90, 180),
        (-90, -180),
        (0, 0),
    ],
)
def test_ubicacion_acepta_coordenadas_validas(latitud, longitud):
    ubicacion = UbicacionIn(
        latitud=latitud,
        longitud=longitud,
    )

    assert ubicacion.latitud == latitud
    assert ubicacion.longitud == longitud


@pytest.mark.parametrize(
    "latitud, longitud",
    [
        (91, 0),
        (-91, 0),
        (0, 181),
        (0, -181),
        (True, 0),
        (0, False),
        ("40.4168", -3.7038),
        (40.4168, "-3.7038"),
        (float("nan"), 0),
        (0, float("nan")),
        (float("inf"), 0),
        (0, float("-inf")),
        (None, 0),
        (0, None),
    ],
)
def test_ubicacion_rechaza_coordenadas_invalidas(latitud, longitud):
    with pytest.raises(ValidationError):
        UbicacionIn(
            latitud=latitud,
            longitud=longitud,
        )


@pytest.mark.parametrize(
    "datos",
    [
        {},
        {"latitud": 40.4168},
        {"longitud": -3.7038},
    ],
)
def test_ubicacion_requiere_ambas_coordenadas(datos):
    with pytest.raises(ValidationError):
        UbicacionIn(**datos)


def test_ubicacion_rechaza_campos_adicionales():
    with pytest.raises(ValidationError):
        UbicacionIn(
            latitud=40.4168,
            longitud=-3.7038,
            distrito="Centro",
        )


# =========================================================
# ASK IN
# =========================================================

THREAD_ID = "550e8400-e29b-41d4-a716-446655440000"
APPROVAL_ID = "550e8400-e29b-41d4-a716-446655440001"


def test_ask_in_valores_predeterminados():
    entrada = AskIn(pregunta="¿Dónde reciclo vidrio?")

    assert entrada.thread_id is None
    assert entrada.auto_aprobar is True
    assert entrada.ubicacion is None
    assert entrada.max_steps is None


def test_ask_in_peticion_completa():
    entrada = AskIn(
        pregunta="¿Dónde reciclo vidrio?",
        thread_id=THREAD_ID,
        auto_aprobar=False,
        ubicacion={
            "latitud": 40.4168,
            "longitud": -3.7038,
        },
        max_steps=4,
    )

    assert entrada.thread_id == THREAD_ID
    assert entrada.auto_aprobar is False
    assert isinstance(entrada.ubicacion, UbicacionIn)
    assert entrada.max_steps == 4


def test_ask_in_requiere_pregunta():
    with pytest.raises(ValidationError):
        AskIn()


@pytest.mark.parametrize(
    "pregunta",
    [None, True, 42, [], {}],
)
def test_ask_in_rechaza_tipo_invalido_de_pregunta(pregunta):
    with pytest.raises(ValidationError):
        AskIn(pregunta=pregunta)


@pytest.mark.parametrize(
    "pregunta",
    ["", "   ", "\t\n"],
)
def test_ask_in_delega_validacion_de_pregunta_vacia(pregunta):
    entrada = AskIn(pregunta=pregunta)

    with pytest.raises(PreguntaVaciaError):
        entrada.pregunta_validada()


def test_ask_in_normaliza_pregunta():
    entrada = AskIn(
        pregunta="  ¿Dónde reciclo BATERÍAS?  ",
    )

    assert (
        entrada.pregunta_validada()
        == "¿Dónde reciclo BATERÍAS?"
    )


def test_ask_in_acepta_longitud_maxima():
    texto = "a" * MAX_PREGUNTA_CARACTERES

    entrada = AskIn(
        pregunta=f"  {texto}  ",
    )

    assert entrada.pregunta_validada() == texto


def test_ask_in_rechaza_longitud_excedida():
    entrada = AskIn(
        pregunta="a" * (MAX_PREGUNTA_CARACTERES + 1),
    )

    with pytest.raises(PreguntaDemasiadoLargaError):
        entrada.pregunta_validada()


@pytest.mark.parametrize(
    "thread_id",
    [
        THREAD_ID,
        THREAD_ID.upper(),
        THREAD_ID.replace("-", ""),
    ],
)
def test_ask_in_normaliza_thread_id(thread_id):
    entrada = AskIn(
        pregunta="Consulta",
        thread_id=thread_id,
    )

    assert entrada.thread_id == THREAD_ID


@pytest.mark.parametrize(
    "thread_id",
    ["", "invalido", 123, True],
)
def test_ask_in_rechaza_thread_id_invalido(thread_id):
    with pytest.raises(ValidationError):
        AskIn(
            pregunta="Consulta",
            thread_id=thread_id,
        )


@pytest.mark.parametrize("max_steps", [1, 2, 3, 4])
def test_ask_in_acepta_max_steps_validos(max_steps):
    entrada = AskIn(
        pregunta="Consulta",
        max_steps=max_steps,
    )

    assert entrada.max_steps == max_steps


@pytest.mark.parametrize(
    "max_steps",
    [0, -1, 5, 8, True, False, "4", 4.0],
)
def test_ask_in_rechaza_max_steps_invalidos(max_steps):
    with pytest.raises(ValidationError):
        AskIn(
            pregunta="Consulta",
            max_steps=max_steps,
        )


@pytest.mark.parametrize(
    "auto_aprobar",
    ["true", "false", 1, 0, None],
)
def test_ask_in_rechaza_booleano_invalido(auto_aprobar):
    with pytest.raises(ValidationError):
        AskIn(
            pregunta="Consulta",
            auto_aprobar=auto_aprobar,
        )


def test_ask_in_rechaza_ubicacion_incompleta():
    with pytest.raises(ValidationError):
        AskIn(
            pregunta="Consulta",
            ubicacion={"latitud": 40.4168},
        )


def test_ask_in_rechaza_campos_adicionales():
    with pytest.raises(ValidationError):
        AskIn(
            pregunta="Consulta",
            role="admin",
        )


def test_ask_in_rechaza_campos_adicionales_anidados():
    with pytest.raises(ValidationError):
        AskIn(
            pregunta="Consulta",
            ubicacion={
                "latitud": 40.4168,
                "longitud": -3.7038,
                "distrito": "Centro",
            },
        )


# =========================================================
# APPROVE IN
# =========================================================

@pytest.mark.parametrize("aprobado", [True, False])
def test_approve_in_acepta_decision_valida(aprobado):
    entrada = ApproveIn(
        thread_id=THREAD_ID,
        approval_id=APPROVAL_ID,
        aprobado=aprobado,
    )

    assert entrada.thread_id == THREAD_ID
    assert entrada.approval_id == APPROVAL_ID
    assert entrada.aprobado is aprobado


@pytest.mark.parametrize(
    "campo",
    ["thread_id", "approval_id", "aprobado"],
)
def test_approve_in_requiere_todos_los_campos(campo):
    datos = {
        "thread_id": THREAD_ID,
        "approval_id": APPROVAL_ID,
        "aprobado": True,
    }

    del datos[campo]

    with pytest.raises(ValidationError):
        ApproveIn(**datos)


@pytest.mark.parametrize(
    "campo",
    ["thread_id", "approval_id"],
)
@pytest.mark.parametrize(
    "valor",
    ["", "invalido", 123, None],
)
def test_approve_in_rechaza_identificadores_invalidos(campo, valor):
    datos = {
        "thread_id": THREAD_ID,
        "approval_id": APPROVAL_ID,
        "aprobado": True,
    }

    datos[campo] = valor

    with pytest.raises(ValidationError):
        ApproveIn(**datos)


@pytest.mark.parametrize(
    "aprobado",
    ["true", "false", 1, 0, None],
)
def test_approve_in_rechaza_booleano_invalido(aprobado):
    with pytest.raises(ValidationError):
        ApproveIn(
            thread_id=THREAD_ID,
            approval_id=APPROVAL_ID,
            aprobado=aprobado,
        )


def test_approve_in_rechaza_plan_proporcionado_por_cliente():
    with pytest.raises(ValidationError):
        ApproveIn(
            thread_id=THREAD_ID,
            approval_id=APPROVAL_ID,
            aprobado=True,
            plan=["Plan modificado por el cliente"],
        )