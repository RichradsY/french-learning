"""Application use cases and response redaction."""
from __future__ import annotations

import re
import unicodedata

from .content import generate_content


class NotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


def normalize_answer(value):
    value = unicodedata.normalize("NFC", str(value)).strip().lower().replace("’", "'")
    return re.sub(r"\s+", " ", value)


class LearningService:
    def __init__(self, repository):
        self.repository = repository

    def get_or_create_day(self, study_date, reveal=False):
        session_id = self.repository.session_id_for_date(study_date)
        if session_id is None:
            questions, vocabulary = generate_content(study_date, self.repository.used_hashes())
            session_id = self.repository.create_session(study_date, questions, vocabulary)
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
        graded = []
        for question in session["questions"]:
            submitted = str(answers.get(str(question["id"]), ""))
            accepted = {normalize_answer(answer) for answer in question["accepted"]}
            graded.append((question["id"], submitted, normalize_answer(submitted) in accepted))
        self.repository.submit(session_id, graded)
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
