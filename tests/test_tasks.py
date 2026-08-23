import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from french_learning.repository import Repository
from french_learning.service import ConflictError, LearningService, ValidationError


class FakeWritingProvider:
    model = "fake-writing"

    def grade_writing(self, task, answer_text):
        feedback = {
            "score_total": 14,
            "dimensions": {
                "task": {"score": 4, "comment_fr": "Sujet traité.", "comment_zh": "完成了任务。"},
                "cohesion": {"score": 4, "comment_fr": "Organisation claire.", "comment_zh": "结构清晰。"},
                "grammar": {"score": 2, "comment_fr": "Quelques erreurs.", "comment_zh": "有少量错误。"},
                "vocabulary": {"score": 4, "comment_fr": "Lexique adapté.", "comment_zh": "词汇合适。"},
            },
            "summary_fr": "Une production compréhensible et bien organisée.",
            "summary_zh": "文章易懂，结构良好。",
            "corrected_text": answer_text.replace("je propose de créer", "je propose la création"),
            "model_answers": [
                {"level": "B2", "text": "Une réponse B2 sur le même espace calme.", "vocabulary": [
                    {"expression_fr": "un espace calme", "meaning_zh": "安静空间"}
                ]},
                {"level": "C2", "text": "Une réponse C2 sur le même espace calme.", "vocabulary": [
                    {"expression_fr": "un lieu apaisé", "meaning_zh": "安宁场所"}
                ]},
            ],
            "optimization_guidance": [{
                "advice_fr": "Variez les structures de phrase pour hiérarchiser les idées.",
                "advice_zh": "变换句式，更清晰地组织观点层次。",
            }],
            "errors": [
                {
                    "original": "je propose de créer",
                    "correction": "je propose la création",
                    "explanation_fr": "La forme nominale est plus naturelle ici.",
                    "explanation_zh": "这里使用名词形式更自然。",
                    "grammar_key": "articles-partitifs",
                }
            ],
        }
        return feedback, {
            "model": self.model,
            "prompt_tokens": 500,
            "completion_tokens": 300,
            "request_count": 1,
        }


class SlowWritingProvider(FakeWritingProvider):
    def __init__(self):
        self.calls = 0

    def grade_writing(self, task, answer_text):
        self.calls += 1
        time.sleep(0.05)
        return super().grade_writing(task, answer_text)


class FailingWritingProvider:
    model = "failing-writing"

    def grade_writing(self, task, answer_text):
        raise RuntimeError("simulated correction failure")


class ExtendedTasksTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Repository(Path(self.temp.name) / "tasks.db")
        self.service = LearningService(self.repo, content_provider=FakeWritingProvider())
        self.today = date.today().isoformat()

    def tearDown(self):
        self.repo.close()
        self.temp.cleanup()

    def test_reading_has_four_hidden_answers_then_grades_and_enters_history(self):
        task = self.service.get_learning_task(self.today, "reading")
        self.assertNotIn("article_fr", task["content"])
        self.assertEqual(480, task["content"]["time_limit_seconds"])
        with self.assertRaises(ValidationError):
            self.service.submit_reading(task["id"], {})
        task = self.service.start_reading(task["id"])
        self.assertEqual("in_progress", task["status"])
        self.assertEqual(4, len(task["content"]["questions"]))
        self.assertNotIn("answer", task["content"]["questions"][0])
        answers = {str(index): "x" for index in range(4)}
        result = self.service.submit_reading(task["id"], answers)
        self.assertEqual("completed", result["status"])
        self.assertIn("answer", result["content"]["questions"][0])
        self.assertEqual(4, len(result["submission"]["feedback"]["questions"]))
        self.assertTrue(any(item["activity_type"] == "reading" for item in self.service.history()))
        with self.assertRaises(ConflictError):
            self.service.submit_reading(task["id"], answers)

    def test_reading_deadline_auto_submits_unanswered_questions(self):
        current = datetime(2026, 8, 24, 7, 0, tzinfo=timezone.utc)
        service = LearningService(self.repo, now_fn=lambda: current)
        task = service.get_learning_task(self.today, "reading")
        started = service.start_reading(task["id"])
        resumed = service.start_reading(task["id"])
        self.assertEqual(started["deadline_at"], resumed["deadline_at"])
        self.assertEqual(
            current + timedelta(seconds=480),
            datetime.fromisoformat(started["deadline_at"]),
        )
        current += timedelta(seconds=481)
        expired = service.get_learning_task_by_id(task["id"])
        self.assertEqual("completed", expired["status"])
        self.assertEqual(0, expired["score"])
        self.assertTrue(expired["submission"]["feedback"]["timed_out"])
        self.assertEqual({str(index): "" for index in range(4)}, expired["submission"]["feedback"]["answers"])

    def test_reading_can_be_submitted_early_with_unanswered_items_counted_wrong(self):
        task = self.service.get_learning_task(self.today, "reading")
        task = self.service.start_reading(task["id"])
        first_answer = task["content"]["questions"][0]["options"][0]
        result = self.service.submit_reading(task["id"], {"0": first_answer})
        self.assertEqual("completed", result["status"])
        self.assertEqual("", result["submission"]["feedback"]["answers"]["1"])
        self.assertFalse(result["submission"]["feedback"]["timed_out"])

    def test_writing_is_scored_once_and_errors_feed_review(self):
        task = self.service.get_learning_task(self.today, "writing")
        prepared_models = task["content"]["model_answers"]
        self.assertEqual(["B2", "C2"], [item["level"] for item in prepared_models])
        answer = " ".join(
            "Dans mon quartier je propose de créer un espace calme pour les habitants et les étudiants qui souhaitent travailler ensemble dans de bonnes conditions".split()
            * 4
        )
        result = self.service.submit_writing(task["id"], answer)
        self.assertEqual(14, result["score"])
        self.assertEqual(14, result["submission"]["feedback"]["score_total"])
        self.assertEqual(
            ["B2", "C2"],
            [item["level"] for item in result["submission"]["feedback"]["model_answers"]],
        )
        self.assertNotEqual(prepared_models, result["submission"]["feedback"]["model_answers"])
        self.assertEqual(prepared_models, result["content"]["model_answers"])
        self.assertEqual(1, self.repo.monthly_api_calls(self.today[:7]))
        self.assertTrue(any(item["kind"] == "writing" for item in self.service.mistakes()))
        grammar = {item["grammar_key"]: item for item in self.service.grammar_summary()}
        self.assertEqual(1, grammar["articles-partitifs"]["mistake_count"])
        with self.assertRaises(ConflictError):
            self.service.submit_writing(task["id"], answer)


    def test_concurrent_writing_submission_calls_provider_once(self):
        provider = SlowWritingProvider()
        service = LearningService(self.repo, content_provider=provider)
        task = service.get_learning_task(self.today, "writing")
        answer = " ".join(
            "je propose de créer un espace calme pour tous les habitants".split() * 6
        )
        outcomes = []

        def submit():
            try:
                outcomes.append(service.submit_writing(task["id"], answer)["score"])
            except ConflictError:
                outcomes.append("conflict")

        threads = [threading.Thread(target=submit) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, provider.calls)
        self.assertEqual({14, "conflict"}, set(outcomes))

    def test_failed_writing_correction_is_charged_but_can_retry(self):
        service = LearningService(self.repo, content_provider=FailingWritingProvider())
        task = service.get_learning_task(self.today, "writing")
        answer = " ".join(
            "un texte français suffisamment long pour demander une correction détaillée".split()
            * 6
        )
        with self.assertRaises(Exception):
            service.submit_writing(task["id"], answer)
        self.assertEqual(1, self.repo.monthly_api_calls(self.today[:7]))
        stored = self.repo.get_learning_task_by_id(task["id"])
        self.assertEqual("ready", stored["status"] if stored else None)


if __name__ == "__main__":
    unittest.main()
