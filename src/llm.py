"""Inicialización del modelo Gemini para los agentes LangGraph.

El RAG mantiene su cliente nativo independiente.
Este módulo solo proporciona el modelo de LangChain.
"""

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from config import (
    BASE_DIR,
    AGENT_MODEL,
    AGENT_TEMPERATURE,
    SUPERVISOR_TEMPERATURE,
    GEMINI_MAX_ATTEMPTS,
    GEMINI_TIMEOUT_SECONDS,
)


def get_llm(
    *,
    supervisor: bool = False,
) -> ChatGoogleGenerativeAI:
    """Crea el modelo Gemini con los límites de ejecución definidos."""
    load_dotenv(dotenv_path=BASE_DIR / ".env")

    temperatura = (
        SUPERVISOR_TEMPERATURE
        if supervisor
        else AGENT_TEMPERATURE
    )

    return ChatGoogleGenerativeAI(
        model=AGENT_MODEL,
        temperature=temperatura,
        timeout=GEMINI_TIMEOUT_SECONDS,
        max_retries=GEMINI_MAX_ATTEMPTS,
    )