# 12. Contratos HTTP

## 1. Convenciones

La API de ReciclaTÍA utilizará FastAPI y Pydantic.

- JSON como formato principal y multipart/form-data para imágenes.
- HTTP en desarrollo y HTTPS en producción.
- UUID serializados como cadenas.
- Fechas UTC en formato ISO 8601.
- Modelos públicos independientes del estado interno y de los modelos relacionales.
- Validación de entradas y resultados antes de comunicar éxito.
- Rechazo de campos adicionales no autorizados.

Los errores técnicos se comunicarán mediante ErrorOut y códigos HTTP no satisfactorios.

## 2. Autenticación

| Modalidad | Cabeceras |
|---|---|
| API key original | X-API-Key |
| Sesión de usuario | Authorization: Bearer |
| Sesión y clave propia seleccionada | Authorization: Bearer y X-API-Key-Id |

No se combinará X-API-Key con las modalidades de sesión.

La selección mediante sesión únicamente estará disponible para claves propias Free registradas y User.

Las claves Admin requerirán siempre su credencial original.

Las cabeceras de autenticación duplicadas o incompatibles devolverán 422 AMBIGUOUS_CREDENTIALS.

Los endpoints de cuenta exigirán una sesión sin selección de clave. Los endpoints del asistente exigirán una API key original o una clave propia seleccionada mediante sesión.

Los endpoints administrativos exigirán una API key Admin original.

Las reglas de autenticación, autorización y propiedad se establecen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

## 3. Endpoints

### 3.1. Públicos

| Método | Ruta | Entrada | Éxito |
|---|---|---|---|
| GET | /health | — | 200 HealthOut |
| GET | /docs | — | 200 |
| GET | /openapi.json | — | 200 |
| POST | /auth/register | RegisterIn | 201 UserOut |
| POST | /auth/login | LoginIn | 200 LoginOut |
| POST | /api-keys/free | Sin cuerpo | 201 ApiKeyCreatedOut |

### 3.2. Asistente

| Método | Ruta | Roles | Entrada | Éxito |
|---|---|---|---|---|
| POST | /ask | free, user, admin | AskIn | 200 AskOut |
| POST | /ask/image | user, admin | Multipart | 200 AskOut |
| POST | /approve | free, user, admin | ApproveIn | 200 AskOut |
| GET | /threads | user, admin | — | 200 list[ConversationOut] |
| GET | /threads/{thread_id} | user, admin | — | 200 ConversationOut |
| GET | /threads/{thread_id}/messages | user, admin | — | 200 list[MessageOut] |

Requieren una API key válida y activa, mediante una modalidad de autenticación autorizada.

### 3.3. Cuenta

Requieren una sesión válida.

| Método | Ruta | Entrada | Éxito |
|---|---|---|---|
| POST | /auth/logout | — | 204 |
| GET | /auth/me | — | 200 UserOut |
| PATCH | /auth/password | PasswordChangeIn | 200 UserOut |
| POST | /api-keys | ApiKeyCreateIn | 201 ApiKeyCreatedOut |
| GET | /api-keys | — | 200 list[ApiKeyOut] |
| GET | /api-keys/{api_key_id} | — | 200 ApiKeyOut |

### 3.4. Historial mediante sesión

Requiere una sesión válida y propiedad de la clave Free o User.

| Método | Ruta | Éxito |
|---|---|---|
| GET | /api-keys/{api_key_id}/threads | 200 list[ConversationOut] |
| GET | /api-keys/{api_key_id}/threads/{thread_id} | 200 ConversationOut |
| GET | /api-keys/{api_key_id}/threads/{thread_id}/messages | 200 list[MessageOut] |

Permite consultar claves propias desactivadas, pero no eliminadas lógicamente.

El acceso al historial no implica recuperar el checkpoint ni autoriza nuevas ejecuciones.

### 3.5. Administración

Requiere una API key Admin original y activa.

