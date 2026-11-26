"""Pruebas de los contratos públicos HTTP."""

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from api.config import MAX_API_STEPS
from api.error_catalog import ErrorCode
from api.exception_handlers import build_error_responses
from api.schemas import (
    ActiveStatusIn,
    AdminApiKeyCreateIn,
    ApiKeyCreateIn,
    ApiKeyCreatedOut,
    ApiKeyOut,
    ApiSchema,
    ApproveIn,
    AskIn,
    AskOut,
    ConversationOut,
    FuenteOut,
    GeografiaOut,
    HealthOut,
    LoginIn,
    LoginOut,
    MessageOut,
    PasswordChangeIn,
    PuntoLimpioOut,
    RegisterIn,
    UbicacionIn,
    UserOut,
)
from config import (
    GEO_MAX_LATITUDE,
    GEO_MAX_LONGITUDE,
    GEO_MAX_RADIUS_METERS,
    GEO_MAX_RESULTS,
    GEO_MIN_LATITUDE,
    GEO_MIN_LONGITUDE,
    GEO_MIN_RADIUS_METERS,
    MAX_PREGUNTA_CARACTERES,
)
from src.enums import ApiKeyRole, MessageRole
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


# =========================================================
# FUENTE OUT
# =========================================================

def test_fuente_out_valida():
    fuente = FuenteOut(
        chunk_id="C1",
        source="fraccion_vidrio.html",
        url="https://www.madrid.es/",
        rol="residuos",
        id_llamada="llamada-1",
    )

    assert fuente.chunk_id == "C1"
    assert fuente.rol == "residuos"
    assert str(fuente.url) == "https://www.madrid.es/"


def test_fuente_out_admite_opcionales_omitidos():
    fuente = FuenteOut(
        chunk_id="C1",
        source="fraccion_vidrio.html",
    )

    assert fuente.url is None
    assert fuente.rol is None
    assert fuente.id_llamada is None


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("chunk_id", ""),
        ("chunk_id", "   "),
        ("source", ""),
        ("source", "   "),
        ("rol", "admin"),
        ("url", "file:///documento.pdf"),
        ("url", "ftp://servidor.es/documento.pdf"),
        ("url", "documento.pdf"),
    ],
)
def test_fuente_out_rechaza_valores_invalidos(campo, valor):
    datos = {
        "chunk_id": "C1",
        "source": "fraccion_vidrio.html",
    }

    datos[campo] = valor

    with pytest.raises(ValidationError):
        FuenteOut(**datos)


@pytest.mark.parametrize(
    "campo",
    ["path", "text", "embedding"],
)
def test_fuente_out_rechaza_campos_internos(campo):
    datos = {
        "chunk_id": "C1",
        "source": "fraccion_vidrio.html",
        campo: "información interna",
    }

    with pytest.raises(ValidationError):
        FuenteOut(**datos)


# =========================================================
# PUNTO LIMPIO OUT
# =========================================================

@pytest.fixture
def punto_limpio_valido():
    return {
        "tipo": "fijo",
        "direccion": "Calle de prueba, 10",
        "latitud": 40.4168,
        "longitud": -3.7038,
        "distancia_metros": 250.0,
    }


def test_punto_limpio_out_valido(punto_limpio_valido):
    punto = PuntoLimpioOut(**punto_limpio_valido)

    assert punto.tipo == "fijo"
    assert punto.distancia_metros == 250.0
    assert punto.distrito is None


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("tipo", ""),
        ("direccion", "   "),
        ("latitud", 91),
        ("longitud", -181),
        ("latitud", True),
        ("longitud", "40"),
        ("distancia_metros", -1),
        ("distancia_metros", True),
        ("distancia_metros", "250"),
        ("distancia_metros", float("nan")),
        ("distancia_metros", float("inf")),
    ],
)
def test_punto_limpio_out_rechaza_valores_invalidos(
    punto_limpio_valido,
    campo,
    valor,
):
    punto_limpio_valido[campo] = valor

    with pytest.raises(ValidationError):
        PuntoLimpioOut(**punto_limpio_valido)


def test_punto_limpio_out_conserva_horarios(
    punto_limpio_valido,
):
    punto_limpio_valido["horario_apertura"] = (
        "09:00, excepto festivos"
    )

    punto = PuntoLimpioOut(**punto_limpio_valido)

    assert punto.horario_apertura == "09:00, excepto festivos"


