"""Allowlist de herramientas de ReciclaTIA."""

from typing import Any, Literal, TypedDict

from config import (
    AGENT_TOOLS_BY_ROLE,
    GEO_MAX_LATITUDE,
    GEO_MAX_LONGITUDE,
    GEO_MAX_RADIUS_METERS,
    GEO_MIN_LATITUDE,
    GEO_MIN_LONGITUDE,
    GEO_MIN_RADIUS_METERS,
)
from src.input_validation import validar_pregunta

from .api_puntos_limpios import (
    TIPOS_PUNTOS_LIMPIOS,
    _coordenada_valida,
    buscar_puntos_limpios_cercanos,
)
from .describir_imagen import describir_imagen as _describir_imagen
from .hora_actual import hora_actual as _hora_actual
from .rag_tool import consultar_rag


# Herramientas autorizadas para el agente.
TOOLS = [
    consultar_rag,
    buscar_puntos_limpios_cercanos,
    _hora_actual,
    _describir_imagen,
]

TOOL_BY_NAME = {t.name: t for t in TOOLS}


# =========================================================
# CONTRATO DE EJECUCIÓN
# =========================================================

RolEspecialista = Literal["residuos", "puntos"]


class ResultadoTool(TypedDict):
    """Resultado de una herramienta sin perder su estructura."""

    ok: bool
    nombre: str
    datos: Any
    error: str | None


# =========================================================
# RESULTADOS DE ERROR
# =========================================================

def _fallo(nombre: str, mensaje: str) -> ResultadoTool:
    """Construye un fallo sin exponer excepciones ni secretos."""

    return {
        "ok": False,
        "nombre": nombre,
        "datos": None,
        "error": mensaje,
    }


# =========================================================
# EJECUCIÓN CENTRALIZADA DE HERRAMIENTAS
# =========================================================

def validar_solicitud_tool(
    nombre: str,
    args: Any,
    *,
    rol: RolEspecialista | None = None,
) -> str | None:
    """Valida permisos y argumentos antes de ejecutar una herramienta."""
    if not isinstance(nombre, str) or nombre not in TOOL_BY_NAME:
        return "Error: herramienta no permitida."

    if rol is not None and nombre not in AGENT_TOOLS_BY_ROLE.get(rol, ()):
        return "Error: herramienta no permitida para el rol."

    if not isinstance(args, dict):
        return "Error: argumentos inválidos."

    herramienta = TOOL_BY_NAME[nombre]

    if (
        any(not isinstance(clave, str) for clave in args)
        or set(args) - set(herramienta.args)
    ):
        return "Error: argumentos no permitidos."

    if nombre == "consultar_rag":
        try:
            validar_pregunta(args.get("pregunta"))
        except ValueError:
            return "Error: pregunta inválida."

    elif nombre == "buscar_puntos_limpios_cercanos":
        if not _coordenada_valida(
            args.get("latitud"),
            GEO_MIN_LATITUDE,
            GEO_MAX_LATITUDE,
        ):
            return "Error: latitud inválida."

        if not _coordenada_valida(
            args.get("longitud"),
            GEO_MIN_LONGITUDE,
            GEO_MAX_LONGITUDE,
        ):
            return "Error: longitud inválida."

        if "radio_metros" in args:
            radio = args["radio_metros"]

            if (
                type(radio) is not int
                or not GEO_MIN_RADIUS_METERS
                <= radio <= GEO_MAX_RADIUS_METERS
            ):
                return "Error: radio inválido."

        if "tipo" in args:
            tipo = args["tipo"]

            if (
                not isinstance(tipo, str)
                or tipo.strip().lower() not in TIPOS_PUNTOS_LIMPIOS
            ):
                return "Error: modalidad inválida."

    elif nombre == "describir_imagen":
        ruta = args.get("ruta_imagen")

        if not isinstance(ruta, str) or not ruta.strip():
            return "Error: ruta de imagen inválida."

    return None


def _ejecutar(
    nombre: str,
    args: dict | None,
    *,
    rol: RolEspecialista | None = None,
) -> ResultadoTool:
    """Valida permisos y argumentos; ejecuta una sola vez."""
    if args is None:
        args = {}

    fallo = validar_solicitud_tool(nombre, args, rol=rol)

    if fallo is not None:
        return _fallo(nombre if isinstance(nombre, str) else "", fallo)

    try:
        datos = TOOL_BY_NAME[nombre].invoke(args)

    except Exception:
        return _fallo(nombre, "Error: no se pudo ejecutar la herramienta.")

    return {
        "ok": True,
        "nombre": nombre,
        "datos": datos,
        "error": None,
    }


# =========================================================
# INTERFAZ ORIGINAL — COMPATIBILIDAD
# =========================================================

def ejecutar_tool(
    nombre: str,
    args: dict | None = None,
) -> str:
    """Mantiene la interfaz textual existente."""

    resultado = _ejecutar(nombre, args)

    if not resultado["ok"]:
        return (
            resultado["error"]
            or "Error: no se pudo ejecutar la herramienta."
        )

    return str(resultado["datos"])


# =========================================================
# INTERFAZ MULTIAGENTE — DATOS ESTRUCTURADOS
# =========================================================

def ejecutar_tool_estructurado(
    nombre: str,
    args: dict | None = None,
    *,
    rol: RolEspecialista,
) -> ResultadoTool:
    """Ejecuta una tool respetando los permisos del especialista."""

    # Un rol desconocido no puede ejecutar ninguna herramienta.
    if rol not in AGENT_TOOLS_BY_ROLE:
        return _fallo(
            nombre if isinstance(nombre, str) else "",
            "Error: rol no autorizado.",
        )

    return _ejecutar(
        nombre,
        args,
        rol=rol,
    )