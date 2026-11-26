# Plan de pruebas — ReciclaTÍA PB03

## 1. Objetivo y referencia

Este documento establece los procedimientos de validación de ReciclaTÍA durante el PB03.

La estrategia y los criterios de aceptación se definen en [08-pruebas-y-validacion.md](../specs/08-pruebas-y-validacion.md).

La referencia inicial se encuentra en [baseline-pb02.md](../entregables/evidencias/baseline-pb02.md):

- Commit: 3997e0a.
- Fecha: 24/11/2026.
- Python: 3.13.2.
- Resultado: 358 pruebas superadas en 1,27 segundos.

Las funcionalidades nuevas deberán validarse sin introducir regresiones no autorizadas.

## 2. Preparación y ejecución

### 2.1. Entorno

Desde la raíz del repositorio:

```bash
source .venv/bin/activate

python --version
python -m pip check

git branch --show-current
git rev-parse HEAD
git status --short
```

Comprobar la disponibilidad de los artefactos documentales y reconstruir el índice cuando sea necesario:

```bash
python main.py rag index --yes
```

Los procedimientos de instalación se establecen en [operaciones-despliegue.md](operaciones-despliegue.md).

### 2.2. Aislamiento

Las pruebas utilizarán:

- PostgreSQL independiente de producción.
- Credenciales ficticias o específicas de evaluación.
- Mocks para Gemini y ArcGIS en pruebas ordinarias.
- Checkpoints, sesiones, contadores y archivos temporales aislados.
- Relojes controlados para pruebas temporales.
- Eventos de sincronización para pruebas concurrentes.

### 2.3. Comandos principales

```bash
# Suite completa
python -m pytest tests/ -q --tb=short

# Descubrimiento
python -m pytest tests/ --collect-only -q

# Diagnóstico
python -m pytest tests/ -x --tb=short

# Selección de pruebas
python -m pytest tests/ -k "nombre_de_prueba" -v

# Comprobación sintáctica
python -m py_compile app.py
```

Los scripts que consuman servicios externos se ejecutarán separadamente.

## 3. Regresión del PB02

Se conservarán los siguientes archivos:

| Componente | Archivos de tests/ |
|---|---|
| Recuperación | test_retrieve.py, test_retrieve_structured.py |
| RAG | test_rag.py, test_rag_domain.py, test_rag_structured.py |
| Generación | test_generate.py |
| Herramientas | test_tools_registry.py, test_rag_tool.py, test_api_puntos_limpios.py, test_describir_imagen.py, test_hora_actual.py |
| Agente | test_agent_regression.py, test_agent_resultado.py |
| Horarios | test_agent_schedule.py, test_agent_schedule_integration.py |
| CLI | test_cli.py |

Se ejecutarán las pruebas específicas durante la implementación y la suite completa antes de integrar cambios.

Las modificaciones de pruebas existentes deberán corresponder a cambios de contrato autorizados o correcciones verificadas.

Se conservará el HITL obligatorio del PB02.

La independencia de la CLI se comprobará mediante:

```bash
python main.py --help
python main.py rag --help
python main.py rag query --help
python main.py rag ask --help
python main.py agente demo --help
```

Se ejecutarán consultas representativas sin depender de FastAPI ni PostgreSQL.

## 4. Evaluación documental

### 4.1. Retrieval

```bash
python tests/evaluate_retrieve.py
```

Se utilizarán las 14 consultas etiquetadas existentes, comparando K=3, 5, 8 y 10.

Caché de embeddings:

```text
output/cache/pb02_embeddings_consultas.json
```

Resultados:

```text
output/evaluation/retrieval_pb02.json
```

Se comprobará la compatibilidad de la caché antes de regenerar embeddings.

La evaluación analizará fuentes esperadas, posición de resultados y distancias vectoriales.

Precision@k y Recall@k únicamente se calcularán cuando existan referencias de relevancia adecuadas.

### 4.2. Generación

```bash
# Evaluación completa
python tests/evaluate_rag.py

# Evaluación selectiva
python tests/evaluate_rag.py --ids 9 10 14
```

