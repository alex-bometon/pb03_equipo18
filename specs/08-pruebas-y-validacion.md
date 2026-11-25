# 08. Estrategia de pruebas y validación

## 1. Objetivo

Definir la estrategia de pruebas y validación de ReciclaTÍA para garantizar el cumplimiento de los requisitos funcionales, técnicos, arquitectónicos y de seguridad establecidos en las especificaciones.

La incorporación de la capa MLOps deberá verificarse tanto mediante nuevas pruebas como mediante la conservación de las comprobaciones correspondientes a las funcionalidades existentes de la fase de desarrollo anterior.

## 2. Principios

- Validación basada en los requisitos establecidos.
- Conservación de las pruebas de regresión.
- Independencia entre pruebas unitarias y servicios externos.
- Separación entre validación estructural y evaluación factual.
- Reproducibilidad de las pruebas.
- Aislamiento de los entornos de desarrollo, pruebas y producción.
- Protección de credenciales y datos personales.
- Control del consumo de recursos durante la evaluación.
- Verificación de situaciones satisfactorias y escenarios de fallo.
- Trazabilidad entre requisitos y pruebas.

La superación de una prueba automatizada no constituirá por sí sola una garantía de corrección factual de todas las respuestas del asistente.

No se considerarán verificadas funcionalidades que no hayan sido sometidas a las comprobaciones correspondientes.

## 3. Niveles de validación

| Nivel | Finalidad |
|---|---|
| Pruebas unitarias | Verificar componentes y funciones de forma aislada |
| Pruebas de integración interna | Verificar la comunicación entre componentes |
| Pruebas de contrato | Comprobar estructuras, restricciones y comportamientos públicos |
| Pruebas de regresión | Detectar modificaciones incompatibles con funcionalidades existentes |
| Pruebas de seguridad | Comprobar autenticación, autorización y resistencia ante entradas adversariales |
| Pruebas de robustez | Verificar límites, concurrencia, errores y recuperación |
| Evaluación del RAG | Medir la pertinencia de la recuperación y la calidad de las respuestas |
| Integración con servicios externos | Comprobar el funcionamiento con proveedores reales |
| Pruebas de interfaz | Verificar los recorridos funcionales del consumidor |
| Pruebas de despliegue | Comprobar el funcionamiento de la infraestructura |
| Pruebas de extremo a extremo | Verificar recorridos completos del producto |

Los diferentes niveles de validación deberán considerarse complementarios.

## 4. Organización de las pruebas

### 4.1. Herramientas

Se conservará pytest como framework principal de pruebas automatizadas.

Las pruebas deberán organizarse dentro del directorio tests/.

Los scripts de evaluación que requieran recursos externos deberán mantenerse diferenciados de las pruebas unitarias ordinarias.

### 4.2. Aislamiento

Las pruebas deberán evitar dependencias no controladas entre casos.

Cada prueba deberá disponer del estado necesario para ejecutarse de forma independiente.

No se dependerá del orden de ejecución de las pruebas para obtener resultados satisfactorios.

### 4.3. Dependencias controladas

Podrán utilizarse mocks, fixtures, clientes de prueba y otras dependencias controladas para verificar el comportamiento de los componentes.

Las pruebas unitarias no deberán requerir:

- Credenciales reales de Gemini.
- Acceso al servicio municipal.
- Una instancia de Render.
- Conexión a PostgreSQL de producción.
- Acceso a conversaciones reales de consumidores.

### 4.4. Estado compartido

Las pruebas que utilicen estructuras en memoria deberán garantizar el aislamiento de:

- Checkpoints.
- Sesiones.
- Contadores de rate limiting.
- Cuotas comerciales.
- Bloqueos de conversaciones.
- Capacidad de ejecución.
- Registros de aprobaciones pendientes.
- Archivos temporales.

El estado generado durante una prueba no deberá modificar el resultado de otra.

## 5. Regresión del PB02

### 5.1. Conservación de funcionalidades

La incorporación de MLOps no deberá eliminar funcionalidades previamente válidas del asistente, salvo aquellas modificaciones expresamente establecidas.

Se conservarán las pruebas relacionadas con:

- Pipeline documental.
- Recuperación semántica.
- Recuperación filtrada.
- Consultas estructuradas.
- Generación fundamentada.
- Validación de fuentes.
- Abstenciones.
- Herramientas.
- Interpretación temporal.
- Orquestación multiagente.
- Interfaz de terminal.

### 5.2. Adaptación de pruebas

Las pruebas existentes podrán modificarse cuando cambie expresamente un contrato o comportamiento del producto.

En particular, deberán adaptarse aquellas que presupongan:

- La existencia obligatoria de HITL en todos los turnos.
- La generación sistemática de planes.
- Los límites internos anteriores.
- La identificación multimodal durante LangGraph.
- La invocación directa del asistente desde Streamlit.

Las modificaciones deberán conservar la finalidad de las comprobaciones que continúen siendo válidas.

No se eliminarán pruebas ni se debilitarán sus condiciones únicamente para obtener una ejecución satisfactoria.

### 5.3. Matriz de pruebas existentes

| Componente | Archivos existentes |
|---|---|
| Recuperación semántica | test_retrieve.py |
| Recuperación estructurada | test_retrieve_structured.py, test_rag_structured.py |
| Generación | test_generate.py |
| Integración RAG | test_rag.py |
| Dominio geográfico | test_rag_domain.py |
| Registro y permisos de herramientas | test_tools_registry.py |
| Herramienta RAG | test_rag_tool.py |
| Herramienta geográfica | test_api_puntos_limpios.py |
| Herramienta multimodal | test_describir_imagen.py |
| Herramienta temporal | test_hora_actual.py |
| Sistema multiagente | test_agent_regression.py |
| Interpretación temporal | test_agent_schedule.py |
| Integración temporal | test_agent_schedule_integration.py |
| Composición de resultados | test_agent_resultado.py |
| Interfaz de terminal | test_cli.py |

