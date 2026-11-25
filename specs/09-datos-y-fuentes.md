# 09. Corpus, procedencia y fuentes externas

## 1. Objetivo

Definir el inventario documental, las fuentes autorizadas, los metadatos y los mecanismos de identificación de la procedencia de la información utilizada por ReciclaTÍA.

El corpus se limita al municipio de Madrid y no constituye un inventario universal de residuos ni una fuente de información actualizada permanentemente.

El alcance funcional se establece en [00-producto.md](00-producto.md).

## 2. Corpus documental

### 2.1. Estructura

```text
data/
└── raw/
    ├── csv/
    ├── html/
    ├── pdf/
    └── txt/
```

El corpus actual contiene cinco archivos CSV y diez archivos HTML.

Los directorios pdf/ y txt/ se conservan como parte de la estructura existente, pero no contienen documentos utilizados por el RAG.

Los documentos originales deberán conservarse como referencia de las transformaciones documentales.

### 2.2. Fuentes CSV

Los siguientes conjuntos proceden del Portal de Datos Abiertos del Ayuntamiento de Madrid.

| Archivo | Fuente oficial |
|---|---|
| puntos_limpios_fijos.csv | [Puntos limpios fijos](https://datos.madrid.es/dataset/200284-0-puntos-limpios-fijos) |
| puntos_limpios_moviles.csv | [Puntos limpios móviles](https://datos.madrid.es/dataset/300101-0-puntos-limpios-moviles) |
| puntos_limpios_moviles_24h.csv | [Puntos limpios móviles 24 horas](https://datos.madrid.es/dataset/900026-0-puntos-limpios-residuos) |
| puntos_limpios_proximidad.csv | [Puntos limpios de proximidad](https://datos.madrid.es/dataset/300198-0-puntos-proximidad) |
| tipos_residuos.csv | [Tipos de residuos y dónde depositarlos](https://datos.madrid.es/dataset/300199-0-tipo-residuo) |

### 2.3. Fuentes HTML

| Archivo | Página municipal de origen |
|---|---|
| fraccion_organica.html | [Recogida de residuos orgánicos](https://www.madrid.es/portales/munimadrid/es/Recogida-de-residuos-organicos/?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD&vgnextoid=12bc51e3f7bee510VgnVCM1000001d4a900aRCRD) |
| fraccion_papel.html | [Recogida de papel y cartón](https://www.madrid.es/portales/munimadrid/es/Inicio/El-Ayuntamiento/Moratalaz/Recogida-de-la-fraccion-papel-y-carton/?vgnextchannel=7cb0ca5d5fb96010VgnVCM100000dc0ca8c0RCRD&vgnextfmt=default&vgnextoid=d9eb6c9c78eb2910VgnVCM2000001f4a900aRCRD) |
| fraccion_plasticos_metales_briks.html | [Recogida de plásticos, metales y briks](https://www.madrid.es/portales/munimadrid/es/Recogida-de-plasticos-metales-y-briks-Horarios-y-frecuencias-de-recogida-/?vgnextchannel=3dfcbb21278fe410VgnVCM1000000b205a0aRCRD&vgnextfmt=default&vgnextoid=54c4ebd9be6e8610VgnVCM1000001d4a900aRCRD) |
| fraccion_resto.html | [Recogida de la fracción resto](https://www.madrid.es/portales/munimadrid/es/Recogida-fraccion-resto-no-reciclable-y-horario/?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD&vgnextoid=61c4ebd9be6e8610VgnVCM1000001d4a900aRCRD) |
| fraccion_vidrio.html | [Recogida de vidrio](https://www.madrid.es/portales/munimadrid/es/Recogida-de-vidrio/?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD&vgnextoid=e3ab6c9c78eb2910VgnVCM2000001f4a900aRCRD) |
| recogida_aceite_vegetal.html | [Recogida de aceite vegetal usado](https://www.madrid.es/portales/munimadrid/es/Inicio/Medio-ambiente/Recogida-de-residuos/Recogida-de-aceite-vegetal-usado/?vgnextchannel=f81379ed268fe410VgnVCM1000000b205a0aRCRD&vgnextfmt=default&vgnextoid=803fab39d9462510VgnVCM1000000b205a0aRCRD) |
| recogida_muebles_enseres.html | [Recogida de muebles, electrodomésticos y enseres](https://www.madrid.es/portales/munimadrid/es/Inicio/MedioAmbiente/ResiduosYLimpiezaUrbana/Tramites/Recogida-de-muebles-electrodomesticos-y-enseres/?vgnextchannel=e5bcbb21278fe410VgnVCM1000000b205a0aRCRD&vgnextfmt=default&vgnextoid=168e3381d0030910VgnVCM1000001d4a900aRCRD) |
| residuos_punto_limpio_fijo.html | [Puntos limpios fijos: cantidades admisibles](https://www.madrid.es/portales/munimadrid/es/UnidadWeb/Puntos-Limpios-Fijos-del-Ayuntamiento-de-Madrid-Descripcion-y-cantidades-admisibles-para-particulares/?vgnextchannel=e278e8124824b010VgnVCM1000000b205a0aRCRD&vgnextoid=cc9a2984ca480510VgnVCM2000000c205a0aRCRD) |
| residuos_punto_limpio_movil.html | [Puntos limpios móviles: cantidades admisibles](https://sede.madrid.es/portal/site/tramites/menuitem.1f3361415fda829be152e15284f1a5a0/?vgnextchannel=518aa38813180210VgnVCM100000c90da8c0RCRD&vgnextfmt=pda&vgnextoid=3cbc6163c4480510VgnVCM2000000c205a0aRCRD) |
| residuos_punto_limpio_proximidad.html | [Puntos limpios de proximidad: cantidades admisibles](https://www.madrid.es/portales/munimadrid/es/Inicio/Medio-ambiente/Gestiones-y-tramites/Puntos-Limpios-de-Proximidad-Descripcion-y-cantidades-admisibles-/?vgnextchannel=658f79ed268fe410VgnVCM1000000b205a0aRCRD&vgnextfmt=default&vgnextoid=2682a2dcf3189610VgnVCM1000001d4a900aRCRD) |

La versión actual de las páginas municipales puede diferir de los documentos incorporados al corpus.

## 3. Artefactos documentales

| Recurso | Finalidad |
|---|---|
| data/raw/ | Documentos originales |
| output/chunks.json | Fragmentos y metadatos |
| output/embeddings.json | Representaciones vectoriales |
| output/chroma_db/ | Índice de recuperación |

Los artefactos deberán conservar su coherencia y procedencia.

El pipeline, la configuración vectorial y los mecanismos de reconstrucción se establecen en [01-retrieval.md](01-retrieval.md).

Su incorporación a Docker se regula en [16-despliegue.md](16-despliegue.md).

## 4. Metadatos documentales

### 4.1. Campos relevantes

| Campo | Responsabilidad |
|---|---|
| source | Nombre del documento original |
| path | Ruta documental relativa |
| document_type | Naturaleza o modalidad del documento |
| district | Distrito municipal |
| destino | Destino documentado del residuo |
| source_row | Número de fila de origen |
| day | Día asociado al registro |
| latitude | Latitud de la instalación |
| longitude | Longitud de la instalación |

Los campos disponibles dependerán del documento y del tipo de registro.

No se completarán metadatos ausentes mediante inferencias del modelo.

Se conservarán otros campos existentes cuando resulten necesarios.

### 4.2. Conservación

Los procesos de transformación deberán preservar los metadatos necesarios para identificar el documento original, aplicar filtros y recuperar registros estructurados.

Los criterios de filtrado y tratamiento de filas se establecen en [02-mejoras-retrieval.md](02-mejoras-retrieval.md).

## 5. Referencias y procedencia pública

### 5.1. Catálogo de fuentes

Se utilizará un diccionario estático denominado FUENTES_OFICIALES:

```python
FUENTES_OFICIALES: dict[str, str]
```

El diccionario establecerá la correspondencia entre los quince nombres de archivo y las URL municipales definidas en los apartados 2.2 y 2.3.

No se mantendrán catálogos independientes en diferentes componentes.

### 5.2. Resolución de URL

La capa de servicios obtendrá la URL pública mediante el nombre de la fuente documental validada.

Ejemplo conceptual:

```python
url = FUENTES_OFICIALES.get(fuente["source"])
```

Si una referencia interna válida no dispone de una URL autorizada, se devolverá url=None.

Esta condición no permitirá aceptar referencias inventadas o estructuralmente inválidas.

La resolución de enlaces no realizará peticiones HTTP ni invocará Gemini.

### 5.3. Referencias normativas

Se conservará FUENTE_HORARIO_VIDRIO como referencia normativa utilizada por src/agent_schedule.py.

La referencia interna identificada mediante NORMA-VIDRIO utilizará esta constante como URL autorizada.

Su valor deberá ser coherente con la referencia correspondiente a fraccion_vidrio.html.

Las condiciones de aplicación de la regla se establecen en [04-consultas-generales.md](04-consultas-generales.md).

### 5.4. Contrato público

Las fuentes se transformarán mediante FuenteOut, definido en [12-contratos-http.md](12-contratos-http.md).

No se expondrán rutas locales del servidor.

La validación de citas, los identificadores locales de generación y la procedencia entre llamadas se regulan en [03-generacion.md](03-generacion.md).

Streamlit representará exclusivamente las referencias recibidas del backend.

## 6. Servicios y fuentes complementarias

| Recurso | Finalidad |
|---|---|
| ChromaDB | Recuperación documental |
| ArcGIS municipal | Información geográfica |
| Corpus local | Respaldo geográfico autorizado |
| Gemini | Embeddings, razonamiento, generación e identificación visual |
| Reloj del sistema | Información temporal de Madrid |

Gemini no constituye una fuente documental.

No se incorporarán motores de búsqueda, proveedores geográficos adicionales ni mecanismos de recuperación web abiertos.

### 6.1. Fuente geográfica externa

Servicio autorizado:

[API ArcGIS de puntos limpios del Ayuntamiento de Madrid](https://sigma.madrid.es/hosted/rest/services/RESIDUOS/PUNTOS_LIMPIOS/MapServer/5/query)

Los resultados identificarán su procedencia:

| Valor | Significado |
|---|---|
| api | Servicio municipal externo |
| corpus_local | Respaldo documental local |

Los contratos, restricciones, cálculo de distancias y condiciones de activación del respaldo se establecen en [05-tools.md](05-tools.md).

### 6.2. Información temporal

Los horarios procederán de los registros documentales o geográficos correspondientes.

La hora actual procederá del reloj del sistema mediante hora_actual().

La interpretación temporal se establece en [04-consultas-generales.md](04-consultas-generales.md).

## 7. Actualización y limitaciones

### 7.1. Actualización controlada

La actualización del corpus constituirá una operación independiente del flujo conversacional.

Cuando se modifiquen documentos deberán actualizarse los fragmentos, metadatos, embeddings e índice afectados.

Reconstruir ChromaDB utilizando embeddings existentes no constituye una actualización de los documentos municipales.

No se implementará una actualización automática permanente durante el PB03.

### 7.2. Limitaciones

- El corpus representa una selección de documentación municipal.
- Las fuentes pueden haber cambiado desde su incorporación.
- Los registros pueden contener información incompleta.
- Los horarios publicados no garantizan la apertura física.
- El respaldo geográfico local puede estar desactualizado.
- Las referencias válidas no garantizan por sí solas la exactitud factual de una respuesta.

Estas limitaciones deberán comunicarse cuando afecten al resultado.

## 8. Separación de datos

El corpus documental permanecerá separado de los datos operativos y de consumidores.

No se incorporarán automáticamente al corpus:

- Preguntas y respuestas.
- Conversaciones y checkpoints.
- Planes y decisiones HITL.
- Imágenes y descripciones visuales.
- Coordenadas personales.
- Credenciales y registros operativos.
- Resultados temporales de herramientas.

La persistencia relacional se regula en [13-persistencia.md](13-persistencia.md).

El tratamiento de información personal, la seguridad de las fuentes y los archivos temporales se regulan en [10-seguridad.md](10-seguridad.md) y [15-robustez-observabilidad.md](15-robustez-observabilidad.md).

## 9. Licencias y atribución

Según las referencias documentales existentes del proyecto, los conjuntos CSV procedentes del Portal de Datos Abiertos del Ayuntamiento de Madrid identifican la licencia Creative Commons Attribution 4.0 International (CC BY 4.0).

Deberán respetarse las condiciones aplicables a cada conjunto.

La transformación de los documentos en fragmentos o embeddings no elimina los requisitos de atribución correspondientes.

No se asumirá automáticamente que las páginas HTML utilizan la misma licencia que los conjuntos de datos abiertos.

Las condiciones de reutilización deberán revisarse cuando se incorporen nuevas fuentes o se amplíe el alcance del producto.

ReciclaTÍA no constituye un servicio oficial del Ayuntamiento de Madrid.

## 10. Criterios de aceptación

- Se conservan los quince documentos originales y sus referencias.
- Los metadatos permiten identificar la procedencia documental.
- FUENTES_OFICIALES contiene las correspondencias autorizadas.
- No se generan URL mediante Gemini.
- Las referencias públicas no exponen rutas locales.
- Los resultados geográficos identifican su procedencia.
- Se mantiene la separación entre corpus y datos operativos.
- Las actualizaciones documentales son independientes del flujo conversacional.
- Se conservan las condiciones de atribución.
- Los recursos documentales mantienen su coherencia durante los despliegues.

La estrategia de validación se establece en [08-pruebas-y-validacion.md](08-pruebas-y-validacion.md).