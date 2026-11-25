# 14. Autenticación y autorización

## 1. Objetivo

Definir los mecanismos de identificación, autenticación, autorización y gestión de credenciales de ReciclaTÍA.

Las decisiones de seguridad serán deterministas y responsabilidad exclusiva del backend.

Los contratos HTTP se establecen en [12-contratos-http.md](12-contratos-http.md) y el almacenamiento relacional en [13-persistencia.md](13-persistencia.md).

## 2. Identidades y roles

Se distinguirán tres elementos:

- Usuario: identidad registrada.
- Sesión: autenticación temporal de un usuario.
- API key: credencial que determina los permisos de acceso al asistente.

El rol pertenece a la API key, no al usuario.

Se utilizará el enumerado compartido de src/enums.py:

```python
from enum import Enum


class ApiKeyRole(str, Enum):
    FREE = "free"
    USER = "user"
    ADMIN = "admin"
```

### 2.1. Permisos

| Funcionalidad | Free anónimo | Free registrado | User | Admin |
|---|---|---|---|---|
| Registro obligatorio | No | Sí | Sí | Sí |
| Consultas textuales | Sí | Sí | Sí | Sí |
| Consultas multimodales | No | No | Sí | Sí |
| Resolución HITL | Sí | Sí | Sí | Sí |
| Historial mediante API key original | No | No | Propio | Global |
| Historial de claves propias mediante sesión | No | Sí | Sí | Sí, para claves no administrativas |
| Administración global | No | No | No | Sí |
| Cuotas comerciales | Free | Free | User | Sin límite comercial |
| Límites técnicos | Sí | Sí | Sí | Sí |

El registro no concede automáticamente permisos User ni Admin.

Una cuenta que posea una API key Admin no adquiere privilegios administrativos mediante su sesión ordinaria.

Los permisos específicos por endpoint se establecen en la especificación 12.

## 3. Registro y contraseñas

### 3.1. Email

El registro aplicará las siguientes reglas:

- Eliminar espacios iniciales y finales.
- Normalizar a minúsculas.
- Validar la estructura.
- Limitar la longitud a 254 caracteres.
- Garantizar la unicidad mediante PostgreSQL.

No se eliminarán caracteres internos, puntos ni etiquetas adicionales.

Durante el PB03 no se verificará automáticamente la titularidad del correo electrónico.

### 3.2. Contraseña

| Requisito | Valor |
|---|---|
| Longitud mínima | 12 caracteres |
| Longitud máxima | 72 bytes en UTF-8 |
| Espacios en blanco | No permitidos |
| Caracteres especiales | Permitidos, no obligatorios |

Las contraseñas no se normalizarán, truncarán ni modificarán mediante strip().

La confirmación de contraseña será responsabilidad del cliente.

### 3.3. Hashing

Se utilizará bcrypt con salt aleatorio y factor de coste configurable.

```python
password_hash = bcrypt.hashpw(
    password.encode("utf-8"),
    bcrypt.gensalt(rounds=BCRYPT_ROUNDS),
).decode("utf-8")
```

La verificación utilizará bcrypt.checkpw().

No se utilizará SHA-256 directamente para almacenar contraseñas.

### 3.4. Creación de cuentas

El registro creará una cuenta activa después de validar los datos y confirmar su persistencia.

No generará automáticamente sesiones ni API keys.

La unicidad del email deberá mantenerse incluso ante registros concurrentes y cuentas eliminadas lógicamente.

## 4. Autenticación de usuarios y sesiones

### 4.1. Inicio de sesión

El backend deberá:

1. Normalizar el email y aplicar los límites de autenticación.
2. Recuperar el usuario.
3. Verificar la contraseña mediante bcrypt.
4. Comprobar que la cuenta está activa y no eliminada.
5. Generar una sesión válida.

Un email inexistente y una contraseña incorrecta producirán INVALID_CREDENTIALS.

No se revelará el estado de una cuenta desactivada antes de comprobar correctamente sus credenciales.

Las entradas de login deberán manejar de forma controlada las contraseñas incompatibles con los límites de bcrypt.

### 4.2. Tokens

Se utilizarán tokens opacos generados mediante secrets:

```python
session_token = secrets.token_urlsafe(32)
```

