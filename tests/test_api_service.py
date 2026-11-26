"""Pruebas del filtrado previo a la ejecución del agente."""

from uuid import uuid4
import pytest

from api.schemas import AskOut, UbicacionIn
from api.service import filtrar_entrada
from src.generation_validation import MENSAJE_ABSTENCION
from src.rag_intents import (
    MENSAJE_ACLARACION_CONTEXTO,
    MENSAJE_ACLARACION_HORARIO_MOVIL,
    MENSAJE_ACLARACION_PROXIMIDAD,
)


def test_filtrado_resuelve_reparacion_fuera_de_dominio():
    """Una reparación obtiene una respuesta anterior al agente."""
    resultado = filtrar_entrada("¿Dónde reparan teléfonos móviles?")

    assert isinstance(resultado, AskOut)
    assert resultado.respuesta == MENSAJE_ABSTENCION
    assert resultado.motivo == "fuera_de_dominio"
    assert resultado.abstencion is True
    assert resultado.estado_evidencia == "insuficiente"
    assert resultado.thread_id is None
    assert resultado.turnos_consumidos == 0
    assert resultado.pendiente_hitl is False
    assert resultado.plan_aprobado is None
    assert resultado.approval_id is None
    assert resultado.done is False
    assert resultado.error is None
    assert resultado.plan == []
    assert resultado.fuentes == []
    assert resultado.geografia == []


def test_filtrado_conserva_identificador_y_turnos():
    """Una respuesta previa conserva los datos autorizados del hilo."""
    thread_id = str(uuid4())

    resultado = filtrar_entrada(
        "¿Dónde reparan teléfonos móviles?",
        thread_id=thread_id,
        turnos_consumidos=2,
    )

    assert isinstance(resultado, AskOut)
    assert resultado.thread_id == thread_id
    assert resultado.turnos_consumidos == 2


def test_filtrado_permite_reciclaje_de_telefonos():
    """Una consulta admisible continúa por el flujo de ejecución."""
    resultado = filtrar_entrada("¿Dónde reciclo un teléfono móvil roto?")

    assert resultado is None


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Qué horario tiene el punto limpio móvil?",
        "¿Qué horario tiene el punto limpio móvil de Madrid?",
        "¿A qué hora pasa el punto limpio móvil en Madrid?",
    ],
)
def test_filtrado_aclara_horario_sin_ubicacion(pregunta):
    """Solicita una parada concreta antes de ejecutar el agente."""
    resultado = filtrar_entrada(pregunta)

    assert isinstance(resultado, AskOut)
    assert resultado.respuesta == MENSAJE_ACLARACION_HORARIO_MOVIL
    assert resultado.motivo == "ambiguedad"
    assert resultado.turnos_consumidos == 0
    assert resultado.pendiente_hitl is False


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Qué horario tiene el punto limpio móvil de Centro?",
        "¿Qué horario tiene el punto limpio móvil 24h?",
        "¿Qué horario tiene el punto limpio móvil de la calle Barcelona?",
        "¿Qué es un punto limpio móvil?",
        "¿Qué horario tiene el punto limpio móvil y qué residuos admite?",
    ],
)
def test_filtrado_no_intercepta_otras_consultas(pregunta):
    """Conserva las consultas documentales y compuestas."""
    assert filtrar_entrada(pregunta) is None


def test_filtrado_considera_contexto_anterior():
    """No pide datos que puedan existir en el contexto autorizado."""
    resultado = filtrar_entrada(
        "¿Qué horario tiene el punto limpio móvil?",
        contexto_revision="Consulta anterior sobre Centro.",
    )

    assert resultado is None


def test_filtrado_considera_entrada_visual():
    """No descarta información que pueda aportar una imagen."""
    resultado = filtrar_entrada(
        "¿Qué horario tiene el punto limpio móvil?",
        hay_imagen=True,
    )

    assert resultado is None


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Qué punto limpio tengo más cerca?",
        "¿Qué puntos limpios hay cerca de mí?",
        "Busca un punto limpio de proximidad cerca de mí",
        "¿Cuál es el punto limpio más próximo?",
    ],
)
def test_filtrado_aclara_proximidad_sin_coordenadas(pregunta):
    """Solicita coordenadas antes de iniciar una búsqueda espacial."""
    resultado = filtrar_entrada(pregunta)

    assert isinstance(resultado, AskOut)
    assert resultado.respuesta == MENSAJE_ACLARACION_PROXIMIDAD
    assert resultado.motivo == "ambiguedad"
    assert resultado.turnos_consumidos == 0
    assert resultado.pendiente_hitl is False


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Qué es un punto limpio de proximidad?",
        "¿Dónde tiro unas pilas y qué punto limpio tengo cerca?",
        "¿Qué punto limpio tengo más cerca para reciclar pilas?",
    ],
)
def test_filtrado_conserva_consultas_documentales_y_compuestas(pregunta):
    """No impide resolver consultas con contenido documental."""
    assert filtrar_entrada(pregunta) is None


