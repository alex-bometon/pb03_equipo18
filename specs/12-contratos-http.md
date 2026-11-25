# 12. Contratos HTTP

## 1. Objetivo

Definir el contrato de comunicación entre los clientes de ReciclaTÍA y el backend FastAPI.

La API será responsable de validar las peticiones, autenticar las credenciales, comprobar los permisos, ejecutar el asistente, persistir los turnos resueltos y devolver respuestas estructuradas.

Los clientes no podrán modificar directamente el estado de LangGraph.

## 2. Convenciones generales

- API REST sobre HTTP y HTTPS.
- JSON como formato principal de intercambio.
- Multipart/form-data para el envío de imágenes.
- UTF-8 como codificación de caracteres.
- UUID como identificador de conversaciones, usuarios y API keys.
- Fechas almacenadas en UTC y serializadas en formato ISO 8601.
- Validación mediante Pydantic.
- Códigos de estado HTTP coherentes con el resultado de cada operación.
- Credenciales transmitidas mediante cabeceras HTTP.
- Las respuestas públicas no expondrán secretos, rutas internas ni excepciones sin sanitizar.

## 3. Credenciales

### 3.1. API key

Cabecera HTTP:

```http
X-API-Key: <api_key>
```

La API key original no se almacena en texto plano en PostgreSQL.

FastAPI identifica la clave, comprueba su estado, determina su rol y aplica los permisos correspondientes.

### 3.2. Token de sesión

Cabecera HTTP:

```http
Authorization: Bearer <session_token>
```

Identifica a un usuario autenticado para operaciones relacionadas con su cuenta, generación de API keys y consulta del historial de sus claves desactivadas.

El token de sesión será opaco y tendrá caducidad. No se utilizarán JWT ni OAuth en esta primera versión.

### 3.3. Roles de API key

| Rol | Usuario obligatorio | Consultas de texto | Consultas con imagen |
|---|---|---|---|
| free | Opcional | Sí | No |
| user | Sí | Sí | Sí |
| admin | Sí, procedimiento restringido | Sí | Sí |

El rol se determina exclusivamente en el backend. El cliente no puede solicitar una elevación de privilegios.

El registro de un usuario no implica automáticamente la asignación del rol User.

Las API keys Admin únicamente pueden generarse mediante procedimientos administrativos restringidos.

### 3.4. Autenticación mediante sesión y selección de API key

Los usuarios registrados podrán utilizar una API key propia mediante las siguientes cabeceras HTTP:

```http
Authorization: Bearer <session_token>
X-API-Key-Id: <api_key_id>
```

El backend comprobará:

- La validez de la sesión.
- La existencia de la API key.
- Que api_key.user_id coincida con user.id.
- Que api_key.is_active=True.
- Que api_key.deleted_at=NULL.
- Que el rol permita ejecutar la operación solicitada.

Esta modalidad estará disponible para las claves Free registradas y User.

Las claves Admin requieren siempre la credencial original mediante X-API-Key.

No se permitirá combinar ambas modalidades de autenticación en una misma petición.

## 4. Cuotas

| Rol | Por minuto | Por hora | Por 24 horas |
|---|---:|---:|---:|
| free | 2 | 10 | 30 |
| user | 5 | 20 | 45 |
| admin | Sin límite comercial | Sin límite comercial | Sin límite comercial |

Las cuotas se aplican individualmente a cada API key mediante ventanas temporales deslizantes.

POST /ask y POST /ask/image comparten los mismos contadores.

POST /approve resuelve un turno previamente iniciado y no consume una nueva consulta comercial.

Las operaciones HTTP podrán tener un limitador general independiente de las cuotas del asistente.

El administrador estará sujeto a los límites técnicos de seguridad y concurrencia.

## 5. Inventario de endpoints

### 5.1. Endpoints públicos

| Método | Ruta | Responsabilidad |
|---|---|---|
| GET | /health | Estado del servicio y almacenamiento |
| GET | /docs | Documentación Swagger |
| GET | /openapi.json | Especificación OpenAPI |
| POST | /auth/register | Registrar un usuario |
| POST | /auth/login | Autenticar un usuario |
| POST | /api-keys/free | Generar una API key anónima |

