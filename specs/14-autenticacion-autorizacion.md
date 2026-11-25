# 14. Autenticación y autorización

## 1. Objetivo

Definir los mecanismos de identificación, autenticación, autorización y gestión de credenciales de ReciclaTÍA.

El sistema deberá permitir:

- El acceso anónimo a las funcionalidades gratuitas.
- El registro de usuarios.
- La autenticación de cuentas.
- La generación controlada de API keys.
- La selección de credenciales propias.
- El aislamiento de conversaciones.
- El acceso autorizado al historial.
- La administración restringida de usuarios y credenciales.
- El control de permisos según el rol de cada API key.

La autenticación mediante API key constituye un requisito académico del Project Break 03.

Las cuentas, sesiones y diferentes niveles de acceso constituyen ampliaciones funcionales de ReciclaTÍA.

La seguridad será responsabilidad del backend y no dependerá de las restricciones visuales de Streamlit.

## 2. Principios de seguridad

- Separación entre identidad, autenticación y autorización.
- Principio de mínimo privilegio.
- Denegación por defecto.
- Validación de credenciales en cada petición protegida.
- Control de acceso basado en roles.
- Control de acceso basado en la propiedad de los recursos.
- Almacenamiento de secretos mediante hashes.
- Independencia entre registro de usuarios y nivel de acceso.
- Imposibilidad de elevar privilegios mediante parámetros del cliente.
- Protección frente a operaciones concurrentes.
- Limitación de intentos de autenticación y emisión.
- Separación entre credenciales del producto y credenciales de proveedores externos.
- Comunicación de errores mediante códigos HTTP adecuados.

Las decisiones de autenticación y autorización serán deterministas y estarán implementadas en Python.

Gemini y LangGraph no determinarán los permisos de los consumidores.

## 3. Roles

Los roles de las API keys se representarán mediante el enumerado ApiKeyRole, definido en src/enums.py.

```python
from enum import Enum


class ApiKeyRole(str, Enum):
    FREE = "free"
    USER = "user"
    ADMIN = "admin"
```

El mismo enumerado se utilizará en:

- SQLModel.
- Pydantic.
- Autenticación.
- Autorización.
- Control de cuotas.

PostgreSQL utilizará el tipo enumerado nativo api_key_role.

Los valores almacenados corresponderán a free, user y admin.

El rol pertenece a la API key, no al usuario.

Una cuenta podrá poseer credenciales con diferentes roles sin que sus permisos se mezclen.

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

El registro de una cuenta no modificará automáticamente las claves Free anónimas utilizadas previamente.

### 3.2. User

Representa el nivel avanzado del producto, destinado a convertirse en una futura modalidad de pago.

Características:

- Requiere registro obligatorio.
- Requiere autorización para acceder a este nivel.
- Permite consultas de texto.
- Permite consultas con imágenes.
- Permite consultar el historial asociado a la API key utilizada.
- Permite resolver aprobaciones pendientes.
- Dispone de cuotas comerciales superiores a las del nivel Free.

El registro de un usuario no implica automáticamente la asignación del rol User.

Durante esta fase no se implementarán:

- Pasarelas de pago.
- Suscripciones comerciales.
- Facturación.
- Renovaciones automáticas.
- Verificación automatizada de correo electrónico.

La autorización del nivel User se resolverá mediante configuración controlada del backend o emisión administrativa.

### 3.3. Admin

Representa el nivel administrativo del producto.

Características:

- Requiere una cuenta asociada.
- Requiere un procedimiento restringido de emisión.
- Permite acceder a todas las conversaciones.
- Permite administrar usuarios.
- Permite administrar API keys.
- No está sujeto a cuotas comerciales del asistente.
- Está sujeto a los límites técnicos de seguridad, concurrencia y ejecución.

Ningún endpoint público, ordinario de cuenta o administrativo de emisión permitirá generar una API key Admin.

La pertenencia de una clave administrativa a una cuenta no convierte automáticamente a todas las demás claves de dicha cuenta en administrativas.

La utilización de una API key Admin requerirá siempre su credencial original.

## 4. Perfiles funcionales

| Funcionalidad | Free anónimo | Free registrado | User | Admin |
|---|---|---|---|---|
| Registro obligatorio | No | Sí | Sí | Sí |
| Consultas de texto | Sí | Sí | Sí | Sí |
| Consultas con imágenes | No | No | Sí | Sí |
| HITL | Sí | Sí | Sí | Sí |
| Historial persistente autorizado | No | Sí | Sí | Sí |
| Historial de claves ajenas | No | No | No | Sí |
| Gestión de cuenta mediante sesión | No | Sí | Sí | Sí |
| Gestión global de usuarios | No | No | No | Sí |
| Gestión global de API keys | No | No | No | Sí |
| Cuotas comerciales | Free | Free | User | Sin límite comercial |
| Límites técnicos | Sí | Sí | Sí | Sí |

El usuario Free registrado podrá consultar el historial de sus claves Free mediante una sesión autenticada.

La API key Free por sí sola no autorizará el acceso a los endpoints generales de historial.

Un usuario registrado podrá consultar el historial de diferentes claves propias seleccionándolas explícitamente mediante los endpoints autorizados de cuenta.

Esta posibilidad no permite utilizar una API key para acceder directamente a conversaciones pertenecientes a otra.

## 5. Registro de usuarios

### 5.1. Endpoint

POST /auth/register

Endpoint público sujeto a los límites de seguridad establecidos en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

### 5.2. Datos de entrada

Se utilizará el contrato RegisterIn.

| Campo | Tipo | Obligatorio |
|---|---|---|
| email | str | Sí |
| password | str | Sí |

No se aceptarán roles, permisos, identificadores de usuario ni estados administrativos proporcionados mediante este contrato.

### 5.3. Validación del email

- Eliminar espacios iniciales y finales.
- Normalizar a minúsculas según la política del producto.
- Validar su estructura.
- Respetar una longitud máxima de 254 caracteres.
- Comprobar su unicidad en PostgreSQL.

No se eliminarán caracteres internos, puntos ni etiquetas adicionales del email.

El backend no modificará la dirección de manera que pueda confundirse con la de otro usuario.

Durante el PB03 se validará el formato de la dirección, pero no se verificará automáticamente que el consumidor controle el buzón correspondiente.

Por este motivo, el registro de una dirección de correo electrónico no constituirá una prueba suficiente para conceder privilegios adicionales.

### 5.4. Validación de la contraseña

La política inicial establece:

- Longitud mínima de 12 caracteres.
- Longitud máxima de 72 bytes en UTF-8, debido al límite de entrada de bcrypt.
- No se permiten espacios ni otros caracteres de espacio en blanco.
- Se permiten caracteres especiales.
- No se exige obligatoriamente un carácter especial.
- No se truncarán contraseñas.
- No se eliminarán espacios mediante strip().
- No se modificarán ni normalizarán las contraseñas introducidas.

La confirmación de contraseña será responsabilidad de la interfaz de registro.

