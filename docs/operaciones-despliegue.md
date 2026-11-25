# Operaciones de despliegue — ReciclaTÍA PB03

## 1. Objetivo

Documentar los procedimientos necesarios para preparar, ejecutar, desplegar y mantener la infraestructura de ReciclaTÍA.

Este documento constituye una guía operativa basada en los requisitos definidos en specs/16-despliegue.md.

Los procedimientos deberán actualizarse conforme se valide la implementación real del backend y de la infraestructura.

Los comandos correspondientes a componentes todavía no implementados constituyen procedimientos previstos, no comprobaciones realizadas.

## 2. Arquitectura de infraestructura

### 2.1. Entorno local

```mermaid
flowchart TD
    U[Navegador] --> S[Streamlit local]
    S -->|HTTP| A[FastAPI y Uvicorn]
    A --> G[LangGraph]
    G --> R[RAG y ChromaDB]
    G --> M[MemorySaver]
    A --> P[PostgreSQL en Docker]
    G --> E[Gemini]
    G --> C[API municipal]
```

### 2.2. Entorno desplegado

```mermaid
flowchart TD
    U[Navegador] --> S[Streamlit local]
    S -->|HTTPS| W[Render Web Service]

    subgraph Docker
        W --> A[FastAPI y Uvicorn]
        A --> T[ThreadPoolExecutor]
        T --> G[LangGraph]
        G --> M[MemorySaver]
        G --> R[RAG y ChromaDB]
    end

    A -->|Red privada| P[Render PostgreSQL]
    G --> E[Gemini]
    G --> C[API municipal de Madrid]
```

### 2.3. Distribución de componentes

| Componente | Desarrollo local | Producción |
|---|---|---|
| FastAPI | Entorno virtual o Docker | Render Web Service |
| Uvicorn | Proceso local o contenedor | Contenedor Docker |
| PostgreSQL | Contenedor Docker independiente | Render PostgreSQL |
| ChromaDB | Sistema de archivos local | Interior del contenedor del backend |
| LangGraph | Proceso del backend | Proceso del backend |
| MemorySaver | Memoria del proceso | Memoria del proceso |
| Streamlit | Ejecución local | Cliente local conectado mediante HTTPS |
| Gemini | Servicio externo | Servicio externo |
| API municipal | Servicio externo | Servicio externo |

## 3. Requisitos previos

El entorno de desarrollo deberá disponer de:

- Python 3.13.2.
- Git.
- Entorno virtual Python.
- Docker.
- Docker Compose, si se utiliza.
- Acceso al repositorio GitHub.
- Cuenta de Render.
- Credenciales autorizadas de Gemini.
- Recursos documentales del proyecto.
- Dependencias declaradas en requirements.txt.

## 4. Preparación del repositorio

### 4.1. Clonación

```bash
git clone https://github.com/alex-bometon/pb03_equipo18.git
cd pb03_equipo18
```

Este procedimiento únicamente será necesario cuando no exista una copia local del repositorio.

### 4.2. Comprobación de la rama

```bash
git branch --show-current
git status
```

Para las operaciones de despliegue deberá utilizarse una versión estable previamente validada.

### 4.3. Identificación de versión

```bash
git rev-parse HEAD
```

El identificador obtenido permitirá relacionar las comprobaciones y despliegues con una versión concreta del código.

## 5. Preparación del entorno Python

### 5.1. Comprobación de versión

```bash
python --version
```

La versión esperada será Python 3.13.2.

### 5.2. Creación del entorno virtual

Cuando no exista un entorno virtual previamente configurado:

```bash
python -m venv .venv
```

### 5.3. Activación en macOS y Linux

```bash
source .venv/bin/activate
```

### 5.4. Activación en Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### 5.5. Instalación de dependencias

```bash
python -m pip install -r requirements.txt
```

No se actualizarán indiscriminadamente las dependencias del proyecto.

### 5.6. Validación de dependencias

```bash
python -m pip check
```

Esta comprobación permitirá identificar incompatibilidades entre las dependencias instaladas.

### 5.7. Registro de versiones

```bash
python -m pip list
```

Las versiones efectivamente utilizadas deberán documentarse durante la validación final.

## 6. Configuración de variables de entorno

### 6.1. Configuración local

El archivo .env permitirá configurar el entorno de desarrollo sin incorporar credenciales al código fuente.

Una vez exista .env.example:

```bash
cp .env.example .env
```

Este comando no deberá ejecutarse sobre un archivo .env existente sin comprobar previamente su contenido, puesto que podría sobrescribir la configuración local.

### 6.2. Configuración general del backend

| Variable | Responsabilidad |
|---|---|
| PORT | Puerto del servidor |
| DATABASE_URL | Cadena de conexión con PostgreSQL |
| GEMINI_API_KEY | Credencial del proveedor Gemini |
| API_KEY | Credencial de aprovisionamiento administrativo |
| CORS_ORIGINS | Orígenes web autorizados |
| LOG_LEVEL | Nivel de logging |
| AGENT_MAX_WORKERS | Número de workers del asistente |
| ASK_TIMEOUT_SECONDS | Timeout del asistente |

### 6.3. Configuración del frontend

