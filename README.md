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

Los registros empleados por las pruebas son sintéticos y solo comprueban la
estructura de respuesta. No representan anuncios reales ni resultados del
conjunto.

Para descargar una muestra pequeña, proporciona un intervalo fijo de fechas de
publicación:

```powershell
python -m radar.extract_sample --publication-date-gt 2026-10-20 --publication-date-lt 2026-10-27 --limit 5
```

Los límites `.gt` y `.lt` son los nombres de filtro documentados por la API.
El programa valida que la respuesta tenga una envoltura JSON reconocible y al
menos un elemento. Si no se reciben registros o la respuesta no es válida, el
programa falla explícitamente y no crea una ejecución vacía. Una muestra puede
quedar vacía para un intervalo sin avisos; en ese caso elige un intervalo
distinto después de consultar la documentación, sin ampliar automáticamente la
consulta.

Cada ejecución válida se guarda en una carpeta nueva bajo
`radar\data\raw\`. Contiene la respuesta descargada y un manifiesto con la URL,
los filtros, la hora UTC, el número de elementos y el estado de las
comprobaciones de estructura. Las carpetas de datos brutos están excluidas de
Git. No se imprimen los registros en consola y las ejecuciones anteriores no
se sobrescriben.

Una consulta limitada por fechas es repetible como solicitud, pero no garantiza
que el servidor devuelva exactamente los mismos registros en el futuro: la
fuente se actualiza diariamente y puede corregir datos. Para pruebas de
transformación reproducibles se conservará más adelante un fixture pequeño,
revisado y minimizado, con su fecha de captura y atribución; no se versionan
respuestas brutas en esta fase.

## Limitaciones actuales

- Aún no se han documentado los significados, tipos, ausencias o claves de
  negocio de los campos de los registros.
- No hay limpieza, validación de calidad del dominio, análisis ni dashboard.
- La petición de muestra no garantiza por sí sola que el endpoint represente
  exactamente el dataset anual de la ficha.
- El workflow de Azure Static Web Apps permanece sin cambios. Despliega desde
  la raíz del repositorio; no se debe abrir un pull request ni fusionar esta
  carpeta a `main` hasta revisar si el código y los archivos del proyecto
  podrían incluirse en el artefacto público.
