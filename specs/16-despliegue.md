# 16. Despliegue e infraestructura

## 1. Objetivo

Definir la infraestructura necesaria para ejecutar, empaquetar, desplegar y mantener ReciclaTÍA como un servicio accesible mediante una API REST.

El despliegue debe garantizar la reproducibilidad del entorno, la separación entre desarrollo y producción, la persistencia del historial, la protección de credenciales y la trazabilidad de las versiones desplegadas.

La infraestructura deberá permitir una futura evolución del producto sin introducir complejidad innecesaria durante esta fase del desarrollo.

## 2. Tecnologías

| Tecnología | Responsabilidad |
|---|---|
| Python 3.13.2 | Entorno de ejecución |
| FastAPI | Exposición de la API REST |
| Uvicorn | Servidor ASGI |
| Docker | Empaquetado y ejecución del backend |
| Docker Compose | Coordinación opcional de servicios locales |
| PostgreSQL | Persistencia relacional |
| SQLModel | Acceso a PostgreSQL |
| ChromaDB | Almacenamiento vectorial |
| Streamlit | Cliente del asistente |
| Render | Infraestructura de despliegue |
| GitHub | Control de versiones |
| GitHub Actions | Automatización opcional de integración continua |

## 3. Entornos

### 3.1. Desarrollo local

El entorno local permitirá desarrollar y validar todas las funcionalidades antes de incorporarlas a producción.

Componentes:

- Entorno virtual Python .venv.
- Backend FastAPI ejecutado localmente o mediante Docker.
- PostgreSQL ejecutado mediante Docker.
- Streamlit ejecutado localmente.
- Índice ChromaDB local.
- Variables de entorno específicas de desarrollo.

### 3.2. Producción

El entorno de producción estará formado por:

- Un servicio web de Render.
- Un contenedor Docker con FastAPI, LangGraph, RAG y ChromaDB.
- Una base de datos PostgreSQL gestionada por Render.
- Una URL pública HTTPS.
- Variables de entorno configuradas en Render.
- Una única instancia del backend.
- Un único proceso de Uvicorn.
- Un único worker de ThreadPoolExecutor.

Streamlit podrá conectarse al backend desplegado sin modificar su código.

### 3.3. Aislamiento

Los entornos de desarrollo y producción no compartirán:

- Bases de datos.
- Credenciales administrativas.
- API keys de consumidores.
- Sesiones de autenticación.
- Configuración de acceso.

Se recomienda utilizar credenciales de Gemini independientes cuando sea posible para distinguir el consumo de cada entorno.

Los datos utilizados durante las pruebas locales no se trasladarán automáticamente a producción.

## 4. Arquitectura de infraestructura

```mermaid
flowchart TD
    A[Navegador] --> B[Streamlit local]
    B -->|HTTPS| C[Render Web Service]
    C --> D[FastAPI y Uvicorn]
    D --> E[ThreadPoolExecutor]
    E --> F[LangGraph]
    F --> G[MemorySaver]
    F --> H[RAG y ChromaDB]
    D -->|Red privada| I[Render PostgreSQL]
    F --> J[Gemini API]
    F --> K[API municipal de Madrid]
```

FastAPI, el núcleo del asistente y ChromaDB compartirán un único contenedor.

PostgreSQL se ejecutará como un servicio independiente.

No se desplegará una base de datos PostgreSQL dentro del contenedor del backend.

## 5. Gestión de dependencias

### 5.1. Dependencias existentes

Se conservarán las dependencias de la fase de desarrollo anterior necesarias para:

- Procesamiento documental.
- Recuperación semántica.
- Generación.
- Orquestación multiagente.
- Procesamiento de imágenes.
- Validación.
- Pruebas automatizadas.
- Interfaz Streamlit.

### 5.2. Dependencias adicionales

| Dependencia | Finalidad |
|---|---|
| fastapi | API REST |
| uvicorn | Servidor ASGI |
| pydantic | Contratos HTTP |
| sqlmodel | Modelos relacionales |
| psycopg2-binary | Conexión con PostgreSQL |
| python-multipart | Recepción de imágenes |
| httpx | Cliente HTTP y pruebas de endpoints |

Las dependencias utilizadas directamente deberán declararse explícitamente, aunque ya se encuentren instaladas indirectamente.

Las versiones deberán ser compatibles con el entorno existente y con Python 3.13.2.

### 5.3. Reproducibilidad

requirements.txt seguirá siendo la referencia de dependencias del proyecto.

Una vez validada la implementación, se documentarán las versiones efectivamente utilizadas para facilitar la reproducción del entorno.

Las dependencias no se actualizarán indiscriminadamente durante la integración de la capa MLOps.

## 6. Docker

### 6.1. Objetivo

Docker permitirá ejecutar el backend dentro de un entorno aislado y reproducible.

