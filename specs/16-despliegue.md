# 16. Despliegue e infraestructura

## 1. Objetivo

Garantizar la ejecución reproducible, el despliegue y el mantenimiento de ReciclaTÍA mediante Docker, PostgreSQL y Render.

Esta especificación define los requisitos de infraestructura.

Los procedimientos operativos se desarrollan en [operaciones-despliegue.md](../docs/operaciones-despliegue.md).

## 2. Entornos

| Componente | Desarrollo | Producción |
|---|---|---|
| Python | 3.13.2 mediante .venv | 3.13.2 mediante Docker |
| FastAPI | Entorno virtual o Docker | Render Web Service |
| PostgreSQL | Contenedor independiente | Render PostgreSQL |
| ChromaDB | Índice local | Índice incluido en la imagen |
| Streamlit | Ejecución local | Cliente local conectado a Render |
| Configuración | Variables de entorno y .env | Variables de entorno de Render |

Desarrollo, pruebas y producción utilizarán bases de datos, credenciales y configuraciones independientes.

No se utilizará PostgreSQL de producción para las pruebas ordinarias.

Se recomienda separar las credenciales de Gemini por entorno cuando resulte posible.

La arquitectura general se establece en [11-arquitectura-mlops.md](11-arquitectura-mlops.md).

## 3. Dependencias

requirements.txt continuará siendo la referencia de dependencias del proyecto.

Se conservarán las dependencias existentes necesarias para el núcleo, la interfaz y las pruebas.

Se declararán explícitamente las dependencias adicionales utilizadas:

| Dependencia | Finalidad |
|---|---|
| fastapi | API REST |
| uvicorn | Servidor ASGI |
| pydantic | Contratos HTTP |
| sqlmodel | Modelos relacionales |
| sqlalchemy | Motor, sesiones y transacciones |
| psycopg2-binary | Driver PostgreSQL |
| python-multipart | Recepción multimedia |
| httpx | Cliente HTTP y pruebas |

Se conservará bcrypt, ya presente en requirements.txt.

Si los contratos utilizan EmailStr de Pydantic, deberá declararse también email-validator.

Las versiones deberán ser compatibles con Python 3.13.2 y con las dependencias existentes.

No se actualizarán indiscriminadamente las bibliotecas durante la integración.

Las versiones efectivamente utilizadas se documentarán después de validar la implementación.

## 4. Docker

### 4.1. Imagen base

Se utilizará inicialmente:

```dockerfile
FROM python:3.13.2-slim
```

Se comprobará la compatibilidad de las dependencias con las arquitecturas utilizadas en desarrollo y producción.

### 4.2. Construcción

El Dockerfile deberá:

1. Configurar el entorno de ejecución.
2. Instalar las dependencias.
3. Incorporar el backend y el núcleo.
4. Incorporar el corpus y los artefactos documentales.
5. Reconstruir ChromaDB.
6. Preparar los directorios temporales.
7. Configurar el arranque de Uvicorn.

Se aprovechará la caché de construcción y, cuando resulte viable, se ejecutará el servicio con un usuario sin privilegios administrativos.

### 4.3. Recursos documentales

La imagen deberá incluir:

- data/raw/.
- output/chunks.json.
- output/embeddings.json.
- El índice ChromaDB reconstruido.

La reconstrucción se realizará preferentemente durante la construcción de la imagen:

```bash
python main.py rag index --yes
```

No se regenerarán los embeddings durante cada build o redeploy.

La construcción no deberá requerir GEMINI_API_KEY.

