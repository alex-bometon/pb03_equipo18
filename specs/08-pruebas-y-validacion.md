# 08. Estrategia de pruebas y validación

## 1. Objetivo

Verificar que ReciclaTÍA conserva las funcionalidades del PB02 y cumple los requisitos funcionales, técnicos, arquitectónicos y de seguridad del Project Break 03.

Esta especificación establece la estrategia de validación y los criterios de aceptación.

Los procedimientos, comandos y casos de prueba se desarrollan en [plan-pruebas.md](../docs/plan-pruebas.md).

## 2. Principios

- Trazabilidad entre requisitos y pruebas.
- Conservación de las comprobaciones de regresión.
- Independencia y reproducibilidad de las pruebas.
- Separación entre validación estructural y evaluación factual.
- Utilización de dependencias controladas.
- Aislamiento de los entornos.
- Verificación de resultados satisfactorios y escenarios de fallo.
- Control del consumo de servicios externos.

No se considerarán verificadas funcionalidades que no hayan sido sometidas a las comprobaciones correspondientes.

## 3. Línea base del PB02

La referencia inicial se encuentra en:

[baseline-pb02.md](../entregables/evidencias/baseline-pb02.md)

Corresponde al commit 3997e0a, validado el 24/11/2026 mediante Python 3.13.2.

| Métrica | Resultado inicial |
|---|---:|
| Pruebas superadas | 358 |
| Pruebas fallidas | 0 |
| Tiempo de ejecución | 1,27 segundos |

Estos resultados constituyen una referencia histórica de regresión, no una validación de las funcionalidades nuevas del PB03.

El número de pruebas no constituye un objetivo cuantitativo obligatorio.

Las pruebas existentes únicamente podrán modificarse cuando cambie un contrato autorizado o se corrija un comportamiento incorrecto.

No se eliminarán comprobaciones ni se debilitarán sus condiciones para ocultar regresiones.

## 4. Niveles de validación

| Nivel | Finalidad |
|---|---|
| Unitario | Verificar funciones y componentes aislados |
| Integración | Comprobar la interacción entre componentes |
| Contratos HTTP | Verificar entradas, respuestas y códigos de estado |
| Regresión | Detectar cambios incompatibles |
| Evaluación RAG | Medir recuperación y calidad documental |
| Seguridad | Verificar permisos y controles adversariales |
| Robustez | Comprobar límites, concurrencia y recuperación |
| Interfaz | Validar los recorridos del consumidor |
| Infraestructura | Comprobar Docker, PostgreSQL y Render |
| Extremo a extremo | Verificar recorridos completos del producto |

Se conservará pytest como framework principal.

Los scripts de evaluación con proveedores reales permanecerán diferenciados de las pruebas unitarias ordinarias.

## 5. Aislamiento y reproducibilidad

Las pruebas deberán ejecutarse sin depender de su orden ni de estados generados por otros casos.

Se utilizarán fixtures, mocks, clientes de prueba y dependencias controladas cuando corresponda.

Las pruebas unitarias no requerirán credenciales reales de Gemini, conexión a ArcGIS ni infraestructura de Render.

Las pruebas relacionales utilizarán PostgreSQL en un entorno aislado de producción.

SQLite no sustituirá la validación de las restricciones reales de PostgreSQL.

Se aislarán los checkpoints, sesiones, contadores, bloqueos, executors y archivos temporales entre pruebas.

Las pruebas temporales utilizarán relojes controlados.

Las pruebas de concurrencia utilizarán mecanismos de sincronización explícitos, evitando depender exclusivamente de pausas arbitrarias.

## 6. Evaluación del RAG

### 6.1. Recuperación

Se conservará tests/evaluate_retrieve.py.

La evaluación deberá comprobar:

- Pertinencia de los fragmentos.
- Correspondencia de fuentes y metadatos.
- Aplicación de filtros.
- Conservación de relaciones documentales.
- Corrección de recuentos y agrupaciones.
- Diferenciación entre búsquedas vacías y fallos técnicos.

Podrán utilizarse las métricas:

| Métrica | Finalidad |
|---|---|
| Hit@k | Comprobar si aparece evidencia relevante entre los primeros k resultados |
| Precision@k | Medir la proporción de resultados relevantes |
| Recall@k | Medir la proporción de evidencias relevantes recuperadas |
| MRR | Evaluar la posición del primer resultado relevante |
| Distancia vectorial | Analizar la similitud de los resultados |

Precision@k y Recall@k requerirán referencias de relevancia adecuadas.

La coincidencia de una fuente documental no implica necesariamente que el fragmento recuperado permita responder correctamente.

Las comparaciones entre configuraciones utilizarán las mismas consultas y referencias de relevancia.

### 6.2. Generación

Se conservarán:

- tests/evaluate_rag.py.
- tests/smoke_generate.py.
- tests/prueba_consumo.py.

La evaluación distinguirá:

| Dimensión | Comprobación |
|---|---|
| Estructura | Cumplimiento del contrato de salida |
| Referencias | Correspondencia entre citas y fuentes |
| Exactitud factual | Corrección de las afirmaciones |
| Fundamentación | Respaldo de las afirmaciones mediante evidencia |
| Suficiencia | Cobertura de los aspectos solicitados |
| Abstención | Capacidad de evitar respuestas no fundamentadas |
| Consumo | Utilización justificada de modelos y herramientas |

La validación estructural no constituye por sí sola una garantía de exactitud factual.

### 6.3. Abstenciones

| Evidencia suficiente | El sistema responde | Evaluación |
|---|---|---|
| Sí | Sí | Respuesta esperada, pendiente de comprobar su calidad |
| Sí | No | Abstención indebida |
| No | Sí | Respuesta indebida |
| No | No | Abstención correcta |

Las aclaraciones se evaluarán separadamente cuando constituyan el resultado esperado.

Los fallos técnicos no se contabilizarán como abstenciones semánticas correctas.

### 6.4. Consumo

Se comprobará la ausencia de llamadas innecesarias a proveedores cuando:

- No exista contexto documental utilizable.
- El filtrado previo resuelva la consulta.
- La recuperación estructurada resulte suficiente.
- Puedan reutilizarse respuestas o evidencias válidas.
- Exista una identificación multimodal previamente admitida.

Los procedimientos y conjuntos de evaluación se establecen en el plan de pruebas.

## 7. Cobertura por componente

| Componente | Ámbito mínimo de validación | Especificación |
|---|---|---|
| Pipeline y recuperación | Chunks, embeddings, índice, filtros e integridad | 01, 02 |
| Generación | Contrato, citas, evidencia y abstenciones | 03 |
| Interpretación | Intenciones, compatibilidad, horarios y contexto | 04 |
| Herramientas | Permisos, argumentos, resultados y respaldo | 05 |
| LangGraph | Enrutamiento, estado, límites y HITL | 06 |
| Streamlit | Comunicación HTTP, sesión y presentación | 07 |
| Fuentes | Procedencia, metadatos y referencias públicas | 09 |
| Seguridad | Inyecciones, archivos, permisos y secretos | 10 |
| Arquitectura | Independencia y dirección de dependencias | 11 |
| API REST | Contratos, códigos HTTP y OpenAPI | 12 |
| Persistencia | Restricciones, transacciones e historial | 13 |
| Autenticación | Cuentas, sesiones, credenciales y propiedad | 14 |
| Robustez | Cuotas, concurrencia, timeout y observabilidad | 15 |
| Infraestructura | Docker, Render, persistencia y recuperación | 16 |

Los requisitos concretos permanecerán definidos en sus respectivas especificaciones.

El inventario de archivos de pruebas y los casos detallados se mantendrán en docs/plan-pruebas.md.

## 8. Validaciones críticas del PB03

### 8.1. Contratos HTTP

Cada endpoint deberá comprobar sus entradas válidas e inválidas, permisos, respuestas y códigos de estado.

Las respuestas AskOut satisfactorias deberán contener error=None y respetar los invariantes del estado correspondiente.

Se comprobará especialmente:

- HTTP 400 EMPTY_QUESTION para preguntas vacías.
- HTTP 422 para incumplimientos de validación.
- Correspondencia entre ErrorOut y el código HTTP.
- Correspondencia entre request_id y X-Request-ID.
- Ausencia de ejecuciones no autorizadas.
- Ausencia de falsos éxitos HTTP 200.

Una respuesta técnicamente fallida no se considerará correcta por contener texto comprensible.

### 8.2. Estado, HITL y persistencia

| Situación | HITL pendiente | Incrementa turnos | Persiste mensajes |
|---|---|---|---|
| Respuesta previa a LangGraph | No | No | No |
| Propuesta válida del agente | Sí | Sí, al iniciar el turno | No |
| Resolución mediante aprobación | No | No | Sí |
| Resolución mediante rechazo | No | No | Sí |
| Fallo técnico | No constituye propuesta válida | Según fase alcanzada | No |
| Timeout | No constituye propuesta válida | Según fase alcanzada | No |

Toda ejecución satisfactoria de LangGraph deberá alcanzar una interrupción real antes de aplicar.

Se comprobará la resolución manual y automática, la validez de approval_id, las aprobaciones obsoletas, la exclusión mutua y la resolución del último turno permitido.

Las respuestas anteriores al agente no deberán crear checkpoints ni nuevas conversaciones SQL.

Los mensajes de turnos resueltos deberán almacenarse atómicamente conforme a [13-persistencia.md](13-persistencia.md).

Se comprobará el tratamiento de fallos de persistencia y estados inconsistentes.

### 8.3. Autenticación y autorización

Se verificarán las modalidades de autenticación y los permisos establecidos en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

Las pruebas deberán comprobar especialmente:

- Aislamiento entre API keys, incluso cuando pertenezcan al mismo usuario.
- Acceso administrativo autorizado.
- Emisión de claves User mediante autorización explícita.
- Ausencia de elevaciones de privilegios.
- Invalidación de sesiones y credenciales.
- Revocación durante una ejecución.
- Límites de emisión y reactivación.
- Ausencia de exposición de secretos.

### 8.4. Filtrado previo y multimodalidad

Las pruebas comprobarán las decisiones de admisibilidad y las operaciones efectivamente ejecutadas.

Una consulta textual resuelta antes del agente no deberá invocar Gemini, RAG ni LangGraph.

Las imágenes técnicamente inválidas no deberán llegar a la identificación semántica.

Las imágenes adaptables deberán procesarse conforme a los límites establecidos.

Las identificaciones visuales no admitidas no ejecutarán LangGraph.

Las identificaciones admitidas deberán reutilizarse sin una segunda llamada multimodal.

Se comprobará la contabilización correspondiente, la procedencia de las observaciones y la eliminación segura de archivos temporales.

### 8.5. Cuotas y concurrencia

Se verificarán de manera independiente:

- Rate limiting HTTP.
- Cuotas comerciales.
- Contadores de turnos.
- Límites de seguridad.
- Presupuestos internos.
- Capacidad global.

Se comprobarán los límites exactos, la expiración de ventanas, el aislamiento de identidades y Retry-After.

Las operaciones concurrentes no podrán modificar simultáneamente un mismo checkpoint.

Cuando se agote la capacidad global, no se admitirán ejecuciones adicionales ni se consumirán cuotas comerciales por una operación no admitida.

### 8.6. Timeouts

Se comprobará que una ejecución que exceda su presupuesto devuelve HTTP 504 AGENT_TIMEOUT.

La finalización de la petición HTTP deberá distinguirse de la finalización real del worker.

Las pruebas deberán verificar:

- Conservación de bloqueos y recursos mientras continúe una ejecución activa.
- Ausencia de persistencia de mensajes tardíos.
- Comprobación del plazo antes de crear la conversación, iniciar LangGraph o resolver una aprobación automática.
- Ausencia de inicio tardío del grafo después de comunicar un timeout.
- Invalidación del hilo cuando no pueda garantizarse su consistencia.
- Liberación de recursos una única vez.
- Ausencia de reintentos automáticos de operaciones POST inciertas.

Los mecanismos y límites se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

### 8.7. Seguridad y observabilidad

Se verificarán los controles frente a entradas adversariales, accesos indebidos, argumentos manipulados y referencias inventadas.

