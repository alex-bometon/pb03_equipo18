# Instrucciones de trabajo — ReciclaTÍA

## 1. Proyecto

ReciclaTÍA es un proyecto académico individual de AI Engineering.

El Project Break 03 incorpora los contenidos correspondientes a los sprints 14, 15 y 16 de MLOps para IA Generativa sobre el asistente desarrollado durante el PB02.

El dominio del producto es la gestión de residuos y puntos limpios del municipio de Madrid.

La incorporación de MLOps no implica sustituir el dominio, reconstruir el RAG ni reescribir desde cero el sistema multiagente.

La rama main constituye la referencia estable del producto. No deberá describirse el contenido de otra rama como si correspondiera necesariamente a main.

## 2. Fuentes de referencia

### 2.1. Requisitos académicos

Repositorio docente:

https://github.com/alex-bometon/bootcamp_AI_Engineering_05_26

Rama de referencia:

apuntes

Documentación del proyecto:

- Project_Break/PB_03_MLOps/README.md.
- Project_Break/PB_03_MLOps/guia_pb03_mlops.html.
- 07_MLOps_para_IA_Generativa/Sprint_14/.
- 07_MLOps_para_IA_Generativa/Sprint_15/.
- 07_MLOps_para_IA_Generativa/Sprint_16/.

El material docente constituye una referencia de aprendizaje y de requisitos académicos.

No deberá modificarse ni presentarse como código propio del producto.

### 2.2. Especificaciones del producto

Los documentos de specs/ contienen los requisitos, contratos y restricciones técnicas de ReciclaTÍA.

Deberán consultarse antes de implementar o modificar los componentes correspondientes.

### 2.3. Documentación operativa

| Documento | Responsabilidad |
|---|---|
| docs/plan-trabajo-pb03.md | Orden de implementación, tareas y dependencias |
| docs/flujo-desarrollo.md | Metodología de trabajo y gestión de Git |
| docs/plan-pruebas.md | Procedimientos de validación |
| docs/operaciones-despliegue.md | Infraestructura y despliegue |
| docs/gestion-incidencias.md | Diagnóstico y recuperación |
| docs/manual_uso.md | Instalación y utilización del producto |

### 2.4. Evidencias

Los resultados reales de ejecución y las decisiones técnicas se documentarán en entregables/.

La línea base anterior a MLOps se encuentra en:

entregables/evidencias/baseline-pb02.md

## 3. Metodología de trabajo

El proyecto seguirá una metodología Specification-Driven Development (SDD).

Antes de trabajar sobre una funcionalidad:

1. Identificar la rama y versión de referencia.
2. Revisar el código existente.
3. Consultar las especificaciones relacionadas.
4. Identificar las dependencias.
5. Revisar los contratos afectados.
6. Comprobar las decisiones técnicas pendientes.
7. Identificar las pruebas necesarias.
8. Proponer una implementación compatible.

No se implementará un contrato todavía indeterminado mediante decisiones arbitrarias.

Cuando exista una contradicción entre documentos o entre una especificación y el código, deberá comunicarse antes de modificar el comportamiento correspondiente.

Las decisiones arquitectónicas y funcionales deberán ser autorizadas antes de incorporarse definitivamente.

No se modificarán las especificaciones únicamente para justificar una implementación incorrecta.

## 4. Mapa de especificaciones

