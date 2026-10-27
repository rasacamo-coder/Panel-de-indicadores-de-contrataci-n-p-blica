"""Descarga acotada de una muestra de avisos desde la API oficial."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
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


def validate_response(payload: object, limit: int) -> dict[str, Any]:
    """Comprueba la envoltura y los registros sin imponer un esquema de dominio."""
    if not isinstance(payload, dict):
        raise ValueError("La respuesta de la API no es un objeto JSON.")

    required_keys = {
        "totalItems",
        "totalPages",
        "currentPage",
        "itemsOfPage",
        "items",
    }
    missing_keys = required_keys.difference(payload)
    if missing_keys:
        raise ValueError(
            "Faltan propiedades de paginación en la respuesta: "
            + ", ".join(sorted(missing_keys))
        )

    items = payload["items"]
    if not isinstance(items, list):
        raise ValueError("La propiedad 'items' no es una lista.")
    if not items:
        raise ValueError("La consulta no devolvió registros.")
    if len(items) > limit:
        raise ValueError("La API devolvió más registros que el límite pedido.")
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("La lista 'items' contiene un registro no JSON-objeto.")

    return payload


def download_sample(
    publication_date_gt: date,
    publication_date_lt: date,
    limit: int = DEFAULT_SAMPLE_SIZE,
    output_dir: Path | None = None,
) -> Path:
    """Descarga, valida y guarda una respuesta y su manifiesto en una carpeta nueva."""
    request_url = build_request_url(
        publication_date_gt, publication_date_lt, limit
    )
    request = Request(
        request_url,
        headers={
            "Accept": "application/json",
            "User-Agent": "radar-contratacion-euskadi/0.1.0",
        },
    )

    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get("Content-Type", "")
        if "json" not in content_type.lower():
            raise ValueError(
                f"La API devolvió un Content-Type inesperado: {content_type}"
            )
        response_body = response.read()

    payload = validate_response(json.loads(response_body), limit)
    target_root = (
        output_dir
        if output_dir is not None
        else Path(__file__).resolve().parent / "data" / "raw"
    )
    target_root.mkdir(parents=True, exist_ok=True)

    retrieved_at = datetime.now(timezone.utc)
    run_id = retrieved_at.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = target_root / run_id
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
        "returned_rows": len(payload["items"]),
        "api_total_items": payload["totalItems"],
        "api_total_pages": payload["totalPages"],
        "envelope_validation": "passed",
        "domain_schema_validation": "not performed",
        "pipeline_version": "0.1.0",
    }

    temporary_dir = Path(
        tempfile.mkdtemp(prefix=".radar-run-", dir=target_root)
    )
    try:
        (temporary_dir / "response.json").write_bytes(response_body)
        (temporary_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_dir.rename(run_dir)
    finally:
        if temporary_dir.exists():
            for child in temporary_dir.iterdir():
                child.unlink()
            temporary_dir.rmdir()

    return run_dir


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

    run_dir = download_sample(
        args.publication_date_gt,
        args.publication_date_lt,
        args.limit,
    )
    print(f"Muestra validada guardada en: {run_dir}")


if __name__ == "__main__":
    main()