El backend validará siempre la contraseña recibida, independientemente de las comprobaciones realizadas por el cliente.

### 5.5. Creación del usuario

Cuando el registro sea válido:

1. Aplicar los límites de seguridad correspondientes.
2. Normalizar y validar el email.
3. Validar la contraseña.
4. Comprobar la disponibilidad del email.
5. Generar user.id.
6. Calcular user.password_hash.
7. Establecer user.created_at.
8. Establecer user.is_active=True.
9. Establecer user.deleted_at=NULL.
10. Persistir el usuario mediante una transacción SQL.
11. Devolver UserOut.

La respuesta será HTTP 201 únicamente después de confirmar la creación del usuario en PostgreSQL.

El registro no concederá automáticamente:

- Permisos administrativos.
- Acceso al nivel User.
- Una API key.
- Un token de sesión.

La autenticación posterior se realizará mediante POST /auth/login.

### 5.6. Errores

| HTTP | Código | Situación |
|---|---|---|
| 422 | INVALID_EMAIL | Formato de email inválido |
| 422 | INVALID_PASSWORD | Contraseña incompatible con los requisitos |
| 422 | VALIDATION_ERROR | Contrato de entrada inválido |
| 409 | EMAIL_ALREADY_EXISTS | Email registrado previamente |
| 429 | RATE_LIMIT_EXCEEDED | Límite de intentos alcanzado |
| 500 | INTERNAL_SERVER_ERROR | Fallo interno inesperado |
| 503 | SERVICE_UNAVAILABLE | PostgreSQL indisponible |

La restricción UNIQUE de PostgreSQL garantizará la unicidad incluso ante registros concurrentes.

Una cuenta eliminada lógicamente no liberará automáticamente su email para un nuevo registro.

## 6. Hashing de contraseñas

Se utilizará bcrypt para almacenar y verificar contraseñas.

bcrypt incorpora un salt aleatorio y un factor de coste configurable que dificulta los ataques de fuerza bruta.

El factor de coste inicial será 12, configurable mediante BCRYPT_ROUNDS.

Este valor deberá comprobarse mediante pruebas de rendimiento.

### 6.1. Registro

1. Validar la contraseña.
2. Convertirla a bytes mediante UTF-8.
3. Generar un salt.
4. Calcular el hash mediante bcrypt.
5. Almacenar el hash resultante en user.password_hash.

Ejemplo conceptual:

```python
import bcrypt


password_bytes = password.encode("utf-8")

salt = bcrypt.gensalt(rounds=12)

password_hash = bcrypt.hashpw(
    password_bytes,
    salt,
).decode("utf-8")
```

### 6.2. Verificación

La contraseña se verificará mediante bcrypt.checkpw().

Ejemplo conceptual:

```python
es_valida = bcrypt.checkpw(
    password.encode("utf-8"),
    password_hash.encode("utf-8"),
)
```

No se compararán hashes generados independientemente, ya que bcrypt utiliza salts aleatorios.

### 6.3. Restricciones

- Las contraseñas originales no se almacenarán.
- Las contraseñas no se registrarán en los logs.
- Los hashes no se expondrán mediante respuestas HTTP.
- Las contraseñas no se truncarán para adaptarlas a bcrypt.
- La verificación estará protegida mediante límites de intentos.
- Los mensajes de credenciales incorrectas serán genéricos.
- No se utilizará SHA-256 directamente para almacenar contraseñas.

## 7. Inicio de sesión

### 7.1. Endpoint

POST /auth/login

Utilizará los contratos LoginIn y LoginOut.

### 7.2. Proceso

1. Validar la estructura de los datos.
2. Normalizar el email.
3. Aplicar los límites de intentos de autenticación.
4. Buscar el usuario mediante su email.
5. Verificar la contraseña.
6. Comprobar user.is_active.
7. Comprobar user.deleted_at.
8. Generar un token de sesión.
9. Registrar su hash y metadatos en memoria.
10. Devolver LoginOut.

La respuesta será HTTP 200 únicamente cuando se haya autenticado correctamente al usuario y creado una sesión válida.

La autenticación no generará automáticamente una API key.

### 7.3. Errores

| HTTP | Código | Situación |
|---|---|---|
| 401 | INVALID_CREDENTIALS | Email o contraseña incorrectos |
| 403 | USER_INACTIVE | Credenciales correctas de una cuenta no habilitada |
| 422 | VALIDATION_ERROR | Contrato de entrada inválido |
| 429 | RATE_LIMIT_EXCEEDED | Demasiados intentos |
| 500 | INTERNAL_SERVER_ERROR | Fallo interno inesperado |
| 503 | SERVICE_UNAVAILABLE | Dependencia necesaria indisponible |

Un email inexistente y una contraseña incorrecta producirán el mismo error de credenciales.

El estado de una cuenta desactivada no se revelará antes de verificar correctamente su contraseña.

Las cuentas eliminadas lógicamente no podrán iniciar sesión.

## 8. Gestión de sesiones

### 8.1. Tipo de sesión

Se utilizarán tokens opacos generados mediante mecanismos criptográficamente seguros.

No se implementarán JWT ni OAuth durante esta fase.

Una sesión identifica a un usuario, pero no concede automáticamente los permisos de una API key.

### 8.2. Generación

Los tokens se generarán mediante el módulo secrets de Python, utilizando al menos 32 bytes aleatorios.

Ejemplo conceptual:

```python
import secrets


session_token = secrets.token_urlsafe(32)
```

El registro interno de sesión contendrá:

- Hash del token.
- Identificador del usuario.
- Fecha de creación.
- Fecha de caducidad.

Se utilizará SHA-256 para obtener el hash de tokens generados con suficiente entropía.

El token original únicamente se devolverá durante el inicio de sesión.

### 8.3. Almacenamiento

Las sesiones se mantendrán en memoria del backend.

No se incorporará una tabla session al modelo relacional.

El almacenamiento estará protegido frente a accesos concurrentes.

Podrán utilizarse estructuras Python y mecanismos de bloqueo compatibles con la arquitectura de un único proceso.

Los tokens caducados deberán retirarse mediante una política de limpieza controlada.

No será necesario introducir un servicio externo para gestionar sesiones.

### 8.4. Caducidad

La duración inicial será de 8 horas desde la creación de la sesión.

```dotenv
SESSION_TTL_SECONDS=28800
```

No se implementarán:

- Refresh tokens.
- Renovación automática.
- Sesiones permanentes.
- Restauración de sesiones tras reiniciar el backend.

Una sesión caducada obligará al usuario a autenticarse nuevamente.

Si un token caducado todavía se encuentra en memoria, podrá identificarse mediante SESSION_EXPIRED.

Si el registro ya se ha eliminado, se tratará como INVALID_SESSION.

Ambos casos devolverán HTTP 401.

### 8.5. Transporte

El cliente enviará el token mediante:

```http
Authorization: Bearer <session_token>
```

Los tokens no se transmitirán mediante parámetros de URL.