Los archivos deberán conservarse o adaptarse conforme a la evolución de sus componentes.

## 6. Validación del pipeline documental

Las pruebas deberán verificar:

- Carga de los documentos autorizados.
- Limpieza y normalización.
- Fragmentación conforme a la configuración.
- Conservación de metadatos.
- Compatibilidad de embeddings.
- Coherencia entre chunks y embeddings.
- Reconstrucción del índice desde artefactos existentes.
- Ausencia de generación innecesaria de embeddings.
- Disponibilidad de la colección ChromaDB.
- Independencia respecto a PostgreSQL y FastAPI.

Las pruebas de reconstrucción desde embeddings existentes deberán verificar que no se realizan llamadas al proveedor de embeddings.

Los requisitos correspondientes se definen en [01-retrieval.md](01-retrieval.md).

## 7. Evaluación de la recuperación

### 7.1. Recuperación semántica

La evaluación deberá comprobar:

- Pertinencia de los fragmentos recuperados.
- Correspondencia con la consulta.
- Conservación de metadatos.
- Respeto del top-k.
- Aplicación de los límites establecidos.
- Comportamiento ante consultas sin evidencia relevante.
- Diferenciación entre ausencia de resultados y fallo técnico.

### 7.2. Recuperación filtrada

Deberá verificarse:

- Correspondencia de modalidad.
- Correspondencia de distrito.
- Combinación correcta de filtros.
- Diferenciación de modalidades específicas.
- Ausencia de sustituciones silenciosas.
- Comportamiento ante restricciones ambiguas.
- Ausencia de resultados incompatibles con la consulta.

### 7.3. Recuperación estructurada

Deberá verificarse:

- Recuperación de registros pertinentes.
- Agrupaciones correctas.
- Recuentos calculados a partir de los datos.
- Conservación de las relaciones entre residuos y destinos.
- Asociación correcta entre paradas y horarios.
- Ausencia de interpretaciones artificialmente exhaustivas.

### 7.4. Métricas

La evaluación podrá utilizar:

- Hit@k.
- Precision@k.
- Recall@k.
- Distribución de distancias vectoriales.
- Posición del primer resultado relevante.
- Proporción de consultas sin resultados.
- Correspondencia de modalidad y distrito.

Las métricas deberán interpretarse según la naturaleza de los casos evaluados.

Precision@k y Recall@k únicamente se calcularán cuando se disponga de referencias de relevancia adecuadas.

La coincidencia de una fuente documental no se considerará equivalente a la corrección factual de una respuesta.

Se conservará tests/evaluate_retrieve.py como mecanismo de evaluación de la recuperación.

## 8. Evaluación de la generación

### 8.1. Validación estructural

Las pruebas deberán verificar:

- Cumplimiento del contrato de generación.
- Respuestas no vacías cuando corresponda.
- Estructura válida de las salidas.
- Correspondencia de identificadores de citas.
- Conservación de fuentes.
- Gestión de respuestas estructuradas inválidas.
- Ausencia de referencias inventadas.

### 8.2. Evaluación factual

La evaluación deberá comprobar:

- Corrección de las recomendaciones.
- Fundamentación de los destinos.
- Conservación de condiciones y excepciones.
- Correspondencia entre afirmaciones y fuentes.
- Ausencia de extrapolaciones geográficas injustificadas.
- Ausencia de información inventada.
- Comunicación de limitaciones.

### 8.3. Abstenciones

Deberá distinguirse entre:

| Resultado | Interpretación |
|---|---|
| Respuesta correcta cuando existe evidencia suficiente | Comportamiento satisfactorio |
| Abstención cuando no existe evidencia suficiente | Comportamiento satisfactorio |
| Respuesta cuando no existe evidencia suficiente | Respuesta indebida |
| Abstención cuando existe evidencia suficiente | Abstención indebida |

Las aclaraciones deberán evaluarse separadamente cuando constituyan la respuesta esperada.

### 8.4. Consumo

Las pruebas deberán comprobar que no se realizan llamadas al modelo cuando:

- No existe contexto documental utilizable.
- La consulta ha sido rechazada previamente.
- Una respuesta determinista permite resolver correctamente la operación.

### 8.5. Scripts de evaluación

Se conservarán los mecanismos existentes:

- tests/evaluate_rag.py.
- tests/smoke_generate.py.
- tests/prueba_consumo.py.

Su ejecución podrá requerir recursos externos.

Estos scripts no deberán confundirse con las pruebas unitarias ordinarias.

## 9. Validación de intenciones y herramientas

### 9.1. Interpretación de consultas

Las pruebas deberán verificar:

- Consultas sobre residuos concretos.
- Consultas generales sobre el catálogo.
- Consultas estructuradas.
- Consultas sobre modalidades de recogida.
- Consultas geográficas.
- Consultas temporales.
- Consultas compuestas.
- Reformulaciones.
- Consultas ambiguas.
- Consultas correspondientes a otros municipios.

### 9.2. Registro y permisos

Deberá comprobarse:

- Existencia de las herramientas registradas.
- Rechazo de herramientas inexistentes.
- Rechazo de herramientas no autorizadas.
- Validación de argumentos.
- Aplicación de permisos por especialista.
- Aplicación de presupuestos internos.
- Ausencia de ejecuciones después de alcanzar los límites.

### 9.3. Herramienta geográfica

Las pruebas deberán verificar:

- Validación de coordenadas.
- Validación de radios.
- Validación de modalidades.
- Cálculo de distancias.
- Ordenación de resultados.
- Límite de instalaciones devueltas.
- Conservación del total de coincidencias.
- Procedencia de los resultados.
- Activación del respaldo ante fallos técnicos.
- Ausencia de respaldo ante respuestas válidas sin coincidencias.

### 9.4. Herramienta temporal

Deberá verificarse:

