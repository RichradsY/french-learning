"""Application use cases and response redaction."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date

from .content import generate_content


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


class ConflictError(Exception):
    pass


def normalize_answer(value):
    value = unicodedata.normalize("NFC", str(value)).strip().lower().replace("’", "'")
    return re.sub(r"\s+", " ", value)


class LearningService:
    def __init__(self, repository, content_provider=None, max_monthly_api_calls=70):
        self.repository = repository
        self.content_provider = content_provider
        self.max_monthly_api_calls = max_monthly_api_calls

    def get_or_create_day(self, study_date, reveal=False):
        with self.repository.generation_lock():
            session_id = self.repository.session_id_for_date(study_date)
            if session_id is None:
                source = "offline"
                generated = None
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
                        questions, vocabulary, usage = self.content_provider.generate(
                            study_date,
                            self.repository.recent_prompts(limit=None),
                            self.repository.recent_words(limit=None),
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
                questions, vocabulary = generated
                try:
                    session_id = self.repository.create_session(
                        study_date, questions, vocabulary, content_source=source
                    )
                except sqlite3.IntegrityError:
                    session_id = self.repository.session_id_for_date(study_date)
                    if session_id is None:
                        raise
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
        return self.repository.history()

    def mistakes(self):
        return self.repository.mistakes()

    def grammar_summary(self):
        return self.repository.grammar_summary()

    def vocabulary(self):
        return self.repository.all_vocabulary()

    @staticmethod
    def _present(session, reveal):
        result = {key: value for key, value in session.items() if key not in ("questions", "vocabulary")}
        result["questions"] = []
        for raw in session["questions"]:
            question = {key: value for key, value in raw.items() if key not in ("session_id", "accepted")}
            if not reveal:
                for secret in ("answer", "option_explanations", "explanation_fr", "explanation_zh", "content_hash"):
                    question.pop(secret, None)
            result["questions"].append(question)
        result["vocabulary"] = [{key: value for key, value in item.items() if key != "session_id"} for item in session["vocabulary"]]
        return result