Resultados:

```text
output/evaluation/rag_pb02.json
```

Casos especialmente relevantes:

| ID | Consulta | Resultado esperado |
|---|---|---|
| 9 | Horario del punto limpio móvil | Aclaración |
| 10 | Tipos de residuos reconocidos | Catálogo estructurado |
| 12 | Horario de piscinas municipales | Abstención |
| 13 | Reciclaje de vidrio en Barcelona | Abstención geográfica |
| 14 | Reparación de móviles cerca de Gran Vía | Abstención |

Los casos 9 y 10 permiten evaluar respuestas estructuradas sin nuevas llamadas a Gemini en la implementación existente.

La revisión factual comprobará las afirmaciones, fuentes, condiciones documentadas y abstenciones conforme a la especificación 08.

Los resultados se asociarán al commit y configuración evaluados.

## 5. Validación de funcionalidades nuevas

Los archivos de pruebas nuevos se crearán durante la implementación, agrupándolos por responsabilidad.

No se considerará obligatorio crear un archivo independiente para cada escenario.

### 5.1. Contratos HTTP

Arrancar el backend una vez implementado:

```bash
python -m uvicorn api.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1 \
  --no-access-log
```

Comprobar:

```text
http://localhost:8000/health
http://localhost:8000/docs
http://localhost:8000/openapi.json
```

Las pruebas automatizadas utilizarán TestClient o HTTPX con dependencias controladas.

| Caso | Entrada o condición | Resultado esperado |
|---|---|---|
| HTTP-01 | Health check operativo | 200 |
| HTTP-02 | Credencial ausente | 401 |
| HTTP-03 | API key inválida | 401 |
| HTTP-04 | Pregunta vacía tras strip() | 400 EMPTY_QUESTION |
| HTTP-05 | Pregunta de 501 caracteres | 422 |
| HTTP-06 | thread_id inválido | 422 |
| HTTP-07 | Coordenadas incompletas o inválidas | 422 |
| HTTP-08 | max_steps fuera de rango | 422 |
| HTTP-09 | Consulta admitida | AskOut válido |
| HTTP-10 | Fallo interno | 500 |
| HTTP-11 | Dependencia indisponible | 503 |
| HTTP-12 | Timeout | 504 |

Comprobar también preguntas de exactamente 500 caracteres, tipos estrictos, campos adicionales y límites válidos.

Todos los endpoints deberán contrastarse con [12-contratos-http.md](../specs/12-contratos-http.md), incluyendo códigos de error, modelos de respuesta y cabeceras.

### Validación de esquemas OpenAPI

Los modelos públicos se comprobarán mediante aplicaciones
FastAPI aisladas dentro de las pruebas automatizadas.

Se verificará:

- Presencia de los modelos públicos.
- Campos obligatorios, opcionales y anulables.
- Valores predeterminados.
- Restricciones numéricas y formatos.
- Enumerados y referencias entre modelos.
- Exclusión de hashes y campos internos.
- Documentación de errores mediante ErrorOut.

La aplicación de producción no incorporará endpoints
artificiales para generar documentación.

La representación de cada endpoint definitivo se comprobará
durante su implementación.

### 5.2. Autenticación y autorización

Preparar:

- Una clave Free anónima.
- Dos usuarios independientes, A y B.
- Una clave Free registrada de A.
- Dos claves User de A.
- Una clave User de B.
- Una clave Admin.

| Bloque | Comprobaciones |
|---|---|
| Registro | Email válido, normalización, duplicados, contraseñas inválidas y registro concurrente |
| Login | Credenciales correctas, incorrectas, usuarios inexistentes y desactivados |
| Sesiones | Caducidad, logout, cambio de contraseña y reinicio |
| Emisión | Free, User autorizado, User no autorizado e intento de emisión Admin |
| Límites | Emisión concurrente, claves activas y reactivaciones |
| Modalidades | API key original, sesión, selección de clave y credenciales incompatibles |
| Propiedad | Claves del mismo usuario, claves ajenas y acceso Admin |
| Administración | Aprovisionamiento idempotente, desactivación, reactivación y eliminación lógica |
| Revocación | Invalidación durante una ejecución |
| Secretos | Hashes protegidos y ausencia de recuperación del secreto original |

