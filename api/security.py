"""Primitivas de seguridad de ReciclaTIA."""

import hashlib
import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from time import monotonic
from uuid import UUID

import bcrypt

from api.credential_validation import (
    PasswordInvalidaError,
    validar_nueva_password,
    validar_password_verificacion,
)
from api.error_catalog import ErrorCode
from api.errors import ApiError

SESSION_CLEANUP_INTERVAL_SECONDS = 60.0


# =========================================================
# CONTRASEÑAS
# =========================================================


def hash_password(password: str, rounds: int) -> str:
    """Valida una contraseña nueva y genera su hash bcrypt."""
    try:
        password = validar_nueva_password(password)
    except PasswordInvalidaError:
        raise ApiError(ErrorCode.INVALID_PASSWORD) from None

    try:
        password_hash = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt(rounds=rounds),
        )
    except ValueError:
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR) from None

    return password_hash.decode("ascii")


def verify_password(
    password: str,
    password_hash: str,
) -> bool:
    """Comprueba una contraseña contra su hash almacenado."""
    try:
        password = validar_password_verificacion(password)
    except PasswordInvalidaError:
        raise ApiError(ErrorCode.INVALID_CREDENTIALS) from None

    if not isinstance(password_hash, str) or not re.fullmatch(
        r"\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}",
        password_hash,
    ):
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR)

    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            password_hash.encode("ascii"),
        )
    except ValueError:
        raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR) from None


# =========================================================
# TOKENS Y API KEYS
# =========================================================


def generate_secret() -> str:
    """Genera una credencial opaca de elevada entropía."""
    return secrets.token_urlsafe(32)


def hash_secret(secret: str) -> str:
    """Calcula el hash hexadecimal SHA-256 de una credencial."""
    return hashlib.sha256(
        secret.encode("utf-8"),
    ).hexdigest()


# =========================================================
# MITIGACIÓN DE ENUMERACIÓN TEMPORAL
# =========================================================


def create_dummy_password_hash(rounds: int) -> str:
    """Genera un hash auxiliar para usuarios inexistentes."""
    return hash_password(
        generate_secret(),
        rounds,
    )


# =========================================================
# GESTIÓN DE SESIONES
# =========================================================


@dataclass(frozen=True)
class SessionRecord:
    """Representa los datos internos de una sesión."""
    user_id: UUID
    created_at: datetime
    expires_at: datetime
    deadline: float
    token_hash: str = field(repr=False)


class SessionStore:
    """Gestiona sesiones temporales protegidas entre hilos."""

    def __init__(self, ttl_seconds: int) -> None:
        """Inicializa el almacenamiento y su sincronización."""
        if ttl_seconds <= 0:
            raise ValueError(
                "La duración de las sesiones debe ser positiva."
            )

        self._ttl_seconds = ttl_seconds
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = RLock()
        self._last_cleanup = monotonic()

    @contextmanager
    def locked(self) -> Iterator[None]:
        """Protege una unidad de trabajo síncrona compuesta."""
        with self._lock:
            yield

    def _cleanup_expired(self, now: float) -> None:
        """Elimina registros caducados con el bloqueo adquirido."""
        elapsed = now - self._last_cleanup

        if elapsed < SESSION_CLEANUP_INTERVAL_SECONDS:
            return

        expired = [
            token_hash
            for token_hash, session in self._sessions.items()
            if now >= session.deadline
        ]

        for token_hash in expired:
            del self._sessions[token_hash]

        self._last_cleanup = now

    def create(self, user_id: UUID) -> tuple[str, SessionRecord]:
        """Crea una sesión y devuelve su token y registro interno."""
        with self._lock:
            now = monotonic()
            self._cleanup_expired(now)

            token = generate_secret()
            token_hash = hash_secret(token)

            if token_hash in self._sessions:
                raise ApiError(ErrorCode.INTERNAL_SERVER_ERROR)

            created_at = datetime.now(timezone.utc)

            session = SessionRecord(
                user_id=user_id,
                created_at=created_at,
                expires_at=created_at + timedelta(
                    seconds=self._ttl_seconds,
                ),
                deadline=now + self._ttl_seconds,
                token_hash=token_hash,
            )

            self._sessions[token_hash] = session

            return token, session

    def get(self, token: str) -> SessionRecord:
        """Recupera una sesión y comprueba su vigencia."""
        if not isinstance(token, str):
            raise ApiError(ErrorCode.INVALID_SESSION)

        try:
            token_hash = hash_secret(token)
        except UnicodeEncodeError:
            raise ApiError(ErrorCode.INVALID_SESSION) from None

        with self._lock:
            now = monotonic()

            try:
                session = self._sessions.get(token_hash)

                if session is None:
                    raise ApiError(ErrorCode.INVALID_SESSION)

                if now >= session.deadline:
                    del self._sessions[token_hash]

                    raise ApiError(ErrorCode.SESSION_EXPIRED)

                return session

            finally:
                self._cleanup_expired(now)

    def revoke(self, token: str) -> None:
        """Invalida una sesión vigente."""
        with self._lock:
            session = self.get(token)

            del self._sessions[session.token_hash]

    def revoke_user(self, user_id: UUID) -> None:
        """Invalida todas las sesiones de un usuario."""
        with self._lock:
            self._cleanup_expired(monotonic())

            user_sessions = [
                token_hash
                for token_hash, session in self._sessions.items()
                if session.user_id == user_id
            ]

            for token_hash in user_sessions:
                del self._sessions[token_hash]