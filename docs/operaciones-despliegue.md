# Operaciones de despliegue — ReciclaTÍA PB03

## 1. Preparación del entorno

Los requisitos de infraestructura se establecen en [16-despliegue.md](../specs/16-despliegue.md).

Se necesitarán Python 3.13.2, Git, Docker, acceso a GitHub y Render, y credenciales autorizadas de Gemini.

### 1.1. Repositorio y dependencias

Si no existe una copia local:

```bash
git clone https://github.com/alex-bometon/pb03_equipo18.git
cd pb03_equipo18
```

Comprobar la versión de trabajo:

```bash
git branch --show-current
git status
git rev-parse HEAD
python --version
```

Crear el entorno virtual si todavía no existe:

```bash
python -m venv .venv
```

Activación en macOS y Linux:

```bash
source .venv/bin/activate
```

Activación en Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Instalar y comprobar las dependencias:

```bash
python -m pip install -r requirements.txt
python -m pip check
```

### 1.2. Configuración

Crear .env a partir de .env.example únicamente si no existe una configuración previa.

```bash
cp -n .env.example .env
```

Las variables se establecerán conforme a las especificaciones 14, 15 y 16.

Se utilizarán configuraciones independientes para desarrollo, pruebas y producción.

Los archivos .env y sus variantes con secretos no se versionarán.

### 1.3. Índice documental

Comprobar la disponibilidad de:

```text
data/raw/
output/chunks.json
output/embeddings.json
```

Cuando sea necesario reconstruir ChromaDB:

```bash
python main.py rag index --yes
```

El índice se generará en output/chroma_db/.

No se regenerarán los embeddings durante cada instalación o despliegue.

## 2. PostgreSQL local

### 2.1. Configuración

Seleccionar una versión de PostgreSQL compatible con la infraestructura prevista en Render.

No se utilizará latest como etiqueta definitiva.

Preparar .env.postgres:

```dotenv
POSTGRES_DB=reciclatia
POSTGRES_USER=reciclatia
POSTGRES_PASSWORD=CONTRASENA_LOCAL
```

Sustituir CONTRASENA_LOCAL por una contraseña adecuada.

Definir POSTGRES_IMAGE con la imagen seleccionada y POSTGRES_DATA_DIR con la ruta de montaje correspondiente a dicha versión.

### 2.2. Creación

```bash
docker volume create reciclatia-postgres-data
docker network create reciclatia-network
```

Estos recursos solo deberán crearse si todavía no existen.

```bash
docker run -d \
  --name reciclatia-postgres \
  --network reciclatia-network \
  --env-file .env.postgres \
  -p 127.0.0.1:5432:5432 \
  -v "reciclatia-postgres-data:${POSTGRES_DATA_DIR}" \
  "$POSTGRES_IMAGE"
```

Comprobar el servicio:

```bash
docker ps

docker exec reciclatia-postgres \
  pg_isready -U reciclatia -d reciclatia

docker logs reciclatia-postgres
```

### 2.3. Conexiones

| Entorno del backend | Host PostgreSQL |
|---|---|
| Python local | localhost |
| Contenedor Docker | reciclatia-postgres |
| Render | Host de la URL interna |

Ejemplo local:

```text
postgresql://usuario:password@localhost:5432/reciclatia
```

Ejemplo entre contenedores:

```text
postgresql://usuario:password@reciclatia-postgres:5432/reciclatia
```

Configurar DATABASE_URL con la conexión correspondiente.

localhost dentro de Docker identifica el propio contenedor.

El backend normalizará las conexiones postgres:// conforme a la especificación 16.

### 2.4. Inspección

```bash
docker exec -it reciclatia-postgres \
  psql -U reciclatia -d reciclatia
```

Dentro de psql:

```sql
\dt
\d conversation
\d message
```

```sql
SELECT COUNT(*) FROM conversation;
SELECT COUNT(*) FROM message;
```

No se realizarán modificaciones destructivas para comprobar el estado de la base de datos.

## 3. Ejecución local

### 3.1. Backend

Con PostgreSQL, las dependencias, las variables de entorno y ChromaDB disponibles:

```bash
python -m uvicorn api.main:app \
  --host 127.0.0.1 \
  --port 8000 \
  --workers 1
```

Durante el desarrollo podrá utilizarse:

```bash
python -m uvicorn api.main:app --reload
```

La recarga automática puede provocar la pérdida del estado almacenado en memoria. No se utilizará en producción.

Comprobar:

```bash
curl -i http://localhost:8000/health
```

| Recurso | Dirección |
|---|---|
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| OpenAPI | http://localhost:8000/openapi.json |

La inicialización del backend creará las tablas inexistentes. No realizará migraciones automáticas de estructuras existentes.

### 3.2. Streamlit

Configurar:

```dotenv
API_BASE_URL=http://localhost:8000
```

Ejecutar:

```bash
python -m streamlit run app.py
```

Dirección habitual:

```text
http://localhost:8501
```

Streamlit no necesitará credenciales de PostgreSQL ni Gemini.

Las comprobaciones funcionales se establecen en [plan-pruebas.md](plan-pruebas.md).

## 4. Docker

### 4.1. Construcción

El Dockerfile y .dockerignore respetarán los requisitos de la especificación 16.

La construcción deberá incorporar los artefactos documentales necesarios y reconstruir ChromaDB sin credenciales de Gemini.

```bash
docker build -t reciclatia-api:local .
docker images reciclatia-api
```

En caso de necesitar comprobar la compatibilidad Linux AMD64 desde ARM64:

```bash
docker buildx build \
  --platform linux/amd64 \
  --load \
  -t reciclatia-api:amd64 .
```

Esta comprobación no sustituye la construcción real en Render.

### 4.2. Ejecución

Preparar .env.docker con la configuración del backend, DATABASE_URL utilizando el nombre del contenedor PostgreSQL y PORT=8000.

```bash
docker run -d \
  --name reciclatia-api \
  --network reciclatia-network \
  --env-file .env.docker \
  -p 127.0.0.1:8000:8000 \
  reciclatia-api:local
```

Comprobar:

```bash
docker ps
docker logs -f reciclatia-api
curl -i http://localhost:8000/health
```

Inspeccionar recursos:

```bash
docker stats --no-stream \
  reciclatia-api \
  reciclatia-postgres
```

Comprobar el índice cuando resulte necesario:

```bash
docker exec reciclatia-api ls -lh output/chroma_db
```

### 4.3. Docker Compose

Si se incorpora la configuración opcional:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f
docker compose stop
docker compose down
```

No utilizar docker compose down -v como procedimiento ordinario, puesto que puede eliminar los datos persistidos.

## 5. Despliegue en Render

### 5.1. Preparación

La versión candidata deberá estar validada e integrada en main conforme a [flujo-desarrollo.md](flujo-desarrollo.md).

Antes de seleccionar infraestructura, comprobar las condiciones vigentes de:

- CPU, memoria y almacenamiento.
- Costes y transferencia de datos.
- Arranques en frío e inactividad.
- Duración del servicio PostgreSQL.
- Disponibilidad de copias de seguridad.

Seleccionar una configuración compatible con el funcionamiento del backend y el periodo de evaluación.

### 5.2. PostgreSQL gestionado

1. Crear un servicio PostgreSQL en Render.
2. Seleccionar versión, región y plan.
3. Obtener la URL interna de conexión.
4. Conservar la URL externa únicamente para operaciones administrativas autorizadas.
5. Restringir el acceso externo cuando sea posible.

El servicio PostgreSQL deberá mantenerse durante todo el periodo de evaluación.

### 5.3. Web Service

Crear un Web Service vinculado al repositorio GitHub.

| Parámetro | Configuración |
|---|---|
| Repositorio | alex-bometon/pb03_equipo18 |
| Rama | main |
| Runtime | Docker |
| Dockerfile | Dockerfile |
| Región | Preferentemente la misma que PostgreSQL |
| Instancias | 1 |
| Health Check Path | /health |

El comando de arranque respetará PORT y la configuración de procesos establecida en la especificación 16.

### 5.4. Variables de entorno

Configurar en Render:

| Variable | Valor |
|---|---|
| DATABASE_URL | URL interna de PostgreSQL |
| GEMINI_API_KEY | Credencial autorizada de Gemini |
| API_KEY | Secreto de aprovisionamiento administrativo |
| CORS_ORIGINS | Orígenes autorizados |

Los restantes parámetros se obtendrán de .env.example y las especificaciones 14 y 15.

Los secretos se proporcionarán durante la ejecución, no durante la construcción de la imagen.

### 5.5. Primer despliegue

1. Iniciar el despliegue.
2. Revisar los registros de construcción.
3. Comprobar la reconstrucción de ChromaDB.
4. Revisar el arranque de Uvicorn y la conexión a PostgreSQL.
5. Comprobar la inicialización de tablas y credenciales administrativas.
6. Registrar el commit desplegado.
7. Ejecutar las pruebas posteriores al despliegue.

Utilizar la URL HTTPS real proporcionada por Render:

```bash
curl -i "$BACKEND_URL/health"
```

Swagger estará disponible en BACKEND_URL/docs.

### 5.6. Conexión de Streamlit

Modificar API_BASE_URL para utilizar la URL HTTPS del backend desplegado.

Reiniciar Streamlit:

```bash
python -m streamlit run app.py
```

El cambio de entorno no requerirá modificar el código fuente.

Validar las funcionalidades conforme al plan de pruebas.

## 6. Redeploy y rollback

### 6.1. Redeploy

Antes de redesplegar:

- Identificar el commit actual y la versión candidata.
- Comprobar la compatibilidad con el esquema relacional.
- Considerar las ejecuciones activas y la pérdida de recursos volátiles.
- Confirmar que se conservará la misma base de datos.

Iniciar el despliegue desde Render o mediante la integración configurada.

Revisar los registros, health check y operaciones protegidas.

La comprobación de persistencia y pérdida de checkpoints se realizará conforme a [plan-pruebas.md](plan-pruebas.md).

Durante un redeploy pueden coexistir temporalmente dos versiones del backend, sin compartir sus recursos en memoria.

### 6.2. Rollback

1. Identificar la versión afectada y revisar los registros.
2. Seleccionar la última versión estable compatible con PostgreSQL.
3. Utilizar el mecanismo de rollback de Render o desplegar dicha versión.
4. Comprobar health, autenticación, historial y funcionalidades principales.
5. Corregir la incidencia en una rama independiente.
6. Validar e integrar la corrección.
7. Restablecer el despliegue automático cuando corresponda.

Un rollback del backend no revertirá automáticamente el esquema PostgreSQL ni recuperará los recursos volátiles anteriores.

## 7. Mantenimiento de servicios locales

### 7.1. Detención y reinicio

Detener Streamlit y Uvicorn mediante Ctrl+C.

Detener los contenedores:

```bash
docker stop reciclatia-api
docker stop reciclatia-postgres
```

Reiniciarlos en orden inverso:

```bash
docker start reciclatia-postgres

