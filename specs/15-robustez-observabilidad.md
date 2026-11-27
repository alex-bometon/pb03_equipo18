# 15. Robustez y observabilidad

## 1. Objetivo

Garantizar la estabilidad del backend mediante controles deterministas de consumo, admisión, concurrencia, tiempos de ejecución y observabilidad.

Los mecanismos HTTP permanecerán separados del núcleo del asistente y se aplicarán independientemente del cliente utilizado.

## 2. Responsabilidades

| Archivo | Responsabilidad |
|---|---|
| api/rate_limit.py | Limitadores y ventanas temporales |
| api/service.py | Admisión y coordinación de ejecuciones |
| api/images.py | Recepción, adaptación y gestión temporal de imágenes |
| api/errors.py | Tratamiento centralizado de errores |
| api/config.py | Configuración del backend |
| api/main.py | Middleware y ciclo de vida |
| config.py | Límites internos del núcleo |

La autenticación se regula en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

## 3. Controles de consumo

### 3.1. Contadores independientes

| Contador | Responsabilidad |
|---|---|
| Rate limiting HTTP | Peticiones contra el backend |
| Cuota comercial | Consultas costosas admitidas |
| turnos_consumidos | Turnos iniciados en LangGraph |

Los límites de seguridad de registro, autenticación y emisión tendrán registros independientes.

No se incorporará un contador SQL adicional de turnos.

### 3.2. Rate limiting HTTP

El límite inicial será de 30 peticiones por minuto por identidad autenticada, incluido Admin.

Se utilizarán identificadores diferenciados según la identidad:

- api_key.id para operaciones asociadas a una clave.
- user.id para operaciones exclusivamente de cuenta.

Las modalidades de autenticación de una misma API key compartirán contador.

No se utilizarán secretos ni hashes como identificadores de consumo.

La contabilización se realizará después de autenticar y superar el limitador HTTP, aunque posteriormente la petición sea rechazada por otras restricciones.

Las peticiones rechazadas antes de alcanzar el limitador no se contabilizarán.

Quedan excluidos:

- GET /health.
- GET /docs.
- GET /openapi.json.
- Preflight CORS.

Los endpoints públicos de registro, login y emisión anónima utilizarán sus propios límites de seguridad.

### 3.3. Cuotas comerciales

| Rol | Minuto | Hora | 24 horas |
|---|---:|---:|---:|
| Free | 2 | 10 | 30 |
| User | 5 | 20 | 45 |
| Admin | Sin límite | Sin límite | Sin límite |

Las cuotas serán independientes por API key.

POST /ask y POST /ask/image compartirán los contadores.

POST /approve no consumirá cuota comercial adicional.

Admin continuará sujeto a todos los límites técnicos.

### 3.4. Contabilización comercial

La cuota se registrará después de superar las validaciones, autorización, restricciones de estado y controles de capacidad, inmediatamente antes de admitir una ejecución costosa.

| Situación | Consume cuota |
|---|---|
| Consulta textual admitida al agente | Sí |
| Identificación multimodal admitida | Sí |
| Abstención o aclaración generada por el agente | Sí |
| Identificación visual fuera de dominio, prohibida o incierta | Sí |
| Ejecución admitida que termina en error o timeout | Sí |
| Respuesta determinista anterior al agente | No |
| Entrada técnicamente inválida | No |
| Operación no autorizada | No |
| Conflicto de conversación | No |
| Cuota o capacidad agotada | No |
| Fallo de admisión del executor | No |
| Aprobación o rechazo | No |
| Historial, cuenta y administración | No |

Una consulta multimodal consumirá una única unidad, incluyendo identificación, agente y aprobación automática.

La admisión y contabilización deberán coordinarse atómicamente.

Si falla el envío de una tarea al executor antes de ser admitida, se deshará exclusivamente su registro de cuota.

No se devolverá la cuota de una ejecución costosa ya admitida que termine en error o timeout.

### 3.5. Contador de turnos

turnos_consumidos continuará gestionándose en el núcleo.

Únicamente aumentará al iniciar un nuevo turno de LangGraph.

La identificación visual previa y la resolución HITL no incrementarán este contador.

Su utilización para persistencia se establece en [13-persistencia.md](13-persistencia.md).

## 4. Ventanas temporales

### 4.1. Algoritmo

Se utilizará Sliding Window Log mediante estructuras Python protegidas frente a concurrencia:

