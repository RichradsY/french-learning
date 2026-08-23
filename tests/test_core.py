import re
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from french_learning.repository import Repository
from french_learning.service import ConflictError, LearningService, ValidationError


class CoreLearningTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.temp.name) / "test.db")
        self.service = LearningService(self.repo)

    def tearDown(self):
        self.repo.close()
        self.temp.cleanup()

    def test_daily_session_has_required_content_and_french_only_prompts(self):
        session = self.service.get_or_create_day("2026-08-23", reveal=True)
        questions = session["questions"]
        self.assertEqual(10, len(questions))
        self.assertEqual(5, sum(q["kind"] == "mcq" for q in questions))
        self.assertEqual(5, sum(q["kind"] == "fill" for q in questions))
        for question in questions:
            self.assertIsNone(re.search(r"[\u4e00-\u9fff]", question["prompt"]))
            if question["kind"] == "mcq":
                self.assertEqual(4, len(question["options"]))
                self.assertEqual(set(question["options"]), set(question["option_explanations"]))
                self.assertTrue(all(question["option_explanations"].values()))
                self.assertFalse(any("请根据前述法语说明" in explanation for explanation in question["option_explanations"].values()))
                self.assertFalse(any(re.search(r"[\u4e00-\u9fff]", option) for option in question["options"]))
        self.assertEqual(5, sum(v["category"] == "community" for v in session["vocabulary"]))
        self.assertEqual(5, sum(v["category"] == "daily" for v in session["vocabulary"]))

    def test_same_day_is_idempotent_and_next_day_avoids_question_repeats(self):
        first = self.service.get_or_create_day("2026-08-23", reveal=True)
        again = self.service.get_or_create_day("2026-08-23", reveal=True)
        second = self.service.get_or_create_day("2026-08-24", reveal=True)
        self.assertEqual(first["id"], again["id"])
        first_hashes = {q["content_hash"] for q in first["questions"]}
        second_hashes = {q["content_hash"] for q in second["questions"]}
        self.assertFalse(first_hashes & second_hashes)

    def test_concurrent_same_day_generation_creates_one_session(self):
        db_path = Path(self.temp.name) / "concurrent.db"
        barrier = threading.Barrier(4)
        ids, errors = [], []

        def generate():
            repository = Repository(db_path)
            try:
                barrier.wait()
                ids.append(LearningService(repository).get_or_create_day("2026-08-27")["id"])
            except Exception as exc:
                errors.append(exc)
            finally:
                repository.close()

        threads = [threading.Thread(target=generate) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual([], errors)
        self.assertEqual(1, len(set(ids)))

    def test_concurrent_old_schema_migration_is_idempotent(self):
        db_path = Path(self.temp.name) / "old-schema.db"
        connection = sqlite3.connect(db_path)
        connection.execute("""CREATE TABLE api_usage (
            id INTEGER PRIMARY KEY, used_at TEXT NOT NULL, model TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL, completion_tokens INTEGER NOT NULL
        )""")
        connection.execute(
            "INSERT INTO api_usage VALUES (1, '2026-08-01T07:00:00', 'legacy', 10, 20)"
        )
        connection.commit()
        connection.close()
        barrier = threading.Barrier(2)
        errors = []

        def migrate():
            try:
                barrier.wait()
                repository = Repository(db_path)
                repository.close()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=migrate) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual([], errors)
        connection = sqlite3.connect(db_path)
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(api_usage)")}
            self.assertIn("request_count", columns)
            self.assertEqual(
                2,
                connection.execute("SELECT request_count FROM api_usage WHERE id = 1").fetchone()[0],
            )
        finally:
            connection.close()

    def test_vocabulary_avoids_repeats_until_each_category_pool_is_exhausted(self):
        first = self.service.get_or_create_day("2026-08-23", reveal=True)
        second = self.service.get_or_create_day("2026-08-24", reveal=True)
        for category in ("community", "daily"):
            first_words = {v["word"] for v in first["vocabulary"] if v["category"] == category}
            second_words = {v["word"] for v in second["vocabulary"] if v["category"] == category}
            self.assertFalse(first_words & second_words)

    def test_answers_are_hidden_until_submission_then_every_option_is_explained(self):
        session = self.service.get_or_create_day("2026-08-23")
        for question in session["questions"]:
            self.assertNotIn("answer", question)
            self.assertNotIn("option_explanations", question)
        answers = {str(q["id"]): "réponse volontairement fausse" for q in session["questions"]}
        result = self.service.submit(session["id"], answers)
        self.assertEqual(0, result["score"])
        for question in result["questions"]:
            self.assertIn("answer", question)
            self.assertIn("explanation_fr", question)
            if question["kind"] == "mcq":
                self.assertEqual(4, len(question["option_explanations"]))

    def test_grading_normalizes_case_spaces_and_french_apostrophes(self):
        session = self.service.get_or_create_day("2026-08-23", reveal=True)
        answers = {}
        for question in session["questions"]:
            answer = question["answer"].upper().replace("'", "’")
            answers[str(question["id"])] = f"  {answer}  "
        result = self.service.submit(session["id"], answers)
        self.assertEqual(10, result["score"])
        self.assertTrue(all(question["is_correct"] for question in result["questions"]))

    def test_concurrent_submission_is_claimed_exactly_once(self):
        session = self.service.get_or_create_day("2026-08-23", reveal=True)
        correct = [
            (question["id"], question["answer"], True)
            for question in session["questions"]
        ]
        wrong = [
            (question["id"], "x", False)
            for question in session["questions"]
        ]
        barrier = threading.Barrier(2)
        results, errors = [], []

        def submit(graded):
            repository = Repository(self.repo.path)
            try:
                barrier.wait()
                results.append(repository.submit(session["id"], graded))
            except Exception as exc:
                errors.append(exc)
            finally:
                repository.close()

        threads = [
            threading.Thread(target=submit, args=(correct,)),
            threading.Thread(target=submit, args=(wrong,)),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual([], errors)
        self.assertEqual(1, sum(result is not None for result in results))
        self.assertEqual(1, sum(result is None for result in results))
        stored = self.repo.get_session(session["id"])
        if stored is None:
            self.fail("Concurrent submission removed the session")
        self.assertEqual("completed", stored["status"])
        self.assertIn(stored["score"], (0, 10))
        self.assertEqual(10, sum("user_answer" in q for q in stored["questions"]))

    def test_submission_requires_exact_question_set_and_completed_score_is_immutable(self):
        session = self.service.get_or_create_day("2026-08-23", reveal=True)
        complete = {str(q["id"]): q["answer"] for q in session["questions"]}
        with self.assertRaises(ValidationError):
            self.service.submit(session["id"], {})
        with self.assertRaises(ValidationError):
            self.service.submit(session["id"], {**complete, "999999": "x"})
        result = self.service.submit(session["id"], complete)
        self.assertEqual(10, result["score"])
        with self.assertRaises(ConflictError):
            self.service.submit(session["id"], complete)

    def test_history_mistakes_and_grammar_aggregate_from_submissions(self):
        session = self.service.get_or_create_day("2026-08-23")
        answers = {str(q["id"]): "x" for q in session["questions"]}
        self.service.submit(session["id"], answers)
        history = self.service.history()
        daily = next(item for item in history if item["activity_type"] == "daily")
        self.assertEqual("completed", daily["status"])
        self.assertEqual(0, daily["score"])
        self.assertEqual(10, len(self.service.mistakes()))
        grammar = self.service.grammar_summary()
        self.assertEqual(10, sum(item["mistake_count"] for item in grammar))


if __name__ == "__main__":
    unittest.main()
