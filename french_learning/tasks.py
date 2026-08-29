"""Validated reading/writing task shapes and offline fallbacks."""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import date

from .content import GRAMMAR, distribute_correct_options

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
    distribute_correct_options(
        questions,
        "reading:" + "|".join(question["prompt"] for question in questions),
    )
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
    result["score_total"] = sum(item["score"] for item in dimensions.values())
    score = result["score_total"]
    errors = result.get("errors")
    if not isinstance(errors, list) or len(errors) > 30:
        raise TaskValidationError("Writing errors must be a list of at most 30 items")
    valid_errors = []
    for item in errors:
        if not isinstance(item, dict):
            continue
        try:
            for field in ("original", "correction", "explanation_fr", "explanation_zh", "grammar_key"):
                item[field] = _required_text(item, field)
        except TaskValidationError:
            continue
        if item["grammar_key"] not in GRAMMAR:
            item["grammar_key"] = "expression-ecrite"
        if answer_text is not None and item["original"] not in answer_text:
            continue
        if not CJK.search(item["explanation_zh"]):
            continue
        valid_errors.append(item)
    result["errors"] = errors = valid_errors
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


def _transport_writing():
    return {
        "title": "Améliorer les transports en commun le soir",
        "context_fr": "Dans votre ville, les bus deviennent rares après vingt heures. Les étudiants qui terminent leurs cours tard, les salariés du soir et les habitants sans voiture rencontrent des difficultés pour rentrer chez eux. La mairie prépare le prochain contrat de transport et invite les usagers à transmettre des propositions concrètes.",
        "instructions_fr": "En tant qu’usager régulier, écrivez au service municipal des mobilités. Décrivez les conséquences des horaires actuels, proposez une amélioration réaliste et expliquez ses avantages pour au moins deux catégories d’habitants. Demandez enfin une expérimentation précise.",
        "instructions_zh": "你作为公共交通的固定使用者写信给市政府交通部门：说明当前班次的影响，提出可行改进，解释它对至少两类居民的好处，并要求开展一次具体试点。",
        "min_words": 120,
        "max_words": 180,
        "model_answers": [
            {
                "level": "B2",
                "text": "Madame, Monsieur,\n\nJe souhaite attirer votre attention sur le manque de transports en commun après vingt heures. Les étudiants et les salariés qui terminent tard doivent souvent marcher longtemps ou payer un taxi. Cette situation limite également les sorties des habitants sans voiture.\n\nJe propose d’ajouter deux départs de bus entre vingt heures et minuit sur les lignes les plus fréquentées. Une expérimentation de trois mois permettrait de mesurer la demande réelle. Elle faciliterait les retours des travailleurs et des étudiants, tout en réduisant l’usage individuel de la voiture.\n\nJe vous serais reconnaissant d’étudier cette proposition et de publier les horaires d’un premier test.\n\nJe vous prie d’agréer, Madame, Monsieur, mes salutations distinguées.",
                "vocabulary": [
                    {"expression_fr": "attirer votre attention sur", "meaning_zh": "提请您关注……"},
                    {"expression_fr": "un départ de bus", "meaning_zh": "一班公交发车"},
                    {"expression_fr": "mesurer la demande réelle", "meaning_zh": "衡量实际需求"},
                ],
            },
            {
                "level": "C2",
                "text": "Madame, Monsieur,\n\nLa faiblesse de l’offre de transport en soirée ne constitue pas un simple inconfort : elle crée une inégalité entre les habitants motorisés et ceux qui dépendent du réseau public. Elle pénalise particulièrement les étudiants, les salariés aux horaires décalés et les personnes souhaitant participer à la vie culturelle.\n\nJe préconise la mise en place de deux rotations supplémentaires sur les axes les plus fréquentés, dans le cadre d’une phase pilote de trois mois. La fréquentation, le coût par trajet et la satisfaction des usagers pourraient être publiés chaque mois. Ces données permettraient d’ajuster les horaires avant toute pérennisation.\n\nJe sollicite donc l’inscription de cette expérimentation au prochain comité des mobilités.\n\nJe vous prie d’agréer, Madame, Monsieur, l’expression de ma considération distinguée.",
                "vocabulary": [
                    {"expression_fr": "les horaires décalés", "meaning_zh": "错峰工作时间"},
                    {"expression_fr": "une phase pilote", "meaning_zh": "试点阶段"},
                    {"expression_fr": "avant toute pérennisation", "meaning_zh": "在任何长期化之前"},
                ],
            },
        ],
    }


def _hybrid_work_writing():
    return {
        "title": "Proposer une organisation de travail hybride",
        "context_fr": "Votre entreprise impose désormais quatre jours de présence au bureau. Cette règle facilite certaines réunions, mais plusieurs collègues perdent beaucoup de temps dans les transports et peinent à se concentrer dans l’espace ouvert. La direction accepte d’examiner une proposition d’équipe fondée sur des objectifs mesurables.",
        "instructions_fr": "Rédigez une note à votre responsable d’équipe. Présentez clairement les limites de l’organisation actuelle, proposez un rythme hybride précis et définissez deux indicateurs permettant d’évaluer cette expérience après deux mois.",
        "instructions_zh": "请给团队负责人写一份内部建议：说明现行办公安排的问题，提出明确的混合办公节奏，并设定两个可在两个月后评估试验效果的指标。",
        "min_words": 120,
        "max_words": 180,
        "model_answers": [
            {
                "level": "B2",
                "text": "Objet : proposition d’une organisation hybride\n\nNotre présence presque quotidienne au bureau facilite les échanges, mais elle entraîne aussi de longs trajets et de nombreuses interruptions. Je propose deux jours de télétravail fixes par semaine, le mardi et le jeudi. Les réunions collectives auraient lieu les autres jours, lorsque toute l’équipe serait présente.\n\nNous pourrions tester ce fonctionnement pendant deux mois. Pour l’évaluer, comparons le nombre de projets terminés dans les délais et demandons chaque semaine aux collègues s’ils parviennent mieux à se concentrer. Si la coordination se dégrade, nous ajusterons les jours choisis.\n\nCette solution préserverait la collaboration tout en offrant de meilleures conditions de travail.",
                "vocabulary": [
                    {"expression_fr": "un rythme hybride", "meaning_zh": "混合办公节奏"},
                    {"expression_fr": "terminer dans les délais", "meaning_zh": "按时完成"},
                    {"expression_fr": "ajuster le fonctionnement", "meaning_zh": "调整运作方式"},
                ],
            },
            {
                "level": "C2",
                "text": "Objet : expérimentation d’un cadre hybride fondé sur les résultats\n\nL’obligation de présence quatre jours sur cinq répond à un besoin légitime de coordination, mais elle confond parfois visibilité et efficacité. Les trajets, le bruit et les sollicitations permanentes réduisent le temps consacré aux tâches exigeant une forte concentration.\n\nJe suggère une phase pilote de huit semaines : trois journées communes au bureau, deux journées à distance et un créneau collectif protégé pour les décisions importantes. Deux critères permettraient d’en juger objectivement : le respect des échéances et le délai moyen de réponse entre collègues. Un bref questionnaire mesurerait également la qualité de concentration.\n\nCe protocole réversible nous fournirait des données concrètes avant toute décision durable.",
                "vocabulary": [
                    {"expression_fr": "confondre visibilité et efficacité", "meaning_zh": "混淆可见度与效率"},
                    {"expression_fr": "une phase pilote", "meaning_zh": "试行阶段"},
                    {"expression_fr": "un protocole réversible", "meaning_zh": "可撤销的试行方案"},
                ],
            },
        ],
    }


def _digital_break_writing():
    return {
        "title": "Raconter une journée sans téléphone",
        "context_fr": "Un magazine francophone prépare un dossier sur l’attention et les habitudes numériques. Il invite ses lecteurs à raconter une journée réellement passée sans téléphone : ce qui les inquiétait avant l’expérience, les difficultés rencontrées et une découverte inattendue faite également au cours de la journée.",
        "instructions_fr": "Écrivez un témoignage destiné au magazine. Racontez les moments importants dans l’ordre, décrivez précisément une difficulté et une découverte positive, puis expliquez quelle habitude numérique vous souhaitez modifier à l’avenir.",
        "instructions_zh": "请为杂志写一篇亲身经历：按顺序讲述一天中的重要时刻，具体描述一个困难和一个意外的积极发现，并说明今后想改变哪一种数字使用习惯。",
        "min_words": 120,
        "max_words": 180,
        "model_answers": [
            {
                "level": "B2",
                "text": "Samedi dernier, j’ai laissé mon téléphone éteint dans un tiroir. Au début, j’étais inquiet : je craignais de manquer un message important et je regardais machinalement ma poche. La difficulté principale est apparue lorsque j’ai voulu retrouver l’adresse d’un ami. J’ai dû demander mon chemin, ce qui m’a permis de discuter avec une commerçante très sympathique.\n\nSans notifications, j’ai lu pendant une heure sans m’interrompre, puis j’ai préparé le dîner avec mes proches. La journée m’a semblé plus longue et plus calme. Je ne souhaite pas abandonner mon téléphone, mais je vais désormais couper les notifications le soir et le laisser hors de la chambre pendant la nuit.",
                "vocabulary": [
                    {"expression_fr": "regarder machinalement", "meaning_zh": "下意识地查看"},
                    {"expression_fr": "sans m’interrompre", "meaning_zh": "不中断地"},
                    {"expression_fr": "couper les notifications", "meaning_zh": "关闭通知"},
                ],
            },
            {
                "level": "C2",
                "text": "Je m’attendais à une journée paisible ; les premières heures ont surtout révélé l’étendue de mes automatismes. À chaque attente, ma main cherchait un écran absent. Le moment le plus délicat fut l’organisation d’un rendez-vous dont je n’avais mémorisé ni l’adresse ni le numéro. Faute de solution immédiate, j’ai accepté d’arriver plus tard et d’expliquer simplement la situation.\n\nCette contrainte a pourtant ouvert un espace inattendu. Dans le train, au lieu de faire défiler des nouvelles oubliées aussitôt, j’ai observé le paysage et terminé un livre commencé depuis des semaines. Je retiens moins une opposition entre connexion et déconnexion qu’un besoin de choix conscient. Dorénavant, je réserverai deux plages précises aux messages plutôt que de rester disponible en permanence.",
                "vocabulary": [
                    {"expression_fr": "révéler l’étendue de", "meaning_zh": "揭示……的程度"},
                    {"expression_fr": "faute de solution immédiate", "meaning_zh": "由于没有即时解决办法"},
                    {"expression_fr": "rester disponible en permanence", "meaning_zh": "始终保持在线可联系"},
                ],
            },
        ],
    }


def _slow_travel_writing():
    return {
        "title": "Défendre un voyage en train plutôt qu’en avion",
        "context_fr": "Sur un forum de voyage, un membre prépare un séjour dans une capitale européenne. L’avion est moins cher et plus rapide, tandis que le train exige une journée entière et une correspondance. Vous avez déjà effectué un trajet comparable et souhaitez répondre sans ignorer les contraintes de budget et de temps.",
        "instructions_fr": "Publiez une réponse argumentée sur le forum. Comparez concrètement les deux options, racontez un élément de votre propre expérience, recommandez un choix adapté à ce voyageur et proposez une manière de réduire l’inconvénient principal.",
        "instructions_zh": "请在旅行论坛发表有论据的回复：具体比较两种交通方式，讲述一段自己的类似经历，向这位旅行者推荐一个选择，并提出减轻其主要缺点的办法。",
        "min_words": 120,
        "max_words": 180,
        "model_answers": [
            {
                "level": "B2",
                "text": "À ta place, je choisirais le train si le voyage dure au moins une semaine. L’avion paraît plus rapide, mais il faut ajouter le trajet vers l’aéroport, les contrôles et l’attente. En train, on arrive généralement au centre-ville et l’on peut lire, travailler ou se lever pendant le trajet.\n\nJ’ai fait un voyage similaire l’an dernier. La correspondance m’inquiétait, pourtant elle s’est bien passée et le paysage a rendu le déplacement agréable. Le principal problème reste le prix. Pour le réduire, je conseille de réserver tôt et de comparer les cartes de réduction. Si ton séjour ne dure que deux jours, l’avion reste compréhensible ; sinon, le train transforme déjà le trajet en partie du voyage.",
                "vocabulary": [
                    {"expression_fr": "À ta place", "meaning_zh": "如果我是你"},
                    {"expression_fr": "ajouter le trajet", "meaning_zh": "把接驳路程也算进去"},
                    {"expression_fr": "réserver tôt", "meaning_zh": "提前预订"},
                ],
            },
            {
                "level": "C2",
                "text": "Le gain de temps affiché par l’avion mérite d’être relativisé : rejoindre un aéroport périphérique, franchir les contrôles puis attendre l’embarquement réduit sensiblement l’écart réel. Le train demeure plus long, mais ce temps est en partie disponible pour lire, travailler ou simplement se reposer.\n\nLors d’un trajet comparable, j’avais choisi une correspondance de quarante minutes. Elle m’a évité une nuit d’hôtel et m’a fait découvrir un itinéraire que je n’aurais jamais envisagé. Je recommanderais donc le rail pour un séjour d’une semaine, à condition d’anticiper l’achat. Une réservation fractionnée et une nuit à bord peuvent atténuer à la fois le coût et la durée ressentie. Pour un week-end très court, la contrainte temporelle justifierait l’avion.",
                "vocabulary": [
                    {"expression_fr": "mériter d’être relativisé", "meaning_zh": "值得被重新衡量"},
                    {"expression_fr": "réduire sensiblement l’écart", "meaning_zh": "明显缩小差距"},
                    {"expression_fr": "atténuer une contrainte", "meaning_zh": "减轻限制因素"},
                ],
            },
        ],
    }


def _festival_review_writing():
    return {
        "title": "Évaluer un festival culturel local",
        "context_fr": "Vous avez participé à la première édition d’un festival réunissant concerts, cinéma et ateliers dans plusieurs lieux de votre région. L’ambiance était chaleureuse et la programmation variée, mais les horaires se chevauchaient et les informations pour rejoindre les différents sites étaient parfois difficiles à trouver.",
        "instructions_fr": "Rédigez une critique pour le journal culturel régional. Présentez deux réussites avec des exemples, analysez un problème d’organisation, proposez une amélioration réalisable et dites clairement si vous recommandez une prochaine édition.",
        "instructions_zh": "请为地方文化报写一篇评论：用例子说明两个亮点，分析一个组织问题，提出一项可行改进，并明确说明你是否推荐参加下一届。",
        "min_words": 120,
        "max_words": 180,
        "model_answers": [
            {
                "level": "B2",
                "text": "La première édition de ce festival a réussi à créer une véritable rencontre entre des publics différents. Le concert d’ouverture était accessible aux familles, tandis que l’atelier de cinéma permettait aux adolescents de réaliser une courte scène. J’ai aussi apprécié les petits lieux, qui favorisaient les échanges avec les artistes.\n\nL’organisation doit cependant progresser. Deux activités importantes avaient lieu à la même heure et le plan des navettes était difficile à trouver. L’an prochain, une application simple ou un programme papier unique devrait regrouper horaires, adresses et temps de déplacement. Malgré ce défaut, je recommande le festival : sa programmation est originale et son accueil chaleureux. Avec une information plus claire, la prochaine édition pourrait devenir un rendez-vous incontournable.",
                "vocabulary": [
                    {"expression_fr": "favoriser les échanges", "meaning_zh": "促进交流"},
                    {"expression_fr": "regrouper les informations", "meaning_zh": "汇总信息"},
                    {"expression_fr": "un rendez-vous incontournable", "meaning_zh": "不容错过的固定活动"},
                ],
            },
            {
                "level": "C2",
                "text": "Pour une première édition, le festival impressionne par la cohérence de son ambition : faire dialoguer musique, cinéma et pratiques amateurs sans réserver la culture aux seuls initiés. Le concert acoustique dans l’ancienne gare et l’atelier de montage ouvert aux lycéens illustraient particulièrement cette réussite. La proximité avec les artistes donnait aux rencontres une qualité rarement obtenue dans de grandes salles.\n\nCette richesse se retournait parfois contre l’événement : plusieurs propositions se chevauchaient, alors que les indications entre les sites restaient lacunaires. Un parcours thématique assorti de temps de déplacement réalistes résoudrait une bonne partie du problème. Je recommande néanmoins vivement une prochaine édition. À condition de clarifier la circulation du public, ce festival possède déjà une identité forte et inclusive.",
                "vocabulary": [
                    {"expression_fr": "faire dialoguer plusieurs disciplines", "meaning_zh": "让多个领域形成对话"},
                    {"expression_fr": "des indications lacunaires", "meaning_zh": "不完整的指引"},
                    {"expression_fr": "assorti de", "meaning_zh": "配有；附带"},
                ],
            },
        ],
    }


def _repair_cafe_reading():
    return {
        "title": "Les cafés de réparation prolongent la vie des objets",
        "article_fr": " ".join([
            "Dans plusieurs quartiers, des associations organisent des cafés de réparation où les habitants apportent un appareil en panne.",
            "Autour d'une table, des bénévoles les aident à comprendre l'origine du problème avant de tenter une réparation.",
            "Il ne s'agit pas d'un service commercial : le propriétaire participe, observe les gestes et apprend à utiliser quelques outils.",
            "Un grille-pain, une lampe ou un vêtement peut ainsi retrouver une seconde vie au lieu d'être immédiatement remplacé.",
            "Cette démarche réduit les déchets, mais elle répond aussi à un besoin de transmission.",
            "Certaines personnes savent recoudre un tissu, tandis que d'autres maîtrisent l'électronique ou la menuiserie.",
            "Le diagnostic reste parfois plus utile que la réparation elle-même, car une pièce introuvable ou un appareil dangereux oblige à renoncer.",
            "Les animateurs insistent donc sur la sécurité et refusent les interventions qui présenteraient un risque.",
            "Le succès de ces rencontres dépend également du matériel disponible et du nombre de bénévoles.",
            "Pour éviter une attente excessive, plusieurs associations proposent désormais une inscription préalable et demandent aux participants de décrire la panne.",
            "Même lorsqu'un objet ne peut pas être sauvé, son propriétaire repart souvent avec une meilleure compréhension de sa fabrication.",
            "Le café de réparation devient ainsi un lieu d'apprentissage collectif autant qu'un moyen de consommer autrement.",
        ]),
        "source_name": "Contenu hors ligne contrôlé",
        "source_url": None,
        "time_limit_seconds": 480,
        "questions": [
            {"prompt": "Quelle particularité distingue le café de réparation d'un service commercial ?", "options": ["Le propriétaire participe à la réparation", "Tous les appareils sont réparés gratuitement", "Les bénévoles vendent des pièces neuves", "Le propriétaire laisse son objet puis repart"], "answer": "Le propriétaire participe à la réparation", "explanation_fr": "Le texte précise que le propriétaire observe, participe et apprend.", "explanation_zh": "文章说明物主会参与、观察并学习维修。"},
            {"prompt": "Pourquoi les bénévoles renoncent-ils parfois à intervenir ?", "options": ["La réparation présenterait un danger", "L'objet est trop facile à réparer", "Le propriétaire connaît déjà les outils", "L'association préfère vendre un appareil"], "answer": "La réparation présenterait un danger", "explanation_fr": "La sécurité peut imposer de refuser certaines interventions.", "explanation_zh": "出于安全原因，有些维修必须被拒绝。"},
            {"prompt": "À quoi sert l'inscription préalable ?", "options": ["À limiter l'attente et préparer le diagnostic", "À garantir que chaque objet sera sauvé", "À réserver l'activité aux professionnels", "À remplacer les bénévoles absents"], "answer": "À limiter l'attente et préparer le diagnostic", "explanation_fr": "Décrire la panne en avance aide l'équipe à organiser la rencontre.", "explanation_zh": "提前描述故障有助于安排活动并减少等待。"},
            {"prompt": "Quelle idée résume la conclusion ?", "options": ["Réparer permet aussi d'apprendre collectivement", "Seuls les objets électroniques méritent une réparation", "Le diagnostic est toujours inutile", "Les ateliers encouragent à acheter davantage"], "answer": "Réparer permet aussi d'apprendre collectivement", "explanation_fr": "Le dernier paragraphe associe consommation différente et apprentissage collectif.", "explanation_zh": "结尾把不同的消费方式与集体学习联系起来。"},
        ],
        "vocabulary": [
            {"word": "une panne", "definition_fr": "Un arrêt de fonctionnement.", "definition_zh": "故障。"},
            {"word": "renoncer", "definition_fr": "Décider de ne pas poursuivre.", "definition_zh": "放弃。"},
            {"word": "un diagnostic", "definition_fr": "L'identification de la cause d'un problème.", "definition_zh": "诊断；故障判断。"},
            {"word": "prolonger", "definition_fr": "Faire durer plus longtemps.", "definition_zh": "延长。"},
        ],
    }


