# 02. Recuperación filtrada y consultas estructuradas

## 1. Objetivo

Complementar la recuperación semántica mediante filtros sobre metadatos y consultas estructuradas, mejorando la pertinencia de las evidencias sin modificar el contrato público del RAG.

Se conservará ChromaDB y no se incorporarán nuevos motores de búsqueda ni mecanismos de reranking.

Las reglas generales de recuperación se establecen en [01-retrieval.md](01-retrieval.md).

## 2. Responsabilidades

| Archivo | Responsabilidad |
|---|---|
| src/retrieve.py | Recuperación semántica, filtros y contratos públicos |
| src/retrieve_structured.py | Consultas estructuradas y agregaciones |
| src/rag_intents.py | Identificación de intenciones documentales |
| src/rag.py | Selección de estrategias y construcción de respuestas RAG |

Los criterios de interpretación de consultas se establecen en [04-consultas-generales.md](04-consultas-generales.md).

## 3. Recuperación filtrada

### 3.1. Metadatos

| Petición | Filtro |
|---|---|
| Punto limpio fijo | document_type=punto_limpio_fijo |
| Punto limpio móvil | document_type=punto_limpio_movil |
| Punto limpio móvil de 24 horas | document_type=punto_limpio_movil_24h |
| Punto limpio de proximidad | document_type=punto_limpio_proximidad |
| Distrito identificado | district |
| Catálogo de residuos | source=tipos_residuos.csv |

