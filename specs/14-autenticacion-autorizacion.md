# 14. Autenticación y autorización

## 1. Objetivo

Definir los mecanismos de identificación, autenticación, autorización y gestión de credenciales de ReciclaTÍA.

El sistema debe permitir el acceso anónimo a las funcionalidades gratuitas, el registro de usuarios, la generación controlada de API keys y la administración restringida de los recursos del producto.

La seguridad será responsabilidad del backend y no dependerá de las restricciones visuales de Streamlit.

## 2. Principios de seguridad

- Separación entre identidad, autenticación y autorización.
- Principio de mínimo privilegio.
- Validación de credenciales en cada petición protegida.
- Denegación por defecto.
- Control de acceso basado en roles.
- Control de acceso basado en la propiedad del recurso.
- Almacenamiento de secretos mediante hashes.
- Imposibilidad de elevar privilegios mediante parámetros proporcionados por el cliente.
- Independencia entre registro de usuarios y nivel de acceso al producto.
- Protección de los recursos frente a accesos no autorizados.

## 3. Roles

Los roles de las API keys se representan mediante el enumerado ApiKeyRole, definido en src/enums.py.

```python
from enum import Enum


class ApiKeyRole(str, Enum):
    FREE = "free"
    USER = "user"
    ADMIN = "admin"
```

El mismo enumerado se utilizará en SQLModel, Pydantic y la capa de autorización.

PostgreSQL utilizará el tipo enumerado nativo api_key_role.

### 3.1. Free

Representa el nivel gratuito del producto.

Características:

- No requiere registro obligatorio.
- Puede estar asociado a un usuario registrado.
- Permite realizar consultas de texto.
- Permite crear y continuar conversaciones propias.
- Permite aprobar o rechazar planes mediante HITL.
- No permite realizar consultas multimodales.
- Está sujeto a las cuotas del nivel gratuito.

Una API key Free anónima tendrá api_key.user_id=NULL.

Una API key Free registrada tendrá api_key.user_id asociado a un usuario existente.

### 3.2. User

Representa el nivel avanzado del producto, destinado a convertirse en la futura modalidad de pago.

Características:

- Requiere registro obligatorio.
- Requiere autorización para acceder a este nivel.
- Permite consultas de texto.
- Permite consultas con imágenes.
- Permite consultar el historial asociado a la API key utilizada.
- Permite resolver aprobaciones pendientes.
- Dispone de cuotas superiores al nivel Free.

El registro de un usuario no implica automáticamente la asignación del rol User.

Durante esta fase de desarrollo no se implementará una pasarela de pago.

### 3.3. Admin

Representa el nivel administrativo del producto.

Características:

- Requiere una cuenta asociada.
- Requiere un procedimiento restringido de emisión.
- Permite acceder a todas las conversaciones.
- Permite administrar usuarios y API keys.
- No está sujeto a las cuotas comerciales del asistente.
- Está sujeto a los límites técnicos de seguridad y concurrencia.

Ningún endpoint público ni endpoint ordinario de cuenta podrá generar una API key Admin.

La pertenencia de una clave administrativa a una cuenta no convierte automáticamente a todas las demás claves de dicha cuenta en administrativas.

## 4. Perfiles funcionales

| Funcionalidad | Free anónimo | Free registrado | User | Admin |
|---|---|---|---|---|
| Registro obligatorio | No | Sí | Sí | Sí |
| Consultas de texto | Sí | Sí | Sí | Sí |
| Consultas con imágenes | No | No | Sí | Sí |
| HITL | Sí | Sí | Sí | Sí |
| Historial persistente propio | No | Sí | Sí | Sí |
| Historial de otras claves | No | No | No | Sí |
| Gestión de claves propias mediante sesión | No | Sí | Sí | Sí |
| Gestión de usuarios | No | No | No | Sí |
| Gestión global de API keys | No | No | No | Sí |

El usuario Free registrado podrá consultar el historial de su clave mediante una sesión autenticada.

La API key Free por sí sola no autoriza el acceso a los endpoints generales de historial.

## 5. Registro de usuarios

### 5.1. Endpoint

POST /auth/register

### 5.2. Datos de entrada

| Campo | Tipo | Obligatorio |
|---|---|---|
| email | str | Sí |
| password | str | Sí |

