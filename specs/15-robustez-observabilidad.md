# 15. Robustez y observabilidad

## 1. Objetivo

Garantizar la estabilidad, seguridad, disponibilidad y trazabilidad del backend de ReciclaTÍA mediante mecanismos deterministas de control de peticiones, consumo de recursos, concurrencia, tiempos de ejecución y gestión de errores.

La robustez del servicio deberá satisfacer los requisitos académicos del Project Break 03 y preservar las funcionalidades desarrolladas durante el PB02.

Las medidas de protección se aplicarán independientemente del cliente utilizado para acceder a la API.

## 2. Principios generales

- Validar las entradas antes de ejecutar operaciones costosas.
- Autenticar y autorizar las operaciones protegidas.
- Limitar el consumo de recursos por consumidor.
- Proteger los servicios externos frente a peticiones excesivas.
- Controlar la concurrencia sobre recursos compartidos.
- Evitar modificaciones simultáneas de una misma conversación.
- Establecer tiempos máximos de espera.
- Gestionar los fallos de forma controlada.
- Diferenciar errores técnicos de resultados semánticos.
- Evitar falsos éxitos HTTP.
- Mantener el HITL obligatorio del agente.
- Registrar información suficiente para diagnosticar incidencias.
- Evitar la exposición de información sensible.
- Mantener las decisiones de seguridad independientes del LLM.
- Reutilizar los mecanismos existentes siempre que resulte posible.

La robustez no deberá modificar innecesariamente la arquitectura del agente ni introducir dependencias externas que excedan el alcance del proyecto.

## 3. Separación de responsabilidades

| Archivo | Responsabilidad |
|---|---|
| api/rate_limit.py | Cuotas, ventanas temporales y límites de peticiones |
| api/security.py | Autenticación y autorización |
| api/dependencies.py | Aplicación de controles reutilizables |
| api/service.py | Coordinación, admisión y ejecución del asistente |
| api/images.py | Validación, adaptación y gestión temporal de imágenes |
| api/errors.py | Excepciones y respuestas HTTP homogéneas |
| api/main.py | Configuración, middleware y ciclo de vida del backend |
| api/config.py | Configuración específica del servicio HTTP |
| src/db.py | Conexión y operaciones de persistencia |
| config.py | Configuración independiente del núcleo del asistente |

La configuración de robustez del backend no deberá impedir el funcionamiento independiente de la CLI ni del sistema RAG.

La lógica de protección HTTP no se incorporará a los nodos de LangGraph.

El núcleo continuará siendo responsable de sus propios límites de ejecución, herramientas y turnos.

## 4. Niveles de protección

Se establecerán cuatro niveles de control independientes.

| Nivel | Finalidad |
|---|---|
| Rate limiting HTTP | Proteger los endpoints frente a peticiones excesivas |
| Cuotas comerciales | Limitar las consultas al asistente según el rol |
| Límites de seguridad | Proteger el registro, autenticación y emisión de credenciales |
| Límites técnicos | Proteger memoria, CPU, conexiones y capacidad de ejecución |

Además, el agente conservará sus propios límites de turnos, iteraciones y herramientas.

Superar cualquiera de estos controles podrá impedir la ejecución de una operación.

Disponer de cuota comercial no garantiza que:

- La petición sea válida.
- La operación esté autorizada.
- La conversación pueda continuar.
- Exista capacidad de ejecución disponible.

## 5. Rate limiting HTTP

### 5.1. Objetivo

Limitar el número de peticiones HTTP realizadas contra los endpoints protegidos, independientemente de que impliquen llamadas al asistente.

Este mecanismo protegerá también:

- La consulta del historial.
- La gestión de cuentas.
- La gestión de API keys.
- Las operaciones administrativas.
- Las solicitudes de aprobación y rechazo.

### 5.2. Identificación

Las operaciones autenticadas mediante API key se contabilizarán utilizando api_key.id.

Las operaciones realizadas mediante sesión y selección de API key utilizarán igualmente api_key.id.

Las operaciones exclusivamente relacionadas con una cuenta utilizarán user.id.

Los identificadores deberán distinguir el tipo de identidad para evitar mezclar contadores de usuarios y API keys.

No se utilizarán los secretos originales ni sus hashes como identificadores de consumo.

Las dos modalidades de autenticación de una misma API key compartirán el mismo contador HTTP.

### 5.3. Límite general

Se establece inicialmente:

```dotenv
RATE_LIMIT_PER_MINUTE=30
```

El límite será de 30 peticiones HTTP por minuto por identidad autenticada.

Este límite también será aplicable a las API keys Admin.

El rate limiting HTTP constituye una medida técnica de protección y no una cuota comercial.

### 5.4. Endpoints excluidos

Los siguientes endpoints no consumirán el límite HTTP asociado a una API key:

- GET /health.
- GET /docs.
- GET /openapi.json.

Los endpoints públicos de registro, autenticación y emisión anónima tendrán sus propios límites de seguridad.

Las peticiones preflight de CORS tampoco consumirán cuota comercial ni requerirán autenticación.

La exclusión del limitador por API key no impedirá aplicar medidas generales de protección de infraestructura.

### 5.5. Contabilización

La identidad deberá autenticarse antes de acceder a su contador HTTP.

Una petición autenticada que haya superado el limitador HTTP podrá consumir una unidad de este contador aunque posteriormente sea rechazada por:

- Permisos insuficientes.
- Validaciones adicionales.
- Conflictos de estado.
- Cuota comercial agotada.
- Capacidad técnica agotada.
- Filtrado semántico.

Una petición rechazada durante las validaciones iniciales de FastAPI, antes de alcanzar el limitador, podrá no contabilizarse.

Una credencial inexistente o inválida no podrá consumir el contador asociado a otra credencial.

El momento de contabilización será independiente de la posterior ejecución del asistente.

### 5.6. Superación del límite

Cuando se alcance el límite:

- No se ejecutará la operación solicitada.
- Se devolverá HTTP 429.
- Se utilizará RATE_LIMIT_EXCEEDED.
- Se incluirá Retry-After cuando pueda determinarse.
- No se consumirá cuota comercial.
- No se modificará el checkpoint.

## 6. Cuotas comerciales y contabilización de turnos

### 6.1. Límites establecidos

| Rol | Por minuto | Por hora | Por 24 horas |
|---|---|---|---|
| Free | 2 | 10 | 30 |
| User | 5 | 20 | 45 |
| Admin | Sin límite comercial | Sin límite comercial | Sin límite comercial |

Las cuotas Free serán idénticas para consumidores anónimos y registrados.

Las cuotas se aplicarán individualmente a cada API key.

Las cuotas de diferentes API keys pertenecientes al mismo usuario serán independientes.

### 6.2. Endpoints que consumen cuota

| Endpoint | Consume cuota comercial |
|---|---|
| POST /ask | Según las condiciones de contabilización |
| POST /ask/image | Según las condiciones de contabilización |
| POST /approve | No |
| GET /threads | No |
| GET /threads/{thread_id} | No |
| GET /threads/{thread_id}/messages | No |
| Endpoints de cuenta | No |
| Endpoints administrativos | No |
| GET /health | No |

POST /ask y POST /ask/image compartirán los mismos contadores comerciales.

POST /approve resolverá un turno previamente iniciado y no consumirá una nueva consulta comercial.

No obstante, estará sujeto a los límites HTTP, de concurrencia y ejecución.

### 6.3. Momento de contabilización

Una consulta se contabilizará después de superar:

- Validaciones aplicables.
- Autenticación.
- Autorización.
- Comprobación de propiedad.
- Restricciones de estado.
- Controles de concurrencia.
- Control de capacidad de ejecución.

La cuota se registrará de manera atómica inmediatamente antes de admitir la ejecución costosa.

Para las consultas textuales, la ejecución costosa comenzará con el procesamiento del agente.

Para las consultas multimodales, la contabilización se realizará antes de la primera llamada de identificación visual.

Una consulta multimodal admitida consumirá una única unidad de cuota comercial aunque posteriormente ejecute LangGraph y resuelva automáticamente su HITL.

No se cobrará una unidad adicional por cada herramienta, llamada al modelo o nodo del agente.

Si una tarea no llega a admitirse por un fallo de infraestructura del executor, no deberá contabilizarse como una consulta ejecutada.

### 6.4. Operaciones contabilizadas

| Situación | Consume cuota comercial |
|---|---|
| Consulta textual ejecutada | Sí |
| Consulta multimodal identificada mediante Gemini | Sí |
| Abstención generada dentro del agente | Sí |
| Aclaración generada dentro del agente | Sí |
| Consulta que genera HITL pendiente | Sí |
| Consulta admitida que termina en timeout | Sí |
| Fallo técnico después de iniciar la ejecución costosa | Sí |
| Imagen identificada como fuera de dominio | Sí |
| Imagen identificada como contenido no permitido | Sí |
| Identificación visual incierta | Sí |
| Consulta textual rechazada mediante filtrado previo | No |
| Aclaración determinista anterior a LangGraph | No |
| Petición HTTP inválida | No |
| Credenciales incorrectas | No |
| Permisos insuficientes | No |
| Imagen técnicamente inválida | No |
| Conversación inexistente o ajena | No |
| Conversación cerrada | No |
| Conversación con HITL pendiente | No |
| Conversación con turnos agotados | No |
| Conversación ocupada | No |
| Estado operativo perdido | No |
| Capacidad técnica agotada | No |
| Cuota comercial agotada | No |
| Aprobación o rechazo mediante POST /approve | No |

No se devolverá automáticamente una cuota correspondiente a una ejecución costosa iniciada que haya terminado en timeout o error técnico.

La ejecución puede haber utilizado recursos de Gemini, ChromaDB o la API municipal antes de fallar.

### 6.5. Filtrado previo de dominio

Las consultas textuales deberán superar un filtro determinista de dominio antes de ejecutar LangGraph.

Cuando una consulta se identifique inequívocamente como fuera de dominio, se devolverá una abstención controlada sin invocar:

- LangGraph.
- Gemini.
- RAG.
- Herramientas.

Las consultas ambiguas podrán recibir una solicitud determinista de aclaración.

Estas operaciones:

- Continuarán sujetas al rate limiting HTTP.
- No consumirán cuota comercial.
- No incrementarán turnos_consumidos.
- No modificarán el checkpoint.
- No generarán mensajes persistidos.
- No crearán una conversación cuando todavía no exista un hilo.

El filtro deberá considerar el contexto operativo autorizado cuando exista una conversación disponible.

No se rechazarán automáticamente consultas breves o reformulaciones únicamente porque carezcan de palabras clave explícitas sobre residuos.

Las respuestas anteriores a LangGraph no se incorporarán al historial operativo del agente.

Cuando no exista contexto suficiente, podrá solicitarse al usuario una consulta más completa.

El filtrado previo no permitirá eludir restricciones de conversaciones cerradas, ocupadas, agotadas o con HITL pendiente.

### 6.6. Contadores independientes

Se mantendrán tres mecanismos principales de contabilización:

| Contador | Responsabilidad |
|---|---|
| Rate limiting HTTP | Peticiones realizadas contra el backend |
| Cuota comercial | Consultas costosas admitidas |
| turnos_consumidos | Turnos iniciados en LangGraph |

El contador turnos_consumidos continuará siendo gestionado por el núcleo del agente.

turn_number se obtendrá directamente de dicho contador.

No se incorporará un cuarto contador SQL independiente.

### 6.7. Contabilización del agente

| Operación | Incrementa turnos_consumidos |
|---|---|
| Iniciar un nuevo turno de LangGraph | Sí |
| Resolver HITL manualmente | No |
| Resolver HITL automáticamente | No |
| Rechazar un plan | No |
| Identificación visual sin ejecución posterior de LangGraph | No |
| Respuesta determinista previa | No |
| Consultar el historial | No |

Los turnos iniciados podrán haber consumido recursos aunque posteriormente no se resuelvan satisfactoriamente.

No se reducirá artificialmente el contador de turnos para recuperar capacidad después de una ejecución fallida.

Si el checkpoint no puede reutilizarse de forma segura, se aplicará THREAD_STATE_LOST.

### 6.8. Persistencia

Únicamente se persistirán los turnos de LangGraph correctamente resueltos mediante aprobación o rechazo.

No se persistirán:

- Respuestas previas al agente.
- Identificaciones visuales rechazadas antes del agente.
- Planes pendientes.
- Fallos técnicos.
- Timeouts.
- Resultados tardíos.

La política completa se establece en [13-persistencia.md](13-persistencia.md).

## 7. Ventanas temporales deslizantes

### 7.1. Algoritmo

Se utilizará el algoritmo Sliding Window Log.

Cada identidad dispondrá de una estructura que registre los instantes de las operaciones contabilizadas.

Las estructuras principales serán:

- defaultdict.
- deque.
- Lock.
- time.monotonic().

Los limitadores HTTP, comerciales y de seguridad mantendrán sus propios registros.

### 7.2. Duración de las ventanas

| Ventana | Duración en segundos |
|---|---|
| Minuto | 60 |
| Hora | 3600 |
| Día | 86400 |

Las ventanas serán deslizantes.

No dependerán de cambios de minuto, hora o día del calendario.

La ventana diaria representará las últimas 24 horas.

### 7.3. Funcionamiento

1. Adquirir el bloqueo correspondiente.
2. Obtener el instante actual mediante time.monotonic().
3. Recuperar los registros de la identidad.
4. Eliminar los registros que hayan salido de la ventana temporal más larga.
5. Calcular el número de operaciones dentro de cada ventana.
6. Comprobar todos los límites aplicables.
7. Rechazar la operación si alguno se ha alcanzado.
8. Registrar el nuevo instante únicamente si todos los límites permiten continuar.
9. Liberar el bloqueo.

La comprobación y el registro deberán ejecutarse de manera atómica.

No se registrará parcialmente una operación en una ventana si otra ventana impide admitirla.

No se mantendrá el bloqueo del contador durante la ejecución del agente.

### 7.4. Límites temporales exactos

Una operación dejará de pertenecer a una ventana cuando haya transcurrido una duración igual o superior a la duración de dicha ventana.

Ejemplo conceptual:

```python
while queue and now - queue[0] >= window_seconds:
    queue.popleft()
```

Se utilizará un criterio temporal consistente en:

- Eliminación de registros caducados.
- Cálculo del consumo.
- Cálculo de Retry-After.
- Pruebas automatizadas.

### 7.5. Reloj monotónico

Se utilizará time.monotonic() para calcular intervalos temporales.

Este reloj no depende de ajustes manuales de la hora del sistema ni de sincronizaciones del reloj del sistema operativo.

No se utilizará para representar fechas almacenadas en PostgreSQL.

Las fechas de persistencia se almacenarán en UTC.

### 7.6. Retry-After

Cuando se alcance una cuota, se calculará el tiempo necesario para que exista capacidad disponible en todas las ventanas aplicables.

Si varias ventanas están agotadas, se utilizará el mayor tiempo de espera requerido.

El tiempo se calculará considerando los registros que deben caducar para situar el consumo por debajo del límite correspondiente.

Retry-After se expresará en segundos enteros, redondeados hacia arriba.

No se utilizará un valor fijo de 60 segundos cuando el límite agotado corresponda a una ventana horaria o diaria.

### 7.7. Concurrencia

Dos peticiones concurrentes no deberán poder superar conjuntamente un límite por haber comprobado el contador antes de registrar sus operaciones.

Las comprobaciones deberán realizarse bajo una protección común.

Se utilizarán relojes simulados en las pruebas para evitar esperas reales.

## 8. Almacenamiento de contadores

Los contadores HTTP, comerciales y de seguridad se mantendrán en memoria del backend.

No se incorporarán tablas adicionales de consumo.

### 8.1. Ventajas

- Implementación sencilla.
- Baja latencia.
- Ausencia de consultas SQL adicionales para contabilizar peticiones.
- Independencia de Redis y otros servicios externos.
- Compatibilidad con un despliegue de un único proceso.

### 8.2. Limitaciones

- Los contadores se reinician al reiniciar FastAPI.
- Los contadores no se comparten entre procesos.
- Los contadores no se comparten entre réplicas.
- No representan un registro persistente de facturación.
- No garantizan cuotas comerciales duraderas después de un redeploy.
- No establecen por sí solos un presupuesto global de consumo de Gemini.
- No limitan completamente el abuso realizado mediante múltiples API keys.

Por este motivo, se utilizará un único proceso de Uvicorn y una única instancia del backend durante el PB03.

Antes de implementar un modelo comercial de pago será necesario incorporar un mecanismo persistente y compartido de contabilización.

### 8.3. Limpieza

Los registros temporales caducados deberán eliminarse mediante una política de limpieza controlada.

Las identidades sin actividad dentro de sus ventanas temporales podrán retirarse de las estructuras de almacenamiento.

La limpieza deberá realizarse bajo las protecciones correspondientes.

No se eliminarán contadores que todavía contengan operaciones dentro de ventanas vigentes.

La memoria destinada a estos registros deberá mantenerse bajo límites controlados.

## 9. Protección de registro, autenticación y emisión

### 9.1. Límites iniciales

| Operación | Límite inicial |
|---|---|
| Inicio de sesión por email normalizado | 5 intentos cada 15 minutos |
| Inicio de sesión por origen fiable | 20 intentos cada 15 minutos |
| Registro por origen fiable | 5 intentos por hora |
| Emisión Free anónima por origen fiable | 3 por hora y 5 por 24 horas |
| Emisión de claves registradas por usuario | 3 por hora y 5 por 24 horas |

Estos valores serán configurables.

Las operaciones de autenticación deberán limitarse antes de ejecutar verificaciones costosas mediante bcrypt.

Los intentos fallidos de autenticación también deberán contabilizarse.

### 9.2. Límites de claves activas

| Tipo de clave | Límite inicial |
|---|---|
| Free registrada | Una clave activa por usuario |
| User | Cinco claves activas por usuario |
| Admin | Emisión interna restringida |

Los límites de claves activas se establecen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

La comprobación del número de claves activas y su creación deberá protegerse frente a operaciones concurrentes.

Esta protección también se aplicará a la reactivación de claves.

Los límites temporales de emisión serán independientes del número de claves activas.

La emisión administrativa de claves registradas respetará los límites correspondientes al usuario destinatario.

### 9.3. Identificación del origen

La dirección IP solo podrá utilizarse como identificador cuando se obtenga de una fuente fiable.

No se confiará directamente en cabeceras X-Forwarded-For proporcionadas por consumidores externos.

Las cabeceras de identificación del origen únicamente se aceptarán cuando procedan de un proxy conocido y correctamente configurado.

Cuando Streamlit realice peticiones al backend, la IP observada podrá corresponder al servidor Streamlit y no al consumidor final.

Cuando no pueda obtenerse un origen individual fiable:

- Se utilizarán los identificadores autenticados disponibles.
- Las operaciones públicas estarán sujetas a límites de protección compartidos.
- No se confiará en identificadores de origen arbitrarios proporcionados por el consumidor.

Los límites compartidos podrán afectar simultáneamente a diferentes usuarios de Streamlit.

Esta limitación deberá documentarse y calibrarse durante las pruebas de despliegue.

La identificación mediante IP no constituye una identificación inequívoca de una persona.

### 9.4. Limitaciones del acceso anónimo

Streamlit conservará la API key Free durante la sesión del consumidor.

No se emitirá automáticamente una nueva clave:

- Para cada mensaje.
- Para cada rerun.
- Para cada conversación.
- Al alcanzar una cuota.
- Después de un error técnico.

La recreación de sesiones anónimas podrá permitir obtener nuevas credenciales dentro de los límites de emisión.

No se incorporarán mecanismos invasivos de identificación de dispositivos.

### 9.5. Autorización del nivel User

La emisión ordinaria de claves User dependerá de USER_TIER_ALLOWED_USER_IDS.

Los permisos no se concederán únicamente mediante la coincidencia de un email.

La política de autorización y emisión administrativa se define en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

## 10. Control de concurrencia

### 10.1. Objetivo

Permitir que el backend atienda peticiones HTTP concurrentes sin provocar inconsistencias en LangGraph ni superar la capacidad disponible.

La concurrencia HTTP será independiente de la capacidad de ejecución simultánea del asistente.

### 10.2. Conceptos

thread_id identificará una conversación.

Un hilo de ejecución de Python representará una unidad de ejecución concurrente.

Un worker de ThreadPoolExecutor ejecutará operaciones bloqueantes.

Un proceso de Uvicorn alojará el backend.

Estos conceptos serán independientes.

Una conversación podrá ser atendida por diferentes hilos de Python en peticiones sucesivas.

### 10.3. Bloqueo por conversación

Cada thread_id dispondrá de un mecanismo de exclusión mutua.

Las siguientes operaciones no podrán modificar simultáneamente una misma conversación:

- POST /ask.
- POST /ask/image.
- POST /approve.

También se protegerán las comprobaciones del checkpoint que determinen si una operación puede continuar.

Las respuestas deterministas previas correspondientes a una conversación existente respetarán los mismos controles de estado y exclusión mutua.

Las consultas a PostgreSQL de carácter exclusivamente histórico no necesitarán adquirir el bloqueo operativo de LangGraph.

### 10.4. Conversación ocupada

Si una petición intenta modificar una conversación que ya está siendo procesada:

- No esperará a que termine la ejecución anterior.
- No iniciará una segunda modificación.
- Devolverá HTTP 409 THREAD_BUSY.
- No consumirá una nueva cuota comercial.

La comprobación de propiedad deberá realizarse antes de revelar que una conversación está ocupada.

### 10.5. Duración del bloqueo

El bloqueo se mantendrá durante las fases aplicables de:

- Comprobación del checkpoint.
- Validación del estado conversacional.
- Filtrado previo sobre un hilo existente.
- Identificación multimodal.
- Ejecución de LangGraph.
- Resolución automática del HITL.
- Transformación y validación del resultado.
- Persistencia del turno resuelto.

Si se produce un timeout, el bloqueo no se liberará mientras una ejecución anterior pueda seguir modificando el estado.

### 10.6. Orden de admisión

Para las consultas al asistente se aplicará el siguiente orden lógico:

1. Validar la estructura inicial de la petición.
2. Autenticar la credencial.
3. Aplicar el rate limiting HTTP.
4. Comprobar permisos.
5. Validar los campos de entrada.
6. Comprobar la existencia y propiedad de una conversación indicada.
7. Adquirir el bloqueo del hilo existente, cuando corresponda.
8. Verificar el estado operativo de la conversación.
9. Aplicar el filtro determinista previo.
10. Validar técnicamente la imagen, cuando corresponda.
11. Comprobar la capacidad global de ejecución.
12. Comprobar y registrar la cuota comercial aplicable.
13. Admitir la tarea costosa.
14. Ejecutar la identificación multimodal, cuando corresponda.
15. Crear una conversación si resulta necesario iniciar LangGraph.
16. Ejecutar LangGraph.
17. Resolver automáticamente el HITL si se ha solicitado.
18. Validar el resultado.
19. Comprobar nuevamente la autorización aplicable.
20. Persistir el turno si está correctamente resuelto.
21. Preparar la respuesta.
22. Liberar los recursos cuando resulte seguro.

El orden concreto de algunas validaciones estructurales podrá depender de FastAPI y Pydantic.

No deberán adelantarse operaciones costosas respecto a los controles de admisión que las protegen.

Las respuestas deterministas válidas podrán finalizar antes de adquirir capacidad del executor.

Las imágenes no admitidas semánticamente finalizarán antes de crear una nueva conversación del agente.

### 10.7. Restricciones de conversaciones existentes

Antes de permitir una nueva consulta se comprobará:

- Disponibilidad del checkpoint.
- Ausencia de HITL pendiente.
- Que la conversación no esté cerrada.
- Que el límite de turnos no esté agotado.
- Que no exista una ejecución concurrente.

Una consulta determinista previa no permitirá eludir estas restricciones.

El último turno permitido podrá finalizar su HITL aunque se haya alcanzado el límite de turnos iniciados.

### 10.8. Liberación de recursos

Los bloqueos deberán liberarse incluso cuando se produzcan excepciones, siempre que ninguna ejecución pueda seguir utilizando los recursos protegidos.

Las estructuras de gestión de bloqueos no deberán crecer indefinidamente.

Solo podrán eliminarse entradas de bloqueo cuando ninguna operación las esté utilizando ni pueda adquirir una referencia anterior de manera concurrente.

La creación, consulta y retirada de bloqueos deberá protegerse adecuadamente.

## 11. Capacidad de ejecución del servidor

### 11.1. ThreadPoolExecutor

Las operaciones bloqueantes del asistente se ejecutarán mediante un ThreadPoolExecutor compartido.

El executor se creará durante el ciclo de vida del backend.

No se creará un executor independiente para cada petición.

Tampoco se crearán executors separados para:

- Identificación multimodal.
- LangGraph.
- Aprobaciones automáticas.

### 11.2. Número de workers

La configuración inicial será:

```dotenv
AGENT_MAX_WORKERS=1
```

Con esta configuración solamente podrá ejecutarse una operación costosa del asistente simultáneamente.

El backend podrá seguir atendiendo otras peticiones HTTP compatibles.

El worker de ThreadPoolExecutor será independiente del proceso de Uvicorn.

El aumento del número de workers requerirá pruebas adicionales de concurrencia, memoria y estabilidad.

### 11.3. Control de admisión

Se utilizará un semáforo cuya capacidad corresponda al número de workers disponibles.

La adquisición de capacidad deberá realizarse sin introducir una cola de espera para nuevas consultas.

La capacidad se comprobará antes de consumir cuota comercial y enviar tareas al executor.

ThreadPoolExecutor por sí solo no garantiza una cola de tareas acotada.

Por este motivo, no se permitirá enviar tareas ilimitadas esperando que el executor las procese posteriormente.

### 11.4. Capacidad agotada

Cuando no exista capacidad disponible:

- No se iniciará una nueva ejecución.
- Se devolverá HTTP 503 SERVER_BUSY.
- No se consumirá cuota comercial.
- No se creará una nueva conversación por la operación rechazada.

Cuando exista simultáneamente un conflicto sobre el mismo thread_id, se aplicará THREAD_BUSY después de comprobar la autorización correspondiente.

Las claves Admin estarán sujetas al mismo límite técnico.

### 11.5. Responsabilidad del worker

El worker ejecutará las operaciones costosas admitidas.

Según el tipo de consulta, estas podrán incluir:

- Identificación visual.
- Validación semántica de la identificación.
- Creación de la conversación antes de LangGraph.
- Ejecución del agente.
- Resolución automática del HITL.

La persistencia definitiva de los mensajes de un turno resuelto no se realizará dentro del worker.

El resultado se devolverá a la capa de servicios para su validación y persistencia autorizada.

Si el worker necesita realizar operaciones SQL previas a LangGraph, utilizará sus propias sesiones de PostgreSQL.

No se compartirán sesiones SQL entre hilos.

### 11.6. Compatibilidad con FastAPI

La espera del resultado no deberá bloquear el event loop de FastAPI.

Podrá utilizarse una función de endpoint o servicio síncrona ejecutada en el mecanismo de concurrencia correspondiente.

No se invocará directamente una espera bloqueante prolongada desde el event loop de un endpoint asíncrono.

### 11.7. Finalización real

La capacidad no se liberará únicamente porque haya terminado la espera HTTP.

Se liberará cuando:

- La tarea haya finalizado realmente.
- Ninguna operación pueda continuar utilizando el recurso reservado.
- Se hayan aplicado los controles de consistencia y limpieza necesarios.

La liberación deberá realizarse exactamente una vez.

## 12. Timeout

### 12.1. Objetivo

Evitar que una petición HTTP permanezca bloqueada indefinidamente esperando una ejecución del asistente.

El timeout limitará la espera del backend, pero no garantizará la interrupción inmediata de operaciones bloqueantes ya iniciadas.

### 12.2. Configuración inicial

```dotenv
ASK_TIMEOUT_SECONDS=60
```

Este valor constituye una configuración inicial de desarrollo.

Deberá calibrarse mediante mediciones reales antes del despliegue definitivo.

La calibración tendrá en cuenta:

- Consultas textuales.
- Consultas compuestas.
- Consultas multimodales.
- Resolución automática del HITL.
- Latencia de Gemini.
- Latencia de la API municipal.
- Límites de espera del cliente HTTP.
- Restricciones de infraestructura.

No se considerarán los 60 segundos un valor definitivo sin evidencia experimental.

### 12.3. Alcance

Una consulta textual dispondrá de un único presupuesto temporal para:

- Ejecución de LangGraph.
- Resolución automática del HITL, cuando corresponda.

Una consulta multimodal dispondrá de un único presupuesto temporal compartido para:

- Identificación visual.
- Validación del resultado multimodal.
- Operaciones necesarias para iniciar el agente.
- Ejecución de LangGraph.
- Resolución automática del HITL.

No se asignará un presupuesto completo independiente a cada fase.

La validación técnica previa de imágenes y la persistencia definitiva de mensajes dispondrán de sus propios controles.

Por tanto, ASK_TIMEOUT_SECONDS no representará necesariamente la duración máxima total de toda la petición HTTP.

### 12.4. HITL manual

Cuando auto_aprobar=False, el tiempo durante el cual el consumidor decide aprobar o rechazar no formará parte del timeout del asistente.

POST /ask o POST /ask/image finalizará cuando exista un HITL pendiente válido.

POST /approve dispondrá de un nuevo presupuesto de ejecución.

El worker no permanecerá reservado mientras el consumidor decide.

El checkpoint conservará la aprobación pendiente.

### 12.5. Aplicación

Se utilizará un único Future para representar la ejecución costosa admitida.

Ejemplo conceptual:

```python
future = executor.submit(
    ejecutar_consulta,
    datos_consulta,
)

resultado = future.result(
    timeout=ASK_TIMEOUT_SECONDS,
)
```

La medición comenzará en el momento de enviar la tarea admitida.

Si existe tiempo transcurrido antes de iniciar la espera, deberá descontarse del presupuesto disponible.

Se distinguirá entre el agotamiento de la espera sobre el Future y una excepción producida dentro de la propia tarea.

El código anterior no representa por sí solo la implementación completa de bloqueos, admisión y liberación de recursos.

### 12.6. Superación del presupuesto

Cuando se alcance el tiempo máximo de espera:

- Se devolverá HTTP 504 AGENT_TIMEOUT.
- No se devolverá una respuesta parcial como resultado satisfactorio.
- No se persistirán los mensajes del turno.
- No se devolverá automáticamente la cuota comercial consumida.
- Se descartará cualquier resultado tardío.

### 12.7. Limitaciones de la cancelación

Un timeout en future.result() no garantiza que una función que ya está ejecutándose se detenga.

future.cancel() únicamente podrá cancelar una tarea que todavía no haya comenzado.

No se implementará cancelación cooperativa ni interrupción forzada de hilos durante el PB03.

Por tanto:

- El worker podrá continuar ocupado.
- El bloqueo de la conversación permanecerá activo.
- Los archivos temporales necesarios permanecerán disponibles.
- El resultado tardío no podrá convertirse en una respuesta satisfactoria.
- La conversación no podrá reutilizarse desde un estado cuya consistencia no pueda garantizarse.

### 12.8. Gestión de resultados tardíos

La capa de servicios conservará la responsabilidad exclusiva de autorizar la persistencia definitiva de mensajes.

Cuando se comunique un timeout, la ejecución correspondiente quedará invalidada como resultado satisfactorio.

La finalización tardía podrá utilizarse únicamente para:

- Liberar capacidad.
- Liberar bloqueos.
- Limpiar archivos temporales.
- Registrar la finalización real.
- Consolidar la invalidación del estado operativo afectado.

No se utilizará para persistir el turno.

La gestión del resultado tardío y la finalización normal deberán coordinarse para evitar condiciones de carrera.

No se liberarán recursos dos veces.

### 12.9. Conversaciones afectadas

Cuando un timeout o fallo técnico deje un checkpoint en un estado cuya consistencia no pueda garantizarse, la conversación se marcará internamente como no reutilizable.

Podrá utilizarse una estructura protegida en memoria para identificar los hilos afectados.

No será necesario añadir una tabla ni una columna de estado operativo a PostgreSQL.

Mientras el worker continúe utilizando una conversación, una segunda operación podrá recibir THREAD_BUSY.

Cuando termine realmente la ejecución y el hilo se encuentre invalidado, los intentos posteriores recibirán HTTP 409 THREAD_STATE_LOST.

El historial previamente persistido permanecerá disponible.

Si el timeout afecta únicamente a una identificación visual y no se modifica ningún checkpoint, no será necesario invalidar una conversación previamente consistente.

Cuando no pueda garantizarse que la ejecución tardía no haya modificado el checkpoint, se aplicará una invalidación conservadora.

### 12.10. Timeouts externos

Las llamadas a Gemini y a la API municipal dispondrán de límites de espera compatibles con el funcionamiento del asistente.

Las operaciones SQL dispondrán de límites de conexión y ejecución independientes.

No se introducirán reintentos ilimitados.

Los mecanismos de recuperación existentes deberán revisarse para evitar acumulaciones excesivas de espera.

No se garantizará que una llamada externa termine exactamente cuando expire el timeout global.

## 13. Límites internos del asistente

Se conservarán los controles deterministas del PB02, ajustando los valores iniciales para optimizar el consumo sin modificar los requisitos funcionales.

| Parámetro | Valor inicial |
|---|---|
| MAX_PREGUNTA_CARACTERES | 500 |
| MAX_STEPS_DEFAULT | 3 |
| MAX_STEPS_LIMIT | 4 |
| MAX_TURNS_DEFAULT | 6 |
| MAX_TURNS_LIMIT | 12 |
| MAX_HISTORY_TURNS | 6 |
| MAX_TOOL_CALLS_PER_SPECIALIST | 4 |
| MAX_TOOL_CALLS_PER_TURN | 6 |
| MAX_ITER | 4 |
| GRAPH_RECURSION_LIMIT | 16 |

El límite de recursión se calculará mediante:

```python
GRAPH_RECURSION_LIMIT = 2 * MAX_ITER + 8
```

El consumidor no podrá incrementar los límites por encima de los máximos autorizados.

### 13.1. Justificación

- MAX_ITER limita las decisiones del supervisor.
- MAX_STEPS_DEFAULT controla las rondas ordinarias de interacción.
- MAX_STEPS_LIMIT limita consultas complejas.
- MAX_TOOL_CALLS_PER_SPECIALIST limita el uso de herramientas por especialista.
- MAX_TOOL_CALLS_PER_TURN establece un presupuesto global interno de herramientas.
- MAX_TURNS_DEFAULT y MAX_TURNS_LIMIT controlan la duración operativa de una conversación.
- MAX_HISTORY_TURNS limita el contexto conversacional interno.

La identificación visual realizada antes de LangGraph consumirá cuota comercial, pero no se contabilizará como una ejecución de una herramienta dentro del grafo.

Se reutilizará su resultado sin repetir la llamada multimodal.

### 13.2. Calibración

Los valores deberán verificarse mediante:

- Pruebas de regresión.
- Consultas simples.
- Consultas compuestas.
- Consultas multimodales.
- Consultas geográficas y temporales.
- Reformulaciones.
- Casos límite.
- Consumo de tokens.
- Número de llamadas a servicios externos.

El límite interno no deberá impedir que el agente alcance correctamente la interrupción HITL obligatoria en las consultas admitidas.

Se utilizarán los límites más restrictivos que permitan satisfacer los requisitos funcionales y académicos.

### 13.3. Agotamiento de turnos

Una conversación con el límite de turnos agotado no podrá iniciar nuevas consultas.

Se devolverá HTTP 409 TURN_LIMIT_REACHED.

El consumidor podrá iniciar una nueva conversación.

Una aprobación correspondiente al último turno permitido podrá resolverse aunque turnos_consumidos haya alcanzado el máximo.

## 14. Robustez del HITL

### 14.1. HITL obligatorio

Toda ejecución satisfactoria del agente deberá generar una respuesta y un plan válidos y alcanzar la interrupción existente antes del nodo aplicar.

Se conservarán:

- Los cinco nodos del PB02.
- MemorySaver.
- La interrupción HITL existente.
- La resolución de aprobación o rechazo.

No se incorporarán salidas directas del grafo que eviten el HITL.

Las respuestas deterministas anteriores a LangGraph no estarán sujetas a esta obligación porque no constituyen ejecuciones del agente.

### 14.2. Comprobación del estado

POST /approve deberá verificar el checkpoint real de LangGraph.

No se confiará exclusivamente en:

- pendiente_hitl mostrado por Streamlit.
- Un plan enviado por el cliente.
- El estado interno aportado por un consumidor.
- La existencia de mensajes SQL.

### 14.3. Operaciones incompatibles

| HTTP | Código | Situación |
|---|---|---|
| 409 | NO_PENDING_APPROVAL | Resolver una aprobación inexistente |
| 409 | PENDING_APPROVAL | Preguntar con HITL pendiente |
| 409 | THREAD_CLOSED | Preguntar en una conversación finalizada |
| 409 | TURN_LIMIT_REACHED | Iniciar un turno cuando se ha agotado el límite |
| 409 | THREAD_BUSY | Modificar una conversación ocupada |
| 409 | THREAD_STATE_LOST | Operar sin checkpoint fiable |
| 409 | STALE_APPROVAL | Resolver una aprobación diferente de la pendiente |

Los códigos se establecen en [12-contratos-http.md](12-contratos-http.md).

### 14.4. Aprobaciones duplicadas

Si dos peticiones intentan resolver la misma aprobación, solamente una podrá modificar el estado.

Una petición concurrente podrá recibir THREAD_BUSY.

Una petición posterior deberá volver a comprobar el checkpoint.

Si la aprobación ya se ha resuelto, deberá rechazarse conforme al estado correspondiente.

La persistencia respetará la restricción:

```sql
UNIQUE (thread_id, turn_number, role)
```

No se generará un segundo par de mensajes por una aprobación repetida.

### 14.5. Aprobaciones obsoletas

Cada aprobación pendiente dispondrá de un UUID denominado approval_id.

El identificador se generará mediante Python.

Estará asociado exclusivamente al plan pendiente correspondiente.

El backend comprobará:

- Que existe un checkpoint válido.
- Que existe una interrupción HITL real.
- Que el plan pendiente es válido.
- Que approval_id coincide con el almacenado.

Si no existe aprobación pendiente, se devolverá NO_PENDING_APPROVAL.

Si existe una aprobación pendiente diferente, se devolverá STALE_APPROVAL.

Una aprobación obsoleta no modificará el estado ni generará mensajes.

### 14.6. Aprobación automática

auto_aprobar=True utilizará la misma función de resolución que POST /approve.

No se simulará una aprobación modificando únicamente atributos del estado público.

La aprobación automática:

- No consumirá una segunda unidad de cuota comercial.
- No incrementará turnos_consumidos.
- Compartirá el presupuesto temporal de la consulta.
- Mantendrá la protección de concurrencia del turno.

### 14.7. Resultado inesperado

Si una ejecución admitida de LangGraph termina sin alcanzar el HITL obligatorio, se considerará un fallo técnico.

No se devolverá HTTP 200 simulando una respuesta directa válida.

## 15. Procesamiento seguro de imágenes

### 15.1. Formatos permitidos

- JPEG.
- PNG.

El formato real se comprobará mediante el contenido del archivo.

No se confiará exclusivamente en la extensión ni en Content-Type.

No se admitirán imágenes animadas ni archivos de otros formatos renombrados como JPEG o PNG.

### 15.2. Límites finales

| Parámetro | Límite |
|---|---|
| Peso | 5 MiB |
| Resolución total | 16.000.000 píxeles |

Estos valores corresponden a los límites del procesamiento de imágenes existente.

### 15.3. Límites absolutos de recepción

| Parámetro | Límite absoluto |
|---|---|
| Peso del archivo | 20 MiB |
| Resolución original | 32.000.000 píxeles |

El límite absoluto protegerá al backend antes de realizar operaciones costosas de descompresión y adaptación.

También deberá limitarse el tamaño total del cuerpo HTTP.

El límite del cuerpo deberá contemplar la sobrecarga de multipart/form-data.

No será suficiente confiar únicamente en Content-Length.

La recepción deberá protegerse antes de permitir que el procesamiento multipart acumule archivos de tamaño arbitrario.

### 15.4. Proceso de validación

1. Aplicar los controles de recepción.
2. Verificar la autorización multimodal.
3. Identificar el formato real.
4. Comprobar las dimensiones declaradas.
5. Detectar riesgos de descompresión excesiva.
6. Verificar la integridad de la imagen.
7. Decodificar de forma controlada.
8. Corregir la orientación cuando corresponda.
9. Eliminar metadatos innecesarios.
10. Redimensionar si supera la resolución final.
11. Comprimir si supera el peso final.
12. Verificar nuevamente la integridad, formato, peso y resolución.
13. Crear un archivo temporal autorizado.
14. Aplicar los controles de admisión y cuota comercial.
15. Ejecutar la identificación multimodal estructurada.
16. Validar su resultado.
17. Determinar si el flujo puede continuar.
18. Ejecutar LangGraph únicamente cuando corresponda.
19. Reutilizar la identificación previamente obtenida.
20. Eliminar el archivo cuando resulte seguro.

Se utilizará Pillow para el procesamiento.

No se desactivarán sus mecanismos de protección frente a imágenes maliciosas o bombas de descompresión.

El procesamiento técnico previo también deberá disponer de límites de recursos adecuados.

### 15.5. Redimensionamiento

Cuando una imagen supere los 16.000.000 píxeles, pero se encuentre dentro del límite absoluto, se intentará reducir su resolución.

Se conservará la relación de aspecto.

La imagen resultante deberá respetar el límite final.

No se redimensionará una imagen que supere el límite absoluto de resolución.

### 15.6. Compresión

Cuando una imagen supere los 5 MiB, pero se encuentre dentro del límite absoluto, se intentará reducir su peso.

La compresión podrá combinarse con el redimensionamiento.

El proceso tendrá un número limitado de intentos.

Si se obtiene una imagen válida y compatible con los límites finales, la consulta podrá continuar.

La adaptación satisfactoria no constituirá un error.

### 15.7. Casos de error

| HTTP | Código | Situación |
|---|---|---|
| 403 | INSUFFICIENT_PERMISSIONS | Rol sin autorización multimodal |
| 413 | IMAGE_FILE_TOO_LARGE | Supera el límite absoluto o no puede adaptarse el peso |
| 422 | IMAGE_RESOLUTION_EXCEEDED | Supera el límite absoluto o no puede adaptarse la resolución |
| 422 | IMAGE_CORRUPTED | Imagen vacía, corrupta o ilegible |
| 422 | IMAGE_CONTENT_NOT_ALLOWED | Contenido no permitido |
| 415 | IMAGE_FORMAT_NOT_ALLOWED | Formato no admitido |

Los fallos técnicos de identificación respetarán el catálogo general de errores.

No se devolverá un error de formato o resolución cuando la causa real sea una excepción interna no relacionada con el archivo.

### 15.8. Archivos temporales

Las imágenes podrán almacenarse temporalmente en:

```text
assets/.api_temporal/
```

La ubicación será compatible con las restricciones existentes de acceso a archivos.

Los nombres serán generados por el backend.

No se utilizará directamente el nombre original proporcionado por el cliente.

No se aceptarán rutas locales proporcionadas por consumidores externos.

El directorio temporal quedará excluido del control de versiones.

### 15.9. Eliminación

Los archivos temporales deberán eliminarse cuando ninguna ejecución pueda seguir utilizándolos.

En caso de timeout, no se eliminarán prematuramente si el worker continúa utilizándolos.

El mecanismo de limpieza será seguro ante ejecuciones normales, excepciones y resultados tardíos.

Los checkpoints de peticiones HTTP no conservarán referencias a archivos temporales que puedan volver a utilizarse después de su eliminación.

El backend podrá realizar una limpieza controlada de archivos abandonados durante el inicio, antes de admitir nuevas ejecuciones.

### 15.10. Privacidad

No se conservarán permanentemente las imágenes recibidas.

No se registrará su contenido binario.

La imagen preparada para identificación no deberá conservar metadatos innecesarios, incluyendo EXIF y coordenadas GPS.

No se incorporarán imágenes de consumidores al corpus documental.

### 15.11. Contrato de identificación multimodal

Se utilizará el siguiente contrato interno:

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

TypedDict describirá la estructura esperada, pero no sustituirá las validaciones en tiempo de ejecución.

La respuesta obtenida de Gemini deberá validarse mediante Python.

Se comprobará:

- La existencia de los campos requeridos.
- Los tipos de datos.
- Los valores permitidos de estado.
- La validez de descripcion.
- La ausencia de una estructura incompatible con el contrato.

La descripción representará una observación visual.

No constituirá por sí sola evidencia documental para determinar dónde depositar el residuo.

### 15.12. Admisibilidad semántica

| Estado | HTTP | Ejecuta LangGraph |
|---|---|---|
| allowed | Según resultado posterior | Sí |
| out_of_domain | 200 | No |
| policy_violation | 422 | No |
| uncertain | 200 | No |

out_of_domain devolverá una abstención controlada.

uncertain devolverá una solicitud controlada de una nueva imagen.

policy_violation devolverá IMAGE_CONTENT_NOT_ALLOWED.

Una imagen técnicamente válida no se considerará automáticamente admisible.

Los controles semánticos constituyen una medida de protección, pero no garantizan una clasificación infalible.

### 15.13. Fallos técnicos de identificación

No se utilizará uncertain como valor de respaldo cuando:

- Gemini produzca una excepción.
- Gemini no devuelva una respuesta válida.
- La salida estructurada incumpla el contrato.
- No pueda completarse la operación por un fallo técnico.

Se utilizará el código HTTP correspondiente:

| Situación | HTTP |
|---|---|
| Resultado incompatible con el contrato | 500 |
| Fallo interno inesperado | 500 |
| Dependencia temporalmente indisponible | 503 |
| Configuración imprescindible ausente | 503 |
| Timeout global | 504 |

Estos casos no se presentarán como abstenciones semánticas satisfactorias.

### 15.14. Interrupción del flujo

Cuando la identificación determine que una imagen no debe admitirse:

- No se ejecutará LangGraph.
- No se consultará ChromaDB.
- No se consultará ArcGIS.
- No se ejecutarán llamadas posteriores de síntesis.
- No se generará HITL.
- No se incrementarán turnos_consumidos.
- No se persistirán mensajes.
- No se creará una conversación nueva.

La cuota comercial correspondiente a la identificación visual ya ejecutada permanecerá consumida.

### 15.15. Reutilización de la identificación

La identificación multimodal admitida se proporcionará al agente mediante el parámetro interno identificacion_imagen.

No se proporcionará simultáneamente una ruta de imagen para volver a ejecutar la identificación.

El agente reutilizará la descripción validada.

No se simulará una segunda ejecución de describir_imagen.

Se conservará el contrato textual de la herramienta existente para la compatibilidad con la CLI.

La descripción visual no permitirá realizar búsquedas abiertas en Internet ni consultar fuentes documentales adicionales.

El conocimiento documental continuará limitado al corpus autorizado y los resultados geográficos a ArcGIS y su respaldo local.

## 16. Gestión centralizada de errores

FastAPI utilizará manejadores de excepciones para generar respuestas homogéneas.

El formato público será ErrorOut, definido en [12-contratos-http.md](12-contratos-http.md).

### 16.1. Clasificación

| Código HTTP | Categoría |
|---|---|
| 400 | Petición que incumple una regla de negocio de entrada |
| 401 | Autenticación |
| 403 | Autorización |
| 404 | Recursos inexistentes o inaccesibles |
| 409 | Conflictos de estado |
| 413 | Tamaño excesivo de archivo |
| 415 | Formato multimedia no admitido |
| 422 | Validación |
| 429 | Límites de consumo |
| 500 | Fallos internos o contratos de resultado inválidos |
| 503 | Dependencia, configuración o capacidad no disponible |
| 504 | Timeout del asistente |

Una pregunta vacía después de aplicar strip() devolverá HTTP 400 EMPTY_QUESTION.

Los incumplimientos estructurales del modelo de entrada devolverán HTTP 422.

### 16.2. Excepciones inesperadas

Las excepciones no previstas deberán transformarse en:

- HTTP 500.
- INTERNAL_SERVER_ERROR.

No se devolverán:

- Stack traces.
- Rutas internas.
- Consultas SQL.
- Variables de entorno.
- Credenciales.
- Excepciones completas de proveedores.
- Información que facilite accesos no autorizados.

Las excepciones podrán registrarse internamente de forma sanitizada.

Los manejadores de validación no deberán reproducir los valores sensibles de la petición original.

### 16.3. Prevención de falsos éxitos HTTP

El material académico del Sprint 15 advierte que una respuesta HTTP 200 puede ocultar un fallo técnico del agente.

Para evitarlo, el backend comprobará el resultado antes de construir AskOut.

No se devolverá HTTP 200 cuando:

- El agente contenga un error técnico.
- El resultado incumpla el contrato.
- LangGraph no alcance el HITL obligatorio.
- El checkpoint resulte incoherente.
- La identificación multimodal no pueda validarse.
- Falle una dependencia imprescindible para completar la operación.
- No pueda confirmarse una persistencia obligatoria.
- Se supere el timeout.

