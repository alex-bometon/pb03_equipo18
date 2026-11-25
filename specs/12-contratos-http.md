# 12. Contratos HTTP

## 1. Objetivo

Definir el contrato de comunicación entre los clientes de ReciclaTÍA y el backend FastAPI.

La API será responsable de:

- Validar las peticiones.
- Autenticar las credenciales.
- Comprobar los permisos.
- Verificar la propiedad de los recursos.
- Aplicar los controles de consumo y admisión.
- Ejecutar el asistente.
- Resolver el HITL cuando corresponda.
- Persistir los turnos resueltos.
- Devolver respuestas estructuradas.
- Comunicar los errores mediante códigos HTTP adecuados.

Los clientes no podrán modificar directamente el estado de LangGraph.

## 2. Convenciones generales

- API REST sobre HTTP en desarrollo y HTTPS en producción.
- JSON como formato principal de intercambio.
- Multipart/form-data para el envío de imágenes.
- UTF-8 como codificación de caracteres.
- UUID como identificador de conversaciones, usuarios, API keys y aprobaciones pendientes.
- Fechas almacenadas en UTC y serializadas en formato ISO 8601.
- Validación mediante Pydantic.
- Códigos de estado HTTP coherentes con el resultado de cada operación.
- Credenciales transmitidas mediante cabeceras HTTP.
- Separación entre modelos públicos y modelos relacionales.
- Validación de los resultados internos antes de construir una respuesta pública.

Los identificadores UUID se representarán como cadenas en JSON.

Las respuestas públicas no expondrán secretos, rutas internas, checkpoints completos ni excepciones sin sanitizar.

Un fallo técnico no se devolverá como una respuesta HTTP 200 con un campo de error relleno.

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

Identifica a un usuario autenticado para operaciones relacionadas con su cuenta, generación de API keys y consulta del historial autorizado.

El token de sesión será opaco y tendrá caducidad.

No se utilizarán JWT ni OAuth durante esta primera versión.

### 3.3. Roles de API key

| Rol | Usuario obligatorio | Consultas de texto | Consultas con imagen |
|---|---|---|---|
| free | Opcional | Sí | No |
| user | Sí | Sí | Sí |
| admin | Sí, procedimiento restringido | Sí | Sí |

El rol pertenece a la API key y se determina exclusivamente en el backend.

El registro de un usuario no implica automáticamente la asignación del rol User.

Las API keys Admin únicamente podrán generarse mediante procedimientos internos restringidos.

### 3.4. Autenticación mediante sesión y selección de API key

Los usuarios registrados podrán utilizar una API key propia mediante las siguientes cabeceras:

```http
Authorization: Bearer <session_token>
X-API-Key-Id: <api_key_id>
```

El backend comprobará:

- La validez de la sesión.
- El estado del usuario autenticado.
- La existencia de la API key.
- Que api_key.user_id coincida con user.id.
- Que api_key.is_active=True.
- Que api_key.deleted_at sea NULL.
- Que el rol permita ejecutar la operación solicitada.

Esta modalidad estará disponible para las claves Free registradas y User.

Las claves Admin requieren siempre la credencial original mediante X-API-Key.

No se permitirá combinar una API key original con la modalidad de autenticación mediante sesión y selección de clave.

La combinación de credenciales incompatibles devolverá HTTP 422 AMBIGUOUS_CREDENTIALS.

## 4. Cuotas

| Rol | Por minuto | Por hora | Por 24 horas |
|---|---:|---:|---:|
| free | 2 | 10 | 30 |
| user | 5 | 20 | 45 |
| admin | Sin límite comercial | Sin límite comercial | Sin límite comercial |

Las cuotas se aplicarán individualmente a cada API key mediante ventanas temporales deslizantes.

POST /ask y POST /ask/image compartirán los mismos contadores.

POST /approve resuelve un turno previamente iniciado y no consume una nueva consulta comercial.

Las operaciones HTTP estarán sujetas a un limitador general independiente de las cuotas comerciales del asistente.

El administrador estará sujeto a los límites técnicos de seguridad, concurrencia y ejecución.

Los criterios de admisión y contabilización se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

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

Los endpoints públicos de registro e inicio de sesión estarán sujetos a los controles específicos de seguridad definidos en la especificación de robustez.

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

- X-API-Key: credencial original.
- Authorization y X-API-Key-Id: sesión válida y selección de una clave propia, exclusivamente para claves Free registradas y User.

El rol Free puede crear y continuar conversaciones propias y resolver su HITL.

El consumidor Free anónimo no dispone de acceso al historial persistente.

El consumidor Free registrado puede consultar su historial mediante los endpoints autenticados por sesión definidos en el apartado 5.4.

El rol User únicamente puede acceder a las conversaciones de la API key utilizada en la petición.

El rol Admin puede acceder a cualquier conversación, respetando las restricciones de estado, concurrencia y aprobación.

### 5.3. Endpoints de cuenta

Requieren una sesión de usuario válida.

| Método | Ruta | Responsabilidad |
|---|---|---|
| POST | /auth/logout | Invalidar la sesión |
| GET | /auth/me | Consultar el usuario autenticado |
| PATCH | /auth/password | Modificar la contraseña |
| POST | /api-keys | Generar una API key Free o User según los permisos |
| GET | /api-keys | Listar las claves propias |
| GET | /api-keys/{api_key_id} | Consultar una clave propia |

El backend determinará los roles que el usuario está autorizado a solicitar.

El rol Admin no podrá asignarse mediante estos endpoints.

Las claves eliminadas lógicamente no estarán disponibles mediante las operaciones ordinarias de consulta.

### 5.4. Historial mediante sesión

| Método | Ruta |
|---|---|
| GET | /api-keys/{api_key_id}/threads |
| GET | /api-keys/{api_key_id}/threads/{thread_id} |
| GET | /api-keys/{api_key_id}/threads/{thread_id}/messages |

