import json
import unittest
from pathlib import Path
from xml.etree import ElementTree


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PUBLIC_DIRECTORY = REPOSITORY_ROOT / "public"


class PublicArtifactTests(unittest.TestCase):
    def test_dashboard_links_resolve_to_published_assets(self):
        html = (PUBLIC_DIRECTORY / "index.html").read_text(encoding="utf-8")

        self.assertIn('href="radar-standalone.css"', html)
        self.assertIn('href="radar.css"', html)
        self.assertIn('src="radar-language.js"', html)
        self.assertIn('src="radar.js"', html)
        self.assertTrue((PUBLIC_DIRECTORY / "radar-standalone.css").is_file())
        self.assertTrue((PUBLIC_DIRECTORY / "radar.css").is_file())
        self.assertTrue((PUBLIC_DIRECTORY / "radar-language.js").is_file())
        self.assertTrue((PUBLIC_DIRECTORY / "radar.js").is_file())
        self.assertTrue(
            (PUBLIC_DIRECTORY / "data" / "radar-summary.json").is_file()
        )

    def test_public_summary_is_aggregated_json(self):
        summary_path = PUBLIC_DIRECTORY / "data" / "radar-summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        self.assertIsInstance(summary.get("summary"), dict)
        self.assertNotIn("records", summary)

    def test_portfolio_links_use_custom_domain(self):
        html = (PUBLIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="https://www.castillomontoya.com/proyectos.html"', html)
        self.assertNotIn("red-ocean-083530310.2.azurestaticapps.net", html)

    def test_favicon_is_published_and_linked(self):
        html = (PUBLIC_DIRECTORY / "index.html").read_text(encoding="utf-8")
        self.assertIn('<link rel="icon" type="image/svg+xml" href="favicon.svg">', html)
        icon = PUBLIC_DIRECTORY / "favicon.svg"
        self.assertEqual(ElementTree.parse(icon).getroot().tag, "{http://www.w3.org/2000/svg}svg")


if __name__ == "__main__":
    unittest.main()
