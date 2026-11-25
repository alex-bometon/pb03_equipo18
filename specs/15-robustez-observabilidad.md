# 15. Robustez y observabilidad

## 1. Objetivo

Garantizar la estabilidad, seguridad, disponibilidad y trazabilidad del backend de ReciclaTÍA mediante mecanismos deterministas de control de peticiones, consumo de recursos, concurrencia, tiempos de ejecución y gestión de errores.

Las medidas de protección se aplicarán independientemente del cliente utilizado para acceder a la API.

## 2. Principios generales

- Validar las entradas antes de ejecutar operaciones costosas.
- Limitar el consumo de recursos por consumidor.
- Proteger los servicios externos frente a peticiones excesivas.
- Controlar la concurrencia sobre recursos compartidos.
- Evitar modificaciones simultáneas de una misma conversación.
- Establecer tiempos máximos de ejecución.
- Gestionar los fallos de forma controlada.
- No confundir abstenciones semánticas con errores técnicos.
- Registrar información suficiente para diagnosticar incidencias.
- Evitar la exposición de información sensible.
- Mantener las decisiones de seguridad independientes del LLM.

## 3. Separación de responsabilidades

| Archivo | Responsabilidad |
|---|---|
| api/rate_limit.py | Cuotas, ventanas temporales y límites de peticiones |
| api/security.py | Autenticación y autorización |
| api/dependencies.py | Aplicación de controles reutilizables |
| api/service.py | Coordinación de operaciones y ejecución del asistente |
| api/images.py | Validación, adaptación y gestión temporal de imágenes |
| api/errors.py | Excepciones y respuestas HTTP homogéneas |
| api/main.py | Configuración, middleware y ciclo de vida del backend |
| api/config.py | Configuración específica del servicio HTTP |

La configuración de robustez del backend no deberá impedir el funcionamiento independiente de la CLI ni del sistema RAG.

## 4. Niveles de protección

Se establecerán cuatro niveles de control independientes.

| Nivel | Finalidad |
|---|---|
| Rate limiting HTTP | Proteger los endpoints frente a peticiones excesivas |
| Cuotas comerciales | Limitar las consultas al asistente según el rol |
| Límites de seguridad | Proteger el registro, la autenticación y la emisión de credenciales |
| Límites técnicos | Proteger la memoria, CPU, conexiones y capacidad de ejecución |

Superar cualquiera de estos controles puede impedir la ejecución de una operación.

Disponer de cuota comercial no garantiza que el servidor tenga capacidad técnica disponible.

## 5. Rate limiting HTTP

### 5.1. Objetivo

Limitar el número de peticiones HTTP realizadas contra los endpoints protegidos, independientemente de que impliquen llamadas al asistente.

Este mecanismo protege también las operaciones de consulta del historial y administración.

### 5.2. Identificación

Las operaciones autenticadas mediante API key se contabilizarán utilizando api_key.id.

Las operaciones realizadas mediante sesión y selección de API key utilizarán igualmente api_key.id.

Las operaciones exclusivamente relacionadas con la cuenta utilizarán user.id.

No se utilizarán los secretos originales como identificadores de los contadores.

### 5.3. Límite general

Se establece como configuración inicial propuesta un límite de 30 peticiones HTTP por minuto por identidad autenticada.

El límite será configurable mediante RATE_LIMIT_PER_MINUTE.

Este límite será aplicable también a las API keys Admin, ya que representa una medida de protección técnica y no una cuota comercial.

### 5.4. Endpoints excluidos

Los siguientes endpoints no consumirán el límite HTTP asociado a una API key:

- GET /health
- GET /docs
- GET /openapi.json

Los endpoints públicos de registro, autenticación y emisión de claves tendrán sus propios límites de seguridad.

La exclusión del limitador por API key no impide aplicar medidas generales de protección de infraestructura.

### 5.5. Superación del límite

Cuando se alcance el límite:

- No se ejecutará la operación solicitada.
- Se devolverá HTTP 429.
- Se utilizará el código RATE_LIMIT_EXCEEDED.
- Se incluirá Retry-After cuando pueda determinarse.
- No se consumirá cuota comercial del asistente.

## 6. Cuotas comerciales del asistente

### 6.1. Límites establecidos

| Rol | Por minuto | Por hora | Por 24 horas |
|---|---:|---:|---:|
| Free | 2 | 10 | 30 |
| User | 5 | 20 | 45 |
| Admin | Sin límite | Sin límite | Sin límite |

Las cuotas Free serán idénticas para consumidores anónimos y usuarios registrados.

Las cuotas se aplicarán individualmente a cada API key.

### 6.2. Endpoints que consumen cuota

| Endpoint | Consume cuota comercial |
|---|---|
| POST /ask | Sí |
| POST /ask/image | Sí |
| POST /approve | No |
| GET /threads | No |
| GET /threads/{thread_id} | No |
| GET /threads/{thread_id}/messages | No |
| Endpoints de cuenta | No |
| Endpoints administrativos | No |
| GET /health | No |

POST /ask y POST /ask/image compartirán los mismos contadores.

POST /approve no consume una nueva consulta comercial porque resuelve un turno previamente iniciado.

No obstante, estará sujeto a los límites HTTP, de concurrencia y de ejecución.

### 6.3. Momento de contabilización

Una consulta se contabilizará cuando haya superado las validaciones, los controles de autorización y los requisitos de admisión y vaya a comenzar la ejecución del asistente.

Se contabilizará antes de iniciar la ejecución para evitar que varias peticiones concurrentes superen simultáneamente el límite.

En las consultas multimodales, la cuota comercial se contabilizará antes de realizar la primera llamada de identificación semántica de la imagen.

### 6.4. Operaciones contabilizadas

| Situación | Consume cuota |
|---|---|
| Consulta válida ejecutada | Sí |
| Consulta multimodal ejecutada | Sí |
| Abstención por falta de evidencia | Sí |
| Consulta identificada como fuera de dominio antes de ejecutar el asistente | No |
| Consulta ambigua resuelta mediante una aclaración determinista previa | No |
| Solicitud de aclaración | Sí |
| Consulta que genera HITL | Sí |
| Consulta cuyo procesamiento termina en timeout | Sí |
| Fallo técnico después de iniciar la ejecución | Sí |
| Imagen identificada como fuera de dominio mediante Gemini | Sí |
| Imagen identificada como contenido no permitido mediante Gemini | Sí |
| Imagen no identificada después de realizar la llamada multimodal | Sí |
| Petición HTTP inválida | No |
| Credenciales incorrectas | No |
| Permisos insuficientes | No |
| Imagen inválida que no puede procesarse | No |
| Conversación ajena | No |
| Conversación cerrada | No |
| Conversación con HITL pendiente | No |
| Conversación ocupada | No |
| Capacidad técnica agotada antes de ejecutar | No |
| Cuota agotada | No |
| Aprobación o rechazo mediante POST /approve | No |

Las consultas textuales deberán superar un filtro de dominio previo a la ejecución del asistente y al consumo de cuota comercial.

Cuando una consulta se identifique inequívocamente como fuera de dominio, se devolverá una respuesta determinista sin invocar LangGraph, Gemini, el RAG ni las herramientas.

Las consultas ambiguas podrán recibir una solicitud de aclaración sin ejecutar el asistente.

Estas operaciones continuarán sujetas al rate limiting HTTP.

Se revisarán los filtros existentes de la fase de desarrollo anterior y se realizarán pruebas de falsos positivos, falsos negativos y continuidad conversacional antes de considerar finalizada la implementación.

No se devolverá automáticamente la cuota consumida por una ejecución que haya terminado en timeout o error técnico, ya que puede haber utilizado recursos y servicios externos.

## 7. Ventanas temporales deslizantes

### 7.1. Algoritmo

Se utilizará el algoritmo Sliding Window Log.

Cada identidad dispondrá de una estructura que registre los instantes de las operaciones contabilizadas.

Las estructuras principales serán:

- defaultdict.
- deque.
- Lock.
- time.monotonic().

### 7.2. Duración de las ventanas

| Ventana | Duración en segundos |
|---|---:|
| Minuto | 60 |
| Hora | 3600 |
| Día | 86400 |

Las ventanas serán deslizantes y no dependerán de cambios de minuto, hora o día del calendario.

### 7.3. Funcionamiento

1. Obtener el instante actual mediante time.monotonic().
2. Acceder al contador de la identidad.
3. Eliminar los registros que hayan salido de la ventana temporal más larga.
4. Calcular las operaciones realizadas dentro de cada ventana.
5. Comprobar todos los límites aplicables.
6. Rechazar la operación si alguno se ha alcanzado.
7. Registrar el instante de la nueva operación si todos permiten continuar.

Las operaciones de comprobación y registro deberán ejecutarse de manera atómica bajo un bloqueo.

No se mantendrá el bloqueo durante la ejecución del asistente.

### 7.4. Reloj monotónico

Se utilizará time.monotonic() para calcular intervalos temporales.

Este reloj no depende de ajustes manuales de la hora del sistema ni de sincronizaciones del reloj del sistema operativo.

No se utilizará para representar fechas almacenadas en PostgreSQL.

Las fechas de persistencia se almacenarán en UTC.

### 7.5. Retry-After

Cuando se alcance una cuota, se calculará el tiempo necesario para que exista capacidad disponible en todas las ventanas aplicables.

Si varias ventanas están agotadas, se utilizará el mayor tiempo de espera requerido.

Retry-After se expresará en segundos enteros, redondeados hacia arriba.

## 8. Almacenamiento de contadores

Los contadores del rate limiting y las cuotas comerciales se mantendrán en memoria durante esta fase de desarrollo.

No se incorporarán tablas adicionales para almacenar el consumo.

### 8.1. Ventajas

- Implementación sencilla.
- Baja latencia.
- Ausencia de consultas SQL adicionales por cada comprobación.
- Independencia de servicios externos como Redis.

### 8.2. Limitaciones

- Los contadores se reinician al reiniciar FastAPI.
- Los contadores no se comparten entre procesos.
- No representan un registro persistente de facturación.
- No permiten garantizar cuotas comerciales duraderas después de un redeploy.
- No establecen por sí solos un presupuesto global de consumo de Gemini.

Por este motivo, se utilizará un único proceso de Uvicorn.

Antes de implementar un modelo comercial de pago será necesario incorporar un mecanismo persistente y compartido de contabilización.

### 8.3. Limpieza

Los registros temporales caducados deberán eliminarse periódicamente.

Las identidades sin actividad dentro de sus ventanas temporales podrán retirarse de las estructuras de almacenamiento.

La memoria destinada a contadores deberá mantenerse bajo límites controlados.

## 9. Protección de registro, autenticación y emisión

Los endpoints públicos y de cuenta tendrán límites independientes de las cuotas comerciales.

### 9.1. Límites iniciales propuestos

| Operación | Límite inicial |
|---|---|
| Inicio de sesión por email normalizado | 5 intentos cada 15 minutos |
| Inicio de sesión por origen fiable | 20 intentos cada 15 minutos |
| Registro por origen fiable | 5 intentos por hora |
| Emisión de claves Free anónimas por origen fiable | 3 por hora y 5 por 24 horas |
| Emisión de claves registradas por usuario | 3 por hora y 5 por 24 horas |

Estos valores serán configurables y podrán ajustarse después de realizar pruebas.

### 9.2. Límites de claves activas

| Tipo de clave | Máximo |
|---|---:|
| Free registrada | 1 por usuario |
| User | 5 por usuario |
| Admin | Emisión interna restringida |

La emisión y sustitución de claves estarán limitadas independientemente del número de claves activas.

### 9.3. Identificación del origen

La dirección IP solo podrá utilizarse como identificador cuando se obtenga de una fuente fiable.

No se confiará directamente en cabeceras X-Forwarded-For proporcionadas por consumidores externos.

Las cabeceras de identificación del origen solo se aceptarán cuando procedan de un proxy conocido y correctamente configurado.

Cuando Streamlit realice peticiones al backend, la IP observada puede corresponder al servidor Streamlit y no al consumidor final.

En ese caso, se utilizarán los identificadores autenticados disponibles y límites globales de protección para las operaciones anónimas.

La identificación por IP no constituye una identificación inequívoca de una persona.

### 9.4. Limitaciones del acceso anónimo

Streamlit conservará la API key Free durante la sesión del consumidor.

No se emitirá una nueva clave para cada petición o rerun.

La recreación de sesiones anónimas puede permitir obtener nuevas credenciales dentro de los límites de emisión.

Esta limitación se documentará expresamente.

## 10. Control de concurrencia

### 10.1. Objetivo

Permitir que diferentes consumidores utilicen el asistente simultáneamente sin provocar inconsistencias en el estado de LangGraph.

### 10.2. Conceptos

El thread_id identifica una conversación del agente.

Un hilo de ejecución de Python representa una unidad de ejecución concurrente.

Ambos conceptos son independientes.

Una conversación puede ser atendida por diferentes hilos de ejecución de Python en peticiones sucesivas.

### 10.3. Bloqueo por conversación

Cada thread_id dispondrá de un mecanismo de exclusión mutua.

Las siguientes operaciones no podrán modificar simultáneamente la misma conversación:

- POST /ask
- POST /ask/image
- POST /approve

Las conversaciones diferentes podrán ejecutarse concurrentemente dentro de los límites globales del servidor.

### 10.4. Conversación ocupada

Si una petición intenta modificar una conversación que ya está siendo procesada:

- No se ejecutará una segunda modificación.
- Se devolverá HTTP 409.
- Se utilizará el código THREAD_BUSY.
- No se consumirá una nueva cuota comercial.

### 10.5. Duración del bloqueo

El bloqueo deberá mantenerse durante:

- La comprobación del checkpoint.
- La ejecución de LangGraph.
- La resolución automática del HITL, cuando corresponda.
- La transformación del resultado.
- La persistencia del turno resuelto.

Si se produce un timeout, el bloqueo no se liberará mientras una ejecución anterior pueda seguir modificando el estado.

### 10.6. Liberación de recursos

Los bloqueos deberán liberarse incluso cuando se produzcan excepciones.

Las estructuras utilizadas para gestionar bloqueos no deberán crecer indefinidamente.

Solo podrán eliminarse bloqueos que no estén siendo utilizados ni tengan operaciones pendientes.

## 11. Capacidad de ejecución del servidor

### 11.1. ThreadPoolExecutor

Las operaciones bloqueantes del asistente podrán ejecutarse mediante ThreadPoolExecutor.

Se propone utilizar un executor compartido durante la vida del backend.

No se creará un executor independiente para cada petición.

### 11.2. Número de workers

Se utilizará inicialmente un único worker en ThreadPoolExecutor.

```python
AGENT_MAX_WORKERS = 1
```

Esta configuración permite controlar el consumo de recursos, simplificar la gestión de concurrencia y reducir el riesgo de inconsistencias en los estados del asistente.

Solo podrá ejecutarse una operación del asistente simultáneamente.

El número de workers será configurable mediante una variable de entorno, permitiendo aumentarlo en el futuro después de realizar pruebas de rendimiento y estabilidad.

El worker de ThreadPoolExecutor es independiente del proceso de Uvicorn.

### 11.3. Control de admisión

Se utilizará un mecanismo adicional de admisión, como un semáforo, para limitar las ejecuciones simultáneas.

ThreadPoolExecutor por sí solo no garantiza una cola de tareas acotada.

En la primera versión no se mantendrá una cola ilimitada de consultas pendientes.

### 11.4. Capacidad agotada

Si el único worker del asistente está ocupado:

- No se iniciará una nueva ejecución.
- Se devolverá HTTP 503.
- Se utilizará el código SERVER_BUSY.
- No se consumirá cuota comercial.

El administrador estará sujeto a este mismo límite técnico.

## 12. Timeout

### 12.1. Objetivo

Evitar que una petición HTTP permanezca bloqueada indefinidamente esperando una respuesta del asistente o de un servicio externo.

### 12.2. Tiempo máximo

Se propone inicialmente:

```python
ASK_TIMEOUT_SECONDS = 60
```

El valor será configurable mediante variables de entorno.