La generación de claves Free estará protegida mediante límites de emisión independientes.

### 5.2. Endpoints del asistente

| Método | Ruta | Roles autorizados |
|---|---|---|
| POST | /ask | free, user, admin |
| POST | /ask/image | user, admin |
| POST | /approve | free, user, admin |
| GET | /threads | user, admin |
| GET | /threads/{thread_id} | user, admin |
| GET | /threads/{thread_id}/messages | user, admin |

Todas estas operaciones requieren una API key válida y activa.

Se admiten dos modalidades de autenticación:

- X-API-Key: credencial original de la API key.
- Authorization y X-API-Key-Id: sesión válida y selección de una API key propia, exclusivamente para claves Free registradas y User.

El rol Free puede crear y continuar conversaciones propias y resolver su HITL.

El consumidor Free anónimo no dispone de acceso al historial persistente.

El consumidor Free registrado puede consultar su historial mediante los endpoints autenticados por sesión definidos en el apartado 5.4.

El rol User únicamente puede acceder a las conversaciones de la API key que utiliza en la petición.

El rol Admin puede acceder a cualquier conversación.

### 5.3. Endpoints de cuenta

Requieren una sesión de usuario válida.

| Método | Ruta | Responsabilidad |
|---|---|---|
| POST | /auth/logout | Invalidar la sesión |
| GET | /auth/me | Consultar el usuario autenticado |
| PATCH | /auth/password | Modificar la contraseña |
| POST | /api-keys | Generar una API key Free o User según los permisos del usuario autenticado |
| GET | /api-keys | Listar las claves propias |
| GET | /api-keys/{api_key_id} | Consultar una clave propia |

El backend determinará los roles que el usuario está autorizado a solicitar.

El rol Admin no podrá asignarse mediante este endpoint.

### 5.4. Historial mediante sesión

| Método | Ruta |
|---|---|
| GET | /api-keys/{api_key_id}/threads |
| GET | /api-keys/{api_key_id}/threads/{thread_id} |
| GET | /api-keys/{api_key_id}/threads/{thread_id}/messages |

Estas operaciones permiten a los usuarios registrados consultar el historial de sus API keys Free y User, incluso cuando están desactivadas.

Las API keys eliminadas lógicamente quedan excluidas de estas operaciones.

FastAPI verifica la propiedad de la clave y de la conversación.

Son operaciones exclusivamente de lectura.

### 5.5. Endpoints administrativos

Requieren una API key administrativa activa.

| Método | Ruta | Responsabilidad |
|---|---|---|
| GET | /admin/users | Listar usuarios |
| GET | /admin/users/{user_id} | Consultar usuario |
| PATCH | /admin/users/{user_id} | Modificar estado del usuario |
| DELETE | /admin/users/{user_id} | Eliminar usuario |
| GET | /admin/api-keys | Listar API keys |
| GET | /admin/api-keys/{api_key_id} | Consultar API key |
| POST | /admin/api-keys | Generar API keys Free o User |
| PATCH | /admin/api-keys/{api_key_id} | Modificar estado de la clave |
| DELETE | /admin/api-keys/{api_key_id} | Eliminar API key |

La generación de API keys Admin no estará disponible mediante ningún endpoint de la API.

Las claves Admin se emitirán exclusivamente mediante un procedimiento interno de aprovisionamiento restringido.

La política de eliminación se desarrollará en la especificación de persistencia.

## 6. Contratos Pydantic del asistente

### 6.1. UbicacionIn

| Campo | Tipo | Obligatorio | Restricción |
|---|---|---|---|
| latitud | float | Sí | Entre -90 y 90 |
| longitud | float | Sí | Entre -180 y 180 |

Ambas coordenadas deben ser números finitos.

La ubicación será proporcionada voluntariamente por el usuario.

Inicialmente se utilizarán coordenadas manuales. La geolocalización del navegador queda como ampliación opcional.

FastAPI construirá el objeto de ubicación que consume el agente.

### 6.2. AskIn

| Campo | Tipo | Obligatorio | Default |
|---|---|---|---|
| pregunta | str | Sí | — |
| thread_id | str o None | No | None |
| auto_aprobar | bool | No | True |
| ubicacion | UbicacionIn o None | No | None |
| max_steps | int o None | No | None |

