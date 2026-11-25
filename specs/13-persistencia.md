# 13. Persistencia y modelo relacional

## 1. Objetivo

Implementar una capa de persistencia relacional mediante SQLModel y PostgreSQL que permita almacenar los usuarios, las API keys, las conversaciones y los mensajes de ReciclaTÍA.

La persistencia debe garantizar la integridad referencial, el aislamiento de conversaciones, el control de acceso a los datos y la conservación del historial después de reinicios y redespliegues.

## 2. Tecnologías

| Tecnología | Responsabilidad |
|---|---|
| PostgreSQL | Sistema gestor de bases de datos relacional |
| SQLModel | Definición de modelos y operaciones ORM |
| SQLAlchemy | Motor de conexión, sesiones y transacciones |
| Pydantic | Validación de contratos |
| psycopg2-binary | Driver de conexión con PostgreSQL |
| Docker | Ejecución de PostgreSQL en desarrollo local |
| Render PostgreSQL | Base de datos gestionada en producción |

PostgreSQL será el sistema de almacenamiento tanto en desarrollo como en producción.

No se utilizará SQLite como almacenamiento alternativo del servicio.

## 3. Separación de responsabilidades

| Archivo | Responsabilidad |
|---|---|
| src/models.py | Modelos relacionales, restricciones e índices |
| src/db.py | Engine, creación de tablas y gestión de sesiones |
| api/schemas.py | Contratos públicos de entrada y salida |
| api/service.py | Coordinación entre el asistente y la persistencia |
| api/dependencies.py | Dependencias de acceso a sesiones y recursos |
| api/security.py | Autenticación y autorización |

Los modelos de base de datos no se expondrán directamente como respuestas HTTP.

Los contratos públicos serán independientes de los modelos persistentes.

## 4. Convenciones de almacenamiento

- Nombres de tablas y atributos en snake_case.
- Identificadores UUID para usuarios, API keys y conversaciones.
- Identificadores BIGINT autoincrementales para mensajes.
- Fechas almacenadas en UTC mediante tipos con soporte de zona horaria.
- Claves primarias y foráneas explícitas.
- Restricciones de unicidad gestionadas por PostgreSQL.
- Contraseñas y API keys almacenadas exclusivamente mediante hashes.
- Transacciones para operaciones que deban ejecutarse de forma atómica.
- Integridad referencial garantizada mediante restricciones de base de datos.

## 5. Modelo entidad-relación

```mermaid
erDiagram
    USER o|--o{ API_KEY : posee
    API_KEY ||--o{ CONVERSATION : identifica
    CONVERSATION ||--o{ MESSAGE : contiene

    USER {
        uuid id PK
        string email UK
        string password_hash
        datetime created_at
        boolean is_active
        datetime deleted_at
    }

    API_KEY {
        uuid id PK
        uuid user_id FK
        string key_hash UK
        enum role
        boolean is_active
        datetime created_at
        datetime last_used_at
        datetime deleted_at
    }

    CONVERSATION {
        uuid id PK
        uuid api_key_id FK
        datetime created_at
    }

    MESSAGE {
        bigint id PK
        uuid thread_id FK
        enum role
        text content
        datetime created_at
        integer turn_number
    }
```

Cada conversación pertenece exclusivamente a una API key.

El propietario registrado de una conversación puede obtenerse mediante la relación entre conversation y api_key.

No se duplicará user_id en la tabla conversation.

## 6. Tabla user

Almacena las cuentas registradas en ReciclaTÍA.

| Campo | Tipo PostgreSQL | Nullable | Restricciones |
|---|---|---|---|
| id | UUID | No | Primary Key |
| email | VARCHAR(254) | No | Unique |
| password_hash | VARCHAR(255) | No | — |
| created_at | TIMESTAMPTZ | No | Default fecha actual |
| is_active | BOOLEAN | No | Default True |
| deleted_at | TIMESTAMPTZ | Sí | Default NULL |

### Reglas

- El email se normalizará antes de almacenarse.
- No podrán existir dos cuentas con el mismo email normalizado.
- La contraseña original nunca se almacenará.
- El hash de la contraseña se almacenará en user.password_hash.
- El usuario se crea inicialmente como activo.
- Un usuario desactivado no puede autenticarse ni utilizar sus API keys.
- Un usuario eliminado lógicamente permanece almacenado para conservar la integridad referencial.

La validación de contraseñas, los requisitos de seguridad y los mecanismos de hashing se definen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

