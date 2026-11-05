# Guía de estudio

## Recorrido recomendado

1. `radar/catalog_source.py`: descarga el JSON y el RDF, valida la envoltura y
   registra captura y manifiesto sin alterar los datos originales.
2. `radar/build_dashboard_data.py`: verifica el hash y el manifiesto, interpreta
   los campos observados y crea métricas agregadas.
3. `radar/update_dashboard.py`: aplica los criterios de frescura y publicación,
   prepara el archivo temporal y lo instala de forma atómica.
4. `public/index.html` y `public/radar.js`: presentan los agregados y el estado
   de carga en un dashboard accesible, con tablas acompañando los gráficos.
5. `radar/tests/`: prueba validaciones, fallos de descarga, privacidad y
   publicación con datos sintéticos.

## Ejecutar pruebas

Desde la raíz del proyecto:

```powershell
python -m unittest discover -s radar\tests -v
node --check public\radar.js
```

Las pruebas son offline; no requieren una captura local ni dependen de la
disponibilidad de Open Data Euskadi.

## Vista local

```powershell
python -m http.server 8000 --directory public
```

Abre `http://localhost:8000/`. Sirve la carpeta por HTTP porque el navegador
bloquea la carga local de JSON a través de `file://`.

## Límites interpretativos

El catálogo cubre 90 días móviles, no todo el histórico. El campo de publicación,
el de órgano y los formatos de fecha se basan en observaciones del conjunto,
no en un contrato de esquema del proveedor. La fecha RDF del catálogo no es el
instante de descarga. Los avisos son publicaciones administrativas, no
adjudicaciones confirmadas. Véase el [inventario de esquema](schema-inventory.md)
y la nota de [storytelling](storytelling.md).