docker exec reciclatia-postgres \
  pg_isready -U reciclatia -d reciclatia

docker start reciclatia-api
```

El orden de arranque será PostgreSQL, backend y Streamlit.

El orden de detención será el inverso.

### 7.2. Limpieza

Identificar los recursos antes de eliminarlos:

```bash
docker ps -a
docker images
docker volume ls
docker network ls
```

Eliminar únicamente los contenedores detenidos pertenecientes al proyecto:

```bash
docker rm reciclatia-api
docker rm reciclatia-postgres
docker image rm reciclatia-api:local
docker network rm reciclatia-network
```

La eliminación de contenedores no eliminará el volumen PostgreSQL creado separadamente.

Operación destructiva:

```bash
docker volume rm reciclatia-postgres-data
```

Este comando solo se ejecutará cuando exista autorización explícita para eliminar los datos y se hayan realizado las copias necesarias.

No se utilizarán comandos globales de limpieza indiscriminada.

## 8. Copias de seguridad y retirada de infraestructura

### 8.1. Copia local

Realizar una exportación lógica de PostgreSQL en una ubicación privada, fuera del repositorio:

```bash
umask 077
mkdir -p "$HOME/reciclatia-backups"

docker exec reciclatia-postgres \
  pg_dump -U reciclatia -d reciclatia \
  > "$HOME/reciclatia-backups/reciclatia-backup.sql"
```

Comprobar que la exportación ha finalizado correctamente.

Las copias importantes deberán verificarse mediante una restauración sobre una base de datos aislada.

No se incorporarán copias SQL al repositorio ni a las evidencias públicas.

### 8.2. Producción

Comprobar los mecanismos de copia y conservación disponibles en el plan de PostgreSQL contratado en Render.

Una copia de PostgreSQL no incluye los recursos almacenados en MemorySaver ni otros estados volátiles.

### 8.3. Retirada de recursos

La eliminación de servicios en Render requerirá:

- Finalización del periodo de evaluación.
- Conservación de datos y evidencias necesarios.
- Autorización expresa.

El Web Service y PostgreSQL son recursos independientes.

Eliminar PostgreSQL constituye una operación destructiva.

Las credenciales que dejen de ser necesarias deberán revocarse.

## 9. Supervisión y registro

Durante la ejecución se revisarán los registros, disponibilidad, memoria, CPU, almacenamiento y consumo de proveedores.

Los procedimientos de diagnóstico se establecen en [gestion-incidencias.md](gestion-incidencias.md).

Cada despliegue relevante deberá registrar:

- Fecha, entorno, rama y commit.
- Imagen y versión de PostgreSQL.
- Resultado de construcción y health check.
- Resultado de las comprobaciones funcionales.
- Incidencias y última versión estable compatible.

Las evidencias se almacenarán conforme al plan de pruebas.

Las tarifas vigentes, costes observados y estimaciones se documentarán en entregables/informe_decisiones.md.

Las cuotas por API key no constituyen por sí solas un límite económico global. Se comprobarán también las protecciones disponibles en el proveedor de inferencia.

Los procedimientos de este documento deberán actualizarse después de validar la infraestructura real.