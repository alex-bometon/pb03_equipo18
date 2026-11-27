"""Pruebas del filtrado previo a la ejecución del agente."""

import json
import logging
from uuid import uuid4
import pytest
from pathlib import Path
from unittest.mock import Mock
from contextlib import ExitStack

from api.config import ApiSettings
from api.schemas import AskOut, UbicacionIn
from api.service import filtrar_entrada, identificar_entrada_visual
from src.generation_validation import MENSAJE_ABSTENCION
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.rate_limit import crear_limitador, reservar_cuota_comercial
from api.request_context import AuthContext
import api.service as servicio
from api.service import (
    ControlAdmision,
    EjecutorAsistente,
    PresupuestoEjecucion,
    filtrar_entrada,
    identificar_entrada_visual,
)
from src.enums import ApiKeyRole
from src.observability import (
    EVENT_LOGGER,
    registrar_evento,
    request_id_context,
)
from src.rag_intents import (
    MENSAJE_ACLARACION_CONTEXTO,
    MENSAJE_ACLARACION_HORARIO_MOVIL,
    MENSAJE_ACLARACION_PROXIMIDAD,
)


from concurrent.futures import ThreadPoolExecutor
from threading import Event


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


def test_identificacion_visual_admitida(tmp_path, monkeypatch):
    """Devuelve la identificación y elimina el archivo temporal."""
    assets = tmp_path / "assets"
    assets.mkdir()

    monkeypatch.setattr("api.images.ASSETS_DIR", assets)

    identificacion = {
        "estado": "allowed",
        "descripcion": "Una botella de plástico.",
    }

    def identificar(ruta):
        archivo = Path(ruta)

        assert archivo.exists()
        assert archivo.read_bytes() == b"imagen adaptada"

        return identificacion

    modelo = Mock(side_effect=identificar)

    monkeypatch.setattr("api.service.identificar_imagen", modelo)

    resultado = identificar_entrada_visual(b"imagen adaptada", "PNG")

    assert resultado == identificacion
    modelo.assert_called_once()

    ruta = Path(modelo.call_args.args[0])

    assert not ruta.exists()


@pytest.mark.parametrize(
    "estado, motivo",
    [("out_of_domain", "fuera_de_dominio"), ("uncertain", "ambiguedad")],
)
@pytest.mark.parametrize("con_hilo", [True, False])
def test_identificacion_visual_no_admitida(
    tmp_path,
    monkeypatch,
    estado,
    motivo,
    con_hilo,
):
    """Resuelve rechazos semánticos sin iniciar otro turno."""
    assets = tmp_path / "assets"
    assets.mkdir()

    monkeypatch.setattr("api.images.ASSETS_DIR", assets)

    modelo = Mock(return_value={
        "estado": estado,
        "descripcion": "Descripción interna no publicable.",
    })

    monkeypatch.setattr("api.service.identificar_imagen", modelo)

    hilo = str(uuid4()) if con_hilo else None
    turnos = 1 if con_hilo else 0

    resultado = identificar_entrada_visual(
        b"imagen adaptada",
        "PNG",
        thread_id=hilo,
        turnos_consumidos=turnos,
    )

    assert isinstance(resultado, AskOut)
    assert resultado.thread_id == hilo
    assert resultado.turnos_consumidos == turnos
    assert resultado.motivo == motivo
    assert resultado.abstencion is True
    assert resultado.estado_evidencia == "insuficiente"
    assert resultado.pendiente_hitl is False
    assert resultado.plan_aprobado is None
    assert resultado.approval_id is None
    assert resultado.done is False
    assert resultado.error is None
    assert resultado.plan == []
    assert resultado.fuentes == []
    assert resultado.geografia == []

    assert "Descripción interna" not in resultado.respuesta

    modelo.assert_called_once()

    assert not Path(modelo.call_args.args[0]).exists()


