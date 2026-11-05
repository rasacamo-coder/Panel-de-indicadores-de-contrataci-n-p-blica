# Arquitectura y flujo de datos

## Componentes

- `radar/catalog_source.py`: descarga el JSON del catálogo y sus metadatos RDF;
  guarda la captura bruta y un manifiesto local bajo `radar/data/raw/`.
- `radar/build_dashboard_data.py`: valida la captura y produce métricas
  agregadas.
- `radar/update_dashboard.py`: prepara, valida y publica el resumen de forma
  atómica.
- `public/`: HTML, CSS, JavaScript y `data/radar-summary.json` necesarios para
  servir el dashboard por HTTP.
- `.github/workflows/update-data.yml`: actualiza el resumen y confirma solo el
  agregado público cuando cambia.

El namespace Python se llama `radar` por continuidad del código, aunque el
nombre público del proyecto es **Panel de indicadores de contratación pública**.

## Flujo

```text
Catálogo JSON + metadatos RDF
        ↓
radar/catalog_source.py
  captura bruta local + manifest.json
        ↓
radar/update_dashboard.py prepare
  validar frescura, fechas y estructura
  generar JSON temporal fuera de public/
        ↓
radar/update_dashboard.py publish
  validar esquema y agregados permitidos
  reemplazo atómico del resumen
        ↓
public/data/radar-summary.json
        ↓
public/radar.js → public/index.html
```

La fuente consultada es el JSON de contrataciones administrativas de los
últimos 90 días. La ventana es móvil. La fecha RDF se distingue del instante de
descarga; el umbral de frescura de tres días es una política del proyecto, no
una garantía del proveedor.

El resumen contiene únicamente agregados y metadatos permitidos: conteos,
series, métricas de completitud y calidad. No incluye títulos, expedientes,
enlaces a registros individuales ni la captura bruta. `publish` vuelve a
validar el esquema y sustituye el archivo atómicamente; ante un error se
conserva el último JSON válido. Una variación del volumen se advierte, pero no
bloquea la publicación porque el historial local no justifica un umbral
estadístico.

## Pruebas y automatización

Las pruebas offline usan datos sintéticos y no necesitan descargar datos:

```powershell
python -m unittest discover -s radar\tests -v
node --check public\radar.js
```

El workflow ejecuta la ingesta, las pruebas, el análisis sintáctico del
JavaScript y la instalación del resumen en ese orden. Solo confirma
`public/data/radar-summary.json`.

El CV web conserva la ruta `/radar.html` y su workflow toma los recursos desde
`public/` en la rama principal de este repositorio. La web vuelve a sincronizar
el agregado una vez al día después de la actualización. No se transfieren
capturas ni se necesita un token de Azure en este repositorio.

## Fuente y licencia

La ficha del catálogo de los últimos 90 días identifica ese JSON bajo
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Esa atribución se
refiere a la ficha concreta y no se extiende automáticamente a otras API del
portal. El dashboard enlaza la fuente y señala que presenta agregaciones y
transformaciones.
