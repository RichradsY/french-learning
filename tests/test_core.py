import re
import tempfile
import unittest
from pathlib import Path

from french_learning.repository import Repository
from french_learning.service import LearningService


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

    def test_history_mistakes_and_grammar_aggregate_from_submissions(self):
        session = self.service.get_or_create_day("2026-08-23")
        answers = {str(q["id"]): "x" for q in session["questions"]}
        self.service.submit(session["id"], answers)
        history = self.service.history()
        self.assertEqual("completed", history[0]["status"])
        self.assertEqual(0, history[0]["score"])
        self.assertEqual(10, len(self.service.mistakes()))
        grammar = self.service.grammar_summary()
        self.assertEqual(10, sum(item["mistake_count"] for item in grammar))


if __name__ == "__main__":
    unittest.main()