def test_identificacion_visual_contenido_no_permitido(
    tmp_path,
    monkeypatch,
):
    """Transforma una infracción semántica en el error previsto."""
    assets = tmp_path / "assets"
    assets.mkdir()

    monkeypatch.setattr("api.images.ASSETS_DIR", assets)

    modelo = Mock(return_value={
        "estado": "policy_violation",
        "descripcion": "Contenido no permitido.",
    })

    monkeypatch.setattr("api.service.identificar_imagen", modelo)

    with pytest.raises(ApiError) as error:
        identificar_entrada_visual(b"imagen adaptada", "JPEG")

    assert error.value.code == ErrorCode.IMAGE_CONTENT_NOT_ALLOWED

    modelo.assert_called_once()

    assert not Path(modelo.call_args.args[0]).exists()


def test_identificacion_visual_fallo_tecnico(
    tmp_path,
    monkeypatch,
):
    """Propaga el fallo técnico y libera el archivo temporal."""
    assets = tmp_path / "assets"
    assets.mkdir()

    monkeypatch.setattr("api.images.ASSETS_DIR", assets)

    modelo = Mock(side_effect=RuntimeError("Fallo simulado de Gemini"))

    monkeypatch.setattr("api.service.identificar_imagen", modelo)

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        identificar_entrada_visual(b"imagen adaptada", "PNG")

    modelo.assert_called_once()

    assert not Path(modelo.call_args.args[0]).exists()


def test_archivo_visual_permanece_hasta_finalizacion_real(
    tmp_path,
    monkeypatch,
):
    """Conserva el archivo mientras el worker sigue utilizándolo."""
    assets = tmp_path / "assets"
    assets.mkdir()

    monkeypatch.setattr("api.images.ASSETS_DIR", assets)

    iniciado = Event()
    finalizar = Event()
    rutas = []

    def identificar(ruta):
        archivo = Path(ruta)
        rutas.append(archivo)

        iniciado.set()

        if not finalizar.wait(timeout=5):
            raise RuntimeError("No se ha liberado el worker.")

        assert archivo.exists()
        assert archivo.read_bytes() == b"imagen adaptada"

        return {
            "estado": "allowed",
            "descripcion": "Una botella de plástico.",
        }

    modelo = Mock(side_effect=identificar)

    monkeypatch.setattr("api.service.identificar_imagen", modelo)

    with ThreadPoolExecutor(max_workers=1) as executor:
        futuro = executor.submit(
            identificar_entrada_visual,
            b"imagen adaptada",
            "PNG",
        )

        try:
            assert iniciado.wait(timeout=5)

            with pytest.raises(TimeoutError):
                futuro.result(timeout=0)

            assert not futuro.done()
            assert rutas[0].exists()

        finally:
            finalizar.set()

        resultado = futuro.result(timeout=5)

    assert resultado["estado"] == "allowed"
    assert not rutas[0].exists()

    modelo.assert_called_once()


# =========================================================
# CONTROL DE ADMISIÓN Y CONCURRENCIA
# =========================================================


def test_exclusion_concurrente_por_hilo():
    """Rechaza operaciones simultáneas sobre una conversación."""
    admision = ControlAdmision(max_workers=1)
    thread_id = uuid4()

    def reservar():
        with admision.reservar_hilo(thread_id):
            pytest.fail("No debe adquirirse un hilo ocupado.")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with admision.reservar_hilo(thread_id):
            futuro = executor.submit(reservar)

            with pytest.raises(ApiError) as error:
                futuro.result(timeout=5)

            assert error.value.code == ErrorCode.THREAD_BUSY

    with admision.reservar_hilo(thread_id):
        pass


def test_reservas_de_hilos_independientes():
    """Permite reservar conversaciones diferentes."""
    admision = ControlAdmision(max_workers=1)

    primero = uuid4()
    segundo = uuid4()

    with admision.reservar_hilo(primero):
        with admision.reservar_hilo(segundo):
            pass


