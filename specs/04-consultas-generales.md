# 04. Interpretación de consultas y datos estructurados

## 1. Objetivo

Seleccionar las estrategias necesarias para interpretar y resolver consultas sobre residuos domésticos y servicios municipales de Madrid.

Se conservarán los mecanismos deterministas del PB02, diferenciando interpretación documental, compatibilidad, proximidad y evaluación temporal.

## 2. Interpretación de consultas

| Módulo | Responsabilidad |
|---|---|
| src/domain.py | Identificación del ámbito geográfico |
| src/rag_intents.py | Identificación de intenciones documentales |
| src/rag.py | Selección de estrategias de recuperación |
| src/agent_routing.py | Selección de especialistas |
| src/agent_schedule.py | Compatibilidad e interpretación temporal |
| src/agent_resultado.py | Integración determinista de resultados |

### 2.1. Estrategias

| Intención | Estrategia |
|---|---|
| Clasificación de un residuo | Recuperación semántica |
| Catálogo general | Recuperación estructurada |
| Modalidad de recogida | Recuperación documental filtrada |
| Horario de una parada móvil | Consulta estructurada |
| Instalaciones cercanas | Búsqueda geográfica |
| Disponibilidad actual | Evaluación temporal |
| Consulta compuesta | Combinación de estrategias |
| Consulta multimodal | Interpretación visual y documental |
| Reformulación | Contexto conversacional autorizado |
| Información insuficiente | Aclaración o abstención |

Las intenciones no serán necesariamente excluyentes.

