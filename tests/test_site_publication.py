import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SITE_DIRECTORY = REPOSITORY_ROOT / "site"
PUBLIC_SITE_FILES = {
    "index.html",
    "styles.css",
    "staticwebapp.config.json",
    "radar.html",
    "radar.css",
    "radar.js",
    "data/radar-summary.json",
}


class StaticSitePublicationTests(unittest.TestCase):
    def test_site_contains_only_the_allowed_public_files(self):
        entries = list(SITE_DIRECTORY.rglob("*"))
        files = {entry.relative_to(SITE_DIRECTORY).as_posix() for entry in entries if entry.is_file()}
        self.assertTrue(all(entry.is_file() or entry.is_dir() for entry in entries))
        self.assertEqual(files, PUBLIC_SITE_FILES)

    def test_static_web_app_configuration_is_valid_json(self):
        config_path = SITE_DIRECTORY / "staticwebapp.config.json"

        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)

        self.assertIsInstance(config, dict)

    def test_index_links_to_the_site_stylesheet(self):
        html = (SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="styles.css"', html)
        self.assertTrue((SITE_DIRECTORY / "styles.css").is_file())

    def test_cv_links_to_radar_and_dashboard_assets_exist(self):
        html = (SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="radar.html"', html)
        dashboard = (SITE_DIRECTORY / "radar.html").read_text(encoding="utf-8")
        self.assertIn('href="radar.css"', dashboard)
        self.assertIn('src="radar.js"', dashboard)
        self.assertTrue((SITE_DIRECTORY / "data" / "radar-summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