El límite abarcará la ejecución completa del agente, incluyendo la resolución automática del HITL cuando corresponda.

Las operaciones manuales de POST /approve tendrán también un tiempo máximo de ejecución.

Las conexiones a PostgreSQL y los servicios externos deberán disponer de sus propios límites de espera.

### 12.3. Aplicación

La ejecución podrá controlarse mediante:

```python
future.result(timeout=ASK_TIMEOUT_SECONDS)
```

Cuando se alcance el tiempo máximo:

- Se devolverá HTTP 504.
- Se utilizará el código AGENT_TIMEOUT.
- No se devolverá una respuesta parcial como resultado satisfactorio.
- No se persistirá el turno como resuelto.

### 12.4. Limitaciones de la cancelación

Un timeout en future.result() no garantiza la interrupción de una función que ya se está ejecutando.

future.cancel() únicamente puede cancelar una tarea que todavía no haya comenzado.

Por tanto:

- El worker continuará ocupado mientras la ejecución siga activa.
- El bloqueo de la conversación deberá conservarse.
- Los archivos temporales necesarios deberán permanecer disponibles.
- El resultado tardío deberá descartarse.
- No deberá persistirse el turno fuera del flujo autorizado.
- La conversación no podrá reutilizarse hasta garantizar que su estado es seguro.

### 12.5. Conversaciones afectadas

Si un timeout o fallo técnico deja el checkpoint en un estado que no puede garantizarse como consistente, la conversación quedará marcada internamente como no reutilizable.

El historial previamente persistido seguirá disponible.

El usuario podrá iniciar una nueva conversación.

Se devolverá THREAD_STATE_LOST ante intentos posteriores de continuar un hilo cuyo estado operativo ya no sea fiable.

### 12.6. Timeouts externos

Las llamadas a Gemini y a la API municipal deberán utilizar tiempos máximos de espera compatibles con el presupuesto temporal del asistente.

No se introducirán reintentos ilimitados.

Los mecanismos de recuperación existentes deberán respetar los límites generales de ejecución.

## 13. Límites internos del asistente

Se conservarán los controles deterministas existentes en PB02, ajustando sus límites para optimizar el consumo de recursos y evitar ejecuciones innecesarias.

| Parámetro | Valor |
|---|---:|
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

El límite de recursión de LangGraph se calculará mediante:

```python
GRAPH_RECURSION_LIMIT = 2 * MAX_ITER + 8
```

El cliente no podrá incrementar estos límites por encima de los máximos establecidos.

Las cuotas HTTP y comerciales no sustituyen los límites internos del agente.

### 13.1. Justificación de los límites

- MAX_ITER=4: el flujo actual requiere como máximo cuatro decisiones del supervisor.
- MAX_STEPS_DEFAULT=3: reduce las rondas ordinarias de interacción con el LLM.
- MAX_STEPS_LIMIT=4: limita el razonamiento de cada especialista en consultas complejas.
- MAX_TOOL_CALLS_PER_SPECIALIST=4: restringe las ejecuciones de herramientas por especialista.
- MAX_TOOL_CALLS_PER_TURN=6: establece un presupuesto global de herramientas por consulta.
- Los límites de turnos e historial se mantienen hasta validar el nuevo ciclo conversacional.

### 13.2. Calibración y validación

Los nuevos límites deberán validarse antes de finalizar el PB03 mediante:

- Pruebas de regresión del PB02.
- Consultas simples y compuestas.
- Consultas multimodales.
- Consultas geográficas y temporales.
- Reformulaciones y continuidad conversacional.
- Casos límite de ejecución.
- Medición del consumo de tokens y llamadas a servicios externos.

Se seleccionarán los límites más restrictivos que permitan conservar las funcionalidades y los criterios de calidad del asistente.

Los valores establecidos son el resultado del análisis estático de la arquitectura existente y deberán confirmarse experimentalmente.

## 14. Robustez del HITL

### 14.1. Comprobación del estado

POST /approve deberá verificar el checkpoint real de LangGraph.

No se confiará en el valor pendiente_hitl que conserve Streamlit.

### 14.2. Operaciones incompatibles

| Situación | HTTP | Código |
|---|---|---|
| Aprobar sin HITL pendiente | 409 | NO_PENDING_APPROVAL |
| Preguntar con HITL pendiente | 409 | PENDING_APPROVAL |
| Preguntar en conversación finalizada | 409 | THREAD_CLOSED |
| Superar el límite de turnos | 409 | TURN_LIMIT_REACHED |
| Modificar conversación ocupada | 409 | THREAD_BUSY |
| Continuar sin checkpoint válido | 409 | THREAD_STATE_LOST |

### 14.3. Aprobaciones duplicadas

Si dos peticiones intentan resolver la misma aprobación, solamente una podrá modificar el estado.

La segunda petición deberá volver a comprobar el checkpoint antes de ejecutar cualquier acción.

La persistencia deberá respetar la restricción:

```sql
UNIQUE (thread_id, turn_number, role)
```

### 14.4. Aprobaciones obsoletas

Se propone incorporar un identificador de aprobación denominado approval_id.

El identificador deberá estar asociado al plan pendiente concreto.

El cliente deberá devolver dicho identificador al aprobar o rechazar.

Esto evitará que una aprobación enviada desde una interfaz desactualizada resuelva accidentalmente un plan posterior.

Una aprobación que no corresponda al plan pendiente devolverá:

- HTTP 409
- STALE_APPROVAL

