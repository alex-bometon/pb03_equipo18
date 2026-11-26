"""Transformación de modelos relacionales en contratos públicos."""

from api.schemas import (
    ApiKeyOut,
    ConversationOut,
    MessageOut,
    UserOut,
)
from src.models import ApiKey, Conversation, Message, User


def to_user_out(user: User) -> UserOut:
    """Transforma un usuario en su representación pública."""
    return UserOut(
        id=user.id,
        email=user.email,
        created_at=user.created_at,
        is_active=user.is_active,
        deleted_at=user.deleted_at,
    )


def to_api_key_out(api_key: ApiKey) -> ApiKeyOut:
    """Transforma una API key sin exponer su credencial."""
    return ApiKeyOut(
        id=api_key.id,
        role=api_key.role,
        user_id=api_key.user_id,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        last_used_at=api_key.last_used_at,
        deleted_at=api_key.deleted_at,
    )


def to_conversation_out(
    conversation: Conversation,
) -> ConversationOut:
    """Transforma una conversación en su representación pública."""
    return ConversationOut(
        thread_id=str(conversation.id),
        api_key_id=str(conversation.api_key_id),
        created_at=conversation.created_at,
    )


def to_message_out(message: Message) -> MessageOut:
    """Transforma un mensaje sin exponer identificadores internos."""
    return MessageOut(
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )