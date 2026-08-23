"""Validated reading/writing task shapes and offline fallbacks."""
from __future__ import annotations

import re
from copy import deepcopy

from .content import GRAMMAR

CJK = re.compile(r"[\u3400-\u9fff]")


class TaskValidationError(ValueError):
    pass


def _required_text(item, key):
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TaskValidationError(f"Missing text field: {key}")
    return value.strip()


def _validate_model_answers(value):
    if not isinstance(value, list) or len(value) != 2:
        raise TaskValidationError("Writing content requires B2 and C2 model answers")
    if [item.get("level") for item in value if isinstance(item, dict)] != ["B2", "C2"]:
        raise TaskValidationError("Writing model answers must be ordered B2 then C2")
    for model_answer in value:
        model_answer["text"] = _required_text(model_answer, "text")
        if CJK.search(model_answer["text"]):
            raise TaskValidationError("Writing model answers must contain French only")
        vocabulary = model_answer.get("vocabulary")
        if not isinstance(vocabulary, list) or not 1 <= len(vocabulary) <= 8:
            raise TaskValidationError("Each writing model answer requires translated vocabulary")
        for note in vocabulary:
            note["expression_fr"] = _required_text(note, "expression_fr")
            note["meaning_zh"] = _required_text(note, "meaning_zh")
            if CJK.search(note["expression_fr"]) or not CJK.search(note["meaning_zh"]):
                raise TaskValidationError("Writing vocabulary must pair French with Chinese")
    return value


def validate_learning_tasks(reading, writing, context):
    if not isinstance(reading, dict) or not isinstance(writing, dict):
        raise TaskValidationError("Reading and writing tasks are required")
    reading = deepcopy(reading)
    writing = deepcopy(writing)
    for field in ("title", "article_fr", "source_name", "source_url"):
        reading[field] = _required_text(reading, field)
    if CJK.search(reading["title"]) or CJK.search(reading["article_fr"]):
        raise TaskValidationError("Reading title and article must contain French only")
    if not 180 <= len(reading["article_fr"].split()) <= 450:
        raise TaskValidationError("Reading article must contain 180 to 450 words")
    allowed_urls = {item.get("url") for item in context if isinstance(item, dict)}
    if reading["source_url"] not in allowed_urls:
        raise TaskValidationError("Reading source URL was not present in fetched context")
    questions = reading.get("questions")
    if not isinstance(questions, list) or len(questions) != 4:
        raise TaskValidationError("Reading task requires four questions")
    for question in questions:
        for field in ("prompt", "answer", "explanation_fr", "explanation_zh"):
            question[field] = _required_text(question, field)
        options = question.get("options")
        if not isinstance(options, list) or len(options) != 4 or len(set(options)) != 4:
            raise TaskValidationError("Reading MCQ requires four unique options")
        if question["answer"] not in options:
            raise TaskValidationError("Reading answer must be one of the options")
        if CJK.search(question["prompt"]) or any(CJK.search(str(option)) for option in options):
            raise TaskValidationError("Reading questions and options must contain French only")
        if not CJK.search(question["explanation_zh"]):
            raise TaskValidationError("Reading question requires a Chinese explanation")
    vocabulary = reading.get("vocabulary")
    if not isinstance(vocabulary, list) or not 4 <= len(vocabulary) <= 6:
        raise TaskValidationError("Reading task requires four to six vocabulary notes")
    for item in vocabulary:
        for field in ("word", "definition_fr", "definition_zh"):
            item[field] = _required_text(item, field)
        if CJK.search(item["word"]) or not CJK.search(item["definition_zh"]):
            raise TaskValidationError("Reading vocabulary must be French with Chinese support")

    reading["time_limit_seconds"] = int(reading.get("time_limit_seconds", 480))
    if not 300 <= reading["time_limit_seconds"] <= 900:
        raise TaskValidationError("Reading time limit must be between 5 and 15 minutes")

    for field in ("title", "instructions_fr", "context_fr"):
        writing[field] = _required_text(writing, field)
        if CJK.search(writing[field]):
            raise TaskValidationError("Writing task fields must contain French only")
    if len(writing["context_fr"].split()) < 35:
        raise TaskValidationError("Writing context must define a concrete situation")
    if len(writing["instructions_fr"].split()) < 25:
        raise TaskValidationError("Writing instructions must define role, recipient and required points")
    writing["instructions_zh"] = _required_text(writing, "instructions_zh")
    if not CJK.search(writing["instructions_zh"]):
        raise TaskValidationError("Writing task requires Chinese instructions")
    writing["min_words"] = int(writing.get("min_words", 120))
    writing["max_words"] = int(writing.get("max_words", 180))
    if not 80 <= writing["min_words"] < writing["max_words"] <= 300:
        raise TaskValidationError("Writing word range is invalid")
    writing["model_answers"] = _validate_model_answers(writing.get("model_answers"))
    return reading, writing


def validate_writing_feedback(payload, answer_text=None):
    if not isinstance(payload, dict):
        raise TaskValidationError("Writing feedback must be an object")
    result = deepcopy(payload)
    score = result.get("score_total")
    if not isinstance(score, int) or not 0 <= score <= 20:
        raise TaskValidationError("Writing score must be between 0 and 20")
    for field in ("summary_fr", "summary_zh", "corrected_text"):
        result[field] = _required_text(result, field)
    if not CJK.search(result["summary_zh"]):
        raise TaskValidationError("Writing feedback requires a Chinese summary")
    dimensions = result.get("dimensions")
    expected = {"task", "cohesion", "grammar", "vocabulary"}
    if not isinstance(dimensions, dict) or set(dimensions) != expected:
        raise TaskValidationError("Writing feedback requires four score dimensions")
    for dimension in dimensions.values():
        if not isinstance(dimension, dict) or not isinstance(dimension.get("score"), int):
            raise TaskValidationError("Writing dimension score is invalid")
        if not 0 <= dimension["score"] <= 5:
            raise TaskValidationError("Writing dimension score must be between 0 and 5")
        dimension["comment_fr"] = _required_text(dimension, "comment_fr")
        dimension["comment_zh"] = _required_text(dimension, "comment_zh")
    if sum(item["score"] for item in dimensions.values()) != score:
        raise TaskValidationError("Writing dimension scores must equal total score")
    errors = result.get("errors")
    if not isinstance(errors, list) or len(errors) > 30:
        raise TaskValidationError("Writing errors must be a list of at most 30 items")
    for item in errors:
        for field in ("original", "correction", "explanation_fr", "explanation_zh", "grammar_key"):
            item[field] = _required_text(item, field)
        if item["grammar_key"] not in GRAMMAR:
            raise TaskValidationError("Writing error has an unknown grammar key")
        if answer_text is not None and item["original"] not in answer_text:
            raise TaskValidationError("Writing error must quote the submitted text exactly")
        if not CJK.search(item["explanation_zh"]):
            raise TaskValidationError("Writing error requires a Chinese explanation")
    if score == 20 and errors:
        raise TaskValidationError("Perfect writing score cannot include reported errors")

    result["model_answers"] = _validate_model_answers(result.get("model_answers"))

    guidance = result.get("optimization_guidance")
    if not isinstance(guidance, list) or not 1 <= len(guidance) <= 6:
        raise TaskValidationError("Writing feedback requires optimization guidance")
    for item in guidance:
        item["advice_fr"] = _required_text(item, "advice_fr")
        item["advice_zh"] = _required_text(item, "advice_zh")
        if CJK.search(item["advice_fr"]) or not CJK.search(item["advice_zh"]):
            raise TaskValidationError("Writing guidance must pair French with Chinese")
    return result