Esta ampliación deberá incorporarse al contrato HTTP antes de implementar el endpoint.

## 15. Procesamiento seguro de imágenes

### 15.1. Formatos permitidos

- JPEG
- PNG

El formato real se verificará mediante el contenido del archivo.

No se confiará exclusivamente en su extensión ni en el Content-Type proporcionado por el cliente.

No se admitirán imágenes animadas ni archivos de formatos diferentes renombrados como JPEG o PNG.

### 15.2. Límites finales

| Parámetro | Límite |
|---|---:|
| Peso | 5 MiB |
| Resolución total | 16.000.000 píxeles |

Estos límites corresponden a las restricciones del procesamiento de imágenes existente.

### 15.3. Límites absolutos de recepción

Se proponen los siguientes límites adicionales:

| Parámetro | Límite absoluto |
|---|---:|
| Peso del archivo recibido | 20 MiB |
| Resolución original | 32.000.000 píxeles |

El límite absoluto protege al backend antes de realizar operaciones de descompresión, redimensionamiento o conversión.

También deberá limitarse el tamaño total del cuerpo HTTP, incluyendo la sobrecarga del formato multipart.

No será suficiente comprobar únicamente Content-Length, ya que puede estar ausente o no representar correctamente el tamaño real recibido.

### 15.4. Proceso de validación

1. Comprobar los límites de recepción.
2. Identificar el formato real.
3. Comprobar las dimensiones declaradas por la imagen.
4. Detectar riesgos de descompresión excesiva.
5. Verificar la integridad.
6. Decodificar la imagen de manera controlada.
7. Corregir la orientación cuando corresponda.
8. Redimensionar si supera la resolución final.
9. Comprimir si supera el peso final.
10. Verificar nuevamente el resultado.
11. Crear un archivo temporal con nombre generado por el backend.
12. Identificar y evaluar semánticamente el contenido de la imagen.
13. Validar el resultado estructurado de la identificación.
14. Detener el flujo si la imagen está fuera de dominio, contiene material no permitido o no puede identificarse con suficiente certeza.
15. Continuar con el asistente únicamente si la imagen ha sido admitida, reutilizando la identificación obtenida sin repetir la llamada multimodal.

Se utilizará Pillow para el procesamiento.

No se desactivarán sus mecanismos de protección frente a imágenes maliciosas o bombas de descompresión.

### 15.5. Redimensionamiento

Cuando una imagen supere los 16.000.000 píxeles, pero esté dentro del límite absoluto, se intentará reducir su resolución.

Se conservará la relación de aspecto.

La reducción deberá permitir que la imagen siga siendo adecuada para identificar el residuo.

### 15.6. Compresión

Cuando la imagen supere los 5 MiB, pero esté dentro del límite absoluto, se intentará reducir su peso.

La compresión podrá combinarse con el redimensionamiento.

El proceso tendrá un número limitado de intentos.

Si se obtiene una imagen válida y compatible con los límites finales, la consulta podrá ejecutarse normalmente.

### 15.7. Casos de error

| HTTP | Código | Situación |
|---|---|---|
| 413 | IMAGE_FILE_TOO_LARGE | Supera el límite absoluto o no puede reducirse al peso permitido |
| 422 | IMAGE_RESOLUTION_EXCEEDED | Supera el límite absoluto de resolución o no puede adaptarse |
| 422 | IMAGE_CORRUPTED | Imagen vacía, corrupta o ilegible |
| 422 | IMAGE_CONTENT_NOT_ALLOWED | La imagen contiene material que vulnera las políticas de contenido |
| 415 | IMAGE_FORMAT_NOT_ALLOWED | Formato no permitido |

Una imagen fuera de dominio o que no pueda identificarse con suficiente certeza generará una respuesta determinista de abstención o aclaración, sin continuar con la ejecución del asistente.

Un fallo técnico durante la identificación multimodal no se considerará una abstención válida.

Redimensionar o comprimir correctamente una imagen no constituye un error.

### 15.8. Archivos temporales

Las imágenes podrán almacenarse temporalmente dentro de:

```text
assets/.api_temporal/
```

Esta ubicación deberá ser compatible con las restricciones de acceso a archivos de las herramientas existentes.

Los nombres serán generados por el backend y no procederán directamente del nombre original enviado por el usuario.

No se aceptarán rutas locales proporcionadas por clientes externos.

El directorio temporal se excluirá del control de versiones.

### 15.9. Eliminación

Los archivos temporales deberán eliminarse cuando ya no puedan ser utilizados por ninguna ejecución.

En caso de timeout, no se eliminarán prematuramente si el worker continúa utilizándolos.

Los checkpoints no deberán conservar referencias a archivos temporales que puedan volver a utilizarse después de su eliminación.

El backend realizará una limpieza controlada de archivos temporales abandonados.

### 15.10. Privacidad

No se conservarán permanentemente las imágenes recibidas.

No se registrará su contenido binario en logs.

Cuando sea posible, se eliminarán los metadatos innecesarios, incluyendo información EXIF y coordenadas GPS.

### 15.11. Validación semántica y de contenido

Una imagen técnicamente válida no se considerará automáticamente admisible.

La identificación multimodal deberá proporcionar una salida estructurada que permita determinar si la imagen:

- Pertenece al dominio del asistente.
- Está fuera del dominio.
- Contiene material que vulnera las políticas de contenido.
- No puede identificarse con suficiente certeza.

Python validará el resultado y decidirá si el flujo puede continuar.