Ejecutar las operaciones protegidas con cada perfil y contrastarlas con la matriz de [14-autenticacion-autorizacion.md](../specs/14-autenticacion-autorizacion.md).

Comprobar específicamente que una sesión ordinaria no permite utilizar privilegios Admin y que las claves propias desactivadas permiten consultar el historial autorizado.

### 5.3. Agente, filtrado y HITL

Consulta inicial de referencia:

```json
{
    "pregunta": "¿Dónde puedo reciclar unas pilas?",
    "thread_id": null,
    "auto_aprobar": false,
    "ubicacion": null,
    "max_steps": 3
}
```

| Consulta | Comprobación |
|---|---|
| ¿Dónde tiro una botella de plástico? | Clasificación documental |
| ¿Qué tipos de residuos puedo reciclar? | Catálogo estructurado |
| ¿Qué punto limpio tengo más cerca? | Necesidad de coordenadas |
| ¿Dónde reciclo vidrio en Barcelona? | Restricción geográfica |
| ¿Qué horario tiene el punto limpio móvil? | Aclaración |
| ¿Dónde tiro unas pilas y qué punto compatible tengo cerca? | Consulta compuesta |
| ¿Cómo programo una API? | Filtrado previo |
| ¿Y si es de plástico? | Reformulación contextual |
| ¿Hay uno más cerca? | Conservación del contexto |
| ¿Y mañana? | Interpretación temporal |
| ¿Qué hago con esto? | Ambigüedad |

Las reformulaciones se probarán con y sin contexto autorizado.

Mediante mocks se comprobará que las respuestas deterministas previas no invocan el agente ni consumen recursos externos.

Para cada ejecución satisfactoria de LangGraph se verificará una interrupción real antes de aplicar, incluyendo consultas informativas, abstenciones y aclaraciones.

Resolver una propuesta mediante:

```json
{
    "thread_id": "UUID_REAL_DEL_HILO",
    "approval_id": "UUID_REAL_DE_LA_PROPUESTA",
    "aprobado": true
}
```

| Caso | Comprobación |
|---|---|
| HITL-01 | Aprobación válida |
| HITL-02 | Rechazo y reformulación |
| HITL-03 | Aprobación automática mediante resolución real |
| HITL-04 | Aprobación sin propuesta pendiente |
| HITL-05 | Identificador obsoleto |
| HITL-06 | Aprobación duplicada |
| HITL-07 | Consulta con HITL pendiente |
| HITL-08 | Consulta después de finalizar |
| HITL-09 | Límite de turnos |
| HITL-10 | Resolución del último turno permitido |
| HITL-11 | Checkpoint perdido |
| HITL-12 | Finalización inesperada sin HITL |

Los invariantes de estado se comprobarán conforme a las especificaciones 06 y 12.

### 5.4. Persistencia

#### Pruebas automatizadas de persistencia

Se utilizará PostgreSQL real mediante una base de datos y un usuario exclusivos de pruebas.

La configuración se obtendrá mediante TEST_DATABASE_URL o el archivo privado .env.test.

Las fixtures de tests/conftest.py comprobarán la identidad de la base de datos, el usuario, el host y los permisos antes de inicializar o limpiar las tablas.

La limpieza se realizará mediante TRUNCATE RESTART IDENTITY sobre las cuatro tablas del entorno de pruebas.

No se utilizará CASCADE ni se ejecutará esta limpieza sobre desarrollo o producción.

Las pruebas que compartan esta base de datos se ejecutarán secuencialmente.

| Archivo | Responsabilidad |
|---|---|
| tests/test_db.py | Operaciones de persistencia y consulta |
| tests/test_db_integrity.py | Restricciones, eliminación lógica y rollback |
| tests/test_db_concurrency.py | Bloqueos y concurrencia |
| tests/conftest.py | Inicialización, aislamiento y limpieza |