def test_capacidad_global_no_bloqueante():
    """Rechaza nuevas ejecuciones cuando no existe capacidad."""
    admision = ControlAdmision(max_workers=1)

    def reservar():
        with admision.reservar_capacidad():
            pytest.fail("No debe adquirirse capacidad ocupada.")

    with ThreadPoolExecutor(max_workers=1) as executor:
        with admision.reservar_capacidad():
            futuro = executor.submit(reservar)

            with pytest.raises(ApiError) as error:
                futuro.result(timeout=5)

            assert error.value.code == ErrorCode.SERVER_BUSY

    with admision.reservar_capacidad():
        pass


def test_liberacion_de_recursos_tras_excepcion():
    """Recupera hilo y capacidad aunque falle la operación."""
    admision = ControlAdmision(max_workers=1)
    thread_id = uuid4()

    with pytest.raises(RuntimeError, match="Fallo simulado"):
        with admision.reservar_hilo(thread_id):
            with admision.reservar_capacidad():
                raise RuntimeError("Fallo simulado")

    with admision.reservar_hilo(thread_id):
        with admision.reservar_capacidad():
            pass


def test_capacidad_agotada_no_retiene_otro_hilo():
    """Libera el hilo cuando no puede admitirse su ejecución."""
    admision = ControlAdmision(max_workers=1)
    thread_id = uuid4()

    with admision.reservar_capacidad():
        with pytest.raises(ApiError) as error:
            with admision.reservar_hilo(thread_id):
                with admision.reservar_capacidad():
                    pytest.fail("No existe capacidad disponible.")

        assert error.value.code == ErrorCode.SERVER_BUSY

        with admision.reservar_hilo(thread_id):
            pass


def test_transferencia_de_recursos_entre_hilos():
    """Permite conservar recursos hasta la finalización real."""
    admision = ControlAdmision(max_workers=1)
    thread_id = uuid4()

    with ExitStack() as recursos:
        recursos.enter_context(admision.reservar_hilo(thread_id))
        recursos.enter_context(admision.reservar_capacidad())

        retenidos = recursos.pop_all()

    try:
        with pytest.raises(ApiError) as error:
            with admision.reservar_hilo(thread_id):
                pytest.fail("El hilo debe permanecer reservado.")

        assert error.value.code == ErrorCode.THREAD_BUSY

        with pytest.raises(ApiError) as error:
            with admision.reservar_capacidad():
                pytest.fail("La capacidad debe seguir reservada.")

        assert error.value.code == ErrorCode.SERVER_BUSY

        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(retenidos.close).result(timeout=5)

    finally:
        retenidos.close()

    with admision.reservar_hilo(thread_id):
        with admision.reservar_capacidad():
            pass


# =========================================================
# EXECUTOR Y PRESUPUESTO TEMPORAL
# =========================================================


@pytest.fixture
def recursos_ejecucion():
    """Proporciona un executor y sus controles independientes."""
    settings = ApiSettings(ASK_TIMEOUT_SECONDS=5.0)

    admision = ControlAdmision(settings.AGENT_MAX_WORKERS)
    limitador = crear_limitador(settings)

    ejecutor = EjecutorAsistente(settings, admision, limitador)

    try:
        yield ejecutor, admision, limitador

    finally:
        ejecutor.cerrar()


@pytest.fixture
def contexto_free():
    """Proporciona una identidad Free ficticia."""
    return AuthContext(user_id=None, api_key_id=uuid4(), role=ApiKeyRole.FREE)


def test_presupuesto_temporal():
    """Calcula el tiempo restante desde un plazo absoluto."""
    instantes = iter([100.0, 115.0, 160.0, 161.0])

    presupuesto = PresupuestoEjecucion(
        60.0,
        reloj=lambda: next(instantes),
    )

    assert presupuesto.deadline == 160.0
    assert presupuesto.restante() == 45.0
    assert presupuesto.restante() == 0.0

    presupuesto.finalizar()

    assert presupuesto.finalizo_a_tiempo() is False


