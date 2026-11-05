# Panel de indicadores de contratación pública

Proyecto de datos que transforma el catálogo abierto de contrataciones
administrativas recientes de Euskadi en métricas agregadas y un dashboard
estático. No es un buscador de expedientes ni un histórico completo: la fuente
cubre una ventana móvil de 90 días.

## Alcance y fuentes

- El dashboard agrega anuncios por fecha de publicación y órgano, muestra
  completitud de campos y señala problemas de calidad de fechas.
- El JSON público no incluye títulos, identificadores, enlaces ni filas
  individuales.
- La ficha de Open Data Euskadi identifica el JSON del catálogo bajo
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Esa referencia no
  se extiende automáticamente a otras API del portal.
- La fecha RDF de actualización de la fuente se distingue del momento de
  descarga. El código aplica una política de frescura de tres días.

## Estructura

- `radar/`: ingesta, agregación, validación, pruebas y capturas locales
  excluidas de Git.
- `public/`: dashboard independiente y único resumen agregado permitido para
  publicación.
- `.github/workflows/update-data.yml`: actualización diaria y validación del
  resumen público.
- `docs/`: arquitectura, guía de estudio, límites narrativos y esquema
  observado.

El nombre `radar` se conserva como namespace interno de Python por continuidad
del código; el nombre público del proyecto es **Panel de indicadores de
contratación pública**.

## Uso local

Desde la raíz, sirve el dashboard por HTTP para que pueda cargar su JSON:

```powershell
python -m http.server 8000 --directory public
```

Abre `http://localhost:8000/`. Abrir el HTML con `file://` no permite cargar de
forma fiable el resumen JSON por las restricciones del navegador.

El dashboard ofrece un selector ES/EN. Sin una preferencia guardada, detecta
un navegador en inglés y, en los demás casos, muestra español. La elección se
recuerda en el navegador; el mismo idioma se comparte con el CV y el
portafolio de Rafael cuando se visitan en ese navegador.

Las pruebas offline usan únicamente la biblioteca estándar de Python:

```powershell
python -m unittest discover -s radar\tests -v
node --check public\radar-language.js
node --check public\radar.js
```

Para descargar y revisar una captura local:

```powershell
python -m radar.catalog_source
python -m radar.build_dashboard_data --help
```

Las capturas originales se guardan bajo `radar/data/raw/` y no se publican.
La actualización automática ejecuta `prepare`, corre las pruebas, valida el
JavaScript y solo después instala `public/data/radar-summary.json` de forma
atómica. Un error conserva el último resumen válido.

## Actualización y publicación

GitHub Actions ejecuta **Update public indicators** a diario (04:23 UTC) o
manualmente desde **Actions → Update public indicators → Run workflow**. El job
comprueba la estructura y frescura de la fuente, valida los agregados y
confirma únicamente el JSON público si ha cambiado.

El dashboard conserva las rutas y sincroniza su selector y recursos ES/EN desde
este repositorio. El sitio de Rafael integra el dashboard conservando la URL
`/radar.html`. Su workflow obtiene los archivos de `public/` desde la rama
principal de este repositorio y los publica junto con la web en Azure Static
Web Apps. La web vuelve a sincronizarlos cada día después de la actualización
programada. Este repositorio no contiene el código privado de despliegue de
Azure ni necesita credenciales de Azure.

## Documentación

- [Arquitectura y flujo de datos](radar/docs/arquitectura.md)
- [Guía de estudio](radar/docs/guia-de-estudio.md)
- [Storytelling y límites](radar/docs/storytelling.md)
- [Inventario de esquema observado](radar/docs/schema-inventory.md)