| Variable | Responsabilidad |
|---|---|
| API_BASE_URL | Dirección del backend FastAPI |

### 6.4. Configuración adicional

Los parámetros de autenticación, sesiones, cuotas, emisión de API keys y procesamiento multimedia deberán configurarse conforme a:

- specs/14-autenticacion-autorizacion.md.
- specs/15-robustez-observabilidad.md.

No se establecerán valores contradictorios en este documento.

### 6.5. Separación de entornos

Desarrollo, pruebas y producción deberán utilizar configuraciones independientes.

No se utilizará la base de datos de producción como base de datos ordinaria de pruebas.

### 6.6. Protección de secretos

Los archivos .env no deberán incorporarse al repositorio.

No se mostrarán credenciales reales en comandos documentados, capturas de pantalla, registros o evidencias de entrega.

## 7. Preparación del índice vectorial

### 7.1. Recursos necesarios

Deberán estar disponibles:

```text
data/raw/
output/chunks.json
output/embeddings.json
```

### 7.2. Reconstrucción del índice

```bash
python main.py rag index --yes
```

Este procedimiento utilizará los artefactos existentes para reconstruir el índice ChromaDB.

### 7.3. Resultado esperado

```text
output/chroma_db/
```

Deberá contener un índice compatible con la configuración documental del proyecto.

### 7.4. Restricciones

No se ejecutará sistemáticamente el pipeline completo de generación de embeddings durante los despliegues.

La reconstrucción desde artefactos existentes no deberá necesitar credenciales de Gemini.

### 7.5. Actualización documental

Si se modifican los documentos originales o el modelo de embeddings, deberá ejecutarse el procedimiento de actualización correspondiente antes de preparar una nueva imagen.

La reconstrucción del índice no constituye por sí sola una actualización documental.

Los requisitos del pipeline se definen en specs/01-retrieval.md.

## 8. PostgreSQL local

### 8.1. Arquitectura

PostgreSQL se ejecutará en un contenedor Docker independiente.

El backend podrá conectarse a esta base de datos desde:

- El entorno virtual local.
- Otro contenedor Docker.
- Una red gestionada mediante Docker Compose.

### 8.2. Versión de PostgreSQL

La versión principal de PostgreSQL deberá seleccionarse antes de comenzar las pruebas de integración.

Se utilizará una versión compatible con la instancia que se configure posteriormente en Render.

No se utilizará la etiqueta latest como referencia definitiva.

Los siguientes comandos emplean POSTGRES_IMAGE como variable que deberá contener la imagen y etiqueta seleccionadas.

### 8.3. Configuración

Se preparará una configuración local que contenga:

```dotenv
POSTGRES_DB=reciclatia
POSTGRES_USER=reciclatia
POSTGRES_PASSWORD=CONTRASENA_LOCAL
```

CONTRASENA_LOCAL representa un valor ilustrativo que deberá sustituirse por una contraseña adecuada.

### 8.4. Creación del volumen

```bash
docker volume create reciclatia-postgres-data
```

El volumen permitirá conservar los datos aunque se detenga o recree el contenedor.

### 8.5. Creación de una red

```bash
docker network create reciclatia-network
```

La red permitirá la comunicación entre el backend y PostgreSQL cuando ambos se ejecuten mediante Docker.

Si la red ya existe, no será necesario crearla nuevamente.

### 8.6. Creación del contenedor

Una vez seleccionada la imagen y preparado el archivo de entorno de PostgreSQL:

```bash
docker run -d \
  --name reciclatia-postgres \
  --network reciclatia-network \
  --env-file .env.postgres \
  -p 127.0.0.1:5432:5432 \
  -v reciclatia-postgres-data:/var/lib/postgresql/data \
  "$POSTGRES_IMAGE"
```

La ruta interna de almacenamiento del volumen deberá comprobarse contra la versión seleccionada de la imagen oficial de PostgreSQL.

El archivo .env.postgres deberá existir y quedar excluido del control de versiones.

### 8.7. Comprobación del contenedor

```bash
docker ps
```

### 8.8. Disponibilidad de PostgreSQL

```bash
docker exec reciclatia-postgres \
  pg_isready -U reciclatia -d reciclatia
```

La disponibilidad del servidor PostgreSQL no garantiza por sí sola que las credenciales y permisos utilizados por el backend sean correctos.

### 8.9. Consulta de registros

```bash
docker logs reciclatia-postgres
```

### 8.10. Conexión desde el entorno virtual

La cadena de conexión tendrá la siguiente estructura:

```text
postgresql://usuario:password@localhost:5432/reciclatia
```

### 8.11. Conexión desde otro contenedor

Cuando el backend se ejecute dentro de la misma red Docker:

```text
postgresql://usuario:password@reciclatia-postgres:5432/reciclatia
```

localhost dentro de un contenedor hace referencia al propio contenedor.

No deberá utilizarse localhost para acceder a PostgreSQL desde otro contenedor independiente.

### 8.12. Normalización de DATABASE_URL

El backend deberá admitir la normalización de cadenas de conexión que utilicen postgres:// al formato compatible con el driver de SQLAlchemy seleccionado.

La normalización deberá realizarse sin exponer la cadena de conexión en los registros.

