# 10. Seguridad del núcleo del asistente

## 1. Objetivo

Proteger el núcleo de ReciclaTÍA frente a entradas no confiables, manipulaciones del modelo, operaciones no autorizadas y alteraciones de las evidencias.

Los controles críticos se aplicarán mediante Python, independientemente de las instrucciones proporcionadas al modelo.

Las validaciones internas permanecerán activas tanto en la ejecución mediante API como mediante CLI.

## 2. Modelo de confianza

Se tratarán como datos no confiables:

- Consultas del consumidor.
- Documentos y metadatos recuperados.
- Imágenes y descripciones visuales.
- Respuestas y argumentos generados por Gemini.
- Resultados de herramientas y servicios externos.
- Contexto conversacional.
- Parámetros e identificadores proporcionados por clientes.

La procedencia oficial de un documento no otorga autoridad a las instrucciones contenidas en él.

El modelo podrá interpretar, razonar y proponer operaciones, pero no establecer sus propios permisos ni modificar los controles del sistema.

Se aplicarán los principios de mínimo privilegio y denegación por defecto.

## 3. Protección frente a prompt injection

Se conservará la separación entre instrucciones y datos establecida en src/agent_prompts.py y src/generate.py.

Las inyecciones directas e indirectas no podrán autorizar:

- Cambios de dominio, permisos o presupuestos.
- Ejecución de herramientas no autorizadas.
- Acceso a información interna o conversaciones ajenas.
- Modificación de evidencias y checkpoints.
- Exposición de credenciales o instrucciones privadas.
- Aprobaciones de planes decididas por el modelo.
- Consultas a servicios externos no autorizados.

Las instrucciones presentes en documentos, imágenes, resultados de herramientas e historial se tratarán exclusivamente como datos.

Las consultas ambiguas no se considerarán automáticamente maliciosas.

Ante una operación no autorizada, se denegará su ejecución y podrá continuarse únicamente con las partes admisibles de la consulta.

Los mecanismos de filtrado previo se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 4. Control de capacidades

### 4.1. Herramientas

Se conservará el registro autorizado y los permisos por especialista definidos en [05-tools.md](05-tools.md).

Los roles internos de LangGraph serán independientes de los roles de API keys. Una credencial Admin no ampliará las capacidades de los especialistas.

Los argumentos generados por el modelo deberán validarse antes de ejecutar cualquier operación.

_preparar_args() conservará la utilización de coordenadas y rutas procedentes del estado autorizado, impidiendo su sustitución por valores arbitrarios generados por Gemini.

Los resultados inválidos o fallidos no se incorporarán como evidencias válidas.

### 4.2. Servicios externos

Las peticiones externas se limitarán a los servicios autorizados.

No se permitirá al modelo proporcionar URLs arbitrarias, expresiones de consulta no autorizadas ni destinos de red alternativos.

Para prevenir SSRF, las redirecciones HTTP deberán deshabilitarse o validarse conforme a los destinos permitidos.

La existencia de una URL en un documento o resultado no autorizará su consulta automática.

PostgreSQL no constituirá una herramienta de consulta libre del modelo.

### 4.3. Sistema de archivos

El acceso a imágenes se limitará a los directorios autorizados bajo assets/.

Se conservarán las comprobaciones de rutas mediante resolve() e is_relative_to(), incluyendo la protección frente a rutas relativas y enlaces simbólicos que resuelvan fuera del directorio permitido.

Los consumidores HTTP no podrán proporcionar rutas locales.

Los requisitos de recepción, adaptación y eliminación de archivos se establecen en la especificación 15.

### 4.4. Contenido ejecutable

Las respuestas del modelo tendrán carácter informativo.

No se utilizarán directamente como código Python, comandos del sistema operativo, consultas SQL arbitrarias ni instrucciones administrativas.

Streamlit no habilitará la ejecución de HTML o JavaScript arbitrario procedente del modelo.

## 5. Integridad de fuentes y evidencias

La recuperación documental utilizará exclusivamente el corpus autorizado.

Las conversaciones, preguntas, imágenes, respuestas generadas y resultados operativos no se incorporarán automáticamente al corpus.

Los metadatos documentales no podrán modificar las instrucciones del sistema.

Las referencias se construirán a partir de evidencias verificadas, conforme a [03-generacion.md](03-generacion.md) y [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

No se inventarán fuentes, instalaciones, coordenadas, horarios, compatibilidades ni resultados de herramientas.

Las observaciones visuales no sustituirán la evidencia documental necesaria para recomendar destinos de residuos.

Las coordenadas no se obtendrán automáticamente de direcciones IP, metadatos GPS de imágenes ni inferencias del modelo.

## 6. Protección del estado y gestión segura de fallos

Los clientes y los modelos no podrán modificar directamente checkpoints, evidencias, contadores, planes ni identificadores de aprobación.

Las identificaciones visuales validadas deberán proceder del mecanismo interno autorizado, no de estructuras proporcionadas directamente por consumidores HTTP.

El aislamiento conversacional y la resolución de HITL se establecen en [06-langgraph.md](06-langgraph.md).

Los controles de autenticación, autorización y propiedad se establecen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

Un fallo técnico no permitirá relajar los controles de seguridad.

Cuando no pueda verificarse una condición crítica de autorización o integridad, se denegará la operación correspondiente.

Los mecanismos de recuperación no podrán ampliar los permisos, inventar evidencias ni sustituir proveedores por otros no autorizados.

## 7. Protección de información sensible

Se evitará incorporar credenciales, hashes, configuraciones sensibles, cadenas de conexión e información de otros consumidores al contexto del modelo.

Las operaciones de inferencia transmitirán únicamente la información necesaria para su finalidad.

Los contratos públicos no expondrán checkpoints, estados internos completos ni trazas privadas.

Las vistas de diagnóstico del núcleo deberán revisarse para impedir la exposición de información sensible.

Se tendrá en cuenta que:

- Las preguntas y respuestas pueden contener datos personales.
- Gemini puede recibir consultas, contexto documental e imágenes preparadas.
- ArcGIS puede recibir coordenadas autorizadas.
- La eliminación local de imágenes no garantiza su eliminación por parte del proveedor externo.
- MemorySaver no proporciona por sí mismo cifrado específico ni supresión definitiva de checkpoints.

Las reglas de persistencia, gestión de credenciales, logging y secretos se establecen en las especificaciones 13, 14, 15 y 16.

## 8. Validación y limitaciones

Las pruebas adversariales deberán comprobar especialmente:

- Inyección directa, documental y multimodal.
- Solicitudes de herramientas no autorizadas.
- Manipulación de argumentos, coordenadas y rutas.
- Acceso a destinos de red no permitidos.
- Contaminación del corpus.
- Fabricación de evidencias y referencias.
- Manipulación del estado y de las decisiones HITL.
- Exposición de información sensible.

Los casos concretos se desarrollarán en [plan-pruebas.md](../docs/plan-pruebas.md), conforme a [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).

La separación de instrucciones y datos no garantiza una protección absoluta frente a prompt injection.

La validación estructural tampoco garantiza la exactitud factual ni la identificación visual correcta.

El PB03 no constituye una certificación de seguridad ni una auditoría completa para explotación comercial.