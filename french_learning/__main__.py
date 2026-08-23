"""Command-line entry point."""
from __future__ import annotations

import argparse
import signal
import sys
from datetime import date
from pathlib import Path

from .mistral_provider import MistralContentProvider
from .repository import Repository
from .scheduler import DailyScheduler, install_launch_agents
from .service import LearningService
from .web import create_server

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB = PROJECT_DIR / "data" / "learning.db"


def parser():
    root = argparse.ArgumentParser(description="Local TCF B1 French learning system")
    commands = root.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="start the local web application")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--db", type=Path, default=DEFAULT_DB)
    serve.add_argument("--offline", action="store_true", help="disable Mistral generation")
    generate = commands.add_parser("generate-today", help="prepare today's idempotent lesson")
    generate.add_argument("--db", type=Path, default=DEFAULT_DB)
    generate.add_argument("--offline", action="store_true", help="disable Mistral generation")
    commands.add_parser("install-scheduler", help="install and start macOS LaunchAgents")
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if args.command == "generate-today":
        repository = Repository(args.db)
        try:
            provider = None if args.offline else MistralContentProvider()
            session = LearningService(repository, content_provider=provider).get_or_create_day(
                date.today().isoformat()
            )
            print(
                f"Séance prête : {session['study_date']} (id={session['id']}, "
                f"source={session['content_source']})"
            )
        finally:
            repository.close()
        return 0
    if args.command == "install-scheduler":
        paths = install_launch_agents(PROJECT_DIR, Path(sys.executable))
        print("LaunchAgents installés :")
        for path in paths:
            print(path)
        print("Application : http://127.0.0.1:8765")
        return 0
    provider = None if args.offline else MistralContentProvider()
    server = create_server(args.host, args.port, args.db, content_provider=provider)
    scheduler = DailyScheduler(args.db, content_provider=provider)
    scheduler.start()
    stopping = False

    def stop_server(_signum, _frame):
        nonlocal stopping
        if not stopping:
            stopping = True
            # shutdown must run outside serve_forever's signal callback path
            import threading
            threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGINT, stop_server)
    signal.signal(signal.SIGTERM, stop_server)
    print(f"Mon français est prêt sur http://{args.host}:{server.server_port}")
    try:
        server.serve_forever()
    finally:
        scheduler.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
