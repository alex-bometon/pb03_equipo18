# 13. Persistencia y modelo relacional

## 1. Objetivo

Implementar una capa de persistencia relacional mediante SQLModel y PostgreSQL que permita almacenar los usuarios, las API keys, las conversaciones y los mensajes de ReciclaTÍA.

La persistencia deberá garantizar:

- La integridad referencial.
- El aislamiento de las conversaciones.
- El control de acceso a los recursos.
- La conservación del historial.
- El almacenamiento atómico de los turnos resueltos.
- La recuperación de los datos después de reinicios y redespliegues.
- La separación entre el historial persistente y el estado operativo del agente.

La persistencia de turnos resueltos deberá respetar los requisitos académicos del Project Break 03.

No se trasladarán los checkpoints de LangGraph a PostgreSQL durante esta fase del desarrollo.

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

La ausencia de conexión a PostgreSQL no deberá provocar un cambio silencioso a otro sistema de almacenamiento.

## 3. Separación de responsabilidades

| Archivo | Responsabilidad |
|---|---|
| src/enums.py | Enumerados compartidos |
| src/models.py | Modelos relacionales, restricciones e índices |
| src/db.py | Engine, creación de tablas, sesiones y operaciones de persistencia |
| api/schemas.py | Contratos públicos de entrada y salida |
| api/service.py | Coordinación entre el asistente y la persistencia |
| api/dependencies.py | Dependencias de acceso a sesiones y recursos |
| api/security.py | Autenticación y autorización |
| api/errors.py | Transformación de errores al contrato HTTP |

Los modelos de base de datos no se expondrán directamente como respuestas HTTP.

Los contratos públicos serán independientes de los modelos persistentes.

La capa de persistencia no será responsable de decidir:

- El enrutamiento del agente.
- La admisibilidad semántica de una consulta.
- La generación de respuestas.
- La necesidad de utilizar herramientas.
- La resolución del HITL.
- Las cuotas comerciales.
- Los permisos HTTP.

La capa de servicios coordinará estas responsabilidades.

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
- Eliminación lógica de usuarios y credenciales.
- Ausencia de eliminación física en cascada durante esta fase.

Los identificadores UUID serán generados mediante mecanismos autorizados del backend.

Los identificadores de recursos no constituirán credenciales de autenticación.

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

No se incorporarán tablas adicionales para:

- Checkpoints.
- Sesiones de autenticación.
- Cuotas comerciales.
- Aprobaciones pendientes.
- Imágenes recibidas.
- Contadores independientes de turnos.

Estas responsabilidades se resolverán mediante los mecanismos establecidos en las especificaciones correspondientes.

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

### 6.1. Reglas

- El email se normalizará antes de almacenarse.
- No podrán existir dos cuentas con el mismo email normalizado.
- La contraseña original nunca se almacenará.
- El hash se almacenará en user.password_hash.
- El usuario se creará inicialmente como activo.
- Un usuario desactivado no podrá autenticarse ni utilizar sus API keys.
- Un usuario eliminado lógicamente permanecerá almacenado para conservar la integridad referencial.
- Un usuario eliminado lógicamente no podrá reactivarse.
- Un usuario eliminado no liberará automáticamente su email para un nuevo registro.

### 6.2. Estados

| Estado | is_active | deleted_at |
|---|---|---|
| Activo | True | NULL |
| Desactivado | False | NULL |
| Eliminado lógicamente | False | Fecha de eliminación |

Un usuario eliminado lógicamente no podrá encontrarse en estado activo.

La coherencia entre is_active y deleted_at deberá garantizarse mediante las restricciones y operaciones de persistencia correspondientes.

### 6.3. Seguridad

Las contraseñas se almacenarán mediante bcrypt.

La validación de contraseñas, los requisitos de seguridad y los mecanismos de hashing se definen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

El modelo público UserOut no expondrá password_hash.

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

El rol de una API key se representará mediante el tipo enumerado api_key_role, cuyos valores permitidos serán:

- free.
- user.
- admin.

Se utilizará ApiKeyRole como enumerado compartido entre los modelos relacionales, los contratos Pydantic y la capa de autorización.

Los valores almacenados en PostgreSQL deberán corresponder a los valores del enumerado y no a los nombres internos de sus miembros Python.

| Rol | user_id |
|---|---|
| free | Opcional: UUID o NULL |
| user | Obligatorio |
| admin | Obligatorio |

Las API keys Free podrán pertenecer tanto a consumidores anónimos como a usuarios registrados.

El registro de una cuenta no implicará automáticamente la asignación del rol User.

Las API keys User requerirán una cuenta registrada y autorización ordinaria o emisión administrativa.

Las API keys Admin únicamente podrán emitirse mediante procedimientos internos restringidos.

La base de datos garantizará mediante una restricción CHECK que ninguna API key User o Admin carezca de un usuario asociado.

La capa de seguridad será responsable de controlar la emisión de credenciales y evitar elevaciones de privilegios.

### 7.2. Generación