Estas operaciones permiten a los usuarios registrados consultar el historial de sus API keys Free y User, incluso cuando están desactivadas.

Las API keys eliminadas lógicamente quedan excluidas.

FastAPI verificará la propiedad de la clave y de la conversación.

Son operaciones exclusivamente de lectura.

La consulta del historial no permitirá reconstruir ni modificar el checkpoint de LangGraph.

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

La generación de API keys Admin no estará disponible mediante ningún endpoint.

Las claves administrativas se emitirán mediante un procedimiento interno de aprovisionamiento restringido.

La eliminación de usuarios y API keys será lógica, conforme a [13-persistencia.md](13-persistencia.md) y [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

## 6. Contratos Pydantic del asistente

### 6.1. UbicacionIn

| Campo | Tipo | Obligatorio | Restricción |
|---|---|---|---|
| latitud | float | Sí | Entre -90 y 90 |
| longitud | float | Sí | Entre -180 y 180 |

Ambas coordenadas deberán ser números finitos.

No se admitirán valores booleanos como coordenadas.

La ubicación será proporcionada voluntariamente por el consumidor.

Inicialmente se utilizarán coordenadas manuales.

La geolocalización del navegador queda como ampliación opcional.

FastAPI construirá el objeto de ubicación que consume el agente.

No se inventarán coordenadas ni se realizará geocodificación automática.

### 6.2. AskIn

| Campo | Tipo | Obligatorio | Default |
|---|---|---|---|
| pregunta | str | Sí | — |
| thread_id | str o None | No | None |
| auto_aprobar | bool | No | True |
| ubicacion | UbicacionIn o None | No | None |
| max_steps | int o None | No | None |

#### Reglas de validación

- pregunta deberá ser una cadena.
- Se eliminarán los espacios iniciales y finales.
- Si la pregunta queda vacía después de aplicar strip(), se devolverá HTTP 400 EMPTY_QUESTION.
- La longitud máxima de la pregunta será de 500 caracteres.
- Una pregunta que supere el límite devolverá HTTP 422 QUESTION_TOO_LONG.
- thread_id, cuando se proporciona, deberá ser un UUID válido.
- max_steps deberá estar comprendido entre 1 y 4.
- max_steps=None utilizará la configuración vigente del agente.
- auto_aprobar deberá representar una decisión booleana válida.
- Streamlit enviará explícitamente auto_aprobar=False.
- Swagger podrá utilizar auto_aprobar=True.

La validación de pregunta vacía se realizará como una regla de negocio, diferenciándola del incumplimiento estructural del modelo Pydantic.

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
| thread_id | str o None | Identificador de conversación |
| respuesta | str | Resultado válido del agente o respuesta determinista previa |
| plan | list[str] | Plan generado por el agente |
| plan_aprobado | bool o None | Decisión HITL |
| done | bool | Estado de finalización de la conversación |
| pendiente_hitl | bool | Checkpoint real de LangGraph |
| fuentes | list[FuenteOut] | Referencias documentales autorizadas |
| geografia | list[GeografiaOut] | Evidencias geográficas transformadas |
| abstencion | bool | Resultado semántico |
| motivo | str o None | Motivo de abstención o aclaración |
| estado_evidencia | Literal | suficiente, parcial, insuficiente |
| limitaciones | list[str] | Limitaciones verificables del resultado |
| turnos_consumidos | int | Contador de turnos iniciados en LangGraph |
| error | str o None | Siempre None en respuestas HTTP satisfactorias |
| approval_id | str o None | UUID de la aprobación pendiente |

#### Invariantes

- respuesta deberá ser una cadena no vacía.
- turnos_consumidos será un entero mayor o igual que cero.
- approval_id únicamente tendrá valor cuando exista una aprobación HITL pendiente.
- pendiente_hitl deberá corresponder al checkpoint real.
- done=True implicará que la conversación ha finalizado tras una aprobación válida.
- Una aprobación pendiente no podrá coexistir con done=True.
- Los fallos técnicos se devolverán mediante ErrorOut y un código HTTP no satisfactorio.
- No se serializará directamente la totalidad de EstadoProducto.

FastAPI validará el resultado antes de construir AskOut.

La ausencia de fuentes documentales no constituye por sí sola un error cuando el resultado es una abstención legítima o utiliza exclusivamente evidencias autorizadas de otra naturaleza.

#### Respuesta sin conversación creada

Cuando la petición se resuelva mediante un filtro previo y todavía no exista una conversación del agente:

- thread_id=None.
- plan=[].
- plan_aprobado=None.
- done=False.
- pendiente_hitl=False.
- approval_id=None.
- turnos_consumidos=0.
- fuentes=[].
- geografia=[].
- abstencion=True.
- estado_evidencia=insuficiente.
- error=None.

No se creará una conversación ni se persistirán mensajes por esta operación.

Cuando exista previamente una conversación autorizada y disponible, se conservará su identificador y su contador de turnos sin modificar el checkpoint.

### 6.4. FuenteOut

Representa una referencia documental utilizada durante el turno.

| Campo | Tipo | Obligatorio |
|---|---|---|
| chunk_id | str | Sí |
| source | str | Sí |
| url | HttpUrl o None | No |
| rol | Literal residuos, puntos o None | No |
| id_llamada | str o None | No |

chunk_id y source deberán contener valores no vacíos.

#### Procedencia autorizada

Las referencias documentales procederán exclusivamente de:

- Documentos recuperados del corpus.
- Referencias normativas previamente incorporadas y autorizadas en el núcleo del asistente.

Las URL oficiales se obtendrán mediante un catálogo estático que relacione los documentos autorizados con sus fuentes de origen.

No se utilizará Gemini para generar enlaces.

La transformación de una referencia en una URL no realizará peticiones externas.

La API ArcGIS constituirá la fuente autorizada de los resultados geográficos y se identificará mediante GeografiaOut.

No se permitirán búsquedas abiertas en Internet ni consultas a fuentes documentales externas adicionales.

#### Restricciones

- No exponer rutas locales.
- No exponer embeddings.
- No exponer el contenido completo de los chunks.
- No inventar identificadores documentales.
- No inventar nombres de fuentes.
- No inventar enlaces.
- No considerar chunk_id como identificador globalmente único.

Los identificadores de cita C1, C2 y sucesivos tienen alcance local dentro de cada llamada al RAG.

Cuando estén disponibles, rol e id_llamada permitirán distinguir su ámbito de procedencia.

No se eliminarán referencias únicamente porque compartan el mismo chunk_id.

Una referencia documental legítima sin URL autorizada podrá devolver url=None.

Una referencia inventada, incoherente o incompatible con el contrato deberá tratarse como un fallo técnico.

#### Ejemplo

```json
{
    "chunk_id": "C1",
    "source": "tipos_residuos.csv",
    "url": "https://datos.madrid.es/dataset/300199-0-tipo-residuo",
    "rol": "residuos",
    "id_llamada": "directo-1"
}
```

### 6.5. PuntoLimpioOut

Representa un registro geográfico individual devuelto por la herramienta autorizada.

| Campo | Tipo | Obligatorio |
|---|---|---|
| tipo | str | Sí |
| direccion | str | Sí |
| distrito | str o None | No |
| latitud | float | Sí |
| longitud | float | Sí |
| distancia_metros | float | Sí |
| horario_apertura | str o None | No |
| horario_cierre | str o None | No |
| dia_semana | str o None | No |
| turno | str o None | No |
| documento_origen | str o None | No |

#### Validación

- tipo y direccion deberán contener valores no vacíos.
- latitud deberá encontrarse entre -90 y 90.
- longitud deberá encontrarse entre -180 y 180.
- Las coordenadas deberán ser finitas.
- distancia_metros deberá ser finita y mayor o igual que cero.
- Los campos documentales opcionales podrán contener None.
- La ausencia de un horario no se interpretará como disponibilidad permanente.

Las coordenadas representan ubicaciones públicas de instalaciones municipales, no la ubicación privada del consumidor.

Las distancias corresponden a distancias geográficas en línea recta.

No representan distancias por carretera ni tiempos de desplazamiento.

No se incluirá un atributo que afirme la apertura física de una instalación.

### 6.6. GeografiaOut

Representa una búsqueda geográfica realizada mediante la herramienta autorizada.

| Campo | Tipo | Restricción |
|---|---|---|
| fuente | Literal | api, corpus_local |
| tipo_solicitado | Literal | todos, fijo, movil, proximidad |
| radio_metros | int | Entre 1 y 5000 |
| total_encontrados | int | Mayor o igual que cero |
| puntos | list[PuntoLimpioOut] | Máximo 10 registros |
| aviso | str o None | Aviso asociado a la procedencia |

#### Reglas

- total_encontrados representa los registros válidos encontrados dentro del radio.
- puntos contiene el subconjunto de registros más próximos devuelto por la herramienta.
- La longitud de puntos no podrá superar total_encontrados.
- Cuando total_encontrados sea cero, puntos deberá ser una lista vacía.
- Cuando existan resultados válidos, puntos deberá contener los registros correspondientes hasta el límite establecido.
- Los registros deberán encontrarse dentro del radio consultado.
- Los resultados conservarán el orden de proximidad establecido por la herramienta.
- Cuando fuente=corpus_local, se incluirá un aviso sobre la posible desactualización de los datos.

puntos_candidatos seguirá siendo un atributo interno utilizado para interpretar horarios y priorizar recomendaciones.

No se expondrá mediante el contrato HTTP.

Los resultados geográficos públicos representan una búsqueda por proximidad, no necesariamente la totalidad de instalaciones consideradas en la síntesis del agente.

#### Resultados vacíos

Una búsqueda válida puede devolver cero registros.

No deberá confundirse una búsqueda vacía legítima con:

- Fallos de conexión.
- Respuestas inválidas del proveedor.
- Fallos de normalización de todos los registros recibidos.
- Fallos del corpus local.
- Errores internos de la herramienta.

El respaldo local se activará únicamente ante fallos técnicos contemplados por la herramienta.

Si ninguna fuente autorizada permite completar la operación, se devolverá el error técnico correspondiente.

### 6.7. ApproveIn

| Campo | Tipo | Obligatorio |
|---|---|---|
| thread_id | str | Sí |
| approval_id | str | Sí |
| aprobado | bool | Sí |

thread_id y approval_id deberán ser UUID válidos.

aprobado deberá ser un booleano.

El backend comprobará que approval_id corresponde a la aprobación actualmente pendiente en el checkpoint de la conversación.

No se aceptarán planes, checkpoints ni estados completos proporcionados por el cliente.

#### Ejemplo

```json
{
    "thread_id": "550e8400-e29b-41d4-a716-446655440000",
    "approval_id": "550e8400-e29b-41d4-a716-446655440002",
    "aprobado": true
}
```

### 6.8. MessageOut

| Campo | Tipo |
|---|---|
| role | MessageRole |
| content | str |
| created_at | datetime |

Representa un mensaje recuperado de PostgreSQL.

Los roles permitidos serán user y assistant.

Los mensajes se devolverán ordenados por su identificador relacional ascendente.

El identificador interno y turn_number no se expondrán mediante este contrato.

### 6.9. ConversationOut

| Campo | Tipo |
|---|---|
| thread_id | str |
| api_key_id | str |
| created_at | datetime |

Representa la información pública de una conversación persistida.

No contiene el checkpoint interno de LangGraph, el plan pendiente ni approval_id.

No deberá utilizarse para deducir el estado operativo del agente.

### 6.10. HealthOut

| Campo | Tipo |
|---|---|
| status | str |
| storage | str |

Ejemplo de respuesta satisfactoria:

```json
{
    "status": "ok",
    "storage": "postgres"
}
```

GET /health devolverá HTTP 200 cuando se cumplan las comprobaciones de disponibilidad establecidas.

No llamará a Gemini.

Si falta configuración imprescindible o no están disponibles los componentes requeridos, se devolverá HTTP 503 mediante ErrorOut.

El endpoint no constituirá una garantía de que todos los proveedores externos respondan correctamente a una consulta posterior.

## 7. Contratos de autenticación y API keys

### 7.1. RegisterIn

| Campo | Tipo |
|---|---|
| email | str |
| password | str |

La confirmación de contraseña será responsabilidad del cliente.

El backend validará siempre la contraseña recibida conforme a la especificación de autenticación.

### 7.2. LoginIn

| Campo | Tipo |
|---|---|
| email | str |
| password | str |

### 7.3. PasswordChangeIn

| Campo | Tipo |
|---|---|
| current_password | str |
| new_password | str |

Se comprobará la contraseña actual y se validará la nueva.

El cambio satisfactorio invalidará todas las sesiones existentes del usuario.

### 7.4. UserOut

| Campo | Tipo |
|---|---|
| id | UUID |
| email | str |
| created_at | datetime |
| is_active | bool |

No se devolverán contraseñas, hashes ni secretos relacionados con la cuenta.

### 7.5. LoginOut

| Campo | Tipo |
|---|---|
| session_token | str |
| token_type | str |
| expires_at | datetime |
| user | UserOut |

token_type identificará la modalidad Bearer.

El token original únicamente se devolverá durante el inicio de sesión.

### 7.6. ApiKeyCreateIn

Utilizado por POST /api-keys.

| Campo | Tipo | Default |
|---|---|---|
| role | Literal free, user | free |

No se admitirán campos adicionales.

El propietario de la nueva API key se obtendrá exclusivamente de la sesión autenticada.

No se permitirá indicar user_id ni solicitar el rol Admin mediante este contrato.

Solicitar el rol User no concede automáticamente autorización para obtenerlo.

### 7.7. AdminApiKeyCreateIn

Utilizado por POST /admin/api-keys.

| Campo | Tipo | Obligatorio |
|---|---|---|
| role | Literal free, user | Sí |
| user_id | UUID o None | Según el rol |

No se admitirán campos adicionales.

Para claves Free, user_id podrá ser None.

Para claves User, user_id será obligatorio.

Cuando exista un propietario, deberá corresponder a una cuenta existente, activa y no eliminada.

La emisión administrativa de una API key User constituye una autorización explícita para esa clave.

No concede al propietario autorización automática para emitir nuevas claves User mediante el endpoint ordinario de cuenta.

Se respetarán los límites de emisión y de claves activas establecidos.

### 7.8. ApiKeyOut

| Campo | Tipo |
|---|---|
| id | UUID |
| role | ApiKeyRole |
| user_id | UUID o None |
| is_active | bool |
| created_at | datetime |
| last_used_at | datetime o None |
| deleted_at | datetime o None |

Los modelos públicos utilizarán ApiKeyRole como enumerado compartido.

No se devolverán key_hash ni la API key original.

### 7.9. ApiKeyCreatedOut

Extiende ApiKeyOut incorporando:

| Campo | Tipo |
|---|---|
| api_key | str |

La API key original únicamente se devolverá durante su generación.

La respuesta será HTTP 201 después de confirmar que la transacción de creación ha finalizado satisfactoriamente.

Las posteriores consultas no permitirán recuperar la clave original.

### 7.10. ActiveStatusIn

Utilizado por:

- PATCH /admin/users/{user_id}
- PATCH /admin/api-keys/{api_key_id}

| Campo | Tipo |
|---|---|
| is_active | StrictBool |

No se admitirán campos adicionales.

Únicamente se podrá modificar el estado activo del recurso.

No se podrán modificar mediante este contrato:

- Identificadores.
- Propietarios.
- Roles.
- Hashes.
- Fechas de eliminación.

La reactivación de una API key deberá respetar los límites de claves activas.

Las cuentas y claves eliminadas lógicamente no podrán reactivarse.

### 7.11. Emisión anónima

POST /api-keys/free no requiere un modelo de entrada.

El backend determinará exclusivamente:

- role=free.
- user_id=None.

La respuesta será ApiKeyCreatedOut.

No se podrá solicitar una clave User o Admin mediante esta operación.

### 7.12. Protección de las respuestas de credenciales

Las respuestas que contengan tokens de sesión originales o API keys originales incluirán:

```http
Cache-Control: no-store
```

No se incluirán estas credenciales en parámetros de URL ni en registros de observabilidad.

La validación de contraseñas, las sesiones, el hashing y las reglas de emisión se establecen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

## 8. Contrato multimodal

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

Los campos compartidos tendrán las mismas restricciones y valores predeterminados que AskIn.

Si se proporciona una coordenada, será obligatorio proporcionar la otra.

### 8.1. Formatos admitidos

- JPEG.
- PNG.

### 8.2. Límites finales

| Parámetro | Límite |
|---|---|
| Peso | 5 MiB |
| Resolución | 16.000.000 píxeles |

Los límites absolutos de recepción y descompresión se definen en la especificación de robustez.

Superar los límites finales no constituye un error si la imagen puede adaptarse correctamente y de forma segura.

### 8.3. Procesamiento

1. Autenticar la credencial.
2. Verificar la autorización multimodal.
3. Validar los campos de entrada.
4. Comprobar la conversación existente, cuando corresponda.
5. Comprobar las restricciones absolutas de recepción.
6. Identificar el formato real del archivo.
7. Validar la integridad.
8. Comprimir o redimensionar cuando sea necesario.
9. Preparar el archivo temporal autorizado.
10. Aplicar los controles de admisión y cuota comercial.
11. Ejecutar la identificación multimodal estructurada.
12. Validar el resultado.
13. Determinar la admisibilidad de la imagen.
14. Ejecutar LangGraph únicamente cuando la imagen haya sido admitida.
15. Reutilizar la identificación obtenida.
16. Resolver automáticamente el HITL cuando corresponda.
17. Validar el resultado y aplicar la política de persistencia.
18. Eliminar el archivo cuando ninguna ejecución pueda seguir utilizándolo.

No se aceptarán rutas locales de archivos proporcionadas por clientes.

### 8.4. Identificación multimodal

El resultado interno de la identificación contendrá:

- estado.
- descripcion.

Los valores permitidos de estado serán:

- allowed.
- out_of_domain.
- policy_violation.
- uncertain.

La descripción no constituirá evidencia documental suficiente para determinar el destino del residuo.

La clasificación semántica se validará mediante Python.

### 8.5. Admisibilidad

| Estado | Comportamiento |
|---|---|
| allowed | Continuar con LangGraph reutilizando la identificación |
| out_of_domain | Abstención controlada sin ejecutar LangGraph |
| policy_violation | HTTP 422 IMAGE_CONTENT_NOT_ALLOWED |
| uncertain | Solicitud controlada de una nueva imagen sin ejecutar LangGraph |

Un fallo de Gemini, una respuesta vacía o una estructura incompatible no se convertirán en uncertain.

Los fallos técnicos se comunicarán mediante el código HTTP correspondiente.

Las imágenes admitidas seguirán el HITL obligatorio del agente.

### 8.6. Timeout

La identificación multimodal, la ejecución de LangGraph y la aprobación automática compartirán un único presupuesto temporal.

No se asignará un timeout completo e independiente a cada fase.

El procesamiento respetará los límites y mecanismos establecidos en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 9. Gestión de conversaciones

### 9.1. Creación

Los identificadores de conversaciones HTTP serán generados exclusivamente por el backend.

Cuando thread_id=None y la consulta haya superado los controles previos necesarios para ejecutar LangGraph:

- Se generará un UUID mediante la función autorizada existente.
- Se creará la conversación en PostgreSQL.
- Se asociará a la API key utilizada.
- Se inicializará el estado del agente.
- Se ejecutará el turno.

La conversación se creará antes de iniciar LangGraph, pero no durante una respuesta determinista previa que no requiera ejecutar el agente.

Una conversación creada puede existir temporalmente sin mensajes persistidos.

### 9.2. Identificadores proporcionados por el cliente

| Situación | Comportamiento |
|---|---|
| thread_id=None u omitido | Nueva conversación cuando proceda ejecutar el agente |
| UUID inválido | 422 INVALID_THREAD_ID |
| UUID válido e inexistente | 404 THREAD_NOT_FOUND |
| UUID existente pero no autorizado | 404 THREAD_NOT_FOUND |
| UUID existente y autorizado | Validar estado operativo |

No se crearán conversaciones utilizando UUID inexistentes proporcionados por clientes.

No se reasignarán conversaciones existentes a otras API keys.

### 9.3. Continuación

Cuando se utiliza un thread_id existente, FastAPI comprobará:

- La existencia de la conversación.
- La autorización de acceso.
- La disponibilidad del estado necesario para continuar.
- Que no exista un HITL pendiente.
- Que la conversación no esté finalizada.
- Que no se hayan agotado los turnos.
- Que no exista otra ejecución modificando el hilo.

Las comprobaciones de estado deberán realizarse bajo los mecanismos de exclusión mutua correspondientes.

Una respuesta determinista previa no permitirá eludir las restricciones de una conversación existente.

### 9.4. Propiedad

La propiedad de una conversación corresponde a api_key_id.

Dos API keys pertenecientes al mismo usuario no comparten conversaciones.

Conocer un thread_id no concede permiso de acceso.

Para evitar revelar la existencia de conversaciones ajenas, se devolverá THREAD_NOT_FOUND cuando la credencial no esté autorizada.

### 9.5. Reinicio del backend

El historial SQL permanecerá disponible después de un reinicio.

MemorySaver perderá los checkpoints almacenados en el proceso.

No se reconstruirá automáticamente un estado de LangGraph utilizando los mensajes SQL.

Cuando una operación requiera un checkpoint que ya no está disponible, se devolverá HTTP 409 THREAD_STATE_LOST.

El consumidor podrá iniciar una nueva conversación.

### 9.6. Pérdida de una respuesta HTTP

Cuando el cliente no reciba una respuesta concluyente a una petición POST:

- No se repetirá automáticamente la operación.
- No se asumirá que la ejecución ha fallado.
- No se asumirá que la ejecución ha finalizado correctamente.
- No se reconstruirá approval_id a partir del historial.
- No se deducirá el estado operativo mediante los mensajes SQL.
- Se permitirá consultar el historial autorizado.
- Se permitirá iniciar una nueva conversación.

No se incorporarán mecanismos de idempotencia HTTP ni endpoints adicionales de recuperación de checkpoints durante el PB03.

La pérdida de una respuesta HTTP no constituye por sí misma un código de error devuelto por el backend.

## 10. HITL

### 10.1. Comportamiento obligatorio

Toda ejecución satisfactoria de LangGraph deberá producir una respuesta válida y un plan, alcanzando la interrupción existente antes del nodo aplicar.

Se conservará el comportamiento del agente desarrollado durante el PB02.

No se incorporarán rutas de finalización directa del grafo que eviten el HITL.

Una ejecución del agente que termine inesperadamente sin alcanzar el HITL requerido se considerará un fallo técnico.

### 10.2. Aprobación manual

Cuando auto_aprobar=False y el agente haya alcanzado correctamente la interrupción HITL:

- pendiente_hitl=True.
- plan_aprobado=None.
- done=False.
- approval_id tendrá un UUID válido.
- error=None.

El turno todavía no estará resuelto.

No se persistirán sus mensajes.

Streamlit habilitará los botones Aprobar y Rechazar únicamente cuando exista una aprobación pendiente válida.

### 10.3. Aprobación automática

Cuando auto_aprobar=True:

1. Ejecutar el agente.
2. Comprobar la existencia del HITL real.
3. Validar la respuesta y el plan.
4. Utilizar la misma función de resolución de HITL que la aprobación manual.
5. Verificar el resultado de la aprobación.
6. Persistir el turno resuelto.
7. Devolver AskOut.

No se simulará una aprobación modificando exclusivamente los atributos públicos del estado.

### 10.4. POST /approve

El backend deberá comprobar:

- La autorización sobre la conversación.
- La disponibilidad del checkpoint.
- La existencia de una interrupción HITL real.
- La validez del plan pendiente.
- La coincidencia de approval_id.
- La disponibilidad de capacidad de ejecución.
- La ausencia de otra operación modificando el hilo.

Si no existe un HITL pendiente, se devolverá HTTP 409 NO_PENDING_APPROVAL.

Si existe una aprobación pendiente, pero approval_id no coincide, se devolverá HTTP 409 STALE_APPROVAL.

La resolución se realizará mediante la API pública del agente.

### 10.5. Aprobación satisfactoria

- plan_aprobado=True.
- pendiente_hitl=False.
- approval_id=None.
- done=True.
- error=None.

La conversación quedará finalizada.

Se persistirá el turno resuelto antes de devolver HTTP 200.

### 10.6. Rechazo satisfactorio

- plan_aprobado=False.
- pendiente_hitl=False.
- approval_id=None.
- done=False.
- plan=[].
- error=None.

El rechazo resuelve el turno, pero permite continuar la conversación mientras no se agoten sus límites.

Se persistirá el turno resuelto antes de devolver HTTP 200.

El rechazo no constituye un error HTTP.

### 10.7. Respuestas anteriores a LangGraph

Las consultas inequívocamente fuera de dominio, las aclaraciones deterministas previas y las imágenes no admitidas semánticamente podrán resolverse antes de ejecutar LangGraph.

Las respuestas semánticas previas válidas:

- No generan un plan.
- No requieren HITL.
- No incrementan turnos_consumidos.
- No generan mensajes persistidos.
- No modifican el checkpoint.

Estas respuestas no constituyen una salida directa del grafo.

Las imágenes con contenido no permitido y los fallos técnicos devolverán ErrorOut en lugar de AskOut.

## 11. Persistencia de turnos

### 11.1. Criterio de persistencia

Únicamente se persistirán los turnos del agente resueltos satisfactoriamente mediante aprobación o rechazo.

Esto incluye las abstenciones y aclaraciones generadas dentro de LangGraph, una vez resuelto su HITL.

No se utilizará exclusivamente done=True como criterio de persistencia.

Un turno rechazado puede estar resuelto aunque la conversación continúe abierta.

### 11.2. Contabilización

Se mantendrán independientes:

- El contador de peticiones HTTP.
- Las cuotas comerciales.
- El contador turnos_consumidos del agente.

turn_number se obtendrá de turnos_consumidos.

No se incorporará un contador SQL independiente.

La aprobación o rechazo no incrementará el número de turno.

Las respuestas anteriores a LangGraph tampoco lo incrementarán.

### 11.3. Transacción

El turno resuelto se almacenará mediante una única transacción SQL que incluya:

- El mensaje original del usuario.
- La respuesta definitiva del asistente.

Ambos mensajes compartirán el mismo turn_number.

No se persistirán como turnos adicionales las solicitudes de aprobación o rechazo.

Se evitará duplicar mensajes ante operaciones de aprobación repetidas.

### 11.4. Situaciones sin persistencia

No se persistirán mensajes en los siguientes casos:

- Respuesta determinista previa a LangGraph.
- Imagen rechazada antes del agente.
- HITL pendiente.
- Fallo técnico.
- Petición inválida.
- Petición no autorizada.
- Cuota agotada.
- Capacidad de ejecución agotada.
- Timeout.
- Resultado tardío de una ejecución cuyo timeout ya fue comunicado.

### 11.5. Confirmación de persistencia

No se devolverá HTTP 200 para un turno resuelto hasta confirmar la persistencia de ambos mensajes.

Si PostgreSQL falla, se devolverá el error técnico correspondiente.

Se ejecutará rollback cuando proceda.

Cuando la consistencia del checkpoint no pueda garantizarse, se impedirá la reutilización de la conversación.

Los datos previamente persistidos deberán permanecer disponibles.

## 12. Contrato de errores

### 12.1. ErrorOut

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

El código HTTP se transmitirá como estado de la respuesta.

Los errores de validación de FastAPI se adaptarán a este contrato.

### 12.2. Protección de información

No se devolverán:

- Stack traces.
- Secretos.
- Rutas internas.
- Consultas SQL.
- Cadenas de conexión.
- Excepciones completas de proveedores.
- Información sobre recursos ajenos.

### 12.3. Prevención de falsos éxitos

No se devolverá HTTP 200 cuando:

- El agente contenga un error técnico.
- El resultado no cumpla el contrato.
- El estado del HITL sea incoherente.
- No se alcance la interrupción obligatoria.
- La identificación multimodal devuelva una estructura inválida.
- Se produzca un fallo bloqueante de una herramienta.
- No pueda confirmarse una persistencia obligatoria.
- Se supere el timeout.

Los resultados internos deberán verificarse antes de construir AskOut y antes de persistir mensajes.

El atributo error de toda respuesta AskOut satisfactoria será None.

### 12.4. Fallos de proveedores

Se distinguirá entre:

| Situación | HTTP |
|---|---|
| Resultado interno o externo incompatible con el contrato | 500 |
| Fallo inesperado del servicio | 500 |
| Dependencia temporalmente indisponible | 503 |
| Configuración imprescindible ausente | 503 |
| Timeout del presupuesto de ejecución | 504 |

Cuando no pueda identificarse con seguridad una causa técnica más específica, se utilizará HTTP 500 INTERNAL_SERVER_ERROR.

No se analizarán mensajes arbitrarios del LLM para decidir códigos HTTP.

## 13. Catálogo de errores

### 13.1. Autenticación y autorización

| HTTP | Código | Situación |
|---|---|---|
| 401 | API_KEY_REQUIRED | Falta una clave obligatoria |
| 401 | INVALID_API_KEY | API key inválida |
| 401 | INVALID_CREDENTIALS | Email o contraseña incorrectos |
| 401 | INVALID_SESSION | Sesión inexistente o inválida |
| 401 | SESSION_EXPIRED | Sesión caducada |
| 403 | API_KEY_INACTIVE | Clave desactivada |
| 403 | USER_INACTIVE | Usuario no habilitado |
| 403 | INSUFFICIENT_PERMISSIONS | Rol sin permisos |
| 403 | USER_TIER_NOT_AUTHORIZED | Usuario sin autorización para emitir claves User |

### 13.2. Recursos

| HTTP | Código | Situación |
|---|---|---|
| 404 | THREAD_NOT_FOUND | Conversación inexistente o no accesible |
| 404 | USER_NOT_FOUND | Usuario inexistente |
| 404 | API_KEY_NOT_FOUND | Clave inexistente o no accesible |
| 409 | EMAIL_ALREADY_EXISTS | Email registrado previamente |
| 409 | API_KEY_LIMIT_REACHED | Límite de API keys activas alcanzado |
| 409 | API_KEY_DELETED | Intento de reactivar una clave eliminada |
| 409 | USER_DELETED | Intento de reactivar un usuario eliminado |

Los conflictos relativos a recursos eliminados únicamente se comunicarán cuando el consumidor esté autorizado a conocer su estado.

### 13.3. Conversaciones y HITL

| HTTP | Código | Situación |
|---|---|---|
| 409 | NO_PENDING_APPROVAL | No existe HITL pendiente |
| 409 | PENDING_APPROVAL | Se intenta iniciar un turno con HITL pendiente |
| 409 | THREAD_CLOSED | Conversación finalizada |
| 409 | TURN_LIMIT_REACHED | Límite de turnos agotado |
| 409 | THREAD_BUSY | Otra petición está modificando el hilo |
| 409 | THREAD_STATE_LOST | Estado operativo perdido o no reutilizable |
| 409 | STALE_APPROVAL | Identificador de aprobación obsoleto |

### 13.4. Validación

| HTTP | Código | Situación |
|---|---|---|
| 400 | EMPTY_QUESTION | Pregunta vacía después de aplicar strip() |
| 422 | QUESTION_TOO_LONG | Pregunta superior a 500 caracteres |
| 422 | INVALID_THREAD_ID | Identificador de conversación inválido |
| 422 | INVALID_LOCATION | Coordenadas inválidas o incompletas |
| 422 | INVALID_MAX_STEPS | Límite de pasos inválido |
| 422 | VALIDATION_ERROR | Incumplimiento del contrato de entrada |
| 422 | INVALID_EMAIL | Formato de email inválido |
| 422 | INVALID_PASSWORD | Contraseña incompatible con los requisitos |
| 422 | AMBIGUOUS_CREDENTIALS | Modalidades de autenticación incompatibles |

Un approval_id cuyo formato no corresponda a un UUID válido devolverá HTTP 422 VALIDATION_ERROR.

### 13.5. Imágenes

| HTTP | Código | Situación |
|---|---|---|
| 413 | IMAGE_FILE_TOO_LARGE | Supera el límite absoluto o no puede adaptarse el peso |
| 422 | IMAGE_RESOLUTION_EXCEEDED | Supera el límite absoluto o no puede adaptarse la resolución |
| 422 | IMAGE_CORRUPTED | Imagen vacía, corrupta o ilegible |
| 422 | IMAGE_CONTENT_NOT_ALLOWED | Contenido no permitido |
| 415 | IMAGE_FORMAT_NOT_ALLOWED | Formato no admitido |

La falta de permisos multimodales se tratará como HTTP 403 INSUFFICIENT_PERMISSIONS.

Los fallos técnicos durante la identificación se tratarán conforme al apartado 13.6.

### 13.6. Cuotas y robustez

| HTTP | Código | Situación |
|---|---|---|
| 429 | RATE_LIMIT_EXCEEDED | Límite de peticiones o cuota alcanzado |
| 500 | INTERNAL_SERVER_ERROR | Fallo interno inesperado o resultado inválido |
| 503 | SERVICE_NOT_CONFIGURED | Configuración imprescindible ausente |
| 503 | SERVICE_UNAVAILABLE | Servicio o dependencia no disponible |
| 503 | SERVER_BUSY | Capacidad de ejecución agotada |
| 504 | AGENT_TIMEOUT | Tiempo máximo de ejecución superado |

Las respuestas 429 incluirán Retry-After cuando pueda determinarse el tiempo de reintento.

## 14. Situaciones que no constituyen errores

| HTTP | Situación |
|---|---|
| 200 | Consulta procesada con HITL pendiente |
| 200 | Plan aprobado y turno correctamente persistido |
| 200 | Plan rechazado y turno correctamente persistido |
| 200 | Abstención documental válida |
| 200 | Consulta fuera de dominio resuelta mediante una abstención controlada |
| 200 | Solicitud de aclaración válida |
| 200 | Coordenadas omitidas que requieren una aclaración válida |
| 200 | Búsqueda geográfica válida sin coincidencias |
| 200 | Uso satisfactorio del corpus local como respaldo autorizado |
| 200 | Consulta multimodal correctamente adaptada y procesada |
| 200 | Imagen identificada correctamente como fuera de dominio |
| 200 | Solicitud de una nueva imagen por identificación incierta |
| 200 | Historial autorizado sin mensajes |
| 200 | Inicio de sesión correcto |
| 200 | Consulta autorizada de cuenta o credencial |
| 200 | Modificación administrativa de estado correcta |
| 201 | Usuario registrado correctamente |
| 201 | API key generada correctamente |
| 204 | Cierre de sesión correcto |
| 204 | Eliminación lógica correcta de un recurso |

Las abstenciones y aclaraciones generadas dentro del agente respetarán el HITL obligatorio.

Las respuestas deterministas anteriores a LangGraph no requerirán HITL ni persistencia.

Una abstención semántica no deberá confundirse con un fallo técnico.

La adaptación correcta de una imagen no garantiza por sí misma que la consulta completa finalice satisfactoriamente.

## 15. Trazabilidad de las respuestas HTTP

Cada petición HTTP dispondrá de un request_id único generado por el backend.

El identificador se devolverá mediante:

```http
X-Request-ID: <request_id>
```

También formará parte de ErrorOut cuando se produzca un error.

Los registros de observabilidad deberán reflejar el código HTTP realmente devuelto.

Se incluirá thread_id cuando exista y resulte aplicable.

No se registrará un resultado técnico fallido como éxito funcional.

Las respuestas HTTP 429 incluirán Retry-After cuando pueda determinarse el tiempo de reintento.

La estructura de registros, las métricas operativas y las restricciones de logging se definen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 16. Criterios de aceptación

### 16.1. Contratos

- Swagger muestra los endpoints y modelos implementados.
- Los contratos públicos no exponen el estado completo del agente.
- Las entradas inválidas reciben los códigos HTTP correspondientes.
- Las respuestas satisfactorias respetan sus invariantes.
- Una pregunta vacía después de aplicar strip() devuelve HTTP 400.
- Los errores estructurales de entrada devuelven HTTP 422.

### 16.2. Autenticación y autorización

- Los endpoints protegidos rechazan peticiones sin credenciales válidas.
- Las API keys Free pueden generarse para consumidores anónimos y registrados.
- Las API keys User requieren autorización ordinaria o emisión administrativa.
- No se permite generar claves Admin mediante endpoints.
- Las conversaciones se aíslan por API key.
- Una clave desactivada no permite nuevas consultas.
- El propietario de una clave desactivada puede consultar su historial mediante una sesión válida.
- Un administrador puede consultar cualquier conversación.
- Las claves eliminadas no pueden reactivarse.
- Las cuentas eliminadas no pueden reactivarse.
- La reactivación de claves respeta los límites de claves activas.
- Los secretos originales únicamente se devuelven en las operaciones autorizadas de emisión o autenticación.

### 16.3. Conversaciones y HITL

- El backend genera los identificadores de conversaciones.
- Un UUID válido e inexistente devuelve HTTP 404.
- Las ejecuciones satisfactorias de LangGraph alcanzan la interrupción HITL obligatoria.
- auto_aprobar=False devuelve una aprobación pendiente válida.
- auto_aprobar=True resuelve el HITL mediante la misma función de aprobación.
- No se puede aprobar sin una interrupción pendiente real.
- Una aprobación obsoleta no puede resolver un nuevo HITL.
- La pérdida de un checkpoint no permite reconstruir automáticamente el estado.
- No se repiten automáticamente peticiones POST cuyo resultado sea desconocido.

### 16.4. Multimodalidad

- Las imágenes se reciben mediante HTTP.
- No se aceptan rutas locales del cliente.
- Se respetan los límites de tamaño y resolución.
- Las imágenes adaptables se procesan de forma segura.
- La identificación multimodal devuelve una estructura validada.
- Las imágenes no admitidas no continúan con LangGraph.
- La identificación se reutiliza sin repetir la llamada multimodal.
- Los fallos técnicos no se presentan como incertidumbre semántica.

### 16.5. Fuentes y geografía

- Las fuentes documentales proceden exclusivamente del corpus y de referencias normativas autorizadas.
- Los resultados geográficos proceden de ArcGIS o del respaldo local autorizado.
- No se realizan búsquedas abiertas en Internet.
- No se inventan citas ni enlaces.
- No se exponen rutas internas ni embeddings.
- Las búsquedas vacías legítimas se distinguen de los fallos técnicos.
- Los horarios publicados no se presentan como confirmación de apertura física.
- El respaldo local identifica explícitamente su procedencia y limitaciones.

### 16.6. Persistencia

- Únicamente se almacenan los turnos del agente correctamente resueltos.
- Los turnos pendientes de HITL no generan mensajes persistidos.
- Las respuestas previas a LangGraph no generan mensajes persistidos.
- Los dos mensajes de cada turno se almacenan atómicamente.
- turn_number procede del contador de turnos del agente.
- Un fallo de persistencia no devuelve éxito.
- Los resultados tardíos tras un timeout no se almacenan.
- El historial autorizado sobrevive a un redeploy.

### 16.7. Robustez y observabilidad

- Las cuotas se aplican independientemente por API key.
- Las peticiones concurrentes respetan los mecanismos de admisión y bloqueo.
- El timeout incluye la identificación multimodal y la aprobación automática cuando corresponda.
- El agotamiento del presupuesto temporal devuelve HTTP 504.
- Los fallos técnicos no se ocultan mediante HTTP 200.
- Toda respuesta AskOut satisfactoria contiene error=None.
- GET /health no llama a Gemini.
- GET /health no declara disponibilidad cuando faltan componentes imprescindibles.
- Las respuestas HTTP incluyen request_id.
- Los registros reflejan el resultado real de cada petición.
- Los errores no exponen información sensible.