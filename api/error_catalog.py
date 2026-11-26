"""Catálogo de errores públicos de ReciclaTÍA."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from config import MAX_PREGUNTA_CARACTERES


class ErrorCode(str, Enum):
    """Códigos públicos de error de la API."""

    # Autenticación y autorización.
    API_KEY_REQUIRED = "API_KEY_REQUIRED"
    INVALID_API_KEY = "INVALID_API_KEY"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INVALID_SESSION = "INVALID_SESSION"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    API_KEY_INACTIVE = "API_KEY_INACTIVE"
    USER_INACTIVE = "USER_INACTIVE"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"
    USER_TIER_NOT_AUTHORIZED = "USER_TIER_NOT_AUTHORIZED"

    # Recursos.
    THREAD_NOT_FOUND = "THREAD_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    API_KEY_NOT_FOUND = "API_KEY_NOT_FOUND"
    EMAIL_ALREADY_EXISTS = "EMAIL_ALREADY_EXISTS"
    API_KEY_LIMIT_REACHED = "API_KEY_LIMIT_REACHED"
    API_KEY_DELETED = "API_KEY_DELETED"
    USER_DELETED = "USER_DELETED"

    # Conversaciones y HITL.
    NO_PENDING_APPROVAL = "NO_PENDING_APPROVAL"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    THREAD_CLOSED = "THREAD_CLOSED"
    TURN_LIMIT_REACHED = "TURN_LIMIT_REACHED"
    THREAD_BUSY = "THREAD_BUSY"
    THREAD_STATE_LOST = "THREAD_STATE_LOST"
    STALE_APPROVAL = "STALE_APPROVAL"

    # Validación.
    EMPTY_QUESTION = "EMPTY_QUESTION"
    QUESTION_TOO_LONG = "QUESTION_TOO_LONG"
    INVALID_THREAD_ID = "INVALID_THREAD_ID"
    INVALID_LOCATION = "INVALID_LOCATION"
    INVALID_MAX_STEPS = "INVALID_MAX_STEPS"
    INVALID_EMAIL = "INVALID_EMAIL"
    INVALID_PASSWORD = "INVALID_PASSWORD"
    AMBIGUOUS_CREDENTIALS = "AMBIGUOUS_CREDENTIALS"
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # Imágenes.
    IMAGE_FILE_TOO_LARGE = "IMAGE_FILE_TOO_LARGE"
    IMAGE_FORMAT_NOT_ALLOWED = "IMAGE_FORMAT_NOT_ALLOWED"
    IMAGE_RESOLUTION_EXCEEDED = "IMAGE_RESOLUTION_EXCEEDED"
    IMAGE_CORRUPTED = "IMAGE_CORRUPTED"
    IMAGE_CONTENT_NOT_ALLOWED = "IMAGE_CONTENT_NOT_ALLOWED"

    # Robustez y dependencias.
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    SERVICE_NOT_CONFIGURED = "SERVICE_NOT_CONFIGURED"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    SERVER_BUSY = "SERVER_BUSY"
    AGENT_TIMEOUT = "AGENT_TIMEOUT"

    # Protocolo HTTP.
    BAD_REQUEST = "BAD_REQUEST"
    ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"

@dataclass(frozen=True)
class ErrorDefinition:
    """Estado HTTP y mensaje público asociados a un error."""

    status_code: int
    message: str

# =============================================================
# CATALOGO COMPLETO
# =============================================================

ERROR_CATALOG: Mapping[ErrorCode, ErrorDefinition] = MappingProxyType({
    # Autenticación y autorización.
    ErrorCode.API_KEY_REQUIRED: ErrorDefinition(
        401,
        "Se requiere una API key.",
    ),
    ErrorCode.INVALID_API_KEY: ErrorDefinition(
        401,
        "La API key proporcionada no es válida.",
    ),
    ErrorCode.INVALID_CREDENTIALS: ErrorDefinition(
        401,
        "Las credenciales proporcionadas no son válidas.",
    ),
    ErrorCode.INVALID_SESSION: ErrorDefinition(
        401,
        "La sesión no es válida.",
    ),
    ErrorCode.SESSION_EXPIRED: ErrorDefinition(
        401,
        "La sesión ha caducado.",
    ),
    ErrorCode.API_KEY_INACTIVE: ErrorDefinition(
        403,
        "La API key está desactivada.",
    ),
    ErrorCode.USER_INACTIVE: ErrorDefinition(
        403,
        "La cuenta está desactivada.",
    ),
    ErrorCode.INSUFFICIENT_PERMISSIONS: ErrorDefinition(
        403,
        "No dispone de permisos para realizar esta operación.",
    ),
    ErrorCode.USER_TIER_NOT_AUTHORIZED: ErrorDefinition(
        403,
        "No está autorizada la emisión de una API key User.",
    ),

    # Recursos.
    ErrorCode.THREAD_NOT_FOUND: ErrorDefinition(
        404,
        "Conversación no encontrada.",
    ),
    ErrorCode.USER_NOT_FOUND: ErrorDefinition(
        404,
        "Usuario no encontrado.",
    ),
    ErrorCode.API_KEY_NOT_FOUND: ErrorDefinition(
        404,
        "API key no encontrada.",
    ),
    ErrorCode.EMAIL_ALREADY_EXISTS: ErrorDefinition(
        409,
        "El email ya está registrado.",
    ),
    ErrorCode.API_KEY_LIMIT_REACHED: ErrorDefinition(
        409,
        "Se ha alcanzado el límite de API keys activas.",
    ),
    ErrorCode.API_KEY_DELETED: ErrorDefinition(
        409,
        "La API key está eliminada.",
    ),
    ErrorCode.USER_DELETED: ErrorDefinition(
        409,
        "El usuario está eliminado.",
    ),

    # Conversaciones y HITL.
    ErrorCode.NO_PENDING_APPROVAL: ErrorDefinition(
        409,
        "No existe ninguna aprobación pendiente.",
    ),
    ErrorCode.PENDING_APPROVAL: ErrorDefinition(
        409,
        "Debe resolver la aprobación pendiente.",
    ),
    ErrorCode.THREAD_CLOSED: ErrorDefinition(
        409,
        "La conversación está finalizada.",
    ),
    ErrorCode.TURN_LIMIT_REACHED: ErrorDefinition(
        409,
        "Se ha alcanzado el límite de turnos.",
    ),
    ErrorCode.THREAD_BUSY: ErrorDefinition(
        409,
        "La conversación está siendo utilizada.",
    ),
    ErrorCode.THREAD_STATE_LOST: ErrorDefinition(
        409,
        "No se puede recuperar el estado de la conversación.",
    ),
    ErrorCode.STALE_APPROVAL: ErrorDefinition(
        409,
        "La aprobación indicada ya no es vigente.",
    ),

    # Validación.
    ErrorCode.EMPTY_QUESTION: ErrorDefinition(
        400,
        "La pregunta no puede estar vacía.",
    ),
    ErrorCode.QUESTION_TOO_LONG: ErrorDefinition(
        422,
        "La pregunta no puede superar "
        f"los {MAX_PREGUNTA_CARACTERES} caracteres.",
    ),
    ErrorCode.INVALID_THREAD_ID: ErrorDefinition(
        422,
        "El identificador de conversación no es válido.",
    ),
    ErrorCode.INVALID_LOCATION: ErrorDefinition(
        422,
        "Las coordenadas proporcionadas no son válidas.",
    ),
    ErrorCode.INVALID_MAX_STEPS: ErrorDefinition(
        422,
        "El número máximo de pasos no es válido.",
    ),
    ErrorCode.INVALID_EMAIL: ErrorDefinition(
        422,
        "El email proporcionado no es válido.",
    ),
    ErrorCode.INVALID_PASSWORD: ErrorDefinition(
        422,
        "La contraseña no cumple los requisitos establecidos.",
    ),
    ErrorCode.AMBIGUOUS_CREDENTIALS: ErrorDefinition(
        422,
        "Las modalidades de autenticación son incompatibles.",
    ),
    ErrorCode.VALIDATION_ERROR: ErrorDefinition(
        422,
        "La petición no cumple el contrato establecido.",
    ),

    # Imágenes.
    ErrorCode.IMAGE_FILE_TOO_LARGE: ErrorDefinition(
        413,
        "La imagen supera el tamaño de archivo permitido.",
    ),
    ErrorCode.IMAGE_FORMAT_NOT_ALLOWED: ErrorDefinition(
        415,
        "El formato de imagen no está permitido.",
    ),
    ErrorCode.IMAGE_RESOLUTION_EXCEEDED: ErrorDefinition(
        422,
        "La imagen supera la resolución permitida.",
    ),
    ErrorCode.IMAGE_CORRUPTED: ErrorDefinition(
        422,
        "No se ha podido interpretar el archivo de imagen.",
    ),
    ErrorCode.IMAGE_CONTENT_NOT_ALLOWED: ErrorDefinition(
        422,
        "El contenido de la imagen no está permitido.",
    ),

    # Robustez y dependencias.
    ErrorCode.RATE_LIMIT_EXCEEDED: ErrorDefinition(
        429,
        "Se ha alcanzado el límite de peticiones.",
    ),
    ErrorCode.INTERNAL_SERVER_ERROR: ErrorDefinition(
        500,
        "Se ha producido un error interno.",
    ),
    ErrorCode.SERVICE_NOT_CONFIGURED: ErrorDefinition(
        503,
        "El servicio no está configurado correctamente.",
    ),
    ErrorCode.SERVICE_UNAVAILABLE: ErrorDefinition(
        503,
        "El servicio no está disponible temporalmente.",
    ),
    ErrorCode.SERVER_BUSY: ErrorDefinition(
        503,
        "El servicio ha alcanzado su capacidad de procesamiento.",
    ),
    ErrorCode.AGENT_TIMEOUT: ErrorDefinition(
        504,
        "Se ha superado el tiempo máximo de ejecución.",
    ),

    # Protocolo HTTP.
    ErrorCode.BAD_REQUEST: ErrorDefinition(
        400,
        "No se ha podido interpretar la petición.",
    ),
    ErrorCode.ROUTE_NOT_FOUND: ErrorDefinition(
        404,
        "La ruta solicitada no existe.",
    ),
    ErrorCode.METHOD_NOT_ALLOWED: ErrorDefinition(
        405,
        "El método HTTP no está permitido para esta ruta.",
    ),
})