Las pruebas de integración se identificarán mediante el marcador integration, registrado en pytest.ini.

Ejecutar exclusivamente las pruebas de integración:

```bash
python -m pytest tests/ -m integration -v --tb=short
```

Ejecutar exclusivamente las pruebas unitarias:

```bash
python -m pytest tests/ -m "not integration" -q
```

Ejecutar la validación completa:

```bash
python -m pytest tests/ -q --tb=short
```

La ausencia de configuración de PostgreSQL de pruebas permitirá omitir las pruebas de integración durante el desarrollo ordinario.

Para considerar validada la persistencia será obligatorio ejecutar las pruebas de integración sin omisiones.

Utilizar PostgreSQL real en un entorno de pruebas.

Inspeccionar las tablas:

```sql
\dt

SELECT COUNT(*) FROM conversation;
SELECT COUNT(*) FROM message;
```

Para una conversación concreta:

```sql
SELECT id, role, content, turn_number, created_at
FROM message
WHERE thread_id = 'UUID_REAL_DEL_HILO'
ORDER BY id;
```

| Escenario | Comprobación |
|---|---|
| Respuesta anterior al agente | Sin nueva conversación ni mensajes |
| Plan pendiente | Sin mensajes persistidos |
| Aprobación | Dos mensajes del turno resuelto |
| Rechazo | Pregunta original y respuesta definitiva de rechazo |
| Aprobación repetida | Sin duplicados |
| Fallo de inserción | Rollback y ausencia de almacenamiento parcial |
| Commit incierto | Sin éxito ficticio ni reintento automático |
| Timeout | Sin persistencia tardía |
| Revocación concurrente | Sin escritura no autorizada |
| Eliminación lógica | Conservación de integridad referencial |

Verificar las claves primarias, foráneas, enumerados, restricciones UNIQUE y CHECK de [13-persistencia.md](../specs/13-persistencia.md).

### 5.5. Cuotas y rate limiting

Utilizar un reloj controlado y operaciones que alcancen realmente el limitador evaluado.

| Control | Procedimiento |
|---|---|
| Cuota Free | Admitir dos consultas y rechazar la tercera en la misma ventana |
| Cuota User | Admitir cinco consultas y rechazar la sexta |
| Rate limiting HTTP | Admitir 30 peticiones y rechazar la siguiente |
| Ventana horaria | Distribuir peticiones sin agotar la ventana menor |
| Ventana diaria | Distribuir peticiones entre ventanas horarias |
| Expiración | Avanzar el reloj hasta el límite exacto |
| Retry-After | Comprobar todas las ventanas agotadas |
| Identidades | Verificar contadores independientes |
| Modalidades | Verificar contador compartido para una misma API key |
| Admin | Sin cuota comercial, sujeto a límites técnicos |

Comprobar la contabilización de todos los escenarios establecidos en [15-robustez-observabilidad.md](../specs/15-robustez-observabilidad.md).

Incluir los límites de registro, login y emisión, así como fallos de admisión del executor.

### 5.6. Multimodalidad

Utilizar imágenes sintéticas o archivos autorizados.

| Caso | Archivo o condición |
|---|---|
| IMG-01 | JPEG válido |
| IMG-02 | PNG válido |
| IMG-03 | Peso superior al límite final, adaptable |
| IMG-04 | Resolución superior al límite final, adaptable |
| IMG-05 | Peso superior al límite absoluto |
| IMG-06 | Resolución superior al límite absoluto |
| IMG-07 | Archivo corrupto o vacío |
| IMG-08 | Formato no autorizado |
| IMG-09 | Extensión engañosa |
| IMG-10 | Imagen animada |
| IMG-11 | Riesgo de descompresión excesiva |
| IMG-12 | Cuerpo HTTP excesivo |

Simular adicionalmente los cuatro estados de IdentificacionImagen y las salidas estructuradas inválidas.

Comprobar:

- Restricción multimodal Free.
- Adaptación y validación posterior.
- Eliminación de metadatos.
- Una única identificación visual por consulta.
- Ausencia de LangGraph cuando la imagen no sea admitida.
- Cuotas y turnos correspondientes.
- Limpieza de archivos temporales tras la finalización real.