| Método | Ruta | Entrada | Éxito |
|---|---|---|---|
| GET | /admin/users | — | 200 list[UserOut] |
| GET | /admin/users/{user_id} | — | 200 UserOut |
| PATCH | /admin/users/{user_id} | ActiveStatusIn | 200 UserOut |
| DELETE | /admin/users/{user_id} | — | 204 |
| GET | /admin/api-keys | — | 200 list[ApiKeyOut] |
| GET | /admin/api-keys/{api_key_id} | — | 200 ApiKeyOut |
| POST | /admin/api-keys | AdminApiKeyCreateIn | 201 ApiKeyCreatedOut |
| PATCH | /admin/api-keys/{api_key_id} | ActiveStatusIn | 200 ApiKeyOut |
| DELETE | /admin/api-keys/{api_key_id} | — | 204 |

Las operaciones DELETE realizarán eliminación lógica.

Ningún endpoint permitirá emitir claves Admin.

## 4. Contratos del asistente

Los modelos se definirán en api/schemas.py.

Los campos de tipo opcional que puedan omitirse tendrán valor predeterminado None, salvo indicación contraria.

### 4.1. UbicacionIn

| Campo | Tipo | Restricción |
|---|---|---|
| latitud | float | [-90, 90] |
| longitud | float | [-180, 180] |

Ambos campos serán obligatorios, numéricos, finitos y no booleanos.

### 4.2. AskIn

| Campo | Tipo | Default |
|---|---|---|
| pregunta | str | Obligatorio |
| thread_id | str o None | None |
| auto_aprobar | bool | True |
| ubicacion | UbicacionIn o None | None |
| max_steps | int o None | None |

Reglas:

- pregunta deberá ser una cadena y se normalizará mediante strip().
- Una pregunta vacía devolverá HTTP 400 EMPTY_QUESTION.
- La longitud máxima será de 500 caracteres después de strip().
- thread_id, cuando exista, deberá ser un UUID válido.
- max_steps deberá estar comprendido entre 1 y 4, sin admitir booleanos.
- auto_aprobar deberá ser un booleano válido.
- Streamlit enviará explícitamente auto_aprobar=False.

La pregunta vacía se tratará mediante una regla de negocio, no mediante una restricción Pydantic que produzca automáticamente HTTP 422.

### 4.3. AskOut

Respuesta de POST /ask, POST /ask/image y POST /approve.

| Campo | Tipo |
|---|---|
| thread_id | str o None |
| respuesta | str |
| plan | list[str] |
| plan_aprobado | bool o None |
| done | bool |
| pendiente_hitl | bool |
| fuentes | list[FuenteOut] |
| geografia | list[GeografiaOut] |
| abstencion | bool |
| motivo | str o None |
| estado_evidencia | Literal suficiente, parcial, insuficiente |
| limitaciones | list[str] |
| turnos_consumidos | int |
| error | str o None |
| approval_id | str o None |

Todos los campos estarán presentes en la respuesta.

respuesta será una cadena no vacía y turnos_consumidos será mayor o igual que cero.

error será siempre None en las respuestas satisfactorias.

#### Invariantes de estado

| Resultado | pendiente_hitl | plan_aprobado | done | approval_id |
|---|---|---|---|---|
| Respuesta anterior al agente | False | None | False | None |
| Propuesta pendiente | True | None | False | UUID válido |
| Plan aprobado | False | True | True | None |
| Plan rechazado | False | False | False | None |

Una propuesta pendiente o aprobada conservará un plan válido.

Una respuesta anterior al agente o un plan rechazado devolverá plan=[].

En las respuestas anteriores a LangGraph:

- fuentes=[].
- geografia=[].
- abstencion=True.
- estado_evidencia=insuficiente.
- thread_id=None y turnos_consumidos=0 cuando no exista conversación previa.
- Se conservarán el identificador y contador existentes cuando corresponda.

Las respuestas anteriores al agente no modificarán el checkpoint.

### 4.4. FuenteOut

| Campo | Tipo |
|---|---|
| chunk_id | str |
| source | str |
| url | HttpUrl o None |
| rol | Literal residuos, puntos o None |
| id_llamada | str o None |

chunk_id y source serán cadenas no vacías.

Las referencias procederán de evidencias documentales validadas.

