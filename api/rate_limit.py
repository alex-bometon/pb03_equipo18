"""Limitadores de consumo mediante ventanas temporales deslizantes."""

from uuid import UUID
import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
import logging
from math import ceil
from threading import Lock

from api.error_catalog import ErrorCode
from api.errors import ApiError
from api.config import ApiSettings
from api.request_context import AuthContext
from src.enums import ApiKeyRole
from src.observability import registrar_evento


MINUTE = 60
HALF_HOUR = 30 * MINUTE
HOUR = 60 * MINUTE
DAY = 24 * HOUR

# Una ventana contiene su duración en segundos y su límite.
Ventana = tuple[int, int]

# Cada identidad pertenece a un ámbito de consumo independiente.
ClaveConsumo = tuple[str, str]

# El objeto distingue registros creados en un mismo instante.
RegistroConsumo = tuple[float, object]


class SlidingWindowLog:
    """Gestiona consumos independientes mediante ventanas deslizantes."""

    def __init__(
        self,
        politicas: Mapping[str, tuple[Ventana, ...]],
        *,
        reloj: Callable[[], float] = time.monotonic,
    ) -> None:
        """Inicializa las políticas y los recursos compartidos."""
        self._politicas = dict(politicas)
        self._reloj = reloj
        self._lock = Lock()

        self._registros: dict[
            ClaveConsumo, deque[RegistroConsumo]
        ] = defaultdict(deque)

        self._proxima_limpieza = reloj() + MINUTE

    def _limpiar_clave(
        self,
        clave: ClaveConsumo,
        ahora: float,
    ) -> None:
        """Elimina registros fuera de la ventana más larga."""
        cola = self._registros.get(clave)

        if cola is None:
            return

        ventanas = self._politicas[clave[0]]
        duracion_maxima = max(duracion for duracion, _ in ventanas)

        while cola and ahora - cola[0][0] >= duracion_maxima:
            cola.popleft()

        if not cola:
            del self._registros[clave]

    def _limpiar_caducados(self, ahora: float) -> None:
        """Retira periódicamente las identidades sin consumo vigente."""
        if ahora < self._proxima_limpieza:
            return

        for clave in tuple(self._registros):
            self._limpiar_clave(clave, ahora)

        self._proxima_limpieza = ahora + MINUTE

    def consumir(self, *claves: ClaveConsumo) -> RegistroConsumo:
        """Comprueba y registra una operación de forma atómica."""
        if not claves:
            raise ValueError("Se requiere una clave de consumo.")

        claves = tuple(dict.fromkeys(claves))

        with self._lock:
            ahora = self._reloj()

            self._limpiar_caducados(ahora)

            retry_after = 0.0

            for clave in claves:
                ventanas = self._politicas[clave[0]]

                self._limpiar_clave(clave, ahora)

                cola = self._registros.get(clave, ())

                for duracion, limite in ventanas:
                    vigentes = [
                        instante
                        for instante, _ in cola
                        if ahora - instante < duracion
                    ]

                    if len(vigentes) >= limite:
                        espera = vigentes[-limite] + duracion - ahora

                        retry_after = max(retry_after, espera)

            if retry_after <= 0:
                registro = (ahora, object())

                for clave in claves:
                    self._registros[clave].append(registro)

                return registro

        espera = ceil(retry_after)

        registrar_evento(
            "rate_limit_exceeded",
            nivel=logging.WARNING,
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED.value,
            ambitos=tuple(dict.fromkeys(clave[0] for clave in claves)),
            retry_after=espera,
        )

        raise ApiError(
            ErrorCode.RATE_LIMIT_EXCEEDED,
            retry_after=espera,
        )

    def revertir(
        self,
        clave: ClaveConsumo,
        registro: RegistroConsumo,
    ) -> bool:
        """Retira exclusivamente un registro de consumo concreto."""
        with self._lock:
            cola = self._registros.get(clave)

            if cola is None:
                return False

            try:
                cola.remove(registro)

            except ValueError:
                return False

            if not cola:
                del self._registros[clave]

            return True
        