def offline_tasks(study_date):
    reading = {
        "title": "Les bibliothèques changent avec les nouveaux usages",
        "article_fr": " ".join([
            "Dans de nombreuses villes françaises, les bibliothèques ne sont plus seulement des lieux où l'on emprunte des livres.",
            "Elles proposent désormais des espaces de travail, des ateliers numériques et des rencontres avec des auteurs.",
            "Cette évolution répond aux habitudes d'un public qui cherche à la fois le calme, des ressources fiables et des activités collectives.",
            "Les étudiants apprécient les horaires élargis, tandis que les familles participent aux animations organisées le mercredi ou le week-end.",
            "Certaines bibliothèques prêtent aussi des instruments de musique, des jeux ou du matériel informatique.",
            "Pour les responsables, le principal défi consiste à conserver la mission culturelle du lieu tout en accueillant des usages très différents.",
            "Le silence absolu n'est donc plus la règle partout : des zones sont séparées selon les besoins.",
            "Les visiteurs peuvent choisir un espace silencieux, une salle de groupe ou un coin destiné aux enfants.",
            "Cette organisation demande des bâtiments adaptés et davantage de personnel pour accompagner le public.",
            "Malgré ces contraintes, les communes considèrent souvent la bibliothèque comme un service essentiel, notamment pour les personnes qui ne disposent pas d'un ordinateur ou d'un lieu tranquille à la maison.",
            "Ainsi, la bibliothèque moderne reste liée aux livres, mais elle devient aussi un lieu d'apprentissage, d'échange et d'inclusion.",
        ]),
        "source_name": "Contenu hors ligne contrôlé",
        "source_url": None,
        "time_limit_seconds": 480,
        "questions": [
            {"prompt": "Quelle évolution principale est décrite ?", "options": ["Les bibliothèques offrent davantage de services", "Les bibliothèques vendent leurs livres", "Les bibliothèques ferment le week-end", "Les bibliothèques remplacent les écoles"], "answer": "Les bibliothèques offrent davantage de services", "explanation_fr": "Le texte présente de nouveaux espaces, prêts et activités.", "explanation_zh": "文章介绍了新的空间、借用服务和活动。"},
            {"prompt": "Pourquoi les espaces sont-ils séparés ?", "options": ["Pour répondre à des besoins différents", "Pour réduire le nombre de visiteurs", "Pour réserver les livres aux étudiants", "Pour supprimer les activités collectives"], "answer": "Pour répondre à des besoins différents", "explanation_fr": "Chaque public peut choisir un espace adapté à son activité.", "explanation_zh": "不同使用者可以选择适合自己活动的空间。"},
            {"prompt": "Quel défi les responsables rencontrent-ils ?", "options": ["Concilier mission culturelle et nouveaux usages", "Trouver des livres anciens à vendre", "Interdire le matériel informatique", "Remplacer tout le personnel"], "answer": "Concilier mission culturelle et nouveaux usages", "explanation_fr": "Le texte nomme explicitement cet équilibre comme le principal défi.", "explanation_zh": "文章明确指出，平衡文化使命与新用途是主要挑战。"},
            {"prompt": "Quelle conclusion correspond au texte ?", "options": ["La bibliothèque devient un lieu d'inclusion", "Les livres n'ont plus aucune importance", "Seules les familles utilisent les bibliothèques", "Toutes les communes refusent cette évolution"], "answer": "La bibliothèque devient un lieu d'inclusion", "explanation_fr": "La dernière phrase insiste sur l'apprentissage, l'échange et l'inclusion.", "explanation_zh": "最后一句强调学习、交流和社会包容。"},
        ],
        "vocabulary": [
            {"word": "un usage", "definition_fr": "Une manière d'utiliser quelque chose.", "definition_zh": "用途；使用方式。"},
            {"word": "élargi", "definition_fr": "Étendu ou rendu plus large.", "definition_zh": "扩大的；延长的。"},
            {"word": "concilier", "definition_fr": "Rendre compatibles deux besoins différents.", "definition_zh": "协调；使兼容。"},
            {"word": "une contrainte", "definition_fr": "Une difficulté ou une obligation à respecter.", "definition_zh": "限制；约束。"},
        ],
    }
    writing = {
        "title": "Proposer une amélioration dans votre quartier",
        "context_fr": "Vous habitez dans un quartier où les étudiants, les familles et les personnes âgées partagent peu d’espaces calmes. La mairie prépare son budget de l’année prochaine et consulte les habitants avant de choisir un nouveau service public. Vous avez observé un problème précis dans la vie quotidienne et vous souhaitez défendre une solution réaliste.",
        "instructions_fr": "En tant qu’habitant, écrivez au service de la participation citoyenne de la mairie. Décrivez le problème et ses conséquences, proposez une solution concrète, puis expliquez au moins deux avantages pour différents habitants. Terminez par une demande claire adressée à la mairie.",
        "instructions_zh": "你以社区居民身份写信给市政府公众参与部门：描述问题及其影响，提出一个具体方案，说明它对不同居民的至少两个好处，最后提出明确请求。",
        "min_words": 120,
        "max_words": 180,
        "model_answers": [
            {
                "level": "B2",
                "text": "Madame, Monsieur,\n\nJe souhaite attirer votre attention sur le manque d’espaces calmes dans notre quartier. Les étudiants travaillent souvent dans des cafés bruyants, tandis que certaines familles ne disposent pas d’une pièce adaptée à la lecture ou aux devoirs.\n\nJe propose donc de transformer une salle municipale peu utilisée en espace d’étude partagé. Ce lieu pourrait ouvrir en soirée et le week-end, avec des tables, une connexion Internet et une petite bibliothèque. Il offrirait aux jeunes de meilleures conditions de travail et permettrait aussi aux adultes de suivre une formation en ligne. De plus, la présence d’un agent municipal garantirait le calme et la sécurité.\n\nJe vous serais reconnaissant d’étudier cette proposition et de consulter les habitants sur les horaires souhaités.\n\nJe vous prie d’agréer, Madame, Monsieur, mes salutations distinguées.",
                "vocabulary": [
                    {"expression_fr": "attirer votre attention sur", "meaning_zh": "提请您关注……"},
                    {"expression_fr": "un espace d’étude partagé", "meaning_zh": "共享学习空间"},
                    {"expression_fr": "garantir le calme", "meaning_zh": "保障安静环境"},
                ],
            },
            {
                "level": "C2",
                "text": "Madame, Monsieur,\n\nNotre quartier gagnerait à se doter d’un jardin intergénérationnel, tant les occasions de rencontre entre habitants y sont rares. Les personnes âgées souffrent parfois d’isolement, tandis que de nombreux enfants connaissent peu la nature et l’origine des aliments qu’ils consomment.\n\nL’aménagement d’un terrain municipal en potager collectif répondrait simultanément à ces deux enjeux. Des parcelles accessibles pourraient être confiées à des binômes réunissant seniors et familles. Outre la transmission de savoir-faire, ce projet favoriserait une alimentation plus durable et renforcerait les liens de voisinage. Des ateliers animés par des associations locales permettraient également d’aborder le compostage et la biodiversité.\n\nJe sollicite donc l’inscription d’une étude de faisabilité au prochain budget, suivie d’une concertation destinée à identifier le terrain le plus approprié.\n\nJe vous prie d’agréer, Madame, Monsieur, l’expression de ma considération distinguée.",
                "vocabulary": [
                    {"expression_fr": "se doter de", "meaning_zh": "配备；建设"},
                    {"expression_fr": "répondre simultanément à deux enjeux", "meaning_zh": "同时应对两个问题"},
                    {"expression_fr": "une étude de faisabilité", "meaning_zh": "可行性研究"},
                    {"expression_fr": "renforcer les liens de voisinage", "meaning_zh": "加强邻里联系"},
                ],
            },
        ],
    }
    return reading, writing
