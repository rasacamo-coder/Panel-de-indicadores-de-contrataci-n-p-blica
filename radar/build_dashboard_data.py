"""Build a public aggregate summary from the latest valid local catalog capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from radar.catalog_source import CATALOG_JSON_URL, DATASET_URL

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_ROOT = Path(__file__).resolve().parent / "data" / "raw" / "catalog"
DEFAULT_OUTPUT_PATH = REPOSITORY_ROOT / "public" / "data" / "radar-summary.json"

PUBLICATION_DATE_FIELD = "contratacion_fecha_de_publicacion_documento"
ORGANIZATION_FIELD = "contratacion_organo_contratacion"
DEADLINE_FIELD = "contratacion_fecha_limite_presentacion"
PUBLICATION_DATE_FORMAT = "%d/%m/%Y"
DEADLINE_FORMAT = "%d/%m/%Y %H:%M"
PUBLICATION_DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
DEADLINE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4} \d{2}:\d{2}$")


class DashboardDataError(Exception):
    """Raised when a local capture cannot be safely aggregated."""


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(manifest, dict):
        return None
    if manifest.get("extraction_status") not in {"valid_with_data", "valid_empty"}:
        return None
    if not isinstance(manifest.get("downloaded_at_utc"), str):
        return None
    return manifest


def latest_valid_capture(input_root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Load and verify the newest capture marked valid by its manifest."""
    candidates: list[tuple[str, Path, dict[str, Any]]] = []
    try:
        directories = list(input_root.iterdir())
    except OSError as error:
        raise DashboardDataError(
            f"No se puede leer el directorio de capturas: {input_root}"
        ) from error

    for directory in directories:
        if not directory.is_dir() or directory.name == "failures":
            continue
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = _read_manifest(manifest_path)
        if manifest is not None:
            candidates.append((manifest["downloaded_at_utc"], directory, manifest))

    if not candidates:
        raise DashboardDataError("No hay una captura válida local para agregar.")

    _, run_directory, manifest = max(
        candidates, key=lambda candidate: (candidate[0], candidate[1].name)
    )
    response_path = run_directory / "response.json"
    try:
        raw_response = response_path.read_bytes()
    except OSError as error:
        raise DashboardDataError(
            "La captura válida más reciente no contiene un response.json legible."
        ) from error

    if hashlib.sha256(raw_response).hexdigest() != manifest.get("sha256"):
        raise DashboardDataError(
            "El SHA-256 de la captura no coincide con su manifiesto."
        )

    try:
        records = json.loads(raw_response)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise DashboardDataError(
            "La captura válida más reciente no contiene JSON válido."
        ) from error
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise DashboardDataError(
            "La captura debe contener una lista de objetos JSON."
        )
    if manifest.get("record_count") != len(records):
        raise DashboardDataError(
            "El número de registros no coincide con el manifiesto."
        )
    return manifest, records


def _parse_catalog_date(
    value: object, pattern: re.Pattern[str], date_format: str
) -> date | datetime | None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        return None
    try:
        parsed = datetime.strptime(value, date_format)
    except ValueError:
        return None
    if parsed.strftime(date_format) != value:
        return None
    return parsed.date() if date_format == PUBLICATION_DATE_FORMAT else parsed


def _non_empty(value: object) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _completeness(records: list[dict[str, Any]], field: str) -> dict[str, Any]:
    if not records:
        non_empty_count = 0
    else:
        non_empty_count = sum(_non_empty(record.get(field)) for record in records)
    total = len(records)
    return {
        "observed_field": field,
        "available": any(field in record for record in records),
        "total_records": total,
        "non_empty_records": non_empty_count,
        "missing_or_empty_records": total - non_empty_count,
        "completeness_percent": (
            round(non_empty_count * 100 / total, 1) if total else None
        ),
    }