def test_executor_resultado_valido(
    recursos_ejecucion,
    contexto_free,
):
    """Devuelve el resultado y conserva la reserva del hilo."""
    ejecutor, admision, _ = recursos_ejecucion
    thread_id = uuid4()

    with ExitStack() as recursos:
        recursos.enter_context(admision.reservar_hilo(thread_id))

        resultado = ejecutor.ejecutar(
            lambda presupuesto: "resultado válido",
            recursos,
            thread_id=thread_id,
            contexto_cuota=contexto_free,
        )

        assert resultado == "resultado válido"

        with pytest.raises(ApiError) as error:
            with admision.reservar_hilo(thread_id):
                pytest.fail("El hilo debe seguir reservado.")

        assert error.value.code == ErrorCode.THREAD_BUSY

    with admision.reservar_hilo(thread_id):
        with admision.reservar_capacidad():
            pass


def test_executor_sin_capacidad_no_consume_cuota(
    recursos_ejecucion,
    contexto_free,
):
    """Rechaza la ejecución antes de contabilizar la cuota."""
    ejecutor, admision, limitador = recursos_ejecucion
    thread_id = uuid4()
    tarea = Mock()

    with admision.reservar_capacidad():
        with pytest.raises(ApiError) as error:
            with ExitStack() as recursos:
                recursos.enter_context(
                    admision.reservar_hilo(thread_id)
                )

                ejecutor.ejecutar(
                    tarea,
                    recursos,
                    thread_id=thread_id,
                    contexto_cuota=contexto_free,
                )

        assert error.value.code == ErrorCode.SERVER_BUSY

    tarea.assert_not_called()

    reservar_cuota_comercial(limitador, contexto_free)
    reservar_cuota_comercial(limitador, contexto_free)

    with pytest.raises(ApiError):
        reservar_cuota_comercial(limitador, contexto_free)


def test_executor_fallo_submit_revierte_cuota(
    recursos_ejecucion,
    contexto_free,
    monkeypatch,
):
    """Revierte únicamente la cuota de una tarea no admitida."""
    ejecutor, admision, limitador = recursos_ejecucion
    thread_id = uuid4()

    reservar_cuota_comercial(limitador, contexto_free)

    monkeypatch.setattr(
        ejecutor._executor,
        "submit",
        Mock(side_effect=RuntimeError("Fallo de admisión")),
    )

    with pytest.raises(RuntimeError, match="Fallo de admisión"):
        with ExitStack() as recursos:
            recursos.enter_context(
                admision.reservar_hilo(thread_id)
            )

            ejecutor.ejecutar(
                lambda presupuesto: None,
                recursos,
                thread_id=thread_id,
                contexto_cuota=contexto_free,
            )

    reservar_cuota_comercial(limitador, contexto_free)

    with pytest.raises(ApiError):
        reservar_cuota_comercial(limitador, contexto_free)

    with admision.reservar_hilo(thread_id):
        with admision.reservar_capacidad():
            pass


def test_executor_error_interno_no_revierte_cuota(
    recursos_ejecucion,
    contexto_free,
):
    """Conserva el consumo de una tarea admitida que falla."""
    ejecutor, admision, limitador = recursos_ejecucion
    thread_id = uuid4()

    def tarea(presupuesto):
        raise RuntimeError("Fallo de ejecución")

    with pytest.raises(RuntimeError, match="Fallo de ejecución"):
        with ExitStack() as recursos:
            recursos.enter_context(
                admision.reservar_hilo(thread_id)
            )

            ejecutor.ejecutar(
                tarea,
                recursos,
                thread_id=thread_id,
                contexto_cuota=contexto_free,
            )

    reservar_cuota_comercial(limitador, contexto_free)

    with pytest.raises(ApiError):
        reservar_cuota_comercial(limitador, contexto_free)

    with admision.reservar_capacidad():
        pass


