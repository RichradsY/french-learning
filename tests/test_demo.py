import json
import re
import tempfile
import unittest
from pathlib import Path

from demo.build import build


class LiveDemoTest(unittest.TestCase):
    def test_build_contains_relative_static_site_and_safe_sample_data(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            build(output)

            expected = {
                ".nojekyll",
                "app.js",
                "demo-api.js",
                "demo-data.json",
                "demo-runtime.js",
                "demo.css",
                "favicon.svg",
                "index.html",
                "styles.css",
            }
            self.assertEqual(expected, {path.name for path in output.iterdir()})

            html = (output / "index.html").read_text(encoding="utf-8")
            self.assertIn("Live Demo", html)
            self.assertIn('href="styles.css"', html)
            self.assertIn('src="demo-api.js"', html)
            self.assertNotIn('href="/styles.css"', html)
            self.assertNotIn('src="/app.js"', html)

            data_text = (output / "demo-data.json").read_text(encoding="utf-8")
            data = json.loads(data_text)
            self.assertEqual(
                {"daily", "reading", "writing", "history", "mistakes", "grammar", "conjugations", "vocabulary"},
                set(data),
            )
            self.assertEqual("completed", data["daily"]["status"])
            self.assertEqual("completed", data["reading"]["status"])
            self.assertEqual("completed", data["writing"]["status"])
            self.assertNotRegex(data_text, r"/Users/|/home/|BEGIN .*PRIVATE KEY")
            self.assertNotRegex(data_text, r"(?:gh[opusr]_|sk-|AIza)[A-Za-z0-9_-]{16,}")
            self.assertIsNone(re.search(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", data_text))

    def test_demo_adapter_covers_every_read_only_navigation_endpoint(self):
        adapter = (Path(__file__).parent.parent / "demo" / "demo-api.js").read_text(
            encoding="utf-8"
        )
        for endpoint in (
            "/api/today",
            "/api/tasks/reading",
            "/api/tasks/writing",
            "/api/history",
            "/api/mistakes",
            "/api/grammar",
            "/api/conjugations",
            "/api/vocabulary",
        ):
            self.assertIn(endpoint, adapter)
        self.assertIn("Cette action est désactivée dans la démonstration", adapter)


if __name__ == "__main__":
    unittest.main()
