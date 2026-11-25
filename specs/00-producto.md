# 00. Producto y alcance

## 1. Propósito

ReciclaTÍA es un asistente especializado en la gestión de residuos domésticos y los servicios municipales de recogida del municipio de Madrid.

Su objetivo es proporcionar información fundamentada que permita identificar el destino adecuado de un residuo, conocer las modalidades de recogida y localizar instalaciones compatibles con las necesidades del consumidor.

El Project Break 03 constituye una continuación del PB02 mediante la incorporación de una API REST, persistencia relacional, autenticación, robustez, observabilidad y despliegue.

Se conservará el núcleo funcional existente, evitando reescrituras innecesarias.

## 2. Dominio y fuentes

El ámbito funcional se limita a los residuos domésticos y los servicios municipales de recogida.

El ámbito geográfico se limita al municipio de Madrid. No se extrapolarán sus normas y servicios a otros municipios.

Las fuentes de conocimiento autorizadas serán:

- Corpus documental municipal.
- Datos estructurados del corpus.
- Referencias normativas previamente autorizadas.
- API ArcGIS del Ayuntamiento de Madrid.
- Corpus georreferenciado local como respaldo.

Gemini se utilizará para embeddings, razonamiento, generación e identificación visual, pero no constituirá una fuente documental independiente.

La información temporal procederá del reloj del sistema en la zona horaria Europe/Madrid.

No se realizarán búsquedas abiertas en Internet ni consultas a proveedores documentales o geográficos adicionales.

