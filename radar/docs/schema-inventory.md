# Inventario del esquema de avisos de contratación

## Alcance y cautelas

La fuente principal investigada es la API REST de Contrataciones Públicas de
Open Data Euskadi. Su operación de avisos devuelve **anuncios de contratación**.
Un anuncio no equivale necesariamente a un contrato adjudicado: la API expone
recursos diferenciados para avisos, contratos y procedimientos de adjudicación,
y documenta enlaces entre algunos de ellos. Por tanto, no se deben presentar
recuentos de avisos como recuentos de contratos únicos ni interpretar el estado
de un aviso como el historial completo de adjudicación.

Este inventario contrasta la especificación OpenAPI disponible durante la
investigación con una única fila de la muestra local. La fila sirve como
observación, no como descripción representativa del conjunto. No se incluyen
valores de registros reales.

## Niveles de evidencia

- **Documentado:** significado o tipo declarado por la documentación oficial
  consultada. No implica que el campo sea obligatorio, esté siempre presente o
  tenga siempre un valor no nulo.
- **Observado:** tipo que tenía el campo en la única fila local inspeccionada.
  La presencia en esa fila no establece cobertura general.
- **Desconocido:** aspecto que no se pudo establecer con la especificación y la
  muestra disponibles. No se asume obligatoriedad, unicidad ni regla de negocio.

Los tipos observados son tipos JSON: texto, entero, booleano, objeto o lista.
El esquema oficial suele describir números como `number`; que la muestra
contenga un entero no demuestra que todos los valores posibles sean enteros.

## Inventario de campos observados

| Campo | Tipo observado en la fila local | Significado documentado oficialmente | Aspectos aún desconocidos |
|---|---|---|---|
| `_links` | objeto | Enlaces relacionados con el recurso. La muestra incluye enlaces identificados como `self` y `contracts`. | Estabilidad de los enlaces, cardinalidad de contratos y garantías de integridad. |
| `budgetWithoutVAT` | entero | Presupuesto sin IVA; la especificación lo tipa como número. | Moneda, precisión, cobertura, nulabilidad y relación con importes adjudicados. |
| `code` | texto | Código del anuncio de contratación. | Unicidad, estabilidad y comportamiento ante modificaciones o publicaciones repetidas. |
| `contractProcedureStatus` | objeto | Estado del procedimiento de contratación. | Catálogo completo de valores, secuencia de estados y relación con fases de adjudicación. |
| `contractProcedureType` | objeto | Tipo de procedimiento de contratación. | Catálogo completo, estabilidad de etiquetas y valores posibles ausentes. |
| `contractType` | objeto | Tipo de contrato. | Catálogo completo, estabilidad de etiquetas y valores posibles ausentes. |
| `contractingAuthority` | objeto | Órgano de contratación. | Identificador estable, estructura completa y cobertura de sus propiedades. |
| `deadlineDate` | texto | Fecha límite; la especificación la representa como texto con patrón de fecha y hora. | Zona horaria, formato exacto en todos los registros, nulabilidad y tratamiento de plazos modificados. |
| `entity` | objeto | Entidad relacionada con el anuncio. | Relación exacta con el órgano de contratación y estabilidad de sus identificadores. |
| `financedEuropeanFunds` | booleano | Indica si hay financiación de fondos europeos. | Nulabilidad y criterio documental preciso para los casos no informados. |
| `firstPublicationDate` | texto | Fecha de primera publicación en el perfil; la especificación indica un patrón de fecha `AAAA-MM-DD`. | Zona horaria no aplicable si es solo fecha, cobertura y posibles correcciones retrospectivas. |
| `id` | entero | Identificador del anuncio de contratación. | Alcance de unicidad y estabilidad temporal; no se ha demostrado una clave definitiva. |
| `lastPublicationDate` | texto | Fecha de última publicación en el perfil; la especificación indica un patrón de fecha `AAAA-MM-DD`. | Qué cambios actualizan esta fecha y cómo tratar correcciones o republicaciones. |
| `mainEntityOfPage` | texto | URL de la página principal del anuncio. | Estabilidad de la URL y si identifica de manera única una versión del anuncio. |
| `minorContract` | booleano | Indica si el anuncio corresponde a un contrato menor. | Nulabilidad y aplicación uniforme de esta clasificación. |
| `numberBidders` | entero | Número de licitadores; la especificación lo tipa como número. | Si cuenta ofertas o licitadores, cuándo se informa y cómo interpretar valores ausentes. |
| `object` | texto | No aparece como propiedad del modelo `contractingNotice` consultado. | Significado preciso y relación —si existe— con `name`, que sí aparece en el esquema. |
| `openingDates` | lista de textos | Fechas de apertura. La documentación describe prefijos para aperturas legal, técnica y económica, o apertura única. | Formato exhaustivo, posibles ausencias y si todas las fases se registran de forma uniforme. |
| `recoveryPlan` | booleano | Indica relación con el Plan de Recuperación, Transformación y Resiliencia. | Nulabilidad y criterio exacto para asignar el valor. |
| `sara` | booleano | Indica sujeción a regulación armonizada. | Nulabilidad y criterio legal aplicado en cada caso. |
| `subjectAppeal` | booleano | Indica si el anuncio está sujeto a recurso. | Nulabilidad y alcance exacto de la clasificación. |