- Utilización de Europe/Madrid.
- Interpretación de horarios diarios y semanales.
- Intervalos que atraviesan la medianoche.
- Cambios horarios.
- Diferenciación entre dentro, fuera y desconocido.
- Priorización por distancia.
- Priorización por horario.
- Aplicación de la regla específica de envases de vidrio.

### 9.5. Integración de resultados

Deberá comprobarse que la integración conserva las evidencias documentales, geográficas y temporales correspondientes.

No se considerará correcta una recomendación únicamente porque la instalación propuesta sea cercana.

Los requisitos se definen en [04-consultas-generales.md] y [05-tools.md].

## 10. Validación del sistema multiagente

### 10.1. Enrutamiento

Las pruebas deberán verificar:

- Ejecución exclusiva del especialista residuos cuando sea suficiente.
- Ejecución exclusiva del especialista puntos cuando sea suficiente.
- Ejecución de ambas especialidades cuando la consulta lo requiera.
- Fallback ante decisiones inválidas del supervisor.
- Ausencia de ejecuciones innecesarias.
- Respeto de las transiciones autorizadas.

### 10.2. Estado

Deberá comprobarse:

- Creación de estados independientes.
- Aislamiento mediante thread_id.
- Limpieza de campos transitorios.
- Conservación del contexto necesario.
- Ausencia de evidencias obsoletas.
- Prioridad del checkpoint real.
- Gestión de ejecuciones incompletas.

### 10.3. Respuestas directas

Las pruebas deberán verificar que una respuesta directa válida:

- Puede finalizar correctamente la ejecución.
- No requiere una interrupción HITL.
- No genera un plan artificial.
- No genera una aprobación ficticia.
- Permite continuar la conversación cuando corresponda.
- Se distingue de un fallo técnico.

### 10.4. Límites internos

Deberán verificarse los límites de:

- Iteraciones del supervisor.
- Rondas por especialista.
- Llamadas por especialista.
- Llamadas por turno.
- Turnos por conversación.
- Historial interno.
- Recursión del grafo.

Los valores concretos se definen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 11. Validación de HITL

### 11.1. Interrupción

Las pruebas deberán verificar que una aprobación pendiente corresponde a una interrupción real antes del nodo aplicar.

No será suficiente comprobar el valor del atributo pendiente_hitl.

### 11.2. Identificador de aprobación

Deberá comprobarse que:

- Cada plan pendiente dispone de un approval_id válido.
- El identificador corresponde al plan vigente.
- No se reutilizan identificadores de aprobaciones anteriores.
- El identificador se elimina al resolver la aprobación.

### 11.3. Matriz de estados

| Situación | pendiente_hitl | plan_aprobado | done | Turno resuelto |
|---|---|---|---|---|
| Respuesta directa válida | False | None | False | Sí |
| Plan pendiente | True | None | False | No |
| Plan aprobado | False | True | True | Sí |
| Plan rechazado | False | False | False | Sí |

La resolución de un turno no deberá confundirse con la finalización de una conversación.

### 11.4. Escenarios de prueba

| Escenario | Resultado esperado |
|---|---|
| Aprobar un plan válido | Ejecutar aplicar y finalizar la conversación |
| Rechazar un plan válido | Resolver el turno y permitir reformulación |
| Aprobar sin HITL pendiente | Rechazar la operación |
| Preguntar con HITL pendiente | Rechazar la operación |
| Aprobar con un identificador obsoleto | Rechazar sin modificar el checkpoint |
| Resolver dos veces la misma aprobación | Impedir una segunda resolución |
| Resolver concurrentemente una aprobación | Permitir una única modificación válida |
| Fallar durante la reanudación | No comunicar éxito ficticio |
| Aprobar automáticamente mediante HTTP | Utilizar las mismas transiciones autorizadas |
| Resolver una respuesta directa | No ejecutar aplicar |
| Aprobar un plan del último turno permitido | Permitir resolver el plan pendiente |

Los contratos y códigos de error se definen en [12-contratos-http.md](12-contratos-http.md).

## 12. Validación de los contratos HTTP

### 12.1. Cobertura

Todos los endpoints públicos, protegidos y administrativos deberán disponer de las comprobaciones correspondientes a sus contratos.

Deberán verificarse:

- Métodos HTTP.
- Rutas.
- Cabeceras.
- Campos obligatorios.
- Campos opcionales.
- Valores predeterminados.
- Tipos de datos.
- Restricciones de validación.
- Códigos de estado.
- Estructuras de respuesta.

### 12.2. Modelos Pydantic

Las pruebas deberán verificar los modelos establecidos en [12-contratos-http.md](12-contratos-http.md).

Los datos inválidos no deberán provocar ejecuciones del asistente.

### 12.3. Respuestas satisfactorias

Deberán comprobarse las respuestas correspondientes a:

- Consultas directas.
- Abstenciones.
- Aclaraciones.
- Planes pendientes.
- Planes aprobados.
- Planes rechazados.
- Consultas multimodales.
- Registro de usuarios.
- Autenticación.
- Emisión de API keys.
- Consulta de conversaciones.
- Consulta de mensajes.
- Operaciones administrativas.

Las respuestas satisfactorias deberán respetar el contrato aplicable.

### 12.4. Respuestas de error

Deberán verificarse todas las categorías de error establecidas:

| HTTP | Categoría |
|---|---|
| 401 | Autenticación |
| 403 | Autorización |
| 404 | Recursos inexistentes o inaccesibles |
| 409 | Conflictos de estado |
| 413 | Tamaño de archivo |
| 415 | Formato multimedia |
| 422 | Validación |
| 429 | Límites de consumo |
| 500 | Fallos internos |
| 503 | Indisponibilidad o falta de capacidad |
| 504 | Timeout |

El catálogo completo de códigos y situaciones se define en el documento 12.

### 12.5. Contrato ErrorOut

Deberá comprobarse:

- Existencia de code.
- Existencia de message.
- Existencia de request_id.
- Correspondencia entre el código HTTP y el código de error.
- Ausencia de información sensible.
- Correspondencia entre request_id y X-Request-ID.

### 12.6. OpenAPI

La documentación OpenAPI deberá representar los contratos implementados.

Swagger deberá permitir utilizar las operaciones conforme a sus mecanismos de autenticación y autorización.

## 13. Validación de autenticación y autorización

### 13.1. Registro de usuarios

Las pruebas deberán contemplar:

- Registro válido.
- Email inválido.
- Email duplicado.
- Normalización del email.
- Contraseña inválida.
- Restricciones de longitud y composición.
- Ausencia de contraseñas originales en PostgreSQL.

### 13.2. Autenticación mediante sesión

Deberá verificarse:

- Inicio de sesión válido.
- Credenciales incorrectas.
- Usuario inexistente.
- Usuario desactivado.
- Usuario eliminado.
- Token válido.
- Token inválido.
- Token caducado.
- Cierre de sesión.
- Invalidación después de modificar la contraseña.
- Pérdida de sesiones después de reiniciar el backend.

### 13.3. API keys

Deberá verificarse:

- Emisión de claves Free anónimas.
- Emisión de claves Free registradas.
- Emisión autorizada de claves User.
- Rechazo de solicitudes User no autorizadas.
- Restricción de emisión de claves Admin.
- Almacenamiento mediante hash.
- Unicidad de las claves.
- Ausencia del secreto original en consultas posteriores.
- Límites de claves activas.
- Límites temporales de emisión.
- Emisión concurrente.
- Desactivación.
- Reactivación autorizada.
- Eliminación lógica.

### 13.4. Modalidades de autenticación

Las pruebas deberán verificar:

- Autenticación mediante X-API-Key.
- Autenticación mediante Authorization.
- Autenticación mediante sesión y X-API-Key-Id.
- Rechazo de modalidades incompatibles.
- Rechazo de selección de claves ajenas.
- Rechazo del uso ordinario de claves Admin mediante sesión.

### 13.5. Autorización por roles

Deberán comprobarse los permisos de Free, User y Admin para cada operación protegida.

Un usuario registrado no deberá adquirir automáticamente permisos User o Admin.

### 13.6. Autorización por propiedad

Las pruebas deberán verificar:

- Acceso a conversaciones propias.
- Rechazo de conversaciones ajenas.
- Aislamiento entre API keys de un mismo usuario.
- Acceso administrativo autorizado.
- Historial de claves propias desactivadas mediante sesión.
- Restricción de acceso ordinario a claves eliminadas.

Los requisitos detallados se definen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

## 14. Validación de persistencia

### 14.1. Base de datos de pruebas

Las pruebas de integración deberán utilizar una instancia o base de datos PostgreSQL aislada.

No deberán ejecutarse operaciones destructivas sobre la base de datos de producción.

### 14.2. Modelo relacional

Deberán verificarse:

- Creación de tablas.
- Tipos de datos.
- Claves primarias.
- Claves foráneas.
- Restricciones de unicidad.
- Enumerados.
- Valores obligatorios.
- Valores predeterminados.
- Integridad referencial.

Las pruebas deberán comprobar las restricciones reales de PostgreSQL.

Una prueba realizada exclusivamente con SQLite no será suficiente para acreditar la compatibilidad con PostgreSQL.

### 14.3. Entidades

Deberá verificarse el almacenamiento y recuperación de:

- Usuarios.
- API keys.
- Conversaciones.
- Mensajes.

### 14.4. Persistencia de turnos

Las pruebas deberán comprobar que:

- Los turnos resueltos se almacenan conforme a la política de persistencia.
- Los turnos pendientes de HITL no se almacenan como resueltos.
- Los fallos técnicos no generan respuestas satisfactorias persistidas.
- Los timeouts no provocan almacenamiento de resultados tardíos.
- Las aprobaciones duplicadas no duplican mensajes.
- Los turnos rechazados pueden persistirse sin finalizar la conversación.

La persistencia de respuestas generadas antes de LangGraph deberá verificarse conforme a la política conjunta que se establezca en los documentos 12, 13 y 15.

### 14.5. Atomicidad

El almacenamiento de los mensajes de un turno deberá comprobarse mediante pruebas de transacción.

Si falla una de las inserciones, no deberá quedar un turno parcialmente almacenado.

### 14.6. Fallo de persistencia

Deberá simularse un fallo de PostgreSQL después de una ejecución satisfactoria del asistente.

La prueba deberá verificar:

- Ausencia de respuesta HTTP satisfactoria.
- Rollback cuando corresponda.
- Conservación del historial anterior.
- Protección frente a la reutilización de un checkpoint inconsistente.

### 14.7. Eliminación lógica

Deberá comprobarse que la eliminación lógica conserva la integridad referencial e impide las operaciones ordinarias incompatibles con el estado del recurso.

### 14.8. Reinicio y redeploy

Deberá verificarse que los usuarios, API keys, conversaciones y mensajes permanecen disponibles cuando se conserva la misma base de datos PostgreSQL.

Los checkpoints de MemorySaver no deberán confundirse con los mensajes persistidos.

Los requisitos se definen en [13-persistencia.md](13-persistencia.md).

## 15. Validación de límites y cuotas

### 15.1. Independencia de controles

Las pruebas deberán distinguir:

- Rate limiting HTTP.
- Cuotas comerciales.
- Límites temporales de emisión de API keys.
- Límites de claves activas.
- Límites internos del asistente.
- Capacidad global de ejecución.

### 15.2. Ventanas temporales

Los mecanismos de ventanas temporales deslizantes deberán probarse mediante referencias temporales controladas.

No será necesario esperar intervalos reales de minutos, horas o días para verificar el funcionamiento de los contadores.

### 15.3. Escenarios