El registro interno de sesión contendrá:

- Hash SHA-256 del token.
- user_id.
- Fecha de creación.
- Fecha de caducidad.

Las sesiones permanecerán en memoria del backend, con acceso protegido frente a concurrencia.

El token original únicamente se devolverá durante el inicio de sesión.

### 4.3. Caducidad

La duración inicial será de ocho horas desde la creación.

Los registros caducados deberán eliminarse mediante una política de limpieza controlada.

Una sesión caducada identificable devolverá SESSION_EXPIRED. Si su registro ya no existe, devolverá INVALID_SESSION.

No se incorporarán JWT, OAuth, refresh tokens ni renovación automática.

### 4.4. Invalidación

| Operación | Sesiones invalidadas |
|---|---|
| Cierre de sesión | Sesión actual |
| Cambio de contraseña | Todas las del usuario |
| Desactivación de cuenta | Todas las del usuario |
| Eliminación de cuenta | Todas las del usuario |
| Reinicio del backend | Todas |

El cambio de contraseña exigirá verificar la contraseña actual, validar la nueva y confirmar su almacenamiento.

La invalidación se coordinará con la emisión y validación concurrente de sesiones.

Cerrar sesión o modificar la contraseña no revocará automáticamente las API keys existentes.

## 5. Generación de API keys

### 5.1. Formato y almacenamiento

Las credenciales se generarán mediante una fuente criptográficamente segura:

```python
api_key = secrets.token_urlsafe(32)

key_hash = hashlib.sha256(
    api_key.encode("utf-8")
).hexdigest()
```

La clave original será independiente de api_key.id.

PostgreSQL almacenará únicamente su hash.

El secreto original se devolverá exclusivamente después de confirmar una emisión autorizada.

No podrá recuperarse posteriormente.

### 5.2. Modalidades de emisión

| Modalidad | Credencial requerida | Roles emitidos | Propietario |
|---|---|---|---|
| Anónima | Ninguna | free | NULL |
| Ordinaria | Sesión válida | free, user | Usuario autenticado |
| Administrativa | API key Admin | free, user | Opcional para Free; obligatorio para User |
| Aprovisionamiento interno | Entorno autorizado | admin | Usuario existente |

Los propietarios de nuevas claves deberán corresponder a usuarios activos y no eliminados.

No se permitirá indicar el propietario mediante la emisión ordinaria.

Las claves anónimas no se reasignarán posteriormente a cuentas registradas.

### 5.3. Autorización del nivel User

La emisión ordinaria de claves User dependerá de USER_TIER_ALLOWED_USER_IDS.

La lista contendrá UUID de cuentas autorizadas mediante un procedimiento administrativo controlado.

No se concederán privilegios basándose únicamente en direcciones de correo electrónico no verificadas.

Una lista vacía impedirá nuevas emisiones ordinarias User.

La emisión administrativa podrá autorizar una clave User concreta sin exigir que su propietario figure en la lista.

Esta emisión no concederá permiso para generar nuevas claves User de forma ordinaria.

Retirar un UUID de la lista impedirá nuevas emisiones ordinarias, pero no revocará automáticamente las credenciales ya emitidas.

### 5.4. Aprovisionamiento Admin

La primera API key administrativa deberá poder aprovisionarse sin depender de otra clave Admin.

Se utilizará API_KEY como secreto de aprovisionamiento, asociado mediante un procedimiento interno a una cuenta administrativa existente y controlada.

El procedimiento deberá:

- Utilizar una credencial de elevada entropía.
- Registrar exclusivamente su hash.
- Asociar el rol Admin en PostgreSQL.
- Ser idempotente.
- Evitar credenciales predeterminadas.
- No reactivar claves desactivadas o eliminadas.
- Detectar discrepancias de configuración sin sobrescribir registros existentes.

API_KEY no constituirá un mecanismo alternativo que permita omitir las comprobaciones de PostgreSQL.

Ningún endpoint permitirá emitir claves Admin.

### 5.5. Límites de claves activas

| Tipo | Límite inicial |
|---|---|
| Free registrada | 1 por usuario |
| User | 5 por usuario |
| Free anónima | Límites temporales de emisión |
| Admin | Aprovisionamiento restringido |

Las claves desactivadas y eliminadas no se contabilizarán como activas.

