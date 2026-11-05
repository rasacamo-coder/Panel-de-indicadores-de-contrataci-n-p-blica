"""Descarga acotada de una muestra de avisos desde la API oficial."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

API_URL = "https://api.euskadi.eus/procurements/contracting-notices"
CATALOG_URL = (
    "https://opendata.euskadi.eus/catalogo/-/contrataciones/"
    "contrataciones-administrativas-del-2026/"
)
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
MAX_ITEMS_PER_PAGE = 50
DEFAULT_SAMPLE_SIZE = 5
REQUEST_TIMEOUT_SECONDS = 30


class SampleExtractionError(Exception):
    """Error de extracción que puede explicarse sin mostrar una traza."""


@dataclass(frozen=True)
class ValidationIssue:
    """Hallazgo preliminar asociado a un registro."""

    code: str
    message: str
    record_index: int | None = None
    field: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "record_index": self.record_index,
            "field": self.field,
        }


@dataclass(frozen=True)
class RecordValidationReport:
    """Errores bloqueantes y advertencias no bloqueantes de los registros."""

    errors: list[ValidationIssue]
    warnings: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def status(self) -> str:
        if self.errors:
            return "failed"
        if self.warnings:
            return "passed_with_warnings"
        return "passed"

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
        }


class RecordValidationError(SampleExtractionError):
    """La validación preliminar encontró errores que impiden guardar."""

    def __init__(self, report: RecordValidationReport):
        self.report = report
        details = "\n".join(
            f"- {self._format_issue(issue)}" for issue in report.errors
        )
        super().__init__(
            "La validación preliminar encontró "
            f"{len(report.errors)} error(es); no se guardó la muestra:\n"
            f"{details}"
        )

    @staticmethod
    def _format_issue(issue: ValidationIssue) -> str:
        location = []
        if issue.record_index is not None:
            location.append(f"registro {issue.record_index}")
        if issue.field is not None:
            location.append(f"campo '{issue.field}'")
        prefix = ", ".join(location) or "respuesta"
        return f"{prefix} [{issue.code}]: {issue.message}"


@dataclass(frozen=True)
class SampleResult:
    """Resultado guardado de una consulta, que puede estar vacía."""

    output_dir: Path
    returned_rows: int
    validation_warnings: int = 0

    @property
    def is_empty(self) -> bool:
        return self.returned_rows == 0


RECORD_FIELD_TYPES: dict[str, str] = {
    "_links": "object",
    "budgetWithoutVAT": "number",
    "code": "string",
    "contractProcedureStatus": "object",
    "contractProcedureType": "object",
    "contractType": "object",
    "contractingAuthority": "object",
    "deadlineDate": "string",
    "entity": "object",
    "financedEuropeanFunds": "boolean",
    "firstPublicationDate": "date",
    "id": "number",
    "lastPublicationDate": "date",
    "mainEntityOfPage": "string",
    "minorContract": "boolean",
    "name": "string",
    "numberBidders": "number",
    "object": "string",
    "openingDates": "string_list",
    "recoveryPlan": "boolean",
    "sara": "boolean",
    "subjectAppeal": "boolean",
}


def build_request_url(
    publication_date_gt: date,
    publication_date_lt: date,
    limit: int = DEFAULT_SAMPLE_SIZE,
) -> str:
    """Construye una consulta pequeña y acotada con parámetros documentados."""
    if publication_date_gt >= publication_date_lt:
        raise ValueError("La fecha .gt debe ser anterior a la fecha .lt.")
    if not 1 <= limit <= MAX_ITEMS_PER_PAGE:
        raise ValueError(
            f"El límite debe estar entre 1 y {MAX_ITEMS_PER_PAGE}."
        )

    query = urlencode(
        {
            "publication-date.gt": publication_date_gt.isoformat(),
            "publication-date.lt": publication_date_lt.isoformat(),
            "orderBy": "firstPublicationDate",
            "orderType": "ASC",
            "currentPage": "1",
            "itemsOfPage": str(limit),
            "lang": "SPANISH",
        }
    )
    return f"{API_URL}?{query}"


def validate_api_envelope(payload: object, limit: int) -> dict[str, Any]:
    """Valida la envoltura y paginación, no el esquema de negocio."""
    if not isinstance(payload, dict):
        raise SampleExtractionError(
            "La respuesta de la API no tiene el formato JSON esperado."
        )

    required_keys = {
        "totalItems",
        "totalPages",
        "currentPage",
        "itemsOfPage",
        "items",
    }
    missing_keys = required_keys.difference(payload)
    if missing_keys:
        raise SampleExtractionError(
            "La respuesta de la API no incluye los datos de paginación "
            "esperados."
        )

    for key in ("totalItems", "totalPages", "currentPage", "itemsOfPage"):
        value = payload[key]
        if type(value) is not int or value < 0:
            raise SampleExtractionError(
                "La respuesta de la API contiene metadatos de paginación "
                "inválidos."
            )
    if payload["currentPage"] < 1:
        raise SampleExtractionError(
            "La respuesta de la API contiene metadatos de paginación inválidos."
        )

    items = payload["items"]
    if not isinstance(items, list):
        raise SampleExtractionError(
            "La respuesta de la API contiene una lista de resultados inválida."
        )
    if (not items and payload["totalItems"] != 0) or (
        items and payload["totalItems"] == 0
    ):
        raise SampleExtractionError(
            "El total indicado por la API no coincide con los resultados."
        )
    if len(items) > limit:
        raise SampleExtractionError(
            "La API devolvió más resultados que el límite solicitado."
        )

    return payload


def validate_record_objects(items: list[object]) -> list[dict[str, Any]]:
    """Valida y devuelve registros JSON, identificando el índice inválido."""
    records: list[dict[str, Any]] = []
    for record_index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise SampleExtractionError(
                f"El registro {record_index} de la respuesta no es un "
                "objeto JSON."
            )
        records.append(item)
    return records


def _matches_record_type(value: object, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "number":
        return type(value) in (int, float)
    if expected_type == "boolean":
        return type(value) is bool
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "string_list":
        return isinstance(value, list) and all(
            isinstance(item, str) for item in value
        )
    if expected_type == "date":
        return isinstance(value, str)
    return False


def _is_documented_iso_date(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value)) and (
        _valid_calendar_date(value)
    )


def _valid_calendar_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def validate_records(
    items: list[dict[str, Any]],
) -> RecordValidationReport:
    """Valida tipos preliminares, fechas documentadas y anomalías investigables."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    observed_values: dict[str, dict[object, list[int]]] = {
        "id": {},
        "code": {},
    }

    for record_index, item in enumerate(items, start=1):
        for field in RECORD_FIELD_TYPES.keys() - item.keys():
            warnings.append(
                ValidationIssue(
                    code="field_missing",
                    message=(
                        "El campo inventariado no aparece en este registro; "
                        "su obligatoriedad no está confirmada."
                    ),
                    record_index=record_index,
                    field=field,
                )
            )

        for field, value in item.items():
            expected_type = RECORD_FIELD_TYPES.get(field)
            if expected_type is None:
                warnings.append(
                    ValidationIssue(
                        code="unknown_field",
                        message=(
                            "El campo no figura en el inventario preliminar."
                        ),
                        record_index=record_index,
                        field=field,
                    )
                )
                continue

            if value is None:
                warnings.append(
                    ValidationIssue(
                        code="field_null",
                        message=(
                            "El campo contiene null; su nulabilidad no está "
                            "confirmada."
                        ),
                        record_index=record_index,
                        field=field,
                    )
                )
                continue

            if expected_type == "date" and not isinstance(value, str):
                errors.append(
                    ValidationIssue(
                        code="unexpected_documented_type",
                        message=(
                            "La fecha de publicación documentada debe ser "
                            "texto con formato AAAA-MM-DD."
                        ),
                        record_index=record_index,
                        field=field,
                    )
                )
                continue

            if not _matches_record_type(value, expected_type):
                warnings.append(
                    ValidationIssue(
                        code="unexpected_type",
                        message=(
                            "El tipo no coincide con el tipo preliminar "
                            "documentado u observado."
                        ),
                        record_index=record_index,
                        field=field,
                    )
                )
                continue

            if expected_type == "date" and not _is_documented_iso_date(value):
                errors.append(
                    ValidationIssue(
                        code="invalid_date_format",
                        message=(
                            "La fecha debe respetar el formato documentado "
                            "AAAA-MM-DD y ser una fecha válida."
                        ),
                        record_index=record_index,
                        field=field,
                    )
                )

            if field in observed_values and type(value) in (int, float, str):
                observed_values[field].setdefault(value, []).append(record_index)

        if ("object" in item) != ("name" in item):
            warnings.append(
                ValidationIssue(
                    code="object_name_discrepancy",
                    message=(
                        "Solo aparece uno de los campos object y name; no se "
                        "asumen equivalentes ni se renombran."
                    ),
                    record_index=record_index,
                    field="object/name",
                )
            )

    for field, values in observed_values.items():
        for indexes in values.values():
            if len(indexes) > 1:
                warnings.append(
                    ValidationIssue(
                        code="possible_identifier_collision",
                        message=(
                            "El mismo valor aparece en varios registros; "
                            "es una colisión candidata, no una deduplicación."
                        ),
                        field=field,
                    )
                )
                for record_index in indexes:
                    warnings.append(
                        ValidationIssue(
                            code="possible_identifier_collision_record",
                            message=(
                                "Este registro participa en una colisión "
                                "candidata que requiere revisión."
                            ),
                            record_index=record_index,
                            field=field,
                        )
                    )

    return RecordValidationReport(errors=errors, warnings=warnings)