Las comunicaciones en producción utilizarán HTTPS.

Las respuestas que contengan tokens originales incluirán:

```http
Cache-Control: no-store
```

### 8.6. Cierre de sesión

Endpoint:

POST /auth/logout

La operación requerirá una sesión válida.

El backend invalidará el token correspondiente.

La respuesta satisfactoria será HTTP 204 sin cuerpo.

Streamlit eliminará de su estado local:

- El token de sesión.
- La selección de API key asociada a esa sesión.
- El estado conversacional autenticado.
- Los controles HITL correspondientes.

Cerrar sesión no eliminará:

- La cuenta.
- Las API keys.
- Las conversaciones.
- El historial persistido.

### 8.7. Cambio de contraseña

Endpoint:

PATCH /auth/password

Utilizará PasswordChangeIn.

La operación deberá:

1. Autenticar la sesión.
2. Verificar la contraseña actual.
3. Validar la nueva contraseña.
4. Calcular el nuevo hash.
5. Confirmar su almacenamiento.
6. Invalidar todas las sesiones del usuario.

Una contraseña actual incorrecta devolverá HTTP 401 INVALID_CREDENTIALS.

Una nueva contraseña incompatible con los requisitos devolverá HTTP 422 INVALID_PASSWORD.

La respuesta satisfactoria podrá utilizar UserOut con HTTP 200.

El usuario deberá iniciar sesión nuevamente.

Cambiar la contraseña no modificará automáticamente las API keys existentes.

### 8.8. Invalidación

Una sesión quedará invalidada cuando:

- El usuario cierre sesión.
- Se alcance su fecha de caducidad.
- El usuario modifique su contraseña.
- El administrador desactive la cuenta.
- El administrador elimine lógicamente la cuenta.
- El proceso del backend se reinicie.

La modificación de contraseña, desactivación o eliminación de una cuenta invalidará todas las sesiones correspondientes.

Una sesión invalidada no podrá reutilizarse posteriormente.

### 8.9. Reinicio del servicio

Después de un reinicio o redeploy, el usuario deberá autenticarse nuevamente.

Las cuentas, API keys, conversaciones y mensajes permanecerán almacenados en PostgreSQL.

La pérdida de una sesión no implica la pérdida del historial persistente.

## 9. Generación de API keys

### 9.1. Formato

Las API keys serán credenciales opacas generadas mediante el módulo secrets.

Ejemplo conceptual:

```python
import secrets


api_key = secrets.token_urlsafe(32)
```

La API key original será independiente de api_key.id.

No se utilizarán UUID como único secreto de autenticación.

El rol se obtendrá del registro persistido en PostgreSQL y no de la apariencia de la clave.

### 9.2. API key Free anónima

Endpoint:

POST /api-keys/free

No requerirá registro ni sesión.

No será necesario proporcionar un body.

El backend determinará exclusivamente:

- api_key.role=ApiKeyRole.FREE.
- api_key.user_id=NULL.
- api_key.is_active=True.
- api_key.deleted_at=NULL.

También generará:

- api_key.id.
- api_key.key_hash.
- api_key.created_at.

last_used_at comenzará con valor NULL.

El consumidor no podrá proporcionar su propio rol, propietario o secreto de autenticación.

Se aplicarán los límites de emisión anónima antes de crear la clave.

La respuesta será HTTP 201 ApiKeyCreatedOut después de confirmar la persistencia.

Streamlit solicitará una clave Free anónima cuando resulte necesario y la conservará durante la sesión del consumidor.

### 9.3. API key Free registrada

Endpoint:

POST /api-keys

Requerirá una sesión válida.

Utilizará ApiKeyCreateIn.

Ejemplo:

```json
{
    "role": "free"
}
```

El backend obtendrá user_id exclusivamente de la sesión autenticada.

No se aceptará user_id como parámetro de creación ordinaria.

La clave resultante tendrá:

- api_key.role=ApiKeyRole.FREE.
- api_key.user_id=user.id.

La creación estará sujeta a los límites de emisión y de claves activas.

La respuesta será HTTP 201 ApiKeyCreatedOut.

### 9.4. API key User

Endpoint:

POST /api-keys

Ejemplo:

```json
{
    "role": "user"
}
```

Requerirá:

- Sesión válida.
- Usuario activo.
- Usuario no eliminado.
- Autorización para obtener una API key User.
- Disponibilidad dentro de los límites de emisión.
- Disponibilidad dentro del límite de claves activas.

El cliente podrá solicitar el rol User, pero no determinar si está autorizado.

Durante el PB03 se utilizará una lista de identificadores UUID de usuarios autorizados mediante configuración del backend.

La variable será:

```dotenv
USER_TIER_ALLOWED_USER_IDS=
```

La lista contendrá los identificadores de las cuentas previamente autorizadas por el responsable del producto.

No se concederá acceso al nivel User únicamente porque una dirección de email coincida con una lista de direcciones permitidas.

El registro público no verifica la titularidad del correo electrónico.

Los identificadores autorizados deberán corresponder a cuentas cuya identidad haya sido comprobada mediante un procedimiento administrativo controlado.

Si el usuario no está autorizado, se devolverá:

```text
HTTP 403 USER_TIER_NOT_AUTHORIZED
```

La autorización para emitir claves User no modificará el rol de las claves Free previamente existentes.

La retirada de un usuario de la lista impedirá nuevas emisiones ordinarias de claves User.

No revocará automáticamente las claves User previamente emitidas.

La revocación de credenciales existentes se realizará mediante las operaciones administrativas correspondientes.

### 9.5. API key Admin

Las API keys administrativas se emitirán exclusivamente mediante un procedimiento interno restringido.

La primera clave administrativa deberá poder aprovisionarse sin depender de otra API key Admin previamente existente.

El procedimiento deberá:

- Utilizar una cuenta administrativa controlada.
- Asociar la clave a un usuario existente.
- Obtener el secreto desde un entorno seguro.
- Utilizar una credencial de elevada entropía.
- Registrar únicamente el hash.
- Evitar contraseñas y credenciales predeterminadas.
- Evitar la exposición de secretos.
- Evitar duplicar credenciales durante reinicios.
- Respetar las restricciones relacionales.

La variable API_KEY requerida por el proyecto podrá utilizarse para aprovisionar una credencial administrativa de demostración.

La credencial deberá quedar vinculada correctamente a una cuenta y un registro api_key con rol Admin.

No se utilizará la comparación directa con API_KEY como mecanismo para omitir las comprobaciones de PostgreSQL.

El aprovisionamiento será idempotente respecto a la credencial ya registrada.

Si una clave existente ha sido desactivada o eliminada, un reinicio del backend no deberá reactivarla automáticamente.

Si existe una discrepancia entre la credencial configurada y su registro persistente, deberá comunicarse el problema de configuración sin sobrescribir silenciosamente los datos.

No se expondrá ningún endpoint para emitir nuevas claves Admin.

### 9.6. Emisión administrativa

Endpoint:

POST /admin/api-keys

