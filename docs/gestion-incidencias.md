# Gestión de incidencias — ReciclaTÍA PB03

## 1. Objetivo

Establecer los procedimientos de diagnóstico, contención, resolución y registro de incidencias en los entornos local y remoto.

Los escenarios de este documento son situaciones previstas, no incidencias necesariamente observadas.

## 2. Procedimiento general

Ante una incidencia:

1. Registrar el contexto y el comportamiento observado.
2. Contener posibles riesgos de seguridad o integridad.
3. Comprobar la disponibilidad de los componentes.
4. Consultar los registros e identificar la causa.
5. Aplicar una corrección o recuperación controlada.
6. Validar el funcionamiento posterior.
7. Registrar las evidencias e incorporar pruebas de regresión cuando corresponda.

No se desactivarán controles de seguridad ni se realizarán operaciones destructivas para resolver incidencias ordinarias.

### Gravedad

| Nivel | Impacto |
|---|---|
| Crítica | Seguridad, integridad de datos o disponibilidad general |
| Alta | Fallo de una funcionalidad principal |
| Media | Degradación funcional o fallo recuperable |
| Baja | Problema limitado sin impacto funcional significativo |

La gravedad dependerá del impacto real, no exclusivamente del código HTTP.

## 3. Diagnóstico inicial

Identificar la versión afectada:

```bash
git branch --show-current
git rev-parse HEAD
git status --short
```

Comprobar dependencias y recursos:

```bash
python --version
python -m pip check

docker ps -a
docker stats --no-stream
```

Comprobar el backend:

```bash
curl -i http://localhost:8000/health
```

Para Render, utilizar la URL HTTPS correspondiente.

Consultar registros locales:

```bash
docker logs --tail 100 reciclatia-api
docker logs --tail 100 reciclatia-postgres
```

En Render, revisar los registros de construcción y ejecución, eventos de despliegue y estado de los servicios.

Para localizar una petición concreta:

```bash
docker logs reciclatia-api 2>&1 | grep -F "$REQUEST_ID"
```

REQUEST_ID deberá contener el identificador obtenido mediante X-Request-ID o ErrorOut.

Los códigos HTTP se interpretarán conjuntamente con los códigos funcionales definidos en [12-contratos-http.md](../specs/12-contratos-http.md).

## 4. Incidencias de infraestructura y dependencias

| ID | Incidencia | Diagnóstico | Resolución |
|---|---|---|---|
| I01 | PostgreSQL no disponible | Estado del servicio, DATABASE_URL, autenticación, red y conexiones | Recuperar conectividad o corregir configuración |
| I02 | Backend no disponible | Registros, dependencias, puerto, configuración, PostgreSQL y ChromaDB | Corregir la causa y recuperar el servicio |
| I04 | Construcción Docker fallida | Primera instrucción fallida, dependencias, arquitectura y .dockerignore | Corregir y reconstruir |
| I05 | ChromaDB no disponible | Colección, dimensiones, configuración y artefactos | Reconstruir el índice desde artefactos compatibles |
| I06 | Gemini no disponible | Credenciales, modelo, cuotas, red y estado del proveedor | Corregir configuración o recuperar disponibilidad |
| I07 | API municipal no disponible | Respuesta externa y funcionamiento del respaldo | Aplicar el respaldo local autorizado |
| I19 | Memoria insuficiente | Consumo, inicialización del índice, workers e imágenes | Optimizar operaciones o ajustar infraestructura |

### Comprobaciones específicas

Disponibilidad de PostgreSQL:

```bash
docker exec reciclatia-postgres \
  pg_isready -U reciclatia -d reciclatia
```

Complementar pg_isready con una conexión autenticada.

Diagnóstico de construcción:

```bash
docker build --progress=plain \
  -t reciclatia-api:local .
```

Comprobación de recursos documentales:

```bash
ls -lh output/chunks.json
ls -lh output/embeddings.json
ls -lh output/chroma_db/
```

Reconstrucción del índice cuando los artefactos sean válidos:

```bash
python main.py rag index --yes
```

No eliminar bases de datos ni volúmenes para solucionar problemas de conexión.

