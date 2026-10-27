import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from http.client import HTTPMessage, IncompleteRead
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from radar.extract_sample import (
    SampleExtractionError,
    build_request_url,
    download_sample,
    main,
    validate_api_envelope,
    validate_record_objects,
)


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


class FailingReadResponse(FakeResponse):
    def read(self):
        raise IncompleteRead(b"partial response")


def synthetic_response_body(items):
    payload = {
        "totalItems": len(items),
        "totalPages": 1 if items else 0,
        "currentPage": 1,
        "itemsOfPage": len(items),
        "items": items,
    }
    return json.dumps(payload).encode("utf-8")


def download_with_response(body, output_dir, content_type="application/json"):
    with patch(
        "radar.extract_sample.urlopen",
        return_value=FakeResponse(body, content_type),
    ):
        return download_sample(
            date(2026, 10, 20),
            date(2026, 10, 27),
            limit=1,
            output_dir=output_dir,
        )


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


class ResponseValidationTests(unittest.TestCase):
    def test_accepts_envelope_without_assuming_record_fields(self):
        synthetic_response = {
            "totalItems": 1,
            "totalPages": 1,
            "currentPage": 1,
            "itemsOfPage": 1,
            "items": [{"synthetic_unknown_field": "synthetic-test-only"}],
        }

        self.assertEqual(
            validate_api_envelope(synthetic_response, 1),
            synthetic_response,
        )
        validate_record_objects(synthetic_response["items"])

    def test_rejects_invalid_top_level_envelope(self):
        with self.assertRaisesRegex(SampleExtractionError, "formato JSON"):
            validate_api_envelope([], 1)

        with self.assertRaisesRegex(SampleExtractionError, "paginación"):
            validate_api_envelope({"items": []}, 1)

    def test_rejects_non_list_items_and_excess_rows(self):
        with self.assertRaisesRegex(SampleExtractionError, "lista de resultados"):
            validate_api_envelope(
                {
                    "totalItems": 1,
                    "totalPages": 1,
                    "currentPage": 1,
                    "itemsOfPage": 1,
                    "items": {},
                },
                1,
            )

        with self.assertRaisesRegex(SampleExtractionError, "más resultados"):
            validate_api_envelope(
                {
                    "totalItems": 2,
                    "totalPages": 1,
                    "currentPage": 1,
                    "itemsOfPage": 2,
                    "items": [{}, {}],
                },
                1,
            )

    def test_rejects_inconsistent_empty_result_count(self):
        with self.assertRaisesRegex(SampleExtractionError, "no coincide"):
            validate_api_envelope(
                {
                    "totalItems": 1,
                    "totalPages": 1,
                    "currentPage": 1,
                    "itemsOfPage": 1,
                    "items": [],
                },
                1,
            )

        with self.assertRaisesRegex(
            SampleExtractionError, "metadatos de paginación"
        ):
            validate_api_envelope(
                {
                    "totalItems": "0",
                    "totalPages": 0,
                    "currentPage": 1,
                    "itemsOfPage": 0,
                    "items": [],
                },
                1,
            )

    def test_record_container_validation_does_not_invent_domain_fields(self):
        validate_record_objects([{}, {"another_unknown_field": 1}])

        with self.assertRaisesRegex(SampleExtractionError, "objeto JSON"):
            validate_record_objects([{"synthetic": True}, None])