Requerirá una API key Admin válida y activa.

Utilizará AdminApiKeyCreateIn.

Ejemplo de emisión Free anónima:

```json
{
    "role": "free",
    "user_id": null
}
```

Ejemplo de emisión User:

```json
{
    "role": "user",
    "user_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

Reglas:

| Rol | Propietario |
|---|---|
| Free | Opcional |
| User | Obligatorio |
| Admin | No admitido |

Cuando se indique un propietario, deberá corresponder a un usuario existente, activo y no eliminado.

La emisión administrativa de una API key User constituirá una autorización explícita para esa credencial.

No será necesario que su propietario figure en la lista de usuarios autorizados para realizar emisiones ordinarias.

La emisión administrativa de una clave User no concederá automáticamente permiso al propietario para generar nuevas claves User.

Se respetarán los límites aplicables de claves activas y emisión.

La respuesta será HTTP 201 ApiKeyCreatedOut después de confirmar la transacción.

### 9.7. Contratos públicos

Los contratos definitivos se establecen en [12-contratos-http.md](12-contratos-http.md).

| Contrato | Responsabilidad |
|---|---|
| ApiKeyCreateIn | Emisión ordinaria mediante sesión |
| AdminApiKeyCreateIn | Emisión administrativa |
| ApiKeyOut | Información pública de una credencial |
| ApiKeyCreatedOut | Información pública y secreto original durante su emisión |
| ActiveStatusIn | Modificación administrativa del estado activo |

Los modelos de emisión rechazarán campos adicionales no autorizados.

Los roles solicitables mediante HTTP serán exclusivamente free y user.

## 10. Hashing de API keys

A diferencia de las contraseñas elegidas por los consumidores, las API keys se generarán mediante una fuente criptográficamente segura y poseerán elevada entropía.

Se utilizará SHA-256 para calcular un hash determinista.

```python
import hashlib


