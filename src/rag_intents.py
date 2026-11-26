"""Detección conservadora de intenciones del asistente RAG.

No accede a Gemini, a ChromaDB ni al estado de los agentes.
"""

import re

from src.domain import _es_otra_ciudad, evaluar_ambito
from src.text_utils import normalizar_texto


PATRON_MOVIL = re.compile(r"\bpuntos?\s+limpios?\s+movil(?:es)?\b")
PATRON_HORARIO = re.compile(
    r"\b(?:horarios?|horas?|dias?|cuando|pasa|visita)\b"
)
PATRON_24H = re.compile(r"\b24\s*(?:h|horas?)\b")
PATRON_DISPOSITIVO_TELEFONICO = re.compile(
    r"\b(?:movil(?:es)?|telefonos?|smartphones?|celular(?:es)?)\b"
)
PATRON_REPARACION = re.compile(
    r"\b(?:reparac(?:ion|iones)|repar(?:ar|an|a)|"
    r"arregl(?:ar|an|o)|servicios?\s+tecnicos?)\b"
)
PATRON_BUSQUEDA_SERVICIO = re.compile(
    r"\b(?:donde|como|cual(?:es)?|hay|cerca|busco|necesito|"
    r"taller(?:es)?|tiendas?|servicios?|tecnicos?|precio|"
    r"coste|cuanto|cuesta)\b"
)
PATRON_CONTEXTO_RESIDUOS = re.compile(
    r"\b(?:recicl\w*|residuos?|basura|contenedores?|"
    r"puntos?\s+limpios?|depositar|desech\w*|"
    r"tirar|tiro|reutiliz\w*|recogida|deshacerme)\b"
)
PATRON_DIRECCION = re.compile(
    r"\b(?:calle|avenida|avda|plaza|paseo|ronda|camino)\s+"
    r"[a-z0-9\s.,\-/]+"
)
DIAS = {
    "lunes": "lunes",
    "martes": "martes",
    "miercoles": "miercoles",
    "jueves": "jueves",
    "viernes": "viernes",
    "sabado": "sabado",
    "sabados": "sabado",
    "domingo": "domingo",
    "domingos": "domingo",
}
PATRON_DIA = re.compile(
    r"\b(?:" + "|".join(DIAS) + r")\b"
)
PATRON_PROXIMIDAD = re.compile(
    r"\b(?:cerca|cercan\w*|alrededor|localiz\w*|"
    r"mas\s+proxim[oa]s?)\b"
)
MENSAJE_ACLARACION_HORARIO_MOVIL = (
    "¿En qué distrito o calle de Madrid quieres consultar "
    "el horario del punto limpio móvil?"
)
MENSAJE_ACLARACION_PROXIMIDAD = (
    "Para buscar puntos limpios cercanos, facilita "
    "voluntariamente latitud y longitud."
)
MENSAJE_ACLARACION_CONTEXTO = (
    "¿A qué residuo o punto limpio te refieres? "
    "Necesito más información para resolver tu consulta."
)


def _es_consulta_catalogo(pregunta: str) -> bool:
    """Selecciona solo peticiones explícitas de panorama general."""
    if re.search(
        r"\b(?:donde|como|tirar|tiro|reciclo|contenedor|"
        r"punto limpio|llevar|depositar)\b",
        pregunta,
    ):
        return False
    return bool(
        re.search(
            r"\b(?:que|cuales)\s+(?:son\s+)?(?:los\s+)?"
            r"tipos\s+de\s+residuos\b",
            pregunta,
        )
        or re.search(
            r"\b(?:catalogo|lista(?:do)?|categorias|clasificacion)\b"
            r".*\b(?:residuos?|destinos?)\b",
            pregunta,
        )
        or re.search(
            r"\b(?:residuos?|destinos?)\b.*"
            r"\b(?:catalogo|lista(?:do)?)\b",
            pregunta,
        )
    )


def es_consulta_reparacion_telefonos(pregunta: str) -> bool:
    """Reconoce solicitudes explícitas de reparación, no de reciclaje.

    «Móvil» puede designar un teléfono o un punto limpio itinerante.
    Por eso se exige contexto de reparación de dispositivos y se evita
    interceptar preguntas que mencionen la gestión de residuos.
    """
    if PATRON_CONTEXTO_RESIDUOS.search(pregunta):
        return False
    return bool(
        PATRON_DISPOSITIVO_TELEFONICO.search(pregunta)
        and PATRON_REPARACION.search(pregunta)
        and PATRON_BUSQUEDA_SERVICIO.search(pregunta)
    )