def test_executor_timeout_interno_de_tarea(
    recursos_ejecucion,
):
    """No confunde una excepción interna con el plazo agotado."""
    ejecutor, admision, _ = recursos_ejecucion
    thread_id = uuid4()

    def tarea(presupuesto):
        raise TimeoutError("Timeout de dependencia externa")

    with pytest.raises(
        TimeoutError,
        match="Timeout de dependencia externa",
    ):
        with ExitStack() as recursos:
            recursos.enter_context(
                admision.reservar_hilo(thread_id)
            )

            ejecutor.ejecutar(
                tarea,
                recursos,
                thread_id=thread_id,
                contexto_cuota=None,
            )


def test_executor_aprobacion_sin_cuota(
    recursos_ejecucion,
    contexto_free,
):
    """Permite resolver HITL sin registrar otra cuota."""
    ejecutor, admision, limitador = recursos_ejecucion
    thread_id = uuid4()

    reservar_cuota_comercial(limitador, contexto_free)
    reservar_cuota_comercial(limitador, contexto_free)

    with ExitStack() as recursos:
        recursos.enter_context(
            admision.reservar_hilo(thread_id)
        )

        resultado = ejecutor.ejecutar(
            lambda presupuesto: "aprobado",
            recursos,
            thread_id=thread_id,
            contexto_cuota=None,
        )

    assert resultado == "aprobado"


def test_executor_timeout_retiene_recursos(contexto_free):
    """Mantiene las reservas mientras siga activo el worker."""
    settings = ApiSettings(ASK_TIMEOUT_SECONDS=1.0)

    admision = ControlAdmision(settings.AGENT_MAX_WORKERS)
    limitador = crear_limitador(settings)

    ejecutor = EjecutorAsistente(
        settings,
        admision,
        limitador,
    )

    thread_id = uuid4()
    iniciado = Event()
    liberar = Event()

    def tarea(presupuesto):
        iniciado.set()

        if not liberar.wait(timeout=10):
            raise RuntimeError("Espera de prueba agotada")

        return "resultado tardío"

    try:
        with pytest.raises(ApiError) as error:
            with ExitStack() as recursos:
                recursos.enter_context(
                    admision.reservar_hilo(thread_id)
                )

                ejecutor.ejecutar(
                    tarea,
                    recursos,
                    thread_id=thread_id,
                    contexto_cuota=contexto_free,
                )

        assert error.value.code == ErrorCode.AGENT_TIMEOUT
        assert iniciado.is_set()

        with pytest.raises(ApiError) as error:
            with admision.reservar_hilo(thread_id):
                pytest.fail("El hilo debe seguir ocupado.")

        assert error.value.code == ErrorCode.THREAD_BUSY

        with pytest.raises(ApiError) as error:
            with admision.reservar_capacidad():
                pytest.fail("El worker debe seguir reservado.")

        assert error.value.code == ErrorCode.SERVER_BUSY

        reservar_cuota_comercial(limitador, contexto_free)

        with pytest.raises(ApiError):
            reservar_cuota_comercial(limitador, contexto_free)

    finally:
        liberar.set()
        ejecutor.cerrar()

    with admision.reservar_hilo(thread_id):
        with admision.reservar_capacidad():
            pass


@pytest.mark.parametrize("invalidacion_explicita", [False, True])
def test_presupuesto_impide_nuevas_fases(invalidacion_explicita):
    """Impide iniciar fases cuando la ejecución pierde vigencia."""
    ahora = 0.0

    presupuesto = PresupuestoEjecucion(60.0, reloj=lambda: ahora)

    presupuesto.comprobar_vigencia()

    if invalidacion_explicita:
        presupuesto.invalidar()
    else:
        ahora = 60.0

    with pytest.raises(ApiError) as error:
        presupuesto.comprobar_vigencia(modifica_checkpoint=True)

    assert error.value.code == ErrorCode.AGENT_TIMEOUT
    assert presupuesto.invalidar() is False