# =========================================================
# GEOGRAFIA OUT
# =========================================================

@pytest.fixture
def geografia_valida(punto_limpio_valido):
    return {
        "fuente": "api",
        "tipo_solicitado": "todos",
        "radio_metros": 2000,
        "total_encontrados": 1,
        "puntos": [punto_limpio_valido],
        "aviso": None,
    }


def test_geografia_out_valida(geografia_valida):
    resultado = GeografiaOut(**geografia_valida)

    assert resultado.total_encontrados == 1
    assert len(resultado.puntos) == 1


def test_geografia_out_acepta_busqueda_vacia(
    geografia_valida,
):
    geografia_valida["total_encontrados"] = 0
    geografia_valida["puntos"] = []

    resultado = GeografiaOut(**geografia_valida)

    assert resultado.total_encontrados == 0
    assert resultado.puntos == []


def test_geografia_out_acepta_limite_presentacion(
    geografia_valida,
    punto_limpio_valido,
):
    geografia_valida["total_encontrados"] = 15

    geografia_valida["puntos"] = [
        {
            **punto_limpio_valido,
            "distancia_metros": 100.0 * indice,
        }
        for indice in range(1, 11)
    ]

    resultado = GeografiaOut(**geografia_valida)

    assert resultado.total_encontrados == 15
    assert len(resultado.puntos) == 10


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("fuente", "desconocida"),
        ("tipo_solicitado", "desconocido"),
        ("radio_metros", 0),
        ("radio_metros", 5001),
        ("radio_metros", True),
        ("total_encontrados", -1),
        ("total_encontrados", True),
        ("total_encontrados", 0),
        ("total_encontrados", 2),
    ],
)
def test_geografia_out_rechaza_valores_invalidos(
    geografia_valida,
    campo,
    valor,
):
    geografia_valida[campo] = valor

    with pytest.raises(ValidationError):
        GeografiaOut(**geografia_valida)


def test_geografia_out_rechaza_mas_de_diez_puntos(
    geografia_valida,
    punto_limpio_valido,
):
    geografia_valida["total_encontrados"] = 11
    geografia_valida["puntos"] = [
        punto_limpio_valido.copy()
        for _ in range(11)
    ]

    with pytest.raises(ValidationError):
        GeografiaOut(**geografia_valida)


def test_geografia_out_rechaza_puntos_desordenados(
    geografia_valida,
    punto_limpio_valido,
):
    geografia_valida["total_encontrados"] = 2

    geografia_valida["puntos"] = [
        {
            **punto_limpio_valido,
            "distancia_metros": 500.0,
        },
        {
            **punto_limpio_valido,
            "distancia_metros": 100.0,
        },
    ]

    with pytest.raises(ValidationError):
        GeografiaOut(**geografia_valida)


def test_geografia_out_rechaza_puntos_fuera_del_radio(
    geografia_valida,
):
    geografia_valida["puntos"][0]["distancia_metros"] = 2001.0

    with pytest.raises(ValidationError):
        GeografiaOut(**geografia_valida)


@pytest.mark.parametrize("aviso", [None, "", "   "])
def test_geografia_out_exige_aviso_en_respaldo_local(
    geografia_valida,
    aviso,
):
    geografia_valida["fuente"] = "corpus_local"
    geografia_valida["aviso"] = aviso

    with pytest.raises(ValidationError):
        GeografiaOut(**geografia_valida)


def test_geografia_out_acepta_respaldo_local(
    geografia_valida,
):
    geografia_valida["fuente"] = "corpus_local"

    geografia_valida["aviso"] = (
        "Los datos pueden estar desactualizados."
    )

    resultado = GeografiaOut(**geografia_valida)

    assert resultado.fuente == "corpus_local"


def test_geografia_out_rechaza_candidatos_internos(
    geografia_valida,
):
    geografia_valida["puntos_candidatos"] = []

    with pytest.raises(ValidationError):
        GeografiaOut(**geografia_valida)


# =========================================================
# ASK OUT
# =========================================================

@pytest.fixture
def ask_out_pendiente():
    return {
        "thread_id": THREAD_ID,
        "respuesta": "Las pilas deben depositarse en puntos autorizados.",
        "plan": [
            "Identificar el punto de recogida.",
            "Depositar las pilas correctamente.",
        ],
        "plan_aprobado": None,
        "done": False,
        "pendiente_hitl": True,
        "fuentes": [],
        "geografia": [],
        "abstencion": False,
        "motivo": None,
        "estado_evidencia": "suficiente",
        "limitaciones": [],
        "turnos_consumidos": 1,
        "error": None,
        "approval_id": APPROVAL_ID,
    }


