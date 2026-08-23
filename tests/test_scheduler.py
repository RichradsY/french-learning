import plistlib
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from french_learning.scheduler import next_run, render_launch_agents


class SchedulerTest(unittest.TestCase):
    def test_next_run_is_today_before_seven_and_tomorrow_after_seven(self):
        before = datetime(2026, 8, 23, 6, 59)
        after = datetime(2026, 8, 23, 7, 1)
        self.assertEqual(datetime(2026, 8, 23, 7, 0), next_run(before))
        self.assertEqual(datetime(2026, 8, 24, 7, 0), next_run(after))

    def test_launch_agents_bind_local_server_and_generate_at_seven(self):
        with tempfile.TemporaryDirectory() as folder:
            files = render_launch_agents(Path(folder), Path("/usr/bin/python3"), Path("/tmp/French Learning"))
            self.assertEqual(2, len(files))
            payloads = [plistlib.loads(path.read_bytes()) for path in files]
            server = next(item for item in payloads if item["Label"].endswith("server"))
            daily = next(item for item in payloads if item["Label"].endswith("daily"))
            self.assertTrue(server["KeepAlive"])
            self.assertIn("127.0.0.1", server["ProgramArguments"])
            self.assertEqual({"Hour": 7, "Minute": 0}, daily["StartCalendarInterval"])
            self.assertIn("generate-today", daily["ProgramArguments"])


if __name__ == "__main__":
    unittest.main()
