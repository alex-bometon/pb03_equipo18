"""Configuración global de ReciclaTIA PB02.

Centraliza los parámetros operativos del proyecto.
Las reglas de negocio, algoritmos y esquemas permanecen
en sus respectivos módulos.

Las credenciales se cargan desde .env.
"""

from pathlib import Path


# =========================================================
# RUTAS DEL PROYECTO
# =========================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
CSV_DIR = RAW_DIR / "csv"
HTML_DIR = RAW_DIR / "html"

ASSETS_DIR = BASE_DIR / "assets"

OUTPUT_DIR = BASE_DIR / "output"
CHUNKS_JSON = OUTPUT_DIR / "chunks.json"
EMBEDDINGS_JSON = OUTPUT_DIR / "embeddings.json"


# =========================================================
# FUENTES DOCUMENTALES OFICIALES
# =========================================================

FUENTES_OFICIALES: dict[str, str] = {
    "puntos_limpios_fijos.csv": (
        "https://datos.madrid.es/dataset/200284-0-puntos-limpios-fijos"
    ),
    "puntos_limpios_moviles.csv": (
        "https://datos.madrid.es/dataset/300101-0-puntos-limpios-moviles"
    ),
    "puntos_limpios_moviles_24h.csv": (
        "https://datos.madrid.es/dataset/900026-0-puntos-limpios-residuos"
    ),
    "puntos_limpios_proximidad.csv": (
        "https://datos.madrid.es/dataset/300198-0-puntos-proximidad"
    ),
    "tipos_residuos.csv": (
        "https://datos.madrid.es/dataset/300199-0-tipo-residuo"
    ),
    "fraccion_organica.html": (
        "https://www.madrid.es/portales/munimadrid/es/"
        "Recogida-de-residuos-organicos/"
        "?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD"
        "&vgnextoid=12bc51e3f7bee510VgnVCM1000001d4a900aRCRD"
    ),
    "fraccion_papel.html": (
        "https://www.madrid.es/portales/munimadrid/es/Inicio/"
        "El-Ayuntamiento/Moratalaz/Recogida-de-la-fraccion-papel-y-carton/"
        "?vgnextchannel=7cb0ca5d5fb96010VgnVCM100000dc0ca8c0RCRD"
        "&vgnextfmt=default"
        "&vgnextoid=d9eb6c9c78eb2910VgnVCM2000001f4a900aRCRD"
    ),
    "fraccion_plasticos_metales_briks.html": (
        "https://www.madrid.es/portales/munimadrid/es/"
        "Recogida-de-plasticos-metales-y-briks-Horarios-y-frecuencias-"
        "de-recogida-/"
        "?vgnextchannel=3dfcbb21278fe410VgnVCM1000000b205a0aRCRD"
        "&vgnextfmt=default"
        "&vgnextoid=54c4ebd9be6e8610VgnVCM1000001d4a900aRCRD"
    ),
    "fraccion_resto.html": (
        "https://www.madrid.es/portales/munimadrid/es/"
        "Recogida-fraccion-resto-no-reciclable-y-horario/"
        "?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD"
        "&vgnextoid=61c4ebd9be6e8610VgnVCM1000001d4a900aRCRD"
    ),
    "fraccion_vidrio.html": (
        "https://www.madrid.es/portales/munimadrid/es/Recogida-de-vidrio/"
        "?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD"
        "&vgnextoid=e3ab6c9c78eb2910VgnVCM2000001f4a900aRCRD"
    ),
    "recogida_aceite_vegetal.html": (
        "https://www.madrid.es/portales/munimadrid/es/Inicio/"
        "Medio-ambiente/Recogida-de-residuos/"
        "Recogida-de-aceite-vegetal-usado/"
        "?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD"
        "&vgnextfmt=default"
        "&vgnextoid=803fab39d9462510VgnVCM1000000b205a0aRCRD"
    ),
    "recogida_muebles_enseres.html": (
        "https://www.madrid.es/portales/munimadrid/es/Inicio/"
        "MedioAmbiente/ResiduosYLimpiezaUrbana/Tramites/"
        "Recogida-de-muebles-electrodomesticos-y-enseres/"
        "?vgnextchannel=e5bcbb21278fe410VgnVCM1000000b205a0aRCRD"
        "&vgnextfmt=default"
        "&vgnextoid=168e3381d0030910VgnVCM1000001d4a900aRCRD"
    ),
    "residuos_punto_limpio_fijo.html": (
        "https://www.madrid.es/portales/munimadrid/es/UnidadWeb/"
        "Puntos-Limpios-Fijos-del-Ayuntamiento-de-Madrid-Descripcion-y-"
        "cantidades-admisibles-para-particulares/"
        "?vgnextchannel=e278e8124824b010VgnVCM1000000b205a0aRCRD"
        "&vgnextoid=cc9a2984ca480510VgnVCM2000000c205a0aRCRD"
    ),
    "residuos_punto_limpio_movil.html": (
        "https://sede.madrid.es/portal/site/tramites/"
        "menuitem.1f3361415fda829be152e15284f1a5a0/"
        "?vgnextchannel=518aa38813180210VgnVCM100000c90da8c0RCRD"
        "&vgnextfmt=pda"
        "&vgnextoid=3cbc6163c4480510VgnVCM2000000c205a0aRCRD"
    ),
    "residuos_punto_limpio_proximidad.html": (
        "https://www.madrid.es/portales/munimadrid/es/Inicio/"
        "Medio-ambiente/Gestiones-y-tramites/"
        "Puntos-Limpios-de-Proximidad-Descripcion-y-cantidades-admisibles-/"
        "?vgnextchannel=658f79ed268fe410VgnVCM1000000b205a0aRCRD"
        "&vgnextfmt=default"
        "&vgnextoid=2682a2dcf3189610VgnVCM1000001d4a900aRCRD"
    ),
}