- defaultdict.
- deque.
- Lock.
- time.monotonic().

| Ventana | Segundos |
|---|---:|
| Minuto | 60 |
| 30 minutos | 1800 |
| Hora | 3600 |
| Día | 86400 |

Las ventanas serán deslizantes, no intervalos del calendario.

### 4.2. Funcionamiento

Dentro de una misma sección crítica:

1. Obtener el instante actual mediante time.monotonic().
2. Eliminar registros fuera de la ventana más larga.
3. Calcular el consumo de cada ventana aplicable.
4. Comprobar todos los límites.
5. Registrar el nuevo instante únicamente si todos permiten continuar.

Una operación caducará cuando:

```python
now - timestamp >= window_seconds
```

No se registrarán parcialmente operaciones rechazadas por otra ventana.

El bloqueo del contador no permanecerá adquirido durante la ejecución del asistente.

### 4.3. Retry-After

Para cada ventana agotada se calculará el tiempo necesario para recuperar capacidad.

Se utilizará el mayor tiempo de espera de todas las ventanas agotadas, redondeado hacia arriba a segundos enteros.

No se devolverá sistemáticamente un valor fijo de 60 segundos.

### 4.4. Almacenamiento y limpieza

Los contadores permanecerán en memoria.

Las entradas caducadas y las identidades sin registros vigentes deberán retirarse mediante una limpieza protegida frente a concurrencia.

Los contadores se reiniciarán con el backend y no se compartirán entre procesos o réplicas.

No constituirán un registro durable de facturación ni un límite económico global.

## 5. Límites de seguridad

| Operación | Identificador | Límite inicial |
|---|---|---|
| Login | Email normalizado | 5 intentos / hora |
| Login | Origen fiable | 20 intentos / 30 minutos |
| Registro | Origen fiable | 5 intentos / hora |
| Emisión Free anónima | Origen fiable | 3 / hora y 5 / 24 horas |
| Emisión registrada | Usuario destinatario | 3 / hora y 5 / 24 horas |

Los intentos fallidos de autenticación también se contabilizarán.

Los límites de login deberán aplicarse antes de ejecutar verificaciones costosas mediante bcrypt.

La emisión administrativa respetará los límites del destinatario cuando exista un usuario asociado.

Los límites de claves activas se definen en la especificación 14.

Solo se utilizarán direcciones IP obtenidas de fuentes fiables. Las cabeceras reenviadas únicamente se aceptarán desde proxies conocidos y configurados.

Cuando no pueda identificarse un origen individual fiable, se utilizarán identidades autenticadas o límites compartidos.

Las peticiones de Streamlit pueden compartir la IP del servidor, lo que deberá considerarse durante la calibración.

No se incorporarán mecanismos invasivos de identificación de dispositivos.

## 6. Admisión y concurrencia

### 6.1. Bloqueo por conversación

POST /ask, POST /ask/image y POST /approve utilizarán exclusión mutua por thread_id.

El bloqueo protegerá las comprobaciones del checkpoint, la ejecución, la validación del resultado y la persistencia correspondiente.

Una operación concurrente sobre el mismo hilo devolverá THREAD_BUSY sin esperar ni consumir cuota comercial.

La autorización se comprobará antes de revelar el estado de ocupación.

Las lecturas exclusivamente históricas no requerirán el bloqueo operativo de LangGraph.

La gestión de bloqueos deberá impedir que se eliminen entradas todavía utilizadas o que se creen bloqueos diferentes para una misma conversación.

### 6.2. Capacidad global

Se utilizará un ThreadPoolExecutor compartido durante la vida del backend.

Configuración inicial:

```dotenv
AGENT_MAX_WORKERS=1
```

Un semáforo limitará el número de ejecuciones admitidas a la capacidad disponible.

La adquisición será no bloqueante.

No se acumularán tareas en una cola de espera.

Cuando no exista capacidad se devolverá SERVER_BUSY sin consumir cuota comercial ni crear una conversación nueva.

La espera del resultado no bloqueará el event loop de FastAPI.

### 6.3. Orden de admisión

Para POST /ask y POST /ask/image:

1. Validar la estructura inicial.
2. Autenticar y aplicar el rate limiting HTTP.
3. Comprobar permisos y validar campos.
4. Comprobar existencia y propiedad del hilo indicado.
5. Adquirir su bloqueo y validar el estado operativo.
6. Aplicar el filtrado determinista previo.
7. Validar y adaptar técnicamente la imagen, cuando corresponda.
8. Reservar capacidad de ejecución.
9. Comprobar y registrar atómicamente la cuota comercial.
10. Admitir la tarea en el executor.
11. Identificar la imagen, cuando corresponda.
12. Crear la conversación si procede iniciar LangGraph.
13. Ejecutar el agente.
14. Resolver automáticamente HITL cuando se solicite.
15. Validar el resultado.
16. Comprobar nuevamente la autorización.
17. Persistir el turno resuelto.
18. Devolver la respuesta y liberar los recursos de forma segura.

Las respuestas anteriores al agente podrán finalizar antes de reservar capacidad.

Las imágenes no admitidas semánticamente no crearán nuevas conversaciones.

Cuando se genere un thread_id nuevo, su bloqueo quedará establecido antes de que la conversación pueda utilizarse desde otra petición.

El orden de algunas validaciones estructurales podrá depender de FastAPI, sin adelantar operaciones costosas respecto a sus controles.

### 6.4. Responsabilidad del worker

Una única tarea realizará la identificación visual, la creación de la conversación, la ejecución del agente y la aprobación automática, según corresponda.

El worker utilizará sus propias sesiones SQL cuando necesite crear una conversación.

La persistencia definitiva de mensajes corresponderá al coordinador del servicio, conforme a la especificación 13.

POST /approve utilizará el mismo mecanismo de admisión y exclusión mutua, sin registrar una nueva cuota comercial.

## 7. Filtrado previo

Se aplicará un filtro determinista antes de ejecutar LangGraph.

Las consultas inequívocamente fuera del dominio y las aclaraciones que puedan resolverse previamente no invocarán Gemini, RAG ni herramientas.

El filtro considerará el contexto operativo autorizado cuando exista.

No se rechazarán reformulaciones únicamente por carecer de palabras clave sobre reciclaje.

Las respuestas previas no consumirán cuota comercial, no incrementarán turnos y no modificarán el checkpoint.

El filtrado no permitirá eludir las restricciones de estado de una conversación existente.

En las consultas multimodales, la ausencia de información que pueda obtenerse mediante la imagen no provocará por sí sola una aclaración previa. El filtrado textual deberá considerar la existencia de la entrada visual antes de impedir su identificación semántica.

Los criterios funcionales y geográficos se establecen en [04-consultas-generales.md](04-consultas-generales.md).

## 8. Timeout

### 8.1. Presupuesto temporal

Configuración inicial:

```dotenv
ASK_TIMEOUT_SECONDS=60
```

Una consulta dispondrá de un único presupuesto compartido para:

- Identificación visual, cuando corresponda.
- Operaciones previas necesarias para iniciar LangGraph.
- Ejecución del agente.
- Aprobación automática.

El tiempo de decisión humana no formará parte del presupuesto.

POST /approve dispondrá de un nuevo presupuesto.

La validación técnica de imágenes y la persistencia definitiva tendrán controles independientes.

El timeout no representa necesariamente la duración máxima total de la petición HTTP.

### 8.2. Aplicación

Se utilizará un único Future para cada ejecución admitida.

El plazo se calculará mediante time.monotonic():

```python
deadline = time.monotonic() + ASK_TIMEOUT_SECONDS
```

La espera utilizará el tiempo restante:

```python
remaining = max(0.0, deadline - time.monotonic())

resultado = future.result(timeout=remaining)
```

Estos fragmentos representan el cálculo temporal, no la implementación completa del control concurrente.

Se distinguirá entre el agotamiento de la espera y una excepción producida por la propia tarea.

### 8.3. Controles entre fases

El worker comprobará el plazo y la vigencia de la ejecución:

- Antes de iniciar la identificación visual.
- Después de la identificación visual.
- Antes de crear una conversación SQL.
- Después de confirmar su creación.
- Antes de iniciar LangGraph.
- Antes de resolver automáticamente HITL.

La declaración de timeout y la autorización para comenzar una fase que pueda modificar el checkpoint deberán coordinarse mediante una protección común.

Una vez invalidada la ejecución, no se autorizará el inicio de nuevas fases.

Si una fase ya había sido autorizada y no puede garantizarse que no modifique el checkpoint, se aplicará invalidación conservadora.