#### Reglas de validación

- pregunta no puede estar vacía ni contener únicamente espacios.
- La longitud máxima es de 500 caracteres.
- thread_id, cuando se proporciona, debe ser un UUID válido.
- max_steps debe estar comprendido entre 1 y 4.
- max_steps=None utiliza la configuración vigente del agente.
- Streamlit enviará explícitamente auto_aprobar=False.
- Swagger podrá utilizar auto_aprobar=True.

#### Ejemplo

```json
{
  "pregunta": "¿Dónde puedo reciclar unas pilas?",
  "thread_id": null,
  "auto_aprobar": false,
  "ubicacion": {
    "latitud": 40.4168,
    "longitud": -3.7038
  },
  "max_steps": 3
}
```

### 6.3. AskOut

Respuesta compartida por POST /ask, POST /ask/image y POST /approve.

| Campo | Tipo | Procedencia |
|---|---|---|
| thread_id | str | Identificador de conversación |
| respuesta | str | Estado del agente |
| plan | list[str] | Estado del agente |
| plan_aprobado | bool o None | Decisión HITL |
| done | bool | Estado de la conversación |
| pendiente_hitl | bool | Checkpoint real de LangGraph |
| fuentes | list[FuenteOut] | Fuentes del agente |
| geografia | list[GeografiaOut] | Evidencias geográficas transformadas |
| abstencion | bool | Estado del agente |
| motivo | str o None | Motivo registrado por el agente |
| estado_evidencia | Literal | suficiente, parcial, insuficiente |
| limitaciones | list[str] | Estado del agente |
| turnos_consumidos | int | Contador de consultas del hilo |
| error | str o None | Error sanitizado |

FuenteOut y GeografiaOut deberán ajustarse a las estructuras reales devueltas por las herramientas existentes.

FastAPI transformará el EstadoProducto en AskOut.

No se serializará directamente la totalidad del estado interno de LangGraph.

