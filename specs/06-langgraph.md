# 06. LangGraph, estado y aprobación humana

## 1. Objetivo

Definir la orquestación multiagente de ReciclaTÍA, incluyendo el enrutamiento, la gestión del estado, la integración de evidencias y la supervisión humana.

Se conservará la arquitectura desarrollada durante el PB02, incluyendo el HITL obligatorio.

El orquestador permanecerá independiente de FastAPI, Streamlit, PostgreSQL y los mecanismos de autenticación y cuotas comerciales.

## 2. Arquitectura del grafo

### 2.1. Nodos

| Nodo | Responsabilidad |
|---|---|
| supervisor | Seleccionar operaciones y controlar el progreso |
| residuos | Obtener evidencia documental y visual |
| puntos | Obtener información geográfica, documental y temporal |
| sintetizar | Integrar evidencias y generar respuesta y plan |
| aplicar | Registrar la aprobación o rechazo |

### 2.2. Topología

```mermaid
flowchart TD
    START([START]) --> S[supervisor]

    S -->|residuos| R[residuos]
    S -->|puntos| P[puntos]
    S -->|sintetizar| Y[sintetizar]

    R --> S
    P --> S
    Y --> S

    S -->|FINISH| H{{Interrupcion HITL}}
    H -->|Decision validada| A[aplicar]

    A --> END([END])
```

Se conservarán los cinco nodos y las aristas existentes.

HITL constituye una interrupción estática, no un nodo adicional.

FINISH continuará conduciendo a aplicar. No se incorporarán rutas satisfactorias que eviten HITL.

### 2.3. Construcción

src/graph.py conservará:

- build_graph(): construcción de un grafo independiente mediante EstadoGrafo.
- get_app(): instancia compilada compartida mediante caché.
- config_hilo(): configuración del thread_id y recursion_limit.
- hay_hitl_pendiente(): comprobación de la interrupción real.

La compilación utilizará:

```python
grafo.compile(
    checkpointer=MemorySaver(),
    interrupt_before=["aplicar"],
)
```

No se construirá un grafo nuevo por cada petición HTTP.

## 3. Responsabilidades

| Archivo | Responsabilidad |
|---|---|
| src/state.py | Contratos y gestión del estado |
| src/agent_routing.py | Enrutamiento y fallback |
| src/agent_prompts.py | Instrucciones del supervisor y especialistas |
| src/agent_tool_loop.py | Ejecución de herramientas |
| src/nodes.py | Implementación de los nodos |
| src/agent_schedule.py | Interpretación temporal |
| src/agent_resultado.py | Integración determinista |
| src/graph.py | Construcción y configuración del grafo |
| src/agent.py | Orquestación de consultas y aprobaciones |
| src/cli_agent.py | Ejecución interactiva independiente |

La coordinación HTTP corresponderá a api/service.py.

## 4. Contratos del orquestador

### 4.1. Procesamiento de consultas

```python
def procesar_turno(
    estado: EstadoProducto,
    mensaje: str,
    thread_id: str,
    *,
    max_steps: int | None = None,
    ubicacion: Ubicacion | None = None,
    ruta_imagen: str | None = None,
    identificacion_imagen: IdentificacionImagen | None = None,
) -> EstadoProducto:
    ...
```

estado será una representación interna autorizada.

ruta_imagen e identificacion_imagen serán mutuamente excluyentes.

La identificación proporcionada deberá superar la validación definida en [05-tools.md](05-tools.md) y tener estado=allowed.

Una ejecución satisfactoria finalizará en una interrupción HITL válida.

La aprobación automática no será responsabilidad de procesar_turno().

### 4.2. Resolución de aprobaciones

```python
def aprobar_plan(
    thread_id: str,
    aprobado: bool,
    *,
    approval_id: str,
) -> EstadoProducto:
    ...
```

La función obtendrá el estado directamente del checkpoint.

No recibirá una copia de EstadoProducto ni un plan proporcionado por el cliente.

aprobado deberá ser un booleano estricto.

### 4.3. Identificadores

```python
def nuevo_thread_id() -> str:
    ...
```

Se conservará la generación mediante uuid4().

En el flujo HTTP se utilizará el mismo identificador en LangGraph y PostgreSQL, conforme a [13-persistencia.md](13-persistencia.md).

## 5. Contratos de estado

### 5.1. Tipos compartidos

Se conservarán los tipos existentes de src/state.py:

```python
class Ubicacion(TypedDict):
    latitud: float
    longitud: float


EstadoEvidencia = Literal[
    "suficiente",
    "parcial",
    "insuficiente",
]


class EventoLog(TypedDict):
    nodo: str
    accion: str
    detalle: str


class TrazaTool(TypedDict, total=False):
    nodo: str
    paso: int
    tool: str
    status: str
    fuente: str | None
    preview: str


class RegistroTurno(TypedDict):
    pedido: str
    respuesta: str
    plan: list[str]
    aprobado: bool
```

RegistroTurno representará exclusivamente turnos resueltos.

El campo aprobado conservará su tipo bool.

IdentificacionImagen se incorporará como tipo compartido conforme al contrato definido en la especificación 05.

### 5.2. EstadoGrafo

Se conservarán todos los campos actuales y se incorporarán identificacion_imagen y approval_id.

| Campo | Tipo |
|---|---|
| pedido | str |
| pedido_original | str |
| contexto_revision | str |
| ubicacion | Ubicacion o None |
| ruta_imagen | str o None |
| identificacion_imagen | IdentificacionImagen o None |
| necesita_residuos | bool |
| necesita_puntos | bool |
| residuos_completado | bool |
| puntos_completado | bool |
| siguiente | str |
| iteracion | int |
| notas_residuos | str |
| notas_puntos | str |
| evidencias | list[dict[str, Any]] |
| fuentes | list[dict[str, Any]] |
| abstencion | bool |
| motivo | str o None |
| limitaciones | list[str] |
| estado_evidencia | EstadoEvidencia |
| respuesta | str |
| plan | list[str] |
| plan_aprobado | bool o None |
| pendiente_hitl | bool |
| approval_id | str o None |
| done | bool |
| error | str o None |
| max_steps | int |
| max_turns | int |
| turnos_consumidos | int |
| tool_calls_turno | int |
| log | list[EventoLog] |
| traza_tools | list[TrazaTool] |
| historial_turnos | list[RegistroTurno] |

Los dos campos nuevos tendrán valor inicial None.

pedido_original conservará la consulta original, independientemente de las reformulaciones internas.

### 5.3. EstadoProducto

```python
class EstadoProducto(EstadoGrafo):
    thread_id: str
    traza: list[EventoLog]
```

Este contrato permanecerá disponible para el orquestador, la CLI y la capa interna de servicios.

No constituirá el modelo HTTP público.

### 5.4. Gestión de estructuras

Las estructuras mutables serán independientes entre conversaciones y checkpoints.

Se conservará la política de sobrescritura de listas.

No se introducirán reducers de concatenación indiscriminada.

Las transformaciones utilizarán copias independientes cuando corresponda.

## 6. Ciclo de vida del estado

### 6.1. Funciones existentes

| Función | Responsabilidad |
|---|---|
| crear_estado_grafo() | Inicializar los canales del grafo |
| crear_estado_producto() | Inicializar el estado del orquestador |
| preparar_nuevo_turno() | Reiniciar los campos transitorios |
| registrar_turno() | Incorporar un turno resuelto al historial |
| estado_desde_grafo() | Adaptar el checkpoint a EstadoProducto |
| _estado_actual() | Recuperar el estado operativo real |

Las funciones de creación, preparación y transformación incorporarán los nuevos campos.

_estado_actual() deberá poder recuperar el estado necesario para aprobar_plan() sin recibir un estado del cliente.

### 6.2. Inicio de una conversación

El estado inicial conservará los valores definidos actualmente en crear_estado_grafo(), incluyendo:

- Contadores a cero.
- Listas y cadenas transitorias vacías.
- abstencion=True.
- estado_evidencia=insuficiente.
- pendiente_hitl=False.
- done=False.
- plan_aprobado=None.
- approval_id=None.
- error=None.

### 6.3. Inicio de un turno

Antes de ejecutar LangGraph deberá comprobarse:

- Validez de la consulta y las entradas adicionales.
- Correspondencia entre estado y thread_id.
- Disponibilidad y consistencia del checkpoint existente.
- Ausencia de ejecuciones incompletas.
- Ausencia de HITL pendiente.
- Conversación no finalizada.
- Disponibilidad de turnos.

El último turno permitido podrá resolver su HITL aunque no se admitan consultas adicionales.

### 6.4. Preparación

preparar_nuevo_turno() reiniciará los campos transitorios:

- Progreso de especialistas.
- Notas, evidencias, fuentes y limitaciones.
- Respuesta, plan, decisión y approval_id.
- Errores, iteraciones y trazas del turno.
- Contador de herramientas.
- Ubicación e información multimodal anteriores.