### 5.3. Validación del email

- Eliminar espacios iniciales y finales.
- Normalizar a minúsculas según la política del producto.
- Validar su estructura.
- Respetar una longitud máxima de 254 caracteres.
- Comprobar su unicidad en PostgreSQL.

No se eliminarán caracteres internos, puntos ni etiquetas adicionales del email.

El backend no modificará la dirección de manera que pueda confundirse con la de otro usuario.

### 5.4. Validación de la contraseña

La política inicial propuesta establece:

- Longitud mínima de 12 caracteres.
- Longitud máxima de 72 bytes en UTF-8, debido al límite de entrada de bcrypt.
- No se permiten espacios ni otros caracteres de espacio en blanco (tabulaciones y saltos de línea).
- Se permiten caracteres especiales.
- No se exige obligatoriamente un carácter especial.
- No se truncarán contraseñas.
- No se modificarán ni normalizarán las contraseñas introducidas.

La confirmación de contraseña será responsabilidad de la interfaz de registro.

El backend validará siempre la contraseña recibida, independientemente de las comprobaciones del cliente.

### 5.5. Creación del usuario

Cuando el registro sea válido:

- Se genera user.id.
- Se almacena user.email normalizado.
- Se almacena user.password_hash.
- Se establece user.created_at.
- Se establece user.is_active=True.
- Se establece user.deleted_at=NULL.

La respuesta será HTTP 201.

El registro no permitirá solicitar un rol administrativo ni asignar directamente permisos de pago.

### 5.6. Errores

| HTTP | Código | Situación |
|---|---|---|
| 422 | INVALID_EMAIL | Formato de email inválido |
| 422 | INVALID_PASSWORD | Contraseña que incumple los requisitos |
| 409 | EMAIL_ALREADY_EXISTS | Email registrado previamente |
| 429 | RATE_LIMIT_EXCEEDED | Límite de intentos alcanzado |
| 503 | SERVICE_UNAVAILABLE | PostgreSQL no disponible |

La restricción UNIQUE de PostgreSQL garantizará la unicidad incluso ante registros concurrentes.

## 6. Hashing de contraseñas

Se utilizará bcrypt para almacenar y verificar contraseñas.

bcrypt incorpora un salt aleatorio y un factor de coste configurable que dificulta los ataques de fuerza bruta.

El factor de coste se seleccionará mediante pruebas de rendimiento. Se propone inicialmente un valor de 12.

### 6.1. Registro

1. Validar la contraseña.
2. Convertirla a bytes mediante UTF-8.
3. Generar un salt.
4. Calcular el hash mediante bcrypt.
5. Almacenar el hash resultante en user.password_hash.

### 6.2. Autenticación

1. Recuperar el usuario mediante su email.
2. Obtener user.password_hash.
3. Verificar la contraseña recibida mediante bcrypt.checkpw().
4. Comprobar el estado del usuario.
5. Generar una sesión si las credenciales son válidas.

No se compararán hashes generados independientemente, ya que bcrypt utiliza salts aleatorios.

### 6.3. Restricciones

- Las contraseñas no se almacenan en texto plano.
- Las contraseñas no se registran en los logs.
- Los hashes no se exponen en respuestas HTTP.
- Los errores de autenticación no revelarán si un email concreto existe.
- La verificación de credenciales estará protegida mediante límites de intentos.

## 7. Inicio de sesión

### 7.1. Endpoint

POST /auth/login

### 7.2. Proceso

1. Validar los datos de entrada.
2. Normalizar el email.
3. Aplicar los límites de intentos de autenticación.
4. Buscar el usuario.
5. Verificar la contraseña.
6. Comprobar user.is_active.
7. Comprobar user.deleted_at.
8. Generar un token de sesión.
9. Devolver LoginOut.

### 7.3. Errores

| HTTP | Código | Situación |
|---|---|---|
| 401 | INVALID_CREDENTIALS | Email o contraseña incorrectos |
| 403 | USER_INACTIVE | Credenciales correctas de un usuario desactivado |
| 429 | RATE_LIMIT_EXCEEDED | Demasiados intentos |
| 503 | SERVICE_UNAVAILABLE | Dependencia necesaria no disponible |

Las cuentas eliminadas lógicamente no podrán iniciar sesión.