def test_presupuesto_registra_exposicion_checkpoint():
    """Conserva la exposición del checkpoint tras invalidarse."""
    presupuesto = PresupuestoEjecucion(60.0, reloj=lambda: 0.0)

    presupuesto.comprobar_vigencia(modifica_checkpoint=True)

    assert presupuesto.invalidar() is True
    assert presupuesto.invalidar() is True


def test_hilo_invalidado_permanece_ocupado():
    """Prioriza la ocupación hasta finalizar la ejecución."""
    admision = ControlAdmision(max_workers=1)
    thread_id = uuid4()

    with admision.reservar_hilo(thread_id):
        admision.invalidar_hilo(thread_id)

        with pytest.raises(ApiError) as error:
            with admision.reservar_hilo(thread_id):
                pytest.fail("No debe reservarse el hilo.")

        assert error.value.code == ErrorCode.THREAD_BUSY

    with pytest.raises(ApiError) as error:
        with admision.reservar_hilo(thread_id):
            pytest.fail("No debe reutilizarse el hilo.")

    assert error.value.code == ErrorCode.THREAD_STATE_LOST

    with admision.reservar_hilo(uuid4()):
        pass

@pytest.mark.parametrize("checkpoint_expuesto", [False, True])
def test_timeout_impide_iniciar_siguiente_fase(
    monkeypatch,
    checkpoint_expuesto,
    eventos_tecnicos,
):
    """Impide nuevas fases tras un timeout declarado."""
    ahora = 0.0

    settings = ApiSettings(ASK_TIMEOUT_SECONDS=60.0)
    admision = ControlAdmision(settings.AGENT_MAX_WORKERS)
    limitador = crear_limitador(settings)

    ejecutor = EjecutorAsistente(
        settings,
        admision,
        limitador,
        reloj=lambda: ahora,
    )

    thread_id = uuid4()
    iniciado = Event()
    liberar = Event()
    siguiente_fase = Mock()
    errores_worker = []

    def tarea(presupuesto):
        presupuesto.comprobar_vigencia(
            modifica_checkpoint=checkpoint_expuesto,
        )

        iniciado.set()

        if not liberar.wait(timeout=10):
            raise RuntimeError("Espera de prueba agotada")

        try:
            presupuesto.comprobar_vigencia(
                modifica_checkpoint=True,
            )

        except ApiError as exc:
            errores_worker.append(exc.code)
            raise

        siguiente_fase()

    def simular_timeout(futuros, *, timeout):
        nonlocal ahora

        assert iniciado.wait(timeout=5)

        ahora = 60.0

        return set(), set(futuros)

    monkeypatch.setattr(servicio, "wait", simular_timeout)

    try:
        with pytest.raises(ApiError) as error:
            with ExitStack() as recursos:
                recursos.enter_context(
                    admision.reservar_hilo(thread_id)
                )

                ejecutor.ejecutar(
                    tarea,
                    recursos,
                    thread_id=thread_id,
                    contexto_cuota=None,
                )

        assert error.value.code == ErrorCode.AGENT_TIMEOUT

        with pytest.raises(ApiError) as error:
            with admision.reservar_hilo(thread_id):
                pytest.fail("El worker continúa activo.")

        assert error.value.code == ErrorCode.THREAD_BUSY

        siguiente_fase.assert_not_called()

    finally:
        liberar.set()
        ejecutor.cerrar()

    siguiente_fase.assert_not_called()

    assert errores_worker == [ErrorCode.AGENT_TIMEOUT]

    if checkpoint_expuesto:
        with pytest.raises(ApiError) as error:
            with admision.reservar_hilo(thread_id):
                pytest.fail("El checkpoint está comprometido.")

        assert error.value.code == ErrorCode.THREAD_STATE_LOST

    else:
        with admision.reservar_hilo(thread_id):
            pass

    with admision.reservar_capacidad():
        pass

        request_id, caplog = eventos_tecnicos

    eventos = obtener_eventos(caplog)
    nombres = [evento["event"] for evento in eventos]

    assert nombres.count("execution_timeout") == 1
    assert nombres.count("execution_discarded") == 1

    assert nombres.count("checkpoint_invalidated") == int(checkpoint_expuesto)

    assert all(
        evento["request_id"] == request_id
        for evento in eventos
    )

    descartado = next(
        evento for evento in eventos
        if evento["event"] == "execution_discarded"
    )

    assert descartado["thread_id"] == str(thread_id)
    assert descartado["duration_ms"] == 60000.0