No regenerar embeddings automáticamente ante un fallo de ChromaDB.

No cambiar modelos, aumentar recursos o ampliar timeouts sin identificar previamente la causa.

Los procedimientos de recuperación de infraestructura se establecen en [operaciones-despliegue.md](operaciones-despliegue.md).

## 5. Incidencias de autenticación, autorización y consumo

| ID | Incidencia | Diagnóstico | Actuación |
|---|---|---|---|
| I08 | Fallo de autenticación | Modalidad utilizada, cabeceras, credencial y sesión | Corregir credenciales o iniciar sesión nuevamente |
| I09 | Operación no autorizada | Rol, propiedad, estado y permisos | Utilizar una identidad legítimamente autorizada |
| I10 | Límite de consumo alcanzado | Limitador afectado y Retry-After | Respetar el periodo de espera |

Los permisos y modalidades de autenticación se comprobarán conforme a [14-autenticacion-autorizacion.md](../specs/14-autenticacion-autorizacion.md).

No se revelará la existencia de recursos ajenos durante el diagnóstico.

No se modificarán directamente los roles, propietarios ni hashes para recuperar un acceso.

No se generarán claves adicionales ni se reiniciará el backend para eludir cuotas.

## 6. Incidencias de ejecución y estado

| ID | Incidencia | Diagnóstico | Actuación |
|---|---|---|---|
| I03 | Fallo de ejecución del asistente | Dependencias, trazas, evidencias, presupuestos y checkpoint | Corregir el componente afectado |
| I11 | THREAD_BUSY | Operación activa sobre el mismo hilo | Esperar su finalización real |
| I12 | SERVER_BUSY | Capacidad ocupada y duración de ejecuciones | Esperar capacidad disponible |
| I13 | AGENT_TIMEOUT | Duración HTTP, fases ejecutadas y finalización real | Descartar resultados tardíos y proteger el estado |
| I14 | THREAD_STATE_LOST | Historial SQL, checkpoint y reinicios | Conservar el historial e iniciar otro hilo |
| I15 | Conflicto HITL | Checkpoint, approval_id vigente y decisión anterior | Aplicar el procedimiento correspondiente |
| I16 | Fallo de persistencia | Transacción, restricciones, mensajes y checkpoint | Recuperar PostgreSQL y proteger la consistencia |

### 6.1. Timeout y concurrencia

Correlacionar request_id con los eventos de ejecución real.

Una respuesta AGENT_TIMEOUT no implica que el worker haya terminado.

Comprobar que:

- Los recursos permanecen reservados mientras sean necesarios.
- No comienzan nuevas fases de una ejecución invalidada.
- No se persisten resultados tardíos.
- Se impide reutilizar checkpoints cuya consistencia no pueda garantizarse.

No liberar manualmente bloqueos mientras una ejecución pueda continuar modificando el estado.

Las garantías de ejecución se establecen en [15-robustez-observabilidad.md](../specs/15-robustez-observabilidad.md).

### 6.2. Conflictos HITL

| Código | Actuación |
|---|---|
| NO_PENDING_APPROVAL | Retirar las acciones HITL obsoletas |
| PENDING_APPROVAL | Resolver la propuesta vigente si se dispone de su identificador confirmado |
| STALE_APPROVAL | Descartar el approval_id obsoleto |
| THREAD_CLOSED | Iniciar una conversación nueva |
| TURN_LIMIT_REACHED | Iniciar una conversación nueva para consultas adicionales |

No sustituir identificadores obsoletos ni simular decisiones mediante modificaciones directas del estado.

La resolución del último turno permitido continuará disponible conforme a la especificación 06.

### 6.3. Persistencia y pérdida de estado

Ante un fallo de persistencia, comprobar el resultado de la transacción y la existencia de los mensajes correspondientes.

Si el resultado del commit es incierto, no asumir que se ha realizado rollback ni repetir automáticamente la operación.

Verificar la ausencia de registros parciales o duplicados y conservar el historial anterior.

Cuando no pueda garantizarse la consistencia entre PostgreSQL y el checkpoint, impedir la continuación del hilo.

No reconstruir checkpoints desde mensajes SQL.

