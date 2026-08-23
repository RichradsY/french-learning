import unittest
from datetime import date, timedelta
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from french_learning.content import MCQ, generate_content
from french_learning.mistral_provider import (
    ContentValidationError,
    MistralContentProvider,
    ProviderUnavailableError,
    _validate_api_key,
    replace_model_mcqs,
    validate_generated,
    validate_no_history_duplicates,
    validate_source_urls,
)
from french_learning.repository import Repository
from french_learning.service import LearningService


class FakeProvider:
    def __init__(self):
        self.calls = 0

    def generate(self, study_date, avoid_prompts=(), avoid_words=()):
        self.calls += 1
        questions, vocabulary = generate_content(study_date, {}, {})
        return questions, vocabulary, {
            "model": "fake-model",
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "request_count": 2,
        }


class MistralProviderValidationTest(unittest.TestCase):
    def test_api_key_rejects_curl_config_injection_characters(self):
        self.assertEqual("valid_token-1234567890", _validate_api_key("valid_token-1234567890"))
        for unsafe in ("short", "token\noutput=/tmp/leak", 'token"proxy=evil.example'):
            with self.assertRaises(ProviderUnavailableError):
                _validate_api_key(unsafe)

    def test_post_passes_key_via_private_curl_config_not_command_line(self):
        dummy_key = "test_token_1234567890"

        def fake_run(command, **kwargs):
            self.assertNotIn(dummy_key, command)
            config_path = command[command.index("--config") + 1]
            with open(config_path, encoding="utf-8") as handle:
                config = handle.read()
            self.assertIn(f"Authorization: Bearer {dummy_key}", config)
            return SimpleNamespace(
                returncode=0,
                stdout='{"choices":[{"message":{"content":"{}"}}],"usage":{}}',
            )

        with patch("french_learning.mistral_provider.subprocess.run", fake_run):
            response = MistralContentProvider()._post({"model": "test"}, dummy_key)
        self.assertIn("choices", response)

    def test_two_request_budget_does_not_overshoot_limit(self):
        with TemporaryDirectory() as folder:
            repository = Repository(f"{folder}/learning.db")
            provider = FakeProvider()
            repository.record_api_usage({
                "model": "previous",
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "request_count": 69,
            })
            try:
                service = LearningService(
                    repository, content_provider=provider, max_monthly_api_calls=70
                )
                session = service.get_or_create_day(date.today().isoformat())
                self.assertEqual(0, provider.calls)
                self.assertEqual("offline", session["content_source"])
                self.assertEqual(69, repository.monthly_api_calls(date.today().isoformat()[:7]))
            finally:
                repository.close()

    def test_online_provider_only_runs_for_today_and_today_is_cached(self):
        with TemporaryDirectory() as folder:
            repository = Repository(f"{folder}/learning.db")
            provider = FakeProvider()
            service = LearningService(repository, content_provider=provider)
            try:
                tomorrow = (date.today() + timedelta(days=1)).isoformat()
                service.get_or_create_day(tomorrow)
                self.assertEqual(0, provider.calls)
                today = date.today().isoformat()
                service.get_or_create_day(today)
                service.get_or_create_day(today)
                self.assertEqual(1, provider.calls)
                self.assertEqual(2, repository.monthly_api_calls(today[:7]))
            finally:
                repository.close()

    def test_offline_shape_is_accepted_by_online_content_validator(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        validated_questions, validated_vocabulary = validate_generated({
            "questions": questions,
            "vocabulary": vocabulary,
        })
        self.assertEqual(10, len(validated_questions))
        self.assertEqual(10, len(validated_vocabulary))

    def test_community_source_urls_must_come_from_fetched_context(self):
        _, vocabulary = generate_content("2026-08-23", {}, {})
        community = [item for item in vocabulary if item["category"] == "community"]
        context = [{"url": item["source_url"]} for item in community]
        validate_source_urls(vocabulary, context)
        community[0]["source_url"] = "https://example.invalid/invented"
        with self.assertRaises(ContentValidationError):
            validate_source_urls(vocabulary, context)

    def test_controlled_rotation_uses_most_recent_occurrence(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        avoid = [MCQ[0]["prompt"]] + [item["prompt"] for item in MCQ[1:]] + [MCQ[0]["prompt"]]
        replaced = replace_model_mcqs({"questions": questions, "vocabulary": vocabulary}, avoid)
        selected = {item["prompt"] for item in replaced["questions"][:5]}
        self.assertNotIn(MCQ[0]["prompt"], selected)

    def test_model_mcqs_are_replaced_with_controlled_items(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        for index in range(5):
            questions[index]["prompt"] = f"Question générée ambiguë {index}"
        replaced = replace_model_mcqs(
            {"questions": questions, "vocabulary": vocabulary},
            avoid_prompts=[item["prompt"] for item in generate_content("2026-08-22", {}, {})[0][:5]],
        )
        controlled_prompts = {item["prompt"] for item in MCQ}
        self.assertTrue(all(item["prompt"] in controlled_prompts for item in replaced["questions"][:5]))
        self.assertEqual(5, len({item["prompt"] for item in replaced["questions"][:5]}))

    def test_semantically_interchangeable_mcq_distractors_are_rejected(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        questions[0].update({
            "prompt": "Il a réussi parce qu'il a travaillé, mais choisissez un connecteur.",
            "options": ["parce que", "car", "puisque", "donc"],
            "answer": "parce que",
            "accepted": ["parce que"],
            "option_explanations": {
                option: "Explication française. 中文解释。"
                for option in ["parce que", "car", "puisque", "donc"]
            },
        })
        with self.assertRaises(ContentValidationError):
            validate_generated({"questions": questions, "vocabulary": vocabulary})

    def test_wrong_counts_and_chinese_prompt_are_rejected(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        with self.assertRaises(ContentValidationError):
            validate_generated({"questions": questions[:9], "vocabulary": vocabulary})
        questions[0]["prompt"] = "选择正确答案"
        with self.assertRaises(ContentValidationError):
            validate_generated({"questions": questions, "vocabulary": vocabulary})

    def test_chinese_answer_and_accepted_variant_are_rejected(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        questions[5]["answer"] = "中文"
        questions[5]["accepted"] = ["中文"]
        with self.assertRaises(ContentValidationError):
            validate_generated({"questions": questions, "vocabulary": vocabulary})
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        questions[5]["accepted"].append("中文")
        with self.assertRaises(ContentValidationError):
            validate_generated({"questions": questions, "vocabulary": vocabulary})

    def test_online_fill_and_vocabulary_must_not_repeat_history(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        with self.assertRaises(ContentValidationError):
            validate_no_history_duplicates(
                questions,
                vocabulary,
                [questions[5]["prompt"].upper().replace("É", "E") + " !!!"],
                [],
            )
        with self.assertRaises(ContentValidationError):
            validate_no_history_duplicates(
                questions, vocabulary, [], [vocabulary[0]["word"].upper()]
            )


if __name__ == "__main__":
    unittest.main()