Deberán verificarse:

- Peticiones dentro del límite.
- Peticiones que alcanzan exactamente el límite.
- Peticiones que superan el límite.
- Expiración de registros antiguos.
- Recuperación de capacidad después de avanzar la ventana.
- Aplicación simultánea de diferentes ventanas temporales.
- Cálculo de Retry-After cuando corresponda.
- Aislamiento de contadores por identidad.
- Aplicación atómica ante peticiones concurrentes.

### 15.4. Cuotas comerciales

Deberá comprobarse:

- Aplicación de los límites Free.
- Aplicación de los límites User.
- Ausencia de cuota comercial para Admin.
- Aplicación de límites técnicos al administrador.
- Contadores compartidos entre POST /ask y POST /ask/image.
- Ausencia de consumo adicional mediante POST /approve.
- Ausencia de consumo ante rechazos previos no contabilizables.
- Contabilización de operaciones que hayan iniciado una ejecución sujeta a cuota.

### 15.5. Reinicio de contadores

Las pruebas deberán verificar el comportamiento de los contadores en memoria después de reiniciar el proceso.

No se atribuirá persistencia durable a mecanismos que no la proporcionan.

Los valores y reglas concretos se definen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 16. Validación del filtrado previo de dominio

### 16.1. Casos de prueba

| Consulta | Comportamiento esperado |
|---|---|
| Pregunta claramente perteneciente al dominio | Admitir la consulta |
| Pregunta inequívocamente ajena al dominio | Respuesta controlada |
| Pregunta ambigua identificable previamente | Solicitar aclaración |
| Reformulación dependiente del contexto | Interpretar el contexto autorizado |
| Pregunta sobre servicios municipales de otro municipio | No extrapolar información de Madrid |
| Pregunta válida sin palabras explícitas de reciclaje | No rechazar únicamente por ausencia de palabras clave |

### 16.2. Ausencia de ejecución

Las pruebas deberán comprobar que una consulta rechazada durante el filtrado previo no provoca llamadas a:

- LangGraph.
- Gemini.
- RAG.
- Herramientas.
- Síntesis.
- HITL.

### 16.3. Evaluación de clasificación

Deberán evaluarse:

- Verdaderos positivos.
- Verdaderos negativos.
- Falsos positivos.
- Falsos negativos.
- Consultas ambiguas.
- Reformulaciones contextuales.

El conjunto de evaluación deberá permitir identificar tanto la admisión indebida de consultas ajenas al dominio como el rechazo incorrecto de consultas válidas.

Las métricas de clasificación deberán utilizar una definición explícita de la clase positiva.

## 17. Validación multimodal

### 17.1. Formatos y archivos

Las pruebas deberán contemplar:

- JPEG válido.
- PNG válido.
- Formato no permitido.
- Extensión engañosa.
- Archivo vacío.
- Archivo corrupto.
- Imagen animada no admitida.
- Archivo situado fuera de ubicaciones autorizadas.

### 17.2. Peso y resolución

Deberán verificarse los siguientes escenarios:

| Situación | Resultado esperado |
|---|---|
| Imagen dentro de los límites finales | Admitir el procesamiento |
| Imagen superior al peso final pero adaptable | Comprimir y continuar |
| Imagen superior a la resolución final pero adaptable | Redimensionar y continuar |
| Imagen que supera el límite absoluto de recepción | Rechazar |
| Imagen que supera la resolución absoluta | Rechazar |
| Imagen que no puede adaptarse de forma segura | Rechazar |
| Imagen corrupta | Rechazar antes de la identificación |
| Riesgo de descompresión excesiva | Impedir el procesamiento inseguro |

La compresión o el redimensionamiento satisfactorios no deberán presentarse como errores.

### 17.3. Validación semántica

Deberá comprobarse:

- Identificación perteneciente al dominio.
- Identificación fuera del dominio.
- Contenido no permitido.
- Identificación incierta.
- Resultado estructurado inválido.
- Fallo técnico del proveedor.

### 17.4. Interrupción del flujo

Una imagen no admitida semánticamente no deberá provocar una ejecución posterior de LangGraph.

Las pruebas deberán comprobar la ausencia de llamadas posteriores al RAG, las herramientas geográficas, la síntesis y HITL.

### 17.5. Reutilización

Las imágenes admitidas deberán utilizar la identificación previamente obtenida.

Deberá comprobarse mediante mocks o contadores de llamadas que no se repite innecesariamente la identificación multimodal durante el mismo turno.

### 17.6. Archivos temporales

Deberá comprobarse:

- Generación de nombres controlados.
- Restricción de rutas.
- Eliminación tras finalizar su utilización.
- Conservación mientras una ejecución activa los necesite.
- Limpieza posterior a excepciones.
- Ausencia de referencias operativas a archivos eliminados.

