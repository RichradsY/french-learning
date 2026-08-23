"""Controlled B1 content pools and deterministic daily selection."""
from __future__ import annotations

import hashlib
import random
from copy import deepcopy


def _mcq(prompt, options, answer, grammar_key, fr, zh, reasons):
    return {
        "kind": "mcq", "prompt": prompt, "options": options, "answer": answer,
        "accepted": [answer], "grammar_key": grammar_key,
        "explanation_fr": fr, "explanation_zh": zh,
        "option_explanations": {
            option: f"{reasons[index]} " + (
                "正确：该选项符合本句的语法与语义。"
                if option == answer
                else "不正确：请根据前述法语说明辨别其时态、句法或语义问题。"
            )
            for index, option in enumerate(options)
        },
    }


def _fill(prompt, answer, grammar_key, fr, zh, accepted=None):
    return {
        "kind": "fill", "prompt": prompt, "options": [], "answer": answer,
        "accepted": accepted or [answer], "grammar_key": grammar_key,
        "explanation_fr": fr, "explanation_zh": zh, "option_explanations": {},
    }


MCQ = [
    _mcq("Hier, nous ___ le musée avant sa fermeture.", ["avons visité", "visitons", "visiterons", "visitions"], "avons visité", "passe-compose", "Une action terminée hier se met au passé composé.", "昨天已完成的动作使用复合过去时。", ["Correct : action achevée.", "Présent, donc incompatible avec « hier ».", "Futur, donc incompatible avec le passé.", "Imparfait : décrit plutôt une habitude ou un arrière-plan."]),
    _mcq("Si j'avais plus de temps, je ___ un cours de cuisine.", ["suivrais", "suivrai", "suivais", "ai suivi"], "suivrais", "conditionnel", "Après « si + imparfait », la conséquence est au conditionnel présent.", "si 加未完成过去时，结果句使用条件式现在时。", ["Correct : conditionnel présent.", "Futur simple interdit dans cette structure.", "Imparfait répéterait la condition.", "Passé composé exprime un fait accompli."]),
    _mcq("C'est le livre ___ je t'ai parlé.", ["dont", "que", "qui", "où"], "dont", "pronoms-relatifs", "Le verbe « parler de » exige le pronom relatif « dont ».", "parler de 中的 de 由关系代词 dont 替代。", ["Correct : remplace « de ce livre ».", "« que » remplace un complément direct.", "« qui » remplace le sujet.", "« où » indique un lieu ou un moment."]),
    _mcq("Elle habite à Lyon ___ trois ans.", ["depuis", "pendant", "il y a", "dans"], "depuis", "temps-prepositions", "« Depuis » relie une action commencée dans le passé au présent.", "depuis 表示从过去开始并持续到现在。", ["Correct : la situation continue.", "« pendant » indique une durée achevée ou délimitée.", "« il y a » situe un événement passé.", "« dans » situe un événement futur."]),
    _mcq("Il faut que vous ___ ce formulaire aujourd'hui.", ["remplissiez", "remplissez", "remplirez", "rempliriez"], "remplissiez", "subjonctif", "« Il faut que » demande le subjonctif.", "il faut que 后使用虚拟式。", ["Correct : subjonctif présent.", "Indicatif présent, incorrect après cette nécessité.", "Futur simple, incorrect ici.", "Conditionnel présent, incorrect ici."]),
    _mcq("Nous n'avons ___ compris cette explication.", ["pas encore", "encore pas", "plus encore", "jamais pas"], "pas encore", "negation", "Au passé composé, « pas encore » encadre le participe avec l'auxiliaire.", "复合过去时中 pas encore 表示“还没有”。", ["Correct : ordre naturel de la négation.", "Ordre non standard.", "Association contradictoire ici.", "Double négation incorrecte."]),
    _mcq("Paul prête son vélo à Léa. Il ___ prête son vélo.", ["lui", "la", "leur", "y"], "lui", "pronoms-complements", "Le complément indirect singulier « à Léa » devient « lui ».", "间接宾语 à Léa 用 lui 替代。", ["Correct : COI singulier.", "« la » est un complément direct féminin.", "« leur » est un COI pluriel.", "« y » remplace surtout un lieu ou « à + chose »."]),
    _mcq("Nous partirons ___ la réunion sera terminée.", ["dès que", "malgré", "afin de", "pourtant"], "dès que", "connecteurs", "« Dès que » introduit le moment qui déclenche le départ.", "dès que 表示“一……就……”。", ["Correct : connecteur temporel.", "« malgré » introduit un nom, pas cette proposition.", "« afin de » demande un infinitif.", "« pourtant » marque une opposition indépendante."]),
    _mcq("Cette solution est ___ que la précédente.", ["meilleure", "plus bonne", "la meilleure", "mieux"], "meilleure", "comparatif", "Le comparatif de l'adjectif « bon » est « meilleur ».", "形容词 bon 的比较级是不规则形式 meilleur。", ["Correct : comparatif adjectival.", "Forme non standard.", "Superlatif, pas comparatif.", "« mieux » compare un verbe ou une manière."]),
    _mcq("Avant de sortir, elle ___ toutes les fenêtres.", ["a fermé", "est fermée", "fermait", "fermera"], "a fermé", "passe-compose", "La fermeture est une action ponctuelle accomplie avant la sortie.", "关窗是出去前完成的瞬时动作。", ["Correct : passé composé avec « avoir ».", "Forme passive ou état, et mauvais auxiliaire.", "Imparfait sans contexte d'habitude.", "Futur incompatible avec le récit passé implicite."]),
    _mcq("Je cherche un appartement ___ ait un balcon.", ["qui", "que", "dont", "lequel"], "qui", "subjonctif", "Après un antécédent recherché et incertain, « qui » est sujet de « ait » au subjonctif.", "寻找尚不确定存在的房子时，关系从句可用虚拟式，qui 作主语。", ["Correct : sujet de « ait ».", "« que » serait complément direct.", "« dont » remplacerait « de ».", "« lequel » ne convient pas comme sujet naturel ici."]),
    _mcq("Elle s'intéresse beaucoup ___ questions écologiques.", ["aux", "des", "les", "dans les"], "aux", "prepositions", "Le verbe « s'intéresser à » se combine avec « les » en « aux ».", "s'intéresser à 加复数定冠词 les 缩合为 aux。", ["Correct : à + les = aux.", "« des » correspond à de + les.", "La préposition « à » manque.", "« dans » change le sens."]),
]

