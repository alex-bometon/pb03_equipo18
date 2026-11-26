# AGENTS.md — Instrucciones de trabajo de ReciclaTÍA

## 1. Contexto del proyecto

ReciclaTÍA es un proyecto académico individual de AI Engineering especializado en residuos domésticos y servicios municipales de recogida de Madrid.

El PB03 incorpora los contenidos de los sprints 14, 15 y 16 de MLOps para IA Generativa sobre el núcleo desarrollado durante el PB02.

Se utilizará Python 3.13.2 y una metodología Specification-Driven Development (SDD).

La incorporación de MLOps no implica reconstruir el RAG ni sustituir el sistema multiagente existente.

## 2. Fuentes de referencia

### Requisitos académicos

Repositorio docente:

https://github.com/alex-bometon/bootcamp_AI_Engineering_05_26

Rama: apuntes.

Consultar:

- Project_Break/PB_03_MLOps/README.md.
- Project_Break/PB_03_MLOps/guia_pb03_mlops.html.
- 07_MLOps_para_IA_Generativa/Sprint_14/.
- 07_MLOps_para_IA_Generativa/Sprint_15/.
- 07_MLOps_para_IA_Generativa/Sprint_16/.

El material docente es una referencia de aprendizaje y requisitos académicos. No deberá modificarse.

### Documentación del proyecto

| Ubicación | Responsabilidad |
|---|---|
| specs/ | Requisitos, contratos y restricciones técnicas |
| docs/plan-trabajo-pb03.md | Fases, tareas, dependencias y progreso |
| docs/flujo-desarrollo.md | Metodología, Git e integración |
| docs/plan-pruebas.md | Procedimientos de validación |
| docs/operaciones-despliegue.md | Infraestructura y despliegue |
| docs/gestion-incidencias.md | Diagnóstico y recuperación |
| docs/manual_uso.md | Utilización del producto |
| entregables/evidencias/ | Resultados reales de validación |
| entregables/informe_decisiones.md | Decisiones y justificaciones |
| README.md | Presentación general del producto |

La línea base del PB02 se encuentra en entregables/evidencias/baseline-pb02.md.

## 3. Metodología de trabajo

Antes de proponer una modificación:

1. Identificar la rama, commit y tarea correspondiente.
2. Revisar el código existente.
3. Consultar las especificaciones relevantes y sus dependencias.
4. Identificar los contratos y archivos afectados.
5. Proponer una implementación y sus pruebas.

No asumir que un componente existe únicamente porque está descrito en una especificación.

Ante contradicciones o requisitos indeterminados, comunicar el problema y proponer una solución antes de modificar el comportamiento.

No alterar contratos, arquitectura, alcance ni dependencias sin justificación y autorización.

Trabajar incrementalmente, completando las comprobaciones de cada bloque antes de avanzar.

### Toma de decisiones

Las decisiones establecidas en las especificaciones o aprobadas
previamente se aplicarán sin solicitar una nueva autorización.

Las decisiones técnicas nuevas requerirán la aprobación expresa
del desarrollador antes de implementar los cambios.

Cuando sea posible, las decisiones pendientes se presentarán
conjuntamente, indicando el problema, las alternativas, la opción
recomendada y sus repercusiones.

No se prolongarán innecesariamente los debates sobre decisiones
ya resueltas.

## 4. Principios técnicos

- Reutilizar el código, corpus, embeddings y herramientas existentes.
- Mantener la separación de responsabilidades entre componentes.
- Conservar la independencia del núcleo y la CLI.
- Respetar los contratos y límites definidos en las especificaciones.
- Mantener los controles críticos de seguridad mediante Python.
- Conservar el HITL obligatorio de las ejecuciones satisfactorias de LangGraph.
- Diferenciar resultados semánticos válidos y fallos técnicos.
- Evitar duplicaciones, refactorizaciones innecesarias y ampliaciones fuera de alcance.

No introducir rutas satisfactorias que eviten HITL dentro de LangGraph. Las respuestas anteriores al agente se gestionarán conforme a las especificaciones correspondientes.

Consultar las especificaciones 11 a 16 antes de modificar la arquitectura MLOps.

### Simplicidad y mantenibilidad

- Aplicar DRY, KISS, YAGNI y separación de responsabilidades.
- Priorizar la solución más sencilla que cumpla los requisitos.
- Reutilizar los módulos existentes cuando mantengan su cohesión.
- No duplicar constantes, validaciones, contratos ni lógica.
- Evitar la fragmentación excesiva del código.
- Justificar la creación de archivos, clases y abstracciones.
- Facilitar la evolución del proyecto sin anticipar necesidades hipotéticas.
- Limitar cada fase a su alcance y evitar implementar componentes cuya integración corresponda a fases posteriores.
- Dimensionar las pruebas según el riesgo y las garantías exigidas, evitando combinaciones redundantes de escenarios ya cubiertos.
- Revisar la teoría, implementaciones, workouts y Live Review pertinentes antes de proponer cambios.