# =========================================================
# FRAGMENTACIÓN DEL CORPUS
# =========================================================

CHUNK_SIZE = 1_000
CHUNK_OVERLAP = 100


# =========================================================
# EMBEDDINGS GEMINI
# =========================================================

EMBEDDING_MODEL = "gemini-embedding-2"
EMBEDDING_DIMENSIONS = 768

EMBED_BATCH_SIZE = 50
MAX_CHUNKS_EMBED = None

EMBED_BATCH_PAUSE_SECONDS = 32
EMBED_MAX_RETRIES = 5
EMBED_RETRY_SECONDS = 60


# =========================================================
# ÍNDICE VECTORIAL CHROMADB
# =========================================================

CHROMA_DIR = OUTPUT_DIR / "chroma_db"
CHROMA_COLLECTION_NAME = "residuos_madrid"
CHROMA_DISTANCE = "cosine"

INDEX_BATCH_SIZE = 100


# =========================================================
# RECUPERACIÓN Y CONTEXTO RAG
# =========================================================

TOP_K = 5
MAX_TOP_K_RETRIEVAL = 10

MAX_PREGUNTA_CARACTERES = 500
MAX_CONTEXTO_CARACTERES = 12_000

EJEMPLOS_POR_DESTINO = 2


# =========================================================
# GENERACIÓN GEMINI
# =========================================================

GENERATION_MODEL = "gemini-3.5-flash-lite"

GEMINI_TIMEOUT_SECONDS = 45
GEMINI_MAX_ATTEMPTS = 1

GENERATION_TEMPERATURE = 0
GENERATION_MAX_RETRIES = 2
GENERATION_RETRY_SECONDS = 2


# =========================================================
# HERRAMIENTA MULTIMODAL
# =========================================================

IMAGE_MODEL = GENERATION_MODEL

IMAGE_MAX_BYTES = 5 * 1024 * 1024
IMAGE_MAX_PIXELS = 16_000_000

IMAGE_ALLOWED_EXTENSIONS = frozenset({
    ".jpg",
    ".jpeg",
    ".png",
})

IMAGE_ALLOWED_FORMATS = frozenset({
    "JPEG",
    "PNG",
})


# =========================================================
# API MUNICIPAL DE PUNTOS LIMPIOS
# =========================================================

API_PUNTOS_LIMPIOS_URL = (
    "https://sigma.madrid.es/hosted/rest/services/"
    "RESIDUOS/PUNTOS_LIMPIOS/MapServer/5/query"
)

API_TIMEOUT_SECONDS = 12
API_RESULT_RECORD_COUNT = 2_000


# =========================================================
# BÚSQUEDA GEOGRÁFICA
# =========================================================

GEO_MIN_LATITUDE = -90
GEO_MAX_LATITUDE = 90

GEO_MIN_LONGITUDE = -180
GEO_MAX_LONGITUDE = 180

GEO_DEFAULT_RADIUS_METERS = 2_000
GEO_MIN_RADIUS_METERS = 1
GEO_MAX_RADIUS_METERS = 5_000

GEO_MAX_RESULTS = 10


# =========================================================
# FECHA Y HORA
# =========================================================

TIMEZONE = "Europe/Madrid"



# =========================================================
# LANGGRAPH — MODELOS Y GENERACIÓN DE AGENTES
# =========================================================

# Reutilizamos el modelo Gemini configurado para el RAG.
AGENT_MODEL = GENERATION_MODEL

# Temperatura de los agentes y del supervisor.
AGENT_TEMPERATURE = 0
SUPERVISOR_TEMPERATURE = 0


# =========================================================
# LANGGRAPH — LÍMITES DE ORQUESTACIÓN
# =========================================================

# Máximo de decisiones del supervisor por consulta.
MAX_ITER = 4

# Máximo de rondas LLM por especialista.
MAX_STEPS_DEFAULT = 3
MAX_STEPS_LIMIT = 4

# Presupuestos de llamadas reales a herramientas.
# Una ronda LLM puede solicitar varias herramientas.
MAX_TOOL_CALLS_PER_SPECIALIST = 4
MAX_TOOL_CALLS_PER_TURN = 6

# Límite de pasos internos del grafo.
GRAPH_RECURSION_LIMIT = 2 * MAX_ITER + 8


# =========================================================
# CONVERSACIÓN — CLI Y STREAMLIT
# =========================================================

# Límites de consultas por conversación.
MAX_TURNS_DEFAULT = 6
MAX_TURNS_LIMIT = 12

# Contexto de turnos anteriores.
MAX_HISTORY_TURNS = 6

# Reutilizamos la validación de longitud del RAG.
AGENT_MAX_MESSAGE_CHARS = MAX_PREGUNTA_CARACTERES


# =========================================================
# OBSERVABILIDAD Y TRAZABILIDAD
# =========================================================

# Longitud máxima de las previsualizaciones de herramientas.
TRACE_PREVIEW_MAX_CHARS = 160


# =========================================================
# HERRAMIENTAS PERMITIDAS POR ESPECIALISTA
# =========================================================

# Restricciones adicionales a la allowlist global de src.tools.
# La ejecución y validación corresponden al módulo de herramientas.
AGENT_TOOLS_BY_ROLE = {
    "residuos": (
        "consultar_rag",
        "describir_imagen",
        "hora_actual",
    ),
    "puntos": (
        "consultar_rag",
        "buscar_puntos_limpios_cercanos",
        "hora_actual",
    ),
}


# =========================================================
# POLÍTICA DE CREDENCIALES
# =========================================================

EMAIL_MAX_LENGTH = 254

PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_BYTES = 72