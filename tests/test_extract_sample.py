import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from radar.extract_sample import (
    build_request_url,
    download_sample,
    validate_response,
)


class FakeResponse:
    headers = {"Content-Type": "application/json"}

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self):
        return self.body


def synthetic_response_body(items):
    payload = {
        "totalItems": len(items),
        "totalPages": 1 if items else 0,
        "currentPage": 1,
        "itemsOfPage": len(items),
        "items": items,
    }
    return json.dumps(payload).encode("utf-8")


class BuildRequestUrlTests(unittest.TestCase):
    def test_builds_small_fixed_date_query(self):
        url = build_request_url(
            date(2026, 10, 20),
            date(2026, 10, 27),
            limit=3,
        )

        parsed_url = urlparse(url)
        query = parse_qs(parsed_url.query)

        self.assertEqual(
            parsed_url.path, "/procurements/contracting-notices"
        )
        self.assertEqual(query["publication-date.gt"], ["2026-10-20"])
        self.assertEqual(query["publication-date.lt"], ["2026-10-27"])
        self.assertEqual(query["currentPage"], ["1"])
        self.assertEqual(query["itemsOfPage"], ["3"])
        self.assertEqual(query["orderBy"], ["firstPublicationDate"])
        self.assertEqual(query["orderType"], ["ASC"])
        self.assertEqual(query["lang"], ["SPANISH"])

    def test_rejects_reversed_or_equal_date_bounds(self):
        with self.assertRaises(ValueError):
            build_request_url(date(2026, 10, 27), date(2026, 10, 27))

        with self.assertRaises(ValueError):
            build_request_url(date(2026, 10, 28), date(2026, 10, 27))

    def test_rejects_limit_outside_documented_range(self):
        with self.assertRaises(ValueError):
            build_request_url(date(2026, 10, 20), date(2026, 10, 27), 0)

        with self.assertRaises(ValueError):
            build_request_url(date(2026, 10, 20), date(2026, 10, 27), 51)


class ValidateResponseTests(unittest.TestCase):
    def test_accepts_a_synthetic_nonempty_api_envelope(self):
        synthetic_response = {
            "totalItems": 1,
            "totalPages": 1,
            "currentPage": 1,
            "itemsOfPage": 1,
            "items": [{"id": "synthetic-test-only"}],
        }

        self.assertEqual(validate_response(synthetic_response, 1), synthetic_response)

    def test_rejects_empty_response_without_saving_it(self):
        empty_response = {
            "totalItems": 0,
            "totalPages": 0,
            "currentPage": 1,
            "itemsOfPage": 1,
            "items": [],
        }

        with self.assertRaisesRegex(ValueError, "no devolvió registros"):
            validate_response(empty_response, 1)

    def test_rejects_missing_pagination_metadata(self):
        with self.assertRaisesRegex(ValueError, "Faltan propiedades"):
            validate_response({"items": [{"id": "synthetic-test-only"}]}, 1)

    def test_rejects_more_rows_than_requested(self):
        oversized_response = {
            "totalItems": 2,
            "totalPages": 1,
            "currentPage": 1,
            "itemsOfPage": 2,
            "items": [
                {"id": "synthetic-test-1"},
                {"id": "synthetic-test-2"},
            ],
        }

        with self.assertRaisesRegex(ValueError, "más registros"):
            validate_response(oversized_response, 1)


class DownloadSampleTests(unittest.TestCase):
    def test_saves_valid_response_and_manifest_in_a_new_run_folder(self):
        body = synthetic_response_body([{"id": "synthetic-test-only"}])

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "radar.extract_sample.urlopen",
                return_value=FakeResponse(body),
            ):
                run_dir = download_sample(
                    date(2026, 10, 20),
                    date(2026, 10, 27),
                    limit=1,
                    output_dir=Path(temp_dir),
                )

            self.assertEqual((run_dir / "response.json").read_bytes(), body)
            manifest = json.loads((run_dir / "manifest.json").read_text("utf-8"))
            self.assertEqual(manifest["returned_rows"], 1)
            self.assertEqual(manifest["envelope_validation"], "passed")
            self.assertEqual(len(list(Path(temp_dir).iterdir())), 1)

    def test_empty_response_does_not_replace_a_previous_valid_run(self):
        valid_body = synthetic_response_body([{"id": "synthetic-test-only"}])
        empty_body = synthetic_response_body([])

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            with patch(
                "radar.extract_sample.urlopen",
                return_value=FakeResponse(valid_body),
            ):
                valid_run_dir = download_sample(
                    date(2026, 10, 20),
                    date(2026, 10, 27),
                    limit=1,
                    output_dir=output_dir,
                )

            valid_response_path = valid_run_dir / "response.json"
            with patch(
                "radar.extract_sample.urlopen",
                return_value=FakeResponse(empty_body),
            ):
                with self.assertRaisesRegex(ValueError, "no devolvió registros"):
                    download_sample(
                        date(2026, 10, 20),
                        date(2026, 10, 27),
                        limit=1,
                        output_dir=output_dir,
                    )

            self.assertEqual(valid_response_path.read_bytes(), valid_body)
            self.assertEqual(len(list(output_dir.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