La arquitectura deberá mantener un equilibrio entre facilidad
de implementación, escalabilidad y coste de mantenimiento.

## 5. Convenciones de programación

- Seguir PEP 8.
- Evitar fragmentar expresiones que puedan escribirse de forma legible dentro del límite de 79 caracteres.
- Utilizar únicamente los saltos de línea y espacios en blanco necesarios para la legibilidad y el cumplimiento de PEP 8.
- Utilizar snake_case para funciones, variables y módulos.
- Utilizar PascalCase para clases.
- Utilizar UPPER_CASE para constantes.
- Incorporar anotaciones de tipos apropiadas.
- Mantener funciones con responsabilidades delimitadas.
- Documentar los contratos públicos y las decisiones no evidentes.
- Declarar explícitamente las dependencias utilizadas directamente.
- Mantener las convenciones lingüísticas del código existente.
- Seguir PEP 257 para las cadenas de documentación.
- Limitar las líneas de código Python a 79 caracteres.
- Limitar comentarios y docstrings a 72 caracteres.
- Agrupar las importaciones en biblioteca estándar, dependencias externas y módulos propios.
- Evitar líneas en blanco innecesarias entre atributos de clases.
- Redactar comentarios y docstrings en español.

La documentación y las explicaciones se redactarán en español.

No renombrar elementos únicamente para uniformar su idioma.

No incorporar bibliotecas ni actualizar dependencias sin una necesidad justificada.

## 6. Seguridad y protección de datos

No incorporar secretos reales a código, repositorios, prompts, pruebas, registros, imágenes Docker, documentación o evidencias.

No mostrar configuraciones sensibles completas durante el diagnóstico.

Utilizar archivos de entorno excluidos del repositorio y valores ficticios en las configuraciones de ejemplo.

No incorporar datos de consumidores al corpus documental.

Mantener los controles definidos en las especificaciones 10, 14, 15 y 16.

No desactivar validaciones, permisos ni restricciones para solucionar errores o superar pruebas.

## 7. Pruebas y validación

Cada modificación funcional deberá disponer de las pruebas correspondientes.

Ejecutar pruebas específicas durante la implementación y las regresiones necesarias antes de integrar cambios.

Utilizar dependencias controladas para evitar llamadas externas innecesarias y PostgreSQL aislado para pruebas relacionales.

No eliminar ni debilitar pruebas para ocultar defectos.

Seguir los procedimientos establecidos en docs/plan-pruebas.md.

Diferenciar las pruebas propuestas, ejecutadas, superadas, fallidas y pendientes.

No inventar resultados, métricas, capturas ni evidencias.

## 8. Git y autorización de operaciones

main será la rama estable y develop la rama de integración.

Seguir el procedimiento establecido en docs/flujo-desarrollo.md.

Antes de trabajar, comprobar la rama activa y las modificaciones pendientes.

Los asistentes no realizarán sin autorización expresa:

- Modificaciones directas de archivos.
- Creación, cambio o eliminación de ramas.
- Commits, push, merges o pull requests.
- Reescrituras del historial.
- Eliminación de archivos o recursos.
- Modificaciones de infraestructura.
- Despliegues o redespliegues.
- Operaciones destructivas sobre bases de datos.

Una solicitud de análisis, explicación o propuesta de código no autoriza modificar el repositorio.

La autorización de una operación concreta no se extenderá automáticamente a operaciones posteriores.

## 9. Interacción con el desarrollador

El asistente actuará como apoyo técnico y formativo.

Durante la implementación deberá:

- Explicar la finalidad del componente y sus dependencias.
- Identificar los archivos y contratos afectados.
- Proporcionar código e instrucciones reproducibles.
- Justificar las decisiones técnicas.
- Explicar el funcionamiento del código.
- Proponer las comprobaciones necesarias.
- Interpretar los resultados obtenidos.

El desarrollador realizará las modificaciones y ejecutará los comandos, salvo autorización expresa en sentido contrario.

Cuando se solicite un archivo completo, proporcionar su contenido íntegro y coherente.

Cuando se solicite una modificación puntual, limitarse al ámbito solicitado.

No sustituir archivos sin revisar previamente su contenido.

## 10. Documentación y finalización

Cada documento conservará exclusivamente la información correspondiente a su responsabilidad.

Cuando cambie un contrato, actualizar su especificación de referencia y revisar los documentos dependientes sin reproducir innecesariamente su contenido.

Al finalizar una tarea, comunicar:

- Cambios realizados o propuestos.
- Archivos afectados.
- Pruebas realmente ejecutadas y resultados.
- Limitaciones y comprobaciones pendientes.
- Siguiente paso, cuando corresponda.

Diferenciar código propuesto, implementado, probado, integrado y desplegado.

Actualizar el seguimiento del proyecto únicamente conforme al progreso verificado.

Priorizar soluciones sencillas, verificables, seguras y compatibles con las especificaciones.