Los resultados esperados se obtendrán de las especificaciones 05, 12 y 15.

### 5.7. Concurrencia y timeout

Utilizar threading.Event u otros mecanismos de sincronización controlados.

| Escenario | Resultado esperado |
|---|---|
| Dos operaciones sobre el mismo hilo | THREAD_BUSY |
| Worker ocupado y otro hilo | SERVER_BUSY |
| Worker ocupado y health check | Servicio HTTP disponible |
| Dos aprobaciones concurrentes | Una única resolución |
| Ejecución superior al presupuesto | AGENT_TIMEOUT |
| Worker activo después del timeout | Recursos todavía reservados |
| Finalización tardía | Descarte y liberación única |

Simular timeouts durante:

1. Identificación visual.
2. Creación SQL de la conversación.
3. Ejecución de LangGraph.
4. Transición hacia aprobación automática.
5. Resolución HITL.

Verificar los controles de plazo entre fases y la sincronización entre el timeout y el inicio de nuevas operaciones.

Una ejecución invalidada no deberá iniciar posteriormente LangGraph, resolver una nueva aprobación ni persistir mensajes.

Comprobar la invalidación conservadora del hilo cuando su consistencia no pueda garantizarse.

## 6. Seguridad y observabilidad

### 6.1. Pruebas adversariales

| ID | Intento |
|---|---|
| SEC-01 | Ignorar instrucciones o fabricar evidencias |
| SEC-02 | Ejecutar herramientas inexistentes o no autorizadas |
| SEC-03 | Manipular argumentos y presupuestos |
| SEC-04 | Acceder a rutas fuera de assets/ |
| SEC-05 | Escapar mediante enlaces simbólicos |
| SEC-06 | Consultar destinos externos no autorizados o redirecciones incompatibles |
| SEC-07 | Sustituir coordenadas autorizadas |
| SEC-08 | Recuperar credenciales o variables de entorno |
| SEC-09 | Acceder a conversaciones ajenas |
| SEC-10 | Aprobar planes mediante instrucciones al modelo |
| SEC-11 | Introducir instrucciones en documentos |
| SEC-12 | Introducir instrucciones en imágenes |
| SEC-13 | Modificar directamente el estado interno |
| SEC-14 | Fabricar citas o referencias |
| SEC-15 | Ejecutar contenido generado en la interfaz |

Verificar los efectos reales de cada entrada, no únicamente el texto devuelto.

### 6.2. CORS

Configurar un origen autorizado y otro no autorizado.

```bash
curl -i -X OPTIONS \
  http://localhost:8000/ask \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-api-key"
```

Comprobar métodos, cabeceras, orígenes, preflight y ausencia de consumo de cuotas.

### 6.3. Observabilidad

Realizar una petición, recuperar X-Request-ID y localizar su registro:

```bash
docker logs reciclatia-api 2>&1 | grep -F "$REQUEST_ID"
```

Verificar los campos y eventos establecidos en la especificación 15.

Utilizar secretos ficticios identificables para comprobar que no aparecen en registros ni errores.

Distinguir la duración HTTP de la finalización real del worker.

## 7. Validación manual de Streamlit

```bash
python -m streamlit run app.py
```

Ejecutar las comprobaciones primero contra el backend local y después contra Render, modificando únicamente API_BASE_URL.

- [ ] Acceso Free anónimo.
- [ ] Registro, login, cambio de contraseña y logout.
- [ ] Emisión y selección de claves autorizadas.
- [ ] Cambio de identidad y limpieza del contexto.
- [ ] Consultas textuales y multimodales.
- [ ] Restricción multimodal Free.
- [ ] Fuentes, mapas, procedencia y limitaciones.
- [ ] Envío voluntario de coordenadas.
- [ ] Respuestas anteriores al agente sin HITL.
- [ ] Propuestas pendientes con acciones HITL.
- [ ] Aprobación, rechazo y reformulación.
- [ ] Nueva conversación.
- [ ] Historial persistente de solo lectura.
- [ ] Sesión caducada y credenciales revocadas.
- [ ] Cuotas y capacidad agotadas.
- [ ] Backend indisponible.
- [ ] Timeout y respuesta HTTP perdida.
- [ ] Ausencia de reintentos automáticos y envíos duplicados.

