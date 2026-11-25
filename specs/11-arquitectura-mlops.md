# 11. Arquitectura MLOps

## 1. Principios arquitectónicos

- Separación de responsabilidades.
- Independencia del núcleo del asistente respecto a sus clientes.
- Validación de entradas y salidas mediante contratos Pydantic.
- Centralización de las reglas de negocio en el backend.
- Persistencia del historial mediante PostgreSQL.
- Autenticación y autorización gestionadas por FastAPI.
- Aislamiento de conversaciones mediante identificadores únicos.
- Conservación de las herramientas y del pipeline RAG existentes.
- Control determinista en Python de los límites y las decisiones de seguridad.

## 2. Capas del sistema

| Capa | Tecnología | Responsabilidad |
|---|---|---|
| Presentación | Streamlit | Interacción con el usuario y representación de resultados |
| Transporte | FastAPI | Exposición de endpoints HTTP |
| Contratos | Pydantic | Validación y serialización de datos |
| Servicios | Python | Seguridad, coordinación y reglas de negocio |
| Orquestación | LangGraph | Ejecución del sistema multiagente |
| Recuperación | RAG y ChromaDB | Recuperación de información documental |
| Persistencia | SQLModel y PostgreSQL | Almacenamiento de datos del producto |
| Inferencia | Gemini | Generación, embeddings y análisis multimodal |
| Infraestructura | Docker y Render | Empaquetado y despliegue del servicio |

## 3. Restricciones arquitectónicas

- Streamlit se comunica con el asistente exclusivamente mediante HTTP.
- Streamlit no ejecuta el grafo ni invoca directamente las herramientas.
- FastAPI utiliza las funciones públicas del orquestador existente.
- Las decisiones HITL se validan contra el estado real de LangGraph.
- Las conversaciones pertenecen a una API key concreta.
- El historial persistente se obtiene desde PostgreSQL.
- Los checkpoints de LangGraph permanecen en MemorySaver.
- Las imágenes se reciben mediante HTTP y se procesan temporalmente en el backend.
- Los secretos no se almacenan en el repositorio ni se exponen en los logs.
- El RAG, el agente y FastAPI se despliegan dentro de un único contenedor Docker.

## 4. Persistencia y estado

PostgreSQL almacena los datos persistentes del producto: usuarios, API keys, conversaciones y mensajes.

MemorySaver mantiene el estado operativo del grafo durante la vida del proceso.

ChromaDB almacena el índice vectorial del corpus documental y puede reconstruirse a partir de los embeddings existentes.

El historial SQL debe sobrevivir a los reinicios y redespliegues del backend. Los checkpoints de LangGraph y las aprobaciones pendientes pueden perderse al reiniciar el proceso.

## 5. Concurrencia

El backend debe admitir peticiones HTTP concurrentes de diferentes usuarios y conversaciones.

Las operaciones que modifican una misma conversación deben ejecutarse de manera controlada, evitando modificaciones simultáneas del checkpoint.

El identificador thread_id representa una conversación de LangGraph y no un hilo de ejecución de Python.

La primera versión utilizará un único proceso de Uvicorn y un único worker de ThreadPoolExecutor para la ejecución del asistente.

La concurrencia de peticiones HTTP será independiente de la capacidad de ejecución simultánea del asistente.

Los mecanismos de admisión, bloqueo, concurrencia y timeout se definen en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 6. Infraestructura

- FastAPI, LangGraph, RAG y ChromaDB: un contenedor Docker desplegado en Render.
- PostgreSQL: servicio gestionado de Render.
- Streamlit: cliente local configurado mediante API_BASE_URL.
- Gemini y API municipal: servicios externos.

## 7. Compatibilidad y regresión

La incorporación de la capa MLOps deberá preservar las funcionalidades existentes del asistente, del sistema RAG y de las herramientas, salvo aquellas modificaciones expresamente definidas en las especificaciones.

Las pruebas de regresión existentes constituirán la referencia para verificar dicha compatibilidad.

## 8. Fuera de alcance inicial

- Kubernetes.
- Microservicios independientes para el RAG.
- Redis.
- JWT y OAuth.
- Checkpoints de LangGraph en PostgreSQL.
- Despliegue de múltiples réplicas del backend.

La geolocalización automática del navegador y la implementación de CI/CD mediante GitHub Actions se consideran ampliaciones opcionales.