import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from radar.build_dashboard_data import (
    DEADLINE_FIELD,
    ORGANIZATION_FIELD,
    PUBLICATION_DATE_FIELD,
    DashboardDataError,
    aggregate_records,
    build_dashboard_data,
)

FIXED_GENERATED_AT = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
SOURCE_MANIFEST = {
    "dataset_url": "https://example.test/catalog",
    "source_url": "https://example.test/contracts.json",
    "source_updated_at": "2026-10-27",
    "downloaded_at_utc": "2026-10-28T04:05:06+00:00",
    "sha256": "synthetic-sha256",
    "freshness_status": "reciente",
}


def synthetic_record(publication, organization, deadline, extra=None):
    record = {
        PUBLICATION_DATE_FIELD: publication,
        ORGANIZATION_FIELD: organization,
        DEADLINE_FIELD: deadline,
    }
    if extra:
        record.update(extra)
    return record


class DashboardAggregationTests(unittest.TestCase):
    def test_aggregates_counts_dates_deadlines_and_completeness(self):
        records = [
            synthetic_record("26/10/2026", "Órgano Alfa", "26/10/2026 10:00"),
            synthetic_record("26/10/2026", "Órgano Alfa", "27/10/2026 12:00"),
            synthetic_record("25/10/2026", "Órgano Beta", "25/10/2026 09:00"),
        ]

        data = aggregate_records(SOURCE_MANIFEST, records, FIXED_GENERATED_AT)

        self.assertEqual(data["summary"]["notice_count"], 3)
        self.assertEqual(data["summary"]["distinct_organizations"], 2)
        self.assertEqual(data["summary"]["distinct_publication_dates"], 2)
        self.assertEqual(data["summary"]["deadlines_before_source_update_day"], 2)
        self.assertEqual(
            data["activity_by_date"],
            [
                {"date": "2026-10-25", "notice_count": 1},
                {"date": "2026-10-26", "notice_count": 2},
            ],
        )
        self.assertEqual(
            data["field_completeness"][ORGANIZATION_FIELD]["completeness_percent"],
            100.0,
        )
        self.assertEqual(data["date_quality"]["deadline_review_available"], True)
        self.assertTrue(data["methodology"]["last_publication_date_is_not_used"])

    def test_empty_and_invalid_dates_are_counted_separately(self):
        records = [
            synthetic_record("", "Órgano Alfa", ""),
            synthetic_record("31/02/2026", "Órgano Alfa", "31/02/2026 09:00"),
            synthetic_record("26-10-2026", "Órgano Beta", "26/10/2026 9:00"),
            synthetic_record("26/10/2026", "Órgano Beta", "26/10/2026 09:00"),
        ]

        data = aggregate_records(SOURCE_MANIFEST, records, FIXED_GENERATED_AT)

        self.assertEqual(data["summary"]["distinct_publication_dates"], 1)
        self.assertEqual(data["summary"]["deadlines_before_source_update_day"], 1)
        self.assertEqual(data["date_quality"]["publication_empty_count"], 1)
        self.assertEqual(data["date_quality"]["publication_invalid_count"], 2)
        self.assertEqual(data["date_quality"]["deadline_empty_count"], 1)
        self.assertEqual(data["date_quality"]["deadline_invalid_count"], 2)

    def test_missing_fields_produce_unavailable_indicators(self):
        data = aggregate_records(SOURCE_MANIFEST, [{"synthetic_only": "fixture"}], FIXED_GENERATED_AT)

        self.assertIsNone(data["summary"]["distinct_organizations"])
        self.assertIsNone(data["summary"]["distinct_publication_dates"])
        self.assertIsNone(data["summary"]["deadlines_before_source_update_day"])
        self.assertIsNone(data["top_organizations"])
        self.assertIsNone(data["activity_by_date"])
        self.assertFalse(data["field_completeness"][PUBLICATION_DATE_FIELD]["available"])

    def test_top_ten_ranking_is_descending_with_deterministic_ties(self):
        records = []
        for name, count in {
            "Órgano A": 12,
            "Órgano B": 11,
            "Órgano C": 10,
            "Órgano D": 9,
            "Órgano E": 8,
            "Órgano F": 7,
            "Órgano G": 6,
            "Órgano H": 5,
            "Órgano I": 4,
            "Órgano J": 3,
            "Órgano K": 2,
            "Órgano L": 1,
        }.items():
            records.extend(
                synthetic_record("26/10/2026", name, "28/10/2026 09:00")
                for _ in range(count)
            )
        records.extend(
            [
                synthetic_record("25/10/2026", "Tie Beta", "28/10/2026 09:00"),
                synthetic_record("25/10/2026", "Tie Alfa", "28/10/2026 09:00"),
            ]
        )

        data = aggregate_records(SOURCE_MANIFEST, records, FIXED_GENERATED_AT)

        self.assertEqual(len(data["top_organizations"]), 10)
        self.assertEqual(
            [row["organization"] for row in data["top_organizations"][:2]],
            ["Órgano A", "Órgano B"],
        )
        tie_data = aggregate_records(
            SOURCE_MANIFEST,
            [
                synthetic_record("26/10/2026", "Tie Beta", "28/10/2026 09:00"),
                synthetic_record("26/10/2026", "Tie Alfa", "28/10/2026 09:00"),
            ],
            FIXED_GENERATED_AT,
        )
        self.assertEqual(
            [row["organization"] for row in tie_data["top_organizations"]],
            ["Tie Alfa", "Tie Beta"],
        )

    def test_missing_source_date_makes_deadline_review_unavailable(self):
        manifest = dict(SOURCE_MANIFEST, source_updated_at=None)
        data = aggregate_records(
            manifest,
            [synthetic_record("26/10/2026", "Órgano Alfa", "25/10/2026 09:00")],
            FIXED_GENERATED_AT,
        )

        self.assertIsNone(data["summary"]["deadlines_before_source_update_day"])
        self.assertFalse(data["date_quality"]["deadline_review_available"])

    def test_output_is_aggregate_only_and_capture_integrity_is_checked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            capture = root / "capture"
            capture.mkdir()
            raw = json.dumps(
                [
                    synthetic_record(
                        "26/10/2026",
                        "Synthetic agency",
                        "27/10/2026 10:00",
                        {
                            "contratacion_objeto_contrato": "PRIVATE SYNTHETIC TITLE",
                            "contratacion_expediente": "SYNTHETIC-CASE-ID",
                            "friendlyUrl": "https://example.test/synthetic-case",
                        },
                    )
                ],
                ensure_ascii=False,
            ).encode("utf-8")
            (capture / "response.json").write_bytes(raw)
            manifest = dict(
                SOURCE_MANIFEST,
                extraction_status="valid_with_data",
                record_count=1,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
            (capture / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8"
            )
            output = root / "public" / "radar-summary.json"

            build_dashboard_data(
                root,
                output,
                generated_at=FIXED_GENERATED_AT,
            )
            public_data = json.loads(output.read_text(encoding="utf-8"))
            serialized = output.read_text(encoding="utf-8")

            self.assertEqual(public_data["summary"]["notice_count"], 1)
            self.assertNotIn("records", public_data)
            self.assertNotIn("contratacion_objeto_contrato", serialized)
            self.assertNotIn("contratacion_expediente", serialized)
            self.assertNotIn("friendlyUrl", serialized)
            self.assertNotIn("PRIVATE SYNTHETIC TITLE", serialized)
            self.assertNotIn("SYNTHETIC-CASE-ID", serialized)
            self.assertNotIn("example.test/synthetic-case", serialized)

    def test_repeated_builds_with_fixed_time_are_reproducible(self):
        records = [
            synthetic_record("26/10/2026", "Órgano Alfa", "27/10/2026 10:00")
        ]
        first = aggregate_records(SOURCE_MANIFEST, records, FIXED_GENERATED_AT)
        second = aggregate_records(SOURCE_MANIFEST, records, FIXED_GENERATED_AT)
        self.assertEqual(first, second)

    def test_no_valid_local_capture_is_an_explicit_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(DashboardDataError, "No hay una captura válida"):
                build_dashboard_data(Path(temp_dir), Path(temp_dir) / "summary.json")


if __name__ == "__main__":
    unittest.main()
