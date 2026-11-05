# Cómo presentar el proyecto

## Resumen breve

> Construí un panel que transforma el catálogo abierto de contrataciones
> administrativas recientes de Euskadi en indicadores agregados de actividad,
> órganos de contratación y calidad de datos. El flujo valida fuente y
> metadatos antes de publicar el dashboard y evita exponer registros
> individuales.

## Capacidades demostrables

- Ingesta y validación de JSON y metadatos RDF con Python.
- Verificación de frescura, estructura, fechas e integridad mediante hash.
- Agregación a un esquema público restringido, pruebas automatizadas y
  publicación atómica.
- Visualización accesible con HTML, CSS, JavaScript, gráficos SVG y tablas.
- Actualización diaria con GitHub Actions e integración del artefacto estático
  en una web de Azure Static Web Apps.

## Alcance y cautelas

- La fuente presenta una ventana móvil de 90 días, no un histórico completo.
- El contenido representa anuncios publicados, no adjudicaciones.
- Los campos y formatos de fecha se basan en lo observado y pueden cambiar.
- No atribuir ahorros, impacto económico, decisiones de compra ni detección de
  oportunidades: el proyecto no mide esos resultados.
- Distinguir la fecha RDF de la fuente del instante en que se descargó.