La imagen contendrá las dependencias y los recursos necesarios para ejecutar ReciclaTÍA sin depender del entorno virtual del desarrollador.

### 6.2. Imagen base

Se propone utilizar:

```dockerfile
FROM python:3.13.2-slim
```

La imagen deberá contener únicamente las dependencias necesarias para ejecutar correctamente el servicio.

Se evitarán herramientas y paquetes innecesarios.

### 6.3. Contenido de la imagen

La imagen deberá incorporar:

- Código del backend FastAPI.
- Núcleo del asistente.
- Configuración no sensible.
- Herramientas del agente.
- Corpus documental necesario.
- Chunks existentes.
- Embeddings precalculados.
- Índice ChromaDB reconstruido.
- Dependencias necesarias.

Los archivos incluidos deberán corresponder a la versión del repositorio utilizada durante la construcción.

### 6.4. Exclusiones

No deberán incorporarse a la imagen:

- Archivos .env con credenciales.
- Entornos virtuales locales.
- Historial de Git.
- Cachés innecesarias.
- Bases de datos locales.
- Logs.
- Imágenes temporales de usuarios.
- Resultados de evaluación que no sean necesarios durante la ejecución.
- Archivos de configuración privada del desarrollador.

### 6.5. Dockerfile

El Dockerfile deberá realizar las siguientes operaciones:

1. Seleccionar la imagen base.
2. Configurar el directorio de trabajo.
3. Copiar requirements.txt.
4. Instalar las dependencias.
5. Copiar el código y los recursos necesarios.
6. Reconstruir el índice vectorial.
7. Preparar los directorios temporales.
8. Configurar el comando de arranque del backend.

Se priorizará el aprovechamiento de la caché de construcción de Docker.

Cuando sea viable, el proceso se ejecutará mediante un usuario sin privilegios de administrador.

### 6.6. Reconstrucción del índice vectorial

Se utilizarán los artefactos existentes:

- output/chunks.json
- output/embeddings.json

El índice podrá reconstruirse mediante:

```bash
python main.py rag index --yes
```

La reconstrucción deberá realizarse preferentemente durante la construcción de la imagen Docker.

No se ejecutará el pipeline completo de generación de embeddings durante cada build o redeploy.

La construcción de la imagen no deberá necesitar GEMINI_API_KEY.

Si el corpus o el modelo de embeddings cambian, se realizará previamente el proceso correspondiente de actualización de artefactos.

### 6.7. Arranque del backend

Uvicorn deberá escuchar en:

```text
0.0.0.0
```

El puerto se obtendrá de la variable PORT.

En ausencia de dicha variable se utilizará el puerto 8000.

Comando de referencia:

```dockerfile
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

En producción no se utilizará la opción --reload.

Se mantendrá un único proceso de Uvicorn para garantizar la coherencia de los recursos almacenados en memoria.

### 6.8. Arquitecturas de hardware

El entorno local puede utilizar ARM64, mientras que la infraestructura de despliegue puede utilizar una arquitectura diferente.

La construcción de imágenes deberá comprobar la compatibilidad de las dependencias con la plataforma de destino.

Render construirá la imagen a partir del Dockerfile del repositorio.

No se asumirá que una imagen construida localmente en ARM64 puede ejecutarse directamente en cualquier infraestructura.

## 7. Dockerignore

Se creará un archivo .dockerignore para reducir el contexto de construcción y evitar incorporar archivos innecesarios o sensibles.

Deberá excluir, como mínimo:

```text
.git
.venv
.venv_backup
.env
.env.*
__pycache__
.pytest_cache
.DS_Store
*.pyc
*.log
*.sqlite
*.sqlite3
*.db
output/cache/
output/evaluation/
output/chroma_db/
assets/.api_temporal/
```

Los patrones deberán ajustarse a la estructura real del proyecto.

No deberán excluirse los documentos necesarios del corpus ni los artefactos:

```text
output/chunks.json
output/embeddings.json
```

El índice ChromaDB local se excluye porque se reconstruirá dentro de la imagen.

El archivo .dockerignore no sustituye a .gitignore.

## 8. PostgreSQL local

### 8.1. Ejecución

PostgreSQL se ejecutará en un contenedor independiente durante el desarrollo local.

Se utilizará una versión estable de PostgreSQL compatible con la versión seleccionada en Render.

La versión concreta deberá fijarse antes de comenzar las pruebas de integración.

### 8.2. Configuración

El contenedor utilizará:

- POSTGRES_DB
- POSTGRES_USER
- POSTGRES_PASSWORD

Las credenciales se obtendrán desde variables de entorno.

No se incluirán contraseñas reales en archivos versionados.

### 8.3. Persistencia

Se utilizará un volumen Docker para conservar los datos de PostgreSQL.

Eliminar o recrear el contenedor no deberá eliminar automáticamente la base de datos si se conserva el volumen.

La eliminación del volumen constituirá una operación destructiva y deberá realizarse únicamente de manera intencionada.

### 8.4. Conexión desde el backend local

Cuando FastAPI se ejecute directamente desde el entorno virtual:

```text
postgresql://usuario:password@localhost:5432/reciclatia
```

Cuando FastAPI se ejecute dentro de Docker Compose:

```text
postgresql://usuario:password@db:5432/reciclatia
```

En el segundo caso, db representa el nombre del servicio PostgreSQL dentro de la red de Docker Compose.

localhost dentro de un contenedor hace referencia al propio contenedor, no a otros servicios.

### 8.5. Comprobación de disponibilidad

La base de datos deberá estar disponible antes de inicializar el backend.

Podrá utilizarse pg_isready para comprobar el estado de PostgreSQL.

Si se utiliza Docker Compose, se configurará un healthcheck y una dependencia de arranque basada en la disponibilidad del servicio.

## 9. Docker Compose

Docker Compose podrá utilizarse para simplificar la ejecución coordinada de los servicios locales.

La configuración podrá incluir:

- api: contenedor del backend.
- db: contenedor PostgreSQL.
- Red interna.
- Volumen persistente de PostgreSQL.
- Variables de entorno.
- Healthchecks.

Streamlit permanecerá inicialmente fuera de Docker Compose.

Su incorporación como servicio independiente constituye una ampliación opcional.

Docker Compose será una herramienta de desarrollo local y no un requisito para el despliegue en Render.

## 10. Despliegue en Render

### 10.1. Servicios necesarios

| Servicio | Tipo |
|---|---|
| Backend ReciclaTÍA | Web Service |
| Base de datos | Render PostgreSQL |

Ambos servicios deberán encontrarse preferentemente en la misma región.

### 10.2. Base de datos

Se creará una instancia PostgreSQL gestionada por Render.

El backend utilizará la URL interna de conexión proporcionada por Render.

La conexión externa se reservará para operaciones administrativas autorizadas, cuando resulte necesaria.

El acceso externo deberá restringirse cuando sea posible.

### 10.3. Configuración del Web Service

| Parámetro | Configuración |
|---|---|
| Repositorio | alex-bometon/pb03_equipo18 |
| Rama | main |
| Runtime | Docker |
| Dockerfile | Dockerfile |
| Health Check Path | /health |
| Instancias | 1 |
| Procesos Uvicorn | 1 |
| Workers del asistente | 1 |

La región y el tipo de instancia se determinarán según la disponibilidad, el coste y los requisitos de memoria del backend.

### 10.4. Puerto

El servicio utilizará el puerto proporcionado por Render mediante la variable PORT.

No se fijará exclusivamente el puerto 8000 para producción.

### 10.5. URL pública

Render proporcionará una URL pública HTTPS.

Los clientes utilizarán dicha URL como API_BASE_URL.

Los endpoints protegidos seguirán exigiendo las credenciales definidas en la especificación HTTP.

### 10.6. Health check

Render comprobará la disponibilidad mediante:

```http
GET /health
```

El endpoint deberá verificar los recursos imprescindibles del backend sin ejecutar el asistente ni consumir servicios de inferencia.

Un despliegue no se considerará validado únicamente porque el proceso de Uvicorn se haya iniciado.

### 10.7. Plan de infraestructura

Se priorizará una infraestructura de coste reducido adecuada para la evaluación académica.

Podrá utilizarse un plan gratuito si la memoria, la disponibilidad y las restricciones del servicio permiten ejecutar correctamente el proyecto.

No se asumirá que el plan gratuito constituye una infraestructura de producción comercial.

## 11. Variables de entorno

### 11.1. Configuración general

| Variable | Responsabilidad |
|---|---|
| PORT | Puerto del backend |
| API_BASE_URL | URL utilizada por Streamlit |
| DATABASE_URL | Conexión PostgreSQL |
| GEMINI_API_KEY | Autenticación con Gemini |
| API_KEY | Credencial de aprovisionamiento administrativo |
| CORS_ORIGINS | Orígenes web autorizados |
| LOG_LEVEL | Nivel de logging |

### 11.2. Autenticación y autorización

| Variable | Valor inicial |
|---|---|
| SESSION_TTL_SECONDS | 28800 |
| BCRYPT_ROUNDS | 12 |
| FREE_MAX_ACTIVE_KEYS | 1 |
| USER_MAX_ACTIVE_KEYS | 5 |
| USER_TIER_ALLOWED_EMAILS | Según configuración |

Las credenciales necesarias para el aprovisionamiento administrativo deberán definirse durante la implementación de dicho procedimiento.

No se utilizarán credenciales administrativas predeterminadas.

### 11.3. Cuotas comerciales

| Variable | Valor inicial |
|---|---:|
| FREE_RATE_LIMIT_PER_MINUTE | 2 |
| FREE_RATE_LIMIT_PER_HOUR | 10 |
| FREE_RATE_LIMIT_PER_DAY | 30 |
| USER_RATE_LIMIT_PER_MINUTE | 5 |
| USER_RATE_LIMIT_PER_HOUR | 20 |
| USER_RATE_LIMIT_PER_DAY | 45 |

### 11.4. Robustez

| Variable | Valor inicial |
|---|---:|
| RATE_LIMIT_PER_MINUTE | 30 |
| AGENT_MAX_WORKERS | 1 |
| ASK_TIMEOUT_SECONDS | 60 |
| IMAGE_UPLOAD_MAX_BYTES | 20971520 |
| IMAGE_UPLOAD_MAX_PIXELS | 32000000 |

Los límites temporales de registro, autenticación y emisión de claves se añadirán a la configuración centralizada.

### 11.5. Configuración local

Las variables se obtendrán desde el entorno de ejecución y, durante el desarrollo, podrán cargarse desde un archivo .env.

El archivo .env.example documentará los parámetros necesarios sin incluir secretos reales.

### 11.6. Configuración en Render

Las variables de producción se configurarán mediante el panel de administración de Render.

No se utilizará un archivo .env de producción versionado en GitHub.

Las variables proporcionadas por el entorno de ejecución deberán tener prioridad sobre los valores locales.

### 11.7. Validación de configuración

El backend comprobará durante su inicialización:

- Variables imprescindibles.
- Formato de DATABASE_URL.
- Validez de los límites configurados.
- Disponibilidad del índice vectorial.
- Conectividad con PostgreSQL.

Los parámetros necesarios exclusivamente para FastAPI no deberán impedir la ejecución independiente del núcleo RAG o de la CLI.

## 12. Gestión de secretos

Los siguientes valores se considerarán sensibles:

- GEMINI_API_KEY
- DATABASE_URL
- API_KEY
- Credenciales de PostgreSQL
- Contraseñas administrativas
- API keys de consumidores
- Tokens de sesión

### 12.1. Restricciones

- No incorporar secretos al repositorio.
- No incorporar secretos a la imagen Docker.
- No introducir secretos mediante argumentos de construcción.
- No registrar secretos en logs.
- No mostrar secretos en capturas de pantalla.
- No publicar credenciales en el informe técnico.
- No proporcionar credenciales administrativas a consumidores ordinarios.

### 12.2. Credenciales de evaluación

Cuando sea necesario proporcionar acceso a los evaluadores del proyecto, se generará una credencial específica para dicho propósito.

Se utilizará preferentemente una API key User, con acceso a las funcionalidades del asistente y sin permisos administrativos.

Las credenciales administrativas solo se facilitarán de forma privada cuando sean necesarias para evaluar funcionalidades de administración.

Las credenciales de evaluación podrán desactivarse al finalizar la evaluación.

### 12.3. Rotación

Una credencial comprometida deberá revocarse o sustituirse.

Eliminar una credencial de un archivo no garantiza que desaparezca del historial de Git.

Si una credencial se publica accidentalmente, deberá considerarse comprometida.

## 13. Inicialización del backend

FastAPI gestionará la inicialización y el cierre de recursos mediante su ciclo de vida.

### 13.1. Inicio

1. Cargar y validar la configuración.
2. Inicializar el engine de PostgreSQL.
3. Comprobar la conexión.
4. Crear las tablas inexistentes.
5. Ejecutar el aprovisionamiento administrativo cuando corresponda.
6. Verificar la disponibilidad de ChromaDB.
7. Inicializar el grafo compartido.
8. Inicializar los contadores, bloqueos y sesiones.
9. Inicializar ThreadPoolExecutor.
10. Habilitar el servicio HTTP.

El aprovisionamiento deberá ser idempotente.

### 13.2. Cierre

Durante el cierre del servicio se gestionarán:

- Las ejecuciones activas.
- Los recursos del executor.
- Las sesiones y conexiones de PostgreSQL.
- Los archivos temporales.
- Los recursos que requieran cierre explícito.

No se asumirá que el proveedor de infraestructura permite finalizar indefinidamente todas las operaciones antes de terminar el contenedor.

### 13.3. Creación de tablas

Se utilizará:

```python
SQLModel.metadata.create_all(engine)
```

Este mecanismo crea las tablas inexistentes, pero no realiza migraciones de estructuras ya existentes.

No se eliminarán ni recrearán automáticamente las tablas durante el arranque.

Los cambios incompatibles en el esquema de PostgreSQL requerirán un procedimiento específico de migración.

Alembic queda fuera del alcance en esta fase del desarrollo.

## 14. Streamlit como cliente HTTP

### 14.1. Configuración

Streamlit utilizará API_BASE_URL para identificar el backend.

Ejemplo local:

```dotenv
API_BASE_URL=http://localhost:8000
```

Ejemplo de producción:

```dotenv
API_BASE_URL=https://nombre-del-servicio.onrender.com
```

La URL de producción será sustituida por la dirección real del servicio desplegado.

### 14.2. Independencia

La modificación de API_BASE_URL no deberá requerir cambios en el código de Streamlit.

La interfaz no importará directamente:

- El agente LangGraph.
- Los nodos del grafo.
- Las herramientas.
- El sistema RAG.
- Los modelos de persistencia.

La comunicación con estos componentes se realizará exclusivamente mediante los endpoints de FastAPI.

### 14.3. Funcionalidades

La interfaz deberá permitir, según el perfil correspondiente:

- Comprobar el estado del backend.
- Iniciar una conversación.
- Realizar consultas textuales.
- Realizar consultas multimodales.
- Mostrar las respuestas del asistente.
- Mostrar fuentes y resultados geográficos.
- Aprobar o rechazar planes.
- Gestionar el thread_id.
- Consultar el historial persistente autorizado.
- Registrar usuarios e iniciar sesión.
- Gestionar y seleccionar API keys propias.
- Mostrar errores controlados.

### 14.4. Timeout del cliente

El timeout HTTP de Streamlit deberá ser superior al timeout configurado en el backend, con un margen suficiente para la transmisión y el procesamiento adicional de la petición.

Se propone un valor inicial de 90 segundos para las consultas del asistente.

Los endpoints que no requieren ejecución del agente podrán utilizar tiempos de espera inferiores.

Los arranques en frío de Render pueden requerir un tratamiento específico.

No se repetirán automáticamente peticiones POST que hayan terminado en timeout, ya que la ejecución anterior podría haber comenzado.

## 15. Persistencia durante reinicios y redespliegues

### 15.1. Recursos persistentes

| Recurso | Conservación tras redeploy |
|---|---|
| Usuarios | Sí |
| API keys | Sí |
| Conversaciones | Sí |
| Mensajes SQL | Sí |
| Corpus documental versionado | Sí, mediante la imagen |
| Embeddings precalculados | Sí, mediante la imagen |
| Índice ChromaDB | Disponible en la nueva imagen |

La persistencia relacional depende de mantener la misma base de datos PostgreSQL.

### 15.2. Recursos no persistentes

| Recurso | Conservación tras redeploy |
|---|---|
| Checkpoints de MemorySaver | No |
| Aprobaciones pendientes | No |
| Sesiones de autenticación | No |
| Contadores de rate limiting | No |
| Contadores de cuotas comerciales | No |
| Bloqueos de conversaciones | No |
| Archivos temporales | No |
| Ejecuciones activas | No garantizada |

Estas pérdidas constituyen limitaciones conocidas de la arquitectura inicial.

### 15.3. Conversaciones anteriores

Los usuarios podrán consultar el historial persistido después de un redeploy.

Las conversaciones cuyo checkpoint se haya perdido no podrán continuar automáticamente desde su estado anterior.

El backend devolverá el error correspondiente cuando una operación necesite un estado no disponible.

No se reconstruirán checkpoints a partir de los mensajes SQL durante esta fase del desarrollo.

### 15.4. Validación de persistencia

Se realizará una prueba de persistencia mediante:

1. Crear o utilizar una API key válida.
2. Iniciar una conversación.
3. Resolver un turno.
4. Consultar el historial mediante la API.
5. Registrar el thread_id y el número de mensajes.
6. Ejecutar un redeploy del backend.
7. Comprobar GET /health.
8. Volver a consultar el historial con la misma API key.
9. Verificar que los mensajes permanecen disponibles.
10. Comprobar el comportamiento de una conversación que requiera un checkpoint perdido.

La prueba deberá utilizar la misma base de datos antes y después del redeploy.

## 16. Gestión de versiones

### 16.1. Ramas

| Rama | Responsabilidad |
|---|---|
| main | Versión estable y desplegable |
| develop | Integración de funcionalidades |
| feature/* | Desarrollo de funcionalidades |
| fix/* | Corrección de errores |
| docs/* | Documentación y especificaciones |

La arquitectura de ramas se mantendrá aunque el desarrollo sea individual.

### 16.2. Integración

Las funcionalidades deberán desarrollarse en ramas independientes.

Antes de integrarlas en develop:

- Revisar los cambios.
- Ejecutar las pruebas correspondientes.
- Comprobar las regresiones.
- Actualizar las especificaciones afectadas.
- Verificar que no se incorporan secretos.

La integración en main se realizará cuando la versión sea estable y desplegable.

### 16.3. Commits

Los commits deberán representar cambios coherentes y fácilmente identificables.

Se recomienda utilizar prefijos como:

- feat.
- fix.
- test.
- docs.
- refactor.
- chore.

No se mezclarán cambios funcionales no relacionados dentro de un mismo commit cuando pueda evitarse.

## 17. Integración continua — CI

### 17.1. Objetivo

Detectar errores automáticamente antes de desplegar una nueva versión.

### 17.2. Validaciones

El proceso de integración continua deberá contemplar:

1. Obtener el código del repositorio.
2. Configurar Python 3.13.2.
3. Instalar dependencias.
4. Ejecutar las pruebas automatizadas.
5. Verificar la compatibilidad de los componentes.
6. Construir la imagen Docker.
7. Comprobar que la construcción no necesita credenciales de Gemini.

### 17.3. Pruebas automatizadas

Las pruebas deberán utilizar mocks o dependencias controladas cuando intervengan servicios externos.

Las pruebas unitarias no deberán depender de credenciales reales ni consumir recursos de Gemini.

Las pruebas de integración con PostgreSQL podrán utilizar una base de datos temporal y aislada.

### 17.4. GitHub Actions

Se propone utilizar GitHub Actions para automatizar las validaciones.

Ubicación orientativa:

```text
.github/workflows/ci.yml
```

La implementación de este workflow se considera una ampliación de esta fase del desarrollo.

Aunque no se automatice completamente, las validaciones deberán realizarse y documentarse manualmente antes de desplegar.

## 18. Entrega y despliegue continuo — CD

### 18.1. Flujo de despliegue

```mermaid
flowchart LR
    A[Rama de trabajo] --> B[Pruebas]
    B --> C[Pull Request a develop]
    C --> D[Validacion de integracion]
    D --> E[Pull Request a main]
    E --> F[Build Docker en Render]
    F --> G[Health check]
    G --> H[Servicio desplegado]