La tabla no declara que los campos sean obligatorios. Todos los campos de la
fila examinada tenían un valor no nulo y no vacío; una observación de una fila
no permite estimar la frecuencia de campos ausentes o vacíos en el conjunto.

## Discrepancia `object` / `name`

La especificación OpenAPI consultada documenta `name` como el asunto del
anuncio y su ejemplo de respuesta también utiliza `name`. En cambio, la única
fila de la muestra local contiene `object` y no `name`. `object` no aparece
como propiedad del modelo `contractingNotice` consultado.

No hay evidencia suficiente para afirmar que ambos nombres sean equivalentes.
La diferencia podría deberse a una variación de esquema, versión o respuesta.
Hasta resolverla:

- conservar el nombre recibido, sin renombrarlo ni traducirlo;
- tratar la discrepancia como una observación de esquema que requiere
  seguimiento;
- no exigir exclusivamente `name` ni exclusivamente `object` en una validación
  de dominio;
- no publicar comparaciones o agrupaciones basadas en ese campo como si su
  semántica estuviera confirmada.

## Identificación y posibles duplicados

- **`id`:** candidato principal para identificar un recurso de aviso, porque la
  documentación lo describe como identificador. No se ha confirmado que sea
  único y estable en todas las versiones, periodos o conjuntos.
- **`code`:** candidato auxiliar, documentado como código del anuncio. No está
  demostrada su unicidad ni que no se reutilice ante modificaciones o
  republicaciones.
- **Enlaces (`_links.self` y `mainEntityOfPage`):** pueden ayudar a comparar
  recursos, pero no se ha probado que sean permanentes ni que identifiquen una
  versión concreta.

No se define una clave natural ni se eliminan registros por duplicidad. Las
primeras implementaciones deberían informar de posibles colisiones para
revisión, conservando los registros originales.

## Validación de calidad: implementado y pendiente

El extractor separa la validación de la envoltura API de la validación
preliminar de registros. Comprueba que cada elemento sea un objeto JSON,
registra campos inventariados ausentes o nulos, tipos inesperados y campos
desconocidos, y señala explícitamente cuándo aparece solo uno de `object` y
`name`. También informa de colisiones candidatas de `id` y `code`; no elimina
ni deduplica registros.

