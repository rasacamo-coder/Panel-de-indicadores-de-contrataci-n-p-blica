import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from radar.build_dashboard_data import (
    DEADLINE_FIELD,
    ORGANIZATION_FIELD,
    PUBLICATION_DATE_FIELD,
    aggregate_records,
)
from radar.catalog_source import (
    CATALOG_JSON_URL,
    DATASET_URL,
    LICENSE_URL,
    CatalogIngestionError,
)
from radar.update_dashboard import (
    DashboardUpdateError,
    prepare_dashboard_update,
    prepare_work_directory,
    publish_prepared_dashboard,
    validate_public_summary,
)

FIXED_NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
RECORDS = [
    {
        PUBLICATION_DATE_FIELD: "27/10/2026",
        ORGANIZATION_FIELD: "Órgano sintético",
        DEADLINE_FIELD: "29/10/2026 10:00",
        "contratacion_objeto_contrato": "Título sintético que no debe publicarse",
        "contratacion_expediente": "EXPEDIENTE-SINTÉTICO",
        "friendlyUrl": "https://example.invalid/registro",
    }
]


def create_capture(root: Path, records=None, *, source_date="2026-10-27"):
    capture = root / "capture"
    capture.mkdir(parents=True)
    payload = RECORDS if records is None else records
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    (capture / "response.json").write_bytes(raw)
    manifest = {
        "source_url": CATALOG_JSON_URL,
        "dataset_url": DATASET_URL,
        "license_url": LICENSE_URL,
        "downloaded_at_utc": "2026-10-28T04:05:06+00:00",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "record_count": len(payload),
        "extraction_status": "valid_with_data" if payload else "valid_empty",
        "source_updated_at": source_date,
        "freshness_status": "reciente",
    }
    (capture / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return root


class DashboardUpdateTests(unittest.TestCase):
    def test_prepare_and_publish_valid_aggregate_only_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captures = create_capture(root)
            public = root / "site" / "radar-summary.json"
            previous = b'{"previous":"valid"}\n'
            public.parent.mkdir()
            public.write_bytes(previous)
            staged = root / "work" / "radar-summary.json"

            prepared = prepare_dashboard_update(
                captures, staged, current_output=public, generated_at=FIXED_NOW
            )

            self.assertEqual(prepared.record_count, 1)
            self.assertEqual(prepared.source_updated_at, "2026-10-27")
            self.assertEqual(public.read_bytes(), previous)
            data = validate_public_summary(json.loads(staged.read_text("utf-8")))
            serialized = staged.read_text("utf-8")
            self.assertEqual(data["summary"]["notice_count"], 1)
            self.assertNotIn("contratacion_objeto_contrato", serialized)
            self.assertNotIn("EXPEDIENTE-SINTÉTICO", serialized)
            self.assertNotIn("example.invalid/registro", serialized)

            self.assertTrue(publish_prepared_dashboard(staged, public))
            self.assertEqual(json.loads(public.read_text("utf-8")), data)

    def test_empty_capture_does_not_replace_last_valid_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captures = create_capture(root, records=[])
            public = root / "site" / "radar-summary.json"
            public.parent.mkdir()
            previous = b"last valid summary\n"
            public.write_bytes(previous)
            staged = root / "work" / "radar-summary.json"

            with self.assertRaisesRegex(DashboardUpdateError, "no contiene registros"):
                prepare_dashboard_update(
                    captures, staged, current_output=public, generated_at=FIXED_NOW
                )

            self.assertEqual(public.read_bytes(), previous)
            self.assertFalse(staged.exists())

    def test_stale_source_metadata_blocks_publication_without_replacing_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captures = create_capture(root, source_date="2026-10-20")
            public = root / "site" / "radar-summary.json"
            public.parent.mkdir()
            previous = b"last valid summary\n"
            public.write_bytes(previous)

            with self.assertRaisesRegex(DashboardUpdateError, "frescura"):
                prepare_dashboard_update(
                    captures,
                    root / "work" / "radar-summary.json",
                    current_output=public,
                    generated_at=FIXED_NOW,
                )

            self.assertEqual(public.read_bytes(), previous)

    def test_missing_source_metadata_blocks_publication(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captures = create_capture(root, source_date=None)
            public = root / "site" / "radar-summary.json"
            public.parent.mkdir()
            previous = b"last valid summary\n"
            public.write_bytes(previous)

            with self.assertRaisesRegex(DashboardUpdateError, "Faltan los metadatos"):
                prepare_dashboard_update(
                    captures,
                    root / "work" / "radar-summary.json",
                    current_output=public,
                    generated_at=FIXED_NOW,
                )

            self.assertEqual(public.read_bytes(), previous)

    def test_schema_or_invalid_dates_block_the_prepared_summary(self):
        invalid_records = [
            [{"synthetic_only": "no required fields"}],
            [
                {
                    PUBLICATION_DATE_FIELD: "2026-10-27",
                    ORGANIZATION_FIELD: "Órgano sintético",
                    DEADLINE_FIELD: "29/10/2026 10:00",
                }
            ],
        ]
        for records in invalid_records:
            with self.subTest(records=records):
                with tempfile.TemporaryDirectory() as temp_dir:
                    root = Path(temp_dir)
                    captures = create_capture(root, records=records)
                    staged = root / "work" / "radar-summary.json"

                    with self.assertRaises(DashboardUpdateError):
                        prepare_dashboard_update(
                            captures, staged, generated_at=FIXED_NOW
                        )

                    self.assertFalse(staged.exists())

    def test_download_failure_cannot_replace_the_last_valid_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            work_directory = root / ".radar-work"
            public = root / "site" / "radar-summary.json"
            public.parent.mkdir()
            previous = b"last valid summary\n"
            public.write_bytes(previous)

            with patch(
                "radar.update_dashboard.ingest_catalog",
                side_effect=CatalogIngestionError("synthetic download failure"),
            ):
                with self.assertRaisesRegex(
                    CatalogIngestionError, "synthetic download failure"
                ):
                    prepare_work_directory(work_directory, current_output=public)

            self.assertEqual(public.read_bytes(), previous)
            self.assertFalse((work_directory / "radar-summary.json").exists())

    def test_unchanged_snapshot_does_not_rewrite_public_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captures = create_capture(root)
            public = root / "site" / "radar-summary.json"
            public.parent.mkdir()
            existing = aggregate_records(
                {
                    "dataset_url": DATASET_URL,
                    "source_url": CATALOG_JSON_URL,
                    "source_updated_at": "2026-10-27",
                    "downloaded_at_utc": "2026-10-28T04:05:06+00:00",
                    "sha256": hashlib.sha256(
                        (captures / "capture" / "response.json").read_bytes()
                    ).hexdigest(),
                    "freshness_status": "reciente",
                },
                RECORDS,
                FIXED_NOW,
            )
            public.write_text(json.dumps(existing), encoding="utf-8")
            old_bytes = public.read_bytes()
            staged = root / "work" / "radar-summary.json"

            prepare_dashboard_update(
                captures,
                staged,
                current_output=public,
                generated_at=datetime(2026, 10, 28, 13, 0, tzinfo=timezone.utc),
            )

            self.assertFalse(publish_prepared_dashboard(staged, public))
            self.assertEqual(public.read_bytes(), old_bytes)

    def test_count_variations_are_reported_for_review(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captures = create_capture(root, records=RECORDS * 2)
            public = root / "site" / "radar-summary.json"
            public.parent.mkdir()
            old = aggregate_records(
                {
                    "dataset_url": DATASET_URL,
                    "source_url": CATALOG_JSON_URL,
                    "source_updated_at": "2026-10-27",
                    "downloaded_at_utc": "2026-10-28T04:05:06+00:00",
                    "sha256": "0" * 64,
                    "freshness_status": "reciente",
                },
                RECORDS,
                FIXED_NOW,
            )
            public.write_text(json.dumps(old), encoding="utf-8")

            prepared = prepare_dashboard_update(
                captures,
                root / "work" / "radar-summary.json",
                current_output=public,
                generated_at=FIXED_NOW,
            )

            self.assertTrue(any("revisar la variación" in warning for warning in prepared.warnings))

    def test_summary_rejects_unexpected_record_shaped_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            captures = create_capture(root)
            staged = root / "work" / "radar-summary.json"
            prepare_dashboard_update(captures, staged, generated_at=FIXED_NOW)
            data = json.loads(staged.read_text("utf-8"))
            data["records"] = [{"id": "individual"}]
            staged.write_text(json.dumps(data), encoding="utf-8")
            public = root / "site" / "radar-summary.json"
            public.parent.mkdir()
            previous = b"last valid summary\n"
            public.write_bytes(previous)

            with self.assertRaisesRegex(DashboardUpdateError, "raíz"):
                publish_prepared_dashboard(staged, public)

            self.assertEqual(public.read_bytes(), previous)


if __name__ == "__main__":
    unittest.main()