Se conservarán max_turns, la configuración permitida de max_steps, el contexto de revisión, el historial acotado y el contador acumulado de turnos.

La ubicación y la información multimodal únicamente permanecerán activas cuando se proporcionen expresamente para el nuevo turno.

### 6.5. Contabilización

preparar_nuevo_turno() incrementará turnos_consumidos una única vez, inmediatamente antes de iniciar LangGraph.

La aprobación y el rechazo no incrementarán el contador.

Los límites se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 7. Supervisor y enrutamiento

### 7.1. Rutas autorizadas

```python
Ruta = Literal[
    "residuos",
    "puntos",
    "sintetizar",
    "FINISH",
]
```

Python validará las decisiones del modelo y aplicará las reglas deterministas existentes.

### 7.2. Selección de operaciones

El supervisor deberá:

1. Identificar las necesidades de la consulta.
2. Ejecutar únicamente los especialistas necesarios.
3. Comprobar su progreso.
4. Solicitar la síntesis.
5. Finalizar el enrutamiento cuando exista una propuesta válida.

Se conservarán las rutas deterministas y el fallback.

Las decisiones inválidas del modelo podrán recuperarse mediante reglas autorizadas, siempre que no exista un fallo técnico bloqueante.

### 7.3. Control de progreso

_ruta_obligatoria() conservará las restricciones de MAX_ITER y reservará las decisiones necesarias para sintetizar y finalizar.

No se permitirá alcanzar FINISH cuando existan especialistas requeridos pendientes.

_hay_salida_valida() comprobará la respuesta, el plan, approval_id y la ausencia de errores bloqueantes.

destino_condicional() conservará:

```python
return "aplicar" if ruta == "FINISH" else ruta
```

Si no puede completarse el flujo dentro de los límites, se comunicará un fallo técnico.

## 8. Especialistas

### 8.1. Residuos

Obtendrá evidencia sobre identificación, clasificación, materiales, tratamiento y destinos de depósito.

Podrá interpretar observaciones visuales, pero las recomendaciones de reciclaje requerirán evidencia documental.

### 8.2. Puntos

Obtendrá información sobre instalaciones, modalidades de recogida, proximidad, compatibilidad documental y horarios.

Las búsquedas geográficas requerirán coordenadas autorizadas.

La evaluación temporal se realizará cuando resulte necesaria conforme a [04-consultas-generales.md](04-consultas-generales.md).

### 8.3. Ejecución

Se conservarán las rutas deterministas y las rutas mediante razonamiento del modelo.

Ambas respetarán los permisos, argumentos, presupuestos, caché y contratos de [05-tools.md](05-tools.md).

Una ruta determinista de herramientas no constituye una finalización directa de LangGraph.

## 9. Síntesis y suficiencia de evidencia

### 9.1. Evaluación

| Estado | Significado |
|---|---|
| suficiente | Permite resolver los aspectos requeridos |
| parcial | Permite resolver únicamente determinados aspectos |
| insuficiente | No permite fundamentar la respuesta solicitada |

Una búsqueda geográfica legítimamente vacía podrá constituir evidencia suficiente para comunicar la ausencia de coincidencias.

Una observación visual podrá ser suficiente para una consulta exclusivamente descriptiva.

La clasificación del destino de un residuo requerirá respaldo documental.

### 9.2. Integración

El nodo sintetizar utilizará preferentemente:

- Respuestas RAG completas y válidas.
- Integración determinista de evidencias.
- Resultados geográficos y temporales ya obtenidos.

Se utilizará Gemini únicamente cuando la integración existente resulte insuficiente.

Los contratos de generación y referencias se establecen en [03-generacion.md](03-generacion.md).

### 9.3. Fallos bloqueantes

_hay_fallo_bloqueante() deberá distinguir:

- Fallos técnicos de operaciones imprescindibles.
- Fallos recuperados mediante mecanismos autorizados.
- Operaciones auxiliares no imprescindibles.
- Ausencia legítima de evidencia.

La necesidad de información temporal se determinará según la consulta y las recomendaciones que se pretenden formular.

La ausencia o fallo de hora_actual no podrá ignorarse sistemáticamente cuando la información temporal resulte imprescindible.

La comprobación de fallos bloqueantes deberá realizarse antes de seleccionar cualquier modalidad de síntesis satisfactoria.

La existencia de evidencia parcial no permitirá ocultar un fallo técnico imprescindible.

### 9.4. Propuesta

Toda síntesis satisfactoria deberá producir:

- Respuesta no vacía.
- Plan válido.
- Fuentes y evidencias correspondientes.
- Estado de evidencia.
- Motivo y limitaciones, cuando proceda.

El plan será una lista de al menos dos cadenas no vacías, coherentes con la respuesta y la evidencia disponible.

Las consultas informativas, abstenciones y aclaraciones obtenidas dentro de LangGraph también generarán planes adecuados y alcanzarán HITL.

Una vez validada la propuesta se generará:

```python
approval_id = str(uuid4())
```

El identificador se almacenará en el checkpoint y será exclusivo de esa propuesta.

## 10. Supervisión humana — HITL

### 10.1. Interrupción

La existencia de una aprobación pendiente se comprobará mediante el checkpoint real:

```python
tuple(snapshot.next) == ("aplicar",)
```

El indicador pendiente_hitl no será suficiente por sí solo.

Una propuesta válida deberá contener:

| Campo | Valor |
|---|---|
| respuesta | Cadena no vacía |
| plan | Lista válida |
| plan_aprobado | None |
| pendiente_hitl | True |
| approval_id | UUID válido |
| done | False |
| error | None |

approval_id podrá existir internamente después de sintetizar, pero solo se expondrá como aprobación pendiente después de confirmar la interrupción.

Una ejecución que termine inesperadamente sin HITL constituirá un fallo técnico.

### 10.2. Validación de decisiones

aprobar_plan() comprobará:

- Identificadores y decisión válidos.
- Existencia y consistencia del checkpoint.
- Interrupción real antes de aplicar.
- Respuesta y plan válidos.
- Ausencia de errores bloqueantes.
- Coincidencia de approval_id.
- Ausencia de resolución previa.

Un identificador anterior no podrá resolver una nueva propuesta.

El núcleo comunicará los conflictos mediante errores internos controlados.

Su transformación HTTP se establece en [12-contratos-http.md](12-contratos-http.md).

### 10.3. Reanudación

```python
app.update_state(
    configuracion,
    {"plan_aprobado": aprobado},
)

app.invoke(
    None,
    config=configuracion,
)
```

Se conservará la reanudación de la interrupción estática.

No se iniciará un nuevo turno.

### 10.4. Confirmación

Después de reanudar deberán verificarse:

- Existencia de un checkpoint final sin tareas pendientes.
- Ausencia de HITL pendiente.
- Eliminación de approval_id.
- Correspondencia entre plan_aprobado y la decisión.
- Valor esperado de done.
- Ausencia de errores.
- Conservación del contador de turnos.
- Registro del turno actual en el historial.

La comprobación deberá demostrar que aplicar resolvió la propuesta actual.

No será suficiente comprobar que el último registro contiene el mismo booleano ni que aumentó la longitud del historial, puesto que este se encuentra acotado.

### 10.5. Aprobación automática

La aprobación automática utilizará procesar_turno() y posteriormente aprobar_plan() con el identificador pendiente real.

Solo podrá realizarse cuando la propuesta sea válida y no existan errores.

No se modificará done directamente ni se omitirá aplicar.

La coordinación HTTP respetará el presupuesto compartido y el bloqueo establecidos en la especificación 15.

## 11. Nodo aplicar

### 11.1. Registro

aplicar validará que plan_aprobado sea un booleano.

Utilizará registrar_turno() antes de modificar la propuesta.

El registro conservará la pregunta, respuesta y plan originales, junto con la decisión.

Se incorporará una única vez al historial interno.

No ejecutará herramientas, invocará Gemini ni realizará operaciones externas.

### 11.2. Transiciones

| Campo | Aprobación | Rechazo |
|---|---|---|
| respuesta | Respuesta aprobada | Mensaje de rechazo |
| plan | Plan aprobado | [] |
| plan_aprobado | True | False |
| pendiente_hitl | False | False |
| approval_id | None | None |
| done | True | False |
| error | None | None |

El mensaje de rechazo será:

```text
Plan rechazado. Puedes reformular tu consulta.
```

La aprobación finalizará la conversación.

El rechazo resolverá el turno y permitirá reformular mientras se respeten las restricciones operativas.

### 11.3. Contexto posterior al rechazo

Se conservará el contexto de revisión y la propuesta original en historial_turnos.

Se limpiarán las evidencias, fuentes, notas y plan activos conforme al comportamiento existente.

Se restablecerá el estado de evidencia a insuficiente y abstencion=True.

La propuesta rechazada no permanecerá pendiente ni constituirá automáticamente evidencia válida para una nueva consulta.

