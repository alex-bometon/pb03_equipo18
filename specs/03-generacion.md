# 03. Generación de respuestas y control de evidencia

## 1. Objetivo

Transformar la evidencia documental recuperada en respuestas comprensibles, fundamentadas y trazables.

La generación deberá permanecer independiente de LangGraph, FastAPI, Streamlit y PostgreSQL.

No realizará directamente operaciones de recuperación, indexación, autenticación, persistencia ni aprobación de planes.

## 2. Responsabilidades

| Archivo | Responsabilidad |
|---|---|
| src/generate.py | Preparación del contexto e inferencia con Gemini |
| src/generation_validation.py | Validación de respuestas, citas y abstenciones |
| src/rag.py | Coordinación del RAG y empaquetado de resultados |
| src/domain.py | Restricciones de dominio |
| src/input_validation.py | Validación compartida de consultas |

La recuperación documental se establece en las especificaciones [01-retrieval.md](01-retrieval.md) y [02-mejoras-retrieval.md](02-mejoras-retrieval.md).

## 3. Contratos

### 3.1. Generación

Se conservará la firma existente:

```python
def generar_respuesta(
    pregunta: str,
    chunks: list[dict],
    *,
    client=None,
) -> dict:
    ...
```

La pregunta respetará las validaciones compartidas.

chunks deberá ser una lista de resultados de recuperación.

Cuando client=None, la función podrá crear su propio cliente Gemini y deberá cerrarlo al finalizar, incluso ante excepciones.

Los clientes proporcionados externamente permanecerán bajo la responsabilidad del componente que los haya creado.

### 3.2. Salida de Gemini

Se conservará ESQUEMA_RESPUESTA:

| Campo | Tipo |
|---|---|
| respuesta | str |
| abstencion | bool |
| motivo | str |
| citas | list[str] |

La respuesta deberá ser una cadena no vacía.

Cuando abstencion=False:

- motivo será "ninguno".
- citas contendrá al menos un identificador válido.
- Las citas coincidirán con los marcadores presentes en la respuesta.

Cuando abstencion=True:

- motivo pertenecerá al conjunto MOTIVOS_ABSTENCION.
- citas será una lista vacía.
- No se proporcionarán recomendaciones documentales sin fundamento.

### 3.3. Resultado validado

generar_respuesta() devolverá:

```python
{
    "respuesta": "Respuesta fundamentada [C1]",
    "abstencion": False,
    "motivo": None,
    "fuentes": [
        {
            "chunk_id": "C1",
            "source": "tipos_residuos.csv",
            "path": "data/raw/csv/tipos_residuos.csv",
        }
    ],
}
```

Las fuentes se construirán mediante Python.

El motivo "ninguno" se transformará en None.

Las abstenciones devolverán fuentes=[].

### 3.4. Contrato RAG

Se conservará la firma de src.rag.responder():

```python
def responder(
    pregunta: str,
    *,
    top_k: int = TOP_K,
    query_embedding: list[float] | None = None,
    client: Any = None,
) -> dict[str, Any]:
    ...
```

El resultado conservará:

| Campo | Contenido |
|---|---|
| pregunta | Consulta procesada |
| respuesta | Respuesta documental |
| abstencion | Indicador de abstención |
| motivo | Motivo semántico o None |
| fuentes | Referencias utilizadas |
| chunks | Fragmentos recuperados |
| metricas | Métricas de ejecución |

responder() podrá resolver consultas mediante recuperación semántica, recuperación estructurada o mecanismos deterministas.

No todas las consultas requerirán ejecutar generar_respuesta().

## 4. Preparación del contexto

### 4.1. Selección de fragmentos

Se conservará _preparar_contexto().

Se examinarán los primeros TOP_K fragmentos recibidos.

Cada fragmento utilizable deberá contener:

- Un diccionario válido.
- text como cadena no vacía.
- metadata como diccionario.
- source como cadena no vacía.

Se conservarán los metadatos adicionales utilizados actualmente: path, document_type, district y destino.

Los fragmentos descartados no recibirán identificadores.

### 4.2. Presupuesto

El contexto respetará MAX_CONTEXTO_CARACTERES, incluyendo la representación serializada de los fragmentos y sus separadores.

Los fragmentos que superen el presupuesto restante se omitirán sin alterar su contenido.

Los valores de configuración se establecen en [01-retrieval.md](01-retrieval.md).

