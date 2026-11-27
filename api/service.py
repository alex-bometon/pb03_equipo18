"""Coordina la admisión y ejecución del asistente desde la API."""


import time
from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor, wait
from contextlib import ExitStack, contextmanager
from typing import TypeVar
from threading import BoundedSemaphore, Lock
from uuid import UUID

from api.schemas import AskOut, UbicacionIn
from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.images import imagen_temporal
from src.state import IdentificacionImagen
from src.tools.describir_imagen import identificar_imagen
from src.domain import es_consulta_programacion, evaluar_ambito
from src.generation_validation import MENSAJE_ABSTENCION
from src.rag_intents import (
    MENSAJE_ACLARACION_CONTEXTO,
    MENSAJE_ACLARACION_HORARIO_MOVIL,
    MENSAJE_ACLARACION_PROXIMIDAD,
    consulta_proximidad,
    es_consulta_reparacion_telefonos,
    es_horario_movil_sin_ubicacion,
    requiere_antecedente,
)
from api.config import ApiSettings
from api.rate_limit import (
    SlidingWindowLog,
    reservar_cuota_comercial,
)
from api.request_context import AuthContext
from src.text_utils import normalizar_texto

T = TypeVar("T")

class ControlAdmision:
    """Controla la exclusión por hilo y la capacidad del asistente."""

    def __init__(self, max_workers: int) -> None:
        """Inicializa los recursos compartidos de admisión."""
        self._lock = Lock()
        self._hilos_ocupados: set[UUID] = set()
        self._hilos_invalidados: set[UUID] = set()
        self._capacidad = BoundedSemaphore(max_workers)

    @contextmanager
    def reservar_hilo(self, thread_id: UUID) -> Iterator[None]:
        """Reserva exclusivamente una conversación reutilizable."""
        with self._lock:
            if thread_id in self._hilos_ocupados:
                raise ApiError(ErrorCode.THREAD_BUSY)

            if thread_id in self._hilos_invalidados:
                raise ApiError(ErrorCode.THREAD_STATE_LOST)

            self._hilos_ocupados.add(thread_id)

        try:
            yield

        finally:
            with self._lock:
                self._hilos_ocupados.remove(thread_id)

    def invalidar_hilo(self, thread_id: UUID) -> None:
        """Impide reutilizar una conversación inconsistente."""
        with self._lock:
            self._hilos_invalidados.add(thread_id)

    @contextmanager
    def reservar_capacidad(self) -> Iterator[None]:
        """Reserva capacidad de ejecución sin acumular solicitudes."""
        if not self._capacidad.acquire(blocking=False):
            raise ApiError(ErrorCode.SERVER_BUSY)

        try:
            yield

        finally:
            self._capacidad.release()


