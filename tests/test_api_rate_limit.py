"""Pruebas de ventanas deslizantes y atomicidad de consumos."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from uuid import uuid4

from api.config import ApiSettings
from api.request_context import AuthContext
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.rate_limit import (
    DAY,
    HALF_HOUR,
    HOUR,
    MINUTE,
    SlidingWindowLog,
    crear_limitador,
    limitar_http,
    limitar_login,
    limitar_registro,
    limitar_emision_anonima,
    limitar_emision_registrada,
    reservar_cuota_comercial,
)
from src.enums import ApiKeyRole


class RelojFalso:
    """Permite controlar el tiempo sin esperas reales."""

    def __init__(self) -> None:
        """Inicializa el instante de prueba."""
        self.ahora = 0.0

    def __call__(self) -> float:
        """Devuelve el instante simulado."""
        return self.ahora

    def avanzar(self, segundos: float) -> None:
        """Avanza el tiempo simulado."""
        self.ahora += segundos


@pytest.fixture
def reloj():
    """Proporciona un reloj independiente para cada prueba."""
    return RelojFalso()


def test_limite_por_minuto(reloj):
    """Admite dos operaciones y rechaza la tercera."""
    limitador = SlidingWindowLog({"free": ((MINUTE, 2),)}, reloj=reloj)

    clave = ("free", "usuario-1")

    limitador.consumir(clave)
    limitador.consumir(clave)

    with pytest.raises(ApiError) as error:
        limitador.consumir(clave)

    assert error.value.code == ErrorCode.RATE_LIMIT_EXCEEDED
    assert error.value.retry_after == MINUTE


def test_expiracion_exacta(reloj):
    """Un registro caduca al alcanzar la duración de la ventana."""
    limitador = SlidingWindowLog({"http": ((MINUTE, 1),)}, reloj=reloj)

    clave = ("http", "clave-1")

    limitador.consumir(clave)

    reloj.avanzar(59.5)

    with pytest.raises(ApiError) as error:
        limitador.consumir(clave)

    assert error.value.retry_after == 1

    reloj.avanzar(0.5)

    limitador.consumir(clave)


def test_identidades_independientes(reloj):
    """El consumo de una identidad no afecta a otra."""
    limitador = SlidingWindowLog({"http": ((MINUTE, 1),)}, reloj=reloj)

    limitador.consumir(("http", "clave-1"))
    limitador.consumir(("http", "clave-2"))

    with pytest.raises(ApiError):
        limitador.consumir(("http", "clave-1"))


def test_ambitos_independientes(reloj):
    """Una misma identidad puede tener consumos independientes."""
    limitador = SlidingWindowLog(
        {
            "http": ((MINUTE, 1),),
            "commercial": ((MINUTE, 1),),
        },
        reloj=reloj,
    )

    limitador.consumir(("http", "clave-1"))
    limitador.consumir(("commercial", "clave-1"))


def test_retry_after_mayor_entre_ventanas(reloj):
    """Selecciona la espera más larga de los límites agotados."""
    limitador = SlidingWindowLog(
        {
            "free": ((MINUTE, 1), (HOUR, 1), (DAY, 1)),
        },
        reloj=reloj,
    )

    clave = ("free", "clave-1")

    limitador.consumir(clave)

    with pytest.raises(ApiError) as error:
        limitador.consumir(clave)

    assert error.value.retry_after == DAY


def test_rechazo_no_registra_consumo(reloj):
    """Los rechazos no prolongan la restricción temporal."""
    limitador = SlidingWindowLog({"http": ((MINUTE, 1),)}, reloj=reloj)

    clave = ("http", "clave-1")

    limitador.consumir(clave)

    reloj.avanzar(30)

    with pytest.raises(ApiError):
        limitador.consumir(clave)

    reloj.avanzar(30)

    limitador.consumir(clave)


def test_admision_atomica_entre_identidades(reloj):
    """No consume parcialmente una operación con varios controles."""
    limitador = SlidingWindowLog(
        {
            "login_email": ((HOUR, 1),),
            "login_origin": ((HALF_HOUR, 1),),
        },
        reloj=reloj,
    )

    email = ("login_email", "usuario@example.com")
    origen = ("login_origin", "192.0.2.10")

    limitador.consumir(email)

    with pytest.raises(ApiError):
        limitador.consumir(email, origen)

    # El rechazo por email no debe haber consumido el origen.
    limitador.consumir(origen)


def test_limpieza_de_identidades_caducadas(reloj):
    """Elimina identidades aunque no vuelvan a realizar consultas."""
    limitador = SlidingWindowLog({"http": ((MINUTE, 1),)}, reloj=reloj)

    antigua = ("http", "clave-antigua")
    nueva = ("http", "clave-nueva")

    limitador.consumir(antigua)

    reloj.avanzar(MINUTE)

    limitador.consumir(nueva)

    assert antigua not in limitador._registros
    assert nueva in limitador._registros


def test_reversion_de_registro_concreto(reloj):
    """Revierte únicamente el consumo indicado."""
    limitador = SlidingWindowLog({"commercial": ((MINUTE, 2),)}, reloj=reloj)

    clave = ("commercial", "clave-1")

    primero = limitador.consumir(clave)
    segundo = limitador.consumir(clave)

    assert limitador.revertir(clave, primero) is True
    assert limitador.revertir(clave, primero) is False

    assert list(limitador._registros[clave]) == [segundo]

    limitador.consumir(clave)

    with pytest.raises(ApiError):
        limitador.consumir(clave)


def test_consumo_concurrente_atomico(reloj):
    """Impide superar el límite mediante peticiones simultáneas."""
    limitador = SlidingWindowLog({"http": ((MINUTE, 5),)}, reloj=reloj)

    clave = ("http", "clave-1")
    trabajadores = 12

    barrera = Barrier(trabajadores)

    def consumir():
        barrera.wait(timeout=5)

        try:
            limitador.consumir(clave)

        except ApiError as exc:
            assert exc.code == ErrorCode.RATE_LIMIT_EXCEEDED
            return False

        return True

    with ThreadPoolExecutor(max_workers=trabajadores) as executor:
        futuros = [executor.submit(consumir) for _ in range(trabajadores)]

        resultados = [futuro.result(timeout=5) for futuro in futuros]

    assert resultados.count(True) == 5
    assert resultados.count(False) == 7


# =========================================================
# POLÍTICAS DE CONSUMO
# =========================================================


@pytest.mark.parametrize("role", list(ApiKeyRole))
def test_limite_http_por_rol(reloj, role):
    """Aplica el límite HTTP a todos los roles."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    contexto = AuthContext(user_id=uuid4(), api_key_id=uuid4(), role=role)

    for _ in range(30):
        limitar_http(limitador, contexto)

    with pytest.raises(ApiError) as error:
        limitar_http(limitador, contexto)

    assert error.value.code == ErrorCode.RATE_LIMIT_EXCEEDED
    assert error.value.retry_after == MINUTE