Los tipos inesperados, las ausencias, los nulos, los campos desconocidos y la
discrepancia `object`/`name` son advertencias porque la evidencia disponible no
confirma obligatoriedad ni estabilidad completa del esquema. Son errores
bloqueantes los registros que no sean objetos JSON y las fechas de publicación
que no sean texto o no cumplan el patrón documentado `AAAA-MM-DD`. Las
ejecuciones con errores no se guardan y no sustituyen muestras anteriores. La
fecha límite y las fechas de apertura solo reciben comprobación de tipo; no se
impone un formato exacto que el inventario no confirma.

Esta validación es preliminar, no semántica ni completa. Quedan pendientes:

1. **Paginación:** ampliar la revisión de coherencia entre páginas, totales,
   páginas vacías y última página cuando sus reglas estén confirmadas.
2. **Fechas:** confirmar formato, zona horaria y valores ausentes para la fecha
   límite y las fechas de apertura.
3. **Relaciones:** inspeccionar la resolución de enlaces entre avisos y
   contratos y las referencias a entidad, autoridad, tipo y estado, sin asumir
   cardinalidad ni secuencia de fases.
4. **Identidad:** verificar el alcance y estabilidad de `id`, `code` y enlaces
   antes de proponer una clave o deduplicación.
5. **Evolución:** comparar esquemas entre ejecuciones y revisar advertencias
   antes de convertirlas en errores.

No se han añadido reglas de negocio ni requisitos de campos obligatorios.

## Métricas candidatas y límites

Una vez validados los campos, la cobertura y su significado, podrían evaluarse:

- número de **avisos** por fecha de primera o última publicación;
- distribución de avisos por tipo de contrato, procedimiento o estado, después
  de confirmar los catálogos y sus etiquetas;
- recuentos por entidad u órgano, si se identifica un campo estable y se
  verifica su cobertura;
- indicadores de calidad, como proporción de campos ausentes, nulos o con tipo
  inesperado por ejecución.

Todos los recuentos deben etiquetarse como avisos, no como contratos
adjudicados. Deben esperar validación adicional las sumas o comparaciones de
presupuestos, las métricas de adjudicación, la evolución por fases, los
recuentos de licitadores y las conclusiones de concentración. En particular,
la especificación identifica un presupuesto sin IVA, pero aún no se han
confirmado aquí la moneda, la cobertura ni su equivalencia con importes
adjudicados.

## Licencia y reutilización

La ficha anual de contrataciones de 2026 declara CC BY 4.0. Esa ficha no
demuestra por sí sola que sus condiciones se apliquen a todas las respuestas de
la API, cuyo alcance documentado es más amplio. Las condiciones aplicables
específicamente al endpoint y a la redistribución de sus respuestas siguen
pendientes de confirmación.

No se recomienda publicar respuestas de la API ni datos derivados hasta
confirmar esas condiciones. Si se confirma CC BY 4.0, la reutilización debe
incluir atribución apropiada, enlace a la licencia e indicación de los cambios,
según sus términos.

## Fuentes y trazabilidad

Fuentes oficiales identificadas durante la investigación:

- [API REST de Contrataciones Públicas — Open Data Euskadi](https://opendata.euskadi.eus/api-procurements/?api=procurements)
- [Especificación OpenAPI de Contrataciones Públicas](https://opendata.euskadi.eus/contenidos/recurso_tecnico/data_apirest/es_def/adjuntos/procurements.json)
- [Ficha: Contrataciones Administrativas del 2026](https://opendata.euskadi.eus/catalogo/-/contrataciones/contrataciones-administrativas-del-2026/)
- [Orientación oficial sobre reutilización de datos abiertos](https://opendata.euskadi.eus/como-reutilizar/-/reutilizar-datos-abiertos/)
- [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)

La muestra local inspeccionada contiene **una sola fila**. La inspección se
limitó a nombres de campos, tipos y presencia de valores; no se reproducen
valores reales en este documento. No se hicieron nuevas peticiones a la API
para elaborar este inventario. Los hallazgos de la muestra no sustituyen la
documentación oficial ni permiten inferir obligatoriedad, unicidad o
representatividad.
