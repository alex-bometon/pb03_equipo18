"""Excepciones controladas de la API de ReciclaTIA."""

from api.error_catalog import ErrorCode


class ApiError(Exception):
    """Representa un error controlado de la API."""

    def __init__(
        self,
        code: ErrorCode,
        *,
        retry_after: int | None = None,
    ) -> None:
        """Inicializa el error y valida sus metadatos."""
        if not isinstance(code, ErrorCode):
            raise TypeError("Se requiere un código de error válido.")

        if retry_after is not None:
            if (
                not isinstance(retry_after, int)
                or isinstance(retry_after, bool)
            ):
                raise TypeError(
                    "retry_after debe ser un número entero."
                )

            if retry_after < 0:
                raise ValueError(
                    "retry_after no puede ser negativo."
                )

            if code != ErrorCode.RATE_LIMIT_EXCEEDED:
                raise ValueError(
                    "retry_after solo está permitido para "
                    "RATE_LIMIT_EXCEEDED."
                )

        self.code = code
        self.retry_after = retry_after

        super().__init__(code.value)