Los requisitos se definen en [05-tools.md](05-tools.md) y [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 18. Validación de concurrencia

### 18.1. Bloqueo por conversación

Se simularán peticiones que intenten modificar simultáneamente un mismo thread_id.

Deberá verificarse que solamente una puede modificar el estado correspondiente.

La petición incompatible deberá recibir THREAD_BUSY conforme al contrato HTTP.

### 18.2. Capacidad global

Con la configuración inicial de un único worker, se simulará una ejecución activa y una nueva petición correspondiente a otra conversación.

Deberá verificarse:

- Rechazo inmediato mediante SERVER_BUSY.
- Ausencia de nueva ejecución.
- Ausencia de consumo comercial.
- Ausencia de acumulación de consultas pendientes.

### 18.3. Independencia de operaciones HTTP

La ocupación del worker del asistente no deberá impedir por sí sola la atención de operaciones HTTP que no requieran dicho worker.

### 18.4. Liberación de recursos

Deberá verificarse la liberación de los recursos después de:

- Ejecuciones satisfactorias.
- Excepciones.
- Fallos de dependencias.
- Operaciones rechazadas.
- Finalización real de ejecuciones que hayan sufrido timeout.

### 18.5. Reproducibilidad

Las pruebas de concurrencia deberán utilizar mecanismos de sincronización controlados.

No deberán depender exclusivamente de pausas arbitrarias ni de la velocidad del equipo donde se ejecuten.

## 19. Validación de timeouts

### 19.1. Timeout del backend

Se simulará una ejecución que supere el tiempo de espera configurado.

Deberá verificarse:

- HTTP 504.
- Código AGENT_TIMEOUT.
- Ausencia de respuesta satisfactoria.
- Ausencia de persistencia del turno como resuelto.

### 19.2. Ejecución subyacente

Las pruebas deberán distinguir entre la finalización de una petición HTTP y la finalización real del worker.

Mientras la ejecución continúe activa, deberán conservarse los bloqueos, la capacidad ocupada y los archivos temporales necesarios.

### 19.3. Resultado tardío

Se simulará la finalización satisfactoria de una ejecución después de haber devuelto un timeout.

El resultado tardío no deberá persistirse automáticamente ni presentarse como una resolución HTTP satisfactoria.

### 19.4. Consistencia posterior

Cuando no pueda garantizarse la consistencia del checkpoint, deberá impedirse su reutilización.

### 19.5. Timeout del cliente

Las pruebas del cliente HTTP deberán verificar que Streamlit no repite automáticamente una petición POST cuyo resultado no haya podido confirmar.

Los mecanismos y valores de timeout se definen en los documentos 15 y 16.

## 20. Validación de observabilidad

### 20.1. Registros HTTP

Las pruebas deberán verificar la generación de registros estructurados conforme a [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

### 20.2. Trazabilidad

Deberá comprobarse:

- Generación de request_id.
- Devolución de X-Request-ID.
- Correspondencia con ErrorOut.
- Identificación de operaciones.
- Asociación con thread_id cuando corresponda.
- Medición de duración.
- Registro del estado HTTP.
- Registro de errores controlados.

### 20.3. Eventos técnicos

Deberán verificarse los eventos asociados a:

- Inicio de ejecución.
- Finalización real.
- Falta de capacidad.
- Timeouts.
- Fallos técnicos.
- Fallos de persistencia.
- Conflictos de estado.

### 20.4. Protección de información

Las pruebas deberán comprobar la ausencia de:

- Contraseñas.
- API keys originales.
- Tokens de sesión.
- Hashes de credenciales.
- Contenido íntegro de imágenes.
- Prompts privados.
- Cadenas de conexión.
- Datos personales innecesarios.

### 20.5. Métricas operativas

Los mecanismos de observabilidad deberán permitir obtener las métricas correspondientes a los requisitos establecidos.

La duración de una petición HTTP no deberá confundirse automáticamente con la duración real de la ejecución del asistente.

## 21. Validación de seguridad

### 21.1. Entradas adversariales

Deberán comprobarse entradas que intenten:

- Modificar las instrucciones del asistente.
- Obtener respuestas sin evidencia.
- Ejecutar herramientas no autorizadas.
- Ampliar los presupuestos internos.
- Obtener credenciales.
- Acceder a archivos arbitrarios.
- Modificar identificadores de conversación.
- Obtener información perteneciente a otros consumidores.
- Resolver aprobaciones no autorizadas.

### 21.2. Seguridad de la API

Deberá verificarse:

- Rechazo de credenciales inválidas.
- Rechazo de operaciones no autorizadas.
- Prevención de elevaciones de privilegios.
- Prevención de acceso a conversaciones ajenas.
- Validación de entradas antes de ejecutar el asistente.
- Protección de recursos administrativos.
- Ausencia de información sensible en respuestas de error.

### 21.3. Seguridad del núcleo

Las pruebas deberán conservar los controles adversariales correspondientes a:

- Inyección de instrucciones.
- Documentos recuperados no confiables.
- Argumentos maliciosos.
- Herramientas fuera de la allowlist.
- Rutas de archivos no autorizadas.
- Referencias documentales inexistentes.
- Resultados de proveedores externos inválidos.

### 21.4. CORS

Deberá verificarse:

- Configuración de orígenes autorizados.
- Restricción de orígenes no autorizados.
- Métodos y cabeceras correspondientes.
- Exposición de las cabeceras previstas.
- Comportamiento de las peticiones preflight.
- Ausencia de consumo comercial durante el preflight.

CORS no se considerará un mecanismo de autenticación.

Los requisitos se definen en los documentos 10, 14 y 15.

## 22. Validación de Streamlit

### 22.1. Conectividad

Las pruebas deberán comprobar la comunicación con FastAPI mediante HTTP y la configuración de API_BASE_URL.

### 22.2. Acceso y autenticación

Deberán verificarse los recorridos de:

- Acceso Free anónimo.
- Registro.
- Inicio de sesión.
- Cierre de sesión.
- Modificación de contraseña.
- Selección de API keys.
- Cambio de identidad.
- Caducidad de sesión.

### 22.3. Conversaciones

Deberá comprobarse:

- Creación de conversaciones.
- Recepción de thread_id.
- Continuidad.
- Nueva conversación.
- Cambio de API key.
- Limpieza del contexto visual.
- Presentación de respuestas directas.
- Conversaciones finalizadas.
- Pérdida del estado operativo.

### 22.4. Presentación

Deberá verificarse:

- Chat.
- Fuentes.
- Evidencias.
- Limitaciones.
- Abstenciones.
- Planes.
- Resultados geográficos.
- Mapas.
- Procedencia de los datos.
- Horarios publicados.

### 22.5. HITL

Deberá comprobarse:

- Presentación de planes pendientes.
- Habilitación correcta de botones.
- Envío de approval_id.
- Aprobación.
- Rechazo.
- Reformulación.
- Ausencia de acciones HITL en respuestas directas.
- Prevención de envíos duplicados.

### 22.6. Historial

Deberá verificarse:

- Historial visual de la sesión actual.
- Historial persistente autorizado.
- Historial de claves desactivadas.
- Restricción de acceso a recursos ajenos.
- Diferenciación entre historial y estado operativo.

### 22.7. Robustez de la interfaz

Deberán comprobarse:

- Backend no disponible.
- Credenciales inválidas.
- Cuotas agotadas.
- Falta de capacidad.
- Conflictos de conversación.
- Timeouts.
- Respuestas incompatibles con el contrato.
- Ausencia de reintentos automáticos indebidos.
- Ausencia de duplicación de peticiones durante reruns.

### 22.8. Independencia

Deberá comprobarse que Streamlit no accede directamente a:

- LangGraph.
- RAG.
- Herramientas.
- Gemini.
- PostgreSQL.
- Checkpoints.

La interfaz deberá respetar [07-streamlit.md](07-streamlit.md).

## 23. Pruebas de integración externa

### 23.1. Separación

Las pruebas con servicios externos reales deberán mantenerse diferenciadas de las pruebas unitarias.

### 23.2. Servicios

Podrán comprobarse las integraciones con:

- Gemini para embeddings.
- Gemini para generación.
- Gemini para identificación multimodal.
- API municipal de puntos limpios.

### 23.3. Consumo

Las pruebas deberán limitar el consumo innecesario de recursos.

No se ejecutará sistemáticamente una evaluación completa contra proveedores reales cuando las modificaciones puedan verificarse mediante dependencias controladas.

### 23.4. Disponibilidad

La superación de pruebas con mocks no acredita por sí sola la disponibilidad actual de un proveedor externo.

Las pruebas reales deberán permitir diferenciar fallos del producto y fallos atribuibles a dependencias externas.

## 24. Escenarios de extremo a extremo

| Escenario | Resultado esperado |
|---|---|
| Consulta textual Free anónima | Respuesta conforme al contrato sin exigir registro |
| Consulta documental sobre un residuo | Recomendación fundamentada |
| Consulta general sobre catálogo | Información estructurada y alcance identificado |
| Consulta fuera del dominio | Respuesta controlada sin ejecución innecesaria |
| Consulta geográfica sin coordenadas | Aclaración o limitación explícita |
| Consulta geográfica con coordenadas | Resultados autorizados con procedencia |
| Consulta compuesta | Integración de las evidencias necesarias |
| Consulta de imagen mediante Free | Rechazo por falta de autorización |
| Consulta de imagen mediante User | Validación e identificación multimodal |
| Imagen técnicamente adaptable | Procesamiento satisfactorio |
| Imagen fuera de dominio | Interrupción antes de LangGraph |
| Respuesta directa | Turno resuelto sin HITL |
| Plan pendiente | Interrupción real e identificador de aprobación |
| Aprobación válida | Resolución del turno y cierre de conversación |
| Rechazo válido | Resolución del turno y posibilidad de reformular |
| Aprobación obsoleta | Rechazo sin modificar el plan vigente |
| Registro e inicio de sesión | Acceso a funcionalidades autorizadas |
| Selección de una clave propia | Aislamiento de conversaciones |
| Consulta de historial ajeno | Rechazo conforme al contrato |
| Consulta de historial propio | Recuperación ordenada de mensajes |
| Cuota agotada | Error controlado sin ejecución indebida |
| Conversación ocupada | Rechazo por conflicto de estado |
| Worker ocupado | Rechazo por falta de capacidad |
| Timeout | Error controlado sin persistencia tardía |
| Caída de la API municipal | Respaldo autorizado cuando corresponda |
| Fallo de Gemini | Error técnico distinguible |
| Fallo de PostgreSQL | Protección de la consistencia |
| Reinicio del backend | Historial disponible y pérdida controlada de estado |
| Cambio de backend local a Render | Funcionamiento sin modificar el código de Streamlit |

Los escenarios deberán comprobar los resultados públicos y, cuando corresponda, las operaciones internas efectivamente realizadas.

Una respuesta visible satisfactoria no acredita por sí sola qué herramientas se han ejecutado.

## 25. Validación de infraestructura

### 25.1. Entorno local

Deberá comprobarse:

- Instalación de dependencias.
- Compatibilidad con Python 3.13.2.
- Ejecución independiente del RAG.
- Ejecución de la interfaz de terminal.
- Inicialización de PostgreSQL.
- Arranque de FastAPI.
- Disponibilidad de Swagger.
- Comunicación con Streamlit.

### 25.2. Docker

Deberá verificarse:

- Construcción correcta de la imagen.
- Inclusión de los recursos documentales necesarios.
- Reconstrucción del índice desde embeddings existentes.
- Ausencia de credenciales en la imagen.
- Construcción sin necesidad de credenciales de Gemini.
- Arranque del contenedor.
- Disponibilidad del puerto configurado.
- Comunicación con PostgreSQL.

### 25.3. Health check

Deberá comprobarse el comportamiento de GET /health cuando:

- El servicio se encuentra operativo.
- PostgreSQL no está disponible.
- El servicio no dispone de los recursos obligatorios.
- La configuración necesaria no permite operar correctamente.

El health check no deberá realizar consultas al modelo de lenguaje.

### 25.4. Render

Deberá verificarse:

- Despliegue desde el repositorio.
- Construcción de la imagen.
- Arranque del backend.
- Conexión con PostgreSQL.
- Acceso HTTPS.
- Disponibilidad de Swagger.
- Funcionamiento de endpoints protegidos.
- Comunicación con Streamlit local.
- Disponibilidad de registros.

### 25.5. Redeploy

Deberá comprobarse que un redeploy conserva los datos relacionales cuando se mantiene la misma base de datos.

La pérdida de los checkpoints, sesiones y contadores en memoria deberá gestionarse conforme a las especificaciones.

### 25.6. Rollback

Deberá verificarse que la recuperación de una versión compatible del backend permite restablecer el servicio sin eliminar la información persistida.

Los requisitos correspondientes se definen en [16-despliegue.md](16-despliegue.md).

## 26. Evaluación de rendimiento y consumo

### 26.1. Métricas

La evaluación podrá contemplar:

- Tiempo de recuperación.
- Tiempo de generación.
- Duración de peticiones HTTP.
- Duración real de las ejecuciones.
- Latencia media.
- Percentiles de latencia.
- Número de llamadas a Gemini.
- Consumo de tokens, cuando esté disponible.
- Llamadas a herramientas.
- Número de errores técnicos.
- Número de timeouts.
- Rechazos por falta de capacidad.

### 26.2. Comparación

Las comparaciones deberán realizarse utilizando condiciones de evaluación identificables y suficientemente comparables.

No se atribuirá una mejora de rendimiento exclusivamente a una modificación cuando existan otras diferencias relevantes entre las ejecuciones.

### 26.3. Calibración

Los límites internos deberán evaluarse mediante consultas representativas.

Las modificaciones orientadas a reducir consumo deberán conservar los requisitos funcionales y de calidad.

### 26.4. Objetivos

No se establecerán valores de rendimiento obtenidos experimentalmente como resultados garantizados antes de realizar las mediciones correspondientes.

Los límites técnicos obligatorios serán los definidos en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 27. Integración continua

Las validaciones automatizadas deberán poder ejecutarse de forma reproducible sobre las versiones candidatas a integración y despliegue.

Las pruebas unitarias no deberán depender de credenciales reales ni consumir recursos externos.

Las pruebas que requieran PostgreSQL deberán utilizar un entorno aislado.

La automatización mediante GitHub Actions constituye una ampliación opcional.

La obligatoriedad de las validaciones no dependerá de que se ejecuten manualmente o mediante automatización.

Los requisitos de integración continua se definen en [16-despliegue.md](16-despliegue.md).

## 28. Trazabilidad de requisitos

Cada requisito verificable deberá disponer de uno o varios mecanismos de comprobación.

Los mecanismos podrán consistir en:

- Pruebas unitarias.
- Pruebas de integración.
- Pruebas de contrato.
- Evaluaciones del RAG.
- Comprobaciones manuales.
- Pruebas de seguridad.
- Pruebas de infraestructura.

La ausencia de una prueba automatizada no implica necesariamente que un requisito no pueda verificarse.

Cuando una comprobación requiera intervención manual, deberán existir condiciones objetivas que permitan determinar su resultado.

Los resultados concretos de ejecución se registrarán fuera de las especificaciones.

## 29. Criterios generales de aceptación

- Las pruebas de regresión correspondientes a funcionalidades vigentes se conservan.
- Los cambios de comportamiento expresamente definidos disponen de pruebas adaptadas.
- Los nuevos contratos HTTP se verifican.
- Los mecanismos de autenticación y autorización se comprueban.
- Los datos de diferentes consumidores permanecen aislados.
- Las restricciones de PostgreSQL se verifican mediante pruebas de integración.
- Los turnos resueltos se persisten conforme a las reglas establecidas.
- Las aprobaciones pendientes no se almacenan como turnos resueltos.
- Las aprobaciones obsoletas no modifican el estado.
- Los resultados tardíos no se persisten automáticamente.
- Las cuotas y los límites se aplican correctamente.
- El filtrado previo evita ejecuciones innecesarias.
- Las imágenes no admisibles no continúan hacia LangGraph.
- Las operaciones concurrentes respetan los mecanismos de exclusión.
- Los timeouts no liberan recursos prematuramente.
- Los errores técnicos se distinguen de resultados semánticos válidos.
- Las respuestas documentales conservan sus fuentes.
- Las evaluaciones factuales se diferencian de las validaciones estructurales.
- Las credenciales no se exponen mediante respuestas ni registros no autorizados.
- Streamlit funciona exclusivamente como cliente HTTP.
- El núcleo RAG y la CLI mantienen su funcionamiento independiente.
- La imagen Docker puede construirse sin credenciales de Gemini.
- El backend puede desplegarse conforme a la arquitectura establecida.
- El historial permanece disponible después de un redeploy que conserve PostgreSQL.
- Las pruebas automatizadas obligatorias no presentan fallos sin resolver.
- Las comprobaciones pendientes, omitidas o no ejecutadas no se presentan como satisfactorias.

## 30. Especificaciones relacionadas

| Documento | Ámbito de validación |
|---|---|
| [00-producto.md](00-producto.md) | Alcance funcional y perfiles |
| [01-retrieval.md](01-retrieval.md) | Pipeline documental y recuperación |
| [02-mejoras-retrieval.md](02-mejoras-retrieval.md) | Filtros y consultas estructuradas |
| [03-generacion.md](03-generacion.md) | Generación y evidencia |
| [04-consultas-generales.md](04-consultas-generales.md) | Interpretación de consultas |
| [05-tools.md](05-tools.md) | Herramientas y permisos |
| [06-langgraph.md](06-langgraph.md) | Orquestación, estado y HITL |
| [07-streamlit.md](07-streamlit.md) | Cliente web |
| [09-datos-y-fuentes.md](09-datos-y-fuentes.md) | Corpus y procedencia |
| [10-seguridad.md](10-seguridad.md) | Seguridad del núcleo |
| [11-arquitectura-mlops.md](11-arquitectura-mlops.md) | Arquitectura |
| [12-contratos-http.md](12-contratos-http.md) | Contratos HTTP |
| [13-persistencia.md](13-persistencia.md) | PostgreSQL y persistencia |
| [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md) | Autenticación y autorización |
| [15-robustez-observabilidad.md](15-robustez-observabilidad.md) | Robustez, límites y observabilidad |
| [16-despliegue.md](16-despliegue.md) | Infraestructura y despliegue |