def aggregate_records(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Return aggregate-only dashboard data; never include individual records."""
    record_count = len(records)
    publication_available = any(
        PUBLICATION_DATE_FIELD in record for record in records
    )
    organization_available = any(ORGANIZATION_FIELD in record for record in records)
    deadline_available = any(DEADLINE_FIELD in record for record in records)

    publication_counts: Counter[date] = Counter()
    organization_counts: Counter[str] = Counter()
    organization_dates: dict[str, Counter[date]] = {}
    invalid_publication_count = 0
    empty_publication_count = 0
    invalid_deadline_count = 0
    empty_deadline_count = 0
    parsed_deadlines: list[datetime] = []

    for record in records:
        raw_publication = record.get(PUBLICATION_DATE_FIELD)
        if not _non_empty(raw_publication):
            empty_publication_count += 1
        else:
            parsed_publication = _parse_catalog_date(
                raw_publication, PUBLICATION_DATE_PATTERN, PUBLICATION_DATE_FORMAT
            )
            if isinstance(parsed_publication, date):
                publication_counts[parsed_publication] += 1
            else:
                invalid_publication_count += 1

        raw_organization = record.get(ORGANIZATION_FIELD)
        organization = raw_organization.strip() if isinstance(raw_organization, str) else ""
        if organization:
            organization_counts[organization] += 1
            organization_dates.setdefault(organization, Counter())
            parsed_publication = _parse_catalog_date(
                raw_publication, PUBLICATION_DATE_PATTERN, PUBLICATION_DATE_FORMAT
            )
            if isinstance(parsed_publication, date):
                organization_dates[organization][parsed_publication] += 1

        raw_deadline = record.get(DEADLINE_FIELD)
        if not _non_empty(raw_deadline):
            empty_deadline_count += 1
        else:
            parsed_deadline = _parse_catalog_date(
                raw_deadline, DEADLINE_PATTERN, DEADLINE_FORMAT
            )
            if isinstance(parsed_deadline, datetime):
                parsed_deadlines.append(parsed_deadline)
            else:
                invalid_deadline_count += 1

    source_updated_at: date | None = None
    raw_source_date = manifest.get("source_updated_at")
    if isinstance(raw_source_date, str):
        try:
            source_updated_at = date.fromisoformat(raw_source_date)
        except ValueError:
            source_updated_at = None

    deadline_review_count: int | None = None
    if deadline_available and source_updated_at is not None:
        deadline_review_count = sum(
            deadline.date() < source_updated_at for deadline in parsed_deadlines
        )

    ordered_organizations = sorted(
        organization_counts.items(), key=lambda item: (-item[1], item[0].casefold(), item[0])
    )
    top_organizations = (
        [
            {"organization": name, "notice_count": count}
            for name, count in ordered_organizations[:10]
        ]
        if organization_available
        else None
    )
    activity_by_organization = (
        [
            {
                "organization": name,
                "notice_count": organization_counts[name],
                "activity_by_date": [
                    {"date": day.isoformat(), "notice_count": count}
                    for day, count in sorted(organization_dates[name].items())
                ],
            }
            for name in sorted(organization_counts, key=lambda value: (value.casefold(), value))
        ]
        if organization_available
        else None
    )

    now = generated_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("generated_at debe incluir zona horaria.")
    now = now.astimezone(timezone.utc)

    return {
        "schema_version": 1,
        "generated_at_utc": now.isoformat(timespec="seconds"),
        "source": {
            "dataset_url": manifest.get("dataset_url", DATASET_URL),
            "source_url": manifest.get("source_url", CATALOG_JSON_URL),
            "source_updated_at": (
                source_updated_at.isoformat() if source_updated_at else None
            ),
            "downloaded_at_utc": manifest.get("downloaded_at_utc"),
            "snapshot_sha256": manifest.get("sha256"),
            "freshness_status": manifest.get("freshness_status", "no_verificable"),
            "record_count": record_count,
        },
        "summary": {
            "notice_count": record_count,
            "distinct_organizations": (
                len(organization_counts) if organization_available else None
            ),
            "distinct_publication_dates": (
                len(publication_counts) if publication_available else None
            ),
            "deadlines_before_source_update_day": deadline_review_count,
        },
        "field_completeness": {
            PUBLICATION_DATE_FIELD: _completeness(records, PUBLICATION_DATE_FIELD),
            ORGANIZATION_FIELD: _completeness(records, ORGANIZATION_FIELD),
            DEADLINE_FIELD: _completeness(records, DEADLINE_FIELD),
        },
        "date_quality": {
            "publication_invalid_count": invalid_publication_count,
            "publication_empty_count": empty_publication_count,
            "deadline_invalid_count": invalid_deadline_count,
            "deadline_empty_count": empty_deadline_count,
            "deadline_review_available": deadline_review_count is not None,
        },
        "activity_by_date": [
            {"date": day.isoformat(), "notice_count": publication_counts[day]}
            for day in sorted(publication_counts)
        ] if publication_available else None,
        "top_organizations": top_organizations,
        "activity_by_organization": activity_by_organization,
        "methodology": {
            "publication_date_field": PUBLICATION_DATE_FIELD,
            "publication_date_format": PUBLICATION_DATE_FORMAT,
            "organization_field": ORGANIZATION_FIELD,
            "deadline_field": DEADLINE_FIELD,
            "deadline_format": DEADLINE_FORMAT,
            "deadline_review_rule": (
                "Fecha límite anterior al día de actualización publicada por la fuente; "
                "caso para revisar, no error confirmado."
            ),
            "last_publication_date_is_not_used": True,
            "aggregation_only": True,
        },
    }


def build_dashboard_data(
    input_root: Path = DEFAULT_INPUT_ROOT,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Build and write an aggregate JSON file to the requested public path."""
    manifest, records = latest_valid_capture(input_root)
    summary = aggregate_records(manifest, records, generated_at)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise DashboardDataError(
            f"No se pudo escribir el resumen agregado: {output_path}"
        ) from error
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera datos agregados del panel desde la última captura local válida."
    )
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()
    try:
        summary = build_dashboard_data(args.input_dir, args.output)
    except DashboardDataError as error:
        parser.exit(status=1, message=f"Error: {error}\n")
    print(
        f"Resumen generado: {summary['summary']['notice_count']} avisos; "
        f"salida: {args.output}"
    )


if __name__ == "__main__":
    main()
