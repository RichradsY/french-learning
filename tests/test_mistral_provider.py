import json
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
    configured_api_key,
    replace_model_mcqs,
    validate_generated,
    validate_no_history_duplicates,
    validate_reading_not_repeated,
    validate_source_urls,
    validate_writing_not_repeated,
)
from french_learning.repository import Repository
from french_learning.service import LearningService
from french_learning.tasks import TaskValidationError, validate_writing_feedback


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


class FailingProvider:
    model = "fake-failing-model"

    def __init__(self):
        self.calls = 0

    def generate(self, study_date, avoid_prompts=(), avoid_words=()):
        self.calls += 1
        raise ProviderUnavailableError("simulated provider failure")


class MistralProviderValidationTest(unittest.TestCase):
    @staticmethod
    def writing_feedback(score=16):
        return {
            "score_total": score,
            "dimensions": {
                key: {
                    "score": score // 4,
                    "comment_fr": "Commentaire précis fondé sur le texte original.",
                    "comment_zh": "基于原文的具体评价。",
                }
                for key in ("task", "cohesion", "grammar", "vocabulary")
            },
            "summary_fr": "Une réponse solide, mais encore perfectible.",
            "summary_zh": "回答扎实，但仍有提升空间。",
            "corrected_text": "Je propose de créer un espace plus calme pour les habitants.",
            "errors": [],
            "model_answers": [
                {"level": "B2", "text": "Réponse B2 sur le même espace calme.", "vocabulary": [
                    {"expression_fr": "mettre en place", "meaning_zh": "实施"}
                ]},
                {"level": "C2", "text": "Réponse C2 sur le même espace calme.", "vocabulary": [
                    {"expression_fr": "à bien des égards", "meaning_zh": "在许多方面"}
                ]},
            ],
            "optimization_guidance": [{
                "advice_fr": "Développez les conséquences.",
                "advice_zh": "进一步展开后果。",
            }],
        }

    def test_writing_feedback_uses_twenty_point_scale_same_theme_models_and_guidance(self):
        feedback = self.writing_feedback()
        validated = validate_writing_feedback(
            feedback, "Je propose un espace plus calme pour les habitants."
        )
        self.assertEqual(16, validated["score_total"])
        self.assertEqual(["B2", "C2"], [item["level"] for item in validated["model_answers"]])

        feedback["score_total"] = 100
        feedback["dimensions"] = {
            key: {**item, "score": 25} for key, item in feedback["dimensions"].items()
        }
        with self.assertRaisesRegex(TaskValidationError, "between 0 and 20"):
            validate_writing_feedback(feedback)

    def test_perfect_writing_score_is_rejected_when_errors_are_reported(self):
        answer = "Je suis habitant ce quartier."
        feedback = self.writing_feedback(20)
        feedback["errors"] = [{
            "original": "habitant ce quartier",
            "correction": "habitant de ce quartier",
            "explanation_fr": "La préposition de est nécessaire.",
            "explanation_zh": "这里需要介词 de。",
            "grammar_key": "prepositions",
        }]
        with self.assertRaisesRegex(TaskValidationError, "Perfect writing score"):
            validate_writing_feedback(feedback, answer)

    def test_writing_grader_prompt_scores_original_on_twenty_points(self):
        provider = MistralContentProvider()
        captured = {}

        def fake_post(request, _key):
            captured.update(request)
            content = json.dumps(self.writing_feedback(), ensure_ascii=False)
            return {"choices": [{"message": {"content": content}}], "usage": {}}

        with patch("french_learning.mistral_provider.configured_api_key", return_value="safe-key"):
            with patch.object(provider, "_post", fake_post):
                feedback, _usage = provider.grade_writing(
                    {"title": "Un sujet", "min_words": 120, "max_words": 180},
                    "Je propose un espace plus calme pour les habitants.",
                )

        prompt_text = captured["messages"][1]["content"]
        self.assertEqual(16, feedback["score_total"])
        self.assertIn("PRODUCTION ORIGINALE", prompt_text)
        self.assertIn("score_total est leur somme sur 20", prompt_text)
        self.assertIn("5 est le maximum, pas une note automatique", prompt_text)
        self.assertIn("deux model_answers, ordonnés B2 puis C2", prompt_text)
        self.assertIn("même angle concret", prompt_text)

    def test_writing_grader_repairs_an_invalid_first_response(self):
        provider = MistralContentProvider()
        valid = json.dumps(self.writing_feedback(), ensure_ascii=False)
        responses = iter([
            {
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
            {
                "choices": [{"message": {"content": valid}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 15},
            },
        ])
        requests = []

        def fake_post(request, _key):
            requests.append(request)
            return next(responses)

        with patch("french_learning.mistral_provider.configured_api_key", return_value="safe-key"):
            with patch.object(provider, "_post", fake_post):
                feedback, usage = provider.grade_writing(
                    {"title": "Un sujet", "min_words": 120, "max_words": 180},
                    "Je propose un espace plus calme pour les habitants.",
                )

        self.assertEqual(16, feedback["score_total"])
        self.assertEqual(2, usage["request_count"])
        self.assertEqual(30, usage["prompt_tokens"])
        self.assertEqual(20, usage["completion_tokens"])
        self.assertEqual(2, len(requests))
        self.assertEqual(requests[0]["messages"], requests[1]["messages"][:2])
        self.assertEqual("assistant", requests[1]["messages"][2]["role"])
        self.assertEqual("{}", requests[1]["messages"][2]["content"])
        self.assertIn(
            "Writing score must be between 0 and 20",
            requests[1]["messages"][3]["content"],
        )
        self.assertIn("clés grammar_key autorisées", requests[1]["messages"][3]["content"])

    def test_writing_grader_reports_the_safe_repair_validation_reason(self):
        provider = MistralContentProvider()
        responses = iter([
            {"choices": [{"message": {"content": "{}"}}], "usage": {}},
            {"choices": [{"message": {"content": "{}"}}], "usage": {}},
        ])

        with patch("french_learning.mistral_provider.configured_api_key", return_value="safe-key"):
            with patch.object(provider, "_post", side_effect=lambda *_args: next(responses)):
                with self.assertRaisesRegex(
                    ContentValidationError,
                    "Writing score must be between 0 and 20",
                ):
                    provider.grade_writing(
                        {"title": "Un sujet", "min_words": 120, "max_words": 180},
                        "Je propose un espace plus calme pour les habitants.",
                    )

    def test_unknown_writing_taxonomy_is_kept_as_generic_written_expression(self):
        feedback = self.writing_feedback()
        feedback["errors"] = [{
            "original": "plus calme",
            "correction": "davantage apaisé",
            "explanation_fr": "Cette formulation est plus précise.",
            "explanation_zh": "这个表达更准确。",
            "grammar_key": "accord-du-participe",
        }]

        validated = validate_writing_feedback(
            feedback,
            "Je propose un espace plus calme pour les habitants.",
        )

        self.assertEqual("expression-ecrite", validated["errors"][0]["grammar_key"])

    def test_writing_total_is_derived_from_the_four_rubric_dimensions(self):
        feedback = self.writing_feedback()
        feedback["score_total"] = 19

        validated = validate_writing_feedback(feedback)

        self.assertEqual(16, validated["score_total"])

    def test_invalid_error_quotes_are_dropped_without_losing_valid_feedback(self):
        feedback = self.writing_feedback()
        feedback["errors"] = [
            {
                "original": "phrase inventée",
                "correction": "phrase corrigée",
                "explanation_fr": "Cette phrase ne vient pas du texte.",
                "explanation_zh": "这句话不在原文中。",
                "grammar_key": "registre",
            },
            {
                "original": "plus calme",
                "correction": "davantage apaisé",
                "explanation_fr": "Cette formulation est plus précise.",
                "explanation_zh": "这个表达更准确。",
                "grammar_key": "registre",
            },
        ]

        validated = validate_writing_feedback(
            feedback,
            "Je propose un espace plus calme pour les habitants.",
        )

        self.assertEqual(["plus calme"], [item["original"] for item in validated["errors"]])

    def test_generation_prompt_prepares_independent_b2_and_c2_models_with_the_topic(self):
        recent_topic = {"title": "Proposer une amélioration dans votre quartier"}
        prompt_text = MistralContentProvider._prompt(
            "2026-08-23", [], [], [], [recent_topic]
        )
        self.assertIn("model_answers", prompt_text)
        self.assertIn("préparées avant de voir la production de l'apprenant", prompt_text)
        self.assertIn("angle concret fixé dès la création du sujet", prompt_text)
        self.assertIn(recent_topic["title"], prompt_text)
        self.assertIn("B1 à C1", prompt_text)
        self.assertIn("词汇与用法", prompt_text)

    def test_repeated_reading_content_is_rejected(self):
        reading = {
            "title": "Une lecture déjà utilisée",
            "article_fr": "Un article contrôlé.",
            "questions": [{"prompt": "Pourquoi ce sujet ?"}],
        }
        with self.assertRaisesRegex(ContentValidationError, "Reading topic repeats"):
            validate_reading_not_repeated(reading, [reading])

    def test_generation_prompt_includes_recent_readings_to_avoid(self):
        recent = [{"title": "Une lecture récente", "questions": ["Une question"]}]
        prompt = MistralContentProvider._prompt(
            "2026-08-26", [], [], [], [], recent
        )
        self.assertIn("LECTURES RÉCENTES À NE PAS RÉPÉTER", prompt)
        self.assertIn("Une lecture récente", prompt)

    def test_repeated_writing_topic_is_rejected(self):
        writing = {
            "title": "Proposer une amélioration dans votre quartier",
            "context_fr": "Les habitants souhaitent disposer d'un nouvel espace calme dans leur quartier.",
        }
        with self.assertRaisesRegex(ContentValidationError, "repeats recent history"):
            validate_writing_not_repeated(writing, [writing])

    def test_api_key_rejects_curl_config_injection_characters(self):
        self.assertEqual("valid_token-1234567890", _validate_api_key("valid_token-1234567890"))
        for unsafe in ("short", "token\noutput=/tmp/leak", 'token"proxy=evil.example'):
            with self.assertRaises(ProviderUnavailableError):
                _validate_api_key(unsafe)

    def test_environment_api_key_is_supported_without_project_storage(self):
        with patch.dict("os.environ", {"MISTRAL_API_KEY": "valid_token-1234567890"}):
            with patch("french_learning.mistral_provider.keychain_api_key") as keychain:
                self.assertEqual("valid_token-1234567890", configured_api_key())
        keychain.assert_not_called()

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

    def test_failed_provider_attempt_is_still_charged_to_budget(self):
        with TemporaryDirectory() as folder:
            repository = Repository(f"{folder}/learning.db")
            provider = FailingProvider()
            try:
                session = LearningService(repository, content_provider=provider).get_or_create_day(
                    date.today().isoformat()
                )
                self.assertEqual(1, provider.calls)
                self.assertEqual("offline", session["content_source"])
                self.assertEqual(2, repository.monthly_api_calls(date.today().isoformat()[:7]))
            finally:
                repository.close()

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
        self.assertEqual(
            {0, 1, 2, 3},
            {
                question["options"].index(question["answer"])
                for question in validated_questions
                if question["kind"] == "mcq"
            },
        )

    def test_generic_option_explanation_is_rejected(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        option = questions[0]["options"][1]
        questions[0]["option_explanations"][option] = (
            "不正确：请根据前述法语说明辨别其时态、句法或语义问题。"
        )

        with self.assertRaisesRegex(ContentValidationError, "Generic option"):
            validate_generated({"questions": questions, "vocabulary": vocabulary})

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

    def test_all_used_controlled_mcqs_choose_oldest_from_newest_first_history(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        newest_to_oldest = [item["prompt"] for item in MCQ]
        replaced = replace_model_mcqs(
            {"questions": questions, "vocabulary": vocabulary}, newest_to_oldest
        )
        selected = [item["prompt"] for item in replaced["questions"][:5]]
        self.assertEqual(
            [item["prompt"] for item in reversed(MCQ[-5:])],
            selected,
        )

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

    def test_all_online_question_kinds_must_avoid_history_and_daily_duplicates(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        with self.assertRaisesRegex(ContentValidationError, "repeats or closely resembles"):
            validate_no_history_duplicates(
                questions, vocabulary, [questions[0]["prompt"]], []
            )
        duplicate = [dict(question) for question in questions]
        duplicate[1] = dict(duplicate[0])
        with self.assertRaisesRegex(ContentValidationError, "unique"):
            validate_generated({"questions": duplicate, "vocabulary": vocabulary})

    def test_online_question_near_duplicate_is_rejected(self):
        questions, vocabulary = generate_content("2026-08-23", {}, {})
        questions[0]["prompt"] = "Il s'en est fallu de peu que le projet ___."
        with self.assertRaisesRegex(ContentValidationError, "closely resembles"):
            validate_no_history_duplicates(
                questions,
                vocabulary,
                ["Il s'en est fallu de peu que nous ___ la correspondance."],
                [],
            )


if __name__ == "__main__":
    unittest.main()