#### Ejemplo de respuesta pendiente de HITL

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "respuesta": "Las pilas deben depositarse en puntos de recogida específicos.",
  "plan": [
    "Separar las pilas del resto de residuos.",
    "Depositarlas en un punto de recogida autorizado."
  ],
  "plan_aprobado": null,
  "done": false,
  "pendiente_hitl": true,
  "fuentes": [],
  "geografia": [],
  "abstencion": false,
  "motivo": null,
  "estado_evidencia": "suficiente",
  "limitaciones": [],
  "turnos_consumidos": 1,
  "error": null
}
```

Ejemplo ilustrativo del contrato, no resultado de una ejecución real.

### 6.4. ApproveIn

| Campo | Tipo | Obligatorio |
|---|---|---|
| thread_id | str | Sí |
| aprobado | bool | Sí |

El backend recuperará el estado asociado a la conversación.

No se aceptarán planes, checkpoints ni estados completos proporcionados por el cliente.

```json
{
  "thread_id": "550e8400-e29b-41d4-a716-446655440000",
  "aprobado": true
}
```

### 6.5. MessageOut

| Campo | Tipo |
|---|---|
| role | MessageRole |
| content | str |
| created_at | datetime |

Representa un mensaje recuperado de PostgreSQL.

GET /threads/{thread_id}/messages devuelve una lista de MessageOut ordenada cronológicamente y con un criterio de desempate determinista.

### 6.6. ConversationOut

| Campo | Tipo |
|---|---|
| thread_id | str |
| api_key_id | str |
| created_at | datetime |

Representa la información pública de una conversación.

No contiene el checkpoint interno de LangGraph.

### 6.7. HealthOut

| Campo | Tipo |
|---|---|
| status | str |
| storage | str |

Ejemplo:

```json
{
  "status": "ok",
  "storage": "postgres"
}
```

Si PostgreSQL no está disponible, el servicio no debe declarar falsamente que está operativo.

## 7. Contratos de autenticación y API keys

### RegisterIn

- email: str
- password: str

### LoginIn

- email: str
- password: str

### PasswordChangeIn

- current_password: str
- new_password: str

### UserOut

- id: str
- email: str
- created_at: datetime
- is_active: bool

### LoginOut

- session_token: str
- token_type: str
- expires_at: datetime
- user: UserOut

### ApiKeyOut

- id: str
- role: Literal["free", "user", "admin"]
- user_id: str o None
- is_active: bool
- created_at: datetime
- last_used_at: datetime o None

### ApiKeyCreatedOut

Contiene los campos de ApiKeyOut y la API key original.

La clave original solo se devuelve durante su generación.

Las posteriores consultas de una API key no devuelven el secreto original ni su hash.

La validación de contraseñas, la caducidad de sesiones y las reglas de emisión se desarrollarán en la especificación de autenticación y autorización.

## 8. Contrato multimodal

POST /ask/image utiliza multipart/form-data.

| Campo | Tipo | Obligatorio |
|---|---|---|
| imagen | UploadFile | Sí |
| pregunta | str | Sí |
| thread_id | str | No |
| auto_aprobar | bool | No |
| latitud | float | No |
| longitud | float | No |
| max_steps | int | No |

Los campos compartidos tendrán las mismas restricciones y valores predeterminados que AskIn.

Si se proporciona una coordenada, será obligatorio proporcionar la otra.

### Formatos admitidos

- JPEG.
- PNG.

### Límites finales

| Parámetro | Límite |
|---|---|
| Peso | 5 MiB |
| Resolución | 16.000.000 píxeles |

### Procesamiento

1. Verificar la autorización de la API key.
2. Comprobar las restricciones absolutas de recepción.
3. Identificar el formato real del archivo.
4. Validar la integridad de la imagen.
5. Comprimir o redimensionar cuando sea necesario.
6. Crear un archivo temporal controlado por el backend.
7. Identificar y evaluar semánticamente el contenido de la imagen.
8. Validar el resultado estructurado de la identificación.
9. Detener el flujo si la imagen está fuera de dominio, contiene material no permitido o no puede identificarse con suficiente certeza.
10. Ejecutar el agente únicamente cuando la imagen haya sido admitida, reutilizando la identificación obtenida.
11. Eliminar el archivo cuando ninguna ejecución pueda seguir utilizándolo.

Superar los límites finales no constituye un error si la imagen puede adaptarse correctamente y de forma segura.

No se admitirán rutas de archivos proporcionadas por clientes.

La respuesta será AskOut.

El límite absoluto de recepción y descompresión se concretará en la especificación de robustez.

## 9. Gestión de conversaciones

### 9.1. Creación

Cuando thread_id=None, FastAPI genera un UUID y crea una conversación asociada a la API key utilizada.

Un identificador existente no puede reasignarse a otra API key.

La política de creación cuando el cliente proporciona un UUID todavía inexistente deberá cerrarse antes de implementar POST /ask.

### 9.2. Continuación

Cuando se utiliza un thread_id existente, FastAPI verifica:

- La existencia de la conversación.
- La autorización de acceso.
- La existencia del estado necesario para continuar.
- Que no exista un HITL pendiente.
- Que la conversación no esté finalizada.
- Que no se hayan agotado los turnos.
- Que no exista otra ejecución modificando el mismo hilo.

### 9.3. Propiedad

La propiedad de una conversación corresponde a api_key_id.

Dos API keys pertenecientes al mismo usuario no comparten conversaciones.

Conocer un thread_id no concede permiso para acceder a él.

Para evitar revelar la existencia de conversaciones ajenas, se devolverá THREAD_NOT_FOUND cuando la clave no tenga acceso al hilo.

### 9.4. Reinicio del backend

El historial SQL permanece disponible después de un reinicio.

MemorySaver pierde los checkpoints almacenados en el proceso.

No se reconstruirá automáticamente un estado de LangGraph utilizando únicamente los mensajes SQL.

Cuando una operación requiera un checkpoint perdido, se devolverá un error controlado y se podrá iniciar una nueva conversación.

## 10. HITL

Si el agente genera un plan que requiere aprobación y auto_aprobar=False, devolverá:

- pendiente_hitl=True
- plan_aprobado=None
- done=False

Streamlit habilitará los botones Aprobar y Rechazar únicamente cuando exista una aprobación pendiente.

POST /approve comprobará el checkpoint real de LangGraph.

Si no existe aprobación pendiente, devolverá 409 NO_PENDING_APPROVAL.

### Aprobación

- plan_aprobado=True
- pendiente_hitl=False
- done=True

### Rechazo

- plan_aprobado=False
- pendiente_hitl=False
- done=False

El rechazo resuelve el turno, pero permite continuar la conversación mientras no se agoten sus límites.

### Respuesta sin plan

Cuando el asistente no necesite generar un plan, devolverá una respuesta directa sin solicitar aprobación.

Este comportamiento requiere una adaptación controlada del flujo HITL existente en PB02.

## 11. Persistencia de turnos

Un turno resuelto correctamente se guardará en PostgreSQL mediante una transacción que incluya el mensaje del usuario y el mensaje del asistente.

No se utilizará exclusivamente done=True como criterio de persistencia, porque una respuesta directa o un plan rechazado pueden cerrar un turno sin finalizar la conversación.

Un HITL pendiente todavía no constituye un turno resuelto.

Los errores técnicos no se registrarán como respuestas satisfactorias del asistente.

Se evitará duplicar mensajes al repetir operaciones de aprobación.

## 12. Contrato de errores

Los errores HTTP tendrán una estructura homogénea.

### ErrorOut

| Campo | Tipo |
|---|---|
| code | str |
| message | str |
| request_id | str |

Ejemplo:

```json
{
  "code": "NO_PENDING_APPROVAL",
  "message": "La conversación no tiene ningún plan pendiente de aprobación.",
  "request_id": "550e8400-e29b-41d4-a716-446655440001"
}
```

El código HTTP se transmite como estado de la respuesta.

No se devolverán stack traces, secretos ni información interna del servidor.

Los errores de validación de FastAPI se adaptarán al contrato común.

## 13. Catálogo de errores

### 13.1. Autenticación y autorización

| HTTP | Código | Situación |
|---|---|---|
| 401 | API_KEY_REQUIRED | No se proporciona una clave obligatoria |
| 401 | INVALID_API_KEY | La clave no es válida |
| 401 | INVALID_CREDENTIALS | Email o contraseña incorrectos |
| 401 | INVALID_SESSION | Sesión inexistente o inválida |
| 401 | SESSION_EXPIRED | Sesión caducada |
| 403 | API_KEY_INACTIVE | Clave desactivada |
| 403 | USER_INACTIVE | Usuario desactivado |
| 403 | INSUFFICIENT_PERMISSIONS | Rol sin permisos para la operación |
| 403 | USER_TIER_NOT_AUTHORIZED | Usuario sin autorización para acceder al nivel User |

### 13.2. Recursos

| HTTP | Código | Situación |
|---|---|---|
| 404 | THREAD_NOT_FOUND | Conversación inexistente o no accesible |
| 404 | USER_NOT_FOUND | Usuario inexistente |
| 404 | API_KEY_NOT_FOUND | Clave inexistente o no accesible |
| 409 | EMAIL_ALREADY_EXISTS | Email registrado previamente |
| 409 | API_KEY_LIMIT_REACHED | Número máximo de API keys activas alcanzado |

### 13.3. Conversaciones y HITL

| HTTP | Código | Situación |
|---|---|---|
| 409 | NO_PENDING_APPROVAL | No existe HITL pendiente |
| 409 | PENDING_APPROVAL | Se intenta iniciar un turno con HITL pendiente |
| 409 | THREAD_CLOSED | Conversación finalizada |
| 409 | TURN_LIMIT_REACHED | Límite de turnos agotado |
| 409 | THREAD_BUSY | Otra petición está modificando el hilo |
| 409 | THREAD_STATE_LOST | El estado necesario para continuar no está disponible |

### 13.4. Validación

| HTTP | Código | Situación |
|---|---|---|
| 422 | EMPTY_QUESTION | Pregunta vacía |
| 422 | QUESTION_TOO_LONG | Pregunta superior a 500 caracteres |
| 422 | INVALID_THREAD_ID | Identificador inválido |
| 422 | INVALID_LOCATION | Coordenadas inválidas o incompletas |
| 422 | INVALID_MAX_STEPS | Límite de pasos inválido |
| 422 | VALIDATION_ERROR | Incumplimiento del contrato de entrada |
| 422 | INVALID_EMAIL | Formato de email inválido |
| 422 | INVALID_PASSWORD | Contraseña que incumple los requisitos de seguridad |
| 422 | AMBIGUOUS_CREDENTIALS | Combinación incompatible de modalidades de autenticación |

### 13.5. Imágenes

| HTTP | Código | Situación |
|---|---|---|
| 413 | IMAGE_FILE_TOO_LARGE | No puede reducirse el peso o supera el límite absoluto |
| 422 | IMAGE_RESOLUTION_EXCEEDED | No puede adaptarse la resolución de forma segura |
| 422 | IMAGE_CORRUPTED | Imagen vacía, corrupta o ilegible |
| 422 | IMAGE_CONTENT_NOT_ALLOWED | La imagen contiene material que vulnera las políticas de contenido |
| 415 | IMAGE_FORMAT_NOT_ALLOWED | Formato no admitido |

### 13.6. Cuotas y robustez

| HTTP | Código | Situación |
|---|---|---|
| 429 | RATE_LIMIT_EXCEEDED | Límite de peticiones o cuota alcanzado |
| 500 | INTERNAL_SERVER_ERROR | Fallo interno inesperado |
| 503 | SERVICE_NOT_CONFIGURED | Configuración imprescindible ausente |
| 503 | SERVICE_UNAVAILABLE | Servicio o dependencia no disponible |
| 503 | SERVER_BUSY | Capacidad de ejecución agotada |
| 504 | AGENT_TIMEOUT | Tiempo máximo de ejecución superado |

Las respuestas 429 incluirán Retry-After cuando sea posible determinar el tiempo de reintento.

## 14. Situaciones que no constituyen errores

| HTTP | Situación |
|---|---|
| 200 | Consulta respondida correctamente |
| 200 | Respuesta directa sin plan |
| 200 | Plan pendiente de HITL |
| 200 | Plan aprobado |
| 200 | Plan rechazado |
| 200 | Abstención por falta de evidencia |
| 200 | Consulta fuera del dominio |
| 200 | Solicitud de aclaración |
| 200 | Coordenadas no proporcionadas cuando no son obligatorias |
| 200 | No se encuentran puntos limpios compatibles |
| 200 | Uso del corpus local como respaldo autorizado |
| 200 | Imagen comprimida correctamente |
| 200 | Imagen redimensionada correctamente |
| 200 | Historial propio sin mensajes |
| 200 | Imagen identificada como fuera de dominio |
| 200 | Solicitud de una nueva imagen por identificación incierta |
| 201 | Usuario registrado correctamente |
| 201 | API key generada correctamente |
| 204 | Cierre de sesión correcto |
| 204 | Eliminación correcta de un recurso |

Estas respuestas serán deterministas, no generarán un plan ni requerirán aprobación HITL y no continuarán con la ejecución del asistente.

Una abstención semántica no debe confundirse con un fallo técnico.

## 15. Observabilidad

Cada petición protegida generará un registro con:

- request_id.
- Método HTTP.
- Ruta.
- thread_id, cuando corresponda.
- duration_ms.
- Código de estado HTTP.

No se registrarán API keys originales, tokens de sesión, contraseñas, cadenas de conexión ni contenido binario de imágenes.

## 16. Criterios de aceptación

- Swagger muestra los contratos y endpoints implementados.
- Los endpoints protegidos rechazan peticiones sin API key.
- Las API keys Free se generan automáticamente.
- Las API keys User se generan a petición del usuario autenticado.
- Las conversaciones se aíslan por API key.
- Una clave desactivada no permite realizar nuevas consultas.
- Su propietario puede consultar el historial mediante una sesión válida.
- Un administrador puede consultar cualquier conversación.
- Las cuotas se aplican de manera independiente por clave.
- El HITL no puede resolverse sin una interrupción pendiente real.
- Las imágenes se reciben mediante HTTP sin aceptar rutas locales del cliente.
- Los errores HTTP respetan el contrato definido.
- Las abstenciones válidas no se presentan como errores técnicos.
- El historial de turnos resueltos sobrevive a un redeploy.
- Dos conversaciones concurrentes no mezclan sus estados.
- Los logs no contienen secretos.