Cuando se identifique contenido fuera del dominio o no permitido, se interrumpirá inmediatamente la ejecución.

No se realizarán consultas posteriores al RAG, búsquedas geográficas, llamadas de síntesis ni operaciones HITL.

Las imágenes rechazadas no se conservarán permanentemente.

Los residuos válidos que carezcan de documentación suficiente en el corpus se tratarán mediante los mecanismos de abstención existentes.

Las llamadas multimodales ya ejecutadas consumirán cuota comercial, aunque el resultado de la identificación determine que el flujo debe detenerse.

La ausencia de una clasificación válida impedirá continuar con el procesamiento de la imagen.

## 16. Gestión centralizada de errores

FastAPI utilizará manejadores de excepciones para generar respuestas homogéneas.

El formato público será ErrorOut, definido en la especificación HTTP.

### 16.1. Clasificación

| Código HTTP | Categoría |
|---|---|
| 401 | Autenticación |
| 403 | Autorización |
| 404 | Recursos inexistentes o inaccesibles |
| 409 | Conflictos de estado |
| 413 | Tamaño excesivo de archivo |
| 415 | Formato multimedia no admitido |
| 422 | Validación |
| 429 | Límites de consumo |
| 500 | Fallos internos |
| 503 | Servicio o capacidad no disponible |
| 504 | Timeout del asistente |

### 16.2. Excepciones inesperadas

Las excepciones no previstas deberán transformarse en:

- HTTP 500
- INTERNAL_SERVER_ERROR

La respuesta pública no incluirá:

- Stack traces.
- Rutas internas.
- Consultas SQL.
- Variables de entorno.
- Credenciales.
- Información técnica que facilite accesos no autorizados.

Las excepciones podrán registrarse internamente de forma sanitizada.

## 17. Consistencia entre LangGraph y PostgreSQL

MemorySaver y PostgreSQL constituyen sistemas de almacenamiento independientes.

No existe una transacción atómica compartida entre ambos.

### 17.1. Persistencia correcta

Un turno resuelto deberá persistirse antes de devolver una respuesta HTTP satisfactoria.

La pregunta y la respuesta se almacenarán dentro de una misma transacción SQL.

### 17.2. Fallo de PostgreSQL

Si el asistente resuelve correctamente un turno, pero PostgreSQL no puede almacenarlo:

- Se ejecutará rollback cuando corresponda.
- No se devolverá HTTP 200.
- Se registrará la incidencia.
- Se impedirá continuar desde un checkpoint inconsistente.
- El historial anteriormente almacenado permanecerá disponible.

### 17.3. Resultado tardío

Si una ejecución finaliza después de haberse devuelto un timeout, su resultado no deberá persistirse automáticamente.

La ejecución del agente y la decisión de persistencia deberán estar desacopladas para permitir este control.

### 17.4. Reinicio del backend

Después de reiniciar el backend:

- Los mensajes SQL permanecen disponibles.
- Los checkpoints de MemorySaver se pierden.
- Las sesiones en memoria se pierden.
- Los contadores temporales se reinician.
- Las API keys permanecen almacenadas en PostgreSQL.
- El índice vectorial deberá estar disponible o reconstruirse.

Estas limitaciones deberán documentarse en el informe técnico.

## 18. Observabilidad

### 18.1. Objetivo

Permitir identificar el comportamiento del backend, diagnosticar errores, medir tiempos de respuesta y comprobar el resultado de las operaciones HTTP.

### 18.2. Identificador de petición

Cada petición HTTP recibirá un request_id único generado por el backend.

Se utilizará UUID.

El identificador se incluirá en los logs y en las respuestas de error.

Se propone devolverlo también mediante la cabecera X-Request-ID.

request_id identifica una petición HTTP.

thread_id identifica una conversación.

Una conversación puede estar asociada a múltiples request_id.

### 18.3. Registro por petición

Cada petición protegida generará un registro de acceso estructurado al finalizar.

| Campo | Tipo | Descripción |
|---|---|---|
| timestamp | datetime | Fecha UTC del registro |
| request_id | str | Identificador de petición |
| method | str | Método HTTP |
| path | str | Ruta del endpoint, sin parámetros sensibles |
| thread_id | str o None | Conversación asociada |
| api_key_id | str o None | Identificador de la clave |
| role | str o None | Rol autenticado |
| duration_ms | float | Duración de la petición |
| status_code | int | Código HTTP |
| error_code | str o None | Código de error funcional |

Se utilizará preferentemente el patrón de ruta definido por FastAPI para evitar registrar parámetros sensibles.

Las peticiones rechazadas antes de autenticarse tendrán valores nulos en los campos de identidad correspondientes.

### 18.4. Ejemplo de registro