Los límites se aplicarán tanto a la emisión ordinaria y administrativa como a la reactivación de claves.

La comprobación y modificación se realizarán de forma atómica conforme a la especificación 13.

Los límites temporales de registro, autenticación y emisión se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 6. Autenticación de peticiones

### 6.1. Modalidades

| Modalidad | Identidad resultante |
|---|---|
| X-API-Key | API key y propietario, cuando exista |
| Authorization: Bearer | Usuario autenticado |
| Authorization: Bearer y X-API-Key-Id | API key propia seleccionada mediante sesión |

Las modalidades incompatibles se rechazarán conforme al contrato HTTP.

### 6.2. API key original

El backend calculará el hash del secreto recibido y localizará la credencial en PostgreSQL.

Deberá comprobar:

- Existencia de la clave.
- Estado activo y ausencia de eliminación lógica.
- Estado activo y ausencia de eliminación del propietario, cuando exista.

El rol se obtendrá exclusivamente del registro persistido.

### 6.3. Sesión

El backend localizará la sesión mediante el hash del token, comprobará su vigencia y verificará el estado actual del usuario en PostgreSQL.

Una sesión previamente válida no permitirá eludir una desactivación posterior.

### 6.4. Selección de API key mediante sesión

Además de validar la sesión, deberá comprobarse:

- Existencia de la API key.
- Propiedad de la clave.
- Estado activo y ausencia de eliminación.
- Rol Free o User.

Esta modalidad no estará disponible para claves Admin.

Las dos modalidades de autenticación de una misma API key compartirán permisos, conversaciones y contadores de consumo.

### 6.5. Contexto de autenticación

El contexto interno contendrá, según la modalidad:

- user_id.
- api_key_id.
- role.

No incluirá secretos originales ni hashes.

La autenticación se realizará antes de contabilizar peticiones asociadas a una identidad.

Los fallos de PostgreSQL no se presentarán como credenciales incorrectas.

## 7. Autorización y propiedad

### 7.1. Conversaciones

Para credenciales Free y User deberá cumplirse:

```python
conversation.api_key_id == auth_context.api_key_id
```

Dos claves del mismo usuario no compartirán automáticamente sus conversaciones.

Una clave Admin activa podrá acceder a cualquier conversación sin modificar su propiedad ni eludir sus restricciones operativas.

### 7.2. Historial

| Modalidad | Acceso |
|---|---|
| Free original | Sin acceso al historial persistente |
| User original | Historial de la clave utilizada |
| Sesión válida | Historial de claves propias Free y User no eliminadas |
| Admin original | Historial global |

La lectura mediante sesión podrá incluir claves propias desactivadas.

Las claves eliminadas quedarán excluidas del acceso ordinario.

Al consultar una conversación mediante sesión se comprobará tanto la propiedad de la clave como la pertenencia de la conversación a dicha clave.

### 7.3. Recursos ajenos

Los recursos inexistentes o ajenos devolverán THREAD_NOT_FOUND o API_KEY_NOT_FOUND, según corresponda.

No se revelará su existencia ni su estado operativo.

Conocer un UUID no constituye autorización.

### 7.4. HITL

La resolución de HITL requerirá autorización sobre la conversación y cumplimiento de las condiciones definidas en [06-langgraph.md](06-langgraph.md).

approval_id no sustituye la autenticación ni la autorización.

## 8. Revocación y administración

### 8.1. Estados de credenciales

| Operación | Consecuencia |
|---|---|
| Desactivar API key | Impedir su utilización |
| Reactivar API key | Recuperar su utilización si cumple las restricciones |
| Eliminar API key | Revocación definitiva dentro de las operaciones ordinarias |
| Desactivar usuario | Invalidar sesiones e impedir utilizar sus claves |
| Reactivar usuario | Permitir nuevamente las operaciones autorizadas |
| Eliminar usuario | Invalidar sesiones e inutilizar todas sus claves |

La eliminación será lógica, conforme a la especificación 13.

No se modificarán propietarios, roles, identificadores ni hashes mediante operaciones administrativas de estado.

La reactivación de una clave exigirá que no esté eliminada, que su propietario esté habilitado y que se respeten los límites de claves activas.