def _food_waste_reading():
    return {
        "title": "Les cantines cherchent à réduire le gaspillage alimentaire",
        "article_fr": " ".join([
            "Dans les cantines scolaires, réduire le gaspillage ne consiste pas seulement à servir des portions plus petites.",
            "Les équipes commencent souvent par peser les restes pendant plusieurs semaines afin de comprendre ce qui est réellement jeté.",
            "Elles distinguent les aliments non servis, qui peuvent parfois être conservés, de ceux laissés dans les assiettes.",
            "Ces observations révèlent des causes variées : un plat peu apprécié, un temps de déjeuner trop court ou une quantité identique pour tous les âges.",
            "Certaines communes proposent alors deux tailles de portion et permettent aux élèves de se resservir.",
            "D'autres présentent les ingrédients avant le repas ou associent les enfants au choix de quelques menus.",
            "L'objectif n'est pas de supprimer toute nouveauté, car la cantine doit aussi faire découvrir des goûts différents.",
            "Il faut plutôt trouver un équilibre entre découverte, nutrition et quantité consommée.",
            "La cuisine peut également adapter ses commandes grâce aux mesures recueillies, ce qui réduit les dépenses sans diminuer la qualité.",
            "Cependant, les responsables soulignent qu'une action isolée produit rarement un effet durable.",
            "Les résultats s'améliorent lorsque cuisiniers, personnels de service, enseignants et élèves comprennent les chiffres et participent aux décisions.",
            "Le gaspillage devient alors un sujet pédagogique concret, lié à la fois au budget, aux ressources naturelles et aux habitudes quotidiennes.",
        ]),
        "source_name": "Contenu hors ligne contrôlé",
        "source_url": None,
        "time_limit_seconds": 480,
        "questions": [
            {"prompt": "Pourquoi les cantines pèsent-elles d'abord les restes ?", "options": ["Pour identifier précisément les sources du gaspillage", "Pour supprimer immédiatement tous les menus nouveaux", "Pour donner la même portion à chaque élève", "Pour remplacer le personnel de cuisine"], "answer": "Pour identifier précisément les sources du gaspillage", "explanation_fr": "Les mesures permettent de distinguer les types de restes et leurs causes.", "explanation_zh": "称重可以区分剩余食物的类型并找出原因。"},
            {"prompt": "Quel système adapte mieux la quantité aux besoins ?", "options": ["Proposer deux portions avec la possibilité de se resservir", "Réduire tous les repas de moitié", "Interdire aux élèves de choisir", "Servir uniquement les plats déjà connus"], "answer": "Proposer deux portions avec la possibilité de se resservir", "explanation_fr": "Cette solution tient compte des appétits différents.", "explanation_zh": "这种方案考虑了不同学生的食量。"},
            {"prompt": "Quel équilibre la cantine doit-elle rechercher ?", "options": ["Découverte, nutrition et quantité consommée", "Prix élevé, rapidité et publicité", "Silence, discipline et horaires", "Variété, emballage et transport"], "answer": "Découverte, nutrition et quantité consommée", "explanation_fr": "Ces trois objectifs sont explicitement associés dans le texte.", "explanation_zh": "文章明确把尝试新口味、营养和实际食用量联系在一起。"},
            {"prompt": "Quand les actions deviennent-elles plus durables ?", "options": ["Lorsque tous les acteurs participent aux décisions", "Lorsqu'une seule mesure est appliquée", "Lorsque les chiffres restent secrets", "Lorsque les élèves sont exclus du projet"], "answer": "Lorsque tous les acteurs participent aux décisions", "explanation_fr": "Le texte insiste sur la compréhension et la participation collectives.", "explanation_zh": "文章强调共同理解数据并参与决策。"},
        ],
        "vocabulary": [
            {"word": "le gaspillage", "definition_fr": "L'utilisation inutile ou la perte d'une ressource.", "definition_zh": "浪费。"},
            {"word": "un reste", "definition_fr": "Ce qui n'a pas été consommé.", "definition_zh": "剩余食物。"},
            {"word": "se resservir", "definition_fr": "Prendre une nouvelle portion.", "definition_zh": "再添一份。"},
            {"word": "recueillir", "definition_fr": "Rassembler des informations.", "definition_zh": "收集。"},
        ],
    }


def _urban_trees_reading():
    return {
        "title": "Les arbres urbains aident les villes à supporter la chaleur",
        "article_fr": " ".join([
            "Lors des périodes de forte chaleur, les rues minérales accumulent l'énergie du soleil et restent chaudes après la tombée de la nuit.",
            "Les arbres peuvent limiter ce phénomène grâce à l'ombre de leurs feuilles et à l'eau qu'ils libèrent dans l'air.",
            "La température ressentie baisse surtout lorsque plusieurs arbres forment un parcours continu entre les logements, les écoles et les transports.",
            "Planter un seul arbre sur une place entièrement bétonnée apporte donc moins de bénéfices qu'un réseau végétal bien organisé.",
            "Les services municipaux doivent cependant choisir des espèces adaptées au climat futur, au sol disponible et au manque d'eau.",
            "Une jeune plantation exige un arrosage régulier pendant plusieurs années avant de devenir suffisamment résistante.",
            "Les racines ont aussi besoin d'espace pour se développer sans endommager les trottoirs ni les réseaux souterrains.",
            "Pour cette raison, certaines villes retirent des surfaces imperméables autour des troncs et récupèrent l'eau de pluie.",
            "Les habitants peuvent participer en signalant les arbres fragiles ou en aidant à arroser pendant les épisodes secs.",
            "Cette mobilisation ne remplace pas l'entretien professionnel, mais elle améliore la surveillance du patrimoine végétal.",
            "Une politique efficace associe ainsi plantation, protection des arbres anciens et transformation progressive des rues.",
            "L'objectif n'est pas seulement esthétique : il s'agit de rendre les déplacements quotidiens plus supportables et les quartiers plus résistants aux chaleurs futures.",
        ]),
        "source_name": "Contenu hors ligne contrôlé",
        "source_url": None,
        "time_limit_seconds": 480,
        "questions": [
            {"prompt": "Comment les arbres réduisent-ils principalement la chaleur urbaine ?", "options": ["Par leur ombre et l'eau libérée dans l'air", "En réfléchissant toute la lumière vers les bâtiments", "En supprimant les réseaux souterrains", "En augmentant la circulation automobile"], "answer": "Par leur ombre et l'eau libérée dans l'air", "explanation_fr": "Le texte associe l'ombre des feuilles et la libération d'eau.", "explanation_zh": "文章把降温作用归因于树荫和树木向空气中释放的水分。"},
            {"prompt": "Pourquoi faut-il prévoir de l'espace autour des racines ?", "options": ["Pour éviter des dégâts et permettre leur développement", "Pour empêcher tout arrosage", "Pour accélérer la chute des feuilles", "Pour réserver le trottoir aux voitures"], "answer": "Pour éviter des dégâts et permettre leur développement", "explanation_fr": "Des racines confinées peuvent mal pousser ou abîmer les aménagements.", "explanation_zh": "根系需要空间生长，否则可能损坏人行道或地下设施。"},
            {"prompt": "Quel rôle les habitants peuvent-ils jouer ?", "options": ["Signaler les arbres fragiles et aider ponctuellement", "Remplacer entièrement les professionnels", "Choisir seuls toutes les espèces", "Couper les arbres anciens"], "answer": "Signaler les arbres fragiles et aider ponctuellement", "explanation_fr": "La participation complète la surveillance et l'arrosage sans remplacer les équipes.", "explanation_zh": "居民可协助报告脆弱树木和临时浇水，但不取代专业团队。"},
            {"prompt": "Quelle stratégie générale le texte recommande-t-il ?", "options": ["Associer plantation, protection et transformation des rues", "Planter uniquement sur les grandes places", "Privilégier l'esthétique à la résistance", "Attendre que les arbres poussent naturellement"], "answer": "Associer plantation, protection et transformation des rues", "explanation_fr": "La conclusion présente ces trois actions comme complémentaires.", "explanation_zh": "结论强调种植、保护老树和改造街道三者应结合。"},
        ],
        "vocabulary": [
            {"word": "accumuler", "definition_fr": "Conserver progressivement une quantité.", "definition_zh": "积累。"},
            {"word": "imperméable", "definition_fr": "Qui ne laisse pas passer l'eau.", "definition_zh": "不透水的。"},
            {"word": "un patrimoine végétal", "definition_fr": "L'ensemble des arbres et plantes à préserver.", "definition_zh": "需要保护的城市植物资产。"},
            {"word": "résistant", "definition_fr": "Capable de supporter une difficulté durable.", "definition_zh": "有抵抗力的。"},
        ],
    }


