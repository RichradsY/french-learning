"""SQLite persistence layer."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .content import GRAMMAR


class Repository:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self._initialize()

    def _initialize(self):
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS daily_sessions (
            id INTEGER PRIMARY KEY, study_date TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'ready', generated_at TEXT NOT NULL,
            submitted_at TEXT, score INTEGER
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
        """)
        self.connection.executemany(
            "INSERT OR IGNORE INTO grammar_points VALUES (?, ?, ?, ?, ?)",
            [(key, *value) for key, value in GRAMMAR.items()],
        )
        self.connection.commit()

    def close(self):
        self.connection.close()

    def used_hashes(self):
        return {row[0] for row in self.connection.execute("SELECT DISTINCT content_hash FROM questions")}

    def session_id_for_date(self, study_date):
        row = self.connection.execute("SELECT id FROM daily_sessions WHERE study_date = ?", (study_date,)).fetchone()
        return row[0] if row else None

    def create_session(self, study_date, questions, vocabulary):
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO daily_sessions(study_date, generated_at) VALUES (?, ?)", (study_date, now)
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
            self.connection.execute("DELETE FROM responses WHERE session_id = ?", (session_id,))
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
        return items

    def grammar_summary(self):
        return [dict(row) for row in self.connection.execute("""
            SELECT g.*, COUNT(CASE WHEN r.is_correct = 0 THEN 1 END) AS mistake_count,
                   COUNT(r.id) AS attempt_count
            FROM grammar_points g LEFT JOIN questions q ON q.grammar_key = g.grammar_key
            LEFT JOIN responses r ON r.question_id = q.id
            GROUP BY g.grammar_key HAVING COUNT(r.id) > 0
            ORDER BY mistake_count DESC, g.title_fr
        """)]

    def all_vocabulary(self):
        return [dict(row) for row in self.connection.execute("""
            SELECT v.*, s.study_date FROM vocabulary v JOIN daily_sessions s ON s.id = v.session_id
            ORDER BY s.study_date DESC, v.category, v.id
        """)]
