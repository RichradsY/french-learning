"""Small loopback-only JSON API and static file server."""
from __future__ import annotations

import json
import mimetypes
import re
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .repository import Repository
from .service import ConflictError, LearningService, NotFoundError, ValidationError
from .speech import MacOSFrenchSpeech, SpeechUnavailableError, SpeechValidationError

STATIC_DIR = Path(__file__).with_name("static")
STATIC_FILES = {
    "/": "index.html",
    "/app.js": "app.js",
    "/styles.css": "styles.css",
    "/favicon.svg": "favicon.svg",
}


class LearningHTTPServer(HTTPServer):
    repository: Repository

    def server_close(self):
        super().server_close()
        self.repository.close()


def _handler_class(service, speech):
    class Handler(BaseHTTPRequestHandler):
        server_version = "FrenchLearning/0.1"

        def log_message(self, format, *args):
            print(f"[{self.log_date_time_string()}] {format % args}")

        def _json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _audio(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "audio/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, max-age=86400")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status, code, message):
            self._json(status, {"error": {"code": code, "message": message}})

        def do_GET(self):
            parsed = urlparse(self.path)
            try:
                if parsed.path in STATIC_FILES:
                    return self._static(STATIC_FILES[parsed.path])
                if parsed.path == "/api/health":
                    return self._json(200, {"status": "ok", "service": "french-learning"})
                if parsed.path == "/api/today":
                    requested = parse_qs(parsed.query).get("date", [date.today().isoformat()])[0]
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", requested):
                        raise ValidationError("Date invalide")
                    try:
                        requested_date = date.fromisoformat(requested)
                    except ValueError as exc:
                        raise ValidationError("Date invalide") from exc
                    if requested_date != date.today():
                        raise ValidationError("Seule la séance d'aujourd'hui peut être générée")
                    return self._json(200, service.get_or_create_day(requested))
                if parsed.path == "/api/history":
                    return self._json(200, service.history())
                if parsed.path == "/api/mistakes":
                    return self._json(200, service.mistakes())
                if parsed.path == "/api/grammar":
                    return self._json(200, service.grammar_summary())
                if parsed.path == "/api/conjugations":
                    return self._json(200, service.conjugation_summary())
                if parsed.path == "/api/vocabulary":
                    return self._json(200, service.vocabulary())
                task_type_match = re.fullmatch(r"/api/tasks/(reading|writing)", parsed.path)
                if task_type_match:
                    requested = parse_qs(parsed.query).get("date", [date.today().isoformat()])[0]
                    if requested != date.today().isoformat():
                        raise ValidationError("Seules les activités d'aujourd'hui peuvent être préparées")
                    return self._json(
                        200, service.get_learning_task(requested, task_type_match.group(1))
                    )
                task_match = re.fullmatch(r"/api/tasks/(\d+)", parsed.path)
                if task_match:
                    return self._json(200, service.get_learning_task_by_id(int(task_match.group(1))))
                match = re.fullmatch(r"/api/sessions/(\d+)", parsed.path)
                if match:
                    return self._json(200, service.get_session(int(match.group(1))))
                return self._error(404, "not_found", "Ressource introuvable")
            except ValidationError as exc:
                return self._error(400, "validation_error", str(exc))
            except NotFoundError as exc:
                return self._error(404, "not_found", str(exc))
            except Exception as exc:
                print(f"Request failed: {exc!r}")
                return self._error(500, "internal_error", "Erreur interne")

        def do_POST(self):
            parsed = urlparse(self.path)
            match = re.fullmatch(r"/api/sessions/(\d+)/submit", parsed.path)
            reading_start_match = re.fullmatch(r"/api/reading/(\d+)/start", parsed.path)
            reading_match = re.fullmatch(r"/api/reading/(\d+)/submit", parsed.path)
            writing_match = re.fullmatch(r"/api/writing/(\d+)/submit", parsed.path)
            if parsed.path != "/api/speech" and not match and not reading_start_match and not reading_match and not writing_match:
                return self._error(404, "not_found", "Ressource introuvable")
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValidationError("Corps de requête invalide")
                payload = json.loads(self.rfile.read(length))
                if parsed.path == "/api/speech":
                    return self._audio(speech.render(payload.get("text")))
                if reading_start_match:
                    return self._json(200, service.start_reading(int(reading_start_match.group(1))))
                if reading_match:
                    return self._json(
                        200,
                        service.submit_reading(
                            int(reading_match.group(1)), payload.get("answers")
                        ),
                    )
                if writing_match:
                    return self._json(
                        200,
                        service.submit_writing(
                            int(writing_match.group(1)), payload.get("text")
                        ),
                    )
                assert match
                return self._json(200, service.submit(int(match.group(1)), payload.get("answers")))
            except (json.JSONDecodeError, AttributeError):
                return self._error(400, "invalid_json", "JSON invalide")
            except (ValidationError, SpeechValidationError) as exc:
                return self._error(400, "validation_error", str(exc))
            except SpeechUnavailableError as exc:
                return self._error(503, "speech_unavailable", str(exc))
            except ConflictError as exc:
                return self._error(409, "conflict", str(exc))
            except NotFoundError as exc:
                return self._error(404, "not_found", str(exc))
            except Exception as exc:
                print(f"Request failed: {exc!r}")
                return self._error(500, "internal_error", "Erreur interne")

        def _static(self, filename):
            path = STATIC_DIR / filename
            if not path.is_file():
                return self._error(404, "not_found", "Fichier introuvable")
            body = path.read_bytes()
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header(
                "Content-Type",
                f"{mime}; charset=utf-8"
                if mime.startswith("text/") or mime == "application/javascript"
                else mime,
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; style-src 'self'; script-src 'self'; "
                "connect-src 'self'; media-src 'self' blob:; img-src 'self' data:",
            )
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(
    host="127.0.0.1",
    port=8765,
    db_path=None,
    content_provider=None,
    speech_service=None,
):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("This learning app only binds to loopback addresses")
    if db_path is None:
        db_path = Path.cwd() / "data" / "learning.db"
    repository = Repository(db_path)
    if speech_service is None:
        speech_service = MacOSFrenchSpeech()
    server = LearningHTTPServer(
        (host, port),
        _handler_class(
            LearningService(repository, content_provider=content_provider), speech_service
        ),
    )
    server.repository = repository
    return server