def _es_consulta_horarios_moviles(pregunta: str) -> bool:
    """Excluye la modalidad 24h y preguntas conceptuales."""
    return bool(
        PATRON_MOVIL.search(pregunta)
        and PATRON_HORARIO.search(pregunta)
        and not PATRON_24H.search(pregunta)
    )


def es_horario_movil_sin_ubicacion(pregunta: str) -> bool:
    """Reconoce peticiones exclusivamente de horario sin parada."""
    return bool(
        re.fullmatch(
            r"(?:que horario tiene|a que hora pasa|que dias visita) "
            rf"(?:el |un )?{PATRON_MOVIL.pattern}"
            r"(?: (?:en|de) madrid)?",
            pregunta.strip("¿?¡! "),
        )
    )


def _extraer_dia(pregunta: str) -> str | None:
    """Detecta un único día sin elegir entre fechas distintas."""
    dias = {DIAS[item.group()] for item in PATRON_DIA.finditer(pregunta)}
    return next(iter(dias)) if len(dias) == 1 else None


def _limpiar_ubicacion(texto: str) -> str:
    """Quita conectores y fechas posteriores a una ubicación."""
    texto = re.split(
        r"\s+(?:el|los|un|una|para)\s+(?:" + "|".join(DIAS)
        + r")\b",
        texto,
        maxsplit=1,
    )[0]
    return texto.strip(" .,:;¿?¡!")


def _extraer_ubicacion_movil(pregunta: str) -> tuple[str | None, str | None]:
    """Extrae una calle o distrito explícito sin adivinar paradas."""
    direccion = PATRON_DIRECCION.search(pregunta)
    if direccion:
        calle = _limpiar_ubicacion(direccion.group())
        return None, calle or None

    distrito = re.search(
        r"\bdistrito\s+(?:de\s+)?([^?.,;]+)", pregunta
    )
    if distrito:
        nombre = _limpiar_ubicacion(distrito.group(1))
        if nombre and nombre != "madrid":
            return nombre, None
        return None, None

    movil = PATRON_MOVIL.search(pregunta)
    if movil is None:
        return None, None
    cola = pregunta[movil.end():]
    lugar = re.match(
        r"\s+(?:de|del|en|por)\s+(?:el\s+|la\s+)?"
        r"([^?.,;]+)",
        cola,
    )
    if lugar:
        nombre = _limpiar_ubicacion(lugar.group(1))
        if nombre not in {"", "madrid", "ciudad de madrid"}:
            if not PATRON_DIA.fullmatch(nombre):
                return nombre, None
    return None, None


def _es_fuera_de_dominio_estructurado(
    pregunta: str,
    *,
    es_horario_movil: bool,
) -> bool:
    """
    Detecta consultas fuera de Madrid reutilizando domain.py.

    Evita interpretar una dirección como una ciudad externa
    y respeta los distritos reconocidos de Madrid.
    """
    if _es_otra_ciudad(pregunta):
        return True

    if not es_horario_movil:
        return False

    distrito, direccion = _extraer_ubicacion_movil(pregunta)

    return bool(
        distrito
        and not direccion
        and evaluar_ambito(f"en {distrito}") == "fuera_de_dominio"
    )


def consulta_proximidad(
    pedido: str,
    *,
    exclusiva: bool = False,
) -> bool:
    """Detecta búsquedas espaciales que requieren coordenadas."""
    texto = normalizar_texto(pedido)

    if exclusiva:
        return bool(
            re.fullmatch(
                r"(?:que puntos? limpios? (?:tengo|hay)|"
                r"cual es el punto limpio|"
                r"busca (?:un|el) punto limpio)"
                r"(?: de proximidad)? (?:mas )?"
                rf"{PATRON_PROXIMIDAD.pattern}(?: de mi)?",
                texto.strip("¿?¡! "),
            )
        )

    return bool(PATRON_PROXIMIDAD.search(texto))


def requiere_antecedente(pregunta: str) -> bool:
    """Reconoce reformulaciones que necesitan una referencia previa."""
    texto = normalizar_texto(pregunta).strip("¿?¡! ")

    return bool(
        re.fullmatch(
            r"y si (?:es|son) de \w+(?: \w+)?"
            r"|y (?:hoy|manana|ahora|pasado manana)"
            rf"|y {PATRON_DIA.pattern}"
            rf"|hay (?:uno|una) (?:mas )?{PATRON_PROXIMIDAD.pattern}"
            r"|que hago con (?:esto|eso|aquello)"
            r"|donde (?:tiro|reciclo|deposito) (?:esto|eso|aquello)",
            texto,
        )
    )