| Archivo | Responsabilidad |
|---|---|
| specs/00-producto.md | Alcance y comportamiento funcional |
| specs/01-retrieval.md | Pipeline documental y recuperación semántica |
| specs/02-mejoras-retrieval.md | Recuperación filtrada y estructurada |
| specs/03-generacion.md | Generación, citas y evidencia |
| specs/04-consultas-generales.md | Interpretación documental, geográfica y temporal |
| specs/05-tools.md | Herramientas, permisos y contratos |
| specs/06-langgraph.md | Orquestación, estado y HITL |
| specs/07-streamlit.md | Cliente web |
| specs/08-pruebas-y-validacion.md | Estrategia de pruebas |
| specs/09-datos-y-fuentes.md | Corpus y procedencia |
| specs/10-seguridad.md | Seguridad del núcleo |
| specs/11-arquitectura-mlops.md | Arquitectura general |
| specs/12-contratos-http.md | Contratos de la API REST |
| specs/13-persistencia.md | Modelos relacionales y transacciones |
| specs/14-autenticacion-autorizacion.md | Autenticación y autorización |
| specs/15-robustez-observabilidad.md | Límites, concurrencia, timeout y logging |
| specs/16-despliegue.md | Docker, PostgreSQL y Render |

Consultar únicamente los documentos relevantes para cada tarea, sin omitir las especificaciones de otros componentes cuando existan dependencias.

## 5. Restricciones arquitectónicas

### 5.1. Separación de responsabilidades

- Mantener el RAG reutilizable e independiente de FastAPI, PostgreSQL, LangGraph y Streamlit.
- Mantener las herramientas independientes de la interfaz.
- Mantener la lógica de orquestación dentro del núcleo multiagente.
- Centralizar los contratos públicos en la capa HTTP.
- Centralizar las reglas de autenticación, autorización y consumo en el backend.
- Mantener separados los modelos públicos y los modelos relacionales.

### 5.2. FastAPI

La aplicación FastAPI se incorporará dentro del paquete api/.

El punto de entrada previsto es:

```text
api/main.py
```

FastAPI utilizará las funciones públicas del orquestador.

No deberá duplicar el funcionamiento interno de LangGraph ni ejecutar directamente las herramientas para sustituir al agente, salvo las operaciones previas expresamente contempladas en las especificaciones.

### 5.3. Streamlit

El archivo app.py conservará su responsabilidad como interfaz Streamlit.

Streamlit deberá comunicarse exclusivamente mediante HTTP con el backend.

No deberá acceder directamente a:

- LangGraph.
- RAG.
- ChromaDB.
- Herramientas.
- Gemini.
- PostgreSQL.
- Checkpoints.

La configuración del backend se realizará mediante API_BASE_URL.

No se duplicarán reglas de negocio en la interfaz.

### 5.4. Almacenamiento

| Sistema | Responsabilidad |
|---|---|
| PostgreSQL | Usuarios, API keys, conversaciones y mensajes |
| ChromaDB | Recuperación documental |
| MemorySaver | Estado operativo del grafo |
| Memoria del proceso | Sesiones, cuotas, bloqueos y contadores |
| Sistema de archivos | Recursos documentales y almacenamiento temporal autorizado |

No utilizar estos sistemas de almacenamiento indistintamente.

No reconstruir automáticamente checkpoints a partir del historial persistente.

### 5.5. Infraestructura

El backend utilizará inicialmente:

- Python 3.13.2.
- FastAPI.
- Uvicorn.
- SQLModel.
- PostgreSQL.
- Docker.
- Render.

La API, LangGraph, RAG y ChromaDB compartirán un único contenedor.

PostgreSQL constituirá un servicio independiente.

Se mantendrá inicialmente una instancia del backend, un proceso de Uvicorn y un worker del asistente.

No introducir nuevas tecnologías sin una necesidad justificada y una decisión autorizada.

## 6. Organización del código

La estructura prevista para la capa MLOps incluye:

| Archivo | Responsabilidad |
|---|---|
| api/main.py | Aplicación FastAPI, rutas y ciclo de vida |
| api/config.py | Configuración específica del backend |
| api/schemas.py | Contratos Pydantic |
| api/errors.py | Gestión homogénea de errores |
| api/security.py | Autenticación y autorización |
| api/dependencies.py | Dependencias reutilizables |
| api/rate_limit.py | Rate limiting y cuotas |
| api/images.py | Procesamiento multimedia previo |
| api/service.py | Coordinación de operaciones |
| src/enums.py | Enumerados compartidos |
| src/models.py | Modelos relacionales |
| src/db.py | Engine, sesiones y creación de tablas |

