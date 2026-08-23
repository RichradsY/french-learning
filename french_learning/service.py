"""Application use cases and response redaction."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta

from .conjugation import conjugation_insights
from .content import generate_content
from .tasks import offline_tasks


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


class ConflictError(Exception):
    pass


def normalize_answer(value):
    value = unicodedata.normalize("NFC", str(value)).strip().lower().replace("’", "'")
    return re.sub(r"\s+", " ", value)


def clean_option_explanations(question):
    suffixes = (
        " 正确：该选项符合本句的语法与语义。",
        " 不正确：请根据前述法语说明辨别其时态、句法或语义问题。",
    )
    notes = question.get("option_explanations")
    if notes:
        question["option_explanations"] = {
            option: next(
                (text.removesuffix(suffix) for suffix in suffixes if text.endswith(suffix)),
                text,
            )
            for option, text in notes.items()
        }
    return question


class LearningService:
    def __init__(self, repository, content_provider=None, max_monthly_api_calls=105, now_fn=None):
        self.repository = repository
        self.content_provider = content_provider
        self.max_monthly_api_calls = max_monthly_api_calls
        self.now_fn = now_fn or (lambda: datetime.now().astimezone())

    def get_or_create_day(self, study_date, reveal=False):
        with self.repository.generation_lock():
            session_id = self.repository.session_id_for_date(study_date)
            if session_id is None:
                source = "offline"
                generated = None
                task_bundle = None
                if (
                    self.content_provider is not None
                    and study_date == date.today().isoformat()
                    and self.repository.monthly_api_calls(study_date[:7]) + 2 <= self.max_monthly_api_calls
                ):
                    reservation_id = self.repository.reserve_api_usage(
                        getattr(self.content_provider, "model", type(self.content_provider).__name__),
                        request_count=2,
                    )
                    try:
                        arguments = (
                            study_date,
                            self.repository.recent_prompts(limit=None),
                            self.repository.recent_words(limit=None),
                        )
                        if hasattr(self.content_provider, "generate_bundle"):
                            questions, vocabulary, reading, writing, usage = (
                                self.content_provider.generate_bundle(*arguments)
                            )
                            task_bundle = (reading, writing)
                        else:
                            questions, vocabulary, usage = self.content_provider.generate(
                                *arguments
                            )
                        self.repository.finalize_api_usage(reservation_id, usage)
                        generated = (questions, vocabulary)
                        source = f"mistral:{usage['model']}"
                    except Exception as exc:
                        print(
                            "Online generation unavailable, using offline content: "
                            f"{type(exc).__name__}: {exc}"
                        )
                if generated is None:
                    generated = generate_content(
                        study_date,
                        self.repository.question_usage(),
                        self.repository.vocabulary_usage(),
                    )
                if task_bundle is None:
                    task_bundle = offline_tasks(study_date)
                questions, vocabulary = generated
                try:
                    session_id = self.repository.create_session(
                        study_date, questions, vocabulary, content_source=source
                    )
                except sqlite3.IntegrityError:
                    session_id = self.repository.session_id_for_date(study_date)
                    if session_id is None:
                        raise
                self.repository.create_learning_tasks(
                    study_date, *task_bundle, content_source=source
                )
        session = self.repository.get_session(session_id)
        return self._present(session, reveal or session["status"] == "completed")

    def get_session(self, session_id):
        session = self.repository.get_session(session_id)
        if not session:
            raise NotFoundError("Séance introuvable")
        return self._present(session, session["status"] == "completed")

    def submit(self, session_id, answers):
        session = self.repository.get_session(session_id)
        if not session:
            raise NotFoundError("Séance introuvable")
        if not isinstance(answers, dict):
            raise ValidationError("Le champ answers doit être un objet")
        if session["status"] == "completed":
            raise ConflictError("Cette séance a déjà été corrigée")
        expected_ids = {str(question["id"]) for question in session["questions"]}
        if set(answers) != expected_ids:
            raise ValidationError("Une réponse est requise pour chacune des 10 questions")
        graded = []
        for question in session["questions"]:
            submitted = str(answers.get(str(question["id"]), ""))
            accepted = {normalize_answer(answer) for answer in question["accepted"]}
            graded.append((question["id"], submitted, normalize_answer(submitted) in accepted))
        score = self.repository.submit(session_id, graded)
        if score is None:
            raise ConflictError("Cette séance a déjà été corrigée")
        return self._present(self.repository.get_session(session_id), True)

    def history(self):
        daily = [dict(item, activity_type="daily") for item in self.repository.history()]
        tasks = [dict(item, activity_type=item["task_type"]) for item in self.repository.task_history()]
        return sorted(daily + tasks, key=lambda item: (item["study_date"], item["activity_type"]), reverse=True)

    def get_learning_task(self, study_date, task_type):
        if task_type not in ("reading", "writing"):
            raise ValidationError("Type d'activité invalide")
        with self.repository.generation_lock():
            task = self.repository.get_learning_task(study_date, task_type)
            if task is None:
                reading, writing = offline_tasks(study_date)
                self.repository.create_learning_tasks(study_date, reading, writing)
                task = self.repository.get_learning_task(study_date, task_type)
        return self._present_task(self._expire_reading(task))

    def get_learning_task_by_id(self, task_id):
        task = self.repository.get_learning_task_by_id(task_id)
        if not task:
            raise NotFoundError("Activité introuvable")
        return self._present_task(self._expire_reading(task))

    def start_reading(self, task_id):
        task = self.repository.get_learning_task_by_id(task_id)
        if not task or task["task_type"] != "reading":
            raise NotFoundError("Lecture introuvable")
        task = self._expire_reading(task)
        if task["status"] == "completed":
            raise ConflictError("Cette lecture a déjà été corrigée")
        if task["status"] == "ready":
            started_at = self.now_fn()
            deadline_at = started_at + timedelta(seconds=task["content"].get("time_limit_seconds", 480))
            self.repository.start_reading(
                task_id,
                started_at.isoformat(timespec="seconds"),
                deadline_at.isoformat(timespec="seconds"),
            )
            task = self.repository.get_learning_task_by_id(task_id)
        return self._present_task(task)

    def submit_reading(self, task_id, answers):
        task = self.repository.get_learning_task_by_id(task_id)
        if not task or task["task_type"] != "reading":
            raise NotFoundError("Lecture introuvable")
        if not isinstance(answers, dict):
            raise ValidationError("Le champ answers doit être un objet")
        if task["status"] == "ready":
            raise ValidationError("Commencez la lecture avant de répondre")
        if task["status"] == "completed":
            raise ConflictError("Cette lecture a déjà été corrigée")
        questions = task["content"]["questions"]
        expected = {str(index) for index in range(len(questions))}
        if not set(answers) <= expected:
            raise ValidationError("Les réponses contiennent une question inconnue")
        deadline = datetime.fromisoformat(task["deadline_at"])
        now = self.now_fn()
        timed_out = now >= deadline
        if now > deadline + timedelta(seconds=5):
            answers = {}
        answers = {index: str(answers.get(index, "")) for index in expected}
        return self._finish_reading(task, answers, timed_out)

    def _finish_reading(self, task, answers, timed_out):
        questions = task["content"]["questions"]
        graded = []
        for index, question in enumerate(questions):
            submitted = str(answers[str(index)])
            graded.append(
                {
                    "index": index,
                    "user_answer": submitted,
                    "is_correct": submitted == question["answer"],
                }
            )
        if self.repository.submit_reading(task["id"], answers, graded, timed_out) is None:
            raise ConflictError("Cette lecture a déjà été corrigée")
        return self._present_task(self.repository.get_learning_task_by_id(task["id"]))

    def _expire_reading(self, task):
        if task["task_type"] != "reading" or task["status"] != "in_progress":
            return task
        if self.now_fn() < datetime.fromisoformat(task["deadline_at"]):
            return task
        answers = {str(index): "" for index in range(len(task["content"]["questions"]))}
        try:
            self._finish_reading(task, answers, True)
        except ConflictError:
            pass
        return self.repository.get_learning_task_by_id(task["id"])

    def submit_writing(self, task_id, answer_text):
        task = self.repository.get_learning_task_by_id(task_id)
        if not task or task["task_type"] != "writing":
            raise NotFoundError("Sujet d'écriture introuvable")
        if not isinstance(answer_text, str):
            raise ValidationError("Le texte est obligatoire")
        answer_text = answer_text.strip()
        word_count = len(re.findall(r"[\wÀ-ÿ]+(?:['’-][\wÀ-ÿ]+)*", answer_text))
        if not 40 <= word_count <= 600:
            raise ValidationError("Le texte doit contenir entre 40 et 600 mots")
        if self.content_provider is None or not hasattr(self.content_provider, "grade_writing"):
            raise ValidationError("La correction détaillée nécessite le service Mistral")
        if self.repository.monthly_api_calls(task["study_date"][:7]) + 1 > self.max_monthly_api_calls:
            raise ValidationError("Le budget mensuel de correction est épuisé")
        if not self.repository.claim_writing_task(task_id):
            raise ConflictError("Cette production écrite a déjà été corrigée")
        reservation_id = self.repository.reserve_api_usage(
            getattr(self.content_provider, "model", type(self.content_provider).__name__), 1
        )
        try:
            feedback, usage = self.content_provider.grade_writing(task["content"], answer_text)
            self.repository.finalize_api_usage(reservation_id, usage)
            if self.repository.submit_writing(task_id, answer_text, feedback) is None:
                raise ConflictError("Cette production écrite a déjà été corrigée")
        except ConflictError:
            self.repository.release_writing_task(task_id)
            raise
        except Exception as exc:
            self.repository.release_writing_task(task_id)
            print(f"Writing correction failed: {type(exc).__name__}: {exc}")
            raise ValidationError("La correction détaillée est momentanément indisponible") from exc
        return self._present_task(self.repository.get_learning_task_by_id(task_id))

    def mistakes(self):
        return [clean_option_explanations(item) for item in self.repository.mistakes()]

    def grammar_summary(self):
        return self.repository.grammar_summary()

    def conjugation_summary(self):
        return conjugation_insights(self.repository.mistakes())

    def vocabulary(self):
        return self.repository.all_vocabulary()

    @staticmethod
    def _present_task(task):
        result = dict(task)
        content = dict(result["content"])
        if result["task_type"] == "reading" and result["status"] == "ready":
            content = {"time_limit_seconds": content.get("time_limit_seconds", 480)}
        elif result["task_type"] == "reading" and result["status"] != "completed":
            content["questions"] = [
                {key: value for key, value in question.items() if key not in ("answer", "explanation_fr", "explanation_zh")}
                for question in content["questions"]
            ]
        result["content"] = content
        return result

    @staticmethod
    def _present(session, reveal):
        result = {key: value for key, value in session.items() if key not in ("questions", "vocabulary")}
        result["questions"] = []
        for raw in session["questions"]:
            question = {key: value for key, value in raw.items() if key not in ("session_id", "accepted")}
            if not reveal:
                for secret in ("answer", "option_explanations", "explanation_fr", "explanation_zh", "content_hash"):
                    question.pop(secret, None)
            result["questions"].append(clean_option_explanations(question))
        result["vocabulary"] = [{key: value for key, value in item.items() if key != "session_id"} for item in session["vocabulary"]]
        return result