Todas las respuestas AskOut satisfactorias contendrán:

```json
{
    "error": null
}
```

El campo error no se utilizará para transportar fallos técnicos dentro de una respuesta HTTP 200.

### 16.4. Resultados semánticos válidos

No constituirán necesariamente errores HTTP:

- Una abstención por ausencia real de evidencia.
- Una aclaración correctamente generada.
- Una búsqueda geográfica legítimamente vacía.
- Una imagen fuera de dominio.
- Una identificación visual incierta.
- Un plan rechazado por el consumidor.
- Un HITL pendiente válido.
- El uso satisfactorio del respaldo geográfico local.

Los resultados semánticos obtenidos dentro de LangGraph conservarán el HITL obligatorio.

Las respuestas previas al agente no necesitarán HITL.

### 16.5. Fallos del RAG y de herramientas

La ausencia de evidencia documental deberá distinguirse de la imposibilidad técnica de obtenerla.

Una búsqueda legítima sin resultados podrá generar una abstención.

Un fallo técnico de ChromaDB, Gemini o una herramienta no se convertirá automáticamente en una abstención satisfactoria.

Si existe un mecanismo de recuperación autorizado y este permite completar correctamente la operación, podrá devolverse un resultado válido con las limitaciones correspondientes.

Si no puede completarse la operación requerida, se devolverá el error técnico correspondiente.

### 16.6. Fallos geográficos

El respaldo local podrá utilizarse cuando falle técnicamente ArcGIS.

Una respuesta vacía válida de ArcGIS no activará automáticamente el respaldo.

No se considerará una búsqueda vacía legítima cuando existan registros recibidos pero todos resulten inválidos durante la normalización.

En ese caso deberá tratarse el problema como un fallo de la fuente y aplicar el respaldo cuando corresponda.

Si ArcGIS y el respaldo local no permiten completar la operación, se devolverá el error técnico adecuado.

### 16.7. Validación de resultados

La capa de servicios comprobará:

- La ausencia de errores técnicos.
- La coherencia del estado.
- La validez del HITL.
- La estructura de las fuentes.
- La estructura de los resultados geográficos.
- La conformidad con AskOut.

No se eliminarán silenciosamente campos o referencias imprescindibles para transformar un resultado inválido en un éxito aparente.

No se utilizarán mensajes arbitrarios generados por el LLM para decidir códigos HTTP.

### 16.8. Errores de conexión del cliente

La pérdida de una respuesta HTTP no se interpretará automáticamente como un error concreto del backend.

Streamlit deberá diferenciar:

- Una respuesta HTTP de error recibida.
- Un timeout del cliente.
- Un fallo de conexión.
- Una respuesta inválida o incompleta.
- Un resultado cuya ejecución no puede confirmarse.

No se repetirán automáticamente peticiones POST cuyo resultado sea desconocido.

## 17. Consistencia entre LangGraph y PostgreSQL

MemorySaver y PostgreSQL constituirán sistemas de almacenamiento independientes.

No existirá una transacción atómica compartida entre ambos.

### 17.1. Persistencia correcta

Un turno del agente correctamente aprobado o rechazado deberá persistirse antes de devolver una respuesta HTTP satisfactoria.

Los dos mensajes correspondientes se almacenarán dentro de una misma transacción.

Se utilizará turnos_consumidos como origen de turn_number.

### 17.2. Fallo de PostgreSQL

Si PostgreSQL no permite confirmar la persistencia obligatoria de un turno:

- No se devolverá HTTP 200.
- Se ejecutará rollback cuando corresponda.
- Se registrará el fallo.
- Se protegerá el estado operativo del agente.

No se asumirá automáticamente que una transacción se ha revertido cuando la conexión se pierda durante la confirmación del commit.

No se repetirá automáticamente una escritura cuyo resultado sea desconocido.

### 17.3. Checkpoint inconsistente

Si una ejecución modifica el checkpoint pero no puede completar correctamente las operaciones obligatorias posteriores, la conversación deberá invalidarse cuando no pueda garantizarse su consistencia.

La invalidación se mantendrá en memoria.

Los intentos posteriores de reutilización recibirán THREAD_STATE_LOST.

No se reconstruirá automáticamente el checkpoint.

### 17.4. Resultados tardíos

Si una ejecución termina después de haberse comunicado HTTP 504, su resultado no se persistirá.

La ejecución costosa y la decisión definitiva de persistencia permanecerán desacopladas.

La finalización tardía no se considerará una nueva operación satisfactoria.

### 17.5. Revocación durante una ejecución

Antes de entregar resultados y persistir turnos se comprobarán las condiciones de autorización aplicables.

Una credencial revocada no deberá recibir nuevos resultados como si continuara autorizada.

Las comprobaciones y escrituras deberán coordinarse con las operaciones administrativas concurrentes.

La revocación no garantizará la interrupción inmediata de las llamadas externas ya iniciadas.

### 17.6. Reinicio del backend

Después de reiniciar FastAPI:

- Los mensajes SQL permanecerán disponibles.
- Las conversaciones permanecerán almacenadas.
- Las API keys permanecerán almacenadas.
- Los checkpoints de MemorySaver se perderán.
- Las aprobaciones pendientes se perderán.
- Las sesiones en memoria se perderán.
- Los contadores temporales se reiniciarán.
- El índice vectorial deberá estar disponible o reconstruirse conforme a la estrategia de despliegue.

El historial SQL no permitirá reconstruir automáticamente las conversaciones operativas.

## 18. Observabilidad

### 18.1. Objetivo

Permitir identificar el comportamiento del backend, diagnosticar errores, medir tiempos de respuesta y comprobar el resultado real de las operaciones HTTP.

La observabilidad deberá permitir diferenciar:

- Éxito HTTP.
- Resultado funcional.
- Suficiencia de evidencia.
- Consumo de recursos.
- Finalización real de una ejecución.

### 18.2. Identificador de petición

Cada petición HTTP recibirá un request_id único generado por el backend.

Se utilizará un UUID.

El identificador se incluirá en los registros de acceso y eventos técnicos correspondientes.

Se devolverá mediante:

```http
X-Request-ID: <request_id>
```

También formará parte de ErrorOut cuando se produzca un error.

request_id identificará una petición HTTP.

thread_id identificará una conversación.

Una conversación podrá estar asociada a múltiples request_id.

### 18.3. Registro por petición

Se generará un registro estructurado al finalizar cada petición atendida por el middleware de observabilidad.

| Campo | Tipo | Descripción |
|---|---|---|
| timestamp | datetime | Fecha UTC |
| request_id | str | Identificador de petición |
| method | str | Método HTTP |
| path | str | Patrón de ruta |
| thread_id | str o None | Conversación autorizada, cuando corresponda |
| api_key_id | str o None | Identificador de credencial |
| role | str o None | Rol autenticado |
| duration_ms | float | Duración |
| status_code | int | Código HTTP |
| error_code | str o None | Código del error correspondiente |

Las peticiones rechazadas antes de autenticarse tendrán valores nulos en los campos de identidad.

No se registrará como conversación autorizada un identificador recibido cuyo acceso no haya sido comprobado.

Se utilizará preferentemente el patrón de ruta definido por FastAPI.

No se registrarán parámetros sensibles de la URL.

### 18.4. Ejemplo

```json
{
    "timestamp": "2026-11-25T18:30:00Z",
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "method": "POST",
    "path": "/ask",
    "thread_id": "550e8400-e29b-41d4-a716-446655440001",
    "api_key_id": "550e8400-e29b-41d4-a716-446655440002",
    "role": "free",
    "duration_ms": 1254.38,
    "status_code": 200,
    "error_code": null
}
```

Este ejemplo representa únicamente el formato previsto.

No corresponde a una ejecución real.

### 18.5. Medición de duración

Se utilizará time.perf_counter() para medir el tiempo transcurrido durante una petición.

```python
start = time.perf_counter()

# Procesamiento de la petición.

duration_ms = (
    time.perf_counter() - start
) * 1000
```

El temporizador deberá comenzar antes de las operaciones que se desean medir.

La medición incluirá las peticiones que terminen en error.

duration_ms representará la duración observada hasta preparar o emitir la respuesta correspondiente, según la implementación del middleware.

No representará necesariamente la duración real del worker cuando exista un timeout.

### 18.6. Niveles de logging

| Nivel | Uso |
|---|---|
| DEBUG | Diagnóstico durante desarrollo |
| INFO | Operaciones correctas y eventos ordinarios |
| WARNING | Peticiones rechazadas y situaciones recuperables |
| ERROR | Fallos técnicos y errores internos |

El nivel será configurable mediante LOG_LEVEL.

En producción se utilizará inicialmente INFO.

### 18.7. Eventos técnicos adicionales

Podrán registrarse eventos estructurados relacionados con:

- Inicio del backend.
- Cierre del backend.
- Inicio de una ejecución del asistente.
- Finalización real de una ejecución.
- Capacidad agotada.
- Timeouts.
- Resultados tardíos descartados.
- Checkpoints invalidados.
- Fallos de persistencia.
- Fallos de proveedores externos.
- Uso del respaldo geográfico.
- Incidencias de archivos temporales.
- Adaptaciones de imágenes.
- Revocaciones de credenciales.

Los eventos deberán conservar el request_id correspondiente cuando exista.

Una ejecución tardía podrá generar un evento de finalización real después de haberse registrado HTTP 504.

Este evento no modificará el código HTTP previamente devuelto.

### 18.8. Resultado funcional

La observabilidad deberá permitir distinguir resultados como:

- HITL pendiente.
- Turno aprobado.
- Turno rechazado.
- Abstención válida.
- Aclaración válida.
- Rechazo previo por dominio.
- Imagen no admitida.
- Fallo técnico.

Podrá utilizarse un campo adicional de resultado funcional o eventos estructurados equivalentes.

