"""Gestión del contexto de las peticiones HTTP."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from fastapi import Request

from src.enums import ApiKeyRole


REQUEST_ID_HEADER = "X-Request-ID"

API_KEY_CHALLENGE = "APIKey"
SESSION_CHALLENGE = "Bearer"

COMBINED_AUTH_CHALLENGE = (
    f"{API_KEY_CHALLENGE}, {SESSION_CHALLENGE}"
)


@dataclass(frozen=True)
class AuthContext:
    """Representa la identidad autenticada de una petición."""

    user_id: UUID | None
    api_key_id: UUID | None
    role: ApiKeyRole | None


def get_request_id(request: Request) -> str:
    """Recupera o genera el identificador de la petición."""
    request_id = getattr(request.state, "request_id", None)

    if request_id is None:
        request_id = str(uuid4())
        request.state.request_id = request_id

    return request_id