El filtrado previo HTTP se establece en [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

### 2.2. Ambigüedad

La interpretación será conservadora:

- Diferenciar teléfonos móviles de puntos limpios móviles.
- Diferenciar reciclaje de dispositivos y solicitudes de reparación.
- Diferenciar distritos de Madrid y municipios homónimos.
- Solicitar aclaraciones cuando una ambigüedad pueda modificar sustancialmente la respuesta.

No se incorporará un servicio externo de reconocimiento de lugares.

## 3. Consultas documentales estructuradas

### 3.1. Catálogo municipal

Se conservará _resultado_catalogo().

Las consultas generales utilizarán los registros estructurados de tipos_residuos.csv para obtener recuentos, agrupaciones por destino y ejemplos.

No se utilizará una selección semántica parcial como si representara el catálogo completo.

La exhaustividad se limitará al conjunto de datos consultado.

### 3.2. Horarios de puntos limpios móviles

Se conservará _resultado_horario_movil() y la extracción de distrito, dirección y día.

Los horarios deberán permanecer asociados a sus respectivas paradas.

Si no existe distrito ni dirección identificable, se solicitará información adicional.

Cuando existan varias coincidencias, se distinguirá entre consultas generales y solicitudes de una parada concreta.

Si los resultados superan top_k, se indicará el total encontrado y el número de registros mostrados.

No se requerirán coordenadas para consultar horarios documentados.

Las consultas sobre puntos limpios móviles ordinarios se distinguirán de las correspondientes a la modalidad de 24 horas.

Los mecanismos de recuperación estructurada se establecen en [02-mejoras-retrieval.md](02-mejoras-retrieval.md).

## 4. Modalidades y compatibilidad

Se distinguirán las modalidades:

- Fijo.
- Móvil ordinario.
- Móvil de 24 horas.
- Proximidad.
- Otras modalidades documentadas.

La compatibilidad deberá proceder de evidencia documental afirmativa.

Se distinguirán modalidades admitidas, excluidas y no verificadas.

Deberán revisarse _tipos_admitidos(), tipo_punto_documentado() y debe_buscar_puntos_automaticamente() para impedir que una negación documental se interprete como autorización.

La modalidad móvil ordinaria no implicará automáticamente compatibilidad con instalaciones móviles de 24 horas, ni viceversa.

Se revisará también la detección de modalidades en las consultas estructuradas.

El parámetro geográfico tipo conservará los valores definidos en [05-tools.md](05-tools.md).

Las distinciones adicionales se aplicarán mediante los atributos de los registros y el filtrado interno.

Cuando el consumidor solicite una modalidad concreta, no se sustituirá silenciosamente por otra.

Si no existe evidencia suficiente para determinar compatibilidad, las instalaciones encontradas no se presentarán como destinos compatibles confirmados.

## 5. Interpretación geográfica

Las búsquedas por proximidad requerirán coordenadas válidas y expresamente autorizadas.

Sin coordenadas, podrá proporcionarse información documental, solicitar la ubicación o comunicar la limitación correspondiente.

No se inventarán coordenadas ni se realizará geocodificación externa.

Se conservará debe_buscar_puntos_automaticamente() para activar búsquedas cuando concurran:

- Una intención de depósito o reciclaje.
- Evidencia documental afirmativa sobre puntos limpios.
- Coordenadas autorizadas.
- Restricciones compatibles.

La búsqueda respetará el radio y la modalidad solicitados.

La ausencia de resultados dentro del radio no permitirá concluir que no existen instalaciones en todo Madrid.

Las modalidades documentadas sin cobertura geográfica, como determinados contenedores de pilas en marquesinas, podrán mencionarse sin inventar ubicaciones ni distancias.

Los contratos geográficos, cálculos y mecanismos de respaldo se establecen en [05-tools.md](05-tools.md).

## 6. Interpretación temporal

### 6.1. Necesidad de consultar la hora

requiere_hora() deberá distinguir:

- Consultas sobre horarios publicados.
- Consultas sobre disponibilidad actual.
- Priorización de instalaciones para acudir en ese momento.
- Restricciones temporales documentadas.

Las consultas exclusivamente documentales sobre horarios no requerirán consultar la hora actual.

Se conservará la evaluación temporal asociada a las búsquedas geográficas cuando resulte pertinente.

Las comprobaciones utilizarán resultados válidos de hora_actual() y la zona Europe/Madrid.

### 6.2. Intervalos

estado_horario() conservará la interpretación de horarios diarios, semanales, múltiples franjas y periodos que atraviesen la medianoche.

Los intervalos ordinarios utilizarán:

```python
apertura <= hora_actual < cierre
```

Los intervalos nocturnos considerarán también el día anterior.

La coincidencia entre apertura y cierre no implicará disponibilidad durante 24 horas.

Los horarios semanales deberán interpretarse completamente antes de concluir que una instalación se encuentra fuera de horario.

Solo se considerará disponibilidad durante 24 horas cuando exista una modalidad o un horario explícito que la respalde.

### 6.3. Estados

| Estado | Significado |
|---|---|
| dentro | Dentro del horario publicado |
| fuera | Fuera del horario publicado |
| desconocido | Información insuficiente para determinarlo |

La ausencia de información no implicará apertura ni cierre.

Los horarios publicados no garantizan apertura física debido a posibles festivos, modificaciones o incidencias.

### 6.4. Referencias futuras

Las referencias a mañana, días concretos o periodos futuros no se evaluarán como si correspondieran al momento actual.

Cuando los mecanismos existentes no permitan interpretar de forma fiable la fecha solicitada, se pedirá una aclaración o se comunicarán únicamente los horarios documentados.

No se incorporará un sistema externo de calendarios.

### 6.5. Fallos temporales

Si la información temporal es complementaria, su ausencia podrá comunicarse como limitación.

Si resulta imprescindible, un fallo técnico no recuperado deberá impedir una respuesta aparentemente satisfactoria.

La integración de horarios documentales utilizará registros verificables, no horarios inferidos libremente por Gemini.

## 7. Priorización de instalaciones

Se conservarán priorizar_puntos(), _priorizar_abiertos() y respuesta_geografica_integrada(), aplicando los siguientes criterios:

| Intención | Criterio principal |
|---|---|
| Instalaciones más cercanas | Distancia ascendente |
| Instalaciones disponibles ahora | Dentro del horario publicado y menor distancia |
| Instalaciones compatibles | Compatibilidad documental |
| Consulta con varios requisitos | Cumplimiento conjunto de las restricciones |

Cuando la disponibilidad actual sea un requisito explícito, las instalaciones fuera de horario o con horario desconocido no se presentarán como opciones que satisfacen dicho requisito.

En las consultas generales con evaluación temporal, se conservará la prioridad:

1. Dentro del horario publicado.
2. Horario desconocido.
3. Fuera del horario publicado.

Dentro de cada grupo se priorizará la menor distancia.

La respuesta integrada podrá mostrar la opción más cercana dentro de horario, una alternativa adicional y otras instalaciones próximas, identificando sus respectivas situaciones horarias.

### 7.1. Agrupación

_agrupar_puntos() conservará la agrupación por dirección normalizada, modalidad y coordenadas con cinco decimales.

Los registros correspondientes a distintos días o franjas de una misma instalación se conservarán dentro de su grupo.

El estado del grupo será dentro si alguno de sus horarios resulta aplicable; desconocido si ninguno está dentro y existe información insuficiente; fuera en los demás casos.

### 7.2. Alcance de los resultados

La síntesis podrá utilizar candidatos internos que no aparezcan entre los resultados públicos de proximidad.

Los límites y contratos correspondientes se establecen en [05-tools.md](05-tools.md).

El número de registros no equivale necesariamente al número de instalaciones únicas.

Cuando la limitación de candidatos afecte a la conclusión, deberá comunicarse.

No se presentarán alternativas que incumplan las restricciones como si satisficieran la consulta original.

## 8. Regla específica para envases de vidrio

Se conservará la franja municipal documentada en src/agent_schedule.py:

```python
VIDRIO_INICIO = time(8, 0)
VIDRIO_FIN = time(22, 30)
```

La evaluación utilizará:

```python
VIDRIO_INICIO <= hora_actual < VIDRIO_FIN
```

es_vidrio_envase_confirmado() únicamente activará esta regla cuando el RAG confirme que el residuo corresponde a un envase de vidrio destinado al contenedor verde.

No bastará con detectar la palabra vidrio ni una referencia negativa al contenedor verde.

No se aplicará automáticamente a vasos, copas, espejos, ventanas o vitrocerámicas.

La integración se realizará mediante anexos_temporales(), conservando la referencia NORMA-VIDRIO y FUENTE_HORARIO_VIDRIO conforme a [09-datos-y-fuentes.md](09-datos-y-fuentes.md).

No se realizará una nueva petición web ni una llamada adicional a Gemini para evaluar la franja.

Si únicamente se solicita conocer el horario permitido, no será necesario consultar la hora actual.

## 9. Consultas compuestas y continuidad

Las consultas compuestas combinarán únicamente las estrategias necesarias.

La integración distinguirá clasificación documental, observaciones visuales, compatibilidad, proximidad y horarios.

Se conservarán las restricciones anteriores que sigan siendo aplicables, sustituyéndolas cuando el consumidor indique otras nuevas.

El contexto conversacional permitirá interpretar reformulaciones, pero no sustituirá la evidencia necesaria.

No se reutilizarán automáticamente coordenadas, archivos ni evaluaciones temporales anteriores.

En consultas multimodales, la descripción validada orientará la recuperación. Las consultas exclusivamente descriptivas podrán resolverse mediante observaciones visuales admitidas.

Se solicitarán aclaraciones únicamente cuando falte información decisiva.

Las respuestas deterministas previas no modificarán el contexto operativo. Las aclaraciones generadas dentro del agente conservarán el ciclo de vida establecido en [06-langgraph.md](06-langgraph.md).

La integración determinista no deberá ocultar fallos técnicos imprescindibles.

## 10. Validación

Se conservarán las pruebas de regresión correspondientes a interpretación documental, modalidades, compatibilidad, geografía, horarios, priorización y consultas compuestas.

Se prestará especial atención a:

- Negaciones documentales interpretadas incorrectamente.
- Diferenciación entre móviles ordinarios y de 24 horas.
- Consultas exclusivamente documentales sin llamadas temporales innecesarias.
- Intervalos nocturnos y horarios incompletos.
- Restricciones temporales futuras.
- Compatibilidad, distancia y disponibilidad como criterios independientes.
- Aplicación exclusiva de la regla horaria a envases de vidrio confirmados.

Los casos de prueba y criterios de aceptación se desarrollan en [plan-pruebas.md](../docs/plan-pruebas.md), conforme a [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).