La tabla describe componentes previstos.

No asumir que un archivo existe únicamente porque aparece en esta estructura.

Los componentes existentes conservarán sus responsabilidades salvo modificación expresamente definida.

No reorganizar archivos ni crear capas adicionales sin una justificación funcional.

## 7. Conservación del núcleo existente

- Reutilizar el pipeline documental.
- Reutilizar los embeddings existentes.
- Conservar las capacidades de recuperación semántica y estructurada.
- Mantener las fuentes y sus metadatos.
- Conservar el registro autorizado de herramientas.
- Mantener los especialistas existentes.
- Conservar la ejecución independiente mediante CLI.
- Adaptar las pruebas afectadas por cambios expresamente definidos.
- Evitar regenerar artefactos documentales innecesariamente.

No eliminar funcionalidades existentes únicamente para simplificar la integración de MLOps.

## 8. Contratos y validación

Los contratos definidos en las especificaciones deberán respetarse en todas las capas.

- Validar entradas antes de ejecutar operaciones costosas.
- Utilizar modelos Pydantic para los contratos HTTP.
- No exponer directamente modelos SQLModel.
- No serializar públicamente el estado interno completo del agente.
- Utilizar el contrato ErrorOut para los errores HTTP definidos.
- Mantener los códigos de error establecidos.
- Diferenciar resultados semánticos válidos y fallos técnicos.
- No modificar nombres, tipos o valores predeterminados sin autorización.

La validación del frontend no sustituye la validación del backend.

Las comprobaciones internas de herramientas y estado deberán permanecer activas independientemente del cliente utilizado.

## 9. Seguridad del núcleo

Tratar como datos no confiables:

- Entradas del consumidor.
- Documentos recuperados.
- Imágenes.
- Respuestas de Gemini.
- Argumentos generados por modelos.
- Resultados de herramientas.
- Respuestas de servicios externos.

Las decisiones críticas deberán realizarse mediante controles deterministas en Python.

Ejecutar herramientas únicamente mediante su registro y permisos autorizados.

No permitir que el modelo:

- Amplíe permisos.
- Modifique límites.
- Ejecute funciones arbitrarias.
- Acceda a recursos no autorizados.
- Invente fuentes.
- Modifique directamente el estado protegido.
- Apruebe planes por sí mismo.

Los prompts constituyen una medida complementaria, no una garantía suficiente de seguridad.

## 10. Evidencia documental

Las respuestas deberán fundamentarse mediante las fuentes autorizadas cuando corresponda.

- Conservar las referencias originales.
- No inventar citas ni enlaces.
- Validar los identificadores documentales.
- Diferenciar evidencia suficiente, parcial e insuficiente.
- Aplicar abstenciones o aclaraciones cuando corresponda.
- No extrapolar información municipal de Madrid a otras localidades.
- Diferenciar los resultados geográficos de la API y del corpus local.
- No presentar horarios publicados como garantía de apertura física.

La salida de Gemini no constituye por sí sola una fuente documental.

La validación de citas no garantiza automáticamente la exactitud factual de toda la respuesta.

## 11. Estado conversacional y HITL

- Aislar las conversaciones mediante thread_id.
- Utilizar el checkpoint real como referencia operativa.
- Diferenciar turno resuelto y conversación finalizada.
- Permitir respuestas directas cuando no se requiera HITL.
- No generar planes artificiales para forzar una aprobación.
- Verificar la existencia de una interrupción real antes de resolver HITL.
- Validar approval_id contra el plan vigente.
- Impedir aprobaciones obsoletas o duplicadas.
- Aplicar las mismas validaciones en aprobación manual y automática.
- No modificar atributos de estado para simular una aprobación.
- No reutilizar estados cuya consistencia no pueda garantizarse.

El cliente no constituye la fuente de verdad del estado operativo.