class PresupuestoEjecucion:
    """Gestiona el plazo y la vigencia de una ejecución."""

    def __init__(
        self,
        timeout_seconds: float,
        *,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        """Establece el plazo absoluto de finalización."""
        self._reloj = reloj
        self.deadline = reloj() + timeout_seconds
        self._lock = Lock()
        self._invalidado = False
        self._checkpoint_expuesto = False
        self._finalizado_en: float | None = None

    def restante(self) -> float:
        """Devuelve el tiempo disponible hasta el plazo."""
        return max(0.0, self.deadline - self._reloj())

    def comprobar_vigencia(
        self,
        *,
        modifica_checkpoint: bool = False,
    ) -> None:
        """Autoriza una fase si la ejecución continúa vigente."""
        with self._lock:
            if (
                self._invalidado
                or self._reloj() >= self.deadline
            ):
                self._invalidado = True
                raise ApiError(ErrorCode.AGENT_TIMEOUT)

            if modifica_checkpoint:
                self._checkpoint_expuesto = True

    def invalidar(self) -> bool:
        """Invalida la ejecución e indica si expuso el checkpoint."""
        with self._lock:
            self._invalidado = True

            return self._checkpoint_expuesto

    def finalizar(self) -> None:
        """Registra el instante real de finalización."""
        with self._lock:
            self._finalizado_en = self._reloj()

    def finalizo_a_tiempo(self) -> bool:
        """Comprueba si la ejecución terminó dentro del plazo."""
        with self._lock:
            return (
                not self._invalidado
                and self._finalizado_en is not None
                and self._finalizado_en < self.deadline
            )
    

class EjecutorAsistente:
    """Coordina la ejecución costosa y su presupuesto temporal."""

    def __init__(
        self,
        settings: ApiSettings,
        admision: ControlAdmision,
        limitador: SlidingWindowLog,
        *,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        """Inicializa el executor compartido del backend."""
        self._admision = admision
        self._limitador = limitador
        self._timeout_seconds = settings.ASK_TIMEOUT_SECONDS
        self._reloj = reloj

        self._executor = ThreadPoolExecutor(
            max_workers=settings.AGENT_MAX_WORKERS,
        )

    def ejecutar(
        self,
        tarea: Callable[[PresupuestoEjecucion], T],
        recursos: ExitStack,
        *,
        thread_id: UUID,
        contexto_cuota: AuthContext | None,
    ) -> T:
        """Admite una tarea y devuelve su resultado dentro del plazo."""
        recursos.enter_context(self._admision.reservar_capacidad())

        reserva = None

        if contexto_cuota is not None:
            reserva = reservar_cuota_comercial(self._limitador, contexto_cuota)

        presupuesto = PresupuestoEjecucion(self._timeout_seconds, reloj=self._reloj)

        def ejecutar_tarea() -> T:
            """Registra la finalización real de la tarea."""
            try:
                presupuesto.comprobar_vigencia()

                return tarea(presupuesto)

            finally:
                presupuesto.finalizar()

        try:
            futuro = self._executor.submit(ejecutar_tarea)

        except BaseException:
            if reserva is not None:
                self._limitador.revertir(*reserva)

            raise

        try:
            terminados, _ = wait((futuro,), timeout=presupuesto.restante())

            if (futuro not in terminados or not presupuesto.finalizo_a_tiempo()):
                raise ApiError(ErrorCode.AGENT_TIMEOUT)

        except BaseException:
            if presupuesto.invalidar():
                self._admision.invalidar_hilo(thread_id)

            self._retener_recursos(futuro, recursos)
            raise

        try:
            return futuro.result()

        except BaseException:
            if presupuesto.invalidar():
                self._admision.invalidar_hilo(thread_id)

            raise

    @staticmethod
    def _retener_recursos(
        futuro: Future,
        recursos: ExitStack,
    ) -> None:
        """Conserva las reservas hasta que termine el worker."""
        retenidos = recursos.pop_all()

        futuro.add_done_callback(lambda _: retenidos.close())
        futuro.cancel()

    def cerrar(self) -> None:
        """Espera la finalización segura durante el apagado."""
        self._executor.shutdown(wait=True, cancel_futures=True)


def _respuesta_previa(
    respuesta: str,
    motivo: str,
    *,
    thread_id: str | None,
    turnos_consumidos: int,
) -> AskOut:
    """Construye una respuesta anterior a la ejecución del agente."""
    return AskOut(
        thread_id=thread_id,
        respuesta=respuesta,
        plan=[],
        plan_aprobado=None,
        done=False,
        pendiente_hitl=False,
        fuentes=[],
        geografia=[],
        abstencion=True,
        motivo=motivo,
        estado_evidencia="insuficiente",
        limitaciones=[],
        turnos_consumidos=turnos_consumidos,
        error=None,
        approval_id=None,
    )


def filtrar_entrada(
    pregunta: str,
    *,
    contexto_revision: str = "",
    ubicacion: UbicacionIn | None = None,
    hay_imagen: bool = False,
    thread_id: str | None = None,
    turnos_consumidos: int = 0,
) -> AskOut | None:
    """Resuelve consultas inequívocas antes de ejecutar el agente."""
    normalizada = normalizar_texto(pregunta)

    if requiere_antecedente(normalizada):
        if contexto_revision or hay_imagen:
            return None

        return _respuesta_previa(
            MENSAJE_ACLARACION_CONTEXTO,
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if (
        es_consulta_reparacion_telefonos(normalizada)
        or es_consulta_programacion(normalizada)
        or evaluar_ambito(normalizada) == "fuera_de_dominio"
    ):
        return _respuesta_previa(
            MENSAJE_ABSTENCION,
            "fuera_de_dominio",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if hay_imagen:
        return None

    if (
        not contexto_revision
        and es_horario_movil_sin_ubicacion(normalizada)
    ):
        return _respuesta_previa(
            MENSAJE_ACLARACION_HORARIO_MOVIL,
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if ubicacion is None and consulta_proximidad(normalizada, exclusiva=True):
        return _respuesta_previa(
            MENSAJE_ACLARACION_PROXIMIDAD,
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    return None


def identificar_entrada_visual(
    datos: bytes,
    formato: str,
    *,
    thread_id: str | None = None,
    turnos_consumidos: int = 0,
) -> IdentificacionImagen | AskOut:
    """Identifica una imagen y resuelve su admisibilidad."""
    with imagen_temporal(datos, formato) as ruta:
        identificacion = identificar_imagen(ruta)

    estado = identificacion["estado"]

    if estado == "allowed":
        return identificacion

    if estado == "policy_violation":
        raise ApiError(ErrorCode.IMAGE_CONTENT_NOT_ALLOWED)

    if estado == "out_of_domain":
        return _respuesta_previa(
            MENSAJE_ABSTENCION,
            "fuera_de_dominio",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    if estado == "uncertain":
        return _respuesta_previa(
            "No puedo identificar suficientemente el residuo. "
            "Proporciona otra imagen en la que se vea con claridad.",
            "ambiguedad",
            thread_id=thread_id,
            turnos_consumidos=turnos_consumidos,
        )

    raise RuntimeError("Estado de identificación visual inválido.")