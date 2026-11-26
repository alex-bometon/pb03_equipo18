# Evidencias de validación — Fase 05

## 1. Identificación

| Parámetro | Valor |
|---|---|
| Proyecto | ReciclaTÍA PB03 |
| Fase | 05 — Adaptación del núcleo |
| Rama | refactor/execution |
| Fecha | 26/11/2026 |
| Commit validado | 0a70351e2f7ee2dc321a71c9b9553907c517e81e |
| Framework de pruebas | pytest |

## 2. Componentes implementados

- Contratos de estado y aprobación HITL.
- Validación de checkpoints y transiciones.
- Preparación de turnos y contexto posterior al rechazo.
- Tratamiento de fallos técnicos y recuperaciones.
- Compatibilidad documental de modalidades.
- Interpretación geográfica y temporal.
- Validación de resultados geográficos y respaldo local.
- Presupuestos y validación de herramientas.
- Reutilización de identificaciones visuales.
- Adaptación de la CLI y de la interfaz existente.

## 3. Regresión completa

Comando ejecutado:

```bash
python -m pytest tests/ -q --tb=short -ra
```

| Métrica | Resultado |
|---|---:|
| Pruebas superadas en fase 04 | 1680 |
| Pruebas superadas en fase 05 | 1680 |
| Incremento neto de pruebas | 0 |
| Fallos | 0 |

## 4. Limitaciones

La regresión existente no cubre exhaustivamente todos los nuevos
supuestos de recuperación e identificación visual previa.

La identificación visual estructurada, la admisibilidad de imágenes
y el filtrado previo se completarán en la fase 06.

Los límites temporales y la coordinación concurrente se implementarán
en la fase 07.

La integración definitiva entre el núcleo, los contratos HTTP y la
persistencia se realizará en la fase 08.

## 5. Conclusión

La adaptación del núcleo ha superado la regresión completa de 1680
pruebas, manteniendo la arquitectura existente y el HITL obligatorio.

La integración mediante pull request hacia develop completará
formalmente la fase 05.