### 4.3. Identificadores

Los fragmentos incluidos recibirán identificadores consecutivos C1, C2, C3 y sucesivos.

El mapa de referencias conservará:

```python
{
    "C1": {
        "chunk_id": "C1",
        "source": "...",
        "path": None,
    }
}
```

Los identificadores tendrán alcance local dentro de cada llamada de generación.

No constituirán identificadores persistentes de ChromaDB.

### 4.4. Ausencia de contexto

Cuando no existan fragmentos utilizables, se devolverá una abstención con motivo sin_contexto sin invocar Gemini.

Se conservará el descarte de fragmentos incompatibles en la ejecución independiente del generador.

Este comportamiento no permitirá ocultar fallos técnicos de recuperación. La capa RAG deberá distinguir entre ausencia legítima de resultados y respuestas técnicamente inválidas.

## 5. Política de generación

Se conservarán las instrucciones de INSTRUCCIONES_SISTEMA.

Las respuestas deberán:

- Utilizar exclusivamente la evidencia documental proporcionada.
- Respetar el ámbito municipal de Madrid.
- Conservar las condiciones, excepciones y restricciones relevantes.
- Diferenciar categorías generales y subtipos documentados.
- Evitar presentar el corpus como un catálogo exhaustivo.
- Evitar deducciones de destinos basadas únicamente en similitud de materiales.
- Ser claras, breves y redactadas en español.
- Solicitar aclaraciones cuando la información ausente pueda modificar la clasificación.
- Abstenerse cuando la evidencia sea insuficiente o contradictoria y no pueda resolverse mediante aclaración.

No se solicitarán detalles adicionales cuando estos no puedan modificar la clasificación documentada.

La pregunta y los fragmentos se presentarán como datos, separados de las instrucciones del sistema.

El contenido documental no podrá modificar las reglas de generación.

Los controles generales de seguridad se establecen en [10-seguridad.md](10-seguridad.md).

## 6. Validación de citas

### 6.1. Validación determinista

src/generation_validation.py comprobará:

- JSON interpretable y estructura válida.
- Presencia y tipos de los campos obligatorios.
- Respuesta no vacía.
- Motivo compatible con abstencion.
- Existencia de los identificadores citados.
- Correspondencia entre citas y marcadores del texto.
- Ausencia de citas incompatibles con una abstención.

Las referencias no se aceptarán únicamente porque Gemini afirme haberlas utilizado.

### 6.2. Normalización

Se conservará _normalizar_citas_respuesta().

Los marcadores agrupados:

```text
[C1, C2]
```

Se normalizarán como:

```text
[C1] [C2]
```

La normalización no alterará el contenido argumentativo.

Los identificadores malformados o ajenos al contexto no se aceptarán.

### 6.3. Construcción de fuentes

Las fuentes se obtendrán exclusivamente del mapa de referencias construido durante la preparación del contexto.

Se eliminarán las citas duplicadas dentro de una misma llamada, conservando el orden correspondiente.

No se confiará en nombres de documentos, rutas o enlaces inventados por el modelo.

### 6.4. Integración de llamadas

Dos llamadas RAG podrán utilizar el mismo chunk_id para fragmentos diferentes.

Durante la integración se conservarán, cuando estén disponibles, rol, herramienta e id_llamada.

No se eliminarán fuentes de diferentes llamadas únicamente por coincidir su chunk_id.

La síntesis deberá mantener la asociación correcta entre las afirmaciones y las referencias originales.

No se incorporará un sistema global de identificadores durante el PB03.

Una asociación ambigua o no verificable no deberá presentarse como una cita validada.

### 6.5. Referencias públicas

