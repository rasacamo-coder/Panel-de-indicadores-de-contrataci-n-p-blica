import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from radar.catalog_source import (
    CATALOG_JSON_URL,
    CATALOG_RDF_URL,
    CatalogIngestionError,
    ingest_catalog,
)


SYNTHETIC_RDF = b"""<?xml version="1.0"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:dct="http://purl.org/dc/terms/">
  <dct:modified>2026-10-27T00:00:00</dct:modified>
</rdf:RDF>
"""
FIXED_NOW = datetime(2026, 10, 28, 2, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, body, content_type="application/json"):
        self.body = body
        self.headers = {"Content-Type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


class SequenceOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def synthetic_record(**overrides):
    record = {
        "synthetic_name": "Synthetic-only contract notice",
        "synthetic_date": "2026-10-27",
        "synthetic_amount": 25,
    }
    record.update(overrides)
    return record


class CatalogIngestionTests(unittest.TestCase):
    def run_ingestion(self, payload, rdf=SYNTHETIC_RDF, root=None, extra=()):
        opener = SequenceOpener(
            [FakeResponse(json_bytes(payload)), FakeResponse(rdf), *extra]
        )
        result = ingest_catalog(
            output_root=root,
            opener=opener,
            now=FIXED_NOW,
            timeout=7,
        )
        return result, opener

    def test_saves_one_synthetic_record_with_hash_and_field_types(self):
        payload = [synthetic_record()]
        body = json_bytes(payload)

        with tempfile.TemporaryDirectory() as temp_dir:
            result, opener = self.run_ingestion(payload, root=Path(temp_dir))

            self.assertEqual(result.status, "valid_with_data")
            self.assertEqual(result.record_count, 1)
            self.assertEqual(result.source_updated_at, "2026-10-27")
            self.assertEqual(result.freshness_status, "reciente")
            self.assertEqual((result.output_dir / "response.json").read_bytes(), body)
            manifest = json.loads(
                (result.output_dir / "manifest.json").read_text("utf-8")
            )
            self.assertEqual(manifest["source_url"], CATALOG_JSON_URL)
            self.assertEqual(manifest["downloaded_at_utc"], FIXED_NOW.isoformat())
            self.assertEqual(manifest["download_size_bytes"], len(body))
            self.assertEqual(manifest["sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(manifest["record_count"], 1)
            self.assertEqual(manifest["observed_fields"]["synthetic_amount"]["types"], {"integer": 1})
            self.assertNotEqual(
                manifest["downloaded_at_utc"][:10],
                manifest["source_updated_at"],
            )
            self.assertEqual(
                [request.full_url for request, _ in opener.requests],
                [CATALOG_JSON_URL, CATALOG_RDF_URL],
            )
            self.assertTrue(all(timeout == 7 for _, timeout in opener.requests))

    def test_valid_empty_list_is_saved_as_valid_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result, _ = self.run_ingestion([], root=Path(temp_dir))

            self.assertEqual(result.status, "valid_empty")
            self.assertEqual(result.record_count, 0)
            self.assertEqual(json.loads((result.output_dir / "response.json").read_text()), [])
            self.assertEqual(
                json.loads((result.output_dir / "manifest.json").read_text())[
                    "extraction_status"
                ],
                "valid_empty",
            )

    def test_saves_multiple_objects_without_removing_records(self):
        payload = [synthetic_record(), synthetic_record(synthetic_extra=True)]

        with tempfile.TemporaryDirectory() as temp_dir:
            result, _ = self.run_ingestion(payload, root=Path(temp_dir))
            stored = json.loads((result.output_dir / "response.json").read_bytes())

            self.assertEqual(len(stored), 2)
            warnings = {
                warning["code"] for warning in result.warnings
            }
            self.assertIn("field_presence_varies", warnings)

    def test_invalid_json_and_wrong_root_write_failure_manifests_only(self):
        cases = [
            (b"{malformed", "invalid_json"),
            (json_bytes({"not": "a list"}), "download_or_structure"),
            (json_bytes([synthetic_record(), "synthetic non-object"]), "download_or_structure"),
        ]
        for body, expected_failure in cases:
            with self.subTest(expected_failure=expected_failure, body=body[:10]):
                with tempfile.TemporaryDirectory() as temp_dir:
                    opener = SequenceOpener([FakeResponse(body)])
                    with self.assertRaises(CatalogIngestionError):
                        ingest_catalog(
                            output_root=Path(temp_dir),
                            opener=opener,
                            now=FIXED_NOW,
                        )

                    self.assertFalse(
                        any(
                            path.is_dir() and path.name != "failures"
                            for path in Path(temp_dir).iterdir()
                        )
                    )
                    failure_manifests = list(
                        (Path(temp_dir) / "failures").glob("*/manifest.json")
                    )
                    self.assertEqual(len(failure_manifests), 1)
                    manifest = json.loads(failure_manifests[0].read_text())
                    self.assertEqual(manifest["extraction_status"], "fallida")
                    self.assertEqual(manifest["failure_kind"], expected_failure)
                    self.assertEqual(manifest["download_size_bytes"], len(body))
                    self.assertEqual(
                        manifest["sha256"], hashlib.sha256(body).hexdigest()
                    )

    def test_http_timeout_and_network_errors_are_distinguished(self):
        scenarios = [
            (
                HTTPError(CATALOG_JSON_URL, 503, "Unavailable", {}, None),
                r"HTTP \(503\)",
            ),
            (TimeoutError(), "tiempo de espera"),
            (URLError("synthetic network failure"), "No se pudo conectar"),
        ]
        for failure, expected_message in scenarios:
            with self.subTest(expected_message=expected_message):
                with tempfile.TemporaryDirectory() as temp_dir:
                    opener = SequenceOpener([failure])
                    with self.assertRaisesRegex(
                        CatalogIngestionError, expected_message
                    ):
                        ingest_catalog(
                            output_root=Path(temp_dir),
                            opener=opener,
                            now=FIXED_NOW,
                        )

                    manifest = json.loads(
                        next(
                            (Path(temp_dir) / "failures").glob("*/manifest.json")
                        ).read_text()
                    )
                    self.assertEqual(manifest["extraction_status"], "fallida")

    def test_rdf_failure_or_missing_date_keeps_valid_download(self):
        invalid_metadata_cases = [
            (OSError("synthetic RDF unavailable"), "no date"),
            (FakeResponse(b"<rdf:RDF>"), "no date"),
            (
                FakeResponse(
                    b'<rdf:RDF xmlns:dct="http://purl.org/dc/terms/"><dct:modified>bad</dct:modified></rdf:RDF>'
                ),
                "no date",
            ),
        ]
        for rdf_response, _ in invalid_metadata_cases:
            with self.subTest(rdf_response=type(rdf_response).__name__):
                with tempfile.TemporaryDirectory() as temp_dir:
                    opener = SequenceOpener(
                        [FakeResponse(json_bytes([synthetic_record()])), rdf_response]
                    )
                    if isinstance(rdf_response, BaseException):
                        original_call = opener

                        def failing_metadata_opener(request, timeout):
                            if request.full_url == CATALOG_RDF_URL:
                                raise OSError("synthetic RDF unavailable")
                            return original_call(request, timeout)

                        opener_callable = failing_metadata_opener
                    else:
                        opener_callable = opener

                    result = ingest_catalog(
                        output_root=Path(temp_dir),
                        opener=opener_callable,
                        now=FIXED_NOW,
                    )
                    self.assertEqual(result.status, "valid_with_data")
                    self.assertEqual(result.freshness_status, "no_verificable")
                    self.assertIsNone(result.source_updated_at)
                    self.assertIn(
                        "source_metadata_unavailable",
                        {warning["code"] for warning in result.warnings},
                    )

    def test_old_source_date_warns_using_project_three_day_threshold(self):
        rdf = b"""<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
        xmlns:dct="http://purl.org/dc/terms/">
        <dct:modified>2026-10-20T00:00:00</dct:modified></rdf:RDF>"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result, _ = self.run_ingestion(
                [synthetic_record()], rdf=rdf, root=Path(temp_dir)
            )

            self.assertEqual(result.freshness_status, "antiguo")
            stale_warning = next(
                warning
                for warning in result.warnings
                if warning["code"] == "source_data_stale"
            )
            self.assertIn("3 días", stale_warning["message"])

    def test_schema_name_and_type_changes_are_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.run_ingestion([synthetic_record()], root=root)
            result, _ = self.run_ingestion(
                [
                    synthetic_record(
                        synthetic_name=None,
                        synthetic_new_field="new",
                        synthetic_amount="changed type",
                    )
                ],
                root=root,
            )

            warnings = {
                (warning["code"], warning["field"])
                for warning in result.warnings
            }
            self.assertIn(("field_added", "synthetic_new_field"), warnings)
            self.assertIn(("field_type_changed", "synthetic_amount"), warnings)
            self.assertIn(("field_type_changed", "synthetic_name"), warnings)

    def test_identical_snapshot_warns_without_deduplicating_records(self):
        payload = [synthetic_record(), synthetic_record()]
        with tempfile.TemporaryDirectory() as temp_dir:
            first, _ = self.run_ingestion(payload, root=Path(temp_dir))
            different, _ = self.run_ingestion(
                [synthetic_record(synthetic_amount=55)], root=Path(temp_dir)
            )
            repeated, _ = self.run_ingestion(payload, root=Path(temp_dir))

            self.assertNotEqual(first.snapshot_sha256, different.snapshot_sha256)
            self.assertEqual(first.snapshot_sha256, repeated.snapshot_sha256)
            self.assertEqual(first.record_count, 2)
            self.assertEqual(repeated.record_count, 2)
            self.assertIn(
                "identical_snapshot",
                {warning["code"] for warning in repeated.warnings},
            )
            valid_runs = [
                path
                for path in Path(temp_dir).iterdir()
                if path.is_dir() and path.name != "failures"
            ]
            self.assertEqual(len(valid_runs), 3)

    def test_invalid_response_preserves_previous_valid_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous, _ = self.run_ingestion([synthetic_record()], root=root)
            saved_response = (previous.output_dir / "response.json").read_bytes()
            invalid_opener = SequenceOpener([FakeResponse(b"not-json")])

            with self.assertRaises(CatalogIngestionError):
                ingest_catalog(
                    output_root=root,
                    opener=invalid_opener,
                    now=FIXED_NOW,
                )

            self.assertTrue(previous.output_dir.exists())
            self.assertEqual(
                (previous.output_dir / "response.json").read_bytes(),
                saved_response,
            )
            valid_runs = [
                path
                for path in root.iterdir()
                if path.is_dir() and path.name != "failures"
            ]
            self.assertEqual(len(valid_runs), 1)

    def test_failed_write_does_not_replace_previous_valid_execution(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            previous, _ = self.run_ingestion([synthetic_record()], root=root)
            previous_response = (previous.output_dir / "response.json").read_bytes()
            real_write_bytes = Path.write_bytes

            def failing_write_bytes(path, data):
                if path.name == "response.json":
                    raise OSError("synthetic disk failure")
                return real_write_bytes(path, data)

            with patch.object(Path, "write_bytes", failing_write_bytes):
                with self.assertRaisesRegex(
                    CatalogIngestionError, "No se pudo guardar"
                ):
                    self.run_ingestion([synthetic_record(synthetic_amount=55)], root=root)

            self.assertEqual(
                (previous.output_dir / "response.json").read_bytes(),
                previous_response,
            )
            valid_runs = [
                path
                for path in root.iterdir()
                if path.is_dir() and path.name != "failures"
            ]
            self.assertEqual(len(valid_runs), 1)


if __name__ == "__main__":
    unittest.main()
