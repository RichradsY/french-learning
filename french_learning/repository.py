"""SQLite persistence layer."""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import fcntl

from .content import GRAMMAR


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection_lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA busy_timeout = 5000")
        with self.generation_lock():
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA journal_mode = WAL")
            self._initialize()

    def _initialize(self):
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS daily_sessions (
            id INTEGER PRIMARY KEY, study_date TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'ready', generated_at TEXT NOT NULL,
            submitted_at TEXT, score INTEGER, content_source TEXT NOT NULL DEFAULT 'offline'
        );
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES daily_sessions(id) ON DELETE CASCADE,
            position INTEGER NOT NULL, kind TEXT NOT NULL, prompt TEXT NOT NULL,
            options_json TEXT NOT NULL, answer TEXT NOT NULL, accepted_json TEXT NOT NULL,
            option_explanations_json TEXT NOT NULL, explanation_fr TEXT NOT NULL,
            explanation_zh TEXT NOT NULL, grammar_key TEXT NOT NULL, content_hash TEXT NOT NULL,
            UNIQUE(session_id, position)
        );
        CREATE INDEX IF NOT EXISTS idx_questions_hash ON questions(content_hash);
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES daily_sessions(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
            user_answer TEXT NOT NULL, is_correct INTEGER NOT NULL, graded_at TEXT NOT NULL,
            UNIQUE(session_id, question_id)
        );
        CREATE TABLE IF NOT EXISTS vocabulary (
            id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL REFERENCES daily_sessions(id) ON DELETE CASCADE,
            category TEXT NOT NULL, word TEXT NOT NULL, part_of_speech TEXT NOT NULL,
            definition_fr TEXT NOT NULL, definition_zh TEXT NOT NULL,
            example_fr TEXT NOT NULL, example_zh TEXT NOT NULL,
            source_name TEXT, source_url TEXT
        );
        CREATE TABLE IF NOT EXISTS grammar_points (
            grammar_key TEXT PRIMARY KEY, title_fr TEXT NOT NULL, explanation_fr TEXT NOT NULL,
            explanation_zh TEXT NOT NULL, example_fr TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS api_usage (
            id INTEGER PRIMARY KEY, used_at TEXT NOT NULL, model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL, completion_tokens INTEGER NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS learning_tasks (
            id INTEGER PRIMARY KEY, study_date TEXT NOT NULL, task_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ready', title TEXT NOT NULL,
            content_json TEXT NOT NULL, source_name TEXT, source_url TEXT,
            content_source TEXT NOT NULL DEFAULT 'offline', generated_at TEXT NOT NULL,
            started_at TEXT, deadline_at TEXT, submitted_at TEXT, score INTEGER,
            UNIQUE(study_date, task_type)
        );
        CREATE TABLE IF NOT EXISTS task_submissions (
            id INTEGER PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES learning_tasks(id) ON DELETE CASCADE,
            answer_text TEXT NOT NULL, feedback_json TEXT NOT NULL,
            submitted_at TEXT NOT NULL, score INTEGER NOT NULL,
            UNIQUE(task_id)
        );
        CREATE TABLE IF NOT EXISTS writing_errors (
            id INTEGER PRIMARY KEY,
            submission_id INTEGER NOT NULL REFERENCES task_submissions(id) ON DELETE CASCADE,
            grammar_key TEXT NOT NULL REFERENCES grammar_points(grammar_key),
            original_text TEXT NOT NULL, correction TEXT NOT NULL,
            explanation_fr TEXT NOT NULL, explanation_zh TEXT NOT NULL
        );
        """)
        columns = {row[1] for row in self.connection.execute("PRAGMA table_info(daily_sessions)")}
        if "content_source" not in columns:
            self.connection.execute("ALTER TABLE daily_sessions ADD COLUMN content_source TEXT NOT NULL DEFAULT 'offline'")
        usage_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(api_usage)")}
        if "request_count" not in usage_columns:
            self.connection.execute("ALTER TABLE api_usage ADD COLUMN request_count INTEGER NOT NULL DEFAULT 1")
            self.connection.execute("UPDATE api_usage SET request_count = 2")
        task_columns = {row[1] for row in self.connection.execute("PRAGMA table_info(learning_tasks)")}
        if "started_at" not in task_columns:
            self.connection.execute("ALTER TABLE learning_tasks ADD COLUMN started_at TEXT")
        if "deadline_at" not in task_columns:
            self.connection.execute("ALTER TABLE learning_tasks ADD COLUMN deadline_at TEXT")
        self.connection.executemany(
            "INSERT OR IGNORE INTO grammar_points VALUES (?, ?, ?, ?, ?)",
            [(key, *value) for key, value in GRAMMAR.items()],
        )
        self.connection.commit()

    def close(self):
        self.connection.close()

    @contextmanager
    def generation_lock(self):
        lock_path = self.path.with_suffix(self.path.suffix + ".generation.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def question_usage(self):
        return {
            row["content_hash"]: row["last_seen"]
            for row in self.connection.execute("""
                SELECT q.content_hash, MAX(s.study_date) AS last_seen
                FROM questions q JOIN daily_sessions s ON s.id = q.session_id
                GROUP BY q.content_hash
            """)
        }

    def vocabulary_usage(self):
        return {
            f"{row['category']}:{row['word']}": row["last_seen"]
            for row in self.connection.execute("""
                SELECT v.category, v.word, MAX(s.study_date) AS last_seen
                FROM vocabulary v JOIN daily_sessions s ON s.id = v.session_id
                GROUP BY v.category, v.word
            """)
        }

    def recent_prompts(self, limit=40):
        query = """
            SELECT q.prompt FROM questions q JOIN daily_sessions s ON s.id = q.session_id
            ORDER BY s.study_date DESC, q.position
        """
        params = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        return [row[0] for row in self.connection.execute(query, params)]

    def recent_words(self, limit=80):
        query = """
            SELECT v.word FROM vocabulary v JOIN daily_sessions s ON s.id = v.session_id
            ORDER BY s.study_date DESC, v.id
        """
        params = ()
        if limit is not None:
            query += " LIMIT ?"
            params = (limit,)
        return [row[0] for row in self.connection.execute(query, params)]

    def monthly_api_calls(self, month_prefix):
        return self.connection.execute(
            "SELECT COALESCE(SUM(request_count), 0) FROM api_usage WHERE used_at LIKE ?",
            (f"{month_prefix}%",),
        ).fetchone()[0]

    def record_api_usage(self, usage):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connection:
            self.connection.execute(
                """INSERT INTO api_usage(
                    used_at, model, prompt_tokens, completion_tokens, request_count
                ) VALUES (?, ?, ?, ?, ?)""",
                (
                    now,
                    usage["model"],
                    usage["prompt_tokens"],
                    usage["completion_tokens"],
                    usage.get("request_count", 1),
                ),
            )

    def reserve_api_usage(self, model, request_count=2):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._connection_lock:
            with self.connection:
                cursor = self.connection.execute(
                    """INSERT INTO api_usage(
                        used_at, model, prompt_tokens, completion_tokens, request_count
                    ) VALUES (?, ?, 0, 0, ?)""",
                    (now, model, request_count),
                )
        return cursor.lastrowid

    def finalize_api_usage(self, usage_id, usage):
        with self._connection_lock:
            with self.connection:
                self.connection.execute(
                    """UPDATE api_usage
                       SET model = ?, prompt_tokens = ?, completion_tokens = ?
                       WHERE id = ?""",
                    (
                        usage["model"],
                        usage["prompt_tokens"],
                        usage["completion_tokens"],
                        usage_id,
                    ),
                )

    def session_id_for_date(self, study_date):
        row = self.connection.execute("SELECT id FROM daily_sessions WHERE study_date = ?", (study_date,)).fetchone()
        return row[0] if row else None

    def create_session(self, study_date, questions, vocabulary, content_source="offline"):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO daily_sessions(study_date, generated_at, content_source) VALUES (?, ?, ?)",
                (study_date, now, content_source),
            )
            session_id = cursor.lastrowid
            self.connection.executemany(
                """INSERT INTO questions(session_id, position, kind, prompt, options_json, answer,
                accepted_json, option_explanations_json, explanation_fr, explanation_zh, grammar_key, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(session_id, q["position"], q["kind"], q["prompt"], json.dumps(q["options"], ensure_ascii=False),
                  q["answer"], json.dumps(q["accepted"], ensure_ascii=False),
                  json.dumps(q["option_explanations"], ensure_ascii=False), q["explanation_fr"],
                  q["explanation_zh"], q["grammar_key"], q["content_hash"]) for q in questions],
            )
            self.connection.executemany(
                """INSERT INTO vocabulary(session_id, category, word, part_of_speech, definition_fr,
                definition_zh, example_fr, example_zh, source_name, source_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(session_id, v["category"], v["word"], v["part_of_speech"], v["definition_fr"],
                  v["definition_zh"], v["example_fr"], v["example_zh"], v["source_name"], v["source_url"])
                 for v in vocabulary],
            )
        return session_id

    def get_session(self, session_id):
        session = self.connection.execute("SELECT * FROM daily_sessions WHERE id = ?", (session_id,)).fetchone()
        if not session:
            return None
        result = dict(session)
        questions = []
        for row in self.connection.execute("SELECT * FROM questions WHERE session_id = ? ORDER BY position", (session_id,)):
            item = dict(row)
            for field in ("options_json", "accepted_json", "option_explanations_json"):
                item[field.removesuffix("_json")] = json.loads(item.pop(field))
            response = self.connection.execute("SELECT user_answer, is_correct FROM responses WHERE question_id = ?", (item["id"],)).fetchone()
            if response:
                item["user_answer"] = response["user_answer"]
                item["is_correct"] = bool(response["is_correct"])
            questions.append(item)
        result["questions"] = questions
        result["vocabulary"] = [dict(row) for row in self.connection.execute("SELECT * FROM vocabulary WHERE session_id = ? ORDER BY category, id", (session_id,))]
        return result

    def submit(self, session_id, graded_answers):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connection:
            claimed = self.connection.execute(
                """UPDATE daily_sessions SET status = 'grading'
                   WHERE id = ? AND status = 'ready'""",
                (session_id,),
            )
            if claimed.rowcount != 1:
                return None
            self.connection.executemany(
                "INSERT INTO responses(session_id, question_id, user_answer, is_correct, graded_at) VALUES (?, ?, ?, ?, ?)",
                [(session_id, question_id, answer, int(correct), now) for question_id, answer, correct in graded_answers],
            )
            score = sum(correct for _, _, correct in graded_answers)
            self.connection.execute(
                "UPDATE daily_sessions SET status = 'completed', submitted_at = ?, score = ? WHERE id = ?",
                (now, score, session_id),
            )
        return score

    def create_learning_tasks(self, study_date, reading, writing, content_source="offline"):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        rows = [
            (
                study_date,
                "reading",
                reading["title"],
                json.dumps(reading, ensure_ascii=False),
                reading.get("source_name"),
                reading.get("source_url"),
                content_source,
                now,
            ),
            (
                study_date,
                "writing",
                writing["title"],
                json.dumps(writing, ensure_ascii=False),
                None,
                None,
                content_source,
                now,
            ),
        ]
        with self.connection:
            self.connection.executemany(
                """INSERT OR IGNORE INTO learning_tasks(
                    study_date, task_type, title, content_json, source_name, source_url,
                    content_source, generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def get_learning_task(self, study_date, task_type):
        row = self.connection.execute(
            "SELECT * FROM learning_tasks WHERE study_date = ? AND task_type = ?",
            (study_date, task_type),
        ).fetchone()
        return self._task_from_row(row) if row else None

    def get_learning_task_by_id(self, task_id):
        row = self.connection.execute(
            "SELECT * FROM learning_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._task_from_row(row) if row else None

    def _task_from_row(self, row):
        task = dict(row)
        task["content"] = json.loads(task.pop("content_json"))
        submission = self.connection.execute(
            "SELECT * FROM task_submissions WHERE task_id = ?", (task["id"],)
        ).fetchone()
        if submission:
            task["submission"] = dict(submission)
            task["submission"]["feedback"] = json.loads(
                task["submission"].pop("feedback_json")
            )
        return task

    def start_reading(self, task_id, started_at, deadline_at):
        with self._connection_lock:
            with self.connection:
                cursor = self.connection.execute(
                    """UPDATE learning_tasks
                       SET status = 'in_progress', started_at = ?, deadline_at = ?
                       WHERE id = ? AND task_type = 'reading' AND status = 'ready'""",
                    (started_at, deadline_at, task_id),
                )
        return cursor.rowcount == 1

    def submit_reading(self, task_id, answers, graded, timed_out=False):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        score = sum(item["is_correct"] for item in graded)
        feedback = {"answers": answers, "questions": graded, "timed_out": bool(timed_out)}
        with self._connection_lock:
            with self.connection:
                claimed = self.connection.execute(
                    "UPDATE learning_tasks SET status = 'grading' WHERE id = ? AND task_type = 'reading' AND status = 'in_progress'",
                    (task_id,),
                )
                if claimed.rowcount != 1:
                    return None
                self.connection.execute(
                    "INSERT INTO task_submissions(task_id, answer_text, feedback_json, submitted_at, score) VALUES (?, '', ?, ?, ?)",
                    (task_id, json.dumps(feedback, ensure_ascii=False), now, score),
                )
                self.connection.execute(
                    "UPDATE learning_tasks SET status = 'completed', submitted_at = ?, score = ? WHERE id = ?",
                    (now, score, task_id),
                )
        return score

    def submit_writing(self, task_id, answer_text, feedback):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        score = feedback["score_total"]
        with self.connection:
            current = self.connection.execute(
                "SELECT status FROM learning_tasks WHERE id = ? AND task_type = 'writing'",
                (task_id,),
            ).fetchone()
            if not current or current["status"] != "grading":
                return None
            cursor = self.connection.execute(
                "INSERT INTO task_submissions(task_id, answer_text, feedback_json, submitted_at, score) VALUES (?, ?, ?, ?, ?)",
                (task_id, answer_text, json.dumps(feedback, ensure_ascii=False), now, score),
            )
            self.connection.executemany(
                """INSERT INTO writing_errors(
                    submission_id, grammar_key, original_text, correction,
                    explanation_fr, explanation_zh
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                [
                    (
                        cursor.lastrowid,
                        item["grammar_key"],
                        item["original"],
                        item["correction"],
                        item["explanation_fr"],
                        item["explanation_zh"],
                    )
                    for item in feedback["errors"]
                ],
            )
            self.connection.execute(
                "UPDATE learning_tasks SET status = 'completed', submitted_at = ?, score = ? WHERE id = ?",
                (now, score, task_id),
            )
        return score

    def claim_writing_task(self, task_id):
        with self._connection_lock:
            with self.connection:
                cursor = self.connection.execute(
                    "UPDATE learning_tasks SET status = 'grading' WHERE id = ? AND task_type = 'writing' AND status = 'ready'",
                    (task_id,),
                )
        return cursor.rowcount == 1

    def release_writing_task(self, task_id):
        with self._connection_lock:
            with self.connection:
                self.connection.execute(
                    "UPDATE learning_tasks SET status = 'ready' WHERE id = ? AND task_type = 'writing' AND status = 'grading'",
                    (task_id,),
                )

    def task_history(self):
        return [
            dict(row)
            for row in self.connection.execute(
                """SELECT id, study_date, task_type, status, title, score,
                          submitted_at, content_source
                   FROM learning_tasks ORDER BY study_date DESC, task_type"""
            )
        ]

    def history(self):
        return [dict(row) for row in self.connection.execute("SELECT * FROM daily_sessions ORDER BY study_date DESC")]

    def mistakes(self):
        rows = self.connection.execute("""
            SELECT q.id, q.prompt, q.answer, q.explanation_fr, q.explanation_zh, q.grammar_key,
                   q.kind, q.options_json, q.option_explanations_json, r.user_answer, s.study_date
            FROM responses r JOIN questions q ON q.id = r.question_id
            JOIN daily_sessions s ON s.id = r.session_id WHERE r.is_correct = 0
            ORDER BY s.study_date DESC, q.position
        """)
        items = []
        for row in rows:
            item = dict(row)
            item["options"] = json.loads(item.pop("options_json"))
            item["option_explanations"] = json.loads(item.pop("option_explanations_json"))
            items.append(item)
        for row in self.connection.execute("""
            SELECT -we.id AS id, we.original_text AS prompt, we.correction AS answer,
                   we.explanation_fr, we.explanation_zh, we.grammar_key,
                   'writing' AS kind, we.original_text AS user_answer, lt.study_date
            FROM writing_errors we
            JOIN task_submissions ts ON ts.id = we.submission_id
            JOIN learning_tasks lt ON lt.id = ts.task_id
            ORDER BY lt.study_date DESC, we.id
        """):
            item = dict(row)
            item["options"] = []
            item["option_explanations"] = {}
            items.append(item)
        return items

    def grammar_summary(self):
        return [dict(row) for row in self.connection.execute("""
            SELECT g.*,
                   COUNT(CASE WHEN r.is_correct = 0 THEN 1 END)
                     + (SELECT COUNT(*) FROM writing_errors we WHERE we.grammar_key = g.grammar_key)
                     AS mistake_count,
                   COUNT(r.id)
                     + (SELECT COUNT(*) FROM writing_errors we WHERE we.grammar_key = g.grammar_key)
                     AS attempt_count
            FROM grammar_points g LEFT JOIN questions q ON q.grammar_key = g.grammar_key
            LEFT JOIN responses r ON r.question_id = q.id
            GROUP BY g.grammar_key
            HAVING COUNT(r.id) > 0
                OR (SELECT COUNT(*) FROM writing_errors we WHERE we.grammar_key = g.grammar_key) > 0
            ORDER BY mistake_count DESC, g.title_fr
        """)]

    def all_vocabulary(self):
        return [dict(row) for row in self.connection.execute("""
            SELECT v.*, s.study_date FROM vocabulary v JOIN daily_sessions s ON s.id = v.session_id
            ORDER BY s.study_date DESC, v.category, v.id
        """)]
