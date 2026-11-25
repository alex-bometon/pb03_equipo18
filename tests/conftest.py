"""Fixtures compartidas de las pruebas del orquestador RAG."""

from unittest.mock import Mock

import pytest

from src import rag

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlmodel import Session

from src.db import create_db_engine, ensure_schema


@pytest.fixture
def chunks():
    """Devuelve resultados representativos de buscar_chunks_relevantes."""
    return [
        {
            "text": "Envases de plástico: contenedor amarillo.",
            "distance": 0.21,
            "metadata": {
                "source": "tipos_residuos.csv",
                "path": "data/raw/csv/tipos_residuos.csv",
            },
        },
        {
            "text": "Papel y cartón: contenedor azul.",
            "distance": 0.28,
            "metadata": {
                "source": "fraccion_papel.html",
                "path": "data/raw/html/fraccion_papel.html",
            },
        },
    ]


@pytest.fixture
def respuesta_generada():
    """Simula el contrato de salida validado por generate.py."""
    return {
        "respuesta": "Los envases van al contenedor amarillo. [C1]",
        "abstencion": False,
        "motivo": None,
        "fuentes": [
            {
                "chunk_id": "C1",
                "source": "tipos_residuos.csv",
                "path": "data/raw/csv/tipos_residuos.csv",
            },
        ],
    }


@pytest.fixture
def dependencias(monkeypatch, chunks, respuesta_generada):
    """Intercepta el retrieval y la generación para evitar llamadas API."""
    recuperar = Mock(return_value=chunks)
    generar = Mock(return_value=respuesta_generada)
    monkeypatch.setattr(rag, "buscar_chunks_relevantes", recuperar)
    monkeypatch.setattr(rag, "generar_respuesta", generar)
    return recuperar, generar


@pytest.fixture
def catalogo_estructurado():
    """Proporciona el contrato agregado de consultar_catalogo_residuos."""
    return {
        "source": "tipos_residuos.csv",
        "path": "data/raw/csv/tipos_residuos.csv",
        "total_relaciones": 5,
        "total_destinos": 2,
        "destinos": [
            {
                "destino": "CONTENEDOR AMARILLO",
                "cantidad": 3,
                "ejemplos": [{"residuo": "Envases de plástico"}],
            },
            {
                "destino": "CONTENEDOR AZUL",
                "cantidad": 2,
                "ejemplos": [{"residuo": "Papel"}],
            },
        ],
        "registros_descartados": 0,
        "registros_duplicados": 0,
    }


@pytest.fixture
def paradas_estructuradas():
    """Representa dos paradas móviles ordinarias documentadas."""
    fuente = "puntos_limpios_moviles.csv"
    ruta = "data/raw/csv/puntos_limpios_moviles.csv"
    entradas = [
        ("CALLE ARRIETA, 15", "MARTES", "12:15 - 14:15", 2),
        ("CALLE BARQUILLO, 7", "SABADO", "07:45 - 09:45", 3),
    ]
    paradas = []
    for direccion, dia, horario, fila in entradas:
        texto = (
            "Punto limpio móvil.\n"
            f"Dirección: {direccion}.\n"
            "Distrito: CENTRO.\n"
            f"Día: {dia}.\n"
            f"Horario: {horario}."
        )
        metadata = {
            "source": fuente,
            "path": ruta,
            "document_type": "punto_limpio_movil",
            "district": "CENTRO",
            "day": dia,
            "source_row": fila,
        }
        paradas.append({
            "direccion": direccion,
            "distrito": "CENTRO",
            "dia": dia,
            "turno": "MAÑANA",
            "horario": horario,
            "source": fuente,
            "path": ruta,
            "text": texto,
            "metadata": metadata,
            "source_row": fila,
        })
    return paradas


@pytest.fixture
def consultas_estructuradas(
    monkeypatch, dependencias, catalogo_estructurado,
    paradas_estructuradas,
):
    """Simula lectores estructurados y deja vigilada la vía semántica."""
    catalogo = Mock(return_value=catalogo_estructurado)
    moviles = Mock(return_value=paradas_estructuradas)
    monkeypatch.setattr(rag, "consultar_catalogo_residuos", catalogo)
    monkeypatch.setattr(rag, "consultar_paradas_moviles", moviles)
    return catalogo, moviles


# =========================================================
# POSTGRESQL — PRUEBAS DE INTEGRACIÓN
# =========================================================

@pytest.fixture(scope="session")
def test_engine():
    """Inicializa exclusivamente PostgreSQL de pruebas."""

    env_path = Path(__file__).resolve().parents[1] / ".env.test"

    database_url = (
        os.environ.get("TEST_DATABASE_URL")
        or dotenv_values(env_path).get("TEST_DATABASE_URL")
    )

    if not database_url:
        pytest.skip("TEST_DATABASE_URL no configurada.")

    url = make_url(database_url)

    if (
        url.drivername not in {
            "postgresql",
            "postgresql+psycopg2",
        }
        or url.database != "reciclatia_test"
        or url.username != "reciclatia_test"
        or url.host not in {"localhost", "127.0.0.1"}
        or url.port != 5432
        or url.query
    ):
        raise RuntimeError(
            "Conexión PostgreSQL de pruebas no autorizada."
        )

    engine = create_db_engine(
        database_url,
        pool_size=3,
        max_overflow=0,
        pool_timeout=5,
        connect_timeout=5,
        statement_timeout=5,
        lock_timeout=3,
    )

    try:
        with engine.connect() as connection:
            result = connection.execute(text("""
                SELECT
                    current_database(),
                    current_user,
                    session_user,
                    rolsuper,
                    has_database_privilege(
                        current_user,
                        'reciclatia',
                        'CONNECT'
                    )
                FROM pg_roles
                WHERE rolname = current_user
            """)).one()

            if tuple(result) != (
                "reciclatia_test",
                "reciclatia_test",
                "reciclatia_test",
                False,
                False,
            ):
                raise RuntimeError(
                    "El entorno de pruebas no está aislado."
                )

        ensure_schema(engine)

        yield engine

    finally:
        engine.dispose()


def clean_test_database(engine):
    """Elimina exclusivamente los registros de pruebas."""

    with engine.begin() as connection:
        database, user = connection.execute(text("""
            SELECT current_database(), current_user
        """)).one()

        if (
            database != "reciclatia_test"
            or user != "reciclatia_test"
        ):
            raise RuntimeError(
                "Limpieza de base de datos no autorizada."
            )

        connection.execute(text("""
            TRUNCATE TABLE
                public.message,
                public.conversation,
                public.api_key,
                public."user"
            RESTART IDENTITY
        """))


@pytest.fixture
def clean_db(test_engine):
    """Limpia los datos antes y después de cada prueba."""

    clean_test_database(test_engine)

    yield test_engine

    clean_test_database(test_engine)


@pytest.fixture
def db_session(clean_db):
    """Proporciona una sesión SQL independiente por prueba."""

    with Session(clean_db) as session:
        yield session

        session.rollback()