@pytest.mark.parametrize("instante_final", [60.0, 61.0])
def test_executor_descarta_future_finalizado_tarde(
    monkeypatch,
    instante_final,
):
    """Rechaza resultados finalizados fuera del presupuesto."""
    ahora = 0.0

    settings = ApiSettings(ASK_TIMEOUT_SECONDS=60.0)
    admision = ControlAdmision(settings.AGENT_MAX_WORKERS)
    limitador = crear_limitador(settings)

    ejecutor = EjecutorAsistente(
        settings,
        admision,
        limitador,
        reloj=lambda: ahora,
    )

    thread_id = uuid4()

    def tarea(presupuesto):
        nonlocal ahora

        presupuesto.comprobar_vigencia(
            modifica_checkpoint=True,
        )

        ahora = instante_final

        return "resultado tardío"

    def esperar_finalizacion(futuros, *, timeout):
        futuro = next(iter(futuros))

        assert futuro.result(timeout=5) == "resultado tardío"

        return {futuro}, set()

    monkeypatch.setattr(servicio, "wait", esperar_finalizacion)

    try:
        with pytest.raises(ApiError) as error:
            with ExitStack() as recursos:
                recursos.enter_context(
                    admision.reservar_hilo(thread_id)
                )

                ejecutor.ejecutar(
                    tarea,
                    recursos,
                    thread_id=thread_id,
                    contexto_cuota=None,
                )

        assert error.value.code == ErrorCode.AGENT_TIMEOUT

    finally:
        ejecutor.cerrar()

    with pytest.raises(ApiError) as error:
        with admision.reservar_hilo(thread_id):
            pytest.fail("El hilo debe estar invalidado.")

    assert error.value.code == ErrorCode.THREAD_STATE_LOST

    with admision.reservar_capacidad():
        pass


def test_executor_error_invalida_checkpoint_expuesto(
    recursos_ejecucion,
):
    """Invalida el hilo si una operación sobre el grafo falla."""
    ejecutor, admision, _ = recursos_ejecucion
    thread_id = uuid4()

    def tarea(presupuesto):
        presupuesto.comprobar_vigencia(
            modifica_checkpoint=True,
        )

        raise RuntimeError("Fallo de LangGraph")

    with pytest.raises(RuntimeError, match="Fallo de LangGraph"):
        with ExitStack() as recursos:
            recursos.enter_context(
                admision.reservar_hilo(thread_id)
            )

            ejecutor.ejecutar(
                tarea,
                recursos,
                thread_id=thread_id,
                contexto_cuota=None,
            )

    with pytest.raises(ApiError) as error:
        with admision.reservar_hilo(thread_id):
            pytest.fail("El hilo debe estar invalidado.")

    assert error.value.code == ErrorCode.THREAD_STATE_LOST

    with admision.reservar_capacidad():
        pass


# =========================================================
# OBSERVABILIDAD DE EJECUCIONES
# =========================================================