def _request_body(request: Request) -> bytes:
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
            if media_type != "application/json" and not media_type.endswith(
                "+json"
            ):
                raise SampleExtractionError(
                    "La API no devolvió JSON. Inténtalo más tarde o revisa "
                    "la documentación de la fuente."
                )
            return response.read()
    except HTTPError as error:
        raise SampleExtractionError(
            f"La API respondió con un error HTTP ({error.code}). "
            "Inténtalo más tarde."
        ) from error
    except (TimeoutError, socket.timeout) as error:
        raise SampleExtractionError(
            "La petición a la API agotó el tiempo de espera. "
            "Comprueba la conexión e inténtalo de nuevo."
        ) from error
    except URLError as error:
        if isinstance(error.reason, (TimeoutError, socket.timeout)):
            raise SampleExtractionError(
                "La petición a la API agotó el tiempo de espera. "
                "Comprueba la conexión e inténtalo de nuevo."
            ) from error
        raise SampleExtractionError(
            "No se pudo conectar con la API. Comprueba la conexión "
            "e inténtalo de nuevo."
        ) from error
    except HTTPException as error:
        raise SampleExtractionError(
            "La respuesta de la API llegó incompleta o no se pudo leer. "
            "Inténtalo más tarde."
        ) from error
    except OSError as error:
        raise SampleExtractionError(
            "La conexión con la API falló. Comprueba la conexión "
            "e inténtalo de nuevo."
        ) from error