La aprobación de un plan no implica ejecutar acciones físicas o servicios externos irreversibles.

## 12. Autenticación y autorización

La seguridad de acceso será responsabilidad del backend.

- Aplicar autenticación a cada operación protegida.
- Diferenciar autenticación, autorización y propiedad del recurso.
- Respetar los perfiles Free, User y Admin.
- Impedir elevaciones de privilegios.
- Verificar la propiedad de las conversaciones.
- No considerar thread_id como credencial de acceso.
- Aplicar el estado de usuarios y API keys.
- Mantener las restricciones de claves desactivadas y eliminadas.
- No almacenar contraseñas originales.
- No almacenar API keys originales.
- No exponer hashes de credenciales mediante contratos públicos.
- No utilizar credenciales administrativas como acceso ordinario del frontend.

Consultar specs/14-autenticacion-autorizacion.md antes de modificar estos mecanismos.

## 13. Persistencia

- Utilizar PostgreSQL como almacenamiento relacional del servicio.
- Mantener el modelo definido en specs/13-persistencia.md.
- Respetar las restricciones de unicidad e integridad referencial.
- Utilizar transacciones para operaciones atómicas.
- Persistir turnos conforme a la política establecida.
- No persistir como resuelto un turno todavía pendiente de HITL.
- No duplicar mensajes ante operaciones repetidas.
- No persistir automáticamente resultados tardíos.
- No devolver éxito cuando falle una persistencia obligatoria.
- Aplicar rollback cuando corresponda.
- Conservar el historial existente ante fallos del estado operativo.

No utilizar SQLite como sustituto de PostgreSQL en el servicio.

No eliminar tablas automáticamente durante la inicialización.

SQLModel.metadata.create_all() no constituye un mecanismo de migración de esquemas existentes.

## 14. Robustez y observabilidad

Respetar los mecanismos definidos en specs/15-robustez-observabilidad.md.

En particular:

- Aplicar rate limiting HTTP.
- Aplicar cuotas comerciales según el rol.
- Mantener independientes los diferentes contadores.
- Comprobar los límites antes de iniciar operaciones contabilizables.
- Impedir modificaciones simultáneas de una misma conversación.
- Rechazar ejecuciones cuando no exista capacidad disponible.
- No introducir colas de ejecución no autorizadas.
- Mantener los recursos ocupados hasta la finalización real del worker.
- Diferenciar timeout HTTP y finalización efectiva de una ejecución.
- Impedir la persistencia automática de resultados tardíos.
- Registrar request_id y thread_id cuando corresponda.
- Medir la duración de peticiones y ejecuciones.
- Utilizar registros estructurados y sanitizados.

No modificar límites o timeouts únicamente para evitar que una prueba falle.

## 15. Procesamiento multimedia

- Recibir las imágenes mediante el contrato HTTP autorizado.
- No aceptar rutas locales arbitrarias proporcionadas por clientes.
- Validar formatos, integridad, peso y resolución.
- Aplicar los mecanismos de adaptación segura establecidos.
- Respetar los límites absolutos de recepción.
- Utilizar directorios temporales autorizados.
- Aplicar la validación semántica previa a LangGraph.
- Interrumpir el flujo cuando la imagen no resulte admisible.
- Reutilizar identificaciones multimodales válidas.
- Evitar llamadas redundantes al proveedor.
- Eliminar los archivos temporales cuando dejen de ser necesarios.

No eliminar archivos que todavía puedan estar siendo utilizados por una ejecución activa.

No presentar la identificación visual como evidencia documental suficiente.

## 16. Convenciones de programación

### 16.1. Lenguaje

Utilizar Python compatible con la versión establecida para el proyecto.

### 16.2. Estilo

- Seguir PEP 8.
- Mantener nombres descriptivos.
- Utilizar snake_case para funciones, variables y módulos.
- Utilizar PascalCase para clases.
- Utilizar UPPER_CASE para constantes.
- Incorporar anotaciones de tipos cuando aporten claridad.
- Mantener funciones con responsabilidades delimitadas.
- Evitar duplicaciones innecesarias.
- Evitar complejidad accidental.

