"""Configuración del cliente nativo de Gemini."""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import (
    BASE_DIR,
    GEMINI_MAX_ATTEMPTS,
    GEMINI_TIMEOUT_SECONDS,
)


def crear_cliente_gemini() -> genai.Client:
    """Crea un cliente Gemini con límites de espera y reintentos."""
    ruta_env = BASE_DIR / ".env"

    load_dotenv(dotenv_path=ruta_env)

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "No se ha encontrado GEMINI_API_KEY. "
            "Configúrala en el archivo .env."
        )

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(
            timeout=GEMINI_TIMEOUT_SECONDS * 1000,
            retry_options=types.HttpRetryOptions(
                attempts=GEMINI_MAX_ATTEMPTS,
            ),
        ),
    )