## 9. Ejecución local de FastAPI

### 9.1. Preparación

Antes de iniciar FastAPI deberán estar disponibles:

- El entorno virtual.
- Las dependencias del backend.
- Las variables de entorno.
- PostgreSQL.
- El índice ChromaDB.

### 9.2. Arranque

Una vez implementado api/main.py:

```bash
python -m uvicorn api.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1
```

### 9.3. Modo de desarrollo

Durante el desarrollo podrá utilizarse:

```bash
python -m uvicorn api.main:app --reload
```

La recarga automática reinicia el proceso cuando detecta modificaciones del código.

Esto puede provocar la pérdida de checkpoints, sesiones y contadores almacenados en memoria.

No se utilizará este modo para la validación final de persistencia ni en producción.

### 9.4. Comprobación de disponibilidad

```bash
curl -i http://localhost:8000/health
```

Respuesta esperada cuando el servicio se encuentre operativo:

```json
{
  "status": "ok",
  "storage": "postgres"
}
```

### 9.5. Documentación interactiva

```text
http://localhost:8000/docs
```

### 9.6. Especificación OpenAPI

```text
http://localhost:8000/openapi.json
```

### 9.7. Inicialización relacional

La inicialización del backend deberá crear las tablas inexistentes mediante los mecanismos establecidos en la especificación de persistencia.

No será necesario crear manualmente todas las tablas antes del primer arranque.

SQLModel.metadata.create_all() no modifica automáticamente estructuras existentes mediante migraciones.

## 10. Ejecución local de Streamlit

### 10.1. Configuración

```dotenv
API_BASE_URL=http://localhost:8000
```

### 10.2. Arranque

```bash
python -m streamlit run app.py
```

### 10.3. Acceso

Dirección local habitual:

```text
http://localhost:8501
```

### 10.4. Comprobaciones

Deberá verificarse:

- Disponibilidad del backend.
- Comunicación mediante HTTP.
- Acceso anónimo o autenticado.
- Envío de consultas.
- Recepción de respuestas.
- Gestión de conversaciones.
- Resolución HITL.
- Presentación de fuentes.
- Consulta de historial autorizado.

### 10.5. Independencia

Streamlit no deberá necesitar acceso directo a PostgreSQL, ChromaDB o Gemini.

El backend deberá encontrarse operativo para proporcionar las funcionalidades del asistente.

## 11. Construcción de la imagen Docker

### 11.1. Imagen base

El Dockerfile utilizará como referencia:

```dockerfile
FROM python:3.13.2-slim
```

### 11.2. Secuencia de construcción

La construcción deberá contemplar:

1. Selección de la imagen base.
2. Configuración del directorio de trabajo.
3. Copia de requirements.txt.
4. Instalación de dependencias.
5. Copia del código y corpus necesario.
6. Copia de chunks y embeddings existentes.
7. Reconstrucción del índice ChromaDB.
8. Preparación de directorios temporales.
9. Configuración del comando de arranque.

### 11.3. Reconstrucción del índice

El Dockerfile deberá ejecutar el procedimiento equivalente a:

```dockerfile
RUN python main.py rag index --yes
```

### 11.4. Comando de arranque

Comando de referencia:

```dockerfile
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

El puerto deberá adaptarse a la configuración del entorno de ejecución.

### 11.5. Construcción local

Una vez implementado y validado el Dockerfile:

```bash
docker build -t reciclatia-api:local .
```

### 11.6. Identificación de la imagen

```bash
docker images reciclatia-api
```

### 11.7. Tamaño de imagen

El tamaño de la imagen deberá revisarse para detectar dependencias o recursos innecesarios.

No se eliminarán recursos obligatorios del RAG únicamente para reducir el tamaño.

### 11.8. Protección de secretos

La imagen deberá poder construirse sin proporcionar GEMINI_API_KEY ni credenciales de PostgreSQL.

Los secretos se proporcionarán durante la ejecución del contenedor.

## 12. Configuración de Dockerignore

El archivo .dockerignore deberá excluir los recursos innecesarios o sensibles durante la construcción.

Contenido de referencia:

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

Los patrones deberán ajustarse a la estructura real del repositorio.

Deberán conservarse dentro del contexto de construcción:

```text
data/raw/
output/chunks.json
output/embeddings.json
```

El índice local de ChromaDB se excluirá porque deberá reconstruirse dentro de la imagen.

.dockerignore no sustituye a .gitignore.

## 13. Ejecución del backend mediante Docker

### 13.1. Preparación

El contenedor PostgreSQL deberá encontrarse operativo dentro de la red correspondiente.

Se preparará una configuración del backend que utilice el nombre del contenedor PostgreSQL en DATABASE_URL.

### 13.2. Arranque

```bash
docker run -d \
  --name reciclatia-api \
  --network reciclatia-network \
  --env-file .env.docker \
  -p 127.0.0.1:8000:8000 \
  reciclatia-api:local