Reactivar una cuenta no recuperará sesiones invalidadas ni reactivará claves desactivadas individualmente.

### 8.2. Operaciones en curso

Antes de entregar una respuesta del asistente o persistir un turno se comprobará nuevamente la autorización aplicable, incluyendo la vigencia de la sesión cuando corresponda.

Si la autorización ha dejado de ser válida:

- No se comunicará éxito autorizado.
- No se iniciará una persistencia de mensajes no autorizada.
- Se devolverá el error correspondiente.
- Se protegerá la consistencia del checkpoint.

Las comprobaciones finales y escrituras se coordinarán con las modificaciones administrativas concurrentes conforme a la especificación 13.

La revocación no garantiza la cancelación inmediata de operaciones externas ya iniciadas.

## 9. Implementación en FastAPI

La autenticación y autorización se centralizarán en api/security.py y api/dependencies.py mediante dependencias reutilizables.

| Dependencia propuesta | Responsabilidad |
|---|---|
| get_session | Proporcionar una sesión SQL |
| get_current_user | Autenticar una sesión de usuario |
| get_current_api_key | Autenticar una clave original |
| get_auth_context | Resolver la modalidad de autenticación |
| require_roles | Comprobar permisos |
| require_admin | Exigir una clave administrativa |
| require_thread_access | Comprobar acceso a la conversación |

Se utilizará Depends o Security según corresponda.

OpenAPI representará las modalidades mediante APIKeyHeader y HTTPBearer, permitiendo probar las operaciones protegidas desde Swagger.

El núcleo RAG y la CLI permanecerán independientes de las credenciales HTTP.

## 10. Configuración

| Variable | Valor inicial |
|---|---|
| API_KEY | Secreto de aprovisionamiento |
| SESSION_TTL_SECONDS | 28800 |
| BCRYPT_ROUNDS | 12 |
| FREE_MAX_ACTIVE_KEYS | 1 |
| USER_MAX_ACTIVE_KEYS | 5 |
| USER_TIER_ALLOWED_USER_IDS | Lista vacía |

La lista de usuarios autorizados deberá contener exclusivamente UUID válidos.

BCRYPT_ROUNDS deberá evaluarse mediante pruebas de rendimiento.

.env.example documentará estos parámetros sin incluir secretos ni identificadores personales reales.

No se utilizará USER_TIER_ALLOWED_EMAILS como mecanismo de autorización.

## 11. Protección de credenciales

Las credenciales de ReciclaTÍA serán independientes de GEMINI_API_KEY y DATABASE_URL.

No se almacenarán ni registrarán secretos originales fuera de los mecanismos expresamente autorizados.

Los tokens y API keys originales únicamente se expondrán en las respuestas de autenticación o emisión correspondientes, protegidas mediante Cache-Control: no-store.

Los errores deberán sanitizarse conforme a los contratos HTTP.

El cliente gestionará las credenciales conforme a [07-streamlit.md](07-streamlit.md).

La pérdida del secreto original de una API key no permitirá recuperarlo desde PostgreSQL ni justificará repetir automáticamente una emisión cuyo resultado sea desconocido.

## 12. Limitaciones

El acceso anónimo no permite identificar permanentemente a una persona.

Los límites de emisión y consumo constituyen medidas de mitigación, no garantías absolutas contra la obtención de múltiples credenciales.

No se implementarán pagos, suscripciones, facturación, verificación automatizada de correo ni identificación invasiva de dispositivos.

La eliminación lógica no constituye una supresión física definitiva de datos personales.

## 13. Criterios de aceptación

- Los usuarios y las API keys se autentican mediante mecanismos seguros.
- Los secretos originales no se almacenan en PostgreSQL.
- Los roles y la propiedad se verifican en cada operación protegida.
- El registro no concede privilegios adicionales.
- La emisión y reactivación respetan los límites establecidos.
- El aprovisionamiento administrativo es idempotente.
- Las sesiones caducadas o invalidadas no autorizan operaciones.
- Las credenciales revocadas no permiten nuevas ejecuciones.
- Los consumidores no acceden a conversaciones ajenas.
- Las claves Admin requieren siempre su secreto original.
- Los errores respetan los contratos HTTP.
- El núcleo conserva su independencia del backend.

La estrategia de validación se establece en [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).