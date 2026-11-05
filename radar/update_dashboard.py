"""Prepare and safely publish validated aggregate dashboard data."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from radar.build_dashboard_data import (
    DEADLINE_FIELD,
    DEADLINE_FORMAT,
    DEADLINE_PATTERN,
    DEFAULT_OUTPUT_PATH,
    ORGANIZATION_FIELD,
    PUBLICATION_DATE_FIELD,
    PUBLICATION_DATE_FORMAT,
    PUBLICATION_DATE_PATTERN,
    DashboardDataError,
    _non_empty,
    _parse_catalog_date,
    build_dashboard_data,
    latest_valid_capture,
)
from radar.catalog_source import (
    CATALOG_JSON_URL,
    DATASET_URL,
    LICENSE_URL,
    STALE_AFTER_DAYS,
    CatalogIngestionError,
    ingest_catalog,
)

DEFAULT_WORK_DIRECTORY = Path(".radar-work")
REQUIRED_SUMMARY_FIELDS = {
    "schema_version",
    "generated_at_utc",
    "source",
    "summary",
    "field_completeness",
    "date_quality",
    "activity_by_date",
    "top_organizations",
    "activity_by_organization",
    "methodology",
}
SOURCE_FIELDS = {
    "dataset_url",
    "source_url",
    "source_updated_at",
    "downloaded_at_utc",
    "snapshot_sha256",
    "freshness_status",
    "record_count",
}
SUMMARY_FIELDS = {
    "notice_count",
    "distinct_organizations",
    "distinct_publication_dates",
    "deadlines_before_source_update_day",
}
FIELD_COMPLETENESS_FIELDS = {
    "observed_field",
    "available",
    "total_records",
    "non_empty_records",
    "missing_or_empty_records",
    "completeness_percent",
}
DATE_QUALITY_FIELDS = {
    "publication_invalid_count",
    "publication_empty_count",
    "deadline_invalid_count",
    "deadline_empty_count",
    "deadline_review_available",
}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class DashboardUpdateError(Exception):
    """Raised when a new summary cannot be safely prepared or published."""


@dataclass(frozen=True)
class PreparedDashboard:
    record_count: int
    source_updated_at: str
    snapshot_sha256: str
    warnings: tuple[str, ...]


def _validate_catalog(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    checked_at: datetime,
) -> tuple[str, list[str]]:
    if not records:
        raise DashboardUpdateError(
            "La captura no contiene registros; se conserva el resumen publicado."
        )
    if manifest.get("source_url") != CATALOG_JSON_URL:
        raise DashboardUpdateError("La captura no corresponde al catálogo esperado.")
    if manifest.get("dataset_url") != DATASET_URL:
        raise DashboardUpdateError("La ficha de la captura no es la esperada.")
    if manifest.get("license_url") != LICENSE_URL:
        raise DashboardUpdateError(
            "La captura no contiene la referencia de licencia de la ficha."
        )

    raw_source_date = manifest.get("source_updated_at")
    if not isinstance(raw_source_date, str):
        raise DashboardUpdateError(
            "Faltan los metadatos de actualización publicados por la fuente."
        )
    try:
        source_date = date.fromisoformat(raw_source_date)
    except ValueError as error:
        raise DashboardUpdateError(
            "La fecha de actualización de la fuente no es válida."
        ) from error
    if source_date.isoformat() != raw_source_date:
        raise DashboardUpdateError(
            "La fecha de actualización de la fuente no usa formato ISO."
        )
    if source_date > checked_at.date():
        raise DashboardUpdateError(
            "La fecha de actualización de la fuente está en el futuro."
        )
    age_days = (checked_at.date() - source_date).days
    if age_days > STALE_AFTER_DAYS:
        raise DashboardUpdateError(
            "La fuente supera la política de frescura: máximo "
            f"{STALE_AFTER_DAYS} días desde su fecha de actualización publicada."
        )
    if manifest.get("freshness_status") != "reciente":
        raise DashboardUpdateError(
            "Los metadatos no confirman una actualización reciente de la fuente."
        )

    required_fields = (
        PUBLICATION_DATE_FIELD,
        ORGANIZATION_FIELD,
        DEADLINE_FIELD,
    )
    missing_fields = [
        field for field in required_fields
        if not any(field in record for record in records)
    ]
    if missing_fields:
        raise DashboardUpdateError(
            "Faltan campos necesarios para el dashboard: "
            + ", ".join(missing_fields)
        )

    valid_publication_dates = 0
    valid_deadline_dates = 0
    warnings: list[str] = []
    for field, pattern, date_format in (
        (PUBLICATION_DATE_FIELD, PUBLICATION_DATE_PATTERN, PUBLICATION_DATE_FORMAT),
        (DEADLINE_FIELD, DEADLINE_PATTERN, DEADLINE_FORMAT),
    ):
        empty_count = 0
        invalid_count = 0
        for record in records:
            value = record.get(field)
            if not _non_empty(value):
                empty_count += 1
                continue
            parsed = _parse_catalog_date(value, pattern, date_format)
            if parsed is None:
                invalid_count += 1
            elif field == PUBLICATION_DATE_FIELD:
                valid_publication_dates += 1
            else:
                valid_deadline_dates += 1
        if invalid_count:
            raise DashboardUpdateError(
                f"El campo {field} contiene {invalid_count} valor(es) no vacío(s) "
                "con un tipo o formato no reconocido; no se publicará un "
                "resumen parcial."
            )
        if empty_count:
            warnings.append(
                f"{empty_count} registro(s) no tienen valor para {field}; "
                "se reflejarán en las métricas de completitud."
            )
    if valid_publication_dates == 0:
        raise DashboardUpdateError(
            "No hay fechas de publicación válidas para generar la serie del dashboard."
        )
    if valid_deadline_dates == 0:
        raise DashboardUpdateError(
            "No hay fechas límite válidas para evaluar el indicador del dashboard."
        )

    organizations = sum(
        isinstance(record.get(ORGANIZATION_FIELD), str)
        and bool(record[ORGANIZATION_FIELD].strip())
        for record in records
    )
    if organizations == 0:
        raise DashboardUpdateError(
            "No hay órganos de contratación utilizables en la captura."
        )
    if organizations < len(records):
        warnings.append(
            f"{len(records) - organizations} registro(s) no tienen órgano "
            "de contratación utilizable."
        )

    return source_date.isoformat(), warnings


def _parse_aware_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise DashboardUpdateError(f"El resumen no contiene {field} válido.")
    try:
        parsed = datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError as error:
        raise DashboardUpdateError(f"El resumen no contiene {field} válido.") from error
    if parsed.tzinfo is None:
        raise DashboardUpdateError(f"El resumen no contiene zona horaria en {field}.")
    return parsed


def _require_exact_keys(value: object, expected: set[str], context: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise DashboardUpdateError(
            f"La estructura de {context} no coincide con el esquema público esperado."
        )
    return value


def validate_public_summary(data: object) -> dict[str, Any]:
    """Reject incomplete or non-aggregate output before it can enter the site."""
    summary = _require_exact_keys(data, REQUIRED_SUMMARY_FIELDS, "la raíz")
    if (
        isinstance(summary["schema_version"], bool)
        or not isinstance(summary["schema_version"], int)
        or summary["schema_version"] != 1
    ):
        raise DashboardUpdateError("Versión de esquema público no compatible.")
    _parse_aware_timestamp(summary["generated_at_utc"], "generated_at_utc")

    source = _require_exact_keys(summary["source"], SOURCE_FIELDS, "source")
    if source["dataset_url"] != DATASET_URL or source["source_url"] != CATALOG_JSON_URL:
        raise DashboardUpdateError("La atribución del resumen no corresponde a la fuente.")
    if not isinstance(source["source_updated_at"], str):
        raise DashboardUpdateError("El resumen no contiene fecha de actualización de fuente.")
    try:
        source_date = date.fromisoformat(source["source_updated_at"])
    except ValueError as error:
        raise DashboardUpdateError("Fecha de actualización de fuente no válida.") from error
    if source_date.isoformat() != source["source_updated_at"]:
        raise DashboardUpdateError("Fecha de actualización de fuente no válida.")
    if source["freshness_status"] != "reciente":
        raise DashboardUpdateError("El resumen no confirma que la fuente esté reciente.")
    if not isinstance(source["snapshot_sha256"], str) or not SHA256_PATTERN.fullmatch(
        source["snapshot_sha256"]
    ):
        raise DashboardUpdateError("El resumen no contiene un hash de captura válido.")
    if isinstance(source["record_count"], bool) or not isinstance(
        source["record_count"], int
    ) or source["record_count"] <= 0:
        raise DashboardUpdateError("El resumen no contiene un recuento válido.")
    _parse_aware_timestamp(source["downloaded_at_utc"], "downloaded_at_utc")

    metrics = _require_exact_keys(summary["summary"], SUMMARY_FIELDS, "summary")
    if (
        isinstance(metrics["notice_count"], bool)
        or not isinstance(metrics["notice_count"], int)
        or metrics["notice_count"] != source["record_count"]
    ):
        raise DashboardUpdateError("El total agregado no coincide con la captura.")
    for key in ("distinct_organizations", "distinct_publication_dates",
                "deadlines_before_source_update_day"):
        value = metrics[key]
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise DashboardUpdateError(f"El indicador {key} no es válido.")

    completeness = _require_exact_keys(
        summary["field_completeness"],
        {PUBLICATION_DATE_FIELD, ORGANIZATION_FIELD, DEADLINE_FIELD},
        "field_completeness",
    )
    for field, value in completeness.items():
        metric = _require_exact_keys(
            value, FIELD_COMPLETENESS_FIELDS, f"field_completeness.{field}"
        )
        if metric["observed_field"] != field:
            raise DashboardUpdateError("El campo de completitud no coincide.")
        if metric["total_records"] != source["record_count"]:
            raise DashboardUpdateError("La completitud no coincide con el total de registros.")
        for key in ("non_empty_records", "missing_or_empty_records"):
            count = metric[key]
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise DashboardUpdateError(f"El recuento de {field} no es válido.")
        if metric["non_empty_records"] + metric["missing_or_empty_records"] != source[
            "record_count"
        ]:
            raise DashboardUpdateError(f"La completitud de {field} no es consistente.")
        if not isinstance(metric["available"], bool):
            raise DashboardUpdateError(f"La disponibilidad de {field} no es válida.")
        percent = metric["completeness_percent"]
        if percent is not None and (
            isinstance(percent, bool)
            or not isinstance(percent, (int, float))
            or not 0 <= percent <= 100
        ):
            raise DashboardUpdateError(f"El porcentaje de {field} no es válido.")
        expected_percent = round(
            metric["non_empty_records"] * 100 / source["record_count"], 1
        )
        if percent != expected_percent:
            raise DashboardUpdateError(f"El porcentaje de {field} no coincide.")

    date_quality = _require_exact_keys(
        summary["date_quality"], DATE_QUALITY_FIELDS, "date_quality"
    )
    for key in (
        "publication_invalid_count",
        "publication_empty_count",
        "deadline_invalid_count",
        "deadline_empty_count",
    ):
        count = date_quality[key]
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise DashboardUpdateError(f"El indicador {key} no es válido.")
    if not isinstance(date_quality["deadline_review_available"], bool):
        raise DashboardUpdateError("La disponibilidad de revisión de plazos no es válida.")

    activity = summary["activity_by_date"]
    if not isinstance(activity, list):
        raise DashboardUpdateError("activity_by_date debe ser una lista.")
    for row in activity:
        item = _require_exact_keys(row, {"date", "notice_count"}, "activity_by_date")
        try:
            day = date.fromisoformat(item["date"])
        except (TypeError, ValueError) as error:
            raise DashboardUpdateError("La serie contiene una fecha no válida.") from error
        if day.isoformat() != item["date"]:
            raise DashboardUpdateError("La serie contiene una fecha no válida.")
        if isinstance(item["notice_count"], bool) or not isinstance(
            item["notice_count"], int
        ) or item["notice_count"] <= 0:
            raise DashboardUpdateError("La serie contiene un recuento no válido.")
    if metrics["distinct_publication_dates"] != len(activity):
        raise DashboardUpdateError("El número de fechas no coincide con la serie.")
    if sum(row["notice_count"] for row in activity) > source["record_count"]:
        raise DashboardUpdateError("La serie supera el número de registros.")

    ranking = summary["top_organizations"]
    if not isinstance(ranking, list):
        raise DashboardUpdateError("top_organizations debe ser una lista.")
    for row in ranking:
        item = _require_exact_keys(row, {"organization", "notice_count"}, "top_organizations")
        if not isinstance(item["organization"], str) or not item["organization"]:
            raise DashboardUpdateError("El ranking contiene un órgano no válido.")
        if isinstance(item["notice_count"], bool) or not isinstance(
            item["notice_count"], int
        ) or item["notice_count"] <= 0:
            raise DashboardUpdateError("El ranking contiene un recuento no válido.")

    by_organization = summary["activity_by_organization"]
    if not isinstance(by_organization, list):
        raise DashboardUpdateError("activity_by_organization debe ser una lista.")
    for row in by_organization:
        item = _require_exact_keys(
            row, {"organization", "notice_count", "activity_by_date"},
            "activity_by_organization",
        )
        if not isinstance(item["organization"], str) or not item["organization"]:
            raise DashboardUpdateError("La actividad contiene un órgano no válido.")
        if isinstance(item["notice_count"], bool) or not isinstance(
            item["notice_count"], int
        ) or item["notice_count"] <= 0:
            raise DashboardUpdateError("La actividad contiene un recuento no válido.")
        if not isinstance(item["activity_by_date"], list):
            raise DashboardUpdateError("La actividad por órgano debe ser una lista.")
        for activity_row in item["activity_by_date"]:
            activity_item = _require_exact_keys(
                activity_row, {"date", "notice_count"}, "activity_by_organization.date"
            )
            try:
                day = date.fromisoformat(activity_item["date"])
            except (TypeError, ValueError) as error:
                raise DashboardUpdateError(
                    "La actividad por órgano contiene una fecha no válida."
                ) from error
            if day.isoformat() != activity_item["date"]:
                raise DashboardUpdateError(
                    "La actividad por órgano contiene una fecha no válida."
                )
            count = activity_item["notice_count"]
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise DashboardUpdateError(
                    "La actividad por órgano contiene un recuento no válido."
                )
    if sum(row["notice_count"] for row in by_organization) != completeness[
        ORGANIZATION_FIELD
    ]["non_empty_records"]:
        raise DashboardUpdateError(
            "La actividad por órgano no coincide con la completitud del campo."
        )
    methodology_fields = {
        "publication_date_field",
        "publication_date_format",
        "organization_field",
        "deadline_field",
        "deadline_format",
        "deadline_review_rule",
        "last_publication_date_is_not_used",
        "aggregation_only",
    }
    methodology = _require_exact_keys(
        summary["methodology"], methodology_fields, "methodology"
    )
    if methodology["aggregation_only"] is not True:
        raise DashboardUpdateError("El resumen no declara que contiene solo agregados.")
    return summary


def prepare_dashboard_update(
    input_root: Path,
    staged_output: Path,
    *,
    current_output: Path = DEFAULT_OUTPUT_PATH,
    generated_at: datetime | None = None,
) -> PreparedDashboard:
    """Build and validate a staging JSON without touching the published file."""
    checked_at = generated_at or datetime.now(timezone.utc)
    if checked_at.tzinfo is None:
        raise DashboardUpdateError("generated_at debe incluir zona horaria.")
    checked_at = checked_at.astimezone(timezone.utc)

    try:
        manifest, records = latest_valid_capture(input_root)
    except DashboardDataError as error:
        raise DashboardUpdateError(str(error)) from error
    source_updated_at, warnings = _validate_catalog(manifest, records, checked_at)

    try:
        data = build_dashboard_data(input_root, staged_output, checked_at)
    except DashboardDataError as error:
        raise DashboardUpdateError(str(error)) from error
    validate_public_summary(data)

    if current_output.is_file():
        try:
            current = json.loads(current_output.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            current = None
            warnings.append(
                "El resumen existente no se pudo interpretar; se sustituirá "
                "solo después de validar la nueva generación."
            )
        if isinstance(current, dict):
            source = current.get("source")
            previous_count = (
                source.get("record_count") if isinstance(source, dict) else None
            )
            if isinstance(previous_count, int) and not isinstance(previous_count, bool):
                if previous_count != len(records):
                    direction = "aumentó" if len(records) > previous_count else "disminuyó"
                    warnings.append(
                        f"El número de registros {direction} de {previous_count} "
                        f"a {len(records)}; revisar la variación de la ventana móvil."
                    )

    return PreparedDashboard(
        record_count=len(records),
        source_updated_at=source_updated_at,
        snapshot_sha256=str(manifest.get("sha256", "")),
        warnings=tuple(warnings),
    )


def publish_prepared_dashboard(staged_output: Path, output_path: Path) -> bool:
    """Atomically replace the public summary after revalidating its JSON."""
    try:
        staged_bytes = staged_output.read_bytes()
        data = json.loads(staged_bytes)
    except OSError as error:
        raise DashboardUpdateError(
            f"No se puede leer el resumen preparado: {staged_output}"
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise DashboardUpdateError("El resumen preparado no es JSON válido.") from error

    validated = validate_public_summary(data)
    if output_path.is_file():
        try:
            current = validate_public_summary(
                json.loads(output_path.read_text(encoding="utf-8"))
            )
        except (OSError, json.JSONDecodeError, DashboardUpdateError):
            current = None
        if current is not None and (
            current["source"]["snapshot_sha256"]
            == validated["source"]["snapshot_sha256"]
            and current["source"]["source_updated_at"]
            == validated["source"]["source_updated_at"]
        ):
            return False

    temporary_path: Path | None = None
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(staged_bytes)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output_path)
    except OSError as error:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise DashboardUpdateError(
            f"No se pudo instalar atómicamente el resumen en {output_path}."
        ) from error
    return True


def prepare_work_directory(
    work_directory: Path,
    current_output: Path = DEFAULT_OUTPUT_PATH,
) -> PreparedDashboard:
    try:
        work_directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise DashboardUpdateError(
            f"El directorio de trabajo ya existe: {work_directory}. "
            "No se sobrescribirán sus archivos."
        ) from error
    except OSError as error:
        raise DashboardUpdateError(
            f"No se pudo crear el directorio de trabajo: {work_directory}."
        ) from error

    captures = work_directory / "captures"
    staged_output = work_directory / "radar-summary.json"
    try:
        result = ingest_catalog(output_root=captures)
        preparation = prepare_dashboard_update(
            captures,
            staged_output,
            current_output=current_output,
        )
    except (CatalogIngestionError, DashboardUpdateError):
        raise

    print(
        f"Captura válida: {preparation.record_count} registro(s); "
        f"actualización de fuente {preparation.source_updated_at}."
    )
    for warning in result.warnings:
        print(f"Advertencia de ingesta [{warning['code']}]: {warning['message']}")
    for warning in preparation.warnings:
        print(f"Advertencia de publicación: {warning}")
    return preparation


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepara y publica de forma segura el resumen agregado del panel."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Descarga, valida y prepara un resumen fuera de public/.",
    )
    prepare_parser.add_argument(
        "--work-dir", type=Path, default=DEFAULT_WORK_DIRECTORY
    )
    publish_parser = subparsers.add_parser(
        "publish", help="Revalida e instala atómicamente el resumen preparado."
    )
    publish_parser.add_argument(
        "--work-dir", type=Path, default=DEFAULT_WORK_DIRECTORY
    )
    publish_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    try:
        if args.command == "prepare":
            prepare_work_directory(args.work_dir)
        else:
            changed = publish_prepared_dashboard(
                args.work_dir / "radar-summary.json", args.output
            )
            print(
                "Resumen público actualizado."
                if changed
                else "La captura y los metadatos no han cambiado; no se modifica el resumen."
            )
    except (CatalogIngestionError, DashboardUpdateError) as error:
        parser.exit(status=1, message=f"Error: {error}\n")


if __name__ == "__main__":
    main()