def test_ask_out_propuesta_pendiente(ask_out_pendiente):
    respuesta = AskOut(**ask_out_pendiente)

    assert respuesta.pendiente_hitl is True
    assert respuesta.plan_aprobado is None
    assert respuesta.approval_id == APPROVAL_ID


def test_ask_out_plan_aprobado(ask_out_pendiente):
    ask_out_pendiente.update(
        pendiente_hitl=False,
        plan_aprobado=True,
        done=True,
        approval_id=None,
    )

    respuesta = AskOut(**ask_out_pendiente)

    assert respuesta.done is True
    assert respuesta.plan_aprobado is True


def test_ask_out_plan_rechazado(ask_out_pendiente):
    ask_out_pendiente.update(
        respuesta="Plan rechazado. Puedes reformular tu consulta.",
        pendiente_hitl=False,
        plan_aprobado=False,
        done=False,
        approval_id=None,
        plan=[],
        abstencion=True,
        estado_evidencia="insuficiente",
    )

    respuesta = AskOut(**ask_out_pendiente)

    assert respuesta.plan_aprobado is False
    assert respuesta.plan == []
    assert respuesta.done is False


@pytest.fixture
def ask_out_previo(ask_out_pendiente):
    ask_out_pendiente.update(
        thread_id=None,
        respuesta="Necesito que concretes el residuo.",
        plan=[],
        pendiente_hitl=False,
        plan_aprobado=None,
        approval_id=None,
        abstencion=True,
        estado_evidencia="insuficiente",
        turnos_consumidos=0,
    )

    return ask_out_pendiente


def test_ask_out_respuesta_previa(ask_out_previo):
    respuesta = AskOut(**ask_out_previo)

    assert respuesta.thread_id is None
    assert respuesta.turnos_consumidos == 0
    assert respuesta.abstencion is True


def test_ask_out_respuesta_previa_con_hilo_existente(
    ask_out_previo,
):
    ask_out_previo.update(
        thread_id=THREAD_ID,
        turnos_consumidos=2,
    )

    respuesta = AskOut(**ask_out_previo)

    assert respuesta.thread_id == THREAD_ID
    assert respuesta.turnos_consumidos == 2


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("respuesta", ""),
        ("respuesta", "   "),
        ("plan", []),
        ("plan", ["Un único paso"]),
        ("plan", ["Primer paso", "   "]),
        ("plan_aprobado", True),
        ("plan_aprobado", False),
        ("done", True),
        ("approval_id", None),
        ("approval_id", "invalido"),
        ("thread_id", None),
        ("turnos_consumidos", 0),
        ("turnos_consumidos", -1),
        ("turnos_consumidos", True),
        ("error", "Fallo interno"),
        ("error", ""),
        ("pendiente_hitl", "true"),
        ("estado_evidencia", "desconocido"),
    ],
)
def test_ask_out_rechaza_propuesta_inconsistente(
    ask_out_pendiente,
    campo,
    valor,
):
    ask_out_pendiente[campo] = valor

    with pytest.raises(ValidationError):
        AskOut(**ask_out_pendiente)


@pytest.mark.parametrize(
    "cambios",
    [
        {"done": False},
        {"approval_id": APPROVAL_ID},
        {"plan": []},
    ],
)
def test_ask_out_rechaza_aprobacion_inconsistente(
    ask_out_pendiente,
    cambios,
):
    ask_out_pendiente.update(
        pendiente_hitl=False,
        plan_aprobado=True,
        done=True,
        approval_id=None,
    )

    ask_out_pendiente.update(cambios)

    with pytest.raises(ValidationError):
        AskOut(**ask_out_pendiente)