def _tool_library_reading():
    return {
        "title": "Les bibliothèques d'objets favorisent le partage du matériel",
        "article_fr": " ".join([
            "Une perceuse, une machine à coudre ou un appareil de nettoyage reste souvent inutilisé pendant la majeure partie de l'année.",
            "Pour éviter que chaque foyer achète le même équipement, des associations créent des bibliothèques d'objets accessibles avec une adhésion modeste.",
            "Le fonctionnement ressemble à celui d'une bibliothèque classique : les membres réservent un objet, l'empruntent pour quelques jours puis le rapportent.",
            "Avant chaque prêt, un bénévole vérifie son état et explique les principales règles de sécurité.",
            "Certains lieux organisent également des ateliers afin que les utilisateurs apprennent à manipuler correctement les outils.",
            "Le partage réduit les dépenses individuelles et limite la fabrication d'appareils rarement employés.",
            "Il permet aussi de tester un équipement avant de décider si un achat personnel est réellement nécessaire.",
            "Cette organisation demande néanmoins un inventaire précis, un espace de stockage et du temps pour entretenir le matériel.",
            "Lorsqu'un objet revient en retard ou abîmé, les membres suivants ne peuvent plus respecter leur propre projet.",
            "Les associations établissent donc des règles claires et demandent parfois une caution pour les appareils coûteux.",
            "Elles suivent surtout le nombre de prêts et la fréquence des réparations afin de choisir les objets les plus utiles.",
            "Au-delà de l'économie réalisée, ces lieux créent une culture de responsabilité partagée autour de biens utilisés collectivement.",
        ]),
        "source_name": "Contenu hors ligne contrôlé",
        "source_url": None,
        "time_limit_seconds": 480,
        "questions": [
            {"prompt": "Quel problème les bibliothèques d'objets cherchent-elles à résoudre ?", "options": ["L'achat individuel de matériel peu utilisé", "Le manque de livres dans les quartiers", "La fermeture des magasins de vêtements", "L'absence de transports publics"], "answer": "L'achat individuel de matériel peu utilisé", "explanation_fr": "Le texte part du constat que beaucoup d'appareils servent rarement.", "explanation_zh": "文章指出许多设备很少使用，却被每户分别购买。"},
            {"prompt": "Que se passe-t-il avant chaque prêt ?", "options": ["Un bénévole contrôle l'objet et rappelle la sécurité", "L'objet est vendu au membre", "Le membre doit réparer un autre appareil", "L'association supprime sa fiche d'inventaire"], "answer": "Un bénévole contrôle l'objet et rappelle la sécurité", "explanation_fr": "Le contrôle et les explications précèdent la remise du matériel.", "explanation_zh": "借出前，志愿者会检查设备并说明安全规则。"},
            {"prompt": "Pourquoi les retards gênent-ils le fonctionnement ?", "options": ["Ils empêchent les emprunteurs suivants de réaliser leur projet", "Ils augmentent immédiatement le prix des outils", "Ils rendent l'adhésion gratuite", "Ils suppriment le besoin de stockage"], "answer": "Ils empêchent les emprunteurs suivants de réaliser leur projet", "explanation_fr": "Une réservation dépend du retour ponctuel de l'emprunt précédent.", "explanation_zh": "下一位使用者的计划依赖上一位按时归还。"},
            {"prompt": "Que souligne le dernier paragraphe au sujet du partage ?", "options": ["Le partage exige une responsabilité collective", "Tous les objets doivent devenir gratuits", "L'entretien professionnel est inutile", "Les achats personnels doivent être interdits"], "answer": "Le partage exige une responsabilité collective", "explanation_fr": "Le dernier paragraphe insiste sur la responsabilité autour des biens communs.", "explanation_zh": "结尾强调共同使用物品需要集体责任。"},
        ],
        "vocabulary": [
            {"word": "une adhésion", "definition_fr": "L'inscription à une association ou à un service.", "definition_zh": "会员资格；加入。"},
            {"word": "un inventaire", "definition_fr": "Une liste détaillée des objets disponibles.", "definition_zh": "库存清单。"},
            {"word": "une caution", "definition_fr": "Une somme garantie, rendue si tout se passe bien.", "definition_zh": "押金。"},
            {"word": "ponctuel", "definition_fr": "Qui respecte l'heure ou le délai prévu.", "definition_zh": "准时的。"},
        ],
    }