El inventario y la procedencia de las fuentes se establecen en [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

## 3. Funcionalidades

| Funcionalidad | Comportamiento esperado |
|---|---|
| Clasificación de residuos | Identificar destinos de depósito documentados. |
| Modalidades de recogida | Diferenciar contenedores y puntos limpios fijos, móviles, móviles de 24 horas y de proximidad. |
| Catálogo de residuos | Consultar relaciones documentadas entre residuos y destinos. |
| Proximidad | Localizar instalaciones mediante coordenadas autorizadas. |
| Compatibilidad | Contrastar si una instalación admite el residuo consultado. |
| Horarios | Consultar e interpretar los horarios publicados. |
| Identificación visual | Describir objetos y materiales observables mediante imágenes admitidas. |
| Consultas compuestas | Integrar información documental, geográfica, visual y temporal. |
| Aclaraciones | Solicitar la información necesaria para fundamentar una respuesta. |
| Reformulaciones | Interpretar consultas relacionadas con el contexto autorizado. |
| HITL | Revisar, aprobar o rechazar propuestas. |
| Historial | Consultar los turnos persistidos según los permisos disponibles. |
| Gestión de cuentas | Registrar usuarios, iniciar y cerrar sesión y modificar contraseñas. |
| Gestión de credenciales | Emitir, consultar y seleccionar API keys autorizadas. |
| Administración | Gestionar usuarios, credenciales y acceso global a conversaciones. |

Las funcionalidades estarán condicionadas por la evidencia disponible, los permisos del consumidor y los límites establecidos.

## 4. Perfiles de acceso

El rol pertenecerá a la API key, no a la cuenta de usuario.

| Perfil | Finalidad |
|---|---|
| Free anónimo | Acceso gratuito a consultas textuales sin registro obligatorio. |
| Free registrado | Acceso gratuito con gestión de cuenta y consulta del historial propio autorizado. |
| User | Acceso avanzado con consultas multimodales y cuotas superiores. |
| Admin | Acceso administrativo al producto y sus recursos. |

El registro no concederá automáticamente permisos User ni Admin.

User representa una posible modalidad comercial futura, sin implementar pagos durante el PB03.

Admin no estará sujeto a cuotas comerciales, pero respetará los límites técnicos.

Las reglas de acceso, propiedad, emisión y revocación se establecen en [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md).

Las cuotas y límites se establecen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 5. Comportamiento del asistente

### 5.1. Evidencia

Las recomendaciones deberán fundamentarse en fuentes autorizadas.

Cuando la evidencia sea parcial, se comunicarán sus limitaciones. Cuando resulte insuficiente, el asistente deberá abstenerse o solicitar una aclaración.

No se inventarán fuentes, instalaciones, horarios, coordenadas ni compatibilidades.

Los fallos técnicos no se presentarán como abstenciones legítimas.

Las reglas de generación se establecen en [03-generacion.md](03-generacion.md).

### 5.2. Dominio y admisibilidad

Las consultas inequívocamente fuera del dominio podrán resolverse antes de ejecutar LangGraph.

Las consultas ambiguas y las reformulaciones deberán interpretarse considerando el contexto autorizado.

Las imágenes deberán superar las validaciones técnicas y semánticas correspondientes.

Se intentará adaptar las imágenes que superen los límites finales cuando resulte posible y seguro.

Las identificaciones admitidas se reutilizarán sin repetir el análisis visual.

La descripción de una imagen no sustituirá la evidencia documental necesaria para clasificar un residuo.

Las reglas correspondientes se establecen en las especificaciones [04-consultas-generales.md](04-consultas-generales.md), [05-tools.md](05-tools.md) y [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

### 5.3. Geografía y tiempo

El uso de coordenadas será voluntario. Inicialmente se introducirán manualmente.

La proximidad geográfica no implica compatibilidad con el residuo consultado.

Las distancias representarán proximidad en línea recta, no rutas ni tiempos de desplazamiento.

Los horarios publicados no constituirán garantías de apertura física.

Los resultados identificarán su procedencia y las limitaciones del respaldo local cuando corresponda.

La interpretación geográfica y temporal se establece en [04-consultas-generales.md](04-consultas-generales.md).

## 6. Conversaciones y HITL

Las conversaciones serán independientes y pertenecerán a una API key.

El backend generará sus identificadores cuando corresponda iniciar LangGraph.

Toda ejecución satisfactoria del agente deberá producir una respuesta y un plan y alcanzar la interrupción HITL existente.

Esto incluye las consultas informativas, geográficas, temporales, multimodales, abstenciones y aclaraciones generadas dentro del agente.

| Resultado | Comportamiento |
|---|---|
| Respuesta anterior al agente | No requiere HITL ni modifica el estado operativo. |
| Propuesta pendiente | Permite aprobar o rechazar, pero no iniciar otro turno del mismo hilo. |
| Plan aprobado | Resuelve el turno y finaliza la conversación. |
| Plan rechazado | Resuelve el turno y permite reformular dentro de los límites establecidos. |
| Fallo técnico | No constituye una propuesta válida. |

La aprobación no ejecutará acciones físicas, reservas, contrataciones ni operaciones administrativas externas.

Streamlit utilizará aprobación manual. La API y la CLI conservarán las modalidades de aprobación automática autorizadas.

La aprobación automática utilizará el mecanismo real de HITL.

Las reglas de estado y resolución se establecen en [06-langgraph.md](06-langgraph.md).

## 7. Historial y continuidad

PostgreSQL conservará las conversaciones y los mensajes correspondientes a turnos de LangGraph correctamente aprobados o rechazados.

Cada turno persistido contendrá la pregunta original y la respuesta definitiva del asistente.

Las propuestas rechazadas podrán conservarse en el historial interno de LangGraph, pero no sustituirán la respuesta definitiva almacenada en SQL.

Las respuestas anteriores al agente, propuestas pendientes y ejecuciones fallidas no generarán mensajes persistidos.

El acceso al historial dependerá de los permisos y la propiedad de las conversaciones.

El historial persistente no equivale al estado operativo del agente.

Después de un reinicio o redeploy, podrán consultarse los mensajes autorizados aunque se hayan perdido los checkpoints.

No se reconstruirá automáticamente el estado operativo utilizando el historial SQL.

Las garantías de almacenamiento se establecen en [13-persistencia.md](13-persistencia.md).

## 8. Interfaces y arquitectura

| Componente | Finalidad | Especificación |
|---|---|---|
| Streamlit | Interfaz web mediante HTTP | [07-streamlit.md](07-streamlit.md) |
| FastAPI | Acceso programático y Swagger | [12-contratos-http.md](12-contratos-http.md) |
| CLI | Ejecución independiente del núcleo | [06-langgraph.md](06-langgraph.md) |
| PostgreSQL | Persistencia relacional | [13-persistencia.md](13-persistencia.md) |
| Docker y Render | Ejecución reproducible y despliegue | [16-despliegue.md](16-despliegue.md) |

Streamlit no ejecutará directamente el agente, el RAG, las herramientas ni operaciones sobre PostgreSQL.

La CLI conservará el funcionamiento independiente del backend HTTP.

La arquitectura y las dependencias entre componentes se establecen en [11-arquitectura-mlops.md](11-arquitectura-mlops.md).

## 9. Requisitos no funcionales

| Requisito | Objetivo | Especificación |
|---|---|---|
| Seguridad | Restringir capacidades y proteger el núcleo frente a entradas no confiables. | [10-seguridad.md](10-seguridad.md) |
| Autorización | Garantizar el acceso legítimo a funcionalidades y recursos. | [14-autenticacion-autorizacion.md](14-autenticacion-autorizacion.md) |
| Robustez | Controlar consumo, concurrencia, timeouts y fallos. | [15-robustez-observabilidad.md](15-robustez-observabilidad.md) |
| Observabilidad | Permitir el diagnóstico y la evaluación operativa. | [15-robustez-observabilidad.md](15-robustez-observabilidad.md) |
| Integridad | Garantizar la consistencia del historial persistente. | [13-persistencia.md](13-persistencia.md) |
| Mantenibilidad | Preservar la separación de responsabilidades. | [11-arquitectura-mlops.md](11-arquitectura-mlops.md) |
| Calidad | Verificar la exactitud, fundamentación y ausencia de regresiones. | [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md) |
| Despliegue | Garantizar la ejecución reproducible y la conservación del historial. | [16-despliegue.md](16-despliegue.md) |

La reducción del consumo no deberá comprometer la calidad, la seguridad ni el cumplimiento de los requisitos académicos.

## 10. Fuera de alcance

Durante el PB03 no se implementarán:

- Ampliación a otros municipios.
- Conversaciones generales ajenas al dominio.
- Búsquedas abiertas en Internet.
- Geocodificación de direcciones y cálculo de rutas.
- Garantías de apertura física o clasificación visual infalible.
- Actualización permanente y automática del corpus.
- Reservas, contrataciones o ejecución de recogidas.
- Pagos, suscripciones y facturación.
- Verificación automatizada de correo electrónico.
- Recuperación automática de checkpoints perdidos.
- Idempotencia avanzada de operaciones HTTP.

Las exclusiones arquitectónicas y de infraestructura se establecen en las especificaciones 11 y 16.

La geolocalización automática, el despliegue independiente de Streamlit y un panel administrativo completo constituirán ampliaciones opcionales.

## 11. Criterios de aceptación del producto

ReciclaTÍA deberá:

- Conservar las funcionalidades del PB02 y su HITL obligatorio.
- Proporcionar respuestas fundamentadas dentro del dominio autorizado.
- Permitir el acceso mediante los perfiles establecidos.
- Exponer sus funcionalidades mediante una API REST protegida.
- Proporcionar una interfaz Streamlit conectada mediante HTTP.
- Conservar el funcionamiento independiente de la CLI.
- Almacenar los turnos resueltos en PostgreSQL.
- Gestionar de forma controlada los fallos y límites de ejecución.
- Funcionar mediante Docker y Render.
- Conservar el historial autorizado después de un redeploy.

La aceptación definitiva exigirá superar las validaciones establecidas en las especificaciones especializadas y acreditar el cumplimiento de los requisitos académicos del Project Break 03.