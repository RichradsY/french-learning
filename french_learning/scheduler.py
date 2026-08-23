"""Daily 07:00 scheduling and macOS LaunchAgent manifests."""
from __future__ import annotations

import os
import plistlib
import subprocess
import threading
from datetime import datetime, time, timedelta
from pathlib import Path

from .repository import Repository
from .service import LearningService

SERVER_LABEL = "com.local.french-learning.server"
DAILY_LABEL = "com.local.french-learning.daily"


def next_run(now=None):
    now = now or datetime.now().astimezone().replace(tzinfo=None)
    target = datetime.combine(now.date(), time(7, 0))
    return target if now < target else target + timedelta(days=1)


class DailyScheduler:
    def __init__(self, db_path, content_provider=None):
        self.db_path = Path(db_path)
        self.content_provider = content_provider
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.thread = threading.Thread(target=self._run, name="daily-content-scheduler", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def _run(self):
        while not self.stop_event.is_set():
            delay = max(1, (next_run() - datetime.now()).total_seconds())
            if self.stop_event.wait(delay):
                return
            repository = Repository(self.db_path)
            try:
                LearningService(repository, content_provider=self.content_provider).get_or_create_day(
                    datetime.now().date().isoformat()
                )
            finally:
                repository.close()


def render_launch_agents(output_dir, python_path, project_dir):
    output_dir = Path(output_dir)
    project_dir = Path(project_dir).resolve()
    python_path = str(Path(python_path).resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    logs = project_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    common = {
        "WorkingDirectory": str(project_dir),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }
    payloads = {
        SERVER_LABEL: {
            **common,
            "Label": SERVER_LABEL,
            "ProgramArguments": [python_path, "-m", "french_learning", "serve", "--host", "127.0.0.1", "--port", "8765"],
            "RunAtLoad": True,
            "KeepAlive": True,
            "ThrottleInterval": 10,
            "StandardOutPath": str(logs / "server.log"),
            "StandardErrorPath": str(logs / "server-error.log"),
        },
        DAILY_LABEL: {
            **common,
            "Label": DAILY_LABEL,
            "ProgramArguments": [python_path, "-m", "french_learning", "generate-today"],
            "StartCalendarInterval": {"Hour": 7, "Minute": 0},
            "StandardOutPath": str(logs / "daily.log"),
            "StandardErrorPath": str(logs / "daily-error.log"),
        },
    }
    paths = []
    for label, payload in payloads.items():
        path = output_dir / f"{label}.plist"
        path.write_bytes(plistlib.dumps(payload, sort_keys=True))
        paths.append(path)
    return paths


def install_launch_agents(project_dir, python_path):
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    paths = render_launch_agents(agents_dir, python_path, project_dir)
    domain = f"gui/{os.getuid()}"
    for path in paths:
        subprocess.run(["launchctl", "bootout", domain, str(path)], capture_output=True, check=False)
        subprocess.run(["launchctl", "bootstrap", domain, str(path)], check=True)
    return paths
