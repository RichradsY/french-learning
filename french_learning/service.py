"""Application use cases and response redaction."""
from __future__ import annotations

import re
import sqlite3
import threading
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


def daily_question_seconds(question):
    return 40 if question["kind"] == "mcq" else 55


class LearningService:
    def __init__(self, repository, content_provider=None, max_monthly_api_calls=105, now_fn=None):
        self.repository = repository
        self.content_provider = content_provider
        self.max_monthly_api_calls = max_monthly_api_calls
        self.now_fn = now_fn or (lambda: datetime.now().astimezone())
        self._writing_workers = set()
        self._writing_workers_lock = threading.Lock()
        if self.content_provider is not None:
            for item in self.repository.pending_writing_tasks():
                self._start_writing_worker(item["id"])

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
                            self.repository.recent_prompts(limit=30),
                            self.repository.recent_words(limit=None),
                        )
                        if hasattr(self.content_provider, "generate_bundle"):
                            questions, vocabulary, reading, writing, usage = (
                                self.content_provider.generate_bundle(
                                    *arguments,
                                    self.repository.recent_writing_topics(limit=None),
                                    self.repository.recent_reading_topics(),
                                )
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
                        self.repository.recent_prompts(limit=30),
                    )
                if task_bundle is None:
                    task_bundle = offline_tasks(
                        study_date,
                        self.repository.recent_writing_topics(limit=None),
                        self.repository.recent_reading_topics(),
                    )
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
        if not reveal:
            session = self._expire_daily(session)
        return self._present(session, reveal or session["status"] == "completed")

    def get_session(self, session_id):
        session = self.repository.get_session(session_id)
        if not session:
            raise NotFoundError("Séance introuvable")
        session = self._expire_daily(session)
        return self._present(session, session["status"] == "completed")

    def start_daily(self, session_id):
        session = self.repository.get_session(session_id)
        if not session:
            raise NotFoundError("Séance introuvable")
        session = self._expire_daily(session)
        if session["status"] == "completed":
            raise ConflictError("Cette séance a déjà été corrigée")
        if session["status"] == "ready":
            started_at = self.now_fn()
            deadline_at = started_at + timedelta(
                seconds=daily_question_seconds(session["questions"][0])
            )
            self.repository.start_daily(
                session_id,
                started_at.isoformat(timespec="seconds"),
                deadline_at.isoformat(timespec="seconds"),
            )
            session = self.repository.get_session(session_id)
        return self._present(session, False)

    def answer_daily(self, session_id, question_id, answer):
        if not isinstance(question_id, int) or not isinstance(answer, str):
            raise ValidationError("Réponse invalide")
        if len(answer) > 500:
            raise ValidationError("Réponse trop longue")
        session = self.repository.get_session(session_id)
        if not session:
            raise NotFoundError("Séance introuvable")
        session = self._expire_daily(session)
        if session["status"] == "ready":
            raise ConflictError("Commencez la séance avant de répondre")
        if session["status"] == "completed":
            if any(q["id"] == question_id and "user_answer" in q for q in session["questions"]):
                return self._present(session, True)
            raise ConflictError("Cette séance a déjà été corrigée")
        current = session["questions"][session["current_position"] - 1]
        if current["id"] != question_id:
            if any(q["id"] == question_id and "user_answer" in q for q in session["questions"]):
                return self._present(session, False)
            raise ConflictError("Cette question n'est plus active")
        now = self.now_fn()
        accepted = {normalize_answer(value) for value in current["accepted"]}
        next_question = next(
            (q for q in session["questions"] if q["position"] == current["position"] + 1),
            None,
        )
        next_deadline = (
            now + timedelta(seconds=daily_question_seconds(next_question))
            if next_question else None
        )
        if self.repository.advance_daily(
            session_id,
            question_id,
            answer,
            normalize_answer(answer) in accepted,
            False,
            now.isoformat(timespec="seconds"),
            next_deadline.isoformat(timespec="seconds") if next_deadline else None,
        ) is None:
            raise ConflictError("Cette question a déjà été enregistrée")
        session = self.repository.get_session(session_id)
        return self._present(session, session["status"] == "completed")

    def _expire_daily(self, session):
        while (
            session
            and session["status"] == "in_progress"
            and self.now_fn() >= datetime.fromisoformat(session["question_deadline_at"])
        ):
            current = session["questions"][session["current_position"] - 1]
            next_question = next(
                (q for q in session["questions"] if q["position"] == current["position"] + 1),
                None,
            )
            deadline = datetime.fromisoformat(session["question_deadline_at"])
            next_deadline = (
                deadline + timedelta(seconds=daily_question_seconds(next_question))
                if next_question else None
            )
            self.repository.advance_daily(
                session["id"],
                current["id"],
                "",
                False,
                True,
                deadline.isoformat(timespec="seconds"),
                next_deadline.isoformat(timespec="seconds") if next_deadline else None,
            )
            session = self.repository.get_session(session["id"])
        return session

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
                reading, writing = offline_tasks(
                    study_date, self.repository.recent_writing_topics(limit=None)
                )
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

    def _prepare_writing_submission(self, task_id, answer_text):
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
        request_budget = int(getattr(self.content_provider, "writing_request_budget", 1))
        if self.repository.monthly_api_calls(task["study_date"][:7]) + request_budget > self.max_monthly_api_calls:
            raise ValidationError("Le budget mensuel de correction est épuisé")
        return task, answer_text, request_budget

    def submit_writing(self, task_id, answer_text):
        task, answer_text, request_budget = self._prepare_writing_submission(task_id, answer_text)
        if not self.repository.claim_writing_task(task_id, answer_text):
            raise ConflictError("Cette production écrite a déjà été corrigée")
        self._grade_claimed_writing(task_id, request_budget, propagate=True)
        return self._present_task(self.repository.get_learning_task_by_id(task_id))

    def queue_writing(self, task_id, answer_text):
        task, answer_text, _request_budget = self._prepare_writing_submission(task_id, answer_text)
        if task["status"] == "completed":
            return self._present_task(task)
        if task["status"] == "grading":
            if task.get("pending_answer_text") != answer_text:
                raise ConflictError("Une autre production est déjà en cours de correction")
            self._start_writing_worker(task_id)
            return self._present_task(task)
        if not self.repository.claim_writing_task(task_id, answer_text):
            raise ConflictError("Cette production écrite a déjà été envoyée")
        self._start_writing_worker(task_id)
        return self._present_task(self.repository.get_learning_task_by_id(task_id))

    def _start_writing_worker(self, task_id):
        with self._writing_workers_lock:
            if task_id in self._writing_workers:
                return
            self._writing_workers.add(task_id)
        threading.Thread(
            target=self._run_writing_worker,
            args=(task_id,),
            name=f"writing-correction-{task_id}",
            daemon=True,
        ).start()

    def _run_writing_worker(self, task_id):
        try:
            task = self.repository.get_learning_task_by_id(task_id)
            if not task or task["status"] != "grading":
                return
            request_budget = int(getattr(self.content_provider, "writing_request_budget", 1))
            self._grade_claimed_writing(task_id, request_budget, propagate=False)
        finally:
            with self._writing_workers_lock:
                self._writing_workers.discard(task_id)

    def _grade_claimed_writing(self, task_id, request_budget, propagate):
        task = self.repository.get_learning_task_by_id(task_id)
        if not task or task["status"] != "grading" or not task.get("pending_answer_text"):
            if propagate:
                raise ConflictError("Cette production écrite n'est plus en cours de correction")
            return
        provider = self.content_provider
        if provider is None:
            self.repository.release_writing_task(task_id, "provider_unavailable")
            if propagate:
                raise ValidationError("La correction détaillée nécessite le service Mistral")
            return
        if self.repository.monthly_api_calls(task["study_date"][:7]) + request_budget > self.max_monthly_api_calls:
            self.repository.release_writing_task(task_id, "budget")
            if propagate:
                raise ValidationError("Le budget mensuel de correction est épuisé")
            return
        reservation_id = self.repository.reserve_api_usage(
            getattr(provider, "model", type(provider).__name__),
            request_budget,
        )
        try:
            feedback, usage = provider.grade_writing(
                task["content"], task["pending_answer_text"]
            )
            self.repository.finalize_api_usage(reservation_id, usage)
            if self.repository.submit_writing(
                task_id, task["pending_answer_text"], feedback
            ) is None:
                raise ConflictError("Cette production écrite a déjà été corrigée")
        except ConflictError:
            self.repository.release_writing_task(task_id)
            if propagate:
                raise
        except Exception as exc:
            self.repository.release_writing_task(task_id, type(exc).__name__)
            print(f"Writing correction failed: {type(exc).__name__}: {exc}")
            if propagate:
                raise ValidationError("La correction détaillée est momentanément indisponible") from exc

    def mistakes(self):
        return [clean_option_explanations(item) for item in self.repository.mistakes()]

    def grammar_summary(self):
        return self.repository.grammar_summary()

    def conjugation_summary(self):
        return conjugation_insights(self.repository.mistakes())

    def vocabulary(self, month=None, starred_only=False):
        if month is not None and not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValidationError("Mois invalide")
        if month is not None:
            try:
                date.fromisoformat(f"{month}-01")
            except ValueError as exc:
                raise ValidationError("Mois invalide") from exc
        return self.repository.all_vocabulary(month, starred_only)

    def set_vocabulary_star(self, vocabulary_id, starred):
        if not isinstance(starred, bool):
            raise ValidationError("État de favori invalide")
        result = self.repository.set_vocabulary_star(vocabulary_id, starred)
        if result is None:
            raise NotFoundError("Mot introuvable")
        return result

    @staticmethod
    def _present_task(task):
        result = dict(task)
        pending_answer = result.pop("pending_answer_text", None)
        grading_error = result.pop("grading_error", None)
        if result["task_type"] == "writing":
            result["draft_text"] = pending_answer if result["status"] == "ready" else None
            result["correction_error"] = bool(grading_error)
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
        result["question_count"] = len(session["questions"])
        result["estimated_seconds"] = sum(daily_question_seconds(q) for q in session["questions"])
        result["questions"] = []
        visible_questions = session["questions"]
        if not reveal and session["status"] == "ready":
            visible_questions = []
        elif not reveal and session["status"] == "in_progress":
            visible_questions = [session["questions"][session["current_position"] - 1]]
            result["question_time_limit_seconds"] = daily_question_seconds(visible_questions[0])
        for raw in visible_questions:
            question = {key: value for key, value in raw.items() if key not in ("session_id", "accepted")}
            if not reveal:
                for secret in ("answer", "option_explanations", "explanation_fr", "explanation_zh", "content_hash"):
                    question.pop(secret, None)
            result["questions"].append(clean_option_explanations(question))
        result["vocabulary"] = (
            [{key: value for key, value in item.items() if key != "session_id"} for item in session["vocabulary"]]
            if reveal else []
        )
        return result