```

### 18.2. Despliegue automático

Render se vinculará al repositorio GitHub y a la rama main.

Los cambios integrados en main podrán desencadenar automáticamente una nueva construcción y despliegue.

Cuando exista integración continua automatizada, se configurará el despliegue para ejecutarse después de superar las comprobaciones requeridas.

### 18.3. Despliegue manual

El despliegue manual se utilizará cuando sea necesario:

- Reproducir una incidencia.
- Validar la persistencia.
- Desplegar una versión concreta.
- Recuperar el servicio.
- Realizar comprobaciones controladas.

### 18.4. Trazabilidad

Se registrará:

- Commit desplegado.
- Fecha del despliegue.
- Resultado de las comprobaciones.
- Estado del servicio.
- Incidencias detectadas.
- Versión anterior estable.

## 19. Rollback

### 19.1. Objetivo

Recuperar una versión estable del backend cuando una nueva versión introduzca errores.

### 19.2. Procedimiento

1. Identificar la incidencia.
2. Consultar los logs.
3. Identificar la última versión estable.
4. Ejecutar el rollback correspondiente.
5. Verificar GET /health.
6. Comprobar la autenticación.
7. Comprobar el historial persistente.
8. Corregir la causa del problema en una rama independiente.
9. Validar y desplegar nuevamente.

Si el rollback deshabilita los despliegues automáticos, deberán reactivarse de manera controlada después de solucionar la incidencia.

### 19.3. Limitaciones

Un rollback del backend no revierte automáticamente las modificaciones realizadas en PostgreSQL.

El código recuperado debe ser compatible con la estructura actual de la base de datos.

Tampoco recupera los checkpoints, sesiones ni contadores almacenados previamente en memoria.

## 20. Gestión de costes

### 20.1. Componentes de coste

| Componente | Factor principal |
|---|---|
| Render Web Service | Capacidad de CPU y memoria |
| Render PostgreSQL | Tipo de instancia y almacenamiento |
| Gemini | Tokens de entrada, salida y operaciones multimodales |
| Embeddings | Generación de vectores |
| Docker | Construcción y almacenamiento de imágenes |
| Transferencia de datos | Volumen de tráfico |
| Almacenamiento adicional | Capacidad y persistencia |

### 20.2. Coste fijo

El coste fijo mensual será la suma de los recursos de infraestructura contratados.

```text
Coste fijo = backend + PostgreSQL + otros servicios contratados
```

### 20.3. Coste variable

El coste variable dependerá principalmente de la utilización de Gemini.

```text
Coste por consulta =
    coste de embeddings
    + coste de tokens de entrada
    + coste de tokens de salida
    + coste de análisis multimodal
    + otros costes asociados