def crear_limitador(
    settings: ApiSettings,
    *,
    reloj: Callable[[], float] = time.monotonic,
) -> SlidingWindowLog:
    """Construye las políticas de consumo a partir de la configuración."""
    return SlidingWindowLog(
        {
            "http_api_key": (
                (MINUTE, settings.RATE_LIMIT_PER_MINUTE),
            ),
            "http_user": (
                (MINUTE, settings.RATE_LIMIT_PER_MINUTE),
            ),
            "commercial_free": (
                (MINUTE, settings.FREE_RATE_LIMIT_PER_MINUTE),
                (HOUR, settings.FREE_RATE_LIMIT_PER_HOUR),
                (DAY, settings.FREE_RATE_LIMIT_PER_DAY),
            ),
            "commercial_user": (
                (MINUTE, settings.USER_RATE_LIMIT_PER_MINUTE),
                (HOUR, settings.USER_RATE_LIMIT_PER_HOUR),
                (DAY, settings.USER_RATE_LIMIT_PER_DAY),
            ),
            "login_email": (
                (HOUR, settings.LOGIN_EMAIL_LIMIT_PER_HOUR),
            ),
            "login_origin": (
                (HALF_HOUR, settings.LOGIN_ORIGIN_LIMIT_PER_30_MINUTES),
            ),
            "register_origin": (
                (HOUR, settings.REGISTER_LIMIT_PER_HOUR),
            ),
            "issue_origin": (
                (HOUR, settings.KEY_ISSUE_LIMIT_PER_HOUR),
                (DAY, settings.KEY_ISSUE_LIMIT_PER_DAY),
            ),
            "issue_user": (
                (HOUR, settings.KEY_ISSUE_LIMIT_PER_HOUR),
                (DAY, settings.KEY_ISSUE_LIMIT_PER_DAY),
            ),
        },
        reloj=reloj,
    )


def limitar_http(
    limitador: SlidingWindowLog,
    contexto: AuthContext,
) -> None:
    """Registra una petición de una identidad autenticada."""
    if contexto.api_key_id is not None:
        clave = ("http_api_key", str(contexto.api_key_id))

    elif contexto.user_id is not None:
        clave = ("http_user", str(contexto.user_id))

    else:
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR)

    limitador.consumir(clave)


def reservar_cuota_comercial(
    limitador: SlidingWindowLog,
    contexto: AuthContext,
) -> tuple[ClaveConsumo, RegistroConsumo] | None:
    """Registra una consulta costosa según el rol autenticado."""
    if contexto.api_key_id is None:
        raise ApiError(ErrorCode.API_KEY_REQUIRED)

    if contexto.role == ApiKeyRole.ADMIN:
        return None

    if contexto.role not in (ApiKeyRole.FREE, ApiKeyRole.USER):
        raise ApiError(ErrorCode.INSUFFICIENT_PERMISSIONS)

    clave = (f"commercial_{contexto.role.value}", str(contexto.api_key_id))

    registro = limitador.consumir(clave)

    return clave, registro

def limitar_login(
    limitador: SlidingWindowLog,
    email: str,
    origen: str,
) -> None:
    """Registra un intento de login con email ya normalizado."""
    limitador.consumir(
        ("login_email", email),
        ("login_origin", origen),
    )


def limitar_registro(
    limitador: SlidingWindowLog,
    origen: str,
) -> None:
    """Registra una solicitud de creación de cuenta."""
    limitador.consumir(("register_origin", origen))


def limitar_emision_anonima(
    limitador: SlidingWindowLog,
    origen: str,
) -> None:
    """Limita la emisión de claves sin propietario registrado."""
    limitador.consumir(("issue_origin", origen))


def limitar_emision_registrada(
    limitador: SlidingWindowLog,
    user_id: UUID,
) -> None:
    """Limita la emisión de claves por usuario destinatario."""
    limitador.consumir(("issue_user", str(user_id)))