Las garantías relacionales se establecen en [13-persistencia.md](../specs/13-persistencia.md).

## 7. Incidencias de entrada e interfaz

| ID | Incidencia | Diagnóstico | Actuación |
|---|---|---|---|
| I17 | Procesamiento multimedia | Formato real, integridad, límites, adaptación e identificación | Solicitar un archivo compatible o resolver el fallo técnico |
| I18 | Streamlit no conecta con FastAPI | API_BASE_URL, health, red, puerto, DNS y timeout | Recuperar conectividad o corregir el cliente |

Una imagen adaptable no constituye necesariamente un error.

No se desactivarán las protecciones multimedia para admitir archivos incompatibles.

Si el health check funciona, revisar el cliente HTTP y el contrato de la operación afectada.

Las peticiones realizadas desde el proceso Python de Streamlit no están sujetas al mecanismo CORS del navegador.

Ante una respuesta HTTP perdida:

- No repetir automáticamente la petición POST.
- Comunicar la incertidumbre del resultado.
- Impedir nuevas operaciones sobre el estado no confirmado.
- Consultar el historial autorizado o iniciar otra conversación.

No desactivar la validación HTTPS para resolver problemas de conexión.

## 8. Incidencias de seguridad

### 8.1. I20 — Exposición de credenciales

1. Identificar y revocar, desactivar o rotar la credencial afectada.
2. Contener los accesos comprometidos.
3. Revisar posibles operaciones no autorizadas.
4. Identificar la exposición en Git, registros, imágenes Docker o documentación.
5. Corregir la configuración y los mecanismos que permitieron la exposición.
6. Comprobar que la credencial anterior ya no permite acceder.

Eliminar un secreto de un archivo no garantiza su desaparición del historial ni de copias anteriores.

### 8.2. I21 — Acceso no autorizado a datos

1. Limitar las operaciones afectadas.
2. Proteger los recursos expuestos y conservar registros sanitizados.
3. Revisar autenticación, propiedad, consultas SQL, sesiones y contratos.
4. Corregir la causa de la exposición.
5. Incorporar una prueba que reproduzca el defecto.
6. Verificar el aislamiento entre consumidores.

Ambos escenarios se tratarán como incidencias críticas.

## 9. Situaciones funcionales normales

No constituyen necesariamente incidencias:

- Abstenciones, aclaraciones y consultas fuera de dominio.
- Evidencia parcial legítima.
- Búsquedas geográficas sin coincidencias y horarios desconocidos.
- Respaldo local satisfactorio.
- Imágenes adaptadas correctamente.
- HITL pendiente o rechazado.
- Aplicación de cuotas y restricciones de acceso.
- Conversaciones sin mensajes persistidos.
- Pérdida de recursos volátiles después de un reinicio.

Se investigarán cuando su comportamiento o frecuencia no corresponda a las especificaciones.

No se contabilizarán automáticamente como fallos técnicos.

## 10. Registro y cierre

Las incidencias realmente observadas se documentarán utilizando la siguiente estructura:

```markdown
# Incidencia

- ID:
- Fecha:
- Gravedad:
- Entorno:
- Rama y commit:
- Componente afectado:
- request_id:
- thread_id:
- api_key_id, cuando proceda:
- Endpoint y código HTTP:
- Código funcional:
- Duración:

## Comportamiento observado

## Comportamiento esperado

## Evidencias y reproducción

## Diagnóstico y causa raíz

## Corrección aplicada

## Validación posterior

## Prevención de recurrencias

## Estado
```

Estados: abierta, en diagnóstico, mitigada, pendiente de verificación o resuelta.

Se distinguirán las hipótesis de las causas confirmadas.

No se incluirán credenciales, datos personales innecesarios ni registros sin sanitizar.

Una incidencia se considerará resuelta cuando se haya aplicado y validado la corrección, comprobado la integridad y seguridad del sistema y registrado la evidencia correspondiente.

Cuando proceda, se incorporarán pruebas de regresión conforme a [plan-pruebas.md](plan-pruebas.md).

Una mitigación temporal no equivale necesariamente a la resolución de la causa raíz.