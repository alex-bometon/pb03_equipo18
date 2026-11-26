# Evidencias de validación — Fase 03

## 1. Identificación

| Parámetro | Valor |
|---|---|
| Proyecto | ReciclaTÍA PB03 |
| Fase | 03 — Contratos HTTP y errores |
| Rama | feature/contracts |
| Fecha | 26/11/2026 |
| Python previsto | 3.13.2 |
| Framework de pruebas | pytest |
| Commit validado | f98fa63ce9edb5f34e99b143ee7b97f2e221b5af |

## 2. Componentes implementados

- Modelos públicos Pydantic.
- Validación estructural y semántica.
- Validación de credenciales.
- Mappers relacionales.
- Catálogo de 46 códigos de error.
- Contrato ErrorOut.
- Manejadores centralizados.
- Middleware ASGI.
- Identificadores de petición.
- Logging HTTP estructurado y CORS.
- Documentación reutilizable de errores.
- Validación de 21 modelos públicos en OpenAPI.

## 3. Regresión completa

Comando ejecutado:

```bash
python -m pytest tests/ -q --tb=short
```

Resultado obtenido:

```text
1276 passed in 5.62s
```

| Métrica | Resultado |
|---|---:|
| Pruebas superadas al cerrar la fase 02 | 424 |
| Pruebas superadas al cerrar la fase 03 | 1276 |
| Incremento neto de pruebas superadas | 852 |
| Pruebas fallidas | 0 |
| Pruebas omitidas | 0 |
| Duración | 5,62 s |

La ejecución no excluyó las pruebas de integración.

## 4. Validación manual HTTP

Se realizaron tres peticiones contra Uvicorn en el entorno local.

| Petición | HTTP | Duración registrada | Resultado |
|---|---:|---:|---|
| GET /openapi.json | 200 | 3,311 ms | Correcto |
| GET /ruta-inexistente | 404 | 3,213 ms | Correcto |
| Prueba de sanitización | 404 | 1,467 ms | Correcto |

### Identificadores de petición

| Petición | Request ID |
|---|---|
| OpenAPI | 64ddd400-e1e7-4748-80b9-4442b5d68bd8 |
| Ruta inexistente | 60ef7e37-54ff-4808-9702-1037856b1c42 |
| Sanitización | c3d45c4c-0dfe-4a7b-9c21-e35f68e3d8db |

Se comprobó la correspondencia de los identificadores entre
cabeceras HTTP, respuestas de error y registros JSON.

## 5. Validación de observabilidad y seguridad

La comprobación manual acreditó:

- Generación de UUID independientes.
- Registros con timestamp UTC.
- Correspondencia entre estados HTTP y códigos de error.
- Ausencia de credenciales ficticias en los registros aportados.
- Sustitución de rutas desconocidas por UNMATCHED.
- Ausencia de datos de identidad sin autenticar.
- Un registro estructurado por cada petición observada.

## 6. Incidencia durante la validación manual

Inicialmente se consultó una instancia anterior de Uvicorn
que devolvía las respuestas predeterminadas de FastAPI.

La instancia se detuvo y se inició nuevamente el backend
desde el código actualizado.

Las comprobaciones posteriores fueron satisfactorias.

No fue necesario modificar los contratos ni desactivar
validaciones para resolver la incidencia.

## 7. Limitaciones

Los tiempos obtenidos corresponden al procesamiento HTTP
de las peticiones observadas.

No representan la latencia de LangGraph, Gemini, ChromaDB
ni de una consulta completa al asistente.

La representación de los modelos en OpenAPI se comprobó
mediante aplicaciones FastAPI aisladas.

Todavía queda pendiente validar los endpoints definitivos,
la autenticación efectiva, las cuotas, la observabilidad
de proveedores externos y el despliegue.

## 8. Conclusión

La fase 03 queda técnicamente validada mediante la ejecución
satisfactoria de 1276 pruebas automatizadas y las
comprobaciones manuales de HTTP y observabilidad.

La integración mediante pull request hacia develop completará
formalmente la fase.