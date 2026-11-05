(() => {
  "use strict";

  const SUMMARY_URL = "data/radar-summary.json";
  const DATE_FORMATTER = new Intl.DateTimeFormat("es-ES", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC"
  });
  const NUMBER_FORMATTER = new Intl.NumberFormat("es-ES");
  const SVG_NS = "http://www.w3.org/2000/svg";

  const elements = {
    loadStatus: document.getElementById("load-status"),
    freshness: document.getElementById("freshness-badge"),
    sourceUpdated: document.getElementById("source-updated"),
    downloaded: document.getElementById("downloaded-at"),
    generated: document.getElementById("generated-at"),
    notices: document.getElementById("kpi-notices"),
    organizations: document.getElementById("kpi-organizations"),
    publicationDays: document.getElementById("kpi-publication-days"),
    deadlines: document.getElementById("kpi-deadlines"),
    filter: document.getElementById("organization-filter"),
    activityChart: document.getElementById("activity-chart"),
    activityDescription: document.getElementById("activity-chart-description"),
    activityCaption: document.getElementById("activity-caption"),
    activityTable: document.getElementById("activity-table"),
    organizationChart: document.getElementById("organization-chart"),
    organizationDescription: document.getElementById("organization-chart-description"),
    organizationTable: document.getElementById("organization-table"),
    completenessTable: document.getElementById("completeness-table"),
    invalidPublication: document.getElementById("invalid-publication"),
    emptyPublication: document.getElementById("empty-publication"),
    invalidDeadline: document.getElementById("invalid-deadline"),
    emptyDeadline: document.getElementById("empty-deadline"),
    datasetLink: document.getElementById("dataset-link")
  };

  function formatCount(value) {
    return value === null || value === undefined ? "No disponible" : NUMBER_FORMATTER.format(value);
  }

  function formatDate(value) {
    if (!value) return "No disponible";
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? "No disponible" : DATE_FORMATTER.format(parsed);
  }

  function formatTimestamp(value) {
    if (!value) return "No disponible";
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return "No disponible";
    return `${DATE_FORMATTER.format(parsed)} · ${new Intl.DateTimeFormat("es-ES", {
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "UTC",
      timeZoneName: "short"
    }).format(parsed)}`;
  }

  function svgElement(name, attributes = {}, text = "") {
    const node = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
    if (text) node.textContent = text;
    return node;
  }

  function resetChart(svg, titleId, descriptionId, description) {
    const title = document.getElementById(titleId);
    const desc = document.getElementById(descriptionId);
    svg.replaceChildren(title, desc);
    desc.textContent = description;
  }

  function appendEmptyChart(svg, message) {
    svg.append(svgElement("text", {
      x: "480", y: "170", "text-anchor": "middle", class: "empty-chart"
    }, message));
  }

  function renderActivityChart(rows, selectedOrganization) {
    const svg = elements.activityChart;
    const label = selectedOrganization || "todos los órganos";
    resetChart(
      svg,
      "activity-chart-title",
      "activity-chart-description",
      `Anuncios por fecha de publicación para ${label}.`
    );
    elements.activityTable.replaceChildren();

    if (!Array.isArray(rows) || rows.length === 0) {
      appendEmptyChart(svg, "No hay fechas válidas disponibles para mostrar.");
      elements.activityCaption.textContent = "No se puede dibujar la serie con las fechas disponibles.";
      return;
    }

    const width = 900;
    const height = 265;
    const left = 58;
    const right = 18;
    const top = 18;
    const bottom = 49;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const maxCount = Math.max(1, ...rows.map((row) => row.notice_count));
    const gridSteps = 4;

    for (let step = 0; step <= gridSteps; step += 1) {
      const y = top + (plotHeight * step) / gridSteps;
      const value = Math.round(maxCount * (gridSteps - step) / gridSteps);
      svg.append(svgElement("line", {
        x1: String(left), y1: String(y), x2: String(width - right), y2: String(y), class: "chart-grid"
      }));
      svg.append(svgElement("text", {
        x: String(left - 10), y: String(y + 4), "text-anchor": "end"
      }, NUMBER_FORMATTER.format(value)));
    }

    const points = rows.map((row, index) => {
      const x = rows.length === 1
        ? left + plotWidth / 2
        : left + (plotWidth * index) / (rows.length - 1);
      const y = top + plotHeight - (row.notice_count / maxCount) * plotHeight;
      return { x, y, row };
    });
    const path = points.map((point, index) =>
      `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
    ).join(" ");
    svg.append(svgElement("path", { d: path, class: "chart-line" }));

    const labelStep = Math.max(1, Math.ceil(rows.length / 8));
    points.forEach((point, index) => {
      const dateLabel = formatDate(point.row.date);
      const circle = svgElement("circle", {
        cx: String(point.x),
        cy: String(point.y),
        r: "4.5",
        class: "chart-point"
      });
      circle.append(svgElement("title", {}, `${dateLabel}: ${formatCount(point.row.notice_count)} anuncios`));
      svg.append(circle);
      if (index % labelStep === 0 || index === points.length - 1) {
        svg.append(svgElement("text", {
          x: String(point.x),
          y: String(height - 17),
          "text-anchor": index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"
        }, dateLabel));
      }
      const row = document.createElement("tr");
      const dateCell = document.createElement("td");
      const countCell = document.createElement("td");
      dateCell.textContent = dateLabel;
      countCell.textContent = formatCount(point.row.notice_count);
      row.append(dateCell, countCell);
      elements.activityTable.append(row);
    });

    elements.activityCaption.textContent =
      `Mostrando ${rows.length} fecha(s) con publicación válida para ${label}.`;
  }

  function renderOrganizationChart(ranking) {
    const svg = elements.organizationChart;
    resetChart(
      svg,
      "organization-chart-title",
      "organization-chart-description",
      "Ranking agregado de hasta diez órganos de contratación por número de anuncios."
    );
    elements.organizationTable.replaceChildren();
    if (!Array.isArray(ranking) || ranking.length === 0) {
      appendEmptyChart(svg, "Ranking no disponible: el campo de órgano no está observado.");
      return;
    }

    const width = 900;
    const left = 300;
    const right = 45;
    const rowHeight = 37;
    const top = 18;
    const maxCount = Math.max(1, ...ranking.map((row) => row.notice_count));
    ranking.forEach((item, index) => {
      const y = top + index * rowHeight;
      const barWidth = ((width - left - right) * item.notice_count) / maxCount;
      const label = item.organization.length > 39
        ? `${item.organization.slice(0, 36)}…`
        : item.organization;
      const labelNode = svgElement("text", {
        x: String(left - 12), y: String(y + 18), "text-anchor": "end"
      }, label);
      labelNode.append(svgElement("title", {}, item.organization));
      svg.append(labelNode);
      svg.append(svgElement("rect", {
        x: String(left), y: String(y + 3), width: String(Math.max(1, barWidth)),
        height: "22", rx: "2", class: "chart-bar"
      }));
      svg.append(svgElement("text", {
        x: String(Math.min(width - 5, left + barWidth + 9)),
        y: String(y + 19),
        class: "chart-value"
      }, formatCount(item.notice_count)));

      const row = document.createElement("tr");
      for (const value of [String(index + 1), item.organization, formatCount(item.notice_count)]) {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      }
      elements.organizationTable.append(row);
    });
  }

  function renderCompleteness(metrics) {
    const labels = [
      ["contratacion_fecha_de_publicacion_documento", "Fecha de publicación"],
      ["contratacion_organo_contratacion", "Órgano de contratación"],
      ["contratacion_fecha_limite_presentacion", "Fecha límite de presentación"]
    ];
    elements.completenessTable.replaceChildren();
    labels.forEach(([field, label]) => {
      const metric = metrics[field];
      const row = document.createElement("tr");
      const values = metric
        ? [
            label,
            `${formatCount(metric.non_empty_records)} / ${formatCount(metric.total_records)}`,
            formatCount(metric.missing_or_empty_records),
            metric.available ? `${NUMBER_FORMATTER.format(metric.completeness_percent)} %` : "No disponible"
          ]
        : [label, "No disponible", "No disponible", "No disponible"];
      values.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value;
        row.append(cell);
      });
      elements.completenessTable.append(row);
    });
  }

  function renderActivityFilter(data) {
    const organizations = data.activity_by_organization;
    elements.filter.replaceChildren(new Option("Todos los órganos", ""));
    if (!Array.isArray(organizations)) {
      elements.filter.disabled = true;
      return;
    }
    organizations.forEach((entry) => {
      elements.filter.add(new Option(`${entry.organization} (${formatCount(entry.notice_count)})`, entry.organization));
    });
    elements.filter.disabled = false;
  }

  function activityForSelection(data, selectedOrganization) {
    if (!selectedOrganization) return data.activity_by_date;
    const organization = data.activity_by_organization?.find(
      (entry) => entry.organization === selectedOrganization
    );
    return organization ? organization.activity_by_date : [];
  }

  function showData(data) {
    elements.loadStatus.textContent = "";
    elements.loadStatus.removeAttribute("data-error");
    elements.notices.textContent = formatCount(data.summary.notice_count);
    elements.organizations.textContent = formatCount(data.summary.distinct_organizations);
    elements.publicationDays.textContent = formatCount(data.summary.distinct_publication_dates);
    elements.deadlines.textContent = formatCount(data.summary.deadlines_before_source_update_day);
    elements.sourceUpdated.textContent = formatDate(data.source.source_updated_at);
    elements.downloaded.textContent = formatTimestamp(data.source.downloaded_at_utc);
    elements.generated.textContent = formatTimestamp(data.generated_at_utc);

    const freshness = data.source.freshness_status || "no_verificable";
    const freshnessLabels = {
      reciente: "Actualización reciente",
      antiguo: "Fuente posiblemente antigua",
      no_verificable: "Frescura no verificable"
    };
    elements.freshness.textContent = freshnessLabels[freshness] || freshnessLabels.no_verificable;
    elements.freshness.dataset.state = freshness;
    if (data.source.dataset_url) elements.datasetLink.href = data.source.dataset_url;

    elements.invalidPublication.textContent = formatCount(data.date_quality.publication_invalid_count);
    elements.emptyPublication.textContent = formatCount(data.date_quality.publication_empty_count);
    elements.invalidDeadline.textContent = formatCount(data.date_quality.deadline_invalid_count);
    elements.emptyDeadline.textContent = formatCount(data.date_quality.deadline_empty_count);
    renderCompleteness(data.field_completeness || {});
    renderOrganizationChart(data.top_organizations);
    renderActivityFilter(data);
    renderActivityChart(activityForSelection(data, ""), "");
    elements.filter.addEventListener("change", () => {
      renderActivityChart(
        activityForSelection(data, elements.filter.value),
        elements.filter.value
      );
    });
  }

  async function loadSummary() {
    try {
      const response = await fetch(SUMMARY_URL, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (data.schema_version !== 1 || !data.summary || !data.source) {
        throw new Error("Formato de resumen no compatible");
      }
      showData(data);
    } catch (error) {
      elements.loadStatus.dataset.error = "true";
      elements.loadStatus.textContent =
        "No se pudo cargar el resumen local. Comprueba que el sitio se sirve por HTTP y que existe data/radar-summary.json.";
      elements.freshness.textContent = "Datos no disponibles";
      elements.freshness.dataset.state = "no_verificable";
    }
  }

  loadSummary();
})();