## 7. Tabla api_key

Almacena las credenciales de acceso y su asociación con el usuario, cuando corresponda.

| Campo | Tipo PostgreSQL | Nullable | Restricciones |
|---|---|---|---|
| id | UUID | No | Primary Key |
| user_id | UUID | Sí | Foreign Key → user.id |
| key_hash | CHAR(64) | No | Unique |
| role | ENUM(api_key_role) | No | free, user, admin |
| is_active | BOOLEAN | No | Default True |
| created_at | TIMESTAMPTZ | No | Default fecha actual |
| last_used_at | TIMESTAMPTZ | Sí | Default NULL |
| deleted_at | TIMESTAMPTZ | Sí | Default NULL |

### 7.1. Restricciones según el rol

El rol de una API key se representa mediante un tipo enumerado denominado `api_key_role`, cuyos valores permitidos son `free`, `user` y `admin`.

La identidad del consumidor y su nivel de acceso constituyen conceptos independientes.

| Rol | user_id |
|---|---|
| free | Opcional: UUID o NULL |
| user | Obligatorio |
| admin | Obligatorio |

Las API keys Free pueden pertenecer tanto a consumidores anónimos como a usuarios registrados.

El registro de una cuenta no implica automáticamente la asignación del rol User.

Las API keys User requieren una cuenta registrada y autorización para acceder a las funcionalidades de dicho nivel.

Las API keys Admin únicamente pueden emitirse mediante procedimientos administrativos restringidos.

La base de datos garantizará mediante una restricción CHECK que ninguna API key User o Admin carezca de un usuario asociado.

La capa de seguridad será responsable de controlar la emisión de credenciales y evitar cualquier elevación de privilegios.

### 7.2. Generación

La generación y emisión de API keys se realizará conforme a las reglas de autenticación, autorización y aprovisionamiento establecidas en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

La capa de persistencia garantizará el cumplimiento de las restricciones de integridad, unicidad y asociación de las credenciales.

### 7.3. Almacenamiento de secretos

El hash de la API key se almacenará en api_key.key_hash como una cadena hexadecimal de 64 caracteres.

El hash será determinista y único, permitiendo localizar una API key mediante una consulta indexada en PostgreSQL.

La clave original no se almacenará ni podrá recuperarse posteriormente desde PostgreSQL.

Ni la clave original ni su hash se devolverán mediante los endpoints de consulta de API keys.

Los mecanismos de generación y hashing se definen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

### 7.4. Estados

| Estado | is_active | deleted_at |
|---|---|---|
| Activa | True | NULL |
| Desactivada | False | NULL |
| Eliminada lógicamente | False | Fecha de eliminación |

Una API key eliminada lógicamente no podrá estar activa.

Una API key desactivada no permite realizar consultas nuevas, continuar conversaciones ni resolver aprobaciones pendientes.

El propietario autenticado puede consultar el historial correspondiente a una clave desactivada.

### 7.5. Último uso

last_used_at se actualizará cuando la API key haya sido autenticada y autorizada para acceder al servicio, una vez superados los controles de admisión correspondientes.

Este atributo no representa necesariamente una consulta completada correctamente.

No se utilizará como contador de consumo ni como mecanismo de rate limiting.

## 8. Tabla conversation

Representa una conversación del asistente.

| Campo | Tipo PostgreSQL | Nullable | Restricciones |
|---|---|---|---|
| id | UUID | No | Primary Key |
| api_key_id | UUID | No | Foreign Key → api_key.id |
| created_at | TIMESTAMPTZ | No | Default fecha actual |

### 8.1. Identificador

conversation.id corresponde al thread_id utilizado por LangGraph.

La base de datos y el grafo utilizan el mismo identificador para referirse a una conversación.

El identificador no constituye una credencial de acceso.

### 8.2. Propiedad

Una conversación pertenece a una única API key.

La propiedad se establece durante su creación y no podrá modificarse mediante los endpoints públicos.

Una API key User no puede acceder a conversaciones de otras claves, aunque pertenezcan al mismo usuario.

Una API key Admin activa puede acceder a cualquier conversación.

### 8.3. Creación

La conversación se registra después de autenticar y autorizar la petición y antes de ejecutar LangGraph.

Si no se proporciona thread_id, FastAPI genera un UUID.

La política aplicable a un UUID proporcionado por el cliente que todavía no existe deberá quedar definida en el contrato HTTP.