key_hash = hashlib.sha256(
    api_key.encode("utf-8")
).hexdigest()
```

### 10.1. Justificación

- Permite localizar directamente la credencial mediante su hash.
- Evita almacenar el secreto original.
- Permite utilizar un índice UNIQUE.
- Evita recorrer todos los registros durante la autenticación.
- Reduce el coste computacional respecto a bcrypt.

SHA-256 no se utilizará directamente para almacenar contraseñas.

### 10.2. Almacenamiento

El hash se almacenará en api_key.key_hash.

La API key original únicamente se devolverá durante su generación autorizada.

Si un consumidor pierde una clave original, no será posible recuperarla desde PostgreSQL.

Un usuario registrado podrá seleccionar una clave Free o User propia mediante su identificador y una sesión válida, cuando el endpoint admita esta modalidad.

### 10.3. Restricciones

- No almacenar claves originales en PostgreSQL.
- No devolver key_hash en respuestas HTTP.
- No registrar claves originales en los logs.
- No incluir claves en URLs.
- No incorporar claves al repositorio.
- No utilizar claves elegidas manualmente por consumidores.
- No utilizar identificadores UUID como sustitutos del secreto.
- No recuperar ni regenerar un secreto original a partir de su hash.

Las respuestas ApiKeyCreatedOut incluirán Cache-Control: no-store.

## 11. Control de emisión de API keys

La generación ilimitada de claves permitiría eludir las cuotas comerciales del asistente.

Se establecen los siguientes límites iniciales:

| Tipo de clave | Límite |
|---|---|
| Free registrada | Una clave activa por usuario |
| User | Cinco claves activas por usuario |
| Admin | Emisión interna restringida |
| Free anónima | Límites de emisión independientes |

Los límites de claves registradas serán configurables.

Las claves desactivadas y eliminadas no se contabilizarán como activas.

### 11.1. Emisión concurrente

La comprobación del número de claves activas y su creación deberán protegerse frente a operaciones concurrentes.

No será suficiente:

1. Consultar el número de claves activas.
2. Liberar la protección.
3. Insertar posteriormente una nueva clave.

Ambas operaciones deberán formar parte de una unidad de trabajo protegida.

Podrán utilizarse bloqueos sobre la fila del propietario dentro de una transacción SQL.

La emisión ordinaria y administrativa deberán utilizar el mismo mecanismo de control.

Si se alcanza el límite de claves activas, se devolverá:

```text
HTTP 409 API_KEY_LIMIT_REACHED
```

### 11.2. Reactivación

La reactivación también estará sujeta al límite de claves activas.

No se permitirá eludir el límite mediante la creación de claves adicionales mientras otras permanecen desactivadas y su posterior reactivación.

Reactivar una clave no reiniciará deliberadamente sus contadores de consumo mantenidos en memoria.

### 11.3. Límites temporales

La emisión y sustitución de credenciales estarán sujetas a los controles establecidos en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

Estos límites serán independientes del número máximo de claves activas.

Superar un límite temporal devolverá HTTP 429 RATE_LIMIT_EXCEEDED.

Cuando pueda determinarse el tiempo de reintento, se incluirá Retry-After.

### 11.4. Consumidores anónimos

Streamlit conservará la API key Free durante la sesión del consumidor.

No se generará una nueva clave:

- Para cada mensaje.
- Para cada rerun.
- Para cada conversación.
- Al alcanzar una cuota comercial.
- Al recibir un error técnico.

La emisión anónima estará protegida mediante límites de seguridad.

La dirección IP podrá utilizarse cuando proceda de una fuente fiable.

No se confiará automáticamente en cabeceras de identificación de origen proporcionadas por consumidores externos.

### 11.5. Limitaciones

El acceso anónimo no permite identificar inequívocamente a una persona.

Un consumidor podría intentar obtener nuevas credenciales utilizando sesiones diferentes.

Durante esta fase se aplicarán mecanismos razonables de mitigación.

No se garantizará una identificación anónima permanente ni se utilizarán mecanismos invasivos de identificación del dispositivo.

Los contadores mantenidos en memoria tampoco constituirán un sistema persistente de facturación.

## 12. Autenticación mediante API key

### 12.1. Cabecera HTTP

```http
X-API-Key: <api_key>
```

Esta modalidad estará disponible para los clientes HTTP autorizados, incluyendo Swagger.

No se admitirán API keys mediante parámetros de URL.

### 12.2. Proceso

1. Obtener la API key de la cabecera.
2. Comprobar que está presente.
3. Calcular su hash.
4. Buscar api_key.key_hash en PostgreSQL.
5. Comprobar que la clave existe.
6. Comprobar api_key.is_active.
7. Comprobar api_key.deleted_at.
8. Recuperar el propietario cuando exista.
9. Comprobar user.is_active y user.deleted_at.
10. Obtener el rol desde PostgreSQL.
11. Construir el contexto de autenticación.

La autenticación no dependerá de roles, identificadores de propietario ni permisos declarados por el consumidor.

### 12.3. Errores

| HTTP | Código | Situación |
|---|---|---|
| 401 | API_KEY_REQUIRED | No se proporciona la credencial obligatoria |
| 401 | INVALID_API_KEY | La credencial no corresponde a una API key válida |
| 403 | API_KEY_INACTIVE | La credencial corresponde a una clave deshabilitada |
| 403 | USER_INACTIVE | El propietario no está habilitado |
| 503 | SERVICE_UNAVAILABLE | No puede consultarse PostgreSQL |

Una credencial eliminada lógicamente no podrá autenticarse.

La ausencia de configuración imprescindible del servidor se comunicará mediante HTTP 503 SERVICE_NOT_CONFIGURED cuando corresponda.

No se confundirá un fallo de configuración del servidor con una credencial incorrecta del consumidor.

### 12.4. Contexto de autenticación

El backend dispondrá de un contexto interno que identifique:

- api_key_id.
- user_id, cuando corresponda.
- role.

El contexto se utilizará para:

- Autorizar operaciones.
- Comprobar la propiedad de recursos.
- Aplicar cuotas.
- Aplicar límites HTTP.
- Registrar eventos operativos autorizados.

No contendrá la API key original ni su hash.

### 12.5. Orden de los controles

La autenticación se realizará antes de contabilizar peticiones contra una API key.

La autorización y los controles posteriores respetarán el orden establecido en la especificación de robustez.

Una credencial inexistente o incorrecta no deberá consumir la cuota comercial de otra clave.

## 13. Autenticación mediante sesión

### 13.1. Cabecera HTTP

```http
Authorization: Bearer <session_token>
```

### 13.2. Proceso

1. Obtener el token.
2. Comprobar su presencia y formato.
3. Calcular su hash.
4. Localizar la sesión.
5. Comprobar su caducidad.
6. Recuperar el usuario desde PostgreSQL.
7. Comprobar user.is_active.
8. Comprobar user.deleted_at.
9. Construir el contexto de identidad.

El estado actual del usuario deberá verificarse en cada operación protegida.

Una sesión previamente válida no podrá utilizarse para eludir la desactivación de una cuenta.

### 13.3. Operaciones autorizadas

- Consultar la cuenta propia.
- Modificar la contraseña.
- Cerrar sesión.
- Solicitar API keys autorizadas.
- Listar las API keys propias.
- Consultar una clave propia.
- Consultar el historial autorizado de una clave propia.

La sesión no concede automáticamente permisos administrativos.

La ejecución del asistente mediante sesión requerirá seleccionar una API key propia autorizada.

### 13.4. Errores

| HTTP | Código | Situación |
|---|---|---|
| 401 | INVALID_SESSION | Sesión inexistente, inválida o ausente |
| 401 | SESSION_EXPIRED | Sesión caducada identificable |
| 403 | USER_INACTIVE | Cuenta no habilitada |
| 503 | SERVICE_UNAVAILABLE | PostgreSQL indisponible |

Un error de autenticación no devolverá un objeto de usuario aparentemente válido acompañado de un campo de error.

## 14. Selección de API keys desde Streamlit

Un usuario registrado podrá disponer de diferentes API keys.

El cliente deberá identificar explícitamente qué credencial desea utilizar.

El identificador seleccionado será api_key.id.

Como las claves originales no podrán recuperarse desde PostgreSQL, se utilizará la siguiente modalidad:

```http
Authorization: Bearer <session_token>
X-API-Key-Id: <api_key_id>
```

### 14.1. Validaciones

El backend comprobará:

- Que la sesión sea válida.
- Que el usuario esté activo.
- Que la API key exista.
- Que api_key.user_id coincida con el usuario autenticado.
- Que la clave esté activa.
- Que la clave no esté eliminada.
- Que el rol permita la operación solicitada.

El identificador de una API key no constituirá una credencial suficiente sin una sesión válida.

Esta modalidad estará disponible para claves Free registradas y User.

No permitirá utilizar claves Admin mediante una sesión ordinaria.

### 14.2. Modalidades admitidas

| Operación | Credencial |
|---|---|
| Consulta del asistente mediante clave original | X-API-Key |
| Consulta del asistente mediante cuenta registrada | Authorization y X-API-Key-Id |
| Operación de cuenta | Authorization |
| Historial mediante cuenta | Authorization y recurso indicado en la ruta |
| Operación administrativa | X-API-Key con rol Admin |

No se aceptarán combinaciones ambiguas de modalidades de autenticación.

Una petición que combine una API key original con la modalidad de sesión y selección de clave devolverá:

```text
HTTP 422 AMBIGUOUS_CREDENTIALS
```

### 14.3. Equivalencia de autenticación

La utilización de una API key original y la utilización autorizada de la misma clave mediante sesión deberán producir un contexto de autenticación equivalente.

Ambas modalidades compartirán:

- api_key_id.
- Permisos.
- Cuotas comerciales.
- Límites HTTP asociados a la clave.
- Conversaciones autorizadas.

No podrán utilizarse las dos modalidades para duplicar los límites de consumo de una misma clave.

### 14.4. Cambio de clave

Cuando el usuario seleccione otra API key:

- Se actualizará la clave seleccionada en Streamlit.
- Se descartará el estado conversacional activo de la interfaz.
- Se retirarán los identificadores de aprobación correspondientes al hilo anterior.
- Se consultará el historial autorizado de la nueva clave.
- No se modificarán los datos almacenados de las claves anteriores.

El cambio de clave no permitirá acceder a una conversación de la clave anterior mediante la nueva credencial.

### 14.5. Pérdida de sesión o credencial

Si la sesión caduca, Streamlit solicitará una nueva autenticación.

No generará automáticamente una nueva API key para sustituir una credencial válida cuya sesión haya caducado.

Si se pierde una respuesta HTTP que contenía una API key recién emitida, no podrá recuperarse su secreto original desde PostgreSQL.

No se repetirá automáticamente la operación de emisión.

El consumidor registrado podrá consultar las claves asociadas a su cuenta y utilizar la modalidad de sesión cuando esté autorizada.

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

Una cuenta registrada no obtendrá permisos administrativos por el hecho de poseer una API key Admin.

Para ejecutar operaciones administrativas deberá proporcionar explícitamente una credencial Admin original, válida y activa.

Una API key Free que solicite una consulta multimodal recibirá:

```text
HTTP 403 INSUFFICIENT_PERMISSIONS
```

La autorización se comprobará antes de procesar la imagen mediante Gemini.

La denegación no consumirá cuota comercial.

Ocultar botones en Streamlit constituirá una medida de interfaz, no un mecanismo de seguridad.

## 16. Autorización basada en la propiedad

La autorización basada en roles no será suficiente para proteger las conversaciones.

También deberá comprobarse la propiedad del recurso solicitado.

### 16.1. API keys Free y User

Una operación sobre una conversación estará autorizada cuando el rol permita el endpoint y se cumpla:

```python
conversation.api_key_id == auth_context.api_key_id
```

La coincidencia entre los propietarios de dos API keys diferentes no concederá acceso cruzado a sus conversaciones.

### 16.2. API key Admin

Una API key Admin activa podrá acceder a cualquier conversación.

La autorización no estará restringida por conversation.api_key_id.

El acceso administrativo:

- No modificará la propiedad de la conversación.
- No permitirá ignorar los límites técnicos.
- No permitirá omitir las comprobaciones del checkpoint.
- No permitirá resolver una aprobación inexistente.
- No permitirá utilizar un approval_id obsoleto.

### 16.3. Acceso mediante sesión

Cuando se consulte el historial de una clave mediante sesión, deberá comprobarse:

```python
api_key.user_id == user.id
```

Para acceder a una conversación concreta también deberá comprobarse:

```python
conversation.api_key_id == api_key.id
```

Las dos comprobaciones serán necesarias.

Conocer el identificador de un recurso no concederá autorización para acceder a él.

### 16.4. Recursos ajenos

Cuando un consumidor intente acceder a una conversación ajena, se devolverá:

```text
HTTP 404 THREAD_NOT_FOUND
```

Cuando intente consultar mediante sesión una clave ajena o no accesible, se devolverá:

```text
HTTP 404 API_KEY_NOT_FOUND
```

No se revelará si el recurso solicitado existe para otro consumidor.

### 16.5. HITL

La resolución de una aprobación exigirá:

- Credencial válida.
- Rol autorizado.
- Acceso autorizado a la conversación.
- Checkpoint real disponible.
- Interrupción HITL pendiente.
- approval_id válido y correspondiente al plan pendiente.

El identificador approval_id no sustituye la autenticación.

El consumidor no podrá proporcionar un plan completo ni un estado de LangGraph para modificar la aprobación.

Se conservará el HITL obligatorio del agente PB02.

## 17. Acceso al historial

### 17.1. Free anónimo

Podrá crear y continuar sus conversaciones utilizando su API key y thread_id.

No dispondrá de acceso a los endpoints de consulta del historial persistente.

Streamlit conservará los mensajes de la conversación activa durante la sesión.

### 17.2. Free registrado

Podrá consultar el historial de sus claves Free mediante los endpoints autenticados por sesión.

No obtendrá acceso a consultas multimodales ni a cuotas superiores por el hecho de registrarse.

### 17.3. User

Podrá consultar el historial de la API key utilizada mediante los endpoints generales autorizados.

También podrá consultar el historial de sus claves Free y User seleccionándolas explícitamente mediante una sesión válida.

No podrá utilizar una API key para consultar conversaciones de otra clave.

### 17.4. Admin

Podrá consultar cualquier conversación mediante una API key administrativa activa.

### 17.5. API keys desactivadas

Una clave desactivada no permitirá autenticarse mediante su secreto original ni ejecutar el asistente mediante sesión.

Su propietario podrá consultar el historial correspondiente mediante una sesión válida.

Estas operaciones serán exclusivamente de lectura.

### 17.6. API keys eliminadas

Las claves eliminadas lógicamente quedarán excluidas de las operaciones ordinarias de consulta.

El acceso a su historial quedará reservado a operaciones administrativas autorizadas.

### 17.7. Historial y estado operativo

El acceso al historial persistente no concederá automáticamente capacidad para continuar una conversación.

La continuación dependerá de:

- La autorización actual.
- El estado de la API key.
- La disponibilidad del checkpoint.
- El estado conversacional.
- Los límites de ejecución.

No se reconstruirán checkpoints a partir del historial SQL.

Los permisos de lectura permanecerán diferenciados de los permisos de ejecución.

## 18. Gestión de credenciales y estados

### 18.1. Contrato de modificación

Las operaciones administrativas de modificación utilizarán ActiveStatusIn.

```python
from pydantic import BaseModel, ConfigDict, StrictBool


class ActiveStatusIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_active: StrictBool
```

Se utilizará en:

- PATCH /admin/users/{user_id}
- PATCH /admin/api-keys/{api_key_id}

No se permitirá modificar mediante estos contratos:

- Identificadores.
- Propietarios.
- Roles.
- Hashes.
- Fechas de eliminación.
- Contraseñas.

Las respuestas utilizarán los modelos públicos correspondientes.

### 18.2. Desactivación de una API key

La operación establecerá:

- api_key.is_active=False.
- api_key.deleted_at permanecerá sin cambios.

La desactivación impedirá realizar nuevas operaciones mediante la clave.

La operación no eliminará:

- La clave.
- Su hash.
- Su propietario.
- Sus conversaciones.
- Sus mensajes.

Una desactivación no podrá convertir una clave eliminada lógicamente en una clave recuperable.

### 18.3. Reactivación de una API key

Requerirá:

- Credencial administrativa válida.
- Clave existente.
- Clave no eliminada.
- Propietario activo y no eliminado, cuando exista.
- Disponibilidad dentro del límite de claves activas.

La comprobación de límites y la modificación del estado deberán protegerse frente a operaciones concurrentes.

Si se supera el límite de claves activas, se devolverá:

```text
HTTP 409 API_KEY_LIMIT_REACHED
```

Si la clave está eliminada lógicamente, se devolverá:

```text
HTTP 409 API_KEY_DELETED
```

Reactivar una clave no:

- Modificará su rol.
- Cambiará su propietario.
- Generará un nuevo secreto.
- Reiniciará deliberadamente sus cuotas.
- Restaurará checkpoints perdidos.

### 18.4. Eliminación de una API key

Endpoint:

DELETE /admin/api-keys/{api_key_id}

Se establecerá:

- api_key.is_active=False.
- api_key.deleted_at=fecha de eliminación.

La clave dejará de autorizar operaciones.

No podrá reactivarse mediante los endpoints administrativos ordinarios.

Se conservarán las referencias necesarias para mantener la integridad relacional.

La respuesta satisfactoria será HTTP 204 después de confirmar la modificación persistente.

### 18.5. Desactivación de un usuario

La operación establecerá:

- user.is_active=False.
- user.deleted_at permanecerá sin cambios.

Se invalidarán todas las sesiones del usuario.

Todas las API keys asociadas dejarán de autorizar operaciones.

No será necesario modificar individualmente api_key.is_active, porque la autenticación comprobará también el estado del propietario.

### 18.6. Reactivación de un usuario

Una cuenta desactivada podrá reactivarse mediante una operación administrativa autorizada, siempre que no esté eliminada lógicamente.

La reactivación:

- Establecerá user.is_active=True.
- No recuperará sesiones previamente invalidadas.
- No modificará el estado individual de sus API keys.
- No restaurará checkpoints perdidos.

Las claves que continuasen individualmente activas podrán volver a utilizarse, siempre que cumplan las demás condiciones de autorización.

Las claves desactivadas individualmente permanecerán desactivadas.

Si el usuario está eliminado lógicamente, se devolverá:

```text
HTTP 409 USER_DELETED
```

### 18.7. Eliminación de un usuario

Endpoint:

DELETE /admin/users/{user_id}

Se establecerá:

- user.is_active=False.
- user.deleted_at=fecha de eliminación.

Se invalidarán todas sus sesiones.

Todas las API keys asociadas quedarán inutilizables.

La eliminación será lógica y conservará la integridad referencial.

La respuesta satisfactoria será HTTP 204 después de confirmar la persistencia.

### 18.8. Operaciones en curso

La desactivación o eliminación de credenciales impedirá admitir nuevas operaciones.

Una ejecución admitida previamente podrá continuar utilizando recursos hasta su finalización real.

Antes de entregar una respuesta del asistente o persistir un turno, el backend volverá a comprobar las condiciones de autorización aplicables.

Si la autorización necesaria ya no es válida:

- No se devolverá un resultado del asistente como éxito autorizado.
- No se iniciará la persistencia de mensajes no autorizada.
- Se devolverá el error correspondiente.
- Se protegerá la consistencia del checkpoint.

Las comprobaciones y escrituras deberán coordinarse con las operaciones administrativas concurrentes.

La revocación de una credencial no garantiza la cancelación inmediata de una ejecución que ya esté utilizando un proveedor externo.

### 18.9. Alcance de la eliminación lógica

La eliminación lógica no constituirá un mecanismo de supresión física definitiva de datos personales.

Los procedimientos de conservación, anonimización y eliminación definitiva deberán desarrollarse antes de una futura explotación comercial.

## 19. Dependencias de FastAPI

La autenticación y la autorización se implementarán mediante dependencias reutilizables de FastAPI.

Se utilizará Depends o Security según corresponda al contrato de autenticación.

### 19.1. Separación de responsabilidades

| Dependencia | Responsabilidad |
|---|---|
| get_session | Proporcionar una sesión de PostgreSQL |
| get_current_user | Identificar al usuario autenticado |
| get_current_api_key | Autenticar una API key original |
| get_auth_context | Resolver la modalidad de autenticación |
| require_roles | Comprobar los roles permitidos |
| require_admin | Exigir una API key administrativa |
| require_thread_access | Comprobar el acceso a la conversación |

Los nombres podrán ajustarse durante la implementación, conservando las responsabilidades establecidas.

### 19.2. Aplicación

Los endpoints no duplicarán la lógica de autenticación.

Las dependencias deberán impedir la ejecución del cuerpo del endpoint cuando no se cumplan sus requisitos de seguridad.

La lógica relacional se mantendrá separada de las operaciones propias de LangGraph.

### 19.3. Swagger y OpenAPI

La documentación OpenAPI deberá representar las modalidades de autenticación admitidas.

Podrán utilizarse los mecanismos APIKeyHeader y HTTPBearer de FastAPI.

Swagger permitirá probar las operaciones protegidas mediante X-API-Key.

La autenticación por sesión será una modalidad adicional, no un sustituto de la autenticación mediante API key exigida en el enunciado.

### 19.4. Independencia del núcleo

La CLI, el RAG y las herramientas del PB02 no dependerán de las credenciales HTTP de ReciclaTÍA.

La autenticación HTTP será responsabilidad del backend FastAPI.

Las credenciales de Gemini continuarán gestionándose mediante la configuración correspondiente del proveedor.

## 20. Errores de seguridad

Todos los errores de autenticación, autorización, validación de credenciales y control de emisión respetarán ErrorOut.

El catálogo completo se establece en [12-contratos-http.md](12-contratos-http.md).

| HTTP | Código | Situación |
|---|---|---|
| 401 | API_KEY_REQUIRED | Credencial obligatoria ausente |
| 401 | INVALID_API_KEY | API key incorrecta |
| 401 | INVALID_CREDENTIALS | Credenciales de cuenta incorrectas |
| 401 | INVALID_SESSION | Sesión inválida |
| 401 | SESSION_EXPIRED | Sesión caducada |
| 403 | API_KEY_INACTIVE | Clave no habilitada |
| 403 | USER_INACTIVE | Usuario no habilitado |
| 403 | INSUFFICIENT_PERMISSIONS | Permisos insuficientes |
| 403 | USER_TIER_NOT_AUTHORIZED | Emisión User no autorizada |
| 404 | API_KEY_NOT_FOUND | Clave inexistente o no accesible |
| 404 | USER_NOT_FOUND | Usuario inexistente |
| 404 | THREAD_NOT_FOUND | Conversación inexistente o no accesible |
| 409 | EMAIL_ALREADY_EXISTS | Email ya registrado |
| 409 | API_KEY_LIMIT_REACHED | Límite de claves activas alcanzado |
| 409 | API_KEY_DELETED | Reactivación de clave eliminada |
| 409 | USER_DELETED | Reactivación de usuario eliminado |
| 422 | INVALID_EMAIL | Email incompatible con el contrato |
| 422 | INVALID_PASSWORD | Contraseña incompatible con los requisitos |
| 422 | AMBIGUOUS_CREDENTIALS | Modalidades de autenticación incompatibles |
| 422 | VALIDATION_ERROR | Entrada estructuralmente inválida |
| 429 | RATE_LIMIT_EXCEEDED | Límite temporal alcanzado |
| 500 | INTERNAL_SERVER_ERROR | Fallo interno inesperado |
| 503 | SERVICE_NOT_CONFIGURED | Configuración imprescindible ausente |
| 503 | SERVICE_UNAVAILABLE | Dependencia requerida indisponible |

Los errores no expondrán información sensible ni permitirán identificar recursos ajenos.

No se devolverá HTTP 200 para:

- Una autenticación fallida.
- Una operación no autorizada.
- Una credencial cuya validez no pueda comprobarse.
- Una modificación administrativa fallida.
- Una emisión de credenciales no confirmada.
- Un fallo técnico de persistencia.

No se devolverá HTTP 201 hasta confirmar la creación del recurso.

## 21. Variables de entorno

| Variable | Valor inicial | Responsabilidad |
|---|---|---|
| API_KEY | Secreto del entorno | Credencial administrativa de aprovisionamiento |
| SESSION_TTL_SECONDS | 28800 | Duración de las sesiones |
| BCRYPT_ROUNDS | 12 | Factor de coste de bcrypt |
| FREE_MAX_ACTIVE_KEYS | 1 | Máximo de claves Free registradas activas |
| USER_MAX_ACTIVE_KEYS | 5 | Máximo de claves User activas |
| USER_TIER_ALLOWED_USER_IDS | Lista vacía | UUID de cuentas autorizadas para emisión ordinaria User |

La lista de usuarios autorizados deberá contener exclusivamente UUID válidos.

Una lista vacía impedirá la emisión ordinaria de claves User.

La emisión administrativa seguirá disponible cuando exista una credencial Admin correctamente aprovisionada.

La variable USER_TIER_ALLOWED_EMAILS no se utilizará como mecanismo de autorización.

Los valores secretos se obtendrán exclusivamente del entorno seguro de ejecución.

Las variables deberán documentarse en .env.example sin incluir secretos reales ni identificadores personales reales.

Las variables relacionadas con rate limiting y límites temporales de emisión se establecen en la especificación de robustez.

## 22. Protección de secretos

### 22.1. Secretos del producto

No se expondrán mediante respuestas HTTP ni logs:

- Contraseñas originales.
- Hashes de contraseñas.
- Hashes de API keys.
- Hashes de tokens de sesión.
- Cadenas de conexión.
- Secretos administrativos.
- Credenciales internas de proveedores.

Las API keys originales únicamente podrán devolverse durante su emisión autorizada.

Los tokens de sesión originales únicamente podrán devolverse durante el inicio de sesión.

Estas excepciones no se aplicarán a los registros de observabilidad.

### 22.2. Credenciales del producto y de Gemini

Se mantendrá la separación entre:

| Credencial | Responsabilidad |
|---|---|
| API_KEY | Aprovisionamiento administrativo del producto |
| API keys ReciclaTÍA | Autenticación y autorización de consumidores |
| Tokens de sesión | Identificación temporal de cuentas |
| GEMINI_API_KEY | Autenticación del backend ante Gemini |
| DATABASE_URL | Configuración de conexión a PostgreSQL |

Una API key ReciclaTÍA no permitirá acceder directamente a Gemini.

La credencial de Gemini no se utilizará para autenticar consumidores de ReciclaTÍA.

### 22.3. Transporte y almacenamiento del cliente

Las comunicaciones en producción utilizarán HTTPS.

Streamlit no almacenará secretos en:

- Archivos de texto.
- Parámetros de URL.
- Logs.
- Cachés compartidas entre usuarios.
- Repositorios.

Los secretos necesarios para una sesión se mantendrán únicamente en el estado correspondiente al consumidor.

### 22.4. Respuestas sensibles

Las respuestas que contengan API keys originales o tokens de sesión incluirán:

```http
Cache-Control: no-store
```

Los errores de validación deberán sanitizarse para evitar devolver contraseñas, tokens o secretos contenidos en las peticiones originales.

Las restricciones de logging se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 23. Criterios de aceptación

### 23.1. Registro y autenticación de usuarios

- Un consumidor puede utilizar el nivel Free sin registrarse.
- Un usuario registrado puede utilizar el nivel Free.
- El registro no concede automáticamente acceso al nivel User.
- Los emails normalizados son únicos.
- Las contraseñas se almacenan mediante bcrypt.
- Las contraseñas originales no aparecen en PostgreSQL ni en logs.
- Las credenciales incorrectas reciben HTTP 401.
- Las cuentas desactivadas no pueden iniciar sesión.
- Las cuentas eliminadas no pueden iniciar sesión.
- Una creación fallida no devuelve HTTP 201.

### 23.2. Sesiones

- Los tokens se generan mediante mecanismos criptográficamente seguros.
- Los tokens originales no se almacenan en PostgreSQL.
- Las sesiones tienen una duración limitada.
- Las sesiones caducadas no autorizan operaciones.
- El cierre de sesión invalida el token correspondiente.
- El cambio de contraseña invalida todas las sesiones del usuario.
- La desactivación y eliminación invalidan todas las sesiones asociadas.
- La pérdida de una sesión tras un redeploy no elimina los datos persistidos.

### 23.3. Emisión de credenciales

- Las API keys Free pueden emitirse para consumidores anónimos y registrados.
- Las claves User requieren un propietario registrado.
- La emisión ordinaria User exige autorización explícita.
- La autorización no depende únicamente de la coincidencia de un email.
- La emisión administrativa User no concede permiso automático para nuevas emisiones ordinarias.
- Las claves Admin requieren aprovisionamiento interno restringido.
- Ningún endpoint permite emitir claves Admin.
- Los límites de emisión impiden generar credenciales ilimitadamente dentro de las ventanas configuradas.
- Las operaciones concurrentes no permiten superar los límites de claves activas.
- Las API keys originales únicamente se devuelven durante su emisión.
- Los hashes no se exponen mediante contratos públicos.
- El aprovisionamiento administrativo es idempotente.
- Los reinicios no reactivan automáticamente credenciales deshabilitadas.

### 23.4. Autenticación mediante API key

- Swagger permite utilizar X-API-Key.
- Los endpoints protegidos rechazan credenciales ausentes o incorrectas.
- La autenticación consulta el estado persistente de la clave.
- La autenticación comprueba el estado del propietario.
- Las API keys no se transmiten mediante URLs.
- La autenticación se realiza antes de contabilizar consumo asociado a la clave.
- Una clave incorrecta no consume la cuota de otra clave.

### 23.5. Autorización y propiedad

- El rol se obtiene exclusivamente del backend.
- Una clave Free no puede realizar consultas multimodales.
- Una clave User no puede ejecutar operaciones administrativas.
- Una clave Admin puede consultar cualquier conversación.
- Dos claves del mismo usuario no comparten conversaciones.
- Los recursos ajenos no revelan su existencia.
- Un usuario puede seleccionar explícitamente una clave propia.
- Una sesión ordinaria no permite utilizar una clave Admin.
- Las modalidades de autenticación incompatibles se rechazan.
- Las dos modalidades de autenticación de una misma clave comparten cuotas y permisos.
- Las peticiones directas a la API respetan las mismas restricciones que Streamlit.
- La resolución de HITL exige autorización y una aprobación pendiente real.

### 23.6. Gestión de estados

- Una clave desactivada no permite realizar nuevas consultas.
- El propietario de una clave desactivada puede consultar su historial autorizado.
- Una clave eliminada lógicamente no puede reactivarse.
- Un usuario eliminado lógicamente no puede reactivarse.
- La reactivación de claves respeta los límites de claves activas.
- La desactivación de un usuario impide utilizar sus API keys.
- La reactivación del usuario no reactiva las claves desactivadas individualmente.
- No se modifican propietarios ni roles mediante operaciones de estado.
- Las modificaciones administrativas respetan las transacciones correspondientes.

### 23.7. Errores y observabilidad

- Las operaciones no autorizadas no devuelven HTTP 200.
- Los fallos de PostgreSQL no se presentan como credenciales incorrectas.
- Los códigos HTTP respetan ErrorOut.
- Los límites de seguridad devuelven HTTP 429.
- Los conflictos de estado devuelven HTTP 409 cuando corresponda.
- Los secretos no aparecen en respuestas de error ni logs.
- Las respuestas sensibles incluyen Cache-Control: no-store.
- No se devuelve éxito cuando no puede confirmarse una operación obligatoria.

### 23.8. Compatibilidad académica

- Se mantiene la autenticación mediante API key exigida en el Project Break 03.
- Se utilizan dependencias reutilizables de FastAPI.
- GET /health permanece accesible sin credenciales.
- Swagger permanece accesible para la validación de contratos.
- Los endpoints protegidos aplican los controles de seguridad correspondientes.
- El rate limiting permanece independiente del mecanismo de autenticación.
- El núcleo del PB02 conserva su independencia respecto a FastAPI y PostgreSQL.
- No se incorporan JWT, OAuth, Redis ni tablas adicionales de sesiones.