## 8. Gestión de sesiones

### 8.1. Tipo de sesión

Se utilizarán tokens opacos generados mediante mecanismos criptográficamente seguros.

No se implementarán JWT ni OAuth durante esta fase del desarrollo.

### 8.2. Generación

Los tokens se generarán mediante el módulo secrets de Python, utilizando al menos 32 bytes aleatorios.

La sesión estará asociada a:

- Hash del token.
- Identificador del usuario.
- Fecha de creación.
- Fecha de caducidad.

El token original se devuelve exclusivamente al cliente durante el inicio de sesión.

### 8.3. Almacenamiento

Las sesiones se mantendrán en memoria del backend.

No se incorporará una tabla session al modelo relacional inicial.

El almacenamiento de sesiones estará protegido frente a accesos concurrentes.

Los tokens caducados deberán eliminarse periódicamente para evitar un crecimiento indefinido de la memoria.

### 8.4. Caducidad

Se propone una duración inicial de 8 horas desde la creación de la sesión.

La duración será configurable mediante una variable de entorno.

No se implementarán refresh tokens ni renovación automática durante esta fase de desarrollo.

Una sesión caducada obliga al usuario a autenticarse nuevamente.

### 8.5. Transporte

El cliente enviará el token mediante:

```http
Authorization: Bearer <session_token>
```

Los tokens no se transmitirán mediante parámetros de URL.

### 8.6. Invalidación

Una sesión quedará invalidada cuando:

- El usuario cierre sesión.
- Se alcance su fecha de caducidad.
- El usuario modifique su contraseña.
- El administrador desactive al usuario.
- El administrador elimine lógicamente al usuario.
- El proceso del backend se reinicie.

La modificación de contraseña invalidará todas las sesiones existentes del usuario.

### 8.7. Reinicio del servicio

Después de un reinicio o redeploy, el usuario deberá autenticarse nuevamente.

Las cuentas, API keys y conversaciones permanecerán almacenadas en PostgreSQL.

La pérdida de una sesión no implica la pérdida de los datos del usuario.

## 9. Generación de API keys

### 9.1. Formato

Las API keys serán credenciales opacas generadas mediante el módulo secrets.

Ejemplo conceptual de generación:

```python
import secrets

api_key = secrets.token_urlsafe(32)
```

La API key original es independiente de api_key.id.

No se utilizarán UUID como único secreto de autenticación.

El rol se obtendrá del registro asociado en PostgreSQL y no de la apariencia de la clave.

### 9.2. API key Free anónima

Endpoint:

POST /api-keys/free

No requiere registro ni sesión.

El backend genera:

- api_key.id.
- api_key.key_hash.
- api_key.role=ApiKeyRole.FREE.
- api_key.user_id=NULL.
- api_key.is_active=True.
- api_key.created_at.
- api_key.last_used_at=NULL.
- api_key.deleted_at=NULL.

La interfaz Streamlit solicitará automáticamente una clave cuando un consumidor anónimo acceda por primera vez al asistente.

La respuesta será HTTP 201.

### 9.3. API key Free registrada

Endpoint:

POST /api-keys

Requiere una sesión de usuario válida.

El backend comprueba la identidad del usuario y genera una clave Free vinculada a su cuenta.

- api_key.role=ApiKeyRole.FREE.
- api_key.user_id=user.id.

El usuario puede utilizar las funcionalidades gratuitas sin contratar el futuro nivel de pago.

### 9.4. API key User

Endpoint:

POST /api-keys

Requiere:

- Sesión válida.
- Usuario activo.
- Autorización para acceder al nivel User.
- Cumplimiento de los límites de emisión de claves.

El cliente podrá solicitar el rol User, pero el backend determinará si está autorizado.

Durante esta fase del desarrollo se utilizará una lista de usuarios autorizados mediante configuración del backend, además de la emisión administrativa.

Esta solución evita introducir una tabla de suscripciones antes de implementar el modelo comercial.

La autorización del nivel User no implica que una API key Free previamente emitida cambie automáticamente de rol.

### 9.5. API key Admin

Las API keys administrativas se emitirán mediante un procedimiento interno de aprovisionamiento.

La primera clave administrativa deberá poder configurarse mediante un proceso controlado que no dependa de la existencia de otra API key Admin.