### 16.3. Idioma

Mantener las convenciones lingüísticas del código existente.

Conservar los nombres establecidos en los contratos públicos, aunque combinen términos en español e inglés.

No renombrar funciones o atributos únicamente para uniformar su idioma.

La documentación y las explicaciones del proyecto se redactarán en español.

### 16.4. Comentarios y docstrings

Los comentarios deberán explicar decisiones, restricciones o comportamientos que no resulten evidentes.

Las funciones públicas deberán disponer de documentación suficiente para comprender su finalidad y contrato.

No añadir comentarios redundantes que se limiten a repetir literalmente el código.

### 16.5. Dependencias

Declarar explícitamente las dependencias utilizadas directamente.

No actualizar indiscriminadamente las dependencias existentes.

No incorporar bibliotecas nuevas sin justificar su necesidad.

## 17. Protección de credenciales y datos

No incorporar secretos reales a:

- Código fuente.
- Repositorio Git.
- Prompts.
- Documentación.
- Pruebas automatizadas.
- Capturas de pantalla.
- Logs.
- Imágenes Docker.
- Argumentos de construcción.
- Evidencias públicas.

Los archivos de configuración de ejemplo utilizarán valores ficticios.

Las credenciales de desarrollo se gestionarán mediante archivos de entorno excluidos del repositorio.

Las credenciales de producción se configurarán mediante el entorno de Render.

No imprimir el contenido completo de .env, DATABASE_URL ni otras configuraciones sensibles durante el diagnóstico.

No incorporar consultas, imágenes o datos personales de consumidores al corpus documental.

## 18. Pruebas y validación

Cada modificación funcional deberá disponer de pruebas adecuadas.

Antes de considerar finalizada una tarea:

1. Ejecutar las pruebas específicas.
2. Revisar los cambios de comportamiento.
3. Comprobar las regresiones correspondientes.
4. Verificar las restricciones de seguridad.
5. Identificar las comprobaciones pendientes.
6. Documentar los resultados reales.

Comando general de referencia:

```bash
python -m pytest tests/ -q --tb=short
```

Comprobación sintáctica de Streamlit:

```bash
python -m py_compile app.py
```

Las pruebas unitarias deberán evitar llamadas reales a Gemini y otros servicios externos mediante dependencias controladas.

Las pruebas de integración con PostgreSQL deberán utilizar una base de datos aislada.

No eliminar ni debilitar pruebas únicamente para conseguir una ejecución satisfactoria.

No inventar resultados, métricas, capturas ni porcentajes de cobertura.

Consultar docs/plan-pruebas.md para los procedimientos específicos.

## 19. Gestión de Git

### 19.1. Ramas