El historial SQL almacenará la respuesta definitiva resultante, conforme a [13-persistencia.md](13-persistencia.md).

## 12. Continuidad y checkpoints

MemorySaver conservará el estado operativo de cada conversación.

El checkpoint real tendrá prioridad sobre cualquier representación anterior del estado.

No se sustituirán canales imprescindibles ausentes o inconsistentes mediante datos del cliente.

Se distinguirán conversaciones nuevas, disponibles, en ejecución, pendientes de HITL, finalizadas, agotadas y no reutilizables.

Una conversación existente sin checkpoint válido no podrá inicializarse nuevamente con el mismo thread_id para recuperar silenciosamente su estado.

historial_turnos conservará exclusivamente turnos aprobados o rechazados, limitado mediante MAX_HISTORY_TURNS.

El contexto anterior permitirá interpretar reformulaciones, pero no sustituirá las evidencias necesarias para fundamentar una respuesta nueva.

Las respuestas anteriores a LangGraph no modificarán el checkpoint ni el historial interno.

No se reconstruirán checkpoints utilizando los mensajes SQL.

## 13. Integración multimodal

| Modalidad | ruta_imagen | identificacion_imagen |
|---|---|---|
| Textual | None | None |
| HTTP multimodal | None | Identificación admitida |
| CLI multimodal | Ruta autorizada | None |

Las comprobaciones existentes de presencia de imágenes deberán contemplar ambas modalidades:

```python
hay_imagen = bool(
    estado.get("ruta_imagen")
    or estado.get("identificacion_imagen")
)
```

Se adaptarán especialmente:

- La identificación de necesidades en agent_routing.py.
- El contexto del supervisor.
- Las entradas y rutas deterministas de agent_tool_loop.py.
- La preparación de argumentos.
- La evaluación de respuestas concluyentes.
- La detección de consultas exclusivamente descriptivas.
- La suficiencia de evidencia y los fallos bloqueantes en nodes.py.

La identificación previa se incorporará como observación visual autorizada del especialista residuos, conforme a la especificación 05.

No se repetirá la identificación ni se simulará una nueva invocación de herramienta.

El estado HTTP no conservará imágenes binarias ni rutas temporales que puedan reutilizarse después de su eliminación.

Las imágenes no admitidas se resolverán antes de ejecutar LangGraph.

## 14. Integración con el servicio HTTP

La capa de servicios será responsable de:

- Autenticación y autorización: especificación 14.
- Contratos y respuestas públicas: especificación 12.
- Filtrado previo, admisión, concurrencia y timeout: especificación 15.
- Persistencia de conversaciones y turnos resueltos: especificación 13.

Las respuestas anteriores al agente no constituirán resultados de procesar_turno() ni generarán estados ficticios.

La aprobación automática respetará los controles temporales antes de iniciar su resolución.

Cuando un fallo o timeout comprometa la consistencia del checkpoint, se impedirá reutilizar el hilo conforme a la especificación 15.

El orquestador no utilizará HTTPException.

Los fallos técnicos se comunicarán mediante estados o excepciones internas controladas, conservando información suficiente para identificar su causa.

## 15. Compatibilidad con CLI

La CLI conservará las consultas textuales, imágenes locales y modalidades de aprobación manual y automática.

Se adaptarán _decidir() y run_demo() a la firma de aprobar_plan():

```python
aprobar_plan(
    estado["thread_id"],
    aprobado,
    approval_id=estado["approval_id"],
)
```

Antes de resolver la propuesta se comprobarán su validez, la interrupción real y la ausencia de errores.

Se conservará la opción --auto-aprobar.

## 16. Criterios de aceptación

- Se conservan los cinco nodos y la topología del PB02.
- Toda ejecución satisfactoria alcanza HITL.
- El estado permanece aislado por conversación.
- Se conservan los contratos existentes con las ampliaciones acordadas.
- El supervisor respeta los límites y permisos.
- La síntesis no oculta fallos técnicos imprescindibles.
- Cada propuesta dispone de un approval_id válido.
- Las aprobaciones se verifican contra el checkpoint real.
- Los turnos resueltos se registran una única vez.
- Aprobar finaliza la conversación y rechazar permite reformular.
- La resolución HITL no incrementa el contador de turnos.
- Las identificaciones visuales previas se reutilizan.
- Los checkpoints perdidos o inconsistentes no se reconstruyen.
- La CLI conserva su funcionamiento independiente.

Las pruebas se establecen en [plan-pruebas.md](../docs/plan-pruebas.md), conforme a [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).