No se mantendrá el bloqueo de coordinación durante una llamada externa prolongada.

### 8.4. Superación del presupuesto

El agotamiento del presupuesto devolverá HTTP 504 AGENT_TIMEOUT.

No se aceptarán resultados parciales o tardíos como ejecuciones satisfactorias.

future.result(timeout=...) no cancela una tarea que ya está ejecutándose.

future.cancel() únicamente podrá cancelar una tarea que todavía no haya comenzado.

No se implementará interrupción forzada de hilos ni un sistema adicional de cancelación cooperativa.

La aceptación del resultado exigirá comprobar que la ejecución finalizó dentro del presupuesto temporal. 

La finalización del Future no constituirá por sí sola una garantía de cumplimiento del plazo.

### 8.5. Finalización real

Tras comunicar un timeout:

- El worker podrá continuar ocupado.
- Se conservarán los bloqueos y archivos temporales necesarios.
- No se iniciará la persistencia definitiva de mensajes.
- Los resultados tardíos se descartarán.
- Los recursos se liberarán exactamente una vez, cuando resulte seguro.

La finalización normal y tardía deberán coordinarse para evitar condiciones de carrera.

### 8.6. Consistencia posterior

Si la ejecución no llegó a modificar ni pudo modificar el checkpoint, no será necesario invalidar un hilo previamente consistente.

Si LangGraph o la resolución HITL comenzaron, o existe incertidumbre sobre sus modificaciones, el hilo se marcará como no reutilizable cuando no pueda garantizarse su consistencia.

La invalidación se mantendrá en memoria.

Mientras continúe la ejecución podrá devolverse THREAD_BUSY. Después de finalizar, un hilo invalidado devolverá THREAD_STATE_LOST.

Las reglas de persistencia y tratamiento de commits inciertos se establecen en la especificación 13.

### 8.7. Dependencias externas

Gemini, ArcGIS y PostgreSQL dispondrán de límites de espera adecuados.

Los reintentos serán acotados.

Los presupuestos deberán calibrarse mediante pruebas de rendimiento, considerando también el timeout del cliente definido en [07-streamlit.md](07-streamlit.md).

## 9. Límites internos del núcleo

Se centralizarán en config.py:

| Parámetro | Valor inicial |
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

El límite de recursión se calculará mediante:

```python
GRAPH_RECURSION_LIMIT = 2 * MAX_ITER + 8
```

El consumidor no podrá superar los máximos autorizados.

La identificación visual previa no se contabilizará como una llamada interna a herramientas.

Los límites deberán permitir completar correctamente las ejecuciones y alcanzar HITL.

El último turno permitido podrá resolver su aprobación aunque se haya agotado el límite de nuevos turnos.

Los mecanismos de aplicación se establecen en [05-tools.md](05-tools.md) y [06-langgraph.md](06-langgraph.md).

## 10. Procesamiento de imágenes

### 10.1. Límites

| Parámetro | Límite final | Límite absoluto |
|---|---:|---:|
| Peso | 5 MiB | 20 MiB |
| Resolución | 16.000.000 píxeles | 32.000.000 píxeles |

Únicamente se admitirán JPEG y PNG no animados.

Se limitará el tamaño total del cuerpo HTTP, incluyendo la sobrecarga multipart, antes de permitir una acumulación arbitraria de archivos.

No se confiará exclusivamente en Content-Length.

### 10.2. Validación y adaptación

Se utilizará Pillow para:

1. Identificar el formato real.
2. Comprobar los límites absolutos.
3. Verificar integridad y riesgos de descompresión.
4. Decodificar de forma controlada.
5. Corregir orientación y eliminar metadatos innecesarios.
6. Redimensionar conservando la relación de aspecto cuando sea necesario.
7. Comprimir mediante un número limitado de intentos.
8. Validar nuevamente formato, integridad, peso y resolución.

Una imagen que supere los límites finales podrá continuar si se adapta correctamente.

Una imagen que supere los límites absolutos será rechazada.

No se desactivarán las protecciones de Pillow.

El procesamiento técnico previo tendrá límites de recursos adecuados.

Los errores correspondientes se establecen en la especificación 12.

### 10.3. Archivos temporales

Se utilizará una ubicación autorizada:

```text
assets/.api_temporal/
```

Los nombres serán generados por el backend.

No se utilizarán rutas ni nombres de almacenamiento determinados por el cliente.

