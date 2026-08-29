import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from french_learning.repository import Repository
from french_learning.service import ConflictError, LearningService, ValidationError
from french_learning.tasks import offline_tasks


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


class BlockingWritingProvider(FakeWritingProvider):
    def __init__(self):
        self.calls = 0
        self.started = threading.Event()
        self.release = threading.Event()

    def grade_writing(self, task, answer_text):
        self.calls += 1
        self.started.set()
        self.release.wait(timeout=2)
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

    def test_offline_writing_rotates_away_from_recent_topic(self):
        _reading, previous = offline_tasks("2026-08-23")
        _reading, current = offline_tasks("2026-08-24", [previous])
        self.assertNotEqual(previous["title"], current["title"])
        self.assertEqual("Raconter une journée sans téléphone", current["title"])
        self.assertEqual(["B2", "C2"], [item["level"] for item in current["model_answers"]])

    def test_offline_writing_rotates_six_distinct_formats_and_topics(self):
        recent = []
        generated = []
        for offset in range(6):
            day = (date(2026, 8, 24) + timedelta(days=offset)).isoformat()
            _reading, writing = offline_tasks(day, recent)
            generated.append(writing)
            recent.append(writing)

        self.assertEqual(6, len({item["title"] for item in generated}))
        instructions = " ".join(item["instructions_fr"].casefold() for item in generated)
        for text_type in ("forum", "témoignage", "note", "critique"):
            self.assertIn(text_type, instructions)

    def test_offline_reading_does_not_repeat_between_august_22_and_24(self):
        first, _writing = offline_tasks("2026-08-22")
        second, _writing = offline_tasks("2026-08-24")
        self.assertNotEqual(first["title"], second["title"])
        self.assertFalse(
            {question["prompt"] for question in first["questions"]}
            & {question["prompt"] for question in second["questions"]}
        )
        self.assertTrue(180 <= len(second["article_fr"].split()) <= 450)

    def test_offline_reading_avoids_the_previous_five_readings(self):
        recent = []
        for offset in range(12):
            day = (date(2026, 8, 26) + timedelta(days=offset)).isoformat()
            reading, _writing = offline_tasks(
                day, avoid_reading_topics=recent[-5:]
            )
            self.assertNotIn(
                reading["title"], {item["title"] for item in recent[-5:]}
            )
            recent_prompts = {
                question["prompt"]
                for previous in recent[-5:]
                for question in previous["questions"]
            }
            self.assertFalse(
                {question["prompt"] for question in reading["questions"]}
                & recent_prompts
            )
            self.assertTrue(180 <= len(reading["article_fr"].split()) <= 450)
            recent.append(reading)

    def test_reading_has_four_hidden_answers_then_grades_and_enters_history(self):
        task = self.service.get_learning_task(self.today, "reading")
        self.assertNotIn("article_fr", task["content"])
        self.assertEqual(480, task["content"]["time_limit_seconds"])
        with self.assertRaises(ValidationError):
            self.service.submit_reading(task["id"], {})
        task = self.service.start_reading(task["id"])
        self.assertEqual("in_progress", task["status"])
        self.assertEqual(4, len(task["content"]["questions"]))
        stored_task = self.repo.get_learning_task_by_id(task["id"])
        self.assertIsNotNone(stored_task)
        assert stored_task is not None
        self.assertEqual(
            {0, 1, 2, 3},
            {
                question["options"].index(question["answer"])
                for question in stored_task["content"]["questions"]
            },
        )
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
        restored = service.get_learning_task_by_id(task["id"])
        self.assertEqual(answer, restored["draft_text"])
        self.assertTrue(restored["correction_error"])

    def test_queued_writing_survives_navigation_and_duplicate_submit(self):
        provider = BlockingWritingProvider()
        service = LearningService(self.repo, content_provider=provider)
        task = service.get_learning_task(self.today, "writing")
        answer = " ".join(
            "je propose une solution concrète pour améliorer la vie des habitants".split()
            * 6
        )

        queued = service.queue_writing(task["id"], answer)
        self.assertEqual("grading", queued["status"])
        self.assertTrue(provider.started.wait(timeout=1))
        self.assertEqual("grading", service.get_learning_task_by_id(task["id"])["status"])
        self.assertEqual("grading", service.queue_writing(task["id"], answer)["status"])
        self.assertEqual(1, provider.calls)

        provider.release.set()
        completed = service.get_learning_task_by_id(task["id"])
        for _attempt in range(100):
            completed = service.get_learning_task_by_id(task["id"])
            if completed["status"] == "completed":
                break
            time.sleep(0.01)
        self.assertEqual("completed", completed["status"])
        self.assertEqual(answer, completed["submission"]["answer_text"])

    def test_service_resumes_a_persisted_grading_job(self):
        task = self.service.get_learning_task(self.today, "writing")
        answer = " ".join(
            "je raconte une expérience personnelle et les changements que je souhaite adopter".split()
            * 5
        )
        self.assertTrue(self.repo.claim_writing_task(task["id"], answer))

        resumed = LearningService(self.repo, content_provider=FakeWritingProvider())
        result = resumed.get_learning_task_by_id(task["id"])
        for _attempt in range(100):
            result = resumed.get_learning_task_by_id(task["id"])
            if result["status"] == "completed":
                break
            time.sleep(0.01)
        self.assertEqual("completed", result["status"])
        self.assertEqual(answer, result["submission"]["answer_text"])


if __name__ == "__main__":
    unittest.main()