No será necesario almacenar el texto de la pregunta ni de la respuesta para obtener esta información.

### 18.9. Información prohibida

No se registrarán:

- Contraseñas.
- API keys originales.
- Tokens de sesión.
- Hashes de credenciales.
- Cadenas de conexión.
- Credenciales de Gemini.
- Cuerpos completos de peticiones.
- Preguntas y respuestas completas del consumidor.
- Descripciones visuales completas.
- Archivos binarios.
- Coordenadas personales.
- Prompts internos.
- Cabeceras de autenticación.
- URLs completas que contengan información sensible.
- Contenido completo de documentos recuperados.

La protección deberá aplicarse también a los registros de las bibliotecas utilizadas.

Los errores no deberán reproducir secretos mediante representaciones completas de excepciones o modelos.

## 19. Métricas operativas y calidad

### 19.1. Métricas HTTP

| Métrica | Finalidad |
|---|---|
| Número de peticiones | Medir utilización |
| Distribución por endpoint | Identificar operaciones más utilizadas |
| Latencia media | Evaluar rendimiento |
| Percentil 95 de latencia | Detectar respuestas lentas |
| Tasa de respuestas 2xx | Evaluar resultados HTTP |
| Tasa de respuestas 4xx | Detectar errores y restricciones |
| Tasa de respuestas 5xx | Detectar fallos técnicos |
| Número de respuestas 429 | Evaluar límites |
| Número de respuestas 504 | Evaluar timeouts |
| Número de respuestas SERVER_BUSY | Evaluar capacidad |

### 19.2. Métricas de ejecución

Cuando resulte posible sin exponer información sensible, se podrán obtener:

- Número de ejecuciones admitidas.
- Número de ejecuciones simultáneas.
- Duración real de las ejecuciones.
- Número de ejecuciones tardías.
- Número de llamadas al modelo.
- Número de llamadas a herramientas.
- Consumo de tokens cuando el proveedor facilite estos datos.
- Número de usos del respaldo geográfico.

La devolución de una respuesta HTTP por timeout no constituirá necesariamente la finalización real de la ejecución.

### 19.3. Métricas funcionales

Se diferenciarán:

- Turnos con HITL pendiente.
- Turnos aprobados.
- Turnos rechazados.
- Abstenciones.
- Aclaraciones.
- Resultados con evidencia suficiente.
- Resultados con evidencia parcial.
- Resultados con evidencia insuficiente.

Una respuesta HTTP 200 no se interpretará automáticamente como una respuesta documentalmente correcta.

Una aprobación del usuario tampoco demostrará por sí sola la calidad factual del resultado.

### 19.4. Evaluación de calidad

La calidad del RAG y del agente deberá evaluarse mediante las pruebas y conjuntos de preguntas correspondientes.

Las métricas HTTP no sustituirán:

- Evaluación de retrieval.
- Validación de referencias.
- Comprobación de abstenciones.
- Evaluación de respuestas.
- Verificación de regresiones.
- Evaluación del consumo.

### 19.5. Obtención de métricas

Las métricas podrán obtenerse inicialmente mediante el análisis de logs y resultados de pruebas.

No será necesario incorporar un nuevo endpoint de métricas.

Prometheus, Grafana y sistemas externos de monitorización quedan fuera del alcance inicial.

## 20. Health check

GET /health permitirá comprobar la disponibilidad del servicio.

### 20.1. Comprobaciones

- Disponibilidad del backend.
- Configuración imprescindible.
- Conectividad real con PostgreSQL.
- Disponibilidad del índice vectorial requerido.

No será suficiente comprobar que existen objetos Python correspondientes al engine o a ChromaDB.

### 20.2. Restricciones

El health check no deberá:

- Ejecutar LangGraph.
- Generar embeddings.
- Invocar Gemini.
- Consultar ArcGIS.
- Consumir cuota comercial.
- Requerir API key.
- Exponer secretos.

Las comprobaciones serán ligeras y tendrán tiempos máximos de espera.

### 20.3. Resultado satisfactorio

```json
{
    "status": "ok",
    "storage": "postgres"
}
```

HTTP 200 únicamente cuando se cumplan las comprobaciones requeridas.

### 20.4. Dependencias no disponibles

Cuando falte una configuración imprescindible o una dependencia requerida no esté disponible, se devolverá HTTP 503 mediante ErrorOut.

No se declarará falsamente que el servicio se encuentra operativo.

Si la configuración impide completamente iniciar FastAPI, el servicio podrá no estar disponible para responder al health check.

### 20.5. Alcance

GET /health no garantizará que Gemini o ArcGIS respondan correctamente a una consulta posterior.

Tampoco constituirá una comprobación de disponibilidad inmediata de un worker.

La falta temporal de capacidad del asistente se comunicará mediante SERVER_BUSY.

## 21. CORS

La política CORS se configurará mediante CORSMiddleware de FastAPI.

### 21.1. Principios

- Permitir únicamente los orígenes necesarios.
- Evitar configuraciones indiscriminadas en producción.
- Permitir los métodos y cabeceras requeridos.
- No utilizar CORS como sustituto de autenticación.
- No utilizar CORS como mecanismo de autorización.

### 21.2. Orígenes

Los orígenes permitidos se obtendrán de CORS_ORIGINS.

Se utilizará una lista explícita de orígenes autorizados.

No se habilitarán indiscriminadamente todos los orígenes en producción.

### 21.3. Métodos

Se permitirán los métodos necesarios:

- GET.
- POST.
- PATCH.
- DELETE.

Las peticiones OPTIONS preflight serán gestionadas por CORSMiddleware.

### 21.4. Cabeceras

Se contemplarán:

- Content-Type.
- X-API-Key.
- Authorization.
- X-API-Key-Id.

Se expondrán cuando corresponda:

- X-Request-ID.
- Retry-After.

### 21.5. Credenciales

Se utilizará inicialmente:

```python
allow_credentials = False
```

La arquitectura inicial no utilizará cookies de autenticación cross-origin.

Las cabeceras de autenticación necesarias deberán estar expresamente permitidas.

### 21.6. Streamlit y Swagger

Cuando Streamlit realiza peticiones HTTP desde su proceso Python hacia FastAPI, CORS no interviene directamente.

CORS regula restricciones aplicadas por navegadores entre diferentes orígenes.

Swagger servido desde el mismo origen que FastAPI tampoco necesita acceso cross-origin.

Una política CORS restrictiva no impide que un cliente HTTP autorizado se comunique directamente con el backend.

### 21.7. Preflight

Las peticiones preflight no requerirán autenticación del producto.

No consumirán cuota comercial.

Las peticiones reales posteriores seguirán sujetas a autenticación, autorización y límites de consumo.

Los manejadores de errores y middleware deberán coordinarse para que las respuestas de la API respeten la política CORS aplicable.

## 22. Variables de entorno

| Variable | Valor inicial | Finalidad |
|---|---|---|
| RATE_LIMIT_PER_MINUTE | 30 | Límite HTTP general |
| FREE_RATE_LIMIT_PER_MINUTE | 2 | Cuota Free por minuto |
| FREE_RATE_LIMIT_PER_HOUR | 10 | Cuota Free por hora |
| FREE_RATE_LIMIT_PER_DAY | 30 | Cuota Free por 24 horas |
| USER_RATE_LIMIT_PER_MINUTE | 5 | Cuota User por minuto |
| USER_RATE_LIMIT_PER_HOUR | 20 | Cuota User por hora |
| USER_RATE_LIMIT_PER_DAY | 45 | Cuota User por 24 horas |
| AGENT_MAX_WORKERS | 1 | Capacidad simultánea inicial |
| ASK_TIMEOUT_SECONDS | 60 | Presupuesto inicial de ejecución |
| IMAGE_UPLOAD_MAX_BYTES | 20971520 | Peso absoluto del archivo |
| IMAGE_UPLOAD_MAX_PIXELS | 32000000 | Resolución absoluta |
| LOG_LEVEL | INFO | Nivel de logging |
| CORS_ORIGINS | Según entorno | Orígenes permitidos |

Los límites de registro, autenticación y emisión también se centralizarán en la configuración del backend.

Las variables de autenticación se establecen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

### 22.1. Validación de configuración

Los valores se validarán durante el inicio del servicio.

No se admitirán:

- Valores negativos.
- Duraciones inválidas.
- Capacidades iguales o inferiores a cero.
- Límites incompatibles entre sí.
- Configuraciones de seguridad incoherentes.
- Valores incompatibles con las restricciones del núcleo.

La configuración de despliegue deberá preservar un único proceso de Uvicorn.

### 22.2. Documentación

Las variables se documentarán en .env.example.

No se incluirán secretos reales.

Los valores pendientes de calibración se identificarán como configuraciones iniciales.

## 23. Pruebas de robustez

### 23.1. Rate limiting HTTP

- Peticiones dentro del límite.
- Superación del límite.
- Recuperación de capacidad.
- Independencia entre API keys.
- Contadores equivalentes entre modalidades de autenticación.
- Aplicación a claves Admin.
- Exclusión de /health.
- Ausencia de consumo comercial en consultas de historial.
- Peticiones autenticadas rechazadas posteriormente.
- Cálculo correcto de Retry-After.

### 23.2. Cuotas comerciales

- Límites por minuto.
- Límites por hora.
- Límites por 24 horas.
- Ventanas deslizantes.
- Comprobación de límites simultáneos.
- Independencia entre credenciales.
- Cuota compartida entre /ask y /ask/image.
- Ausencia de consumo adicional en /approve.
- Contabilización de identificaciones multimodales rechazadas.
- Consumo en ejecuciones admitidas que terminan en error.
- Ausencia de consumo en operaciones no admitidas.
- Operaciones concurrentes sin superar cuotas.
- Cálculo de Retry-After para varias ventanas agotadas.

### 23.3. Filtrado previo