Los archivos se eliminarán cuando ninguna ejecución pueda seguir utilizándolos, incluyendo excepciones y timeouts.

Podrá realizarse una limpieza de archivos abandonados durante el inicio del backend.

El directorio temporal se excluirá del repositorio y de la imagen Docker.

No se conservarán permanentemente imágenes ni referencias operativas a archivos eliminados.

### 10.4. Identificación semántica

El contrato IdentificacionImagen y la función identificar_imagen() se definen en [05-tools.md](05-tools.md).

Únicamente una identificación admitida permitirá iniciar LangGraph.

La identificación se reutilizará sin realizar una segunda llamada multimodal.

Las identificaciones rechazadas o inciertas no crearán conversaciones, consumirán turnos ni generarán mensajes persistidos.

La cuota comercial correspondiente a la identificación admitida al executor permanecerá consumida.

Los fallos técnicos no se convertirán en incertidumbre semántica.

## 11. Gestión de fallos

Los manejadores centralizados de FastAPI utilizarán ErrorOut y el catálogo de [12-contratos-http.md](12-contratos-http.md).

Antes de devolver una respuesta satisfactoria, el servicio comprobará:

- Ausencia de errores técnicos bloqueantes.
- Coherencia del estado y resolución HITL cuando corresponda.
- Validez de fuentes y resultados geográficos.
- Cumplimiento del contrato AskOut.
- Autorización vigente.
- Confirmación de la persistencia obligatoria.

No se eliminarán evidencias o campos imprescindibles para convertir un resultado inválido en éxito.

Los fallos recuperables podrán utilizar mecanismos de respaldo autorizados. Los fallos imprescindibles no recuperados deberán comunicarse como errores técnicos.

La lógica de recuperación documental y geográfica se establece en las especificaciones 01 y 05.

## 12. Observabilidad

### 12.1. Registro HTTP

Cada petición dispondrá de un request_id generado mediante UUID.

Se emitirá un registro estructurado al finalizar la petición:

| Campo | Tipo |
|---|---|
| timestamp | datetime UTC |
| request_id | str |
| method | str |
| path | str |
| thread_id | str o None |
| api_key_id | str o None |
| role | str o None |
| duration_ms | float |
| status_code | int o None |
| error_code | str o None |

path representará preferentemente el patrón de ruta, sin parámetros sensibles.

Los campos de identidad solo se completarán después de comprobar la autenticación y autorización correspondientes.

La duración se medirá mediante time.perf_counter().

El registro reflejará el código HTTP efectivamente devuelto.

Las rutas desconocidas se identificarán mediante UNMATCHED y las peticiones preflight mediante PREFLIGHT. Si no se ha transmitido ningún estado HTTP, status_code será None.

### 12.2. Eventos técnicos

Se registrarán los eventos relevantes de ejecución, capacidad agotada, timeout, finalización tardía, invalidación de checkpoints, fallos de persistencia y dependencias, respaldo geográfico y procesamiento de imágenes.

Los eventos conservarán request_id cuando corresponda.

La finalización real de un worker podrá registrarse después de la respuesta HTTP, sin modificar su resultado.

### 12.3. Niveles

| Nivel | Uso |
|---|---|
| DEBUG | Diagnóstico de desarrollo |
| INFO | Operaciones ordinarias |
| WARNING | Rechazos y situaciones recuperables |
| ERROR | Fallos técnicos |

El nivel inicial de producción será INFO.

Las respuestas satisfactorias y redirecciones se registrarán en INFO, los rechazos en WARNING y los fallos internos en ERROR.

### 12.4. Información prohibida

No se registrarán:

- Contraseñas, API keys, tokens ni hashes de credenciales.
- Cadenas de conexión y credenciales de proveedores.
- Cabeceras de autenticación.
- Cuerpos completos de peticiones.
- Preguntas, respuestas o descripciones visuales completas.
- Imágenes binarias.
- Coordenadas personales.
- Prompts internos y documentos completos.

Las restricciones se aplicarán también a los registros de bibliotecas y excepciones.

Se desactivarán los registros de acceso predeterminados de Uvicorn.

## 13. Métricas