```json
{
  "timestamp": "2026-11-24T18:30:00Z",
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

El ejemplo representa el formato previsto y no corresponde a una ejecución real.

### 18.5. Medición de duración

Se utilizará time.perf_counter() para medir el tiempo transcurrido durante una petición.

```python
duration_ms = (
    time.perf_counter() - start
) * 1000
```

El temporizador se iniciará antes de ejecutar la lógica del endpoint y finalizará cuando la respuesta esté preparada.

### 18.6. Niveles de logging

| Nivel | Uso |
|---|---|
| DEBUG | Diagnóstico durante desarrollo |
| INFO | Operaciones correctas y eventos ordinarios |
| WARNING | Peticiones rechazadas, límites y situaciones recuperables |
| ERROR | Fallos técnicos y errores internos |

El nivel de logging será configurable mediante LOG_LEVEL.

En producción se utilizará inicialmente INFO.

### 18.7. Eventos técnicos adicionales

Podrán registrarse eventos específicos relacionados con:

- Inicio y cierre del backend.
- Conexión a PostgreSQL.
- Disponibilidad de ChromaDB.
- Timeouts.
- Fallos de persistencia.
- Ejecuciones tardías descartadas.
- Errores de servicios externos.
- Incidencias de limpieza de archivos temporales.

Estos eventos no sustituirán ni duplicarán innecesariamente el registro de acceso HTTP.

### 18.8. Información prohibida

No se registrarán:

- Contraseñas.
- API keys originales.
- Tokens de sesión.
- Hashes de credenciales.
- Cadenas de conexión.
- Credenciales de Gemini.
- Cuerpos completos de peticiones.
- Preguntas y respuestas completas del usuario.
- Archivos binarios.
- Coordenadas personales.
- Prompts internos del agente.
- Cabeceras de autenticación.
- URLs completas que contengan información sensible.

## 19. Métricas operativas

La información registrada deberá permitir obtener las siguientes métricas:

| Métrica | Finalidad |
|---|---|
| Número de peticiones | Medir utilización |
| Distribución por endpoint | Identificar operaciones más utilizadas |
| Latencia media | Evaluar rendimiento |
| Percentil 95 de latencia | Detectar respuestas lentas |
| Tasa de respuestas 2xx | Evaluar funcionamiento |
| Tasa de respuestas 4xx | Detectar errores de uso y restricciones |
| Tasa de respuestas 5xx | Detectar fallos técnicos |
| Número de respuestas 429 | Evaluar límites |
| Número de respuestas 504 | Evaluar timeouts |
| Número de respuestas SERVER_BUSY | Evaluar capacidad |
| Ejecuciones simultáneas | Evaluar concurrencia |

Las métricas podrán obtenerse inicialmente a partir de los logs.

Prometheus, Grafana y sistemas externos de monitorización quedan fuera del alcance inicial.

## 20. Health check

GET /health permitirá comprobar la disponibilidad del servicio.

### 20.1. Comprobaciones

- Disponibilidad del backend.
- Configuración imprescindible.
- Conectividad con PostgreSQL.
- Disponibilidad del índice vectorial requerido por el asistente.

### 20.2. Restricciones

El health check no deberá:

- Ejecutar el agente.
- Generar embeddings.
- Invocar Gemini.
- Consumir cuota comercial.
- Requerir API key.
- Exponer secretos.

Las comprobaciones deberán ser ligeras y disponer de tiempos máximos de espera.

### 20.3. Resultado

Cuando el servicio esté operativo:

- HTTP 200
- status=ok
- storage=postgres

Cuando una dependencia imprescindible no esté disponible:

- HTTP 503
- Error controlado según el contrato HTTP

La respuesta no garantizará el funcionamiento de servicios externos que no hayan sido comprobados.

## 21. CORS

La política CORS se configurará mediante CORSMiddleware de FastAPI.

Los orígenes permitidos se obtendrán de CORS_ORIGINS.

### 21.1. Principios

- Permitir únicamente los orígenes necesarios.
- Evitar configuraciones indiscriminadas en producción.
- Permitir los métodos y cabeceras necesarios.
- No utilizar CORS como sustituto de autenticación y autorización.

### 21.2. Cabeceras

Deberán contemplarse:

- Content-Type.
- X-API-Key.
- Authorization.
- X-API-Key-Id.

Cuando corresponda, se expondrán al cliente:

- X-Request-ID.
- Retry-After.

### 21.3. Streamlit

Cuando Streamlit realiza peticiones HTTP desde su proceso Python hacia FastAPI, CORS no interviene directamente.

CORS regula las restricciones de acceso entre orígenes aplicadas por los navegadores.

Swagger servido desde el mismo origen que FastAPI tampoco necesita acceso cross-origin.

### 21.4. Configuración inicial

Se utilizará una lista explícita de orígenes permitidos mediante CORS_ORIGINS.

No se habilitarán indiscriminadamente todos los orígenes.

allow_credentials=False, puesto que la autenticación inicial no utiliza cookies cross-origin.

Se permitirán los métodos GET, POST, PATCH y DELETE.

Se permitirán exclusivamente las cabeceras necesarias para los contratos HTTP del producto.

Se expondrán las cabeceras X-Request-ID y Retry-After.

Las peticiones preflight serán gestionadas por CORSMiddleware y no requerirán autenticación ni consumirán cuotas comerciales.

La comunicación entre el servidor Streamlit y FastAPI no estará condicionada por CORS.

## 22. Variables de entorno

| Variable | Valor inicial propuesto | Finalidad |
|---|---|---|
| RATE_LIMIT_PER_MINUTE | 30 | Límite HTTP general |
| FREE_RATE_LIMIT_PER_MINUTE | 2 | Cuota Free por minuto |
| FREE_RATE_LIMIT_PER_HOUR | 10 | Cuota Free por hora |
| FREE_RATE_LIMIT_PER_DAY | 30 | Cuota Free por 24 horas |
| USER_RATE_LIMIT_PER_MINUTE | 5 | Cuota User por minuto |
| USER_RATE_LIMIT_PER_HOUR | 20 | Cuota User por hora |
| USER_RATE_LIMIT_PER_DAY | 45 | Cuota User por 24 horas |
| AGENT_MAX_WORKERS | 1 | Máximo de ejecuciones simultáneas |
| ASK_TIMEOUT_SECONDS | 60 | Tiempo máximo del asistente |
| IMAGE_UPLOAD_MAX_BYTES | 20971520 | Peso absoluto de recepción |
| IMAGE_UPLOAD_MAX_PIXELS | 32000000 | Resolución absoluta |
| LOG_LEVEL | INFO | Nivel de logging |
| CORS_ORIGINS | Según entorno | Orígenes permitidos |

Los límites de registro, login y emisión de credenciales también deberán centralizarse en la configuración del backend.

Los valores de configuración se validarán durante el inicio del servicio.

No se admitirán valores negativos, incoherentes o incompatibles con las restricciones internas del asistente.

Las variables se documentarán en .env.example.

## 23. Pruebas de robustez

Las pruebas deberán cubrir, como mínimo:

### Rate limiting

- Peticiones dentro del límite.
- Superación del límite por minuto.
- Superación del límite por hora.
- Superación del límite diario.
- Recuperación de capacidad al expirar una ventana.
- Independencia entre API keys.
- Contadores compartidos entre /ask y /ask/image.
- Exclusión de /approve de las cuotas comerciales.
- Control de peticiones concurrentes.
- Cálculo correcto de Retry-After.

### Concurrencia

- Ejecución simultánea de conversaciones distintas.
- Rechazo de modificaciones simultáneas del mismo thread_id.
- Aprobaciones concurrentes.
- Capacidad máxima del executor.
- Liberación de recursos después de una excepción.

### Timeout

- Ejecución dentro del límite.
- Ejecución superior al límite.
- Conservación de bloqueos mientras el worker continúa activo.
- Descarte de resultados tardíos.
- Ausencia de persistencia de turnos afectados.
- Limpieza segura de archivos temporales.

### Imágenes

- Imagen válida.
- Formato incorrecto.
- Imagen corrupta.
- Archivo vacío.
- Redimensionamiento correcto.
- Compresión correcta.
- Superación de los límites absolutos.
- Eliminación de metadatos innecesarios.
- Limpieza de archivos temporales.
- Detección de imágenes fuera de dominio.
- Detección de contenido no permitido.
- Tratamiento de imágenes cuya identificación es incierta.
- Validación del contrato de identificación multimodal.
- Interrupción del flujo tras rechazar una imagen.
- Ausencia de llamadas posteriores al LLM, RAG y herramientas tras el rechazo.
- Ausencia de HITL para imágenes rechazadas.
- Reutilización de la identificación multimodal sin llamadas duplicadas.
- Contabilización correcta de la cuota comercial.

### Observabilidad

- Generación de request_id.
- Registro de peticiones satisfactorias.
- Registro de errores 4xx y 5xx.
- Medición de duración.
- Ausencia de secretos en logs.
- Health check sin consumo del LLM.

### Estrategia

Se utilizarán mocks, relojes simulados y dependencias controladas para evitar llamadas innecesarias a Gemini durante las pruebas.

Las pruebas de rate limiting HTTP podrán realizarse mediante GET /threads sin consumir tokens del modelo.

Las pruebas de timeout utilizarán ejecuciones controladas que permitan comprobar el comportamiento real del mecanismo de espera.

## 24. Criterios de aceptación

- El backend aplica rate limiting HTTP.
- Las cuotas Free y User respetan los límites establecidos.
- Admin no tiene cuota comercial, pero mantiene límites técnicos.
- Las cuotas se aplican de forma independiente por API key.
- Las comprobaciones de consumo son atómicas.
- POST /ask y POST /ask/image comparten cuota.
- POST /approve no consume una nueva consulta comercial.
- La emisión de claves está limitada.
- No se producen modificaciones concurrentes del mismo checkpoint.
- Solo se permite una ejecución simultánea del asistente con la configuración inicial.
- Las peticiones que excedan la capacidad de ejecución reciben HTTP 503 SERVER_BUSY sin consumir cuota comercial, salvo conflictos del mismo thread_id, que reciben HTTP 409 THREAD_BUSY.
- El backend devuelve HTTP 429 al superar los límites aplicables.
- El backend devuelve HTTP 504 al superar el tiempo máximo.
- Los resultados tardíos no se persisten.
- Los archivos temporales se eliminan de forma segura.
- Las imágenes se adaptan cuando es posible.
- Las imágenes que superan los límites absolutos se rechazan.
- Las imágenes se someten a una validación semántica antes de ejecutar el asistente.
- Las imágenes fuera de dominio no continúan con el flujo.
- Las imágenes que vulneran las políticas de contenido se rechazan.
- Las imágenes cuya identificación es incierta no continúan con el flujo.
- Las imágenes rechazadas no generan llamadas posteriores al LLM, RAG, herramientas ni HITL.
- La identificación multimodal no se ejecuta de forma duplicada.
- Las llamadas multimodales realizadas consumen cuota comercial independientemente de su resultado semántico.
- Los errores respetan el contrato HTTP.
- Las abstenciones válidas no se confunden con errores técnicos.
- Cada petición protegida dispone de un registro de acceso.
- Los registros contienen duración y estado HTTP.
- Los logs no contienen secretos.
- GET /health funciona sin ejecutar el asistente.
- La política CORS es configurable.
- Las limitaciones del almacenamiento en memoria quedan documentadas.
- Las pruebas de robustez pueden ejecutarse sin consumir innecesariamente recursos de Gemini.