```

El archivo .env.docker deberá contener la configuración necesaria para ejecutar el backend dentro de Docker, incluyendo el puerto 8000 para este ejemplo.

No deberá versionarse.

### 13.3. Comprobación

```bash
docker ps
```

### 13.4. Registros

```bash
docker logs -f reciclatia-api
```

### 13.5. Health check

```bash
curl -i http://localhost:8000/health
```

### 13.6. Inspección del consumo

```bash
docker stats reciclatia-api reciclatia-postgres
```

### 13.7. Validación del índice

Cuando resulte necesario comprobar la existencia de los recursos vectoriales dentro del contenedor:

```bash
docker exec reciclatia-api ls -lh output/chroma_db
```

La existencia del directorio no constituye por sí sola una garantía de funcionamiento del índice.

## 14. Docker Compose

### 14.1. Finalidad

Docker Compose podrá utilizarse para coordinar la ejecución local de FastAPI y PostgreSQL.

### 14.2. Servicios previstos

| Servicio | Responsabilidad |
|---|---|
| api | Backend ReciclaTÍA |
| db | PostgreSQL |

La configuración podrá incluir:

- Red interna.
- Volumen persistente de PostgreSQL.
- Variables de entorno.
- Healthchecks.
- Dependencias de arranque.

### 14.3. Arranque coordinado

Una vez implementado el archivo de configuración correspondiente:

```bash
docker compose up -d --build
```

### 14.4. Estado de los servicios

```bash
docker compose ps
```

### 14.5. Registros

```bash
docker compose logs -f
```

Para consultar exclusivamente el backend:

```bash
docker compose logs -f api
```

### 14.6. Detención

```bash
docker compose stop
```

### 14.7. Eliminación de contenedores y redes

```bash
docker compose down
```

Este procedimiento conservará los volúmenes persistentes administrados por Compose salvo que se solicite expresamente su eliminación.

No se utilizará docker compose down -v como operación ordinaria, puesto que puede eliminar los datos almacenados en los volúmenes.

### 14.8. Alcance

Docker Compose constituye una herramienta opcional de desarrollo local.

Render gestionará los servicios de producción de manera independiente.

## 15. Compatibilidad de arquitecturas

### 15.1. Desarrollo local

El entorno local puede utilizar procesadores ARM64.

### 15.2. Infraestructura remota

El entorno remoto puede utilizar una arquitectura de procesador diferente.

### 15.3. Validación

La construcción satisfactoria de una imagen en el entorno local no garantiza automáticamente la compatibilidad con la plataforma remota.

Deberán comprobarse:

- Disponibilidad de la imagen base.
- Compatibilidad de dependencias.
- Arquitectura de las extensiones compiladas.
- Funcionamiento del índice vectorial.
- Construcción en Render.

### 15.4. Construcción para arquitectura específica

Cuando resulte necesario validar una imagen Linux AMD64 desde un entorno ARM64:

```bash
docker buildx build \
  --platform linux/amd64 \
  --load \
  -t reciclatia-api:amd64 .