La existencia de una conversación en PostgreSQL no implica necesariamente que exista un checkpoint activo en MemorySaver.

### 8.4. Conversaciones sin mensajes

Una conversación puede existir sin mensajes persistidos cuando:

- Su primer turno está ejecutándose.
- Existe un HITL pendiente.
- La ejecución ha sufrido un fallo técnico.
- El proceso se ha reiniciado antes de resolver el turno.

Estas situaciones no constituyen por sí mismas una inconsistencia relacional.

## 9. Tabla message

Almacena los mensajes pertenecientes a los turnos resueltos del asistente.

| Campo | Tipo PostgreSQL | Nullable | Restricciones |
|---|---|---|---|
| id | BIGINT | No | Primary Key, autoincremental |
| thread_id | UUID | No | Foreign Key → conversation.id |
| role | ENUM(message_role) | No | user, assistant |
| content | TEXT | No | — |
| created_at | TIMESTAMPTZ | No | Default fecha actual |
| turn_number | INTEGER | No | Mayor que 0 |

### 9.1. Roles

| Rol | Contenido |
|---|---|
| user | Pregunta válida enviada por el usuario |
| assistant | Respuesta definitiva del turno |

No se almacenarán como mensajes los prompts internos, los mensajes de sistema, las instrucciones del supervisor ni las llamadas internas a herramientas.

### 9.2. Número de turno

turn_number identifica el turno al que pertenece cada mensaje dentro de una conversación.

Su valor procede del contador de turnos del agente.

Un turno resuelto contiene un mensaje user y un mensaje assistant.

Se establecerá una restricción de unicidad compuesta:

```sql
UNIQUE (thread_id, turn_number, role)
```

Esta restricción evita insertar dos mensajes con el mismo rol para un mismo turno.

Pueden existir saltos en la numeración si algún turno ejecutado no llega a resolverse correctamente.

### 9.3. Orden de recuperación

Los mensajes se recuperarán ordenados por id ascendente.

El identificador autoincremental proporciona un criterio determinista de orden dentro de cada conversación.

created_at representa el momento de almacenamiento del mensaje.

El contrato público MessageOut devolverá role, content y created_at.

## 10. Índices

| Tabla | Campo o combinación | Finalidad |
|---|---|---|
| user | id | Identificación del usuario |
| user | email | Autenticación y unicidad |
| api_key | id | Identificación de la clave |
| api_key | key_hash | Autenticación mediante API key |
| api_key | user_id | Recuperación de claves de un usuario |
| conversation | id | Identificación del hilo |
| conversation | api_key_id | Recuperación de conversaciones por clave |
| message | id | Identificación y orden |
| message | thread_id, id | Recuperación ordenada del historial |
| message | thread_id, turn_number, role | Unicidad del mensaje por turno |

Los índices asociados a claves primarias y restricciones UNIQUE son gestionados por PostgreSQL.

No se crearán índices adicionales redundantes.

## 11. Integridad referencial

No se permitirá:

- Crear una API key User o Admin sin un usuario existente.
- Crear una conversación sin una API key existente.
- Crear un mensaje sin una conversación existente.
- Reasignar una conversación a una API key diferente.
- Activar una clave eliminada lógicamente.

Las claves foráneas impedirán eliminar físicamente registros que tengan dependencias.

No se configurará eliminación física en cascada durante esta primera versión.

## 12. Persistencia de turnos

### 12.1. Criterio de persistencia

Un turno se almacena cuando se ha resuelto correctamente y no existe una aprobación pendiente.

| Situación | Persistir mensajes |
|---|---|
| Respuesta directa válida | Sí |
| Abstención válida sin HITL pendiente | Sí |
| Plan pendiente de HITL | No |
| Plan aprobado | Sí |
| Plan rechazado | Sí |
| Fallo técnico | No |
| Petición HTTP inválida | No |
| Petición no autorizada | No |
| Cuota agotada | No |
| Timeout | No |

El atributo done no se utilizará como único criterio para determinar si debe guardarse un turno.

Un turno rechazado puede estar resuelto aunque la conversación continúe abierta.

### 12.2. Transacción

El almacenamiento de un turno comprende dos inserciones:

1. Mensaje del usuario.
2. Mensaje definitivo del asistente.

Ambas inserciones se realizan dentro de la misma transacción.

Si una de ellas falla, se ejecuta rollback.

No deben quedar turnos parcialmente persistidos.

### 12.3. Prevención de duplicados