def test_filtrado_permite_proximidad_con_coordenadas():
    """Una búsqueda con ubicación válida puede continuar."""
    ubicacion = UbicacionIn(latitud=40.4168, longitud=-3.7038)

    resultado = filtrar_entrada(
        "¿Qué punto limpio tengo más cerca?",
        ubicacion=ubicacion,
    )

    assert resultado is None


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Dónde reciclo vidrio en Barcelona?",
        "¿Dónde deposito residuos en Málaga?",
        "¿Qué horario tiene el punto limpio móvil de Bilbao?",
        "¿Dónde reciclo vidrio en la ciudad de Salamanca?",
    ],
)
def test_filtrado_resuelve_consultas_geograficas_externas(pregunta):
    """Reutiliza la restricción geográfica existente."""
    resultado = filtrar_entrada(pregunta)

    assert isinstance(resultado, AskOut)
    assert resultado.motivo == "fuera_de_dominio"
    assert resultado.turnos_consumidos == 0
    assert resultado.pendiente_hitl is False


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Dónde reciclo vidrio en Madrid?",
        "¿Dónde reciclo vidrio en Salamanca?",
        "¿Dónde deposito residuos en Carabanchel?",
        "¿Qué horario tiene el punto limpio móvil de la calle Barcelona?",
    ],
)
def test_filtrado_conserva_consultas_geograficas_admitidas(pregunta):
    """Respeta distritos, direcciones y el ámbito municipal."""
    assert filtrar_entrada(pregunta) is None


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Cómo programo una API?",
        "¿Cómo desarrollo una API REST?",
        "¿Cómo crear un programa informático?",
    ],
)
def test_filtrado_rechaza_consultas_de_programacion(pregunta):
    """Resuelve solicitudes ajenas al dominio sin ejecutar el agente."""
    resultado = filtrar_entrada(pregunta)

    assert isinstance(resultado, AskOut)
    assert resultado.motivo == "fuera_de_dominio"
    assert resultado.abstencion is True
    assert resultado.turnos_consumidos == 0
    assert resultado.pendiente_hitl is False


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Cómo reciclo un ordenador?",
        "¿Dónde tiro un ordenador que utilizaba para trabajar?",
        "¿Dónde tiro un ordenador que utilizaba para estudiar?",
        "¿Qué hago con una placa electrónica?",
    ],
)
def test_filtrado_conserva_consultas_de_residuos_electronicos(pregunta):
    """No confunde residuos electrónicos con desarrollo de software."""
    assert filtrar_entrada(pregunta) is None


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Y si es de plástico?",
        "¿Y mañana?",
        "¿Hay uno más cerca?",
        "¿Qué hago con esto?",
    ],
)
def test_filtrado_aclara_reformulacion_sin_contexto(pregunta):
    """Una referencia sin antecedente requiere aclaración."""
    resultado = filtrar_entrada(pregunta)

    assert isinstance(resultado, AskOut)
    assert resultado.respuesta == MENSAJE_ACLARACION_CONTEXTO
    assert resultado.motivo == "ambiguedad"
    assert resultado.turnos_consumidos == 0
    assert resultado.pendiente_hitl is False


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Y si es de plástico?",
        "¿Y mañana?",
        "¿Hay uno más cerca?",
        "¿Qué hago con esto?",
    ],
)
def test_filtrado_admite_reformulacion_con_contexto(pregunta):
    """Las referencias pueden interpretarse con contexto autorizado."""
    resultado = filtrar_entrada(
        pregunta,
        contexto_revision=(
            "Plan rechazado. Consulta original: "
            "¿Dónde reciclo una botella de vidrio?"
        ),
    )

    assert resultado is None


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Cómo programo una API?",
        "¿Dónde reparan teléfonos móviles?",
        "¿Dónde reciclo vidrio en Barcelona?",
    ],
)
def test_contexto_no_elude_restricciones_de_dominio(pregunta):
    """El contexto anterior no amplía el dominio autorizado."""
    thread_id = str(uuid4())

    resultado = filtrar_entrada(
        pregunta,
        contexto_revision="¿Dónde reciclo unas pilas?",
        thread_id=thread_id,
        turnos_consumidos=1,
    )

    assert isinstance(resultado, AskOut)
    assert resultado.motivo == "fuera_de_dominio"
    assert resultado.thread_id == thread_id
    assert resultado.turnos_consumidos == 1


def test_referencia_con_imagen_no_requiere_contexto():
    """Una imagen puede aportar el referente que falta."""
    assert filtrar_entrada("¿Qué hago con esto?", hay_imagen=True) is None


def test_contexto_no_sustituye_coordenadas():
    """Las coordenadas anteriores no se reutilizan automáticamente."""
    resultado = filtrar_entrada(
        "¿Qué punto limpio tengo más cerca?",
        contexto_revision="Consulta anterior sobre puntos limpios.",
    )

    assert isinstance(resultado, AskOut)
    assert resultado.respuesta == MENSAJE_ACLARACION_PROXIMIDAD