| Rama | Responsabilidad |
|---|---|
| main | Versión estable y desplegable |
| develop | Integración |
| feature/* | Funcionalidades |
| fix/* | Correcciones |
| refactor/* | Reestructuración |
| test/* | Pruebas |
| docs/* | Documentación |
| chore/* | Mantenimiento |

### 19.2. Comprobaciones iniciales

Antes de modificar archivos, comprobar la rama activa y el estado del repositorio.

```bash
git branch --show-current
git status --short
```

### 19.3. Restricciones para asistentes

No realizar sin autorización expresa:

- Modificaciones directas de archivos.
- Creación o cambio de ramas.
- Commits.
- Push.
- Merges.
- Pull requests.
- Eliminación de ramas.
- Reescritura del historial.
- Eliminación de archivos o recursos.
- Modificaciones en infraestructura remota.
- Despliegues o redespliegues.
- Operaciones destructivas sobre bases de datos.

Las solicitudes de análisis, explicación o propuesta de código no constituyen autorización para modificar el repositorio.

La autorización para una operación concreta no implica autorización automática para operaciones posteriores.

### 19.4. Integración

No trabajar directamente sobre main para incorporar funcionalidades todavía no validadas.

Utilizar el flujo definido en docs/flujo-desarrollo.md.

No utilizar operaciones destructivas ni reescrituras del historial como procedimientos ordinarios.

## 20. Interacción con asistentes de programación

El asistente deberá actuar como apoyo técnico y formativo.

Durante el desarrollo:

- Explicar la finalidad del componente que se está implementando.
- Identificar sus dependencias.
- Indicar los archivos afectados.
- Explicar los contratos relevantes.
- Proporcionar instrucciones reproducibles.
- Justificar las decisiones técnicas.
- Explicar el funcionamiento del código.
- Identificar posibles errores.
- Proponer las pruebas correspondientes.
- Interpretar los resultados proporcionados por el desarrollador.

El trabajo se realizará incrementalmente.

No avanzar automáticamente a una fase posterior cuando la actual requiera comprobaciones, decisiones o validaciones pendientes.

Cuando se solicite un archivo completo, proporcionar una versión íntegra y coherente, evitando omitir secciones necesarias.

Cuando se solicite una modificación puntual, limitar el cambio al ámbito solicitado.

No sustituir archivos existentes sin revisar previamente su contenido.

## 21. Comunicación de resultados

Al finalizar una tarea deberá identificarse:

| Información | Contenido |
|---|---|
| Objetivo | Funcionalidad o problema tratado |
| Archivos | Componentes afectados |
| Cambios | Modificaciones realizadas o propuestas |
| Justificación | Motivo técnico |
| Pruebas | Comprobaciones realmente ejecutadas |
| Resultado | Estado observado |
| Limitaciones | Aspectos pendientes |
| Siguiente paso | Continuación propuesta |

Diferenciar expresamente:

- Código propuesto.
- Código implementado.
- Código probado.
- Código integrado.
- Código desplegado.

No atribuir a una rama, versión o servicio funcionalidades que todavía no estén disponibles.

No afirmar que una operación ha sido realizada cuando únicamente se haya descrito su procedimiento.

## 22. Documentación

### README.md

Descripción accesible del producto, arquitectura general y primeros pasos.

### specs/

Requisitos, contratos, restricciones, invariantes y criterios de aceptación.

### docs/

Procedimientos concretos de desarrollo, utilización, validación, despliegue y diagnóstico.

### entregables/informe_decisiones.md

Decisiones técnicas, justificaciones, conclusiones y resultados de la implementación.

### entregables/evidencias/

Comprobaciones realmente realizadas sobre versiones identificables.

No duplicar innecesariamente información entre documentos.

Cuando cambie un contrato, actualizar su especificación de referencia y revisar los documentos dependientes.

Los procedimientos previstos deberán distinguirse de los resultados realmente obtenidos.

## 23. Fuera de alcance

No incorporar durante esta fase, salvo decisión expresamente autorizada:

- Kubernetes.
- Redis.
- JWT u OAuth.
- Alembic.
- Múltiples réplicas del backend.
- Checkpoints de LangGraph en PostgreSQL.
- ChromaDB como servicio remoto independiente.
- Microservicios separados para el RAG.
- Pasarelas de pago.
- Despliegue independiente de Streamlit.
- Cambio de dominio documental.
- Reescritura completa del sistema multiagente.

Las ampliaciones opcionales no deberán comprometer los requisitos obligatorios ni el plazo de entrega.

## 24. Regla general

Ante una decisión técnica no contemplada, una contradicción o una limitación relevante:

1. Identificar el problema.
2. Consultar las fuentes de referencia.
3. Analizar las consecuencias.
4. Proponer alternativas.
5. Solicitar autorización para cambios de alcance o contratos.
6. Documentar la decisión.
7. Implementar y validar el comportamiento acordado.

Priorizar una implementación sencilla, verificable, segura y compatible con las especificaciones del producto.