```

Esta operación podrá requerir emulación y consumir recursos adicionales.

No sustituye la validación real del despliegue remoto.

## 16. Preparación del despliegue en Render

### 16.1. Condiciones previas

Antes de desplegar deberán estar completadas:

- Implementación de los contratos HTTP.
- Validación de autenticación y autorización.
- Validación de persistencia.
- Validación del asistente.
- Pruebas de regresión.
- Construcción local de Docker.
- Configuración segura de variables de entorno.
- Integración de la versión estable en main.

### 16.2. Servicios necesarios

| Servicio | Tipo de recurso |
|---|---|
| Backend ReciclaTÍA | Render Web Service |
| Base de datos | Render PostgreSQL |

### 16.3. Selección de infraestructura

Antes de contratar o crear los servicios deberán comprobarse:

- Memoria RAM disponible.
- Capacidad de CPU.
- Coste.
- Región.
- Tiempo de disponibilidad.
- Arranques en frío.
- Restricciones por inactividad.
- Capacidad de almacenamiento.
- Duración de PostgreSQL.
- Disponibilidad de copias de seguridad.
- Límites de transferencia.

Se priorizará una infraestructura de coste reducido compatible con la evaluación académica.

No se seleccionará automáticamente un plan gratuito sin verificar sus restricciones y la capacidad real del backend.

### 16.4. Región

El backend y PostgreSQL deberán encontrarse preferentemente en la misma región para facilitar la comunicación interna y reducir latencia.

## 17. Creación de PostgreSQL en Render

### 17.1. Procedimiento

Desde el panel de administración de Render:

1. Crear un servicio PostgreSQL.
2. Asignar un nombre identificable.
3. Seleccionar la región.
4. Seleccionar una versión compatible de PostgreSQL.
5. Seleccionar el plan correspondiente.
6. Esperar a que el servicio se encuentre disponible.
7. Localizar las cadenas de conexión proporcionadas.

### 17.2. URL interna

La URL interna será la utilizada preferentemente por el backend desplegado en Render.

Deberá configurarse mediante DATABASE_URL.

### 17.3. URL externa

La URL externa se reservará para operaciones administrativas autorizadas, como la inspección de datos desde un cliente externo.

### 17.4. Seguridad

La conexión externa deberá restringirse cuando sea posible.

No se publicarán las cadenas de conexión.

### 17.5. Persistencia

La base de datos deberá conservarse durante todo el periodo de evaluación.

La eliminación del Web Service no deberá confundirse con la eliminación del servicio PostgreSQL.

## 18. Creación del Web Service en Render

### 18.1. Configuración prevista

| Parámetro | Valor |
|---|---|
| Repositorio | alex-bometon/pb03_equipo18 |
| Rama | main |
| Runtime | Docker |
| Dockerfile | Dockerfile |
| Health Check Path | /health |
| Número de instancias | 1 |
| Procesos Uvicorn | 1 |
| Workers del asistente | 1 |

### 18.2. Procedimiento

Desde el panel de Render:

1. Crear un Web Service.
2. Vincular el repositorio GitHub.
3. Seleccionar la rama main.
4. Seleccionar Docker como entorno de ejecución.
5. Configurar la ubicación del Dockerfile.
6. Seleccionar la región correspondiente.
7. Seleccionar el plan de infraestructura.
8. Configurar las variables de entorno.
9. Configurar el health check.
10. Iniciar el despliegue.

Los nombres exactos de las opciones del panel podrán variar según la versión de la plataforma.

### 18.3. Puerto

El contenedor deberá escuchar en 0.0.0.0.

Uvicorn utilizará el valor de PORT proporcionado por el entorno de ejecución.

No se fijará exclusivamente el puerto 8000 para producción.

### 18.4. Arranque

Render construirá la imagen a partir del Dockerfile del repositorio.

El comando de arranque deberá respetar la configuración de un único proceso Uvicorn.

## 19. Variables de entorno en Render

### 19.1. Variables generales

| Variable | Configuración |
|---|---|
| DATABASE_URL | URL interna de PostgreSQL |
| GEMINI_API_KEY | Credencial autorizada |
| API_KEY | Credencial de aprovisionamiento administrativo |
| CORS_ORIGINS | Orígenes explícitamente autorizados |
| LOG_LEVEL | INFO como configuración inicial |
| AGENT_MAX_WORKERS | 1 |

### 19.2. Variables adicionales

Los valores de autenticación, límites y procesamiento multimedia deberán obtenerse de las especificaciones 14 y 15 y de la configuración centralizada del backend.

### 19.3. Secretos

Los secretos deberán configurarse en el entorno de ejecución de Render.

No se incorporarán a:

- Dockerfile.
- Argumentos de construcción.
- GitHub.
- README.md.
- Capturas de pantalla.
- Documentación pública.

### 19.4. Separación del frontend

API_BASE_URL se utilizará para configurar Streamlit.

No será necesario proporcionar al frontend DATABASE_URL ni GEMINI_API_KEY.

## 20. Primer despliegue

### 20.1. Construcción

Deberán revisarse los registros de construcción para comprobar:

- Obtención del código.
- Instalación de dependencias.
- Disponibilidad de los artefactos documentales.
- Reconstrucción de ChromaDB.
- Ausencia de errores.

### 20.2. Inicialización

Deberán revisarse los registros de ejecución para comprobar:

- Arranque de Uvicorn.
- Configuración del puerto.
- Conexión a PostgreSQL.
- Inicialización de tablas.
- Aprovisionamiento administrativo.
- Disponibilidad del índice.
- Inicialización de recursos del asistente.

### 20.3. URL pública

Una vez disponible, Render proporcionará una dirección HTTPS.

Ejemplo ilustrativo:

```text
https://nombre-del-servicio.onrender.com
```

### 20.4. Health check

```bash
curl -i https://nombre-del-servicio.onrender.com/health
```

La dirección de ejemplo deberá sustituirse por la URL real.

### 20.5. Swagger

```text
https://nombre-del-servicio.onrender.com/docs
```

### 20.6. Validación

Un despliegue no se considerará satisfactorio únicamente porque Render indique que el proceso está iniciado.

Deberán realizarse las pruebas funcionales correspondientes.

## 21. Conexión de Streamlit al backend desplegado

### 21.1. Configuración

```dotenv
API_BASE_URL=https://nombre-del-servicio.onrender.com
```

### 21.2. Ejecución

```bash
python -m streamlit run app.py
```

### 21.3. Comprobaciones

Deberá verificarse que:

- Streamlit reconoce la disponibilidad del backend.
- Las consultas se ejecutan mediante HTTPS.
- Las credenciales se transmiten conforme al contrato.
- Las conversaciones mantienen su thread_id.
- Las respuestas se representan correctamente.
- El historial autorizado puede consultarse.
- Las decisiones HITL se resuelven correctamente.

### 21.4. Independencia del código

El cambio de backend local a backend remoto deberá realizarse modificando la configuración de API_BASE_URL, sin alterar el código fuente de Streamlit.

## 22. Inspección de PostgreSQL

### 22.1. Inspección local

Podrá utilizarse psql dentro del contenedor:

```bash
docker exec -it reciclatia-postgres \
  psql -U reciclatia -d reciclatia