def _parse_api_response(
    response_body: bytes, limit: int
) -> tuple[dict[str, Any], RecordValidationReport]:
    try:
        payload = json.loads(response_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SampleExtractionError(
            "La API devolvió contenido JSON inválido o incompleto."
        ) from error

    envelope = validate_api_envelope(payload, limit)
    records = validate_record_objects(envelope["items"])
    report = validate_records(records)
    if not report.is_valid:
        raise RecordValidationError(report)
    return envelope, report


def _save_sample(
    response_body: bytes,
    payload: dict[str, Any],
    request_url: str,
    publication_date_gt: date,
    publication_date_lt: date,
    limit: int,
    output_dir: Path | None,
    validation_report: RecordValidationReport,
) -> SampleResult:
    target_root = (
        output_dir
        if output_dir is not None
        else Path(__file__).resolve().parent / "data" / "raw"
    )
    try:
        target_root.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise SampleExtractionError(
            "No se pudo preparar la carpeta local para guardar la muestra."
        ) from error

    retrieved_at = datetime.now(timezone.utc)
    run_id = retrieved_at.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = target_root / run_id
    items = payload["items"]
    result_status = "empty" if not items else "non_empty"
    manifest = {
        "source_api": API_URL,
        "catalog_reference": CATALOG_URL,
        "license_reference": LICENSE_URL,
        "license_note": (
            "La ficha de 2026 declara CC BY 4.0; hay que confirmar si esa "
            "licencia cubre el alcance de esta respuesta API antes de "
            "redistribuirla."
        ),
        "request_url": request_url,
        "publication_date_gt": publication_date_gt.isoformat(),
        "publication_date_lt": publication_date_lt.isoformat(),
        "requested_limit": limit,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "returned_rows": len(items),
        "api_total_items": payload["totalItems"],
        "api_total_pages": payload["totalPages"],
        "result_status": result_status,
        "envelope_validation": "passed",
        "record_object_validation": "passed",
        "domain_schema_validation": validation_report.status,
        "record_validation": validation_report.as_dict(),
        "pipeline_version": "0.1.0",
    }

    temporary_dir: Path | None = None
    try:
        temporary_dir = Path(
            tempfile.mkdtemp(prefix=".radar-run-", dir=target_root)
        )
        (temporary_dir / "response.json").write_bytes(response_body)
        (temporary_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_dir.rename(run_dir)
    except OSError as error:
        if temporary_dir is not None and temporary_dir.exists():
            try:
                shutil.rmtree(temporary_dir)
            except OSError as cleanup_error:
                raise SampleExtractionError(
                    "No se pudo guardar la muestra ni limpiar su carpeta "
                    "temporal. Revisa la carpeta local de datos."
                ) from cleanup_error
        raise SampleExtractionError(
            "No se pudo guardar la muestra en la carpeta local de datos. "
            "Comprueba los permisos y el espacio disponible."
        ) from error

    return SampleResult(
        output_dir=run_dir,
        returned_rows=len(items),
        validation_warnings=len(validation_report.warnings),
    )


def download_sample(
    publication_date_gt: date,
    publication_date_lt: date,
    limit: int = DEFAULT_SAMPLE_SIZE,
    output_dir: Path | None = None,
) -> SampleResult:
    """Descarga y guarda una respuesta en una carpeta nueva, incluso si está vacía."""
    try:
        request_url = build_request_url(
            publication_date_gt, publication_date_lt, limit
        )
    except ValueError as error:
        raise SampleExtractionError(str(error)) from error

    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "radar-contratacion-euskadi/0.1.0",
        },
    )
    response_body = _request_body(request)
    payload, validation_report = _parse_api_response(response_body, limit)
    return _save_sample(
        response_body=response_body,
        payload=payload,
        request_url=request_url,
        publication_date_gt=publication_date_gt,
        publication_date_lt=publication_date_lt,
        limit=limit,
        output_dir=output_dir,
        validation_report=validation_report,
    )


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"Fecha no válida: {value}. Usa el formato AAAA-MM-DD."
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Descarga una muestra pequeña de avisos de contratación."
    )
    parser.add_argument(
        "--publication-date-gt",
        required=True,
        type=_parse_iso_date,
        help="Límite inferior exclusivo, formato AAAA-MM-DD.",
    )
    parser.add_argument(
        "--publication-date-lt",
        required=True,
        type=_parse_iso_date,
        help="Límite superior exclusivo, formato AAAA-MM-DD.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_SAMPLE_SIZE,
        help=f"Máximo de resultados (1-{MAX_ITEMS_PER_PAGE}; predeterminado: 5).",
    )
    args = parser.parse_args()

    try:
        result = download_sample(
            args.publication_date_gt,
            args.publication_date_lt,
            args.limit,
        )
    except SampleExtractionError as error:
        parser.exit(status=1, message=f"Error: {error}\n")

    if result.is_empty:
        print(
            "La consulta fue válida, pero no devolvió registros. "
            f"Se guardó el resultado vacío en: {result.output_dir}"
        )
    else:
        print(
            f"Muestra validada guardada en: {result.output_dir} "
            f"({result.returned_rows} registros; "
            f"{result.validation_warnings} advertencias preliminares)"
        )


if __name__ == "__main__":
    main()