| Dimensión | Métricas |
|---|---|
| HTTP | Peticiones por endpoint, latencia media, p95 y distribución de estados |
| Robustez | Errores, respuestas 429, timeouts y rechazos de capacidad |
| Ejecución | Duración real, ejecuciones admitidas y tardías |
| Consumo | Llamadas a modelos, herramientas y tokens cuando estén disponibles |
| Resultado funcional | HITL pendiente, aprobación, rechazo, abstención y aclaración |
| Evidencia | Suficiente, parcial o insuficiente |

Las métricas podrán obtenerse mediante logs y pruebas.

No se incorporarán endpoints adicionales de métricas, Prometheus ni Grafana.

El éxito HTTP y la aprobación del usuario no acreditan por sí solos la calidad factual de la respuesta.

La evaluación de calidad se establece en [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).

## 14. Health check

GET /health comprobará:

- Configuración imprescindible.
- Conectividad real con PostgreSQL.
- Disponibilidad y validez básica de la colección ChromaDB requerida.

Las comprobaciones serán ligeras y tendrán tiempos de espera acotados.

No ejecutarán LangGraph ni invocarán Gemini o ArcGIS.

No requerirán autenticación ni consumirán cuotas.

El endpoint devolverá HTTP 503 si el backend puede responder, pero no dispone de los recursos imprescindibles.

No garantizará la disponibilidad de proveedores externos ni la existencia de un worker libre.

## 15. CORS

Se utilizará CORSMiddleware.

| Configuración | Valor |
|---|---|
| allow_origins | Lista explícita mediante CORS_ORIGINS |
| allow_methods | GET, POST, PATCH, DELETE |
| allow_headers | Content-Type, X-API-Key, Authorization, X-API-Key-Id |
| expose_headers | X-Request-ID, Retry-After |
| allow_credentials | False |

Las peticiones OPTIONS preflight serán gestionadas por el middleware, sin autenticación ni consumo de cuotas.

Las respuestas de error respetarán la política CORS aplicable.

No se utilizarán orígenes indiscriminados en producción.

CORS no sustituye la autenticación ni restringe directamente las peticiones realizadas desde el proceso Python de Streamlit.

Los rechazos preflight conservarán el comportamiento nativo de CORSMiddleware, conforme a la especificación 12.

## 16. Configuración

| Variable | Valor inicial |
|---|---|
| RATE_LIMIT_PER_MINUTE | 30 |
| FREE_RATE_LIMIT_PER_MINUTE | 2 |
| FREE_RATE_LIMIT_PER_HOUR | 10 |
| FREE_RATE_LIMIT_PER_DAY | 30 |
| USER_RATE_LIMIT_PER_MINUTE | 5 |
| USER_RATE_LIMIT_PER_HOUR | 20 |
| USER_RATE_LIMIT_PER_DAY | 45 |
| AGENT_MAX_WORKERS | 1 |
| ASK_TIMEOUT_SECONDS | 60 |
| IMAGE_UPLOAD_MAX_BYTES | 20971520 |
| IMAGE_UPLOAD_MAX_PIXELS | 32000000 |
| LOG_LEVEL | INFO |
| CORS_ORIGINS | Según entorno |

Los límites de seguridad también se centralizarán en api/config.py.

La configuración deberá validarse durante el inicio del backend, rechazando valores inválidos o incompatibles.

.env.example documentará los parámetros sin secretos reales.

La arquitectura inicial utilizará un único proceso de Uvicorn, conforme a [11-arquitectura-mlops.md](11-arquitectura-mlops.md).

## 17. Criterios de aceptación

- Los limitadores aplican ventanas deslizantes y comprobaciones atómicas.
- Las cuotas comerciales y los turnos permanecen diferenciados.
- Las operaciones no admitidas no consumen cuota comercial.
- Las ejecuciones concurrentes no modifican simultáneamente un checkpoint.
- No se acumulan tareas esperando capacidad.
- El timeout utiliza un presupuesto compartido y controles entre fases.
- Los resultados tardíos no generan mensajes persistidos.
- Los recursos se liberan únicamente cuando resulta seguro.
- Las imágenes adaptables se procesan sin llamadas multimodales duplicadas.
- Los fallos técnicos no se presentan como resultados satisfactorios.
- Los registros permiten diagnosticar errores sin exponer secretos.
- El health check comprueba los recursos imprescindibles.
- Se conserva la independencia del núcleo.

Los casos de prueba se desarrollan en [plan-pruebas.md](../docs/plan-pruebas.md), conforme a la estrategia de [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).