FILL = [
    _fill("Demain, quand tu arriveras, nous ___ déjà ___. (finir)", "aurons déjà fini", "futur-anterieur", "Le futur antérieur exprime une action achevée avant une autre action future.", "先于另一个未来动作完成的行为使用先将来时。"),
    _fill("Elle souhaite que nous ___ à l'heure. (venir)", "venions", "subjonctif", "« Souhaiter que » est suivi du subjonctif.", "souhaiter que 后使用虚拟式。"),
    _fill("Je ne trouve plus mes clés. Je ___ ai peut-être laissées au bureau.", "les", "pronoms-complements", "« Les » remplace « mes clés », complément direct féminin pluriel.", "les 替代阴性复数直接宾语 mes clés。"),
    _fill("Nous vivons dans ce quartier ___ 2022.", "depuis", "temps-prepositions", "« Depuis » marque le point de départ d'une situation qui continue.", "depuis 表示持续到现在的起点。"),
    _fill("Si vous étiez disponible, nous ___ en discuter demain. (pouvoir)", "pourrions", "conditionnel", "La conséquence de « si + imparfait » se met au conditionnel présent.", "si + 未完成过去时的结果句用条件式现在时。"),
    _fill("C'est une collègue avec ___ je travaille souvent.", "qui", "pronoms-relatifs", "Après une préposition désignant une personne, on emploie « qui ».", "介词后指人时使用关系代词 qui。"),
    _fill("Il est parti tôt ___ éviter les embouteillages.", "pour", "but", "« Pour + infinitif » exprime le but lorsque le sujet est le même.", "同一主语时用 pour + 不定式表达目的。"),
    _fill("Bien qu'il ___ fatigué, il a terminé son rapport. (être)", "soit", "subjonctif", "« Bien que » est toujours suivi du subjonctif.", "bien que 后总是使用虚拟式。"),
    _fill("Nous avons acheté ___ pain et ___ confiture.", "du pain et de la confiture", "articles-partitifs", "Les quantités non comptées prennent les articles partitifs « du » et « de la ».", "不可数数量使用部分冠词 du 和 de la。", ["du pain et de la confiture"]),
    _fill("Le train avait déjà quitté la gare quand nous ___. (arriver)", "sommes arrivés", "passe-compose", "L'arrivée ponctuelle se met au passé composé ; le départ antérieur est au plus-que-parfait.", "到达是瞬时动作，用复合过去时；更早的离开用愈过去时。", ["sommes arrivés", "sommes arrivées"]),
    _fill("Elle travaille beaucoup, ___ elle prend toujours le temps de lire.", "pourtant", "connecteurs", "« Pourtant » introduit un contraste avec la première proposition.", "pourtant 用来引出与前句形成反差的内容。"),
    _fill("Ce projet est ___ intéressant que l'autre.", "plus", "comparatif", "« Plus + adjectif + que » forme le comparatif de supériorité.", "plus + 形容词 + que 构成较高级。"),
]