@pytest.mark.parametrize(
    "cambios",
    [
        {"done": True},
        {"approval_id": APPROVAL_ID},
        {"plan": ["Primer paso", "Segundo paso"]},
    ],
)
def test_ask_out_rechaza_rechazo_inconsistente(
    ask_out_pendiente,
    cambios,
):
    ask_out_pendiente.update(
        pendiente_hitl=False,
        plan_aprobado=False,
        done=False,
        approval_id=None,
        plan=[],
    )

    ask_out_pendiente.update(cambios)

    with pytest.raises(ValidationError):
        AskOut(**ask_out_pendiente)


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("done", True),
        ("approval_id", APPROVAL_ID),
        ("plan", ["Primer paso", "Segundo paso"]),
        ("abstencion", False),
        ("estado_evidencia", "suficiente"),
        ("turnos_consumidos", 1),
    ],
)
def test_ask_out_rechaza_respuesta_previa_inconsistente(
    ask_out_previo,
    campo,
    valor,
):
    ask_out_previo[campo] = valor

    with pytest.raises(ValidationError):
        AskOut(**ask_out_previo)


def test_ask_out_respuesta_previa_rechaza_fuentes(
    ask_out_previo,
):
    ask_out_previo["fuentes"] = [
        {
            "chunk_id": "C1",
            "source": "fraccion_vidrio.html",
        }
    ]

    with pytest.raises(ValidationError):
        AskOut(**ask_out_previo)


def test_ask_out_respuesta_previa_rechaza_geografia(
    ask_out_previo,
    geografia_valida,
):
    ask_out_previo["geografia"] = [geografia_valida]

    with pytest.raises(ValidationError):
        AskOut(**ask_out_previo)


def test_ask_out_valida_modelos_anidados(
    ask_out_pendiente,
    geografia_valida,
):
    ask_out_pendiente["geografia"] = [geografia_valida]

    ask_out_pendiente["fuentes"] = [
        {
            "chunk_id": "C1",
            "source": "fraccion_vidrio.html",
        }
    ]

    respuesta = AskOut(**ask_out_pendiente)

    assert isinstance(respuesta.fuentes[0], FuenteOut)
    assert isinstance(respuesta.geografia[0], GeografiaOut)
    assert isinstance(
        respuesta.geografia[0].puntos[0],
        PuntoLimpioOut,
    )


def test_ask_out_requiere_todos_los_campos(
    ask_out_pendiente,
):
    for campo in AskOut.model_fields:
        datos = ask_out_pendiente.copy()

        del datos[campo]

        with pytest.raises(ValidationError):
            AskOut(**datos)


@pytest.mark.parametrize(
    "campo",
    [
        "checkpoint",
        "evidencias",
        "historial_turnos",
        "traza_tools",
        "log",
    ],
)
def test_ask_out_rechaza_campos_internos(
    ask_out_pendiente,
    campo,
):
    ask_out_pendiente[campo] = []

    with pytest.raises(ValidationError):
        AskOut(**ask_out_pendiente)


# =========================================================
# MESSAGE OUT
# =========================================================

@pytest.fixture
def mensaje_valido() -> dict[str, object]:
    """Proporciona los datos válidos de un mensaje."""

    return {
        "role": "user",
        "content": "¿Dónde debo reciclar una pila?",
        "created_at": datetime(
            2026, 11, 25, 15, 30, tzinfo=timezone.utc
        ),
    }


@pytest.mark.parametrize("role", list(MessageRole))
def test_message_out_acepta_roles_validos(
    mensaje_valido: dict[str, object],
    role: MessageRole,
) -> None:
    mensaje_valido["role"] = role.value

    mensaje = MessageOut(**mensaje_valido)

    assert mensaje.role == role
    assert isinstance(mensaje.role, MessageRole)


@pytest.mark.parametrize(
    "role",
    ["system", "admin", "tool", "", None, True],
)
def test_message_out_rechaza_roles_invalidos(
    mensaje_valido: dict[str, object],
    role: object,
) -> None:
    mensaje_valido["role"] = role

    with pytest.raises(ValidationError):
        MessageOut(**mensaje_valido)


@pytest.mark.parametrize(
    "content",
    ["", "   ", "\t\n", None, True, 123],
)
def test_message_out_rechaza_contenido_invalido(
    mensaje_valido: dict[str, object],
    content: object,
) -> None:
    mensaje_valido["content"] = content

    with pytest.raises(ValidationError):
        MessageOut(**mensaje_valido)


def test_message_out_conserva_contenido(
    mensaje_valido: dict[str, object],
) -> None:
    contenido = "  Primera línea.\nSegunda línea.  "
    mensaje_valido["content"] = contenido

    mensaje = MessageOut(**mensaje_valido)

    assert mensaje.content == contenido


