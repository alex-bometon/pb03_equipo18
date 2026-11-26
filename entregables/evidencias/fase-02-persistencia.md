# Evidencias de validación — Fase 02

## 1. Identificación

| Parámetro | Valor |
|---|---|
| Proyecto | ReciclaTÍA PB03 |
| Fase | 02 — Persistencia relacional |
| Rama | feature/persistence |
| Fecha | 25/11/2026 |
| Python | 3.13.2 |
| PostgreSQL | 18.7 |
| Infraestructura | Docker local |
| Framework de pruebas | pytest |
| Base de datos de pruebas | reciclatia_test |

## 2. Componentes implementados

- Enumerados compartidos.
- Cuatro modelos relacionales mediante SQLModel.
- Engine y pool de conexiones.
- Inicialización de PostgreSQL mediante lifespan.
- Operaciones de persistencia y consulta.
- Eliminación lógica.
- Almacenamiento atómico de turnos.
- Bloqueos relacionales.
- Entorno aislado de pruebas.

## 3. Pruebas ejecutadas

```bash
python -m pytest tests/ -m integration -v --tb=short
```

La primera ejecución obtuvo 24 pruebas superadas y una prueba fallida.

La prueba test_count_active_keys produjo una excepción ForeignKeyViolation al intentar insertar claves asociadas a un usuario que todavía no había sido insertado mediante SQL.

## 4. Incidencia detectada y resolución

| Parámetro | Descripción |
|---|---|
| Prueba afectada | test_count_active_keys |
| Excepción | sqlalchemy.exc.IntegrityError |
| Causa | Orden de inserción de entidades dependientes |
| Solución | Ejecutar flush() después de incorporar el usuario y antes de incorporar sus claves |
| Impacto sobre el modelo | Ninguno |
| Estado | Resuelta |

La corrección mantuvo las claves foráneas y la atomicidad de la transacción.

No fue necesario eliminar restricciones ni confirmar parcialmente la transacción mediante commit().

## 5. Resultado final

Comando:

```bash
python -m pytest tests/ -q --tb=short
```

| Métrica | Resultado |
|---|---:|
| Pruebas existentes antes de la fase | 394 |
| Pruebas adicionales de inicialización | 5 |
| Pruebas de integración relacional | 25 |
| Total de pruebas superadas | 424 |
| Pruebas fallidas | 0 |
| Pruebas omitidas | 0 |

## 6. Validaciones acreditadas

- Creación y recuperación de usuarios.
- Unicidad de email y hash de API key.
- Integridad referencial.
- Restricciones de propietarios y roles.
- Propiedad de conversaciones.
- Persistencia y orden de mensajes.
- Prevención de duplicidades.
- Rollback ante fallos de inserción.
- Eliminación lógica.
- Bloqueos mediante SELECT FOR UPDATE.
- Protocolo concurrente de emisión de claves.
- Conservación de las pruebas de regresión.

## 7. Limitaciones

La validación corresponde a la capa relacional y a la inicialización del backend.

Todavía no acredita el funcionamiento integral de la autenticación HTTP, los endpoints del asistente, las cuotas comerciales ni la coordinación entre LangGraph y PostgreSQL.

Estos componentes se validarán en las fases posteriores.

## 8. Conclusión

La fase 02 queda técnicamente validada mediante PostgreSQL real y la ejecución satisfactoria de las 424 pruebas automatizadas.

La integración de la rama en develop completará formalmente la fase.