GRAMMAR = {
    "passe-compose": ("Le passé composé", "Exprime une action achevée et délimitée dans le passé.", "表示过去已经完成且有边界的动作。", "Hier, j'ai terminé ce dossier."),
    "conditionnel": ("Le conditionnel présent", "Exprime une hypothèse, un souhait ou une conséquence irréelle.", "表达假设、愿望或非现实条件的结果。", "Avec plus de temps, je voyagerais."),
    "pronoms-relatifs": ("Les pronoms relatifs", "Relient deux propositions en remplaçant un nom.", "关系代词连接从句并替代名词。", "Voici la personne dont je parle."),
    "temps-prepositions": ("Depuis, pendant, il y a", "Ces marqueurs situent différemment une durée dans le temps.", "这些时间标记以不同方式定位时长。", "J'habite ici depuis deux ans."),
    "subjonctif": ("Le subjonctif présent", "S'emploie après la nécessité, le souhait, le doute ou certaines conjonctions.", "用于必要、愿望、怀疑以及某些连词之后。", "Il faut que tu viennes."),
    "negation": ("La négation", "Les éléments négatifs entourent généralement le verbe conjugué.", "否定成分通常位于变位动词两侧。", "Je n'ai pas encore fini."),
    "pronoms-complements": ("Les pronoms compléments", "Ils remplacent un complément direct ou indirect.", "宾语代词替代直接或间接宾语。", "Je lui écris souvent."),
    "connecteurs": ("Les connecteurs logiques", "Ils organisent le temps, la cause, la conséquence ou l'opposition.", "逻辑连接词组织时间、原因、结果或转折。", "Il pleut, pourtant nous sortons."),
    "comparatif": ("Le comparatif", "Il compare deux éléments avec plus, moins, aussi ou une forme irrégulière.", "使用 plus、moins、aussi 或不规则形式比较两个事物。", "Ce trajet est plus court."),
    "prepositions": ("Les prépositions contractées", "À et de se contractent devant certains articles définis.", "à 和 de 在某些定冠词前发生缩合。", "Je parle aux voisins."),
    "futur-anterieur": ("Le futur antérieur", "Exprime une action future terminée avant une autre.", "表示在另一未来动作前已完成的动作。", "Quand tu viendras, j'aurai fini."),
    "but": ("Exprimer le but", "Pour ou afin de sont suivis de l'infinitif avec un même sujet.", "同一主语时 pour 或 afin de 后接不定式表达目的。", "Je révise pour réussir."),
    "articles-partitifs": ("Les articles partitifs", "Du, de la et de l' désignent une quantité non comptée.", "du、de la、de l' 表示不可数数量。", "Nous achetons du fromage."),
}