```

### 22.2. Listado de tablas

Desde psql:

```sql
\dt
```

### 22.3. Inspección de estructuras

```sql
\d conversation
\d message
```

### 22.4. Comprobación de registros

```sql
SELECT COUNT(*) FROM conversation;
SELECT COUNT(*) FROM message;
```

### 22.5. Inspección remota

Podrá utilizarse un cliente PostgreSQL autorizado, como pgAdmin, cuando resulte necesario verificar los datos del servicio gestionado.

Deberán utilizarse los parámetros de conexión externa correspondientes y respetar las restricciones de seguridad del proveedor.

### 22.6. Protección de datos

Las consultas destinadas a generar evidencias deberán evitar recuperar credenciales, hashes o información personal innecesaria.

No se utilizarán operaciones de modificación o eliminación para comprobar ordinariamente el estado de producción.

## 23. Redespliegue

### 23.1. Finalidad

El redeploy permitirá desplegar nuevamente una versión del backend, actualizar el código o verificar el comportamiento de la infraestructura ante reinicios.

### 23.2. Preparación

Antes de ejecutar un redeploy deberá identificarse:

- La versión actualmente desplegada.
- La versión que se desplegará.
- La base de datos utilizada.
- La compatibilidad del esquema relacional.
- La posible existencia de ejecuciones activas.
- La pérdida prevista de recursos almacenados en memoria.

### 23.3. Procedimiento

1. Confirmar que la versión candidata ha superado las pruebas necesarias.
2. Registrar el commit correspondiente.
3. Iniciar el despliegue desde Render o mediante la integración configurada.
4. Consultar los registros de construcción.
5. Consultar los registros de ejecución.
6. Comprobar GET /health.
7. Verificar las operaciones protegidas.
8. Comprobar la persistencia del historial.

### 23.4. Recursos conservados

| Recurso | Comportamiento previsto |
|---|---|
| Usuarios | Se conservan en PostgreSQL |
| API keys | Se conservan en PostgreSQL |
| Conversaciones | Se conservan en PostgreSQL |
| Mensajes | Se conservan en PostgreSQL |
| Corpus | Disponible mediante la nueva imagen |
| Embeddings | Disponibles mediante la nueva imagen |
| ChromaDB | Reconstruido o disponible en la nueva imagen |

La conservación de los datos relacionales depende de mantener la misma base de datos PostgreSQL.

### 23.5. Recursos no conservados

| Recurso | Comportamiento previsto |
|---|---|
| Checkpoints | Se pierden al reiniciar el proceso |
| Sesiones | Se pierden |
| Aprobaciones pendientes | Se pierde su estado operativo |
| Cuotas comerciales | Se reinician |
| Rate limiting | Se reinicia |
| Bloqueos | Se pierden |
| Archivos temporales | No se garantiza su conservación |
| Ejecuciones activas | No se garantiza su finalización |

### 23.6. Solapamiento de versiones

Durante un redeploy, la infraestructura puede mantener temporalmente la versión anterior y la nueva.

Los recursos almacenados en memoria no se compartirán entre ambas ejecuciones.

Esta circunstancia deberá considerarse una limitación de la arquitectura inicial.

## 24. Validación de persistencia tras redeploy

### 24.1. Preparación

Se utilizará una API key User autorizada que permita consultar el historial persistente.

### 24.2. Comprobación inicial

1. Realizar una consulta.
2. Resolver el HITL si corresponde.
3. Confirmar que el turno se encuentra resuelto.
4. Registrar el thread_id.
5. Consultar los mensajes asociados.
6. Registrar el número de mensajes y su contenido significativo, sin datos sensibles.

### 24.3. Redeploy

Ejecutar el procedimiento de redeploy manteniendo la misma base de datos PostgreSQL.

### 24.4. Comprobación posterior

1. Verificar GET /health.
2. Autenticarse nuevamente si resulta necesario.
3. Utilizar la misma API key.
4. Consultar el historial del thread_id anterior.
5. Comparar los mensajes antes y después del redeploy.
6. Comprobar el comportamiento de una operación que requiera el checkpoint perdido.

### 24.5. Resultado esperado

Los mensajes persistidos deberán continuar disponibles.

El estado operativo anterior no deberá reconstruirse automáticamente a partir del historial SQL.

Cuando la continuación requiera un checkpoint perdido, el backend deberá devolver el error correspondiente.

### 24.6. Evidencia

La comprobación deberá documentarse mediante:

- Commit desplegado.
- Fecha.
- Identificador de conversación.
- Número de mensajes anterior.
- Número de mensajes posterior.
- Resultado de la consulta de historial.
- Resultado de la operación que requiere estado operativo.

No deberán publicarse credenciales utilizadas durante la prueba.

## 25. Rollback

### 25.1. Finalidad

El rollback permitirá recuperar una versión estable del backend cuando una modificación desplegada introduzca errores.

### 25.2. Condiciones previas

Antes de recuperar una versión anterior deberá comprobarse su compatibilidad con:

- El esquema actual de PostgreSQL.
- Los recursos documentales.
- Las variables de entorno.
- Las dependencias externas.
- Los contratos necesarios para utilizar el servicio.

### 25.3. Procedimiento

1. Identificar la incidencia.
2. Consultar los registros.
3. Determinar la versión afectada.
4. Identificar la última versión estable compatible.
5. Comprobar el estado de PostgreSQL.
6. Utilizar el mecanismo de rollback disponible en Render o desplegar una versión estable preparada.
7. Verificar GET /health.
8. Comprobar la autenticación.
9. Comprobar el historial persistente.
10. Validar las operaciones principales del servicio.
11. Corregir la causa de la incidencia en una rama independiente.
12. Ejecutar las pruebas correspondientes.
13. Integrar y desplegar nuevamente la versión corregida.

### 25.4. Despliegues automáticos

Si el mecanismo de rollback deshabilita temporalmente los despliegues automáticos, deberán reactivarse de manera controlada después de resolver la incidencia.

### 25.5. Limitaciones

Un rollback del backend:

- No revierte automáticamente cambios en PostgreSQL.
- No recupera checkpoints anteriores.
- No recupera sesiones caducadas o eliminadas.
- No restaura contadores almacenados anteriormente en memoria.
- No garantiza la recuperación de ejecuciones interrumpidas.

No se eliminarán tablas ni se modificará destructivamente la base de datos como consecuencia automática de un rollback.

## 26. Detención y reinicio de servicios locales

### 26.1. Detener Streamlit o Uvicorn

Desde la terminal donde se ejecuta el proceso:

```text
Ctrl + C
```

### 26.2. Detener el contenedor del backend

```bash
docker stop reciclatia-api
```

### 26.3. Detener PostgreSQL

```bash
docker stop reciclatia-postgres
```

### 26.4. Reiniciar PostgreSQL

```bash
docker start reciclatia-postgres
```

### 26.5. Reiniciar el backend

```bash
docker start reciclatia-api
```

### 26.6. Orden recomendado

Para iniciar los servicios:

1. PostgreSQL.
2. Backend.
3. Streamlit.

Para detenerlos:

1. Streamlit.
2. Backend.
3. PostgreSQL.

Deberá evitarse detener PostgreSQL mientras el backend está persistiendo un turno.

## 27. Eliminación de recursos locales

### 27.1. Inventario

Antes de eliminar recursos deberá comprobarse qué elementos pertenecen al proyecto.

```bash
docker ps -a
docker images
docker volume ls
docker network ls
```

### 27.2. Eliminar el contenedor del backend

```bash
docker stop reciclatia-api
docker rm reciclatia-api
```

### 27.3. Eliminar el contenedor PostgreSQL

```bash
docker stop reciclatia-postgres
docker rm reciclatia-postgres
```

La eliminación del contenedor no elimina por sí sola el volumen persistente creado separadamente.

### 27.4. Eliminar la imagen del backend

```bash
docker image rm reciclatia-api:local
```

### 27.5. Eliminar la red

```bash
docker network rm reciclatia-network
```

La red deberá encontrarse libre de contenedores conectados.

### 27.6. Eliminar el volumen

La siguiente operación elimina los datos persistidos en el volumen PostgreSQL local:

```bash
docker volume rm reciclatia-postgres-data
```

Solo deberá ejecutarse cuando exista una decisión explícita de eliminar esos datos y se hayan realizado las copias necesarias.

### 27.7. Restricciones

No se utilizarán indiscriminadamente comandos globales de eliminación de recursos Docker.

La limpieza deberá limitarse a los componentes pertenecientes a ReciclaTÍA.

No deberán eliminarse imágenes, redes o volúmenes utilizados por otros proyectos.

## 28. Copias de seguridad

### 28.1. Finalidad

Las copias de seguridad permitirán conservar los datos relacionales frente a determinadas operaciones destructivas, caducidad de servicios o fallos de infraestructura.

### 28.2. Copia local de PostgreSQL

Ejemplo de exportación lógica:

```bash
docker exec reciclatia-postgres \
  pg_dump -U reciclatia -d reciclatia \
  > reciclatia-backup.sql
