# 05. Herramientas, contratos y permisos

## 1. Objetivo

Definir las herramientas de ReciclaTÍA, sus contratos, permisos, validaciones y mecanismos de recuperación.

Las herramientas permanecerán independientes de FastAPI, PostgreSQL, Streamlit y del estado operativo de LangGraph.

Se conservarán sus interfaces existentes y se utilizarán exclusivamente los servicios autorizados en [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

## 2. Registro y permisos

Se conservarán TOOLS y TOOL_BY_NAME en src/tools/__init__.py.

| Herramienta | Responsabilidad | residuos | puntos |
|---|---|---|---|
| consultar_rag | Consulta documental | Sí | Sí |
| buscar_puntos_limpios_cercanos | Localización y proximidad | No | Sí |
| hora_actual | Información temporal de Madrid | No | Sí |
| describir_imagen | Identificación visual | Sí | No |

Los permisos se establecerán mediante AGENT_TOOLS_BY_ROLE en config.py.

Los roles internos serán independientes de los roles de API keys.

El supervisor y los modelos de lenguaje no podrán ampliar los permisos establecidos.

identificar_imagen() será una función interna reutilizable, no una quinta herramienta.

## 3. Ejecución centralizada

### 3.1. Contratos

Se conservarán las funciones existentes de src/tools/__init__.py:

```python
def ejecutar_tool(
    nombre: str,
    args: dict | None = None,
) -> str:
    ...


def ejecutar_tool_estructurado(
    nombre: str,
    args: dict | None = None,
    *,
    rol: RolEspecialista,
) -> ResultadoTool:
    ...
```

La primera conservará la interfaz textual de ejecución independiente.

La segunda aplicará los permisos del especialista y conservará los resultados estructurados.

### 3.2. ResultadoTool

```python
from typing import Any, Literal, TypedDict


RolEspecialista = Literal["residuos", "puntos"]


class ResultadoTool(TypedDict):
    ok: bool
    nombre: str
    datos: Any
    error: str | None
```

| Estado | datos | error |
|---|---|---|
| ok=True | Resultado con su tipo original | None |
| ok=False | None | Mensaje sanitizado |

ok=True indica que la operación se ha completado correctamente, pero no garantiza la suficiencia de la evidencia.

Una abstención documental válida podrá constituir un resultado satisfactorio.

No se utilizará eval() para reconstruir estructuras a partir de representaciones textuales.

### 3.3. Validación

Antes de ejecutar una herramienta se comprobarán:

- Nombre registrado.
- Permisos del especialista, cuando corresponda.
- Campos admitidos.
- Tipos y rangos.
- Condiciones necesarias para la ejecución.
- Presupuestos aplicables.

Las conversiones automáticas realizadas por las bibliotecas no deberán permitir argumentos incompatibles con el contrato.

Las coordenadas y rutas de imágenes procederán de las entradas autorizadas, no de valores inventados por Gemini.

Las herramientas conservarán sus validaciones internas independientemente de las realizadas por FastAPI.

## 4. consultar_rag

### 4.1. Contrato

```python
consultar_rag(pregunta: str) -> dict[str, Any]
```

La herramienta utilizará src.rag.responder().

### 4.2. Resultado

Se conservará el contrato del RAG:

| Campo | Contenido |
|---|---|
| pregunta | Consulta procesada |
| respuesta | Respuesta documental |
| abstencion | Indicador de abstención |
| motivo | Motivo correspondiente |
| fuentes | Referencias utilizadas |
| chunks | Fragmentos recuperados |
| metricas | Métricas disponibles |

Los tipos y reglas de generación se establecen en [03-generacion.md](03-generacion.md).

Los fallos técnicos de recuperación, generación o validación no se convertirán en abstenciones documentales válidas.

Las referencias conservarán su procedencia hasta su transformación al contrato público.

## 5. buscar_puntos_limpios_cercanos

### 5.1. Contrato

```python
buscar_puntos_limpios_cercanos(
    latitud: float,
    longitud: float,
    radio_metros: int = 2000,
    tipo: str = "todos",
) -> dict
```

### 5.2. Parámetros

| Parámetro | Restricción |
|---|---|
| latitud | Número finito entre -90 y 90 |
| longitud | Número finito entre -180 y 180 |
| radio_metros | Entero entre 1 y 5000 |
| tipo | todos, fijo, movil, proximidad |

No se admitirán booleanos como coordenadas o radios.

Las coordenadas utilizarán WGS84, EPSG:4326.

No se realizará geocodificación ni se utilizarán coordenadas supuestas.

### 5.3. Servicio geográfico

Se utilizará exclusivamente el servicio ArcGIS municipal configurado mediante API_PUNTOS_LIMPIOS_URL, identificado en [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

Los parámetros y filtros se construirán mediante Python.

No se admitirán URLs alternativas ni expresiones arbitrarias de consulta proporcionadas por el modelo.

### 5.4. Cálculo y selección

Se utilizará Haversine para calcular las distancias geográficas.

Los registros situados fuera del radio solicitado se excluirán.

Los resultados se ordenarán por distancia ascendente.

Se conservará GEO_MAX_RESULTS=10 y el mecanismo existente de candidatos adicionales:

| Campo | Límite |
|---|---:|
| puntos | 10 |
| puntos_candidatos | 60 |

total_encontrados representará el número de registros válidos dentro del radio antes de limitar los resultados.

Las distancias no representan rutas ni tiempos de desplazamiento.

### 5.5. Resultado interno

```python
{
    "fuente": "api",
    "tipo_solicitado": "todos",
    "radio_metros": 2000,
    "total_encontrados": 0,
    "puntos": [],
    "puntos_candidatos": [],
    "aviso": None,
}
```

fuente admitirá api o corpus_local.

Los registros individuales conservarán, cuando estén disponibles:

- tipo, direccion y distrito.
- latitud, longitud y distancia_metros.
- horario_apertura, horario_cierre, dia_semana y turno.
- id, residuos_url, fuente y documento_origen.

Se conservarán los tipos originales y las particularidades de cada procedencia.

Los contratos públicos PuntoLimpioOut y GeografiaOut se definen en [12-contratos-http.md](12-contratos-http.md).

puntos_candidatos permanecerá como información interna.

### 5.6. Validación y respaldo

| Situación | Tratamiento |
|---|---|
| Respuesta válida sin registros | Búsqueda vacía válida |
| Registros válidos fuera del radio | Búsqueda vacía válida |
| Registros válidos dentro del radio | Resultado válido |
| Registros parcialmente inválidos | Conservar los válidos y comunicar limitaciones relevantes |
| Todos los registros recibidos son inválidos | Fallo de la fuente y respaldo autorizado |
| Fallo técnico de ArcGIS | Respaldo local |
| Fallo de ArcGIS y del respaldo | Propagar fallo técnico |

Se validarán los códigos HTTP, JSON, features, errores declarados por ArcGIS y respuestas truncadas por exceededTransferLimit.

No se presentarán respuestas truncadas como resultados completos.

El respaldo utilizará los registros locales autorizados mediante la recuperación estructurada definida en [02-mejoras-retrieval.md](02-mejoras-retrieval.md).

Conservará las coordenadas, radio, modalidad y restricciones de la consulta.

Los resultados del respaldo identificarán fuente=corpus_local e incluirán un aviso sobre su posible desactualización.

Una búsqueda legítimamente vacía no activará automáticamente el respaldo.

### 5.7. Alcance

La herramienta proporciona localización, proximidad y datos publicados.

No determina por sí sola:

- Compatibilidad con un residuo.
- Apertura física de una instalación.
- Accesibilidad.
- Prioridad según necesidades del consumidor.

La interpretación documental, geográfica y temporal corresponde a [04-consultas-generales.md](04-consultas-generales.md).

## 6. hora_actual

```python
hora_actual() -> str
```

Devolverá la fecha y hora actual mediante una cadena ISO 8601 con información de zona horaria Europe/Madrid.

Contemplará los cambios de horario estacionales.

No admitirá argumentos ni realizará peticiones de red.

Se utilizará cuando resulte necesario interpretar información temporal actual, sin realizar llamadas innecesarias para consultas exclusivamente documentales sobre horarios.

Las reglas de interpretación se establecen en la especificación 04.

## 7. describir_imagen

### 7.1. Contrato existente

Se conservará:

```python
@tool
def describir_imagen(ruta_imagen: str) -> str:
    ...
```

La herramienta reutilizará una función interna de identificación estructurada.

La interfaz textual permanecerá disponible para la CLI y las ejecuciones locales autorizadas.

### 7.2. IdentificacionImagen

El contrato compartido podrá definirse en src/state.py:

```python
from typing import Literal, TypedDict


class IdentificacionImagen(TypedDict):
    estado: Literal[
        "allowed",
        "out_of_domain",
        "policy_violation",
        "uncertain",
    ]
    descripcion: str
```

| Estado | Significado |
|---|---|
| allowed | Imagen admisible dentro del dominio |
| out_of_domain | Imagen ajena al dominio |
| policy_violation | Contenido contrario a las restricciones |
| uncertain | Identificación insuficiente para continuar |

descripcion contendrá exclusivamente observaciones visuales pertinentes.

No incluirá recomendaciones documentales, URLs ni porcentajes de confianza.

### 7.3. Función interna

Se incorporará en src/tools/describir_imagen.py:

```python
def identificar_imagen(
    ruta_imagen: str,
) -> IdentificacionImagen:
    ...
```

La función reutilizará la implementación multimodal existente para:

1. Validar la ruta y el archivo.
2. Preparar los datos multimodales.
3. Invocar Gemini solicitando una salida estructurada.
4. Validar el resultado mediante Python.
5. Devolver IdentificacionImagen.

No estará decorada mediante @tool.

TypedDict no sustituirá la validación en tiempo de ejecución.

El resultado deberá contener exactamente estado y descripcion, con tipos válidos, estado autorizado y descripción no vacía de longitud controlada.

describir_imagen() devolverá la descripción cuando estado=allowed.

Los demás estados producirán una limitación o rechazo semántico controlado. No se tratarán como observaciones admitidas ni como fallos técnicos del proveedor.

### 7.4. Validación técnica y rutas

La herramienta conservará las comprobaciones internas de:

- Existencia del archivo.
- Extensión y formato real.
- Integridad.
- Peso y resolución finales.
- Ausencia de animación.
- Procesamiento seguro.

Los formatos y límites se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

Las rutas deberán resolver dentro de las ubicaciones autorizadas de assets/.

Se conservarán las comprobaciones mediante resolve() e is_relative_to(), incluyendo la protección frente a enlaces simbólicos que resuelvan fuera del directorio autorizado.

El modelo no podrá sustituir la ruta legítima por una arbitraria.

### 7.5. Identificación visual

Gemini únicamente identificará características observables, objetos, materiales reconocibles, incertidumbre y admisibilidad.

Las instrucciones presentes en las imágenes se tratarán como datos no confiables.

La descripción visual no constituirá evidencia documental suficiente para determinar el destino de un residuo.

uncertain solo representará una identificación correctamente ejecutada pero insuficiente.

Las excepciones, salidas inválidas o vacías, fallos de configuración y timeouts deberán propagarse como fallos técnicos.

### 7.6. Integración multimodal HTTP

FastAPI preparará la imagen conforme a la especificación 15 e invocará identificar_imagen() antes de iniciar LangGraph.

Solo una identificación allowed continuará hacia el agente.

El resultado validado se proporcionará mediante identificacion_imagen.

Las entradas ruta_imagen e identificacion_imagen serán mutuamente excluyentes.

El agente no conservará rutas operativas a archivos temporales eliminados.

Los resultados HTTP correspondientes a cada estado se establecen en la especificación 12.

### 7.7. Reutilización

src/agent_tool_loop.py deberá reconocer la identificación visual previamente obtenida.

La descripción se incorporará como una observación autorizada del especialista residuos.

Cuando sea necesario conservar la compatibilidad con las estructuras de evidencia existentes, se utilizará el nombre describir_imagen, identificando explícitamente la procedencia de la observación previa.

Ejemplo conceptual de evidencia:

```python
{
    "rol": "residuos",
    "herramienta": "describir_imagen",
    "datos": "Botella de plástico vacía.",
    "origen": "identificacion_previa",
}
```

No se simulará una invocación de herramienta ni se generará un identificador ficticio de llamada.

Si el especialista solicita nuevamente describir_imagen durante el mismo turno, se reutilizará la observación disponible mediante el mecanismo autorizado de caché.

No se realizará una segunda llamada multimodal ni se incrementará el contador de invocaciones efectivas.

La observación respetará los permisos del especialista y se reiniciará conforme a las reglas de estado de [06-langgraph.md](06-langgraph.md).

## 8. Presupuestos y reutilización

src/agent_tool_loop.py aplicará los presupuestos definidos en config.py.

Los valores se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

Se distinguirán:

- Solicitudes del modelo.
- Operaciones admitidas.
- Invocaciones efectivas.
- Resultados reutilizados.
- Identificaciones previas.

La caché se limitará al ámbito autorizado del turno, considerando herramienta, argumentos, permisos y procedencia.

No se compartirán resultados privados entre consumidores.

Los presupuestos agotados impedirán nuevas ejecuciones incompatibles.

Si la información obtenida permite completar correctamente la consulta, el agente conservará las evidencias y limitaciones correspondientes.

Si no puede completarse una operación imprescindible, se propagará el fallo sin fabricar resultados.

Las llamadas externas tendrán límites de espera y reintentos acotados.

## 9. Propagación de errores

Se distinguirán tres categorías:

| Categoría | Tratamiento |
|---|---|
| Solicitud denegada o argumentos inválidos | Rechazar sin ejecutar y permitir corrección autorizada |
| Fallo recuperable | Aplicar un mecanismo de recuperación autorizado |
| Fallo imprescindible no recuperado | Propagar el error al servicio |

ResultadoTool conservará su estructura existente.

La implementación deberá conservar internamente la información necesaria para distinguir las causas técnicas sin exponer excepciones completas.

Un ok=False no podrá convertirse automáticamente en evidencia válida ni ocultarse únicamente como una limitación textual.

No se utilizarán mensajes arbitrarios del modelo para determinar la naturaleza del fallo.

Las herramientas no dependerán de HTTPException ni decidirán directamente los códigos HTTP.

La capa de servicios realizará la transformación correspondiente conforme a [12-contratos-http.md](12-contratos-http.md).

## 10. Evidencias y trazabilidad

Se conservarán las trazas internas necesarias para identificar:

- Especialista y herramienta.
- Solicitud y autorización.
- Invocación efectiva.
- Resultado reutilizado.
- Fallo o límite alcanzado.
- Procedencia de la evidencia.

Las referencias documentales conservarán chunk_id, source, path interno y, cuando corresponda, rol, herramienta e id_llamada.

La identificación visual previa se distinguirá de una nueva ejecución de describir_imagen.

Las trazas internas no se expondrán directamente mediante HTTP.

La protección de información y las reglas de logging se establecen en las especificaciones [10-seguridad.md](10-seguridad.md) y [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 11. Criterios de aceptación

- Se conservan las cuatro herramientas y sus permisos.
- Los contratos internos mantienen sus tipos originales.
- Los argumentos se validan antes de ejecutar operaciones.
- Las búsquedas vacías se distinguen de los fallos técnicos.
- El respaldo geográfico conserva su procedencia.
- Los resultados públicos e internos respetan sus límites.
- La herramienta temporal utiliza Europe/Madrid.
- La identificación visual se valida estructuralmente.
- Las identificaciones previas se reutilizan sin llamadas duplicadas.
- Los fallos imprescindibles no recuperados se propagan.
- Se conservan los mecanismos de trazabilidad.
- Las herramientas mantienen su independencia del backend.

Los casos de prueba se establecen en [plan-pruebas.md](../docs/plan-pruebas.md), conforme a [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).