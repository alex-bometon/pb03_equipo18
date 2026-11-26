"""Gestión del contexto de las peticiones HTTP."""

from uuid import uuid4

from fastapi import Request


REQUEST_ID_HEADER = "X-Request-ID"


def get_request_id(request: Request) -> str:
    """Recupera o genera el identificador de la petición."""
    request_id = getattr(request.state, "request_id", None)

    if request_id is None:
        request_id = str(uuid4())
        request.state.request_id = request_id

    return request_id