La restricción UNIQUE de la tabla message impide insertar más de un mensaje por rol y turno.

La capa de servicios comprobará adicionalmente el estado real del agente y utilizará bloqueos por thread_id.

La restricción de unicidad no convierte automáticamente todos los endpoints en operaciones idempotentes.

### 12.4. Fallo de persistencia

Si LangGraph resuelve correctamente un turno pero PostgreSQL no puede almacenarlo, FastAPI devolverá un error técnico conforme al contrato HTTP.

Se ejecutará rollback de la transacción cuando corresponda.

No se devolverá una respuesta satisfactoria que declare como persistido un turno que no lo está.

Si el fallo de persistencia provoca una inconsistencia entre el checkpoint y la base de datos, la conversación quedará marcada internamente como no reutilizable.

No se permitirá continuar una conversación desde un checkpoint cuya consistencia no pueda garantizarse.

Los intentos posteriores de continuar una conversación afectada devolverán HTTP 409 THREAD_STATE_LOST.

El historial previamente persistido permanecerá disponible.

No existe una transacción atómica compartida entre MemorySaver y PostgreSQL.

## 13. Gestión de la conexión

### 13.1. Variables de entorno

DATABASE_URL se obtendrá del entorno.

Ejemplo de desarrollo local:

```text
postgresql://usuario:password@localhost:5432/reciclatia
```

Los valores reales nunca se incorporarán al repositorio.

Cuando Render proporcione una URL con el prefijo postgres://, se normalizará al prefijo postgresql://.

### 13.2. Engine

Se creará un engine de SQLModel compartido durante la vida del backend.

El engine gestiona las conexiones y su reutilización.

No se creará un engine por petición.

### 13.3. Session

Cada operación o unidad de trabajo tendrá su propia Session.

Las sesiones no se compartirán entre hilos de ejecución ni entre usuarios.

Se cerrarán correctamente después de finalizar las operaciones.

No se mantendrá una sesión de base de datos abierta durante la ejecución prolongada del agente si no resulta necesaria.

### 13.4. Creación de tablas

FastAPI ejecutará la creación de tablas durante su ciclo de inicio mediante:

```python
SQLModel.metadata.create_all(engine)
```

Los modelos deberán estar importados antes de ejecutar create_all.

create_all crea las tablas inexistentes, pero no modifica automáticamente la estructura de tablas ya creadas.

Alembic y las migraciones automatizadas quedan fuera del alcance inicial.

### 13.5. Independencia del núcleo

La configuración de PostgreSQL será obligatoria para ejecutar FastAPI.

No será obligatoria para importar el RAG, ejecutar la CLI ni realizar las pruebas unitarias independientes del backend.

## 14. Operaciones de persistencia

### Usuarios

- Crear usuario.
- Buscar usuario por email.
- Buscar usuario por identificador.
- Listar usuarios.
- Actualizar contraseña.
- Activar o desactivar usuario.
- Eliminar usuario lógicamente.

### API keys

- Registrar nueva API key.
- Buscar API key mediante su hash.
- Buscar API key mediante su identificador.
- Listar claves de un usuario.
- Listar todas las claves como administrador.
- Actualizar last_used_at.
- Activar o desactivar una clave.
- Eliminar una clave lógicamente.

### Conversaciones

- Crear conversación.
- Recuperar conversación mediante thread_id.
- Recuperar conversación verificando api_key_id.
- Listar conversaciones de una API key.
- Listar todas las conversaciones como administrador.

### Mensajes

- Persistir un turno completo.
- Recuperar mensajes de una conversación.
- Comprobar si un turno ya está almacenado.

La capa de persistencia se responsabiliza del acceso a los datos.

La capa de servicios y seguridad determina si una operación está autorizada.

## 15. Desactivación y eliminación

### 15.1. Desactivación de una API key

- api_key.is_active=False.
- api_key.deleted_at=NULL.
- Se conservan la clave y sus conversaciones.
- Se impide su utilización como credencial activa.
- Su propietario puede consultar el historial mediante una sesión válida.
- La clave puede reactivarse mediante una operación administrativa autorizada.

### 15.2. Eliminación de una API key

Se aplicará eliminación lógica.

- api_key.is_active=False.
- api_key.deleted_at recibe la fecha de eliminación.
- Se conservan las referencias y los mensajes.
- La clave deja de estar disponible para su utilización ordinaria.
- No podrá reactivarse mediante las operaciones administrativas normales.
- El acceso ordinario al historial de claves eliminadas queda reservado al administrador.