def test_limite_http_cuenta_independiente(reloj):
    """Separa el consumo de cuenta del consumo de una API key."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    identidad = uuid4()

    cuenta = AuthContext(user_id=identidad, api_key_id=None, role=None)

    clave = AuthContext(
        user_id=identidad,
        api_key_id=identidad,
        role=ApiKeyRole.USER,
    )

    for _ in range(30):
        limitar_http(limitador, cuenta)

    with pytest.raises(ApiError):
        limitar_http(limitador, cuenta)

    limitar_http(limitador, clave)


@pytest.mark.parametrize(
    "role, limite",
    [(ApiKeyRole.FREE, 2), (ApiKeyRole.USER, 5)],
)
def test_cuota_comercial_por_rol(reloj, role, limite):
    """Aplica las cuotas comerciales sin afectar al límite HTTP."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    contexto = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=role,
    )

    for _ in range(limite):
        assert reservar_cuota_comercial(
            limitador,
            contexto,
        ) is not None

    with pytest.raises(ApiError) as error:
        reservar_cuota_comercial(limitador, contexto)

    assert error.value.code == ErrorCode.RATE_LIMIT_EXCEEDED

    limitar_http(limitador, contexto)


def test_admin_sin_cuota_comercial(reloj):
    """Excluye a Admin únicamente del consumo comercial."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    contexto = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=ApiKeyRole.ADMIN,
    )

    for _ in range(100):
        assert reservar_cuota_comercial(
            limitador,
            contexto,
        ) is None

    assert not limitador._registros


def test_reversion_cuota_comercial(reloj):
    """Recupera capacidad cuando falla la admisión al executor."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    contexto = AuthContext(
        user_id=None,
        api_key_id=uuid4(),
        role=ApiKeyRole.FREE,
    )

    reserva = reservar_cuota_comercial(limitador, contexto)
    reservar_cuota_comercial(limitador, contexto)

    assert reserva is not None

    with pytest.raises(ApiError):
        reservar_cuota_comercial(limitador, contexto)

    assert limitador.revertir(*reserva) is True

    reservar_cuota_comercial(limitador, contexto)

    with pytest.raises(ApiError):
        reservar_cuota_comercial(limitador, contexto)


def test_login_limite_por_email(reloj):
    """Limita un email aunque los intentos cambien de origen."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    email = "usuario@example.com"

    for i in range(5):
        limitar_login(limitador, email, f"192.0.2.{i + 1}")

    with pytest.raises(ApiError) as error:
        limitar_login(limitador, email, "192.0.2.20")

    assert error.value.retry_after == HOUR

    reloj.avanzar(HOUR)

    limitar_login(limitador, email, "192.0.2.20")


def test_login_limite_por_origen(reloj):
    """Limita los intentos dirigidos a cuentas diferentes."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    origen = "192.0.2.1"

    for i in range(20):
        limitar_login(limitador, f"usuario{i}@example.com", origen)

    with pytest.raises(ApiError) as error:
        limitar_login(limitador, "otro@example.com", origen)

    assert error.value.retry_after == HALF_HOUR

    reloj.avanzar(HALF_HOUR)

    limitar_login(limitador, "otro@example.com", origen)