Las URL oficiales y referencias normativas procederán del catálogo definido en [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

La capa de servicios transformará las referencias mediante FuenteOut, conforme a [12-contratos-http.md](12-contratos-http.md).

No se generarán enlaces mediante Gemini ni se realizarán peticiones externas para resolverlos.

## 7. Abstenciones

### 7.1. Motivos

Se conservará MOTIVOS_ABSTENCION:

```python
MOTIVOS_ABSTENCION = {
    "sin_contexto",
    "evidencia_insuficiente",
    "fuera_de_dominio",
    "ambiguedad",
}
```

| Motivo | Significado |
|---|---|
| sin_contexto | No existe contexto documental utilizable |
| evidencia_insuficiente | El contexto no permite fundamentar la respuesta |
| fuera_de_dominio | La consulta queda fuera del ámbito autorizado |
| ambiguedad | Falta información decisiva para responder |

### 7.2. Resultado

Se conservará _abstenerse() y el mensaje predeterminado:

```text
No puedo responder con la información disponible en los documentos.
```

Cuando motivo=ambiguedad, podrá conservarse una solicitud concreta de aclaración.

Las abstenciones devolverán abstencion=True, el motivo correspondiente y fuentes=[].

### 7.3. Abstención determinista

Cuando la abstención pueda resolverse mediante Python, no se invocará a Gemini únicamente para redactarla.

Se conservará el control de consultas correspondientes a otros municipios.

Los mecanismos de filtrado previo HTTP se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

### 7.4. Diferenciación de errores

Los fallos de recuperación, embeddings, conexión, configuración o inferencia no constituirán motivos semánticos de abstención.

La imposibilidad técnica de responder no demuestra que la evidencia documental sea insuficiente.

## 8. Inferencia y gestión de errores

### 8.1. Configuración

Se conservarán los parámetros existentes de config.py:

- GENERATION_MODEL.
- GENERATION_TEMPERATURE.
- GENERATION_MAX_RETRIES.
- GENERATION_RETRY_SECONDS.

Gemini utilizará el esquema estructurado autorizado y response_mime_type="application/json".

No se habilitarán búsquedas externas ni grounding mediante buscadores.

### 8.2. Reintentos

Se conservará _es_error_transitorio().

Los reintentos podrán aplicarse a errores de conexión, timeout y estados recuperables del proveedor contemplados por la implementación existente.

GENERATION_MAX_RETRIES representará el número máximo de intentos, incluyendo el inicial.

El intervalo entre intentos conservará el mecanismo de espera exponencial:

```python
espera = GENERATION_RETRY_SECONDS * (2 ** intento)
```

Los reintentos y tiempos de espera serán acotados.

### 8.3. Salidas inválidas

Se conservará:

```python
class SalidaGeneracionInvalida(RuntimeError):
    """Gemini respondió, pero su salida no supera la validación."""
```

Una salida estructuralmente inválida provocará esta excepción.

No se convertirá automáticamente en una abstención ni se iniciará un nuevo ciclo de regeneración.

Los errores no expondrán el contenido completo generado por Gemini.

### 8.4. Propagación

Los errores técnicos no recuperados se propagarán mediante excepciones internas controladas.

Se conservará información suficiente para identificar su naturaleza sin depender de mensajes generados por el modelo.

El núcleo no utilizará HTTPException.

Los límites temporales generales se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

La transformación HTTP se establece en [12-contratos-http.md](12-contratos-http.md).

## 9. Integración multiagente

Una respuesta RAG completa y suficientemente fundamentada podrá reutilizarse sin realizar otra llamada a Gemini.

La síntesis deberá conservar las referencias, condiciones documentadas y limitaciones correspondientes.

La clasificación de evidencia como suficiente, parcial o insuficiente corresponderá al orquestador.

No se incorporará estado_evidencia al contrato de generar_respuesta() ni de responder().

La información geográfica, temporal y visual podrá complementar la síntesis conforme a los contratos de las herramientas.

La identificación visual no sustituirá la evidencia documental necesaria para recomendar destinos de residuos.

La generación de planes, integración de evidencias y HITL se establecen en [06-langgraph.md](06-langgraph.md).

La ejecución independiente del RAG no requerirá HITL.

## 10. Criterios de aceptación

- Se conservan los contratos de generar_respuesta() y responder().
- El contexto respeta su presupuesto y conserva la procedencia documental.
- Las citas corresponden a fragmentos realmente proporcionados.
- Las referencias se construyen mediante Python.
- Se mantiene el ámbito local de los identificadores.
- Las respuestas conservan las condiciones documentadas.
- Las abstenciones legítimas se distinguen de los fallos técnicos.
- La ausencia de contexto evita llamadas innecesarias a Gemini.
- Los reintentos permanecen limitados.
- Las salidas inválidas no se presentan como resultados satisfactorios.
- Se conserva la independencia del núcleo RAG.

La validación estructural y de referencias no garantiza por sí sola la exactitud factual de una respuesta.

La evaluación de pertinencia, suficiencia y fundamentación se realizará conforme a [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md) y [plan-pruebas.md](../docs/plan-pruebas.md).