### 15.3. Desactivación de un usuario

- user.is_active=False.
- user.deleted_at=NULL.
- Se impide la autenticación del usuario.
- Se impide el uso de todas las API keys vinculadas al usuario.
- Se invalidan las sesiones existentes.
- Se conserva la información almacenada.

No es necesario modificar permanentemente el estado individual de cada API key.

La autorización comprobará tanto el estado de la clave como el estado de su propietario.

### 15.4. Eliminación de un usuario

Se aplicará eliminación lógica.

- user.is_active=False.
- user.deleted_at recibe la fecha de eliminación.
- Se invalidan las sesiones del usuario.
- Las API keys asociadas quedan inutilizables.
- Se conservan las conversaciones y los mensajes para mantener la integridad referencial.

### 15.5. Alcance de la eliminación lógica

La eliminación lógica es una decisión funcional de esta primera versión.

No constituye un mecanismo de supresión definitiva de datos personales.

La anonimización, la retención temporal y el borrado físico seguro deberán contemplarse antes de una futura puesta en producción comercial.

## 16. PostgreSQL frente a MemorySaver

| Información | Almacenamiento |
|---|---|
| Usuarios | PostgreSQL |
| API keys | PostgreSQL |
| Propiedad de conversaciones | PostgreSQL |
| Historial de mensajes | PostgreSQL |
| Estado operativo de LangGraph | MemorySaver |
| Checkpoints | MemorySaver |
| HITL pendiente | MemorySaver |
| Índice vectorial | ChromaDB |
| Archivos de imagen recibidos | Almacenamiento temporal |

No se almacenarán los checkpoints de LangGraph en PostgreSQL, excede el alcance por ahora.

Después de un reinicio del backend, el historial seguirá disponible, pero los hilos que necesiten un checkpoint perdido no podrán continuar desde ese estado.

El usuario podrá iniciar una conversación nueva.

## 17. Privacidad y minimización de datos

No se almacenarán permanentemente:

- Contraseñas originales.
- API keys originales.
- Archivos binarios de imágenes recibidas.
- Rutas temporales del servidor.
- Coordenadas como atributos independientes de la base de datos.
- Prompts internos del agente.
- Checkpoints completos.
- Trazas internas de herramientas como mensajes del chat.

Las respuestas del asistente pueden contener direcciones, coordenadas u otra información relacionada con la consulta, que pasará a formar parte del historial textual.

La información almacenada deberá limitarse a la necesaria para el funcionamiento del producto.

## 18. Criterios de aceptación

- PostgreSQL funciona tanto en desarrollo local como en Render.
- Las tablas se crean correctamente durante el inicio de FastAPI.
- Los modelos respetan las restricciones de integridad referencial.
- No existen emails ni hashes de API keys duplicados.
- Las claves Free pueden estar asociadas a un usuario registrado o a un consumidor anónimo.
- Las claves User y Admin deben tener obligatoriamente un usuario asociado.
- Los roles de las API keys están restringidos mediante el ENUM api_key_role.
- Los roles de los mensajes están restringidos mediante el ENUM message_role.
- Ningún usuario puede generar una API key Admin mediante los endpoints públicos.
- Cada conversación pertenece a una única API key.
- Dos claves del mismo usuario no comparten conversaciones.
- Los mensajes se recuperan en orden determinista.
- Un turno resuelto se guarda mediante una única transacción.
- No quedan turnos parcialmente almacenados.
- No se duplican mensajes al repetir una operación de persistencia.
- Los turnos pendientes de HITL no se guardan como resueltos.
- El historial sigue disponible tras reiniciar FastAPI.
- El historial sigue disponible tras un redeploy en Render.
- No se almacenan secretos en texto plano.
- Las API keys desactivadas conservan su historial.
- La capa RAG puede seguir utilizándose sin conexión a PostgreSQL.
- Las pruebas de regresión del PB02 continúan superándose, salvo aquellas cuyo comportamiento se modifique expresamente y requieran actualizar su contrato.
- Un fallo de persistencia no genera una respuesta HTTP satisfactoria.
- No se permite continuar una conversación desde un checkpoint inconsistente.
- Un fallo de persistencia no elimina el historial previamente almacenado.
- Los registros eliminados lógicamente no pueden reactivarse mediante operaciones administrativas ordinarias.
- La desactivación de un usuario no requiere modificar individualmente el estado de sus API keys.