class DownloadSampleTests(unittest.TestCase):
    def test_saves_valid_nonempty_response_and_manifest(self):
        body = synthetic_response_body([{"id": "synthetic-test-only"}])

        with tempfile.TemporaryDirectory() as temp_dir:
            result = download_with_response(body, Path(temp_dir))

            self.assertEqual(result.returned_rows, 1)
            self.assertFalse(result.is_empty)
            self.assertEqual(
                (result.output_dir / "response.json").read_bytes(), body
            )
            manifest = json.loads(
                (result.output_dir / "manifest.json").read_text("utf-8")
            )
            self.assertEqual(manifest["result_status"], "non_empty")
            self.assertEqual(manifest["envelope_validation"], "passed")
            self.assertEqual(
                manifest["record_object_validation"], "passed"
            )
            self.assertEqual(
                manifest["domain_schema_validation"], "not performed"
            )

    def test_valid_empty_response_is_saved_without_replacing_prior_run(self):
        valid_body = synthetic_response_body([{"id": "synthetic-test-only"}])
        empty_body = synthetic_response_body([])

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prior_result = download_with_response(valid_body, output_dir)
            prior_response = (prior_result.output_dir / "response.json").read_bytes()

            empty_result = download_with_response(empty_body, output_dir)

            self.assertTrue(empty_result.is_empty)
            self.assertEqual(empty_result.returned_rows, 0)
            empty_manifest = json.loads(
                (empty_result.output_dir / "manifest.json").read_text("utf-8")
            )
            self.assertEqual(empty_manifest["result_status"], "empty")
            self.assertTrue(prior_result.output_dir.exists())
            self.assertEqual(
                (prior_result.output_dir / "response.json").read_bytes(),
                prior_response,
            )
            self.assertEqual(len(list(output_dir.iterdir())), 2)

    def test_http_error_is_reported_without_replacing_prior_run(self):
        valid_body = synthetic_response_body([{"id": "synthetic-test-only"}])
        http_error = HTTPError(
            "https://api.euskadi.eus/",
            503,
            "Service Unavailable",
            HTTPMessage(),
            None,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prior_result = download_with_response(valid_body, output_dir)
            prior_response = (prior_result.output_dir / "response.json").read_bytes()
            with patch("radar.extract_sample.urlopen", side_effect=http_error):
                with self.assertRaisesRegex(
                    SampleExtractionError, "error HTTP \\(503\\)"
                ):
                    download_sample(
                        date(2026, 10, 20),
                        date(2026, 10, 27),
                        limit=1,
                        output_dir=output_dir,
                    )

            self.assertEqual(
                (prior_result.output_dir / "response.json").read_bytes(),
                prior_response,
            )
            self.assertEqual(len(list(output_dir.iterdir())), 1)

    def test_timeout_and_network_errors_have_distinct_messages(self):
        with patch(
            "radar.extract_sample.urlopen", side_effect=TimeoutError
        ):
            with self.assertRaisesRegex(
                SampleExtractionError, "tiempo de espera"
            ):
                download_sample(
                    date(2026, 10, 20),
                    date(2026, 10, 27),
                    output_dir=Path("unused"),
                )

    def test_incomplete_http_response_has_a_clear_error(self):
        with patch(
            "radar.extract_sample.urlopen",
            return_value=FailingReadResponse(b""),
        ):
            with self.assertRaisesRegex(
                SampleExtractionError, "llegó incompleta"
            ):
                download_sample(
                    date(2026, 10, 20),
                    date(2026, 10, 27),
                    output_dir=Path("unused"),
                )

        with patch(
            "radar.extract_sample.urlopen",
            side_effect=URLError("synthetic offline failure"),
        ):
            with self.assertRaisesRegex(
                SampleExtractionError, "No se pudo conectar"
            ):
                download_sample(
                    date(2026, 10, 20),
                    date(2026, 10, 27),
                    output_dir=Path("unused"),
                )

    def test_command_line_prints_friendly_error_without_traceback(self):
        error_output = io.StringIO()
        with patch(
            "radar.extract_sample.urlopen",
            side_effect=URLError("synthetic offline failure"),
        ):
            with patch.object(
                sys,
                "argv",
                [
                    "extract_sample.py",
                    "--publication-date-gt",
                    "2026-10-20",
                    "--publication-date-lt",
                    "2026-10-27",
                ],
            ):
                with redirect_stderr(error_output):
                    with self.assertRaises(SystemExit) as exit_context:
                        main()

        self.assertEqual(exit_context.exception.code, 1)
        self.assertIn("Error: No se pudo conectar", error_output.getvalue())
        self.assertNotIn("Traceback", error_output.getvalue())

    def test_rejects_malformed_json_and_wrong_content_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(
                SampleExtractionError, "JSON inválido"
            ):
                download_with_response(b"{not-json", Path(temp_dir))

            with self.assertRaisesRegex(
                SampleExtractionError, "no devolvió JSON"
            ):
                download_with_response(
                    b"<html>synthetic error</html>",
                    Path(temp_dir),
                    content_type="text/html; charset=utf-8",
                )

            self.assertEqual(list(Path(temp_dir).iterdir()), [])

    def test_save_failure_cleans_temporary_files_and_preserves_prior_run(self):
        valid_body = synthetic_response_body([{"id": "synthetic-test-only"}])

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prior_result = download_with_response(valid_body, output_dir)
            prior_response = (prior_result.output_dir / "response.json").read_bytes()

            with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(
                    SampleExtractionError, "No se pudo guardar"
                ):
                    download_with_response(valid_body, output_dir)

            self.assertEqual(
                (prior_result.output_dir / "response.json").read_bytes(),
                prior_response,
            )
            self.assertEqual(list(output_dir.iterdir()), [prior_result.output_dir])


if __name__ == "__main__":
    unittest.main()
