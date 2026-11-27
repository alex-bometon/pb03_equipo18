# Evidencias de validación — Fase 06

## 1. Identificación

| Parámetro | Valor |
|---|---|
| Proyecto | ReciclaTÍA PB03 |
| Fase | 06 — Filtrado previo y multimodalidad |
| Rama | feature/input-processing |
| Fecha | 27/11/2026 |
| Framework de pruebas | pytest |

## 2. Componentes implementados

- Filtrado determinista anterior a LangGraph.
- Interpretación del contexto operativo autorizado.
- Validación técnica compartida de imágenes.
- Limitación del cuerpo HTTP multipart.
- Redimensionamiento y compresión de imágenes.
- Corrección de orientación y eliminación de metadatos.
- Almacenamiento temporal seguro.
- Identificación visual estructurada mediante Gemini.
- Validación del contrato IdentificacionImagen.
- Tratamiento diferenciado de los estados semánticos.
- Reutilización de identificaciones visuales en LangGraph.
- Conservación del HITL obligatorio.

## 3. Regresión completa

Comando ejecutado:

​```bash
python -m pytest tests/ -q --tb=short -ra
​```

| Métrica | Resultado |
|---|---:|
| Pruebas superadas en fase 05 | 1680 |
| Pruebas superadas en fase 06 | PENDIENTE_RECUENTO |
| Fallos | 0 |

## 4. Garantías verificadas

- Validación de formatos, peso, resolución e integridad.
- Adaptación de imágenes dentro de los límites absolutos.
- Rechazo de imágenes animadas.
- Limitación de cuerpos HTTP sin Content-Length.
- Protección de rutas y directorios temporales.
- Eliminación de archivos tras identificaciones y excepciones.
- Conservación de archivos mientras el worker permanece activo.
- Diferenciación entre rechazo semántico y fallo técnico.
- Ausencia de nuevas llamadas multimodales al reutilizar una identificación previa.
- Ausencia de consumo de turnos en respuestas previas al agente.

## 5. Limitaciones

Las pruebas multimodales utilizan respuestas simuladas de Gemini. No acreditan la precisión semántica del proveedor real.

La coordinación concurrente, los límites comerciales y los timeouts HTTP definitivos se implementarán en la fase 07.

La integración completa con autenticación, persistencia y endpoints se realizará en la fase 08.

La exclusión del directorio temporal de la imagen Docker se incorporará en la fase 10.

## 6. Conclusión

Los componentes de filtrado y multimodalidad han superado la regresión completa.

Se conserva la arquitectura multiagente existente, el registro de cuatro herramientas y el HITL obligatorio, sin incorporar dependencias adicionales.

La integración mediante pull request hacia develop completará formalmente la fase 06.