```

### 28.3. Verificación

La existencia de un archivo exportado no garantiza que la copia pueda restaurarse correctamente.

Las copias importantes deberán verificarse mediante procedimientos de restauración sobre una base de datos aislada.

### 28.4. Producción

Los mecanismos de copia y conservación de PostgreSQL en Render dependerán del plan contratado.

Deberá comprobarse su disponibilidad antes de confiar en ellos.

### 28.5. Protección

Las copias de PostgreSQL podrán contener datos personales y hashes de credenciales.

No deberán incorporarse al repositorio público ni a las evidencias de entrega.

Se almacenarán exclusivamente en ubicaciones autorizadas.

### 28.6. Alcance

Una copia de PostgreSQL no incluye automáticamente los checkpoints de MemorySaver, las sesiones ni los contadores almacenados en memoria.

## 29. Eliminación de recursos en Render

### 29.1. Condiciones

La eliminación de recursos remotos únicamente deberá realizarse cuando:

- Haya finalizado el periodo durante el cual se necesita el servicio.
- Se hayan conservado los datos necesarios.
- Se hayan documentado las evidencias correspondientes.
- Se haya autorizado expresamente la eliminación.

### 29.2. Web Service

La eliminación del Web Service retirará el backend desplegado.

### 29.3. PostgreSQL

La eliminación de PostgreSQL constituye una operación destructiva sobre los datos relacionales.

No deberá realizarse automáticamente al eliminar el Web Service.

### 29.4. Credenciales

Las credenciales que ya no resulten necesarias deberán desactivarse o revocarse conforme a su finalidad.

## 30. Supervisión operativa

Durante la ejecución local y remota deberá revisarse:

- Disponibilidad del backend.
- Disponibilidad de PostgreSQL.
- Consumo de memoria.
- Consumo de CPU.
- Duración de las peticiones.
- Errores HTTP.
- Timeouts.
- Rechazos por falta de capacidad.
- Consumo de Gemini.
- Espacio de almacenamiento.
- Estado de los servicios externos.

Los requisitos de observabilidad se definen en specs/15-robustez-observabilidad.md.

Los procedimientos específicos de diagnóstico se documentarán en docs/gestion-incidencias.md.

## 31. Gestión de costes de infraestructura

### 31.1. Selección de servicios

La selección del plan de despliegue deberá considerar conjuntamente:

- Coste del backend.
- Coste de PostgreSQL.
- Recursos disponibles.
- Consumo del proveedor de inferencia.
- Transferencia de datos.
- Almacenamiento.

### 31.2. Seguimiento

Durante las pruebas de despliegue deberán registrarse las condiciones económicas de los servicios utilizados.

### 31.3. Límites

Las cuotas por API key no constituyen por sí solas un límite económico global.

Deberán configurarse las protecciones adicionales del proveedor de inferencia cuando estén disponibles.

### 31.4. Documentación económica

Los precios consultados, hipótesis de consumo, cálculos y estimaciones mensuales deberán documentarse en entregables/informe_decisiones.md.

No se incorporarán precios estáticos a este procedimiento como si constituyeran tarifas permanentemente vigentes.

## 32. Trazabilidad de despliegues

Cada despliegue relevante deberá registrar:

| Campo | Información |
|---|---|
| Commit | Identificador del código desplegado |
| Rama | Rama de origen |
| Fecha | Fecha de despliegue |
| Entorno | Local o Render |
| Imagen | Identificación de la imagen cuando corresponda |
| PostgreSQL | Versión y entorno utilizado |
| Health check | Resultado |
| Pruebas funcionales | Resultado de las comprobaciones |
| Estado | Satisfactorio, fallido o pendiente |
| Incidencias | Problemas observados |
| Versión anterior | Última versión estable identificada |

Los resultados concretos deberán almacenarse dentro de la documentación de entrega.

## 33. Lista de comprobación previa al despliegue

- [ ] Versión candidata identificada.
- [ ] Especificaciones actualizadas.
- [ ] Dependencias compatibles con Python 3.13.2.
- [ ] Pruebas unitarias superadas.
- [ ] Pruebas de integración superadas.
- [ ] Pruebas de regresión superadas.
- [ ] PostgreSQL validado.
- [ ] Construcción Docker satisfactoria.
- [ ] Índice reconstruido sin regenerar embeddings.
- [ ] Ausencia de secretos en la imagen.
- [ ] Variables de entorno configuradas.
- [ ] Configuración de un proceso Uvicorn.
- [ ] Configuración inicial de un worker del asistente.
- [ ] Health check configurado.
- [ ] Compatibilidad de la versión con PostgreSQL.
- [ ] Plan de infraestructura adecuado.
- [ ] Versión integrada en main.

## 34. Lista de comprobación posterior al despliegue

- [ ] Construcción remota satisfactoria.
- [ ] Backend iniciado.
- [ ] PostgreSQL disponible.
- [ ] ChromaDB disponible.
- [ ] GET /health satisfactorio.
- [ ] Swagger disponible.
- [ ] Autenticación funcional.
- [ ] Consultas textuales funcionales.
- [ ] Consultas multimodales autorizadas funcionales.
- [ ] HITL funcional.
- [ ] Historial persistente disponible.
- [ ] Streamlit conectado mediante HTTPS.
- [ ] Errores controlados.
- [ ] Registros disponibles.
- [ ] Consumo de recursos revisado.
- [ ] Persistencia tras redeploy comprobada.
- [ ] Evidencias registradas.

Estas listas representan comprobaciones pendientes hasta que se ejecuten sobre una versión concreta del producto.

## 35. Referencias

### Documentación del proyecto

- [Arquitectura MLOps](../specs/11-arquitectura-mlops.md)
- [Contratos HTTP](../specs/12-contratos-http.md)
- [Persistencia](../specs/13-persistencia.md)
- [Autenticación y autorización](../specs/14-autenticacion-autorizacion.md)
- [Robustez y observabilidad](../specs/15-robustez-observabilidad.md)
- [Despliegue e infraestructura](../specs/16-despliegue.md)
- [Flujo de desarrollo](flujo-desarrollo.md)
- [Gestión de incidencias](gestion-incidencias.md)
- [Plan de pruebas](plan-pruebas.md)
- [Plan de trabajo PB03](plan-trabajo-pb03.md)
- [Informe de decisiones](../entregables/informe_decisiones.md)

### Documentación técnica oficial

- [Docker](https://docs.docker.com/)
- [PostgreSQL](https://www.postgresql.org/docs/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Uvicorn](https://www.uvicorn.org/)
- [SQLModel](https://sqlmodel.tiangolo.com/)
- [Render](https://render.com/docs)
- [Streamlit](https://docs.streamlit.io/)