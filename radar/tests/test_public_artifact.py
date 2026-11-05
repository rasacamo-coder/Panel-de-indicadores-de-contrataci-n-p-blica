import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIRECTORY = REPOSITORY_ROOT / "public"


class PublicArtifactTests(unittest.TestCase):
    def test_dashboard_links_resolve_to_published_assets(self):
        html = (PUBLIC_DIRECTORY / "index.html").read_text(encoding="utf-8")

        self.assertIn('href="radar-standalone.css"', html)
        self.assertIn('href="radar.css"', html)
        self.assertIn('src="radar.js"', html)
        self.assertTrue((PUBLIC_DIRECTORY / "radar-standalone.css").is_file())
        self.assertTrue((PUBLIC_DIRECTORY / "radar.css").is_file())
        self.assertTrue((PUBLIC_DIRECTORY / "radar.js").is_file())
        self.assertTrue(
            (PUBLIC_DIRECTORY / "data" / "radar-summary.json").is_file()
        )

    def test_public_summary_is_aggregated_json(self):
        summary_path = PUBLIC_DIRECTORY / "data" / "radar-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertIsInstance(summary.get("summary"), dict)
        self.assertNotIn("records", summary)


if __name__ == "__main__":
    unittest.main()