- Admisión de consultas del dominio.
- Abstención determinista fuera de dominio.
- Aclaraciones previas.
- Consultas dependientes del contexto.
- Reformulaciones.
- Falsos positivos y negativos.
- Ausencia de llamadas a Gemini y LangGraph tras un rechazo previo.
- Ausencia de consumo comercial.
- Ausencia de incremento de turnos.
- Ausencia de mensajes SQL.
- Ausencia de creación de conversaciones innecesarias.
- Respeto de restricciones de conversaciones existentes.

### 23.4. Seguridad y credenciales

- Límites de registro.
- Límites de autenticación.
- Límites de emisión.
- Emisión concurrente de claves.
- Reactivación respetando claves activas máximas.
- Rechazo de credenciales incorrectas.
- Revocación durante una ejecución.
- Ausencia de exposición de secretos.

### 23.5. Concurrencia

- Atención concurrente de peticiones HTTP.
- Una única ejecución simultánea con la configuración inicial.
- Rechazo de modificaciones simultáneas del mismo hilo.
- Respuesta THREAD_BUSY.
- Respuesta SERVER_BUSY.
- Ausencia de consumo comercial ante falta de capacidad.
- Ausencia de acumulación de tareas en cola.
- Liberación correcta ante excepciones.
- Conservación de capacidad durante resultados tardíos.
- Liberación de recursos exactamente una vez.
- Ausencia de bloqueos prolongados del event loop.

### 23.6. Timeout

- Ejecución dentro del presupuesto.
- Ejecución superior al presupuesto.
- Timeout durante identificación multimodal.
- Timeout durante LangGraph.
- Timeout durante aprobación automática.
- Presupuesto compartido entre fases.
- Nuevo presupuesto para aprobación manual.
- Ausencia de timeout durante la decisión humana.
- Conservación de bloqueos.
- Conservación de capacidad.
- Descarte de resultados tardíos.
- Ausencia de persistencia tardía.
- Invalidación de checkpoints inconsistentes.
- Limpieza segura de imágenes.

### 23.7. HITL

- HITL obligatorio en ejecuciones satisfactorias.
- auto_aprobar=False devuelve aprobación pendiente.
- auto_aprobar=True utiliza la resolución real.
- Aprobación válida.
- Rechazo válido.
- Aprobaciones concurrentes.
- Aprobaciones repetidas.
- Identificadores de aprobación obsoletos.
- Resolución del último turno permitido.
- Ausencia de incremento del contador al resolver HITL.
- Ausencia de mensajes SQL mientras el plan permanece pendiente.

### 23.8. Imágenes

- Imagen JPEG válida.
- Imagen PNG válida.
- Formato no admitido.
- Imagen corrupta.
- Archivo vacío.
- Imagen animada.
- Redimensionamiento correcto.
- Compresión correcta.
- Superación del límite absoluto de peso.
- Superación del límite absoluto de resolución.
- Archivo recibido sin Content-Length fiable.
- Eliminación de metadatos.
- Limpieza de archivos temporales.
- Identificación admitida.
- Identificación fuera de dominio.
- Identificación incierta.
- Contenido no permitido.
- Resultado estructurado inválido.
- Ausencia de llamadas posteriores tras un rechazo semántico.
- Ausencia de identificación multimodal duplicada.
- Contabilización comercial correcta.

### 23.9. Prevención de falsos éxitos

- El agente devuelve un error técnico.
- El agente devuelve una estructura incompatible.
- LangGraph termina sin HITL obligatorio.
- Gemini devuelve JSON inválido.
- Gemini no está disponible.
- ChromaDB falla.
- ArcGIS y el respaldo local fallan.
- Todos los registros geográficos recibidos son inválidos.
- PostgreSQL falla al persistir un turno.
- La confirmación de un commit resulta desconocida.
- Una ejecución supera el timeout.
- Una abstención documental legítima se procesa correctamente.
- Una búsqueda geográfica vacía legítima se procesa correctamente.
- Un plan rechazado se registra correctamente.

En los casos de fallo técnico se verificará que no se devuelve HTTP 200.

En los casos satisfactorios se comprobarán tanto el código HTTP como las invariantes funcionales.

### 23.10. Observabilidad

- Generación de request_id.
- Cabecera X-Request-ID.
- Correspondencia entre ErrorOut y el registro.
- Registro de operaciones satisfactorias.
- Registro de errores 4xx y 5xx.
- Medición de duración.
- Diferenciación entre finalización HTTP y finalización real.
- Registro de resultados tardíos.
- Ausencia de secretos en logs.
- Ausencia de información sensible en errores de validación.

### 23.11. Health check y CORS

- /health sin autenticación.
- /health sin consumo de Gemini.
- /health con PostgreSQL disponible.
- /health con PostgreSQL indisponible.
- /health con ChromaDB indisponible.
- CORS con origen autorizado.
- CORS con origen no autorizado.
- Preflight sin autenticación.
- Cabeceras necesarias permitidas.
- Cabeceras de trazabilidad expuestas.

### 23.12. Estrategia de pruebas

Se utilizarán:

- Mocks.
- Relojes simulados.
- Dependencias controladas.
- Ejecuciones bloqueantes simuladas.
- Barreras o eventos de sincronización.
- PostgreSQL de pruebas cuando corresponda.

Las pruebas no dependerán innecesariamente de llamadas reales a Gemini.

Las pruebas de rate limiting HTTP podrán utilizar endpoints de historial con una credencial autorizada.

Las pruebas de concurrencia y timeout deberán comprobar la liberación real de recursos, no únicamente el código HTTP devuelto.

## 24. Criterios de aceptación

### 24.1. Consumo y seguridad

- El backend aplica rate limiting HTTP.
- Las cuotas Free y User respetan los límites.
- Admin mantiene límites técnicos.
- Las cuotas son independientes por API key.
- Las dos modalidades de autenticación de una clave comparten contadores.
- Las comprobaciones de consumo son atómicas.
- POST /ask y POST /ask/image comparten cuota.
- POST /approve no consume una nueva consulta comercial.
- La emisión de claves está limitada.
- El agotamiento de límites devuelve HTTP 429.
- Retry-After corresponde a la ventana aplicable.
- Los secretos no se utilizan como identificadores de consumo.

### 24.2. Contabilización y persistencia

- turnos_consumidos aumenta únicamente al iniciar LangGraph.
- Resolver HITL no incrementa turnos_consumidos.
- turn_number procede del contador del agente.
- Las respuestas anteriores a LangGraph no generan mensajes SQL.
- Los planes pendientes no se persisten como turnos resueltos.
- Los turnos aprobados y rechazados se almacenan atómicamente.
- Los resultados tardíos no se almacenan.

### 24.3. Concurrencia

- No se producen modificaciones concurrentes del mismo checkpoint.
- Solo se permite una ejecución simultánea con la configuración inicial.
- Las peticiones del mismo hilo ocupado reciben THREAD_BUSY.
- Las peticiones sin capacidad disponible reciben SERVER_BUSY.
- Los rechazos por falta de capacidad no consumen cuota comercial.
- No se acumulan consultas en una cola de espera.
- La finalización HTTP por timeout no libera prematuramente recursos.
- Los bloqueos se liberan de forma segura.

### 24.4. Timeout

- El timeout es configurable.
- La identificación visual comparte presupuesto con LangGraph.
- La aprobación automática comparte presupuesto con la consulta.
- La aprobación manual dispone de un nuevo presupuesto.
- El tiempo de decisión humana no consume el presupuesto del asistente.
- El timeout devuelve HTTP 504.
- Los resultados tardíos se descartan.
- Los checkpoints inconsistentes no pueden reutilizarse.

### 24.5. HITL

- Se conserva el HITL obligatorio.
- Las aprobaciones se validan contra el checkpoint real.
- Las aprobaciones obsoletas no modifican el estado.
- Las aprobaciones duplicadas no generan mensajes duplicados.
- El último turno permitido puede resolver su HITL.
- Una finalización inesperada sin HITL no devuelve un falso éxito.

### 24.6. Multimodalidad

- Las imágenes se adaptan cuando resulta posible.
- Los límites absolutos se aplican antes de operaciones costosas.
- Las imágenes inválidas se rechazan.
- Las imágenes pasan una identificación semántica estructurada.
- Las imágenes no admitidas no ejecutan LangGraph.
- Los fallos técnicos no se convierten en incertidumbre semántica.
- La identificación admitida se reutiliza.
- No se realizan identificaciones visuales duplicadas.
- Las identificaciones ejecutadas consumen cuota comercial.
- Los archivos temporales se eliminan de forma segura.

### 24.7. Errores y resultados

- Los errores respetan ErrorOut.
- Una pregunta vacía recibe HTTP 400.
- Los contratos de entrada inválidos reciben HTTP 422.
- Los conflictos de estado reciben HTTP 409.
- Los fallos técnicos no se presentan mediante HTTP 200.
- Toda respuesta AskOut satisfactoria contiene error=None.
- Las abstenciones legítimas no se confunden con fallos técnicos.
- Las búsquedas vacías legítimas se distinguen de los fallos de fuentes.
- Los fallos de persistencia no generan respuestas satisfactorias.
- No se realizan reintentos POST automáticos cuando el resultado sea desconocido.

### 24.8. Observabilidad

- Las peticiones disponen de request_id.
- Las respuestas incluyen X-Request-ID.
- Los registros contienen duración y código HTTP.
- Los registros permiten identificar fallos técnicos.
- Se distingue la finalización HTTP de la finalización real.
- Se pueden obtener métricas operativas a partir de los registros.
- El éxito HTTP no se interpreta automáticamente como calidad documental.
- Los logs no contienen secretos.

### 24.9. Infraestructura

- GET /health no ejecuta el asistente.
- GET /health comprueba las dependencias requeridas.
- GET /health no declara una disponibilidad falsa.
- La política CORS es configurable.
- El backend utiliza un único proceso durante el PB03.
- Las limitaciones del almacenamiento en memoria están documentadas.
- El núcleo del PB02 conserva su independencia.
- Las pruebas pueden ejecutarse sin consumir innecesariamente recursos de Gemini.
- No se introducen servicios externos de monitorización, colas o contabilización fuera del alcance académico.