"""Descarga acotada de una muestra de avisos desde la API oficial."""

from __future__ import annotations

import argparse
import json
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
class SampleResult:
    """Resultado guardado de una consulta, que puede estar vacía."""

    output_dir: Path
    returned_rows: int

    @property
    def is_empty(self) -> bool:
        return self.returned_rows == 0


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


def validate_record_objects(items: list[object]) -> None:
    """Comprueba solo que cada resultado sea un objeto JSON."""
    if not all(isinstance(item, dict) for item in items):
        raise SampleExtractionError(
            "La respuesta de la API contiene un resultado que no es un "
            "objeto JSON."
        )


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


def _parse_api_response(response_body: bytes, limit: int) -> dict[str, Any]:
    try:
        payload = json.loads(response_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise SampleExtractionError(
            "La API devolvió contenido JSON inválido o incompleto."
        ) from error

    envelope = validate_api_envelope(payload, limit)
    validate_record_objects(envelope["items"])
    return envelope


def _save_sample(
    response_body: bytes,
    payload: dict[str, Any],
    request_url: str,
    publication_date_gt: date,
    publication_date_lt: date,
    limit: int,
    output_dir: Path | None,
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
        "domain_schema_validation": "not performed",
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

    return SampleResult(output_dir=run_dir, returned_rows=len(items))


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
    payload = _parse_api_response(response_body, limit)
    return _save_sample(
        response_body=response_body,
        payload=payload,
        request_url=request_url,
        publication_date_gt=publication_date_gt,
        publication_date_lt=publication_date_lt,
        limit=limit,
        output_dir=output_dir,
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
            f"({result.returned_rows} registros)"
        )


if __name__ == "__main__":
    main()
