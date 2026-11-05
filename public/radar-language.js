(() => {
  "use strict";

  const STORAGE_KEY = "rafael-site-language";
  const translations = {
    "Panel de indicadores de contratación pública | Rafael Castillo": "Public Procurement Indicators | Rafael Castillo",
    "Saltar al contenido": "Skip to content",
    "Perfil": "Profile",
    "Experiencia": "Experience",
    "Formación": "Education",
    "Competencias": "Skills",
    "Proyectos": "Projects",
    "Sobre mí": "About me",
    "Actividad": "Activity",
    "Calidad": "Data quality",
    "Metodología": "Methodology",
    "PROYECTO DE DATOS · EUSKADI": "DATA PROJECT · EUSKADI",
    "Indicadores de": "Public procurement",
    "contratación pública.": "indicators.",
    "Una lectura exploratoria de los anuncios administrativos publicados recientemente: actividad, órganos que publican y señales de calidad que conviene interpretar con contexto.": "An exploratory view of recently published administrative procurement notices: publication activity, contracting authorities, and data-quality signals that should be interpreted in context.",
    "Analiza anuncios del catálogo móvil de los últimos 90 días; no es un histórico completo ni un recuento de contratos adjudicados.": "This analysis covers notices in the rolling 90-day catalog; it is neither a complete historical record nor a count of awarded contracts.",
    "ESTADO DE LA INSTANTÁNEA": "SNAPSHOT STATUS",
    "Actualización publicada": "Source last updated",
    "Descarga del conjunto": "Dataset downloaded",
    "Resumen generado": "Summary generated",
    "Cargando el resumen agregado…": "Loading the aggregated summary…",
    "01 / VOLUMEN": "01 / VOLUME",
    "anuncios en la captura": "notices in this snapshot",
    "02 / ÓRGANOS": "02 / AUTHORITIES",
    "órganos distintos observados": "distinct authorities observed",
    "03 / PUBLICACIÓN": "03 / PUBLICATION",
    "fechas distintas con anuncios": "distinct dates with notices",
    "04 / REVISIÓN": "04 / REVIEW",
    "plazos anteriores a la actualización de la fuente": "deadlines before the source update",
    "01": "01",
    "ACTIVIDAD": "ACTIVITY",
    "Ritmo de": "Publication",
    "publicación.": "patterns.",
    "Recuento por fecha de publicación documentada en el catálogo.": "Notice counts by publication date recorded in the catalog.",
    "Filtrar actividad por órgano": "Filter activity by authority",
    "Todos los órganos": "All authorities",
    "Anuncios por fecha de publicación": "Notices by publication date",
    "Gráfico de líneas que se actualizará al cargar el resumen de datos.": "Line chart that updates when the data summary loads.",
    "El gráfico se basa en fechas válidas con formato día/mes/año.": "The chart uses valid dates in day/month/year format.",
    "Consultar los valores del gráfico en una tabla": "View chart values in a table",
    "Volumen de anuncios por fecha de publicación según el filtro seleccionado": "Notice counts by publication date for the selected filter",
    "Fecha": "Date",
    "Anuncios": "Notices",
    "02": "02",
    "ÓRGANOS ACTIVOS": "ACTIVE AUTHORITIES",
    "Quién publica": "Who publishes",
    "más avisos.": "the most notices.",
    "Diez órganos con mayor volumen en esta instantánea; no implica adjudicación.": "The ten authorities with the most notices in this snapshot; this does not indicate contract awards.",
    "Diez órganos con más anuncios": "Ten authorities with the most notices",
    "Gráfico de barras con recuento agregado por órgano de contratación.": "Bar chart of aggregated notice counts by contracting authority.",
    "Los nombres corresponden al texto observado en el campo del órgano de contratación.": "Names reflect the text found in the contracting-authority field.",
    "Consultar el ranking en una tabla": "View the ranking in a table",
    "Diez órganos con mayor número de anuncios": "Ten authorities with the highest number of notices",
    "Posición": "Rank",
    "Órgano de contratación": "Contracting authority",
    "03": "03",
    "CALIDAD Y LÍMITES": "DATA QUALITY & LIMITATIONS",
    "Transparencia sobre": "Transparency about",
    "los datos.": "the data.",
    "La completitud describe presencia de valores, no su validez semántica.": "Completeness describes whether values are present, not whether they are semantically valid.",
    "Completitud de campos usados": "Completeness of fields used",
    "Valores no vacíos en los campos analizados": "Non-empty values in analyzed fields",
    "Campo observado": "Observed field",
    "No vacíos": "Non-empty",
    "Vacíos": "Empty",
    "Completitud": "Completeness",
    "Fechas para revisar": "Dates to review",
    "Publicación: formato inválido": "Publication: invalid format",
    "Publicación: vacío": "Publication: empty",
    "Plazo límite: formato inválido": "Deadline: invalid format",
    "Plazo límite: vacío": "Deadline: empty",
    "Los plazos anteriores al día de actualización publicado se señalan como posibles casos para revisar; el dato no confirma que el plazo esté cerrado ni que el anuncio haya quedado sin efecto.": "Deadlines earlier than the published source-update date are flagged for review; this does not confirm that a deadline has closed or that a notice is no longer active.",
    "04": "04",
    "MÉTODO Y FUENTE": "METHOD & SOURCE",
    "Agregados claros,": "Clear aggregates,",
    "sin prometer de más.": "without overclaiming.",
    "Se conserva la captura original fuera del sitio público. La automatización valida su hash, los metadatos y las fechas con los formatos observados antes de instalar únicamente recuentos agregados.": "The original snapshot is kept outside the public site. Automation validates its hash, metadata, and dates against observed formats before publishing aggregated counts only.",
    "Alcance y limitaciones": "Scope and limitations",
    "La fuente reúne anuncios de contratación administrativa de los últimos 90 días; la ventana es móvil.": "The source contains administrative procurement notices from the last 90 days; this is a rolling window.",
    "Los nombres y significados de campo son observaciones preliminares, no un esquema contractual exhaustivo.": "Field names and meanings are preliminary observations, not a comprehensive procurement schema.",
    "La fecha de publicación se toma de": "The publication date is taken from",
    ". No se sustituye por": ". It is not replaced with",
    "Los órganos distintos se cuentan por el texto observado, sin unificar variantes.": "Distinct authorities are counted by the observed text, without merging variants.",
    "No se muestran datos individuales, importes adjudicados ni tipos de contrato como métricas.": "Individual records, awarded amounts, and contract types are not shown as metrics.",
    "Atribución": "Attribution",
    "Fuente:": "Source:",
    "Open Data Euskadi · Contrataciones administrativas de los últimos 90 días": "Open Data Euskadi · Administrative procurement notices from the last 90 days",
    "; esta atribución no se extiende a otras API del portal. La fecha publicada por la fuente y el momento de descarga se presentan por separado.": "; this attribution does not extend to other portal APIs. The source's publication date and the download time are shown separately.",
    ". La ficha de este conjunto identifica el JSON bajo": ". The dataset record identifies the JSON under",
    "; esta atribución no se extiende a otras API del portal. Se han realizado agregaciones y transformaciones; la fecha publicada por la fuente y el momento de descarga se presentan por separado.": "; this attribution does not extend to other portal APIs. Aggregations and transformations have been applied; the source's publication date and download time are shown separately.",
    "Cargando…": "Loading…",
    "No disponible": "Not available",
    "Actualización reciente": "Recently updated",
    "Fuente posiblemente antigua": "Source may be outdated",
    "Frescura no verificable": "Freshness cannot be verified",
    "Datos no disponibles": "Data unavailable",
    "No hay fechas válidas disponibles para mostrar.": "No valid dates are available to display.",
    "No se puede dibujar la serie con las fechas disponibles.": "The series cannot be plotted with the available dates.",
    "No disponible: el campo de órgano no está observado.": "Unavailable: no contracting-authority field was observed.",
    "Ranking no disponible: el campo de órgano no está observado.": "Ranking unavailable: no contracting-authority field was observed.",
    "Ranking agregado de hasta diez órganos de contratación por número de anuncios.": "Aggregated ranking of up to ten contracting authorities by number of notices.",
    "Anuncios por fecha de publicación para todos los órganos.": "Notices by publication date for all authorities.",
    "Anuncios por fecha de publicación para": "Notices by publication date for",
    "todos los órganos": "all authorities",
    "Notices by publication date for": "Notices by publication date for",
    "Mostrando": "Showing",
    "fecha(s) con publicación válida para": "valid publication date(s) for",
    "anuncios": "notices",
    "Filtrado por": "Filtered by",
    "No se pudo cargar el resumen local. Comprueba que el sitio se sirve por HTTP y que existe data/radar-summary.json.": "Could not load the local summary. Make sure the site is served over HTTP and data/radar-summary.json exists.",
    "Panel de indicadores de contratación pública · Proyecto de datos de Rafael Castillo": "Public Procurement Indicators · A data project by Rafael Castillo",
    "Ver proyectos ↑": "View projects ↑"
  };
  const attributeTranslations = {
    "Panel de indicadores de contratación pública de Euskadi, con métricas agregadas de publicaciones, órganos de contratación y calidad de datos.": "Euskadi public procurement indicators based on aggregated publication, contracting-authority, and data-quality metrics.",
    "Navegación principal": "Main navigation",
    "Rafael Castillo, currículum": "Rafael Castillo, résumé",
    "Secciones del panel": "Dashboard sections",
    "Procedencia de esta instantánea": "Snapshot provenance",
    "Indicadores principales": "Key indicators",
    "Gráfico de líneas con recuento agregado por fecha de publicación.": "Line chart of aggregated counts by publication date.",
    "Gráfico de barras con recuento agregado por órgano de contratación.": "Bar chart of aggregated counts by contracting authority.",
    "Volver al currículum": "Back to résumé"
  };

  function normalize(value) {
    return value.replace(/\s+/gu, " ").trim();
  }

  function translateStatic(language) {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      node.__languageSource ??= node.nodeValue;
      const source = normalize(node.__languageSource);
      const translated = translations[source];
      const leading = node.__languageSource.match(/^\s*/u)[0];
      const trailing = node.__languageSource.match(/\s*$/u)[0];
      node.nodeValue = language === "en" && translated
        ? `${leading}${translated}${trailing}`
        : node.__languageSource;
    }
    for (const element of document.querySelectorAll("[alt], [aria-label], [title], meta[name='description']")) {
      for (const attribute of ["alt", "aria-label", "title", "content"]) {
        const current = element.getAttribute(attribute);
        if (!current) continue;
        element.__languageAttributes ??= {};
        element.__languageAttributes[attribute] ??= current;
        const source = element.__languageAttributes[attribute];
        const value = language === "en" ? attributeTranslations[source] || translations[source] || source : source;
        element.setAttribute(attribute, value);
      }
    }
    document.title = language === "en"
      ? translations["Panel de indicadores de contratación pública | Rafael Castillo"]
      : "Panel de indicadores de contratación pública | Rafael Castillo";
  }

  function setLanguage(language, persist) {
    currentLanguage = language === "en" ? "en" : "es";
    document.documentElement.lang = currentLanguage;
    translateStatic(currentLanguage);
    for (const button of document.querySelectorAll("[data-language-toggle]")) {
      const target = currentLanguage === "en" ? "es" : "en";
      button.textContent = target.toUpperCase();
      button.lang = currentLanguage;
      button.setAttribute("aria-label", currentLanguage === "en" ? "Switch to Spanish" : "Cambiar a inglés");
      button.title = currentLanguage === "en" ? "Switch to Spanish" : "Cambiar a inglés";
    }
    if (persist) {
      try {
        localStorage.setItem(STORAGE_KEY, currentLanguage);
      } catch (error) {
        console.warn("The language preference could not be saved.", error);
      }
    }
    window.dispatchEvent(new CustomEvent("site-language-change", { detail: { language: currentLanguage } }));
  }

  let currentLanguage = "es";
  window.siteLanguage = {
    get current() {
      return currentLanguage;
    },
    translate(value) {
      return currentLanguage === "en" ? translations[value] || value : value;
    }
  };

  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    currentLanguage = saved === "es" || saved === "en"
      ? saved
      : navigator.language.toLowerCase().startsWith("en") ? "en" : "es";
  } catch (error) {
    console.warn("The saved language preference could not be read.", error);
    currentLanguage = navigator.language.toLowerCase().startsWith("en") ? "en" : "es";
  }
  setLanguage(currentLanguage, false);

  for (const button of document.querySelectorAll("[data-language-toggle]")) {
    button.addEventListener("click", () => {
      setLanguage(currentLanguage === "en" ? "es" : "en", true);
    });
  }
})();