El comportamiento esperado se establece en [07-streamlit.md](../specs/07-streamlit.md).

## 8. Infraestructura, recuperación y rendimiento

### 8.1. Docker y Render

Seguir los procedimientos de [operaciones-despliegue.md](operaciones-despliegue.md).

```bash
docker build -t reciclatia-api:local .

docker ps

curl -i http://localhost:8000/health

docker stats --no-stream \
  reciclatia-api \
  reciclatia-postgres
```

Comprobar la construcción sin credenciales de Gemini, la reconstrucción del índice, PostgreSQL, HTTPS, Swagger, los endpoints protegidos y Streamlit.

### 8.2. Persistencia tras redeploy

1. Crear una conversación utilizando una clave User de pruebas.
2. Resolver un turno mediante rechazo para mantener el hilo abierto.
3. Registrar commit, thread_id y mensajes persistidos.
4. Redesplegar el backend conservando PostgreSQL.
5. Comprobar health y autenticación con la misma API key original.
6. Comparar el historial anterior y posterior.
7. Intentar continuar el hilo.

Resultado esperado: historial conservado y THREAD_STATE_LOST al intentar continuar una conversación cuyo checkpoint haya desaparecido.

### 8.3. Rollback

Desplegar una versión anterior compatible con el esquema existente.

Comprobar health, autenticación, historial y funcionalidades principales.

No eliminar la base de datos ni asumir la recuperación de recursos volátiles.

### 8.4. Escenarios de fallo

| ID | Simulación |
|---|---|
| FAIL-01 | PostgreSQL indisponible |
| FAIL-02 | Backend indisponible |
| FAIL-03 | Fallo de ejecución del asistente |

Registrar detección, diagnóstico, impacto, recuperación y validación posterior.

Los procedimientos de resolución se establecen en [gestion-incidencias.md](gestion-incidencias.md).

### 8.5. Rendimiento y consumo

Evaluar consultas deterministas, textuales, estructuradas, compuestas, geográficas y multimodales.

Registrar las métricas de la especificación 08, identificando commit, modelo, configuración, entorno y estado de caché.

Se conservarán los scripts:

```text
tests/smoke_generate.py
tests/prueba_consumo.py
```

Antes de ejecutarlos se comprobará su consumo de servicios externos.

Los resultados servirán para calibrar los timeouts, presupuestos y estimaciones económicas.

## 9. Registro de evidencias

Las evidencias se almacenarán en:

```text
entregables/evidencias/
├── baseline-pb02.md
├── validacion-sprint14.md
├── validacion-sprint15.md
├── validacion-sprint16.md
├── evaluacion-rag.md
├── rendimiento-consumo.md
├── persistencia-redeploy.md
└── validacion-final.md
```

Los documentos se crearán cuando existan resultados reales.

### Plantilla

```markdown
# Evidencia de validación

- Fecha:
- Rama y commit:
- Entorno y configuración:
- Caso o requisito evaluado:
- Procedimiento ejecutado:
- Resultado esperado:
- Resultado observado:
- Pruebas superadas, fallidas y omitidas:
- Duración:
- Evidencias adicionales:
- Estado:
- Incidencias y limitaciones:
```

Estados admitidos: superada, fallida, omitida, bloqueada o pendiente.

No se incluirán secretos ni información personal innecesaria.

Las comprobaciones no ejecutadas no se presentarán como satisfactorias.

## 10. Seguimiento

El seguimiento de las tareas se mantendrá en [plan-trabajo-pb03.md](plan-trabajo-pb03.md).

Los resultados de validación se registrarán en sus evidencias correspondientes, evitando mantener matrices de progreso duplicadas.

La aceptación final se realizará conforme a [08-pruebas-y-validacion.md](../specs/08-pruebas-y-validacion.md).