def test_registro_por_origen(reloj):
    """Limita el registro sin interferir con otros controles."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    origen = "192.0.2.1"

    for _ in range(5):
        limitar_registro(limitador, origen)

    with pytest.raises(ApiError) as error:
        limitar_registro(limitador, origen)

    assert error.value.retry_after == HOUR

    limitar_emision_anonima(limitador, origen)


@pytest.mark.parametrize("registrada", [False, True])
def test_limites_emision(reloj, registrada):
    """Aplica simultáneamente los límites horario y diario."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)
    user_id = uuid4()

    def emitir():
        if registrada:
            limitar_emision_registrada(limitador, user_id)
        else:
            limitar_emision_anonima(limitador, "192.0.2.1")

    for _ in range(3):
        emitir()

    with pytest.raises(ApiError) as error:
        emitir()

    assert error.value.retry_after == HOUR

    reloj.avanzar(HOUR)

    emitir()
    emitir()

    with pytest.raises(ApiError) as error:
        emitir()

    assert error.value.retry_after == DAY - HOUR


@pytest.mark.parametrize(
    "role, limite_minuto, limite_hora",
    [
        (ApiKeyRole.FREE, 2, 10),
        (ApiKeyRole.USER, 5, 20),
    ],
)
def test_cuota_comercial_horaria(
    reloj,
    role,
    limite_minuto,
    limite_hora,
):
    """Agota la cuota horaria sin agotar la ventana por minuto."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    contexto = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=role,
    )

    for _ in range(limite_hora // limite_minuto):
        for _ in range(limite_minuto):
            reservar_cuota_comercial(limitador, contexto)

        reloj.avanzar(MINUTE)

    with pytest.raises(ApiError) as error:
        reservar_cuota_comercial(limitador, contexto)

    assert error.value.code == ErrorCode.RATE_LIMIT_EXCEEDED
    assert error.value.retry_after == HOUR - reloj.ahora

    reloj.avanzar(HOUR - reloj.ahora)

    for _ in range(limite_minuto):
        reservar_cuota_comercial(limitador, contexto)

    with pytest.raises(ApiError):
        reservar_cuota_comercial(limitador, contexto)


@pytest.mark.parametrize(
    "role, limite_minuto, limite_hora, limite_dia",
    [
        (ApiKeyRole.FREE, 2, 10, 30),
        (ApiKeyRole.USER, 5, 20, 45),
    ],
)
def test_cuota_comercial_diaria(
    reloj,
    role,
    limite_minuto,
    limite_hora,
    limite_dia,
):
    """Agota la cuota diaria respetando las ventanas menores."""
    limitador = crear_limitador(ApiSettings(), reloj=reloj)

    contexto = AuthContext(
        user_id=uuid4(),
        api_key_id=uuid4(),
        role=role,
    )

    for inicio in range(0, limite_dia, limite_hora):
        cantidad = min(limite_hora, limite_dia - inicio)
        lotes = cantidad // limite_minuto

        for _ in range(lotes):
            for _ in range(limite_minuto):
                reservar_cuota_comercial(limitador, contexto)

            reloj.avanzar(MINUTE)

        reloj.avanzar(HOUR - lotes * MINUTE)

    with pytest.raises(ApiError) as error:
        reservar_cuota_comercial(limitador, contexto)

    assert error.value.code == ErrorCode.RATE_LIMIT_EXCEEDED
    assert error.value.retry_after == DAY - reloj.ahora

    reloj.avanzar(DAY - reloj.ahora)

    for _ in range(limite_minuto):
        reservar_cuota_comercial(limitador, contexto)

    with pytest.raises(ApiError):
        reservar_cuota_comercial(limitador, contexto)


def test_limpieza_respeta_ventana_maxima(reloj):
    """Conserva cada registro mientras afecte a alguna ventana."""
    limitador = SlidingWindowLog(
        {
            "http": ((MINUTE, 1),),
            "commercial": (
                (MINUTE, 2),
                (HOUR, 10),
                (DAY, 30),
            ),
        },
        reloj=reloj,
    )

    http = ("http", "clave-1")
    comercial = ("commercial", "clave-1")
    nueva = ("http", "clave-2")

    limitador.consumir(http)
    limitador.consumir(comercial)

    reloj.avanzar(HOUR)

    limitador.consumir(nueva)

    assert http not in limitador._registros
    assert comercial in limitador._registros

    reloj.avanzar(DAY - HOUR)

    limitador.consumir(nueva)

    assert comercial not in limitador._registros