import json
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SITE_DIRECTORY = REPOSITORY_ROOT / "site"
PUBLIC_SITE_FILES = {
    "index.html",
    "styles.css",
    "staticwebapp.config.json",
}


class StaticSitePublicationTests(unittest.TestCase):
    def test_site_contains_only_the_allowed_public_files(self):
        entries = list(SITE_DIRECTORY.iterdir())
        self.assertTrue(all(entry.is_file() for entry in entries))
        self.assertEqual({entry.name for entry in entries}, PUBLIC_SITE_FILES)

    def test_static_web_app_configuration_is_valid_json(self):
        config_path = SITE_DIRECTORY / "staticwebapp.config.json"

        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)

        self.assertIsInstance(config, dict)

    def test_index_links_to_the_site_stylesheet(self):
        html = (SITE_DIRECTORY / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="styles.css"', html)
        self.assertTrue((SITE_DIRECTORY / "styles.css").is_file())


if __name__ == "__main__":
    unittest.main()
