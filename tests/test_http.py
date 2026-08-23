import json
import tempfile
import threading
import unittest
from datetime import date, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from french_learning.web import create_server


class HttpApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.server = create_server("127.0.0.1", 0, Path(cls.temp.name) / "api.db")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def get_json(self, path):
        with urlopen(self.base + path, timeout=3) as response:
            return response.status, json.load(response)

    def post_json(self, path, body):
        request = Request(self.base + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=3) as response:
            return response.status, json.load(response)

    def test_health_and_home_are_served(self):
        status, health = self.get_json("/api/health")
        self.assertEqual(200, status)
        self.assertEqual("ok", health["status"])
        with urlopen(self.base + "/", timeout=3) as response:
            html = response.read().decode()
        self.assertIn("Mon français", html)

    def test_today_hides_answers_and_submission_returns_results(self):
        status, today = self.get_json(f"/api/today?date={date.today().isoformat()}")
        self.assertEqual(200, status)
        self.assertNotIn("answer", today["questions"][0])
        answers = {str(question["id"]): "x" for question in today["questions"]}
        status, result = self.post_json(f"/api/sessions/{today['id']}/submit", {"answers": answers})
        self.assertEqual(200, status)
        self.assertEqual(0, result["score"])
        self.assertIn("answer", result["questions"][0])
        _, history = self.get_json("/api/history")
        self.assertTrue(any(item["id"] == today["id"] for item in history))

    def test_invalid_calendar_date_returns_validation_error(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + "/api/today?date=2026-99-99", timeout=3)
        self.assertEqual(400, caught.exception.code)
        payload = json.load(caught.exception)
        self.assertEqual("validation_error", payload["error"]["code"])

    def test_non_today_date_is_rejected(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + f"/api/today?date={tomorrow}", timeout=3)
        self.assertEqual(400, caught.exception.code)

    def test_unknown_route_has_structured_404(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.base + "/api/unknown", timeout=3)
        self.assertEqual(404, caught.exception.code)
        payload = json.load(caught.exception)
        self.assertEqual("not_found", payload["error"]["code"])


if __name__ == "__main__":
    unittest.main()