Los registros deberán permitir identificar peticiones, resultados, errores y duraciones sin exponer información sensible.

Se comprobará la política CORS mediante solicitudes de orígenes autorizados y no autorizados.

### 8.8. Fallos de dependencias

Se simularán, como mínimo, los siguientes fallos:

| Dependencia | Comprobación |
|---|---|
| Gemini | Diferenciar indisponibilidad, salida inválida y timeout |
| ArcGIS | Activar el respaldo autorizado cuando corresponda |
| PostgreSQL | Impedir falsos éxitos y proteger la consistencia |

También se comprobarán fallos de ChromaDB y de las herramientas imprescindibles.

Los fallos técnicos no recuperados deberán comunicarse conforme al catálogo HTTP.

## 9. Rendimiento y consumo

Las evaluaciones deberán utilizar condiciones comparables e identificar la versión del código, configuración y entorno.

Se registrarán, cuando corresponda:

- Latencia de recuperación y generación.
- Duración HTTP y duración real del agente.
- Latencia media, mediana y percentiles.
- Número de llamadas a Gemini y herramientas.
- Consumo de tokens, cuando esté disponible.
- Errores, timeouts y rechazos de capacidad.
- Consumo de memoria y recursos de infraestructura.

Se distinguirá entre éxito HTTP, resultado funcional válido y calidad documental.

No se establecerán garantías de rendimiento sin mediciones que las respalden.

Los resultados permitirán calibrar los límites y timeouts iniciales sin comprometer el comportamiento requerido.

## 10. Validación de infraestructura y extremo a extremo

Antes de la entrega deberá comprobarse:

- Funcionamiento independiente del núcleo RAG y la CLI.
- Instalación reproducible de dependencias.
- Construcción de Docker sin credenciales de Gemini.
- Reconstrucción del índice desde artefactos existentes.
- Funcionamiento de PostgreSQL.
- Disponibilidad de GET /health y Swagger.
- Funcionamiento de Streamlit mediante HTTP.
- Despliegue HTTPS en Render.
- Ejecución de recorridos representativos de cada perfil.
- Persistencia del historial después de un redeploy.
- Tratamiento de checkpoints perdidos.
- Recuperación de una versión compatible del backend.

La validación del historial tras el redeploy utilizará la misma base de datos antes y después de la operación.

Las pruebas con mocks no sustituirán las comprobaciones necesarias de integración real y despliegue.

Los procedimientos se establecen en [plan-pruebas.md](../docs/plan-pruebas.md) y [operaciones-despliegue.md](../docs/operaciones-despliegue.md).

## 11. Evidencias y trazabilidad

Los resultados de ejecución se registrarán en entregables/evidencias/.

Cada evidencia deberá identificar:

- Fecha y commit evaluado.
- Entorno y configuración relevante.
- Pruebas o procedimiento ejecutados.
- Resultados obtenidos.
- Fallos y limitaciones.
- Comprobaciones pendientes.

Se distinguirán los resultados automatizados, las evaluaciones factuales y las comprobaciones manuales.

No se incluirán secretos ni datos personales innecesarios.

Las comprobaciones no ejecutadas no se presentarán como satisfactorias.

## 12. Criterios de aceptación

El producto podrá considerarse validado cuando:

- Se superen las pruebas obligatorias de regresión y de las funcionalidades nuevas.
- Los contratos HTTP y relacionales se respeten.
- Los controles de seguridad y robustez funcionen correctamente.
- El HITL obligatorio del PB02 permanezca operativo.
- No existan falsos éxitos HTTP ni persistencia indebida de resultados tardíos.
- Las evaluaciones documentales acrediten el comportamiento esperado.
- La interfaz funcione exclusivamente mediante HTTP.
- El núcleo conserve su independencia.
- El backend funcione mediante Docker y Render.
- El historial sobreviva al redeploy.
- Los fallos, limitaciones y resultados pendientes estén documentados.

Las validaciones serán obligatorias independientemente de que se ejecuten manualmente o mediante CI automatizada.

La estrategia de integración y despliegue se establece en [16-despliegue.md](16-despliegue.md).