COMMUNITY_VOCAB = [
    ("entraide", "nom féminin", "aide mutuelle", "互助", "L'entraide entre voisins facilite la vie du quartier.", "邻里互助让社区生活更轻松。", "Vie de quartier", "https://www.reddit.com/r/france/"),
    ("sobriété", "nom féminin", "réduction volontaire de la consommation", "节制；节约", "La sobriété énergétique reste un sujet fréquent dans les discussions.", "能源节制仍是讨论中的常见话题。", "Discussions publiques", "https://www.franceinfo.fr/"),
    ("démarche", "nom féminin", "action organisée pour obtenir un résultat", "流程；举措", "Cette démarche citoyenne rassemble plusieurs associations.", "这项公民行动汇集了多个协会。", "Vie associative", "https://www.service-public.fr/"),
    ("essor", "nom masculin", "développement rapide", "兴起；快速发展", "L'essor du vélo transforme les déplacements urbains.", "自行车的兴起正在改变城市出行。", "Mobilités urbaines", "https://www.francebleu.fr/"),
    ("pénurie", "nom féminin", "manque important d'une ressource", "短缺", "La commune cherche des solutions face à la pénurie de logements.", "市镇正在寻找应对住房短缺的办法。", "Actualité locale", "https://www.france24.com/fr/"),
    ("bénévole", "nom", "personne qui agit sans être payée", "志愿者", "Des bénévoles organisent une collecte ce week-end.", "志愿者本周末组织募捐。", "Associations", "https://www.helloasso.com/"),
    ("réaménagement", "nom masculin", "nouvelle organisation d'un espace", "重新规划", "Le réaménagement de la place suscite un débat local.", "广场重新规划引发了本地讨论。", "Débat municipal", "https://www.mairie.com/"),
    ("concertation", "nom féminin", "discussion avant une décision collective", "协商", "Une concertation est ouverte aux habitants du quartier.", "一场面向街区居民的协商正在开展。", "Participation citoyenne", "https://www.vie-publique.fr/"),
    ("abordable", "adjectif", "dont le prix reste accessible", "负担得起的", "Les étudiants demandent des logements plus abordables.", "学生希望有更负担得起的住房。", "Communauté étudiante", "https://www.etudiant.gouv.fr/"),
    ("signalement", "nom masculin", "action d'indiquer un problème", "报告；举报", "La mairie a reçu plusieurs signalements concernant l'éclairage.", "市政府收到了多起有关照明问题的报告。", "Services locaux", "https://www.service-public.fr/"),
]

DAILY_VOCAB = [
    ("ranger", "verbe", "mettre en ordre", "整理", "Je range mon bureau avant de travailler.", "我工作前整理书桌。"),
    ("emprunter", "verbe", "prendre pour rendre plus tard", "借入", "Puis-je emprunter ce livre ?", "我可以借这本书吗？"),
    ("prévenir", "verbe", "informer à l'avance", "提前通知", "Préviens-moi si tu arrives en retard.", "如果你迟到，请提前告诉我。"),
    ("habitude", "nom féminin", "comportement répété", "习惯", "Lire le matin est une bonne habitude.", "早上阅读是一个好习惯。"),
    ("pratique", "adjectif", "facile et utile", "实用的；方便的", "Cette application est très pratique.", "这个应用很实用。"),
    ("pourtant", "adverbe", "marque une opposition", "然而", "Il est fatigué, pourtant il continue.", "他很累，然而仍在继续。"),
    ("accueillir", "verbe", "recevoir une personne", "接待；欢迎", "Nous accueillons des amis ce soir.", "今晚我们接待朋友。"),
    ("se dépêcher", "verbe pronominal", "faire vite", "赶快", "Dépêche-toi, le bus arrive !", "快点，公交车来了！"),
    ("quartier", "nom masculin", "partie d'une ville", "街区", "Mon quartier est calme le soir.", "我的街区晚上很安静。"),
    ("réussir", "verbe", "obtenir un bon résultat", "成功；通过", "Elle travaille pour réussir l'examen.", "她努力学习以通过考试。"),
]


def content_hash(question):
    raw = f"{question['kind']}|{question['prompt']}|{question['answer']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _select(pool, count, usage, seed):
    candidates = deepcopy(pool)
    random.Random(seed).shuffle(candidates)
    candidates.sort(key=lambda item: usage.get(content_hash(item), ""))
    chosen = candidates[:count]
    for item in chosen:
        item["content_hash"] = content_hash(item)
    return chosen


def generate_content(study_date, question_usage, vocabulary_usage):
    questions = _select(MCQ, 5, question_usage, f"{study_date}:mcq") + _select(FILL, 5, question_usage, f"{study_date}:fill")
    for index, question in enumerate(questions, 1):
        question["position"] = index
    rng = random.Random(study_date)
    community = list(COMMUNITY_VOCAB)
    daily = list(DAILY_VOCAB)
    rng.shuffle(community)
    rng.shuffle(daily)
    community.sort(key=lambda entry: vocabulary_usage.get(f"community:{entry[0]}", ""))
    daily.sort(key=lambda entry: vocabulary_usage.get(f"daily:{entry[0]}", ""))
    community = community[:5]
    daily = daily[:5]
    vocabulary = []
    for category, entries in (("community", community), ("daily", daily)):
        for entry in entries:
            word, part, definition_fr, definition_zh, example_fr, example_zh, *source = entry
            vocabulary.append({"category": category, "word": word, "part_of_speech": part, "definition_fr": definition_fr, "definition_zh": definition_zh, "example_fr": example_fr, "example_zh": example_zh, "source_name": source[0] if source else None, "source_url": source[1] if source else None})
    return questions, vocabulary