Este procedimiento deberá:

- Asociar la clave a una cuenta administrativa controlada.
- Obtener los secretos desde un entorno seguro.
- Registrar únicamente el hash de la clave.
- Evitar contraseñas y credenciales predeterminadas.
- Evitar la exposición de secretos en los logs.
- Impedir la duplicación de credenciales durante reinicios.

La variable API_KEY requerida por el proyecto podrá utilizarse para aprovisionar una credencial administrativa de demostración, siempre que se vincule correctamente al modelo persistente.

No se aceptará como mecanismo universal para omitir las comprobaciones de PostgreSQL.

Ningún endpoint de registro o gestión ordinaria de cuenta permitirá generar una clave Admin.

La emisión de nuevas claves Admin se realizará exclusivamente mediante el procedimiento interno restringido.

### 9.6. Emisión administrativa

Endpoint:

POST /admin/api-keys

Requiere una API key Admin activa.

Permite generar claves Free o User según las reglas de asociación y autorización correspondientes.

No permite asignar el rol Admin mediante este endpoint.

## 10. Hashing de API keys

A diferencia de las contraseñas elegidas por usuarios, las API keys se generan mediante una fuente criptográficamente segura y poseen una elevada entropía.

Se utilizará SHA-256 para calcular un hash determinista de cada API key.

```python
import hashlib

key_hash = hashlib.sha256(
    api_key.encode("utf-8")
).hexdigest()
```

### 10.1. Justificación

- Permite localizar directamente la clave mediante su hash.
- Evita almacenar el secreto original.
- Permite utilizar un índice UNIQUE.
- Evita recorrer todos los registros para autenticar una petición.
- Reduce el coste computacional de la autenticación frente a bcrypt.

SHA-256 no se utilizará para almacenar contraseñas.

### 10.2. Almacenamiento

El hash se almacenará en api_key.key_hash.

La API key original únicamente se devolverá durante su generación.

Si el usuario pierde una clave, no será posible recuperar su valor original desde PostgreSQL.

El usuario podrá utilizar su cuenta y seleccionar la clave mediante su identificador cuando la operación admita autenticación por sesión.

### 10.3. Restricciones

- No almacenar claves originales en PostgreSQL.
- No devolver key_hash en respuestas HTTP.
- No registrar claves originales en los logs.
- No incluir claves en URLs.
- No incorporar claves al repositorio.
- No utilizar claves elegidas manualmente por usuarios.

## 11. Control de emisión de API keys

La generación ilimitada de claves permitiría eludir las cuotas del asistente.

Se propone establecer las siguientes restricciones iniciales:

| Tipo de clave | Límite |
|---|---|
| Free registrada | Una clave activa por usuario |
| User | Hasta cinco claves activas por usuario |
| Admin | Emisión interna restringida |
| Free anónima | Límites de emisión independientes |

Las claves desactivadas no se contabilizarán como claves activas, pero la emisión de sustituciones también estará limitada para evitar el reinicio deliberado de cuotas.

La comprobación y la creación de una nueva clave deberán protegerse frente a peticiones concurrentes.

### 11.1. Consumidores anónimos

Streamlit conservará la clave Free durante la sesión del usuario.

No se generará una nueva clave para cada mensaje ni para cada rerun de Streamlit.

La emisión anónima estará protegida mediante rate limiting.

La dirección IP podrá utilizarse como señal complementaria de seguridad cuando pueda obtenerse de una fuente fiable.

No se confiará automáticamente en cabeceras de IP proporcionadas por el cliente.

### 11.2. Limitaciones

El uso de sesiones anónimas no permite identificar inequívocamente a una persona.

Un consumidor puede intentar obtener nuevas claves mediante sesiones distintas.

Durante esta fase del desarrollo se aplicarán mecanismos razonables de mitigación, sin pretender garantizar una identificación anónima permanente.

Los límites temporales de emisión y sustitución de API keys, así como los mecanismos de control de consumo, se definen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 12. Autenticación mediante API key

### 12.1. Cabecera HTTP

```http
X-API-Key: <api_key>
```

### 12.2. Proceso

