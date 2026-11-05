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
    validate_records,
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


def valid_synthetic_record():
    return {
        "_links": {},
        "budgetWithoutVAT": 123.45,
        "code": "SYNTHETIC-CODE",
        "contractProcedureStatus": {},
        "contractProcedureType": {},
        "contractType": {},
        "contractingAuthority": {},
        "deadlineDate": "synthetic-date-time-format-not-validated",
        "entity": {},
        "financedEuropeanFunds": False,
        "firstPublicationDate": "2026-10-20",
        "id": 123,
        "lastPublicationDate": "2026-10-21",
        "mainEntityOfPage": "https://example.invalid/synthetic",
        "minorContract": False,
        "name": "Synthetic subject",
        "numberBidders": 2,
        "object": "Synthetic object",
        "openingDates": ["synthetic-opening-date"],
        "recoveryPlan": False,
        "sara": True,
        "subjectAppeal": False,
    }


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

        secret_marker = "SYNTHETIC_PRIVATE_SENTINEL"
        with self.assertRaisesRegex(
            SampleExtractionError, "registro 2.*objeto JSON"
        ) as error_context:
            validate_record_objects([{"synthetic": True}, secret_marker])

        self.assertNotIn(secret_marker, str(error_context.exception))

    def test_preliminary_record_validator_accepts_synthetic_documented_types(self):
        report = validate_records([valid_synthetic_record()])

        self.assertTrue(report.is_valid)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])
        self.assertEqual(report.status, "passed")

    def test_preliminary_type_mismatch_is_a_warning_not_a_blocking_error(self):
        report = validate_records([{"id": "synthetic-wrong-type"}])

        self.assertTrue(report.is_valid)
        self.assertIn("unexpected_type", {issue.code for issue in report.warnings})
        self.assertEqual(report.errors, [])
        self.assertEqual(report.status, "passed_with_warnings")

    def test_missing_null_unknown_and_object_name_discrepancy_are_warnings(self):
        report = validate_records(
            [
                {
                    "object": "synthetic object",
                    "id": None,
                    "futureSyntheticField": "not real data",
                }
            ]
        )
        warning_codes = {issue.code for issue in report.warnings}

        self.assertTrue(report.is_valid)
        self.assertIn("field_missing", warning_codes)
        self.assertIn("field_null", warning_codes)
        self.assertIn("unknown_field", warning_codes)
        self.assertIn("object_name_discrepancy", warning_codes)
        self.assertEqual(report.errors, [])

    def test_invalid_documented_publication_date_is_a_blocking_error(self):
        record = valid_synthetic_record()
        record["firstPublicationDate"] = "2026-02-30"

        report = validate_records([record])

        self.assertFalse(report.is_valid)
        self.assertEqual(report.status, "failed")
        self.assertIn(
            "invalid_date_format", {issue.code for issue in report.errors}
        )

    def test_non_text_documented_publication_date_is_a_blocking_error(self):
        record = valid_synthetic_record()
        record["lastPublicationDate"] = 20261021

        report = validate_records([record])

        self.assertFalse(report.is_valid)
        self.assertIn(
            "unexpected_documented_type",
            {issue.code for issue in report.errors},
        )

    def test_candidate_identifier_collisions_are_reported_not_removed(self):
        first = valid_synthetic_record()
        second = valid_synthetic_record()

        report = validate_records([first, second])

        collision_issues = [
            issue
            for issue in report.warnings
            if issue.code == "possible_identifier_collision_record"
        ]
        self.assertEqual(len(collision_issues), 4)
        self.assertEqual(
            {issue.record_index for issue in collision_issues}, {1, 2}
        )
        self.assertEqual(report.errors, [])

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
                manifest["domain_schema_validation"],
                "passed_with_warnings",
            )
            self.assertEqual(
                manifest["record_validation"]["status"],
                "passed_with_warnings",
            )
            self.assertGreater(
                len(manifest["record_validation"]["warnings"]), 0
            )

    def test_invalid_record_does_not_save_or_replace_prior_run(self):
        valid_body = synthetic_response_body([valid_synthetic_record()])
        secret_marker = "SYNTHETIC_PRIVATE_SENTINEL"
        invalid_body = synthetic_response_body(
            [valid_synthetic_record(), secret_marker]
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            prior_result = download_with_response(valid_body, output_dir)
            prior_response = (prior_result.output_dir / "response.json").read_bytes()

            with patch(
                "radar.extract_sample.urlopen",
                return_value=FakeResponse(invalid_body),
            ):
                with self.assertRaisesRegex(
                    SampleExtractionError,
                    "registro 2.*objeto JSON",
                ) as error_context:
                    download_sample(
                        date(2026, 10, 20),
                        date(2026, 10, 27),
                        limit=2,
                        output_dir=output_dir,
                    )

            self.assertNotIn(secret_marker, str(error_context.exception))
            self.assertEqual(
                (prior_result.output_dir / "response.json").read_bytes(),
                prior_response,
            )
            self.assertEqual(list(output_dir.iterdir()), [prior_result.output_dir])

    def test_cli_reports_validation_field_and_error_without_record_values(self):
        record = valid_synthetic_record()
        record["firstPublicationDate"] = "SYNTHETIC_INVALID_DATE"
        body = synthetic_response_body([record])
        error_output = io.StringIO()

        with patch(
            "radar.extract_sample.urlopen",
            return_value=FakeResponse(body),
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

        message = error_output.getvalue()
        self.assertEqual(exit_context.exception.code, 1)
        self.assertIn("registro 1", message)
        self.assertIn("campo 'firstPublicationDate'", message)
        self.assertIn("invalid_date_format", message)
        self.assertIn("no se guardó la muestra", message)
        self.assertNotIn("SYNTHETIC_INVALID_DATE", message)
        self.assertNotIn("SYNTHETIC-CODE", message)
        self.assertNotIn("Traceback", message)

    def test_cli_reports_non_object_record_index_without_revealing_value(self):
        secret_marker = "SYNTHETIC_PRIVATE_SENTINEL"
        body = synthetic_response_body(
            [valid_synthetic_record(), secret_marker]
        )
        error_output = io.StringIO()

        with patch(
            "radar.extract_sample.urlopen",
            return_value=FakeResponse(body),
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

        message = error_output.getvalue()
        self.assertEqual(exit_context.exception.code, 1)
        self.assertIn("registro 2", message)
        self.assertIn("objeto JSON", message)
        self.assertNotIn(secret_marker, message)
        self.assertNotIn("Traceback", message)

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
