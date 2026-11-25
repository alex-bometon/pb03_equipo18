"""Punto de entrada del backend HTTP de ReciclaTÍA."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.config import load_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Gestiona el ciclo de vida del backend."""

    app.state.settings = load_settings()

    yield


app = FastAPI(
    title="ReciclaTÍA API",
    description="API REST del asistente de gestión de residuos de Madrid.",
    lifespan=lifespan,
)