Las URL se resolverán mediante el catálogo de [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

Los identificadores de cita tendrán alcance local por llamada, conforme a [03-generacion.md](03-generacion.md).

No se expondrán rutas internas, embeddings ni el contenido completo de los chunks.

### 4.5. PuntoLimpioOut

| Campo | Tipo | Restricción |
|---|---|---|
| tipo | str | No vacío |
| direccion | str | No vacío |
| distrito | str o None | — |
| latitud | float | [-90, 90] |
| longitud | float | [-180, 180] |
| distancia_metros | float | Mayor o igual que cero |
| horario_apertura | str o None | — |
| horario_cierre | str o None | — |
| dia_semana | str o None | — |
| turno | str o None | — |
| documento_origen | str o None | — |

Los valores numéricos serán finitos.

Las distancias serán geográficas en línea recta.

Los horarios publicados no constituirán una garantía de apertura física.

### 4.6. GeografiaOut

| Campo | Tipo | Restricción |
|---|---|---|
| fuente | Literal api, corpus_local | — |
| tipo_solicitado | Literal todos, fijo, movil, proximidad | — |
| radio_metros | int | 1–5000 |
| total_encontrados | int | Mayor o igual que cero |
| puntos | list[PuntoLimpioOut] | Máximo 10 |
| aviso | str o None | — |

puntos contendrá los registros más próximos, ordenados por distancia y situados dentro del radio consultado.

total_encontrados representará el número de registros válidos antes de limitar su presentación.

La longitud de puntos será min(total_encontrados, 10).

El respaldo local incluirá un aviso sobre su posible desactualización.

geografia=[] indica ausencia de una búsqueda geográfica satisfactoria. Una búsqueda válida sin coincidencias se representará mediante GeografiaOut con total_encontrados=0 y puntos=[].

puntos_candidatos permanecerá como atributo interno.

### 4.7. ApproveIn

| Campo | Tipo |
|---|---|
| thread_id | str |
| approval_id | str |
| aprobado | bool |

Todos los campos serán obligatorios.

Los identificadores deberán ser UUID válidos y aprobado será un booleano estricto.

El cliente no proporcionará planes, checkpoints ni estados completos.

### 4.8. MessageOut

| Campo | Tipo |
|---|---|
| role | MessageRole |
| content | str |
| created_at | datetime |

MessageRole admitirá user y assistant.

Los mensajes se devolverán ordenados por su identificador relacional ascendente.

No se expondrán el identificador interno ni turn_number.

### 4.9. ConversationOut

| Campo | Tipo |
|---|---|
| thread_id | str |
| api_key_id | str |
| created_at | datetime |

No incluirá información sobre el estado operativo ni aprobaciones pendientes.

### 4.10. HealthOut

| Campo | Tipo |
|---|---|
| status | str |
| storage | str |

Respuesta satisfactoria:

```json
{
    "status": "ok",
    "storage": "postgres"
}
```

GET /health comprobará los recursos imprescindibles conforme a [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

Si el servicio no está preparado, devolverá HTTP 503 mediante ErrorOut.

## 5. Contratos de cuentas y credenciales

### 5.1. Modelos de entrada

| Modelo | Campos |
|---|---|
| RegisterIn | email: str, password: str |
| LoginIn | email: str, password: str |
| PasswordChangeIn | current_password: str, new_password: str |
| ApiKeyCreateIn | role: Literal free, user; default free |
| AdminApiKeyCreateIn | role: Literal free, user; user_id: UUID o None |
| ActiveStatusIn | is_active: StrictBool |

Los campos serán obligatorios salvo los valores opcionales expresamente indicados.

Reglas particulares:

- La confirmación de contraseña pertenece al cliente.
- POST /api-keys obtiene el propietario de la sesión.
- AdminApiKeyCreateIn permite user_id=None para Free y exige un propietario para User.
- ActiveStatusIn únicamente permite modificar is_active.
- POST /api-keys/free no admite cuerpo de entrada y genera exclusivamente una clave Free anónima.

Las condiciones de emisión, modificación y validación se establecen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

### 5.2. UserOut

| Campo | Tipo |
|---|---|
| id | UUID |
| email | str |
| created_at | datetime |
| is_active | bool |
| deleted_at | datetime o None |

deleted_at será obligatorio y admitirá None. Un usuario eliminado no podrá tener is_active=True.

### 5.3. LoginOut

| Campo | Tipo |
|---|---|
| session_token | str |
| token_type | str |
| expires_at | datetime |
| user | UserOut |

token_type identificará la modalidad Bearer.

### 5.4. ApiKeyOut

| Campo | Tipo |
|---|---|
| id | UUID |
| role | ApiKeyRole |
| user_id | UUID o None |
| is_active | bool |
| created_at | datetime |
| last_used_at | datetime o None |
| deleted_at | datetime o None |

ApiKeyRole admitirá free, user y admin.

### 5.5. ApiKeyCreatedOut

Extiende ApiKeyOut incorporando api_key: str.

La credencial original únicamente se devolverá durante su emisión, después de confirmar la transacción.

Los tokens y API keys originales se devolverán con la cabecera:

```http
Cache-Control: no-store
```

Los modelos públicos no incluirán hashes ni contraseñas.

## 6. Contrato multimodal

POST /ask/image utilizará multipart/form-data.

| Campo | Tipo | Obligatorio |
|---|---|---|
| imagen | UploadFile | Sí |
| pregunta | str | Sí |
| thread_id | str o None | No |
| auto_aprobar | bool | No |
| latitud | float o None | No |
| longitud | float o None | No |
| max_steps | int o None | No |

Los campos compartidos respetarán los valores predeterminados y restricciones de AskIn.

Las coordenadas deberán proporcionarse conjuntamente.

Los campos escalares recibidos mediante multipart/form-data se convertirán explícitamente a sus tipos autorizados antes de aplicar las validaciones compartidas. No se admitirán conversiones ambiguas ni valores incompatibles con el contrato.

Los formatos autorizados, límites de recepción, adaptación y procesamiento se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

No se aceptarán rutas locales del cliente.

### Identificación semántica

| Estado | Resultado HTTP |
|---|---|
| allowed | Continuar hacia LangGraph |
| out_of_domain | 200 AskOut anterior al agente |
| uncertain | 200 AskOut solicitando otra imagen |
| policy_violation | 422 IMAGE_CONTENT_NOT_ALLOWED |
| Identificación técnicamente inválida | ErrorOut |

El contrato interno de identificación se define en [05-tools.md](05-tools.md).

## 7. Conversaciones, HITL y persistencia

### 7.1. Identificación

| thread_id recibido | Comportamiento |
|---|---|
| None u omitido | Generar UUID al admitir la ejecución de LangGraph |
| Formato inválido | 422 INVALID_THREAD_ID |
| UUID inexistente o no autorizado | 404 THREAD_NOT_FOUND |
| UUID existente y autorizado | Comprobar estado operativo |

El backend no aceptará UUID desconocidos como identificadores de conversaciones nuevas.

La autorización y las restricciones de estado se comprobarán también antes de resolver respuestas previas al agente.

### 7.2. HITL

Toda ejecución satisfactoria de LangGraph deberá alcanzar su interrupción HITL real.

- auto_aprobar=False devolverá la propuesta pendiente.
- auto_aprobar=True resolverá la aprobación mediante el mismo mecanismo que POST /approve.
- POST /approve comprobará el checkpoint y approval_id vigentes.
- Aprobar finalizará la conversación.
- Rechazar resolverá el turno y permitirá reformular dentro de sus límites.

La resolución interna se establece en [06-langgraph.md](06-langgraph.md).

### 7.3. Persistencia

Únicamente se almacenarán mensajes correspondientes a turnos de LangGraph correctamente resueltos mediante aprobación o rechazo.

Se confirmará la persistencia antes de devolver HTTP 200 para un turno resuelto.

Las respuestas previas, propuestas pendientes, fallos técnicos y resultados tardíos no generarán mensajes persistidos.

Los requisitos transaccionales se establecen en [13-persistencia.md](13-persistencia.md).

### 7.4. Estado perdido o incierto

Un checkpoint perdido o inconsistente devolverá HTTP 409 THREAD_STATE_LOST cuando se intente continuar el hilo.

No se reconstruirán checkpoints desde PostgreSQL.

No se incorporarán mecanismos de idempotencia ni endpoints de recuperación de estado durante el PB03.

El tratamiento de respuestas HTTP perdidas corresponde al cliente, conforme a [07-streamlit.md](07-streamlit.md).

## 8. Contrato de errores

### 8.1. ErrorOut

| Campo | Tipo |
|---|---|
| code | str |
| message | str |
| request_id | str |

Los errores de validación de FastAPI se adaptarán a este contrato.

No se expondrán secretos, consultas SQL, stack traces, excepciones completas ni datos de recursos ajenos.

### 8.2. Autenticación y autorización

| HTTP | Código |
|---|---|
| 401 | API_KEY_REQUIRED |
| 401 | INVALID_API_KEY |
| 401 | INVALID_CREDENTIALS |
| 401 | INVALID_SESSION |
| 401 | SESSION_EXPIRED |
| 403 | API_KEY_INACTIVE |
| 403 | USER_INACTIVE |
| 403 | INSUFFICIENT_PERMISSIONS |
| 403 | USER_TIER_NOT_AUTHORIZED |

### 8.3. Recursos

| HTTP | Código |
|---|---|
| 404 | THREAD_NOT_FOUND |
| 404 | USER_NOT_FOUND |
| 404 | API_KEY_NOT_FOUND |
| 409 | EMAIL_ALREADY_EXISTS |
| 409 | API_KEY_LIMIT_REACHED |
| 409 | API_KEY_DELETED |
| 409 | USER_DELETED |

Los estados de recursos eliminados únicamente se comunicarán cuando exista autorización para conocerlos.

### 8.4. Conversaciones y HITL

| HTTP | Código | Situación |
|---|---|---|
| 409 | NO_PENDING_APPROVAL | No existe aprobación pendiente |
| 409 | PENDING_APPROVAL | Nueva consulta durante HITL |
| 409 | THREAD_CLOSED | Conversación finalizada |
| 409 | TURN_LIMIT_REACHED | Turnos agotados |
| 409 | THREAD_BUSY | Modificación concurrente |
| 409 | THREAD_STATE_LOST | Estado perdido o inconsistente |
| 409 | STALE_APPROVAL | approval_id distinto del vigente |

### 8.5. Validación

| HTTP | Código | Situación |
|---|---|---|
| 400 | EMPTY_QUESTION | Pregunta vacía tras strip() |
| 422 | QUESTION_TOO_LONG | Supera 500 caracteres |
| 422 | INVALID_THREAD_ID | UUID de conversación inválido |
| 422 | INVALID_LOCATION | Coordenadas inválidas o incompletas |
| 422 | INVALID_MAX_STEPS | Número de pasos inválido |
| 422 | INVALID_EMAIL | Email inválido |
| 422 | INVALID_PASSWORD | Contraseña incompatible |
| 422 | AMBIGUOUS_CREDENTIALS | Modalidades de autenticación incompatibles |
| 422 | VALIDATION_ERROR | Otro incumplimiento del contrato |

Un approval_id con formato inválido devolverá VALIDATION_ERROR.

### 8.6. Imágenes

| HTTP | Código | Situación |
|---|---|---|
| 413 | IMAGE_FILE_TOO_LARGE | Límite absoluto o peso no adaptable |
| 415 | IMAGE_FORMAT_NOT_ALLOWED | Formato no admitido |
| 422 | IMAGE_RESOLUTION_EXCEEDED | Resolución absoluta o no adaptable |
| 422 | IMAGE_CORRUPTED | Archivo vacío, corrupto o ilegible |
| 422 | IMAGE_CONTENT_NOT_ALLOWED | Contenido no permitido |

La falta de permiso multimodal devolverá HTTP 403 INSUFFICIENT_PERMISSIONS.

### 8.7. Robustez y dependencias

| HTTP | Código | Situación |
|---|---|---|
| 429 | RATE_LIMIT_EXCEEDED | Límite o cuota alcanzado |
| 500 | INTERNAL_SERVER_ERROR | Fallo interno o resultado inválido |
| 503 | SERVICE_NOT_CONFIGURED | Configuración imprescindible ausente |
| 503 | SERVICE_UNAVAILABLE | Dependencia indisponible |
| 503 | SERVER_BUSY | Capacidad agotada |
| 504 | AGENT_TIMEOUT | Presupuesto temporal superado |

Cuando no pueda determinarse una causa técnica más específica, se utilizará INTERNAL_SERVER_ERROR.

No se utilizarán mensajes generados por el LLM para determinar códigos HTTP.

### 8.8. Protocolo HTTP

| HTTP | Código | Situación |
|---|---|---|
| 400 | BAD_REQUEST | Petición no interpretable |
| 404 | ROUTE_NOT_FOUND | Ruta inexistente |
| 405 | METHOD_NOT_ALLOWED | Método HTTP no permitido |

Los errores generados por el framework se adaptarán a ErrorOut.

Se conservarán las cabeceras necesarias del protocolo, como Allow
y WWW-Authenticate, cuando corresponda.

No se expondrán directamente los detalles internos de las excepciones
del framework.

### 8.9. Catálogo y tratamiento centralizado

Los códigos públicos, estados HTTP y mensajes se centralizarán
en api/error_catalog.py.

Los errores controlados de la API se representarán mediante ApiError,
sin permitir mensajes públicos personalizados.

El contrato ErrorOut utilizará códigos reconocidos por el catálogo,
mensajes no vacíos e identificadores UUID en formato canónico.

Los errores de validación del núcleo y de las credenciales se
traducirán según su tipo y contexto, sin interpretar mensajes
de excepciones.

Los incumplimientos de la política de creación de contraseñas
devolverán INVALID_PASSWORD.

Las contraseñas incorrectas o incompatibles utilizadas para
autenticación devolverán INVALID_CREDENTIALS.

Retry-After podrá proporcionarse mediante un entero no negativo
cuando se produzca RATE_LIMIT_EXCEEDED.

Los manejadores utilizarán un mecanismo común de construcción de
respuestas de error.

Las respuestas de rechazo preflight generadas por CORSMiddleware conservarán su formato nativo. Incluirán X-Request-ID, pero no estarán sujetas a ErrorOut.

Los errores de validación se identificarán mediante su tipo,
ubicación y operación HTTP, sin repetir las validaciones
realizadas por los modelos.

Cuando se detecten varios errores simultáneamente, se aplicará
la siguiente prioridad:

1. INVALID_CREDENTIALS.
2. INVALID_THREAD_ID.
3. INVALID_EMAIL.
4. INVALID_PASSWORD.
5. EMPTY_QUESTION.
6. QUESTION_TOO_LONG.
7. INVALID_LOCATION.
8. INVALID_MAX_STEPS.
9. VALIDATION_ERROR.

La prioridad se aplicará exclusivamente a los errores
efectivamente detectados.

Las inconsistencias en modelos de salida y las excepciones
internas no clasificadas devolverán INTERNAL_SERVER_ERROR.

La documentación OpenAPI de errores se construirá mediante
build_error_responses(), utilizando el catálogo centralizado.

Cada endpoint declarará únicamente los códigos de error
aplicables a su operación. Cuando corresponda, documentará
ErrorOut como respuesta HTTP 422 en lugar del contrato
predeterminado de FastAPI.

## 9. Resultados válidos y falsos éxitos

No constituyen errores HTTP:

- Una propuesta pendiente de HITL.
- La aprobación o el rechazo correctamente resueltos.
- Una abstención o aclaración legítima.
- Una consulta fuera de dominio resuelta antes del agente.
- Una identificación visual fuera de dominio o incierta.
- Una imagen correctamente adaptada.
- Una búsqueda geográfica válida sin coincidencias.
- La utilización satisfactoria del respaldo local.
- Un historial autorizado vacío.

Las abstenciones y aclaraciones obtenidas dentro de LangGraph conservarán el HITL obligatorio.

No se devolverá HTTP 200 ante resultados estructuralmente inválidos, fallos técnicos imprescindibles, inconsistencias del checkpoint, persistencia obligatoria no confirmada o timeouts.

## 10. Cabeceras y trazabilidad

| Cabecera de respuesta | Aplicación |
|---|---|
| X-Request-ID | Todas las peticiones HTTP |
| Retry-After | HTTP 429 cuando pueda determinarse |
| Cache-Control: no-store | Emisión de credenciales originales |
| WWW-Authenticate | Errores 401 asociados a API key o sesión |

request_id será generado por el backend y coincidirá con el incluido en ErrorOut.

Las cuotas, controles de admisión, concurrencia, procesamiento multimedia, logging y CORS se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

La validación de los contratos se realizará conforme a [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).