1. Obtener la API key de la cabecera.
2. Comprobar que está presente.
3. Calcular su hash.
4. Buscar api_key.key_hash en PostgreSQL.
5. Comprobar api_key.is_active.
6. Comprobar api_key.deleted_at.
7. Si existe api_key.user_id, recuperar el usuario.
8. Comprobar user.is_active y user.deleted_at.
9. Obtener el rol de la clave.
10. Construir el contexto de autenticación.

La autenticación no dependerá de datos proporcionados por el cliente sobre su identidad o sus permisos.

### 12.3. Contexto de autenticación

El backend dispondrá de un objeto interno con:

- api_key_id.
- user_id, cuando corresponda.
- role.

Este contexto se utilizará durante las comprobaciones de autorización, consumo y propiedad de los recursos.

No contendrá la API key original ni su hash.

## 13. Autenticación mediante sesión

Las operaciones relacionadas con cuentas requieren un token de sesión válido.

### 13.1. Proceso

1. Obtener el token de la cabecera Authorization.
2. Calcular su hash.
3. Localizar la sesión.
4. Comprobar su caducidad.
5. Recuperar el usuario desde PostgreSQL.
6. Comprobar user.is_active.
7. Comprobar user.deleted_at.
8. Construir el contexto de identidad.

El estado actual del usuario se verificará en cada operación protegida.

Una sesión previamente válida no podrá utilizarse para eludir la desactivación de una cuenta.

### 13.2. Operaciones autorizadas

- Consultar la cuenta propia.
- Modificar la contraseña.
- Cerrar sesión.
- Solicitar API keys autorizadas.
- Listar las API keys propias.
- Consultar el historial correspondiente a una clave propia.

La sesión no concede automáticamente permisos administrativos.

## 14. Selección de API keys desde Streamlit

Un usuario registrado puede disponer de varias API keys.

El cliente debe identificar explícitamente qué clave desea utilizar.

El identificador seleccionado será api_key.id.

Como las claves originales no pueden recuperarse desde PostgreSQL, se propone admitir una modalidad de autenticación mediante sesión y selección de API key.

```http
Authorization: Bearer <session_token>
X-API-Key-Id: <api_key_id>
```

### 14.1. Validaciones

El backend debe comprobar:

- Que la sesión sea válida.
- Que la API key exista.
- Que api_key.user_id coincida con el usuario autenticado.
- Que la clave esté activa.
- Que la clave no esté eliminada.
- Que el rol permita la operación solicitada.

Esta modalidad podrá utilizarse con claves Free registradas y User.

No permitirá utilizar claves Admin mediante una sesión ordinaria.

### 14.2. Clientes externos

Swagger y otros clientes podrán continuar utilizando la credencial original mediante X-API-Key.

Las dos modalidades de autenticación deberán producir un contexto interno equivalente para las operaciones autorizadas del asistente.

No se aceptarán peticiones que mezclen ambas modalidades de manera ambigua.

### 14.3. Cambio de clave

Cuando el usuario seleccione otra API key:

- Se actualizará la clave seleccionada en Streamlit.
- Se descartará la conversación activa de la interfaz.
- Se consultarán las conversaciones correspondientes a la nueva clave.
- No se modificarán los datos almacenados de las claves anteriores.

El cambio de API key no permite acceder al historial de la clave anterior mediante la nueva credencial.

## 15. Autorización basada en roles

La autorización se realizará después de autenticar la credencial.

Los roles admitidos se definirán explícitamente para cada endpoint.