def test_message_out_normaliza_fecha_utc(
    mensaje_valido: dict[str, object],
) -> None:
    mensaje_valido["created_at"] = datetime(
        2026,
        11,
        25,
        16,
        30,
        tzinfo=timezone(timedelta(hours=1)),
    )

    mensaje = MessageOut(**mensaje_valido)

    assert mensaje.created_at.hour == 15
    assert mensaje.created_at.utcoffset() == timedelta(0)


def test_message_out_rechaza_fecha_sin_zona(
    mensaje_valido: dict[str, object],
) -> None:
    mensaje_valido["created_at"] = datetime(2026, 11, 25)

    with pytest.raises(ValidationError):
        MessageOut(**mensaje_valido)


@pytest.mark.parametrize(
    "campo",
    ["id", "thread_id", "turn_number"],
)
def test_message_out_rechaza_campos_internos(
    mensaje_valido: dict[str, object],
    campo: str,
) -> None:
    mensaje_valido[campo] = "dato interno"

    with pytest.raises(ValidationError):
        MessageOut(**mensaje_valido)


@pytest.mark.parametrize(
    "campo",
    list(MessageOut.model_fields),
)
def test_message_out_requiere_todos_los_campos(
    mensaje_valido: dict[str, object],
    campo: str,
) -> None:
    del mensaje_valido[campo]

    with pytest.raises(ValidationError):
        MessageOut(**mensaje_valido)


def test_message_out_serializacion_publica(
    mensaje_valido: dict[str, object],
) -> None:
    mensaje = MessageOut(**mensaje_valido)
    resultado = mensaje.model_dump(mode="json")

    assert resultado == {
        "role": "user",
        "content": "¿Dónde debo reciclar una pila?",
        "created_at": "2026-11-25T15:30:00Z",
    }


# =========================================================
# CONVERSATION OUT
# =========================================================

@pytest.fixture
def conversacion_valida() -> dict[str, object]:
    """Proporciona los datos válidos de una conversación."""

    return {
        "thread_id": THREAD_ID,
        "api_key_id": "550e8400-e29b-41d4-a716-446655440002",
        "created_at": datetime(
            2026, 11, 25, 15, 30, tzinfo=timezone.utc
        ),
    }


def test_conversation_out_valida(
    conversacion_valida: dict[str, object],
) -> None:
    conversacion = ConversationOut(**conversacion_valida)

    assert conversacion.thread_id == THREAD_ID
    assert conversacion.api_key_id == conversacion_valida["api_key_id"]


@pytest.mark.parametrize("campo", ["thread_id", "api_key_id"])
def test_conversation_out_normaliza_uuid(
    conversacion_valida: dict[str, object],
    campo: str,
) -> None:
    identificador = str(conversacion_valida[campo])
    conversacion_valida[campo] = identificador.upper()

    conversacion = ConversationOut(**conversacion_valida)

    assert getattr(conversacion, campo) == identificador


@pytest.mark.parametrize("campo", ["thread_id", "api_key_id"])
@pytest.mark.parametrize(
    "valor",
    ["", "invalido", None, True, 123],
)
def test_conversation_out_rechaza_uuid_invalido(
    conversacion_valida: dict[str, object],
    campo: str,
    valor: object,
) -> None:
    conversacion_valida[campo] = valor

    with pytest.raises(ValidationError):
        ConversationOut(**conversacion_valida)


def test_conversation_out_rechaza_fecha_sin_zona(
    conversacion_valida: dict[str, object],
) -> None:
    conversacion_valida["created_at"] = datetime(2026, 11, 25)

    with pytest.raises(ValidationError):
        ConversationOut(**conversacion_valida)


@pytest.mark.parametrize(
    "campo",
    [
        "id",
        "checkpoint",
        "approval_id",
        "pendiente_hitl",
        "plan",
        "turnos_consumidos",
        "api_key",
        "key_hash",
    ],
)
def test_conversation_out_rechaza_campos_internos(
    conversacion_valida: dict[str, object],
    campo: str,
) -> None:
    conversacion_valida[campo] = "dato interno"

    with pytest.raises(ValidationError):
        ConversationOut(**conversacion_valida)


@pytest.mark.parametrize(
    "campo",
    list(ConversationOut.model_fields),
)
def test_conversation_out_requiere_todos_los_campos(
    conversacion_valida: dict[str, object],
    campo: str,
) -> None:
    del conversacion_valida[campo]

    with pytest.raises(ValidationError):
        ConversationOut(**conversacion_valida)