La generación y emisión de API keys se realizará conforme a [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

La capa de persistencia garantizará:

- La unicidad del identificador.
- La unicidad del hash.
- La asociación válida con el propietario, cuando corresponda.
- La coherencia del rol.
- El cumplimiento de los límites de claves activas.
- La atomicidad de las operaciones de creación.

La comprobación del número de claves activas y la creación de una nueva clave deberán realizarse de manera protegida frente a operaciones concurrentes.

No será suficiente comprobar el límite mediante una consulta independiente sin proteger la posterior inserción.

Para claves asociadas a usuarios podrá utilizarse el bloqueo de la fila del propietario dentro de la transacción correspondiente.

La misma protección deberá aplicarse a la reactivación de claves.

### 7.3. Almacenamiento de secretos

El hash de la API key se almacenará en api_key.key_hash como una cadena hexadecimal de 64 caracteres.

Se utilizará SHA-256 sobre credenciales generadas mediante una fuente criptográficamente segura.

El hash será determinista y único, permitiendo localizar una API key mediante una consulta indexada en PostgreSQL.

La clave original no se almacenará ni podrá recuperarse posteriormente desde PostgreSQL.

Ni la clave original ni su hash se devolverán mediante los endpoints ordinarios de consulta.

La clave original únicamente se devolverá durante una operación de emisión autorizada y correctamente persistida.

Los contratos ApiKeyOut y ApiKeyCreatedOut se definen en [12-contratos-http.md](12-contratos-http.md).

### 7.4. Estados

| Estado | is_active | deleted_at |
|---|---|---|
| Activa | True | NULL |
| Desactivada | False | NULL |
| Eliminada lógicamente | False | Fecha de eliminación |

Una API key eliminada lógicamente no podrá estar activa.

Una API key desactivada no permitirá:

- Autenticarse mediante la clave original.
- Realizar nuevas consultas.
- Continuar conversaciones.
- Resolver aprobaciones pendientes.
- Utilizar la modalidad de sesión y selección de clave para ejecutar el asistente.

El propietario autenticado podrá consultar el historial correspondiente a una clave desactivada mediante los endpoints autorizados de lectura.

Las claves eliminadas lógicamente quedarán excluidas de las operaciones ordinarias de consulta.

### 7.5. Último uso

last_used_at se actualizará cuando la API key haya sido autenticada y autorizada para acceder al servicio y haya superado los controles de admisión aplicables a la operación.

Este atributo no representa necesariamente una consulta completada correctamente.

Una ejecución admitida que termine posteriormente en error o timeout podrá haber actualizado last_used_at.

No se utilizará este atributo como:

- Contador de consumo.
- Mecanismo de rate limiting.
- Registro de facturación.
- Indicador de éxito funcional.

Las fechas se almacenarán en UTC.

### 7.6. Inmutabilidad de la identidad y el rol

Una vez creada una API key, no podrán modificarse mediante los endpoints administrativos ordinarios:

- Su identificador.
- Su propietario.
- Su rol.
- Su hash.

La modificación de permisos requerirá la emisión de una nueva credencial conforme a las reglas de autorización correspondientes.

No se reasignarán claves anónimas a cuentas registradas.

## 8. Tabla conversation

Representa una conversación del asistente.

| Campo | Tipo PostgreSQL | Nullable | Restricciones |
|---|---|---|---|
| id | UUID | No | Primary Key |
| api_key_id | UUID | No | Foreign Key → api_key.id |
| created_at | TIMESTAMPTZ | No | Default fecha actual |

### 8.1. Identificador

conversation.id corresponde al thread_id utilizado por LangGraph.

La base de datos y el grafo utilizarán el mismo identificador para referirse a una conversación.

El identificador no constituye una credencial de acceso.

Los identificadores de conversaciones HTTP serán generados exclusivamente por el backend.

Se reutilizará la función existente de generación de identificadores del agente.

### 8.2. Propiedad

Una conversación pertenecerá a una única API key.

La propiedad se establecerá durante su creación y no podrá modificarse mediante los endpoints públicos.

Una API key Free o User no podrá acceder a conversaciones de otras claves, aunque pertenezcan al mismo usuario.

Una API key Admin activa podrá acceder a cualquier conversación conforme a las reglas de autorización y estado establecidas.

El acceso administrativo no modificará la propiedad de la conversación.

### 8.3. Creación

La conversación se registrará después de superar los controles aplicables de autenticación, autorización, validación y admisión, y antes de iniciar LangGraph.

Cuando thread_id=None y la consulta vaya a ejecutar el agente:

1. Generar un UUID.
2. Crear la conversación asociada a la API key correspondiente.
3. Confirmar su almacenamiento en PostgreSQL.
4. Inicializar el estado del agente.
5. Ejecutar LangGraph con el mismo identificador.

La creación de la conversación constituye una operación de persistencia independiente del almacenamiento posterior de sus mensajes.

Si no puede confirmarse la creación de la conversación, no se iniciará LangGraph.

#### Identificadores proporcionados por clientes

| Situación | Comportamiento |
|---|---|
| thread_id=None u omitido | Crear una conversación cuando proceda ejecutar LangGraph |
| UUID inválido | HTTP 422 INVALID_THREAD_ID |
| UUID válido e inexistente | HTTP 404 THREAD_NOT_FOUND |
| UUID existente pero ajeno | HTTP 404 THREAD_NOT_FOUND |
| UUID existente y autorizado | Recuperar la conversación y comprobar su estado operativo |

No se crearán conversaciones utilizando identificadores inexistentes proporcionados por clientes.

### 8.4. Respuestas anteriores a LangGraph

Las respuestas deterministas generadas antes de ejecutar LangGraph no crearán una conversación cuando todavía no exista un hilo.

Esto incluye:

- Consultas inequívocamente fuera de dominio.
- Solicitudes deterministas de aclaración.
- Imágenes identificadas como fuera de dominio.
- Imágenes cuya identificación resulte incierta.
- Rechazos de contenido no permitido.

Estas operaciones no generarán mensajes persistidos.

Cuando no exista una conversación previa, las respuestas semánticas válidas devolverán thread_id=None.

Si existe una conversación autorizada y operativamente disponible, las respuestas previas conservarán su identificador sin modificar el checkpoint ni generar mensajes SQL.

Las respuestas previas tampoco se incorporarán al historial operativo del agente.

Las restricciones de estado de una conversación existente deberán comprobarse antes de permitir estas operaciones.

### 8.5. Conversaciones sin mensajes

Una conversación podrá existir sin mensajes persistidos cuando:

- Su primer turno esté ejecutándose.
- Exista un HITL pendiente.
- La ejecución haya sufrido un fallo técnico.
- La ejecución haya superado el timeout.
- El proceso se haya reiniciado antes de resolver el turno.
- No haya podido confirmarse la persistencia del primer turno.

Estas situaciones no constituyen por sí mismas una inconsistencia relacional.

Una conversación vacía no implica necesariamente que pueda iniciarse nuevamente su estado operativo.

La existencia de una fila en PostgreSQL no garantiza la existencia de un checkpoint válido en MemorySaver.

## 9. Tabla message

Almacena los mensajes pertenecientes a los turnos del agente correctamente resueltos.

| Campo | Tipo PostgreSQL | Nullable | Restricciones |
|---|---|---|---|
| id | BIGINT | No | Primary Key, autoincremental |
| thread_id | UUID | No | Foreign Key → conversation.id |
| role | ENUM(message_role) | No | user, assistant |
| content | TEXT | No | No vacío |
| created_at | TIMESTAMPTZ | No | Default fecha actual |
| turn_number | INTEGER | No | Mayor que 0 |

### 9.1. Roles

| Rol | Contenido |
|---|---|
| user | Pregunta original del usuario correspondiente al turno |
| assistant | Respuesta del asistente y decisión HITL correspondiente |

El enumerado MessageRole representará los roles permitidos.

No se almacenarán como mensajes independientes:

- Prompts internos.
- Mensajes de sistema.
- Instrucciones del supervisor.
- Llamadas a herramientas.
- Respuestas técnicas de herramientas.
- Solicitudes de aprobación.
- Pulsaciones de botones.
- Eventos de observabilidad.
- Checkpoints.

Cada turno resuelto generará exclusivamente dos mensajes.

### 9.2. Número de turno

turn_number identifica el turno al que pertenece cada mensaje dentro de una conversación.

Su valor procederá directamente de turnos_consumidos del estado del agente después de resolver satisfactoriamente el HITL.

No se incorporará un contador SQL independiente.

No se utilizará MAX(turn_number) para determinar el número del siguiente turno.

La función preparar_nuevo_turno() del agente continuará siendo responsable de incrementar turnos_consumidos.

Se mantendrá la siguiente distinción:

| Operación | Incrementa turnos_consumidos |
|---|---|
| Inicio de un nuevo turno de LangGraph | Sí |
| Aprobación manual | No |
| Rechazo manual | No |
| Aprobación automática | No |
| Respuesta determinista previa | No |
| Identificación visual sin ejecución posterior del agente | No |
| Consulta del historial | No |

El rate limiting HTTP y las cuotas comerciales serán mecanismos independientes del contador de turnos del agente.

Los dos mensajes correspondientes al mismo turno recibirán el mismo turn_number.

Se establecerá una restricción de unicidad compuesta:

```sql
UNIQUE (thread_id, turn_number, role)
```

Esta restricción evita insertar dos mensajes con el mismo rol para un mismo turno.

No se renumerarán los turnos ya almacenados.

Una ejecución fallida podrá consumir un turno del agente sin generar mensajes persistidos. La posibilidad de continuar dependerá de que el estado operativo siga siendo consistente.

### 9.3. Orden de recuperación

Los mensajes se recuperarán ordenados por id ascendente.

El identificador autoincremental proporcionará un criterio determinista de orden dentro de cada conversación.

El mensaje user se insertará antes que el mensaje assistant dentro de la transacción correspondiente.

created_at representará el momento de almacenamiento del mensaje.

El contrato público MessageOut devolverá:

- role.
- content.
- created_at.

No será necesario exponer id ni turn_number mediante este contrato.

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

Los índices asociados a claves primarias y restricciones UNIQUE serán gestionados por PostgreSQL.

No se crearán índices adicionales redundantes.

Los índices se definirán de acuerdo con las consultas reales previstas.

## 11. Integridad referencial

No se permitirá:

- Crear una API key User o Admin sin un usuario existente.
- Crear una conversación sin una API key existente.
- Crear un mensaje sin una conversación existente.
- Reasignar una conversación a una API key diferente.
- Reasignar una API key a otro usuario.
- Cambiar el rol de una API key existente.
- Activar una clave eliminada lógicamente.
- Activar un usuario eliminado lógicamente.
- Almacenar mensajes con roles no permitidos.
- Almacenar números de turno iguales o inferiores a cero.
- Duplicar mensajes de un mismo rol y turno.

Las restricciones de integridad deberán aplicarse mediante la base de datos cuando corresponda, además de las validaciones de la aplicación.

Las claves foráneas impedirán eliminar físicamente registros que tengan dependencias.

No se configurará eliminación física en cascada durante esta primera versión.

## 12. Persistencia de turnos

### 12.1. Criterio de persistencia

Únicamente se almacenarán los turnos de LangGraph correctamente resueltos mediante aprobación o rechazo.

Se conservará el HITL obligatorio del PB02.

Una respuesta generada por LangGraph no constituirá un turno resuelto hasta que la decisión HITL se haya registrado satisfactoriamente.

| Situación | Persistir mensajes |
|---|---|
| Plan pendiente de HITL | No |
| Plan aprobado manualmente | Sí |
| Plan aprobado automáticamente | Sí |
| Plan rechazado | Sí |
| Abstención del agente con HITL resuelto | Sí |
| Aclaración del agente con HITL resuelto | Sí |
| Respuesta determinista anterior a LangGraph | No |
| Imagen fuera de dominio antes de LangGraph | No |
| Imagen de identificación incierta antes de LangGraph | No |
| Imagen con contenido no permitido | No |
| Fallo técnico | No |
| Petición HTTP inválida | No |
| Petición no autorizada | No |
| Cuota agotada | No |
| Capacidad de ejecución agotada | No |
| Timeout | No |
| Resultado tardío después de un timeout | No |

La comprobación de pendiente_hitl=False no será suficiente por sí sola para autorizar la persistencia.

También deberá comprobarse que:

- El turno se ha ejecutado realmente en LangGraph.
- El HITL se ha resuelto correctamente.
- La decisión registrada es coherente.
- El checkpoint resultante es válido.
- El estado no contiene errores técnicos.
- El turno corresponde a la operación actual.
- La respuesta satisface el contrato de salida.
- La operación no ha superado el timeout.
- La autorización necesaria continúa siendo válida.

El atributo done no se utilizará como único criterio de persistencia.

Un turno rechazado podrá estar resuelto aunque la conversación continúe abierta.

### 12.2. Obtención del contenido del turno

Se reutilizará el historial operativo generado por la función registrar_turno() del agente.

El contrato existente RegistroTurno contiene:

- pedido.
- respuesta.
- plan.
- aprobado.

La función registrar_turno() se ejecuta antes de retirar los datos de un plan rechazado.

Esto permite recuperar la propuesta original incluso cuando el nodo aplicar sustituye la respuesta visible tras un rechazo.

La capa de servicios verificará que el registro recuperado corresponde al turno que acaba de resolverse.

No utilizará registros de turnos anteriores como contenido del turno actual.

#### Mensaje user

El contenido procederá del campo pedido del RegistroTurno correspondiente.

Este campo deberá conservar la pregunta original del usuario.

No se almacenará como pregunta una reformulación interna del supervisor o de los especialistas.

#### Mensaje assistant

El contenido incluirá la respuesta correspondiente al turno y una indicación textual determinista de la decisión HITL.

Para un turno aprobado:

- Se conservará la respuesta definitiva del asistente.
- Se indicará que el plan fue aprobado.

Para un turno rechazado:

- Se conservará la respuesta originalmente presentada al usuario.
- Se indicará expresamente que el plan fue rechazado.
- Se conservará, cuando corresponda, el mensaje final de rechazo y reformulación.

La indicación de aprobación o rechazo será añadida por Python, no generada por Gemini.

No se presentará una propuesta rechazada como una propuesta aprobada.

La aprobación de un plan representa una decisión sobre la propuesta, no una verificación adicional de la exactitud documental ni una ejecución física de las acciones recomendadas.

No será necesario añadir una columna plan_aprobado a la tabla message.

Tampoco se almacenará un tercer mensaje para representar la decisión HITL.

#### Ejemplo de turno aprobado

Mensaje user:

```text
¿Dónde puedo reciclar unas pilas?
```

Mensaje assistant:

```text
Las pilas deben depositarse en puntos de recogida específicos.

Decisión HITL: plan aprobado.
```

#### Ejemplo de turno rechazado

Mensaje user:

```text
¿Dónde puedo reciclar unas pilas?
```

Mensaje assistant:

```text
Las pilas deben depositarse en puntos de recogida específicos.

Decisión HITL: plan rechazado.

Plan rechazado. Puedes reformular tu consulta.
```

Los ejemplos representan únicamente el formato de persistencia.

La respuesta real deberá proceder del agente y de las evidencias autorizadas.

### 12.3. Transacción

El almacenamiento de un turno comprenderá dos inserciones:

1. Mensaje user.
2. Mensaje assistant.

Ambas inserciones se realizarán dentro de la misma transacción SQL.

Los dos registros compartirán:

- thread_id.
- turn_number.

La persistencia deberá completarse antes de devolver una respuesta HTTP satisfactoria correspondiente a un turno resuelto.

Si una inserción falla antes de confirmar la transacción, se ejecutará rollback.

No deberán quedar turnos parcialmente persistidos.

```mermaid
flowchart TD
    A[Turno HITL resuelto] --> B[Validar resultado y autorización]
    B --> C[Preparar ambos mensajes]
    C --> D[Iniciar transacción SQL]
    D --> E[Insertar mensaje user]
    E --> F[Insertar mensaje assistant]
    F --> G{Commit correcto}
    G -->|Sí| H[HTTP 200 AskOut]
    G -->|No| I[Gestionar fallo de persistencia]
    I --> J[ErrorOut]
```

El contrato público deberá validarse antes de confirmar la persistencia siempre que sea posible, evitando guardar un turno cuya representación pública sea incompatible con el contrato HTTP.

### 12.4. Prevención de duplicados

La restricción UNIQUE de la tabla message impedirá insertar más de un mensaje por rol y turno.

La capa de servicios comprobará adicionalmente:

- El estado real del agente.
- La identidad de la aprobación resuelta.
- La correspondencia entre el turno actual y el registro obtenido.
- La ausencia de modificaciones concurrentes.

Se utilizarán bloqueos por thread_id conforme a la especificación de robustez.

La restricción de unicidad no convierte automáticamente los endpoints en operaciones idempotentes.

Una petición de aprobación repetida deberá rechazarse conforme al estado real de la conversación.

No deberá generar otro par de mensajes.

### 12.5. Fallo de persistencia

Si LangGraph resuelve correctamente un turno pero PostgreSQL no puede almacenarlo, FastAPI devolverá un error técnico conforme al contrato HTTP.

| Situación | HTTP |
|---|---|
| Fallo interno inesperado de persistencia | 500 |
| PostgreSQL temporalmente indisponible | 503 |

Se ejecutará rollback cuando corresponda.

No se devolverá una respuesta satisfactoria que declare como persistido un turno cuya persistencia no pueda confirmarse.

Cuando una interrupción de la conexión impida determinar el resultado de un commit, no se asumirá automáticamente que la transacción se ha revertido.

La operación se tratará como un resultado de persistencia no confirmado.

No se repetirá automáticamente la escritura.

Si el fallo de persistencia provoca una inconsistencia entre el checkpoint y la base de datos, o impide garantizar su consistencia, la conversación quedará marcada internamente como no reutilizable.

Los intentos posteriores de continuar una conversación afectada devolverán:

```text
HTTP 409 THREAD_STATE_LOST
```

El historial anteriormente confirmado permanecerá disponible.

No existe una transacción atómica compartida entre MemorySaver y PostgreSQL.

### 12.6. Timeout y resultados tardíos

El timeout de ThreadPoolExecutor no garantiza que una función que ya está ejecutándose se detenga.

Por tanto, la finalización tardía de una ejecución no autorizará por sí sola la escritura de mensajes en PostgreSQL.

El worker responsable de ejecutar el agente no realizará la persistencia definitiva de los mensajes del turno.

La escritura de los mensajes se realizará desde el flujo de servicio autorizado después de recuperar y validar satisfactoriamente el resultado dentro del presupuesto temporal.

La persistencia deberá respetar el bloqueo de la conversación.

Cuando se comunique HTTP 504:

- No se guardarán los mensajes del turno fallido.
- No se aceptará posteriormente un resultado tardío como turno satisfactorio.
- No se iniciará una persistencia diferida del turno.
- No se liberarán prematuramente los recursos todavía utilizados por el worker.
- No se permitirá continuar desde un estado cuya consistencia no pueda garantizarse.

Podrá existir una fila conversation sin mensajes si fue creada antes de que la ejecución terminara en timeout.

La ausencia de mensajes no autoriza reconstruir automáticamente el estado perdido.

Las operaciones SQL tendrán sus propios límites de espera.

El presupuesto del agente y el tiempo necesario para la confirmación de una transacción SQL constituyen controles diferenciados.

### 12.7. Revocación de credenciales durante una ejecución

Antes de persistir el resultado de una ejecución admitida, se comprobarán nuevamente las condiciones de autorización aplicables.

Cuando la credencial haya sido desactivada o eliminada durante la ejecución, no se iniciará una nueva persistencia del turno que ya no esté autorizado.

La comprobación final de autorización y las escrituras correspondientes deberán protegerse frente a modificaciones administrativas concurrentes mediante transacciones y los bloqueos necesarios.

La revocación no garantiza que una llamada externa ya iniciada se detenga inmediatamente.

Si el agente ha modificado su checkpoint pero el turno no puede persistirse por pérdida de autorización, se impedirá su reutilización cuando no pueda garantizarse la consistencia.

## 13. Gestión de la conexión

### 13.1. Variables de entorno

DATABASE_URL se obtendrá del entorno.

Ejemplo de desarrollo local:

```text
postgresql://usuario:password@localhost:5432/reciclatia
```

Los valores reales nunca se incorporarán al repositorio.

Cuando Render proporcione una URL con el prefijo postgres://, se normalizará al prefijo postgresql://.

Se utilizará el driver de PostgreSQL establecido para el proyecto.

### 13.2. Engine

Se creará un engine de SQLModel compartido durante la vida del backend.

El engine gestionará las conexiones y su reutilización.

No se creará un engine por petición.

La configuración de conexión deberá disponer de límites de espera razonables.

Los errores del motor se tratarán conforme al catálogo de errores HTTP.

### 13.3. Session

Cada operación o unidad de trabajo tendrá su propia Session.

Las sesiones:

- No se compartirán entre hilos de ejecución.
- No se compartirán entre usuarios.
- No se reutilizarán después de cerrarse.
- Se cerrarán correctamente tras completar las operaciones.
- Ejecutarán rollback cuando corresponda.

No se mantendrá abierta una transacción SQL durante una llamada prolongada al agente o a Gemini si no resulta necesaria.

La creación de una conversación y la persistencia de sus mensajes serán operaciones diferenciadas.

### 13.4. Creación de tablas

FastAPI ejecutará la creación de tablas durante su ciclo de inicio mediante:

```python
SQLModel.metadata.create_all(engine)
```

Los modelos deberán estar importados antes de ejecutar create_all.

create_all creará las tablas inexistentes, pero no modificará automáticamente la estructura de tablas ya creadas.

Alembic y las migraciones automatizadas quedan fuera del alcance inicial.

No se eliminarán tablas existentes ni se recrearán destructivamente durante un inicio ordinario del servicio.

### 13.5. Independencia del núcleo

La configuración de PostgreSQL será obligatoria para ejecutar FastAPI.

No será obligatoria para:

- Importar el RAG.
- Ejecutar la CLI independiente.
- Reconstruir ChromaDB.
- Ejecutar pruebas unitarias independientes del backend.

El núcleo del asistente no deberá importar FastAPI ni depender de una conexión activa a PostgreSQL.

### 13.6. Comprobación de disponibilidad

GET /health verificará las condiciones de disponibilidad establecidas para PostgreSQL y los demás componentes imprescindibles.

La existencia de un engine no demuestra por sí sola que PostgreSQL esté disponible.

Cuando corresponda, se realizará una comprobación real de conexión.

No se devolverá status=ok cuando la base de datos requerida no esté disponible.

La comprobación de salud no ejecutará Gemini.

## 14. Operaciones de persistencia

### 14.1. Usuarios

- Crear usuario.
- Buscar usuario por email.
- Buscar usuario por identificador.
- Listar usuarios.
- Actualizar contraseña.
- Activar o desactivar usuario.
- Eliminar usuario lógicamente.

### 14.2. API keys

- Registrar nueva API key.
- Buscar API key mediante su hash.
- Buscar API key mediante su identificador.
- Listar claves de un usuario.
- Listar claves como administrador.
- Contar claves activas de un usuario según su rol.
- Actualizar last_used_at.
- Activar o desactivar una clave.
- Eliminar una clave lógicamente.

### 14.3. Conversaciones

- Crear conversación.
- Recuperar conversación mediante thread_id.
- Recuperar conversación verificando api_key_id.
- Listar conversaciones de una API key.
- Listar conversaciones como administrador.

### 14.4. Mensajes

- Persistir un turno completo.
- Recuperar mensajes de una conversación.
- Comprobar si un turno ya está almacenado.

La capa de persistencia se responsabilizará del acceso a los datos.

La capa de servicios y seguridad determinará si una operación está autorizada.

Las operaciones de lectura de historial no invocarán LangGraph, Gemini ni las herramientas.

Las operaciones de lectura no reconstruirán checkpoints.

## 15. Desactivación y eliminación

### 15.1. Desactivación de una API key

- api_key.is_active=False.
- api_key.deleted_at permanece en NULL.
- Se conservan la clave, sus conversaciones y sus mensajes.
- Se impide su utilización como credencial activa.
- Su propietario puede consultar el historial autorizado mediante una sesión válida.
- La clave puede reactivarse mediante una operación administrativa autorizada.

Una operación de desactivación no podrá borrar una fecha de eliminación ya establecida.

### 15.2. Reactivación de una API key

La reactivación de una clave exigirá:

- Una operación administrativa autorizada.
- Que la clave no esté eliminada lógicamente.
- Que su propietario, cuando exista, sea un usuario activo y no eliminado.
- Que se respeten los límites de claves activas correspondientes al rol.

Se comprobarán los límites dentro de una operación protegida frente a concurrencia.

Si se ha alcanzado el límite de claves activas, se devolverá:

```text
HTTP 409 API_KEY_LIMIT_REACHED
```

Si se intenta reactivar una clave eliminada, se devolverá:

```text
HTTP 409 API_KEY_DELETED
```

La reactivación no restaurará automáticamente checkpoints perdidos.

Tampoco reiniciará deliberadamente los contadores de consumo existentes en memoria.

### 15.3. Eliminación de una API key

Se aplicará eliminación lógica.

- api_key.is_active=False.
- api_key.deleted_at recibe la fecha de eliminación.
- Se conservan las referencias y los mensajes.
- La clave deja de estar disponible para su utilización ordinaria.
- No podrá reactivarse mediante las operaciones administrativas normales.
- El acceso ordinario al historial de claves eliminadas queda reservado al administrador.

No se devolverá la API key original ni su hash durante la eliminación.

### 15.4. Desactivación de un usuario

- user.is_active=False.
- user.deleted_at permanece en NULL.
- Se impide la autenticación del usuario.
- Se impide el uso de todas las API keys vinculadas al usuario.
- Se invalidan las sesiones existentes.
- Se conserva la información almacenada.

No será necesario modificar individualmente el estado de cada API key.

La autorización comprobará tanto el estado de la clave como el estado de su propietario.

Una operación de desactivación no podrá borrar una fecha de eliminación ya establecida.

### 15.5. Reactivación de un usuario

Una cuenta desactivada podrá reactivarse mediante una operación administrativa autorizada, siempre que no esté eliminada lógicamente.

La reactivación:

- Establecerá user.is_active=True.
- No modificará individualmente el estado de las API keys.
- No restaurará sesiones previamente invalidadas.
- No reactivará claves que hubiesen sido desactivadas individualmente.
- No restaurará checkpoints perdidos.

Si se intenta reactivar un usuario eliminado, se devolverá:

```text
HTTP 409 USER_DELETED
```

### 15.6. Eliminación de un usuario

Se aplicará eliminación lógica.

- user.is_active=False.
- user.deleted_at recibe la fecha de eliminación.
- Se invalidan las sesiones del usuario.
- Las API keys asociadas quedan inutilizables.
- Se conservan las conversaciones y los mensajes para mantener la integridad referencial.

No se realizará una eliminación física en cascada.

### 15.7. Alcance de la eliminación lógica

La eliminación lógica es una decisión funcional de esta primera versión.

No constituye un mecanismo de supresión definitiva de datos personales.

Antes de una futura explotación comercial deberán definirse los procedimientos correspondientes de:

- Retención de información.
- Acceso a datos personales.
- Anonimización.
- Supresión definitiva.
- Borrado seguro.
- Gestión de copias de seguridad.

## 16. PostgreSQL frente a MemorySaver

### 16.1. Responsabilidades

| Información | Almacenamiento |
|---|---|
| Usuarios | PostgreSQL |
| Hashes de API keys | PostgreSQL |
| Propiedad de conversaciones | PostgreSQL |
| Historial de mensajes | PostgreSQL |
| Estado operativo de LangGraph | MemorySaver |
| Checkpoints | MemorySaver |
| HITL pendiente | MemorySaver |
| approval_id pendiente | MemorySaver |
| Contexto de revisión | MemorySaver |
| Sesiones de autenticación | Memoria del backend |
| Contadores HTTP y comerciales | Memoria del backend |
| Índice vectorial | ChromaDB |
| Archivos de imagen recibidos | Almacenamiento temporal |

No se almacenarán checkpoints de LangGraph en PostgreSQL.

Esta funcionalidad queda fuera del alcance académico del PB03.

### 16.2. Reinicio y redeploy

Después de un reinicio del backend:

- Los usuarios permanecerán almacenados.
- Las API keys permanecerán almacenadas.
- Las conversaciones permanecerán almacenadas.
- Los mensajes confirmados permanecerán almacenados.
- Los checkpoints de MemorySaver se perderán.
- Las aprobaciones pendientes se perderán.
- Los tokens de sesión dejarán de ser válidos.
- Los contadores mantenidos en memoria se reiniciarán.

Una API key original podrá seguir utilizándose si continúa siendo válida y está autorizada.

Un usuario autenticado mediante sesión deberá iniciar sesión nuevamente.

La recuperación de mensajes no dependerá de la existencia de un checkpoint.

### 16.3. Conversaciones sin estado operativo

Cuando una conversación exista en PostgreSQL pero una operación requiera un checkpoint perdido o no reutilizable, se devolverá:

```text
HTTP 409 THREAD_STATE_LOST
```

No se reconstruirá automáticamente el estado de LangGraph utilizando los mensajes SQL.

No se inicializará un nuevo checkpoint con el mismo thread_id para sustituir silenciosamente uno perdido.

El usuario podrá consultar su historial autorizado e iniciar una nueva conversación.

### 16.4. Pérdida de una respuesta HTTP

Si el cliente pierde la respuesta de una operación, el historial SQL podrá contener o no los mensajes del turno correspondiente, dependiendo de si se confirmó la persistencia.

La ausencia de mensajes no permite determinar inequívocamente si:

- La consulta no se ejecutó.
- La consulta continúa ejecutándose.
- Existe un HITL pendiente.
- La ejecución falló.
- Se perdió el estado operativo.

La consulta del historial no se utilizará como mecanismo automático de recuperación del checkpoint.

No se implementarán mecanismos adicionales de idempotencia HTTP durante el PB03.

### 16.5. Alcance del historial persistente

PostgreSQL conservará los turnos del agente correctamente resueltos.

No conservará necesariamente todas las interacciones visibles durante una sesión de Streamlit.

En particular, las respuestas deterministas anteriores a LangGraph podrán mostrarse durante la sesión sin formar parte del historial SQL.

Esta distinción es deliberada y permite reutilizar el modelo de turnos existente.

El historial persistente tampoco constituye una copia completa de:

- Las herramientas ejecutadas.
- Las imágenes adjuntas.
- Los mapas presentados.
- Las estructuras de evidencia.
- Los checkpoints.
- Los planes pendientes.

La recuperación del historial no deberá prometer la reconstrucción exacta de todos los elementos visuales de una sesión anterior.

## 17. Privacidad y minimización de datos

No se almacenarán permanentemente como datos independientes del historial:

- Contraseñas originales.
- API keys originales.
- Tokens de sesión originales.
- Archivos binarios de imágenes recibidas.
- Rutas temporales del servidor.
- Coordenadas privadas proporcionadas mediante atributos específicos de la consulta.
- Prompts internos del agente.
- Checkpoints completos.
- Trazas internas de herramientas.
- Embeddings de las consultas personales del consumidor.

Las preguntas y respuestas almacenadas podrán contener información introducida voluntariamente por el usuario o información relacionada con la consulta.

Los mensajes podrán incluir direcciones, referencias documentales o información geográfica necesaria para representar el resultado.

Los mensajes no se incorporarán automáticamente al corpus documental.

No se utilizarán los datos de conversaciones para reconstruir ChromaDB.

La información almacenada deberá limitarse a la necesaria para el funcionamiento del producto.

## 18. Criterios de aceptación

### 18.1. Infraestructura y modelos

- PostgreSQL funciona tanto en desarrollo local como en Render.
- Las tablas se crean correctamente durante el inicio de FastAPI.
- Los modelos respetan las restricciones de integridad referencial.
- Los roles de las API keys están restringidos mediante api_key_role.
- Los roles de los mensajes están restringidos mediante message_role.
- No existen emails normalizados duplicados.
- No existen hashes de API keys duplicados.
- No se almacenan secretos originales.
- No se utiliza SQLite como respaldo silencioso de PostgreSQL.

### 18.2. Usuarios y API keys

- Las claves Free pueden asociarse a consumidores anónimos o registrados.
- Las claves User y Admin requieren un usuario asociado.
- No pueden generarse claves Admin mediante endpoints ordinarios.
- No puede modificarse el propietario de una clave existente.
- No puede modificarse el rol de una clave existente.
- Las claves desactivadas conservan su historial.
- Las claves eliminadas no pueden reactivarse.
- Los usuarios eliminados no pueden reactivarse.
- La emisión y reactivación respetan los límites de claves activas.
- Las operaciones concurrentes no permiten superar dichos límites.
- Desactivar un usuario impide utilizar sus claves sin modificar individualmente su estado.

### 18.3. Conversaciones

- El backend genera los identificadores de conversaciones.
- PostgreSQL y LangGraph utilizan el mismo thread_id.
- Un UUID inexistente proporcionado por un cliente no crea una conversación.
- Cada conversación pertenece a una única API key.
- Dos claves del mismo usuario no comparten conversaciones.
- Las respuestas anteriores a LangGraph no crean conversaciones innecesarias.
- Una conversación vacía no se confunde con un checkpoint disponible.

### 18.4. Turnos e historial

- Las ejecuciones satisfactorias de LangGraph conservan el HITL obligatorio.
- Los turnos pendientes de HITL no generan mensajes persistidos.
- Los turnos aprobados generan exactamente dos mensajes.
- Los turnos rechazados generan exactamente dos mensajes.
- Las respuestas anteriores a LangGraph no generan mensajes persistidos.
- turn_number procede de turnos_consumidos.
- Aprobar o rechazar no incrementa turnos_consumidos.
- La respuesta original se conserva cuando se rechaza un plan.
- El historial distingue las propuestas aprobadas de las rechazadas.
- Los mensajes se recuperan en orden determinista.
- Las lecturas de historial no ejecutan el agente.

### 18.5. Atomicidad y robustez

- Los dos mensajes de un turno se almacenan mediante una única transacción.
- No quedan turnos parcialmente almacenados.
- No se duplican mensajes al repetir una aprobación.
- No se devuelve HTTP 200 cuando falla una persistencia obligatoria.
- No se devuelve HTTP 201 cuando no puede confirmarse la creación del recurso.
- Un fallo de persistencia no elimina el historial anteriormente confirmado.
- Los resultados tardíos después de un timeout no generan mensajes.
- No se permite continuar una conversación desde un checkpoint inconsistente.
- Los errores de PostgreSQL respetan el contrato ErrorOut.
- GET /health no declara disponibilidad cuando PostgreSQL está indisponible.

### 18.6. Reinicio y redeploy

- El historial permanece disponible después de reiniciar FastAPI.
- El historial permanece disponible después de un redeploy en Render.
- La pérdida de MemorySaver no elimina los mensajes almacenados.
- La pérdida de sesiones no elimina usuarios ni API keys.
- No se reconstruyen checkpoints a partir del historial SQL.
- Las operaciones que necesitan un checkpoint perdido devuelven THREAD_STATE_LOST.
- La pérdida de una respuesta HTTP no provoca reintentos automáticos de escritura.

### 18.7. Independencia y regresión

- La capa RAG puede seguir utilizándose sin PostgreSQL.
- La CLI puede seguir ejecutándose independientemente del backend.
- La reconstrucción de ChromaDB no depende de PostgreSQL.
- Los modelos relacionales no introducen dependencias HTTP en el núcleo.
- Se mantienen los comportamientos del PB02 que no hayan sido modificados expresamente.
- Las pruebas de regresión continúan superándose o se actualizan justificadamente cuando cambia un contrato autorizado.