```

Una consulta puede generar varias llamadas al modelo.

El número de consultas HTTP no representa necesariamente el número de llamadas facturables.

### 20.4. Estimación mensual

```text
Coste mensual estimado =
    coste fijo mensual
    + número de consultas mensuales
      × coste medio por consulta
```

El coste medio deberá calcularse mediante consultas representativas.

Se distinguirán, cuando resulte posible:

- Consultas textuales simples.
- Consultas compuestas.
- Consultas multimodales.
- Consultas deterministas.
- Abstenciones.
- Consultas con HITL.

### 20.5. Medidas de reducción de costes

- Filtrado de dominio antes de ejecutar el asistente.
- Reutilización de embeddings existentes.
- Uso de rutas deterministas.
- Límites de rondas y llamadas a herramientas.
- Prevención de llamadas duplicadas.
- Interrupción del flujo multimodal fuera de dominio.
- Cuotas comerciales.
- Rate limiting HTTP.
- Restricción de ejecuciones simultáneas.
- Control de emisión de API keys.
- Reducción de contexto innecesario.
- Configuración adecuada de timeouts y reintentos.

Los límites de consumo del proveedor de Gemini deberán utilizarse como protección adicional cuando estén disponibles.

Las cuotas por API key no representan por sí solas un límite económico global.

### 20.6. Evidencias económicas

El informe técnico deberá incluir:

- Tarifas de infraestructura consultadas.
- Modelo Gemini utilizado.
- Tarifas aplicables al modelo.
- Consumo observado en consultas representativas.
- Estimación económica mensual.
- Hipótesis utilizadas en el cálculo.
- Limitaciones de la estimación.

Los precios se consultarán en las fuentes oficiales durante la validación final.

No se utilizarán tarifas desactualizadas ni estimaciones presentadas como costes reales.

## 21. Escalabilidad

### 21.1. Arquitectura inicial

La primera versión utilizará:

- Una instancia de Render.
- Un proceso de Uvicorn.
- Un worker del asistente.
- PostgreSQL gestionado.
- ChromaDB local.
- MemorySaver.
- Sesiones y cuotas almacenadas en memoria.

Esta configuración prioriza la simplicidad, el control del consumo y la estabilidad.

### 21.2. Escalado vertical

Consiste en aumentar los recursos de la instancia existente.

Puede incluir:

- Mayor memoria RAM.
- Mayor capacidad de CPU.
- Mayor capacidad de almacenamiento.
- Mayor capacidad de conexiones a PostgreSQL.

El escalado vertical puede realizarse sin distribuir necesariamente los estados entre varias instancias.

### 21.3. Incremento de workers

El número de workers del asistente podrá aumentarse después de validar:

- Consumo de memoria.
- Latencia.
- Consistencia de checkpoints.
- Seguridad de los recursos compartidos.
- Cuotas de Gemini.
- Capacidad de PostgreSQL.

No se aumentará el número de workers exclusivamente para reducir los tiempos de espera sin evaluar sus consecuencias.

### 21.4. Escalado horizontal

Consiste en ejecutar varias instancias del backend.

La arquitectura actual no permite escalar horizontalmente de forma segura sin realizar modificaciones adicionales.

Los siguientes recursos deberían externalizarse o coordinarse:

| Recurso actual | Posible evolución |
|---|---|
| MemorySaver | Checkpoints persistentes compartidos |
| Sesiones en memoria | Almacenamiento compartido de sesiones |
| Rate limiting en memoria | Contadores distribuidos |
| Cuotas comerciales | Registro persistente de consumo |
| Bloqueos por conversación | Bloqueos distribuidos |
| ChromaDB local | Estrategia de distribución o servicio vectorial compartido |

La incorporación de Redis, checkpoints persistentes o servicios vectoriales externos queda fuera del alcance inicial.

### 21.5. Redespliegues

Aunque se configure una única instancia, el proveedor puede mantener temporalmente la versión anterior y la nueva durante un redeploy.

Los recursos almacenados en memoria no se compartirán entre ambas ejecuciones.

Los redeploys deberán considerarse puntos de pérdida del estado operativo del agente.

## 22. Limitaciones de infraestructura

Los planes gratuitos de alojamiento pueden presentar restricciones relacionadas con:

- Memoria disponible.
- Capacidad de CPU.
- Arranques en frío.
- Suspensión por inactividad.
- Tiempo de disponibilidad.
- Capacidad de almacenamiento.
- Duración de la base de datos.
- Copias de seguridad.
- Transferencia de datos.

Estas restricciones deberán comprobarse antes de seleccionar el plan de despliegue.

La persistencia de PostgreSQL frente a un reinicio del backend no implica que la base de datos tenga una duración indefinida ni que disponga de copias de seguridad.

El plan seleccionado deberá permanecer disponible durante todo el periodo de evaluación.

Se documentará la estrategia de conservación de los datos si el servicio contratado tiene fecha de caducidad.

## 23. Gestión de incidencias

Se documentarán, como mínimo, tres escenarios de fallo y sus procedimientos de diagnóstico.

### 23.1. PostgreSQL no disponible

Posibles causas:

- DATABASE_URL incorrecta.
- Credenciales inválidas.
- Base de datos suspendida.
- Restricciones de red.
- Servicio no disponible.

Comprobaciones:

- Configuración de conexión.
- Logs del backend.
- Estado de PostgreSQL.
- Resultado de GET /health.

### 23.2. Backend no disponible

Posibles causas:

- Error durante la construcción Docker.
- Dependencias incompatibles.
- Puerto incorrecto.
- Fallo de inicialización.
- Memoria insuficiente.

Comprobaciones:

- Logs de construcción.
- Logs de ejecución.
- Configuración de PORT.
- Estado del servicio Render.
- Resultado del health check.

### 23.3. Fallo del asistente

Posibles causas:

- Timeout.
- Cuota de Gemini agotada.
- Credenciales externas incorrectas.
- Fallo del servicio municipal.
- Estado de conversación inconsistente.

Comprobaciones:

- request_id.
- thread_id.
- Código HTTP.
- Código de error.
- Duración de la petición.
- Disponibilidad de servicios externos.

No se documentarán como incidencias reales aquellos escenarios que únicamente se hayan planteado de forma teórica.

## 24. Pruebas de despliegue

### 24.1. Validación local

- Instalación correcta de dependencias.
- Ejecución de pruebas unitarias.
- Ejecución de pruebas de integración.
- Creación de tablas PostgreSQL.
- Construcción de la imagen Docker.
- Arranque del contenedor.
- Disponibilidad de GET /health.
- Acceso a Swagger.
- Comunicación entre Streamlit y FastAPI.

### 24.2. Validación de seguridad

| Código HTTP esperado | Comprobación |
|---|---|
| 401 | Petición sin credenciales obligatorias |
| 403 | Operación sin permisos suficientes |
| 404 | Acceso a conversación ajena |
| 409 | Conflicto de estado HITL |
| 429 | Superación del rate limiting |
| 504 | Ejecución superior al timeout |

Las pruebas de rate limiting podrán realizarse sobre endpoints que no invoquen Gemini.

El timeout deberá validarse mediante una ejecución controlada que supere el límite configurado.

### 24.3. Validación en Render

- Construcción correcta del servicio.
- Arranque del backend.
- Conexión con PostgreSQL.
- Acceso a la URL pública HTTPS.
- Disponibilidad de GET /health.
- Acceso a Swagger.
- Autenticación.
- Consulta textual válida.
- Consulta multimodal válida.
- HITL.
- Recuperación de historial.
- Comunicación con Streamlit local.
- Registro de peticiones en logs.
- Persistencia del historial después de un redeploy.

### 24.4. Evidencias

Se conservarán evidencias de las comprobaciones realizadas.

Las evidencias podrán incluir:

- Capturas de Swagger.
- Respuestas HTTP.
- Salidas de terminal.
- Resultados de pytest.
- Logs sanitizados.
- Capturas del estado del despliegue.
- Comprobaciones de PostgreSQL.
- Comparaciones del historial antes y después de un redeploy.

Las evidencias no incluirán secretos.

## 25. Criterios de aceptación

- El entorno del proyecto es reproducible.
- El backend puede ejecutarse mediante Docker.
- La imagen Docker no contiene credenciales.
- La imagen incluye los recursos necesarios del RAG.
- El índice ChromaDB puede reconstruirse sin generar nuevos embeddings.
- PostgreSQL se ejecuta independientemente del backend.
- FastAPI se despliega correctamente en Render.
- El backend utiliza el puerto configurado por Render.
- GET /health permite comprobar el estado del servicio.
- Swagger está disponible mediante HTTPS.
- Streamlit se comunica con el backend mediante HTTP.
- El cambio de entorno no requiere modificar el código de Streamlit.
- Se utiliza un único proceso de Uvicorn.
- Se utiliza inicialmente un único worker del asistente.
- El historial SQL sobrevive a un redeploy.
- La pérdida de estados en memoria tras un redeploy está documentada.
- Los secretos se gestionan mediante variables de entorno.
- Los entornos de desarrollo y producción están aislados.
- El procedimiento de despliegue y rollback es reproducible.

## 26. Fuera de alcance inicial

- Kubernetes.
- Redis.
- Múltiples réplicas del backend.
- Checkpoints de LangGraph en PostgreSQL.
- Migraciones automatizadas mediante Alembic.
- Infraestructura como código avanzada.
- Balanceadores gestionados específicamente por el proyecto.
- Sistemas externos avanzados de monitorización.
- Base de datos vectorial en la nube.
- Despliegue del RAG como servicio independiente.
- Despliegue independiente de Streamlit.

La incorporación de estas tecnologías deberá justificarse mediante necesidades reales del producto en futuras fases de desarrollo.