@pytest.fixture
def eventos_tecnicos(caplog, monkeypatch):
    """Captura eventos asociados a una petición ficticia."""
    request_id = str(uuid4())

    monkeypatch.setattr(EVENT_LOGGER, "propagate", False)
    monkeypatch.setattr(EVENT_LOGGER, "handlers", [caplog.handler])

    caplog.set_level(logging.INFO, logger=EVENT_LOGGER.name)

    token = request_id_context.set(request_id)

    try:
        yield request_id, caplog

    finally:
        request_id_context.reset(token)


def obtener_eventos(caplog):
    """Recupera exclusivamente los eventos técnicos propios."""
    return [
        json.loads(registro.getMessage())
        for registro in caplog.records
        if registro.name == EVENT_LOGGER.name
    ]

def test_executor_propaga_request_id(
    recursos_ejecucion,
    eventos_tecnicos,
):
    """Correlaciona los eventos del coordinador y del worker."""
    ejecutor, admision, _ = recursos_ejecucion
    request_id, caplog = eventos_tecnicos
    thread_id = uuid4()

    def tarea(presupuesto):
        registrar_evento("test_worker")
        return "resultado válido"

    with ExitStack() as recursos:
        recursos.enter_context(
            admision.reservar_hilo(thread_id)
        )

        resultado = ejecutor.ejecutar(
            tarea,
            recursos,
            thread_id=thread_id,
            contexto_cuota=None,
        )

    assert resultado == "resultado válido"

    eventos = obtener_eventos(caplog)

    assert {evento["event"] for evento in eventos} == {
        "execution_admitted",
        "test_worker",
        "execution_completed",
    }

    assert all(
        evento["request_id"] == request_id
        for evento in eventos
    )

    finalizado = next(
        evento for evento in eventos
        if evento["event"] == "execution_completed"
    )

    assert finalizado["thread_id"] == str(thread_id)
    assert finalizado["duration_ms"] >= 0


def test_rate_limit_no_registra_identidad(
    recursos_ejecucion,
    contexto_free,
    eventos_tecnicos,
):
    """Registra el ámbito agotado sin revelar la identidad."""
    _, _, limitador = recursos_ejecucion
    request_id, caplog = eventos_tecnicos

    reservar_cuota_comercial(limitador, contexto_free)
    reservar_cuota_comercial(limitador, contexto_free)

    with pytest.raises(ApiError) as error:
        reservar_cuota_comercial(limitador, contexto_free)

    assert error.value.code == ErrorCode.RATE_LIMIT_EXCEEDED

    eventos = obtener_eventos(caplog)

    assert len(eventos) == 1

    evento = eventos[0]

    assert evento["request_id"] == request_id
    assert evento["event"] == "rate_limit_exceeded"
    assert evento["scopes"] == ["commercial_free"]
    assert evento["retry_after"] > 0
    assert evento["level"] == "WARNING"

    assert str(contexto_free.api_key_id) not in caplog.text


def test_executor_no_registra_excepcion_completa(
    recursos_ejecucion,
    eventos_tecnicos,
):
    """Registra el fallo sin revelar el contenido de la excepción."""
    ejecutor, admision, _ = recursos_ejecucion
    request_id, caplog = eventos_tecnicos
    thread_id = uuid4()
    secreto = "credencial-ficticia-no-registrable"

    def tarea(presupuesto):
        raise RuntimeError(secreto)

    with pytest.raises(RuntimeError):
        with ExitStack() as recursos:
            recursos.enter_context(
                admision.reservar_hilo(thread_id)
            )

            ejecutor.ejecutar(
                tarea,
                recursos,
                thread_id=thread_id,
                contexto_cuota=None,
            )

    eventos = obtener_eventos(caplog)

    fallo = next(
        evento for evento in eventos
        if evento["event"] == "execution_failed"
    )

    assert fallo["request_id"] == request_id
    assert fallo["thread_id"] == str(thread_id)
    assert fallo["level"] == "ERROR"
    assert fallo["duration_ms"] >= 0

    assert secreto not in caplog.text