| Endpoint | Free | User | Admin |
|---|---|---|---|
| POST /ask | Sí | Sí | Sí |
| POST /ask/image | No | Sí | Sí |
| POST /approve | Sí | Sí | Sí |
| GET /threads | No | Sí | Sí |
| GET /threads/{thread_id} | No | Sí | Sí |
| GET /threads/{thread_id}/messages | No | Sí | Sí |
| /admin/* | No | No | Sí |

Los endpoints de cuenta utilizarán autenticación mediante sesión.

No se deducirán permisos administrativos a partir de la existencia de una cuenta registrada.

Ocultar botones en Streamlit constituye una medida de interfaz, no un mecanismo de seguridad.

## 16. Autorización basada en la propiedad

La autorización basada en roles no es suficiente para proteger las conversaciones.

También deberá comprobarse la propiedad del recurso solicitado.

### 16.1. API key Free y User

La operación estará autorizada cuando:

```text
conversation.api_key_id == api_key.id
```

La coincidencia entre los usuarios propietarios de dos API keys diferentes no concede acceso cruzado a sus conversaciones.

### 16.2. API key Admin

Una API key Admin activa puede acceder a cualquier conversación.

La operación no estará restringida por conversation.api_key_id.

### 16.3. Acceso mediante sesión

Cuando se consulte el historial de una clave utilizando una sesión:

```text
api_key.user_id == user.id
```

También deberá comprobarse:

```text
conversation.api_key_id == api_key.id
```

Estas dos comprobaciones garantizan que el usuario posee la clave seleccionada y que la conversación pertenece a esa clave.

### 16.4. Recursos ajenos

Cuando un consumidor intente acceder a una conversación que no le pertenece, se devolverá HTTP 404 THREAD_NOT_FOUND.

No se revelará si el identificador corresponde a una conversación existente de otro consumidor.

## 17. Acceso al historial

### 17.1. Free anónimo

Puede continuar su conversación utilizando su API key y thread_id.

No dispone de acceso a los endpoints de consulta del historial persistente.

La interfaz conserva los mensajes de la conversación activa durante la sesión.

### 17.2. Free registrado

Puede consultar el historial de sus claves mediante los endpoints autenticados por sesión.

No obtiene acceso a consultas multimodales ni a cuotas superiores por el hecho de registrarse.

### 17.3. User

Puede consultar el historial de la API key utilizada.

También puede consultar el historial de otras claves propias seleccionándolas explícitamente mediante una sesión válida.

### 17.4. Admin

Puede consultar cualquier conversación mediante una API key administrativa activa.

### 17.5. API keys desactivadas

Una clave desactivada no permite autenticarse ni realizar nuevas consultas.

Su propietario puede consultar el historial mediante una sesión válida.

### 17.6. API keys eliminadas

El acceso ordinario al historial de las claves eliminadas lógicamente queda reservado al administrador.

La política deberá respetar los procedimientos de acceso y supresión de datos personales aplicables.

Las reglas de conservación de registros e integridad referencial se definen en [13-persistencia.md](13-persistencia.md).

## 18. Gestión de credenciales y estados

### 18.1. Desactivación de API key

- api_key.is_active=False.
- api_key.deleted_at=NULL.

La desactivación impide realizar nuevas operaciones mediante la clave.

Puede revertirse mediante una operación administrativa autorizada.

### 18.2. Eliminación de API key

- api_key.is_active=False.
- api_key.deleted_at=fecha de eliminación.

Una clave eliminada lógicamente no podrá reactivarse mediante operaciones ordinarias.

### 18.3. Desactivación de usuario

- user.is_active=False.
- user.deleted_at=NULL.

Todas las API keys asociadas al usuario dejan de autorizar operaciones.

Se invalidan sus sesiones activas.

No es necesario modificar individualmente api_key.is_active, ya que la autenticación comprueba también el estado del propietario.

### 18.4. Eliminación de usuario

- user.is_active=False.
- user.deleted_at=fecha de eliminación.

Todas las API keys asociadas quedan inutilizables.

Se invalidan todas las sesiones del usuario.

La eliminación será lógica y conservará la integridad referencial de los registros.

### 18.5. Operaciones en curso

La desactivación impedirá admitir nuevas operaciones.

Antes de entregar resultados o persistir turnos, el backend volverá a comprobar las condiciones de autorización cuando corresponda.

La revocación de una credencial no garantiza la cancelación inmediata de una ejecución que ya esté utilizando un servicio externo.

## 19. Dependencias de FastAPI

La autenticación y la autorización se implementarán mediante dependencias reutilizables de FastAPI.

Se propone la siguiente separación de responsabilidades:

| Dependencia | Responsabilidad |
|---|---|
| get_session | Proporcionar una sesión de PostgreSQL |
| get_current_user | Identificar al usuario autenticado |
| get_current_api_key | Autenticar una API key |
| get_auth_context | Resolver la modalidad de autenticación |
| require_roles | Comprobar los roles permitidos |
| require_admin | Exigir credenciales administrativas |
| require_thread_access | Comprobar la propiedad de la conversación |

Los nombres son orientativos y podrán ajustarse durante la implementación.

No se duplicará la lógica de autenticación en cada endpoint.

La documentación OpenAPI deberá representar las modalidades de autenticación admitidas.

## 20. Errores de seguridad

Los errores derivados de la autenticación, la autorización, la validación de credenciales y los límites de emisión respetarán el catálogo de errores y los códigos HTTP definidos en [12-contratos-http.md](12-contratos-http.md).

Todas las respuestas de error utilizarán el contrato ErrorOut.

Los errores no expondrán información sensible ni permitirán identificar recursos para los que el consumidor no dispone de autorización.

## 21. Variables de entorno

| Variable | Responsabilidad |
|---|---|
| API_KEY | Credencial administrativa de aprovisionamiento, cuando proceda |
| SESSION_TTL_SECONDS | Duración de las sesiones |
| BCRYPT_ROUNDS | Factor de coste de bcrypt |
| FREE_MAX_ACTIVE_KEYS | Límite de claves Free registradas activas |
| USER_MAX_ACTIVE_KEYS | Límite de claves User activas |
| USER_TIER_ALLOWED_EMAILS | Usuarios autorizados para acceder al nivel User durante PB03 |

Los valores secretos se obtendrán exclusivamente del entorno seguro de ejecución.

La lista de autorización temporal no constituirá un sistema de suscripciones.

Las variables deberán documentarse en .env.example sin incluir credenciales reales.

## 22. Protección de secretos

No se expondrán mediante respuestas HTTP ni logs:

- Contraseñas originales.
- Hashes de contraseñas.
- API keys originales, excepto en la respuesta correspondiente a su emisión.
- Hashes de API keys.
- Tokens de sesión, excepto en la respuesta correspondiente al inicio de sesión.
- Hashes de tokens de sesión.
- Cadenas de conexión.
- Credenciales de Gemini.
- Secretos administrativos.

Las excepciones relativas a la devolución de API keys y tokens de sesión se aplican exclusivamente a las respuestas HTTP autorizadas, nunca a los logs.

Las comunicaciones en producción utilizarán HTTPS.

Streamlit no almacenará credenciales en archivos de texto ni parámetros de URL.

Las restricciones específicas de logging se definen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 23. Criterios de aceptación

- Un consumidor puede utilizar el nivel Free sin registrarse.
- Un usuario registrado puede utilizar el nivel Free.
- El registro no concede automáticamente acceso al nivel User.
- Una API key User requiere un propietario registrado.
- Una API key Admin requiere aprovisionamiento restringido.
- No se pueden generar claves Admin mediante endpoints públicos.
- Los roles utilizan el enumerado ApiKeyRole.
- Las contraseñas se almacenan mediante bcrypt.
- Las API keys se almacenan mediante hashes deterministas.
- Los secretos originales no pueden recuperarse desde PostgreSQL.
- Las sesiones tienen una duración limitada.
- Las sesiones caducadas no autorizan operaciones.
- El usuario puede seleccionar explícitamente una API key propia.
- Dos claves del mismo usuario no comparten conversaciones.
- Una clave Free no puede realizar consultas multimodales.
- Una clave Free registrada puede consultar su historial mediante sesión.
- Una clave User no puede ejecutar operaciones administrativas.
- Una clave Admin puede consultar cualquier conversación.
- Una clave desactivada no permite realizar nuevas consultas.
- El historial de una clave desactivada permanece disponible para su propietario.
- Un usuario desactivado no puede utilizar ninguna de sus claves.
- Los límites de emisión impiden generar claves de manera ilimitada.
- Las peticiones directas a la API respetan las mismas restricciones que Streamlit.
- Los secretos no aparecen en los logs.
- La pérdida de una sesión tras un redeploy no elimina las cuentas, claves ni conversaciones.
- Las modalidades de autenticación incompatibles se rechazan.
- Una sesión ordinaria no permite utilizar una API key Admin.
- La modificación de contraseña invalida todas las sesiones existentes del usuario.
- Las claves eliminadas lógicamente no pueden reactivarse mediante operaciones administrativas ordinarias.
- El aprovisionamiento administrativo es idempotente.
- Las API keys originales únicamente se devuelven durante su emisión.
- Los tokens de sesión originales únicamente se devuelven durante el inicio de sesión.