Las reglas de reconstrucción y actualización documental se establecen en [01-retrieval.md](01-retrieval.md) y [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

### 4.4. Exclusiones

.dockerignore deberá excluir:

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

Los patrones deberán adaptarse a la estructura real del repositorio.

No se excluirán el corpus ni los artefactos necesarios para reconstruir el índice.

.dockerignore no sustituye a .gitignore.

### 4.5. Arranque

```dockerfile
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
```

En producción no se utilizará --reload.

El número de procesos de Uvicorn será uno.

## 5. PostgreSQL

### 5.1. Desarrollo

PostgreSQL se ejecutará en un contenedor independiente con un volumen persistente.

Se utilizará una versión compatible con la seleccionada en Render.

La versión definitiva se fijará antes de las pruebas de integración.

Docker Compose será opcional y podrá coordinar el backend, PostgreSQL, la red interna, el volumen y las comprobaciones de disponibilidad.

### 5.2. Producción

Se utilizará Render PostgreSQL.

El backend utilizará preferentemente la URL interna de conexión y ambos servicios estarán en la misma región.

El acceso externo se reservará para operaciones administrativas autorizadas.

### 5.3. Conexión

DATABASE_URL identificará la base de datos correspondiente al entorno.

Las URL con esquema postgres:// se normalizarán a postgresql:// cuando corresponda.

La configuración del host dependerá de si el backend se ejecuta directamente en el entorno virtual o dentro de una red Docker.

### 5.4. Creación de tablas

Se utilizará:

```python
SQLModel.metadata.create_all(engine)
```

Este mecanismo creará las tablas inexistentes.

No realizará migraciones de estructuras existentes ni eliminará automáticamente tablas.

Los cambios incompatibles de esquema requerirán un procedimiento específico.

Alembic queda fuera del alcance inicial.

El modelo relacional se define en [13-persistencia.md](13-persistencia.md).

## 6. Render

| Parámetro | Configuración |
|---|---|
| Repositorio | alex-bometon/pb03_equipo18 |
| Rama de despliegue | main |
| Runtime | Docker |
| Dockerfile | Dockerfile |
| Health Check Path | /health |
| Instancias | 1 |
| Procesos de Uvicorn | 1 |
| Workers del asistente | 1 |
| Puerto | Variable PORT |

Render proporcionará la URL HTTPS utilizada por los clientes.

Streamlit cambiará de entorno mediante API_BASE_URL, sin modificar su código.

La selección de región, versión de PostgreSQL y tipo de instancia dependerá de la disponibilidad, memoria, CPU y coste.

Podrá utilizarse un plan gratuito únicamente si satisface los requisitos técnicos y de persistencia durante el periodo de evaluación.

No se asumirá que la infraestructura gratuita resulta suficiente para una explotación comercial.

## 7. Configuración y secretos

### 7.1. Variables generales

| Variable | Responsabilidad |
|---|---|
| PORT | Puerto del backend |
| API_BASE_URL | Dirección del backend para Streamlit |
| DATABASE_URL | Conexión PostgreSQL |
| GEMINI_API_KEY | Credencial de Gemini |
| API_KEY | Aprovisionamiento administrativo |
| CORS_ORIGINS | Orígenes web autorizados |
| LOG_LEVEL | Nivel de logging |

Los parámetros de autenticación, incluyendo USER_TIER_ALLOWED_USER_IDS, se definen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

Los parámetros de robustez, incluyendo RATE_LIMIT_PER_MINUTE, ASK_TIMEOUT_SECONDS y AGENT_MAX_WORKERS, se definen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

.env.example documentará todos los parámetros necesarios sin incluir secretos reales.

### 7.2. Configuración por entorno

Las variables del entorno de ejecución tendrán prioridad sobre los valores cargados desde archivos locales.

Los parámetros exclusivos de FastAPI se gestionarán mediante api/config.py.

La ausencia de DATABASE_URL o de otras variables exclusivas del backend no impedirá ejecutar independientemente el RAG o la CLI.

### 7.3. Protección

Los secretos no se incorporarán a:

- Repositorios.
- Imágenes Docker.
- Argumentos de construcción.
- Logs.
- Capturas de pantalla.
- Documentación de entrega.

Las credenciales comprometidas deberán revocarse o sustituirse.

Eliminar un secreto del código no garantiza su desaparición del historial de Git.

## 8. Ciclo de vida del backend

FastAPI gestionará los recursos mediante su ciclo de vida.

### 8.1. Inicialización

1. Validar la configuración.
2. Inicializar PostgreSQL y comprobar la conexión.
3. Crear las tablas inexistentes.
4. Ejecutar el aprovisionamiento administrativo idempotente.
5. Comprobar el índice ChromaDB.
6. Inicializar el grafo compartido.
7. Inicializar sesiones, contadores y bloqueos.
8. Inicializar el executor.
9. Habilitar el servicio HTTP.

Una configuración imprescindible inválida impedirá inicializar correctamente el servicio.

### 8.2. Disponibilidad

GET /health comprobará los recursos imprescindibles conforme a [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

No ejecutará el asistente ni realizará llamadas a Gemini o ArcGIS.

### 8.3. Cierre

Se gestionará el cierre del executor, conexiones, sesiones y archivos temporales.

No se asumirá que la infraestructura permite finalizar indefinidamente las ejecuciones activas.

## 9. Timeouts

ASK_TIMEOUT_SECONDS tendrá inicialmente un valor de 60 segundos.

El timeout HTTP del cliente Streamlit será inicialmente de 90 segundos.

Ambos valores deberán calibrarse mediante pruebas de rendimiento.

El timeout del cliente deberá contemplar el presupuesto de ejecución del asistente y un margen para la comunicación y las operaciones adicionales del backend.

Los timeouts HTTP no constituyen necesariamente límites absolutos de duración de toda la petición.

Los arranques en frío pueden incrementar los tiempos de espera.

Las reglas de ejecución, descarte de resultados tardíos y conservación de recursos se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

El comportamiento del cliente se define en [07-streamlit.md](07-streamlit.md).

## 10. Reinicios y redespliegues

El historial SQL deberá conservarse después de reiniciar o redesplegar el backend, siempre que se mantenga la misma base de datos PostgreSQL.

La conservación de los recursos documentales se garantizará mediante la imagen Docker.

Los recursos almacenados exclusivamente en memoria se perderán con el proceso, conforme a [11-arquitectura-mlops.md](11-arquitectura-mlops.md).

Durante un redeploy pueden coexistir temporalmente dos versiones del backend sin compartir checkpoints, sesiones, contadores ni bloqueos.

No se garantizará la continuidad de operaciones activas durante un redeploy.

La prueba de persistencia deberá comprobar:

- Conservación de los mensajes previamente confirmados.
- Acceso autorizado al historial.
- Disponibilidad del servicio tras el redeploy.
- Tratamiento controlado de checkpoints perdidos.

El procedimiento se desarrolla en [operaciones-despliegue.md](../docs/operaciones-despliegue.md).

## 11. CI/CD y rollback

### 11.1. Integración continua

Toda versión candidata a producción deberá superar:

- Instalación y comprobación de dependencias.
- Pruebas unitarias.
- Pruebas de integración correspondientes.
- Pruebas de regresión.
- Construcción de Docker sin secretos.
- Comprobaciones de disponibilidad.

Las pruebas automatizadas ordinarias no consumirán recursos de Gemini.

La automatización mediante GitHub Actions será opcional, pero las validaciones serán obligatorias.

### 11.2. Despliegue continuo

Render desplegará versiones identificables de main.

Los despliegues automáticos deberán producirse únicamente a partir de versiones previamente validadas.

Cuando no exista CI automatizada, las comprobaciones deberán realizarse antes de integrar los cambios en main.

Se conservará información sobre:

- Commit desplegado.
- Fecha y resultado del despliegue.
- Resultado del health check.
- Versión estable anterior.

### 11.3. Rollback

Deberá poder recuperarse una versión estable compatible con la base de datos existente.

Un rollback del backend no revertirá automáticamente cambios de esquema ni recuperará checkpoints, sesiones o contadores anteriores.

La recuperación no deberá eliminar los datos persistidos.

Los mecanismos disponibles dependerán de las capacidades del proveedor.

El flujo de integración se establece en [flujo-desarrollo.md](../docs/flujo-desarrollo.md).

## 12. Capacidad, costes y escalabilidad

La infraestructura inicial utilizará una única instancia, un proceso de Uvicorn y un worker del asistente.

La selección de infraestructura deberá considerar:

- Memoria consumida por el núcleo y ChromaDB.
- CPU y latencia.
- Consumo de servicios externos.
- Arranques en frío.
- Disponibilidad.
- Duración y capacidad de PostgreSQL.
- Copias de seguridad.
- Coste operativo.

Las cuotas por API key no constituyen un límite económico global.

Se utilizarán los límites disponibles del proveedor de inferencia como protección adicional.

Antes de incrementar workers deberán evaluarse memoria, latencia, consistencia de estados y capacidad de las dependencias.

El escalado horizontal requerirá coordinar o externalizar los recursos actualmente almacenados en memoria.

No se dependerá del sistema de archivos del contenedor para almacenar datos permanentes del producto.

## 13. Criterios de aceptación

- El entorno utiliza Python 3.13.2 y dependencias compatibles.
- Docker puede construirse sin credenciales de Gemini.
- La imagen contiene un índice ChromaDB utilizable.
- PostgreSQL permanece independiente del backend.
- Los secretos no se incorporan a la imagen ni al repositorio.
- FastAPI funciona en Render mediante HTTPS.
- El servicio utiliza PORT y responde a GET /health.
- Swagger y los endpoints protegidos están disponibles.
- Streamlit funciona con el backend local y desplegado.
- Los entornos de desarrollo, pruebas y producción están aislados.
- Se conserva el historial después de un redeploy.
- La pérdida del estado operativo se gestiona correctamente.
- Los despliegues son identificables mediante commits.
- Existe un procedimiento de recuperación de versiones estables.

La estrategia de pruebas se establece en [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).

## 14. Fuera de alcance

- Kubernetes.
- Redis.
- Múltiples réplicas del backend.
- Checkpoints persistentes.
- Migraciones automatizadas mediante Alembic.
- Infraestructura como código avanzada.
- Monitorización externa avanzada.
- Base vectorial en la nube.
- Microservicios independientes para el RAG.
- Despliegue independiente obligatorio de Streamlit.