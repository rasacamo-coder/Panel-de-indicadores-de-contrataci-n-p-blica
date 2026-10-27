# Muestra local del Radar de Contratación Pública de Euskadi

Este paquete obtiene una página pequeña del endpoint oficial de avisos de
contratación. No transforma los registros ni presupone que los campos de una
respuesta sean suficientes para calcular métricas.

## Fuente y alcance

- API documentada: [API REST de Contrataciones Públicas](https://opendata.euskadi.eus/webopd00-apicontract/es/?api=procurements)
- Endpoint: `GET https://api.euskadi.eus/procurements/contracting-notices`
- Ficha candidata: [Contrataciones Administrativas del 2026](https://opendata.euskadi.eus/catalogo/-/contrataciones/contrataciones-administrativas-del-2026/)
- Licencia de la ficha: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)

La documentación de la API describe datos de avisos desde 2015 y actualización
diaria. La ficha de 2026 describe anuncios publicados ese año por el Gobierno
Vasco, sus organismos autónomos y entes públicos. Aún no se ha verificado que el
alcance completo del endpoint y el de esa ficha sean idénticos. La ficha declara
CC BY 4.0; antes de redistribuir respuestas de la API hay que confirmar que esa
licencia cubre el alcance concreto de la consulta.

La API documenta filtros `publication-date.gt` y `publication-date.lt`,
ordenación, `currentPage` e `itemsOfPage` (10 por defecto, máximo 50). El
programa exige límites de fecha explícitos, solicita como máximo cinco
resultados por defecto y utiliza solo la biblioteca estándar de Python. La API
no publica aquí una cuota de consultas; el programa limita cada petición a una
página pequeña.

## Requisitos

- Python 3.10 o posterior.
- Acceso de red al endpoint HTTPS oficial.
- No hacen falta paquetes externos, credenciales ni recursos de Azure.

## Probar

Desde la raíz del repositorio, ejecutar las pruebas offline:

```powershell
python -m unittest discover -s radar\tests -v
```

Los registros empleados por las pruebas son sintéticos y están identificados
como tales en los propios casos. No representan anuncios reales ni resultados
del conjunto.

Para descargar una muestra pequeña, proporciona un intervalo fijo de fechas de
publicación:

```powershell
python -m radar.extract_sample --publication-date-gt 2026-10-20 --publication-date-lt 2026-10-27 --limit 5
```

Los límites `.gt` y `.lt` son los nombres de filtro documentados por la API.
El programa comprueba por separado:

1. Que el servidor devuelve JSON y que la envoltura incluye los campos de
   paginación esperados y una lista `items` que respeta el límite pedido.
2. Que cada elemento de `items` es un objeto JSON.
3. Que los registros cumplen un tipado preliminar basado en
   [el inventario de esquema](docs/schema-inventory.md).

La validación preliminar distingue errores bloqueantes y advertencias:

- Un elemento que no sea un objeto JSON, una fecha de publicación con tipo
  distinto de texto o una fecha de publicación que no respete `AAAA-MM-DD`
  impide guardar la nueva ejecución. Las ejecuciones anteriores permanecen
  intactas.
- Los campos ausentes o nulos, los tipos inesperados, los campos desconocidos y
  la discrepancia `object`/`name` se registran como advertencias. No se declaran
  campos obligatorios, no se renombran campos y las advertencias no impiden
  guardar la respuesta.
- Las posibles colisiones de `id` o `code` se informan para revisión. No se
  eliminan registros ni se define una clave única.
- El manifiesto de cada ejecución incluye el estado de validación y el detalle
  de advertencias. Los errores bloqueantes se informan al usuario y no generan
  una nueva ejecución guardada. El mensaje de consola informa del número de
  advertencias.

Esta comprobación es estructural y de tipado preliminar, no una validación de
dominio completa. Los tipos de varios campos se apoyan en la única fila
inspeccionada y podrían cambiar en la fuente; por eso un tipo inesperado es una
advertencia, no un error bloqueante. Solo se valida el formato de las fechas de
primera y última publicación, cuyo patrón `AAAA-MM-DD` está documentado. Para
`deadlineDate` y `openingDates` se comprueba el tipo observado, pero no se
impone un formato de fecha aún no suficientemente confirmado. No se aplican
reglas de negocio ni se interpreta un aviso como contrato adjudicado.

Una respuesta correcta con cero elementos se guarda como una ejecución con
`result_status: "empty"` y el comando termina con un mensaje informativo. No es
un error de red ni una respuesta inválida, pero tampoco aporta filas para
análisis. Se guarda en una carpeta nueva; las ejecuciones anteriores no se
eliminan ni se sobrescriben. Los errores HTTP, de conexión, timeout, tipo de
contenido, JSON o almacenamiento se muestran como mensajes breves y terminan
con código distinto de cero, sin presentar una traza al usuario.

Cada respuesta de API válida se guarda en una carpeta nueva bajo
`radar\data\raw\`. Contiene la respuesta descargada y un manifiesto con la URL,
los filtros, la hora UTC, el número de elementos, si la muestra está vacía y el
resultado de las comprobaciones estructurales. Las carpetas de datos brutos
están excluidas de Git. No se imprimen los registros en consola y las
ejecuciones anteriores no se sobrescriben.

Una consulta limitada por fechas es repetible como solicitud, pero no garantiza
que el servidor devuelva exactamente los mismos registros en el futuro: la
fuente se actualiza diariamente y puede corregir datos. Para pruebas de
transformación reproducibles se conservará más adelante un fixture pequeño,
revisado y minimizado, con su fecha de captura y atribución; no se versionan
respuestas brutas en esta fase.

## Limitaciones actuales

- El inventario de esquema y el tipado son preliminares; obligatoriedad,
  nulabilidad, semántica completa y reglas de negocio siguen sin confirmarse.
- No hay limpieza, validación de calidad del dominio, análisis ni dashboard.
- La petición de muestra no garantiza por sí sola que el endpoint represente
  exactamente el dataset anual de la ficha.
- El workflow de Azure Static Web Apps permanece sin cambios. Despliega desde
  la raíz del repositorio; no se debe abrir un pull request ni fusionar esta
  carpeta a `main` hasta revisar si el código y los archivos del proyecto
  podrían incluirse en el artefacto público.