def _school_garden_reading():
    return {
        "title": "Les jardins scolaires transforment la manière d'apprendre",
        "article_fr": " ".join([
            "Dans certaines écoles, une partie de la cour est transformée en jardin pédagogique cultivé par plusieurs classes.",
            "Les élèves y sèment des graines, observent la croissance des plantes et récoltent parfois des légumes destinés à un atelier de cuisine.",
            "Ce projet ne remplace pas les cours traditionnels, mais il donne une forme concrète à plusieurs connaissances.",
            "En sciences, les enfants étudient les besoins des végétaux, les insectes et la décomposition de la matière organique.",
            "En mathématiques, ils mesurent les parcelles, comparent les récoltes et organisent un calendrier d'arrosage.",
            "Le jardin développe également la coopération, car chaque groupe dépend du travail réalisé par les autres semaines après semaine.",
            "Les enseignants doivent toutefois prévoir des activités adaptées aux saisons et aux périodes de vacances.",
            "Une plantation fragile peut disparaître si personne ne l'arrose pendant plusieurs jours de chaleur.",
            "Certaines écoles associent donc les familles ou une association de quartier à l'entretien estival.",
            "Elles choisissent aussi des espèces locales qui demandent moins d'eau et résistent mieux aux conditions du terrain.",
            "Même une petite surface peut servir, à condition de fixer des objectifs réalistes et d'observer régulièrement les résultats.",
            "Le succès du jardin se mesure moins à la quantité produite qu'à la curiosité, à la patience et aux compétences acquises par les élèves.",
        ]),
        "source_name": "Contenu hors ligne contrôlé",
        "source_url": None,
        "time_limit_seconds": 480,
        "questions": [
            {"prompt": "Comment le jardin complète-t-il les cours ?", "options": ["Il rend plusieurs connaissances concrètes", "Il remplace toutes les matières scolaires", "Il réduit le nombre d'enseignants", "Il fournit tous les repas de l'école"], "answer": "Il rend plusieurs connaissances concrètes", "explanation_fr": "Le jardin permet d'appliquer des notions de sciences et de mathématiques.", "explanation_zh": "花园让科学和数学知识变得具体可操作。"},
            {"prompt": "Pourquoi la coopération est-elle nécessaire ?", "options": ["Le travail d'un groupe influence les suivants", "Chaque élève possède une parcelle secrète", "Les plantes poussent uniquement en groupe", "Les familles donnent toutes les réponses"], "answer": "Le travail d'un groupe influence les suivants", "explanation_fr": "L'entretien régulier crée une dépendance entre les groupes successifs.", "explanation_zh": "持续养护使不同小组的工作相互依赖。"},
            {"prompt": "Comment certaines écoles organisent-elles l'été ?", "options": ["Elles sollicitent les familles ou une association", "Elles déplacent le jardin dans une salle", "Elles arrêtent définitivement le projet", "Elles remplacent les plantes par du plastique"], "answer": "Elles sollicitent les familles ou une association", "explanation_fr": "Des partenaires peuvent assurer l'entretien pendant les vacances.", "explanation_zh": "学校会请家庭或社区协会在假期协助养护。"},
            {"prompt": "Quel est le principal critère de réussite ?", "options": ["Les apprentissages et la curiosité des élèves", "Le poids maximal de la récolte", "La taille exacte du terrain", "Le prix de vente des légumes"], "answer": "Les apprentissages et la curiosité des élèves", "explanation_fr": "La conclusion privilégie les compétences acquises à la quantité produite.", "explanation_zh": "结尾认为学习成果和好奇心比收获数量更重要。"},
        ],
        "vocabulary": [
            {"word": "semer", "definition_fr": "Mettre des graines dans la terre.", "definition_zh": "播种。"},
            {"word": "une parcelle", "definition_fr": "Une petite partie délimitée d'un terrain.", "definition_zh": "一小块土地。"},
            {"word": "la récolte", "definition_fr": "Les produits recueillis après la culture.", "definition_zh": "收获；收成。"},
            {"word": "acquérir", "definition_fr": "Obtenir progressivement une connaissance ou une capacité.", "definition_zh": "获得；习得。"},
        ],
    }


def offline_tasks(study_date, avoid_writing_topics=(), avoid_reading_topics=()):
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
    readings = [
        reading,
        _repair_cafe_reading(),
        _food_waste_reading(),
        _urban_trees_reading(),
        _tool_library_reading(),
        _school_garden_reading(),
    ]
    used_reading_titles = {
        str(item.get("title", "")).casefold().strip()
        for item in avoid_reading_topics
        if isinstance(item, dict)
    }
    start = date.fromisoformat(study_date).toordinal() % len(readings)
    ordered_readings = readings[start:] + readings[:start]
    reading = next(
        (
            candidate for candidate in ordered_readings
            if candidate["title"].casefold() not in used_reading_titles
        ),
        ordered_readings[0],
    )
    distribute_correct_options(reading["questions"], f"{study_date}:reading-options")
    candidates = [
        _transport_writing(),
        writing,
        _hybrid_work_writing(),
        _slow_travel_writing(),
        _digital_break_writing(),
        _festival_review_writing(),
    ]
    used_titles = {
        str(topic.get("title", "")).casefold().strip()
        for topic in avoid_writing_topics
        if isinstance(topic, dict)
    }
    start = date.fromisoformat(study_date).toordinal() % len(candidates)
    ordered = candidates[start:] + candidates[:start]
    writing = next(
        (candidate for candidate in ordered if candidate["title"].casefold() not in used_titles),
        ordered[0],
    )
    return reading, writing