La estructura y procedencia de los metadatos se definen en [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

### 3.2. Aplicación de filtros

Los filtros se aplicarán únicamente cuando las restricciones puedan identificarse de forma inequívoca.

Se conservarán las siguientes reglas:

- Diferenciar modalidades ordinarias y móviles de 24 horas.
- Reconocer distritos mediante los metadatos del índice.
- Conservar las variantes documentadas de un mismo distrito.
- Combinar modalidad y distrito mediante $and cuando corresponda.
- Utilizar $in para variantes equivalentes.
- Evitar filtros restrictivos cuando existan varias interpretaciones incompatibles.

No se deducirán distritos a partir de ubicaciones ambiguas ni se aplicarán restricciones arbitrarias.

### 3.3. Ausencia de coincidencias

Un filtro válido sin registros devolverá una lista vacía sin generar embeddings.

No se eliminarán silenciosamente las restricciones para obtener resultados de otras modalidades, distritos o fuentes incompatibles.

## 4. Recuperación estructurada

Las consultas estructuradas utilizarán operaciones sobre los documentos y metadatos de ChromaDB sin generar embeddings ni ejecutar búsquedas vectoriales.

Las agrupaciones y recuentos no estarán limitados por TOP_K.

Los resultados conservarán la procedencia de los registros utilizados.

Las respuestas finales podrán limitar el número de elementos presentados, indicando su alcance conforme a [04-consultas-generales.md](04-consultas-generales.md).

## 5. Catálogo de residuos

### 5.1. Contratos públicos

Se conservarán las funciones de src/retrieve.py:

```python
def listar_destinos_residuos() -> list[str]:
    ...


def consultar_catalogo_residuos() -> dict:
    ...
```

Su implementación permanecerá delegada a src/retrieve_structured.py.

### 5.2. Fuente

Se utilizará tipos_residuos.csv.

El catálogo representa relaciones documentadas entre residuos y destinos de depósito, no una taxonomía universal ni necesariamente exhaustiva.

### 5.3. Resultado

| Campo | Tipo | Contenido |
|---|---|---|
| source | str | Documento de origen |
| path | str o None | Ruta documental interna |
| total_relaciones | int | Relaciones válidas recuperadas |
| total_destinos | int | Destinos diferentes |
| destinos | list[dict] | Agrupaciones por destino |
| registros_descartados | int | Registros inválidos descartados |
| registros_duplicados | int | Registros duplicados descartados |
| ejemplos_por_destino | int | Máximo de ejemplos por destino |

Cada elemento de destinos conservará:

```python
{
    "destino": str,
    "cantidad": int,
    "ejemplos": list[dict],
}
```

Cada ejemplo contendrá residuo y, cuando esté disponible, source_row.

### 5.4. Agrupaciones y recuentos

Las cantidades se calcularán a partir de los registros válidos.

Se comprobará la coherencia entre el destino indicado en los metadatos y el contenido documental.

Los duplicados se identificarán mediante la combinación de destino normalizado y source_row, cuando el número de fila sea válido.

Una misma numeración de fila podrá pertenecer legítimamente a destinos diferentes.

### 5.5. Ejemplos

Se conservará en config.py:

```python
EJEMPLOS_POR_DESTINO = 2
```

Los ejemplos procederán literalmente de los registros recuperados.

No se modificarán los recuentos para adaptarlos al número de ejemplos presentados.

## 6. Paradas móviles y horarios

### 6.1. Contrato público

```python
def consultar_paradas_moviles(
    *,
    distrito: str | None = None,
    direccion: str | None = None,
    dia: str | None = None,
) -> list[dict]:
    ...
```

Se requerirá al menos distrito o direccion.

El día, por sí solo, no permitirá identificar una parada.

Los criterios proporcionados deberán ser cadenas no vacías y respetar MAX_PREGUNTA_CARACTERES.

### 6.2. Fuente

Se utilizarán los registros correspondientes a:

- source=puntos_limpios_moviles.csv.
- document_type=punto_limpio_movil.

Los puntos limpios móviles de 24 horas quedarán excluidos de esta consulta.

### 6.3. Resultado

Cada registro conservará los campos:

| Campo | Contenido |
|---|---|
| direccion | Dirección de la parada |
| distrito | Distrito municipal |
| dia | Día documentado |
| turno | Turno, cuando esté disponible |
| horario | Horario publicado |
| source | Documento de origen |
| path | Ruta documental interna |
| text | Contenido documental |
| metadata | Metadatos originales |
| source_row | Número de fila, cuando sea válido |

### 6.4. Selección de registros

Se conservarán los mecanismos existentes de:

- Normalización de distritos.
- Comparación de variantes documentadas.
- Coincidencia de direcciones respetando límites de palabras.
- Filtrado por día.
- Comprobación de coherencia entre texto y metadatos.
- Eliminación de duplicados mediante source_row válido.
- Ordenación por distrito, dirección, día y fila.

No se seleccionará arbitrariamente una parada cuando existan varias coincidencias.

Cada horario permanecerá asociado a su registro original.

La interpretación temporal y las solicitudes de aclaración se regulan en [04-consultas-generales.md](04-consultas-generales.md).

## 7. Recuperación geográfica local

Se conservará la función interna de src/retrieve_structured.py:

```python
def consultar_puntos_limpios_locales(
    abrir_coleccion: Callable,
) -> list[dict]:
    ...
```

Recuperará registros georreferenciados correspondientes a las cuatro modalidades de puntos limpios documentadas.

Se comprobarán:

- Correspondencia entre modalidad y fuente.
- Coordenadas numéricas, finitas y dentro de rango.
- Presencia de dirección y distrito.
- Coherencia de los metadatos.

Los registros conservarán fuente=corpus_local y documento_origen.

Esta función no realizará búsquedas vectoriales, calculará distancias ni determinará compatibilidades.

Las condiciones de activación del respaldo y su contrato geográfico se establecen en [05-tools.md](05-tools.md).

## 8. Validación y errores

Las reglas generales se establecen en [01-retrieval.md](01-retrieval.md).

En las consultas estructuradas deberá comprobarse adicionalmente:

- Correspondencia entre documentos y metadatos.
- Coherencia de las fuentes.
- Validez de los registros utilizados.
- Correspondencia entre campos documentales y metadatos.
- Consistencia de las rutas de procedencia del catálogo.

Se conservarán los mecanismos de descarte y contabilización de registros inválidos.

Cuando existan descartes que afecten a la completitud del resultado, deberá comunicarse la limitación correspondiente.

La ausencia legítima de coincidencias deberá distinguirse de un conjunto de registros inutilizables por problemas de integridad.

Los fallos de ChromaDB no se transformarán en resultados vacíos.

## 9. Criterios de aceptación

- Los filtros respetan las restricciones identificadas.
- Las modalidades permanecen diferenciadas.
- Los filtros sin coincidencias no activan búsquedas incompatibles.
- Las consultas estructuradas no requieren embeddings.
- Los recuentos se calculan sobre registros válidos.
- Los duplicados se identifican correctamente.
- Los ejemplos conservan su contenido original.
- Los horarios permanecen asociados a sus paradas.
- El respaldo local conserva su procedencia.
- Los fallos técnicos se distinguen de los resultados legítimamente vacíos.
- Se conservan los contratos públicos y el funcionamiento independiente del RAG.

La estrategia de pruebas y evaluación se establece en [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).