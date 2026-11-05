"""Ingesta local del JSON de contrataciones administrativas recientes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

CATALOG_JSON_URL = (
    "https://opendata.euskadi.eus/contenidos/ds_contrataciones/"
    "ultimas_contrataciones_admin/opendata/contratos.json"
)
CATALOG_RDF_URL = (
    "https://opendata.euskadi.eus/contenidos/ds_contrataciones/"
    "ultimas_contrataciones_admin/es_contracc/r01DCATDataset.rdf"
)
DATASET_URL = (
    "https://opendata.euskadi.eus/catalogo/-/"
    "contrataciones-administrativas-de-los-ultimos-dias/"
)
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
DEFAULT_TIMEOUT_SECONDS = 30
STALE_AFTER_DAYS = 3
DEFAULT_OUTPUT_ROOT = Path(__file__).resolve().parent / "data" / "raw" / "catalog"


class CatalogIngestionError(Exception):
    """Error legible durante descarga, validación o almacenamiento."""


@dataclass(frozen=True)
class CatalogResult:
    """Resultado satisfactorio de una ingesta del catálogo."""

    output_dir: Path
    status: str
    record_count: int
    snapshot_sha256: str
    source_updated_at: str | None
    freshness_status: str
    warnings: tuple[dict[str, str], ...]


def _read_url(
    url: str,
    opener: Callable[..., Any],
    timeout: int,
) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "Accept": "application/json, application/rdf+xml, application/xml",
            "User-Agent": "panel-indicadores-contratacion-euskadi/0.1.0",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            return response.read(), response.headers.get("Content-Type", "")
    except HTTPError as error:
        raise CatalogIngestionError(
            f"La fuente respondió con un error HTTP ({error.code})."
        ) from error
    except (TimeoutError, socket.timeout) as error:
        raise CatalogIngestionError(
            "La conexión con la fuente agotó el tiempo de espera."
        ) from error
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise CatalogIngestionError(
                "La conexión con la fuente agotó el tiempo de espera."
            ) from error
        raise CatalogIngestionError(
            "No se pudo conectar con la fuente de contrataciones."
        ) from error
    except (HTTPException, OSError) as error:
        raise CatalogIngestionError(
            "No se pudo leer la respuesta de la fuente de contrataciones."
        ) from error


def _json_media_type_is_valid(content_type: str) -> bool:
    media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
    return not media_type or media_type == "application/json" or media_type.endswith(
        "+json"
    )


def _json_type(value: object) -> str:
    if value is None:
        return "null"
    if type(value) is bool:
        return "boolean"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "unknown"


def _observe_fields(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    observed: dict[str, dict[str, Any]] = {}
    for record in records:
        for field, value in record.items():
            field_observation = observed.setdefault(
                field, {"present_records": 0, "types": Counter()}
            )
            field_observation["present_records"] += 1
            field_observation["types"][_json_type(value)] += 1

    return {
        field: {
            "present_records": data["present_records"],
            "types": dict(sorted(data["types"].items())),
        }
        for field, data in sorted(observed.items())
    }


def _parse_metadata_date(value: str) -> date:
    candidate = value.strip()
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        pass

    try:
        parsed_datetime = datetime.fromisoformat(
            candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate
        )
    except ValueError as error:
        raise ValueError("El metadato de actualización no es una fecha válida.") from error
    return parsed_datetime.date()


def _source_updated_at(rdf_body: bytes) -> date:
    try:
        root = ET.fromstring(rdf_body)
    except ET.ParseError as error:
        raise ValueError("El RDF de metadatos no es XML válido.") from error

    for element in root.iter():
        if element.tag.rsplit("}", maxsplit=1)[-1] == "modified":
            if element.text and element.text.strip():
                return _parse_metadata_date(element.text)
    raise ValueError("El RDF no contiene una fecha de actualización.")


def _previous_valid_manifests(output_root: Path) -> list[dict[str, Any]]:
    if not output_root.exists():
        return []

    candidates: list[tuple[str, dict[str, Any]]] = []
    try:
        directories = list(output_root.iterdir())
    except OSError as error:
        raise CatalogIngestionError(
            "No se pudieron revisar las ejecuciones anteriores."
        ) from error

    for directory in directories:
        if not directory.is_dir() or directory.name == "failures":
            continue
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CatalogIngestionError(
                "No se pudo leer el manifiesto de una ejecución anterior."
            ) from error
        if manifest.get("extraction_status") in {
            "valid_with_data",
            "valid_empty",
        }:
            candidates.append((str(manifest.get("downloaded_at_utc", "")), manifest))

    return [
        manifest
        for _, manifest in sorted(candidates, key=lambda candidate: candidate[0])
    ]


def _compare_schema(
    current: dict[str, dict[str, Any]],
    previous: dict[str, dict[str, Any]] | None,
    record_count: int,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if record_count > 0:
        for field, observation in current.items():
            if observation["present_records"] != record_count:
                warnings.append(
                    {
                        "code": "field_presence_varies",
                        "field": field,
                        "message": (
                            "El campo no aparece en todos los registros de "
                            "esta instantánea."
                        ),
                    }
                )

    if previous is None:
        return warnings
    previous_schema = previous.get("observed_fields", {})
    for field in sorted(current.keys() - previous_schema.keys()):
        warnings.append(
            {
                "code": "field_added",
                "field": field,
                "message": "Campo no observado en la ejecución válida anterior.",
            }
        )
    for field in sorted(previous_schema.keys() - current.keys()):
        warnings.append(
            {
                "code": "field_missing_since_previous",
                "field": field,
                "message": "Campo anterior ausente en esta instantánea.",
            }
        )
    for field in sorted(current.keys() & previous_schema.keys()):
        current_types = set(current[field]["types"])
        previous_types = set(previous_schema[field].get("types", {}))
        if current_types != previous_types:
            warnings.append(
                {
                    "code": "field_type_changed",
                    "field": field,
                    "message": (
                        "Los tipos JSON observados difieren de la ejecución "
                        "válida anterior."
                    ),
                }
            )
    return warnings


def _freshness(
    source_date: date | None, today: date
) -> tuple[str, str | None]:
    if source_date is None or source_date > today:
        return "no_verificable", None
    age_days = (today - source_date).days
    status = "antiguo" if age_days > STALE_AFTER_DAYS else "reciente"
    return status, f"{age_days} día(s)"


def _make_run_id(downloaded_at: datetime) -> str:
    return downloaded_at.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]


def _write_json_atomic(target_dir: Path, manifest: dict[str, Any]) -> None:
    temporary_dir: Path | None = None
    try:
        temporary_dir = Path(
            tempfile.mkdtemp(prefix=".catalog-run-", dir=target_dir.parent)
        )
        (temporary_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_dir.rename(target_dir)
    except OSError as error:
        if temporary_dir is not None and temporary_dir.exists():
            shutil.rmtree(temporary_dir, ignore_errors=True)
        raise CatalogIngestionError(
            "No se pudo guardar el manifiesto de la ejecución."
        ) from error


def _save_failure(
    output_root: Path,
    downloaded_at: datetime,
    reason: str,
    failure_kind: str,
    downloaded_body: bytes | None = None,
) -> None:
    failures_root = output_root / "failures"
    try:
        failures_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise CatalogIngestionError(
            "La ingesta falló y no se pudo guardar el manifiesto de fallo."
        ) from error

    run_dir = failures_root / _make_run_id(downloaded_at)
    manifest = {
        "source_url": CATALOG_JSON_URL,
        "dataset_url": DATASET_URL,
        "downloaded_at_utc": downloaded_at.isoformat(),
        "download_size_bytes": (
            len(downloaded_body) if downloaded_body is not None else None
        ),
        "sha256": (
            hashlib.sha256(downloaded_body).hexdigest()
            if downloaded_body is not None
            else None
        ),
        "record_count": None,
        "observed_fields": {},
        "structure_warnings": [],
        "extraction_status": "fallida",
        "failure_kind": failure_kind,
        "failure_message": reason,
        "source_updated_at": None,
        "freshness_status": "no_verificable",
    }
    _write_json_atomic(run_dir, manifest)


def ingest_catalog(
    output_root: Path | None = None,
    *,
    opener: Callable[..., Any] | None = None,
    now: datetime | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> CatalogResult:
    """Descarga y almacena una instantánea del catálogo sin modificar registros."""
    root = output_root if output_root is not None else DEFAULT_OUTPUT_ROOT
    open_url = opener if opener is not None else urlopen
    downloaded_at = now or datetime.now(timezone.utc)
    if downloaded_at.tzinfo is None:
        raise ValueError("now debe incluir zona horaria.")
    downloaded_at = downloaded_at.astimezone(timezone.utc)

    response_body: bytes | None = None
    try:
        response_body, content_type = _read_url(
            CATALOG_JSON_URL, open_url, timeout
        )
        if not _json_media_type_is_valid(content_type):
            raise CatalogIngestionError(
                "La fuente no devolvió un tipo de contenido JSON."
            )
        payload = json.loads(response_body)
        if not isinstance(payload, list):
            raise CatalogIngestionError(
                "El JSON del catálogo debe tener una lista en la raíz."
            )
        if not all(isinstance(record, dict) for record in payload):
            raise CatalogIngestionError(
                "Todos los elementos del catálogo deben ser objetos JSON."
            )
    except (CatalogIngestionError, json.JSONDecodeError, UnicodeDecodeError) as error:
        message = (
            str(error)
            if isinstance(error, CatalogIngestionError)
            else "La fuente devolvió JSON inválido o ilegible."
        )
        failure_kind = (
            "invalid_json"
            if isinstance(error, (json.JSONDecodeError, UnicodeDecodeError))
            else "download_or_structure"
        )
        _save_failure(
            root, downloaded_at, message, failure_kind, downloaded_body=response_body
        )
        raise CatalogIngestionError(message) from error

    snapshot_hash = hashlib.sha256(response_body).hexdigest()
    observed_fields = _observe_fields(payload)
    previous_manifests = _previous_valid_manifests(root)
    previous = previous_manifests[-1] if previous_manifests else None
    warnings = _compare_schema(observed_fields, previous, len(payload))

    if any(
        manifest.get("sha256") == snapshot_hash
        for manifest in previous_manifests
    ):
        warnings.append(
            {
                "code": "identical_snapshot",
                "field": "",
                "message": (
                    "El SHA-256 coincide con una ejecución válida anterior; "
                    "esto no demuestra que no haya anuncios nuevos."
                ),
            }
        )

    source_date: date | None = None
    try:
        rdf_body, _ = _read_url(CATALOG_RDF_URL, open_url, timeout)
        source_date = _source_updated_at(rdf_body)
    except (CatalogIngestionError, ValueError):
        warnings.append(
            {
                "code": "source_metadata_unavailable",
                "field": "",
                "message": (
                    "No se pudo consultar o interpretar la fecha de "
                    "actualización publicada por la fuente."
                ),
            }
        )

    freshness_status, source_age = _freshness(source_date, downloaded_at.date())
    if freshness_status == "antiguo":
        warnings.append(
            {
                "code": "source_data_stale",
                "field": "",
                "message": (
                    f"La fecha de actualización publicada tiene {source_age}; "
                    f"el umbral de advertencia del proyecto es "
                    f"{STALE_AFTER_DAYS} días."
                ),
            }
        )

    status = "valid_empty" if not payload else "valid_with_data"
    manifest = {
        "source_url": CATALOG_JSON_URL,
        "dataset_url": DATASET_URL,
        "license_url": LICENSE_URL,
        "license_note": (
            "CC BY 4.0 está declarada para el JSON de esta ficha; no se "
            "presupone que cubra todas las respuestas de la API."
        ),
        "downloaded_at_utc": downloaded_at.isoformat(),
        "download_size_bytes": len(response_body),
        "sha256": snapshot_hash,
        "record_count": len(payload),
        "observed_fields": observed_fields,
        "structure_warnings": warnings,
        "extraction_status": status,
        "source_updated_at": source_date.isoformat() if source_date else None,
        "source_age": source_age,
        "freshness_status": freshness_status,
        "freshness_threshold_days": STALE_AFTER_DAYS,
    }

    try:
        root.mkdir(parents=True, exist_ok=True)
        run_dir = root / _make_run_id(downloaded_at)
        temporary_dir = Path(tempfile.mkdtemp(prefix=".catalog-run-", dir=root))
        try:
            (temporary_dir / "response.json").write_bytes(response_body)
            (temporary_dir / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_dir.rename(run_dir)
        except OSError as error:
            if temporary_dir.exists():
                shutil.rmtree(temporary_dir, ignore_errors=True)
            raise error
    except OSError as error:
        message = "No se pudo guardar la instantánea del catálogo."
        _save_failure(
            root, downloaded_at, message, "storage", downloaded_body=response_body
        )
        raise CatalogIngestionError(message) from error

    return CatalogResult(
        output_dir=run_dir,
        status=status,
        record_count=len(payload),
        snapshot_sha256=snapshot_hash,
        source_updated_at=source_date.isoformat() if source_date else None,
        freshness_status=freshness_status,
        warnings=tuple(warnings),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga el JSON público de contrataciones de los últimos 90 días."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="Directorio local para ejecuciones (predeterminado: radar/data/raw/catalog).",
    )
    args = parser.parse_args()

    try:
        result = ingest_catalog(output_root=args.output_dir)
    except CatalogIngestionError as error:
        parser.exit(status=1, message=f"Error: {error}\n")

    print(
        f"Ingesta {result.status}: {result.record_count} registro(s); "
        f"frescura {result.freshness_status}; resultado guardado en "
        f"{result.output_dir}"
    )
    for warning in result.warnings:
        print(f"Advertencia [{warning['code']}]: {warning['message']}")


if __name__ == "__main__":
    main()