def test_conversation_out_serializacion_publica(
    conversacion_valida: dict[str, object],
) -> None:
    conversacion = ConversationOut(**conversacion_valida)

    assert conversacion.model_dump(mode="json") == {
        "thread_id": THREAD_ID,
        "api_key_id": conversacion_valida["api_key_id"],
        "created_at": "2026-11-25T15:30:00Z",
    }


# =========================================================
# HEALTH OUT
# =========================================================

def test_health_out_valido() -> None:
    resultado = HealthOut(
        status="ok",
        storage="postgres",
    )

    assert resultado.model_dump(mode="json") == {
        "status": "ok",
        "storage": "postgres",
    }


@pytest.mark.parametrize(
    "status, storage",
    [
        ("error", "postgres"),
        ("degraded", "postgres"),
        ("ok", "sqlite"),
        ("ok", "mysql"),
        ("ok", ""),
        ("ok", None),
        ("OK", "postgres"),
        (True, "postgres"),
    ],
)
def test_health_out_rechaza_estados_invalidos(
    status: object,
    storage: object,
) -> None:
    with pytest.raises(ValidationError):
        HealthOut(
            status=status,
            storage=storage,
        )


@pytest.mark.parametrize(
    "datos",
    [
        {},
        {"status": "ok"},
        {"storage": "postgres"},
    ],
)
def test_health_out_requiere_todos_los_campos(
    datos: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        HealthOut(**datos)


@pytest.mark.parametrize(
    "campo",
    ["database_url", "error", "version", "gemini_api_key"],
)
def test_health_out_rechaza_campos_adicionales(
    campo: str,
) -> None:
    datos = {
        "status": "ok",
        "storage": "postgres",
        campo: "dato interno",
    }

    with pytest.raises(ValidationError):
        HealthOut(**datos)


# =========================================================
# VALIDACIÓN DE OPENAPI
# =========================================================


@pytest.fixture(scope="module")
def openapi_components() -> dict[str, Any]:
    """Genera los esquemas OpenAPI de los contratos públicos."""
    application = FastAPI()

    @application.post(
        "/ask",
        response_model=AskOut,
        responses=build_error_responses(
            ErrorCode.VALIDATION_ERROR,
        ),
    )
    def ask(data: AskIn) -> None:
        """Declara el contrato de consulta."""

    @application.post("/approve", response_model=AskOut)
    def approve(data: ApproveIn) -> None:
        """Declara el contrato de aprobación."""

    @application.post(
        "/auth/register",
        status_code=201,
        response_model=UserOut,
    )
    def register(data: RegisterIn) -> None:
        """Declara el contrato de registro."""

    @application.post("/auth/login", response_model=LoginOut)
    def login(data: LoginIn) -> None:
        """Declara el contrato de inicio de sesión."""

    @application.patch("/auth/password", response_model=UserOut)
    def change_password(data: PasswordChangeIn) -> None:
        """Declara el contrato de cambio de contraseña."""

    @application.post(
        "/api-keys",
        status_code=201,
        response_model=ApiKeyCreatedOut,
    )
    def create_api_key(data: ApiKeyCreateIn) -> None:
        """Declara el contrato de emisión ordinaria."""

    @application.post(
        "/admin/api-keys",
        status_code=201,
        response_model=ApiKeyCreatedOut,
    )
    def admin_create_api_key(data: AdminApiKeyCreateIn) -> None:
        """Declara el contrato de emisión administrativa."""

    @application.patch("/admin/users/{user_id}",
                       response_model=UserOut)
    def update_user(user_id: str, data: ActiveStatusIn) -> None:
        """Declara el contrato de modificación de estado."""

    @application.get("/health", response_model=HealthOut)
    @application.get("/api-keys", response_model=list[ApiKeyOut])
    @application.get("/threads",
                     response_model=list[ConversationOut])
    @application.get("/threads/{thread_id}/messages",
                     response_model=list[MessageOut])
    def read_contracts() -> None:
        """Declara los contratos restantes de salida."""

    return application.openapi()["components"]["schemas"]


@pytest.mark.parametrize(
    "model_name",
    [
        "UbicacionIn",
        "AskIn",
        "ApproveIn",
        "FuenteOut",
        "PuntoLimpioOut",
        "GeografiaOut",
        "AskOut",
        "RegisterIn",
        "LoginIn",
        "PasswordChangeIn",
        "ApiKeyCreateIn",
        "AdminApiKeyCreateIn",
        "ActiveStatusIn",
        "UserOut",
        "LoginOut",
        "ApiKeyOut",
        "ApiKeyCreatedOut",
        "MessageOut",
        "ConversationOut",
        "HealthOut",
        "ErrorOut",
    ],
)
def test_public_openapi_models(
    openapi_components: dict[str, Any],
    model_name: str,
) -> None:
    """Comprueba la presencia y configuración de cada modelo."""
    schema = openapi_components[model_name]

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert "properties" in schema


def test_openapi_ask_input(
    openapi_components: dict[str, Any],
) -> None:
    """Comprueba la estructura pública de AskIn."""
    schema = openapi_components["AskIn"]
    properties = schema["properties"]

    assert set(schema["required"]) == {"pregunta"}
    assert properties["auto_aprobar"]["default"] is True
    assert properties["pregunta"]["type"] == "string"

    assert str(MAX_PREGUNTA_CARACTERES) in (
        properties["pregunta"]["description"]
    )

    for field_name in ("thread_id", "ubicacion", "max_steps"):
        field = properties[field_name]

        assert {"type": "null"} in field["anyOf"]
        assert field.get("default") is None


def test_openapi_ask_output(
    openapi_components: dict[str, Any],
) -> None:
    """Exige todos los campos de una respuesta AskOut."""
    schema = openapi_components["AskOut"]
    properties = schema["properties"]

    assert set(schema["required"]) == set(properties)

    for field_name in (
        "thread_id",
        "approval_id",
        "plan_aprobado",
        "motivo",
        "error",
    ):
        assert {"type": "null"} in (
            properties[field_name]["anyOf"]
        )


def test_openapi_error_output(
    openapi_components: dict[str, Any],
) -> None:
    """Comprueba los campos obligatorios de ErrorOut."""
    schema = openapi_components["ErrorOut"]

    assert set(schema["required"]) == {
        "code",
        "message",
        "request_id",
    }


def test_openapi_location_limits(
    openapi_components: dict[str, Any],
) -> None:
    """Comprueba los límites geográficos documentados."""
    properties = openapi_components["UbicacionIn"]["properties"]

    latitude = properties["latitud"]
    longitude = properties["longitud"]

    assert latitude["minimum"] == GEO_MIN_LATITUDE
    assert latitude["maximum"] == GEO_MAX_LATITUDE
    assert longitude["minimum"] == GEO_MIN_LONGITUDE
    assert longitude["maximum"] == GEO_MAX_LONGITUDE


def test_openapi_max_steps(
    openapi_components: dict[str, Any],
) -> None:
    """Comprueba los límites de ejecución del asistente."""
    properties = openapi_components["AskIn"]["properties"]

    integer_schema = next(
        item
        for item in properties["max_steps"]["anyOf"]
        if item.get("type") == "integer"
    )

    assert integer_schema["minimum"] == 1
    assert integer_schema["maximum"] == MAX_API_STEPS


def test_openapi_geography_limits(
    openapi_components: dict[str, Any],
) -> None:
    """Comprueba las restricciones del resultado geográfico."""
    properties = openapi_components["GeografiaOut"]["properties"]

    radius = properties["radio_metros"]

    assert radius["minimum"] == GEO_MIN_RADIUS_METERS
    assert radius["maximum"] == GEO_MAX_RADIUS_METERS
    assert properties["puntos"]["maxItems"] == GEO_MAX_RESULTS
    assert properties["total_encontrados"]["minimum"] == 0


@pytest.mark.parametrize(
    "model_name, field_name",
    [
        ("ApproveIn", "thread_id"),
        ("ApproveIn", "approval_id"),
        ("ConversationOut", "thread_id"),
        ("ConversationOut", "api_key_id"),
        ("UserOut", "id"),
        ("ApiKeyOut", "id"),
        ("ApiKeyCreatedOut", "id"),
        ("ErrorOut", "request_id"),
    ],
)
def test_openapi_uuid_format(
    openapi_components: dict[str, Any],
    model_name: str,
    field_name: str,
) -> None:
    """Documenta correctamente los identificadores UUID."""
    field = openapi_components[model_name]["properties"][field_name]

    assert field["type"] == "string"
    assert field["format"] == "uuid"


@pytest.mark.parametrize(
    "model_name, field_name",
    [
        ("UserOut", "created_at"),
        ("ApiKeyOut", "created_at"),
        ("ApiKeyCreatedOut", "created_at"),
        ("LoginOut", "expires_at"),
        ("ConversationOut", "created_at"),
        ("MessageOut", "created_at"),
    ],
)
def test_openapi_datetime_format(
    openapi_components: dict[str, Any],
    model_name: str,
    field_name: str,
) -> None:
    """Documenta las fechas mediante el formato date-time."""
    field = openapi_components[model_name]["properties"][field_name]

    assert field["type"] == "string"
    assert field["format"] == "date-time"


@pytest.mark.parametrize(
    "model_name, field_name",
    [
        ("RegisterIn", "password"),
        ("LoginIn", "password"),
        ("PasswordChangeIn", "current_password"),
        ("PasswordChangeIn", "new_password"),
    ],
)
def test_openapi_password_fields(
    openapi_components: dict[str, Any],
    model_name: str,
    field_name: str,
) -> None:
    """Documenta las contraseñas como campos de escritura."""
    field = openapi_components[model_name]["properties"][field_name]

    assert field["type"] == "string"
    assert field["format"] == "password"
    assert field["writeOnly"] is True


@pytest.mark.parametrize("model_name", ["RegisterIn", "LoginIn"])
def test_openapi_email_format(
    openapi_components: dict[str, Any],
    model_name: str,
) -> None:
    """Documenta el formato de email en las entradas."""
    field = openapi_components[model_name]["properties"]["email"]

    assert field["format"] == "email"


def test_openapi_credential_outputs(
    openapi_components: dict[str, Any],
) -> None:
    """Excluye los hashes de los contratos públicos."""
    user = openapi_components["UserOut"]["properties"]
    api_key = openapi_components["ApiKeyOut"]["properties"]
    created = openapi_components["ApiKeyCreatedOut"]["properties"]
    login = openapi_components["LoginOut"]["properties"]

    assert "password_hash" not in user
    assert "key_hash" not in api_key
    assert "key_hash" not in created
    assert "api_key" not in api_key

    assert "api_key" in created
    assert "session_token" in login


def test_openapi_enums(
    openapi_components: dict[str, Any],
) -> None:
    """Comprueba los valores de los enumerados públicos."""
    for enum_type in (ErrorCode, ApiKeyRole, MessageRole):
        schema = openapi_components[enum_type.__name__]

        assert set(schema["enum"]) == {
            member.value
            for member in enum_type
        }


@pytest.mark.parametrize(
    "model_name",
    [
        "ApiKeyCreateIn",
        "AdminApiKeyCreateIn",
        "ApiKeyCreatedOut",
    ],
)
def test_openapi_issuable_roles(
    openapi_components: dict[str, Any],
    model_name: str,
) -> None:
    """Impide documentar Admin como rol de emisión."""
    role = openapi_components[model_name]["properties"]["role"]

    assert set(role["enum"]) == {
        ApiKeyRole.FREE.value,
        ApiKeyRole.USER.value,
    }


@pytest.mark.parametrize(
    "model_name, field_name, nested_model",
    [
        ("AskOut", "fuentes", "FuenteOut"),
        ("AskOut", "geografia", "GeografiaOut"),
        ("GeografiaOut", "puntos", "PuntoLimpioOut"),
    ],
)
def test_openapi_nested_lists(
    openapi_components: dict[str, Any],
    model_name: str,
    field_name: str,
    nested_model: str,
) -> None:
    """Comprueba las referencias de los modelos anidados."""
    field = openapi_components[model_name]["properties"][field_name]

    assert field["type"] == "array"
    assert field["items"]["$ref"] == (
        f"#/components/schemas/{nested_model}"
    )


def test_openapi_nested_user(
    openapi_components: dict[str, Any],
) -> None:
    """Comprueba la referencia al usuario autenticado."""
    field = openapi_components["LoginOut"]["properties"]["user"]

    assert field["$ref"] == "#/components/schemas/UserOut"


def test_openapi_user_deleted_at(
    openapi_components: dict[str, Any],
) -> None:
    """Documenta la fecha de eliminación como campo nullable."""
    schema = openapi_components["UserOut"]

    field = schema["properties"]["deleted_at"]

    assert "deleted_at" in schema["required"]

    assert any(
        item.get("type") == "null"
        for item in field["anyOf"]
    )

    assert any(
        item.get("type") == "string"
        and item.get("format") == "date-time"
        for item in field["anyOf"]
    )