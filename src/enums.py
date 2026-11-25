"""Enumerados compartidos de ReciclaTIA."""

from enum import Enum


class ApiKeyRole(str, Enum):
    """Roles asociados a las API keys."""

    FREE = "free"
    USER = "user"
    ADMIN = "admin"


class MessageRole(str, Enum):
    """Roles de los mensajes persistidos."""

    USER = "user"
    ASSISTANT = "assistant"
