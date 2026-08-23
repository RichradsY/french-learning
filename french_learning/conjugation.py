"""Conjugation insights derived only from the learner's stored mistakes."""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

PRONOUNS = ("je", "tu", "il / elle", "nous", "vous", "ils / elles")
TENSE_BY_GRAMMAR = {
    "passe-compose": "Passé composé",
    "conditionnel": "Conditionnel présent",
    "subjonctif": "Subjonctif présent",
    "futur-anterieur": "Futur antérieur",
}


def _forms(*values):
    return dict(zip(PRONOUNS, values))


def _regular_er(infinitive, auxiliary="avoir"):
    stem, participle = infinitive[:-2], infinitive[:-2] + "é"
    present = _forms(
        stem + "e", stem + "es", stem + "e", stem + "ons", stem + "ez", stem + "ent"
    )
    return _regular_tables(infinitive, stem, participle, present, auxiliary)


def _regular_ir(infinitive):
    stem, long_stem, participle = infinitive[:-2], infinitive[:-2] + "iss", infinitive[:-2] + "i"
    present = _forms(
        stem + "is", stem + "is", stem + "it", long_stem + "ons", long_stem + "ez", long_stem + "ent"
    )
    return _regular_tables(infinitive, long_stem, participle, present, "avoir")


def _regular_tables(infinitive, imperfect_stem, participle, present, auxiliary):
    future_stem = infinitive
    if auxiliary == "être":
        perfect = _forms(
            f"suis {participle}(e)", f"es {participle}(e)", f"est {participle}(e)",
            f"sommes {participle}(e)s", f"êtes {participle}(e)(s)", f"sont {participle}(e)s",
        )
        future_perfect = _forms(
            f"serai {participle}(e)", f"seras {participle}(e)", f"sera {participle}(e)",
            f"serons {participle}(e)s", f"serez {participle}(e)(s)", f"seront {participle}(e)s",
        )
    else:
        perfect = _forms(*[f"{aux} {participle}" for aux in ("ai", "as", "a", "avons", "avez", "ont")])
        future_perfect = _forms(*[f"{aux} {participle}" for aux in ("aurai", "auras", "aura", "aurons", "aurez", "auront")])
    return {
        "Présent": present,
        "Passé composé": perfect,
        "Imparfait": _forms(*[imperfect_stem + ending for ending in ("ais", "ais", "ait", "ions", "iez", "aient")]),
        "Futur simple": _forms(*[future_stem + ending for ending in ("ai", "as", "a", "ons", "ez", "ont")]),
        "Futur antérieur": future_perfect,
        "Conditionnel présent": _forms(*[future_stem + ending for ending in ("ais", "ais", "ait", "ions", "iez", "aient")]),
        "Subjonctif présent": _forms(
            *[imperfect_stem + ending for ending in ("e", "es", "e", "ions", "iez", "ent")]
        ),
    }


def _irregular(present, perfect, imperfect, future, conditional, subjunctive, future_perfect):
    return {
        "Présent": _forms(*present),
        "Passé composé": _forms(*perfect),
        "Imparfait": _forms(*imperfect),
        "Futur simple": _forms(*future),
        "Futur antérieur": _forms(*future_perfect),
        "Conditionnel présent": _forms(*conditional),
        "Subjonctif présent": _forms(*subjunctive),
    }


VERBS = {
    "être": ("是；处于", _irregular(
        ("suis", "es", "est", "sommes", "êtes", "sont"),
        ("ai été", "as été", "a été", "avons été", "avez été", "ont été"),
        ("étais", "étais", "était", "étions", "étiez", "étaient"),
        ("serai", "seras", "sera", "serons", "serez", "seront"),
        ("serais", "serais", "serait", "serions", "seriez", "seraient"),
        ("sois", "sois", "soit", "soyons", "soyez", "soient"),
        ("aurai été", "auras été", "aura été", "aurons été", "aurez été", "auront été"),
    )),
    "avoir": ("有", _irregular(
        ("ai", "as", "a", "avons", "avez", "ont"),
        ("ai eu", "as eu", "a eu", "avons eu", "avez eu", "ont eu"),
        ("avais", "avais", "avait", "avions", "aviez", "avaient"),
        ("aurai", "auras", "aura", "aurons", "aurez", "auront"),
        ("aurais", "aurais", "aurait", "aurions", "auriez", "auraient"),
        ("aie", "aies", "ait", "ayons", "ayez", "aient"),
        ("aurai eu", "auras eu", "aura eu", "aurons eu", "aurez eu", "auront eu"),
    )),
    "aller": ("去", _irregular(
        ("vais", "vas", "va", "allons", "allez", "vont"),
        ("suis allé(e)", "es allé(e)", "est allé(e)", "sommes allé(e)s", "êtes allé(e)(s)", "sont allé(e)s"),
        ("allais", "allais", "allait", "allions", "alliez", "allaient"),
        ("irai", "iras", "ira", "irons", "irez", "iront"),
        ("irais", "irais", "irait", "irions", "iriez", "iraient"),
        ("aille", "ailles", "aille", "allions", "alliez", "aillent"),
        ("serai allé(e)", "seras allé(e)", "sera allé(e)", "serons allé(e)s", "serez allé(e)(s)", "seront allé(e)s"),
    )),
    "faire": ("做", _irregular(
        ("fais", "fais", "fait", "faisons", "faites", "font"),
        ("ai fait", "as fait", "a fait", "avons fait", "avez fait", "ont fait"),
        ("faisais", "faisais", "faisait", "faisions", "faisiez", "faisaient"),
        ("ferai", "feras", "fera", "ferons", "ferez", "feront"),
        ("ferais", "ferais", "ferait", "ferions", "feriez", "feraient"),
        ("fasse", "fasses", "fasse", "fassions", "fassiez", "fassent"),
        ("aurai fait", "auras fait", "aura fait", "aurons fait", "aurez fait", "auront fait"),
    )),
    "venir": ("来", _irregular(
        ("viens", "viens", "vient", "venons", "venez", "viennent"),
        ("suis venu(e)", "es venu(e)", "est venu(e)", "sommes venu(e)s", "êtes venu(e)(s)", "sont venu(e)s"),
        ("venais", "venais", "venait", "venions", "veniez", "venaient"),
        ("viendrai", "viendras", "viendra", "viendrons", "viendrez", "viendront"),
        ("viendrais", "viendrais", "viendrait", "viendrions", "viendriez", "viendraient"),
        ("vienne", "viennes", "vienne", "venions", "veniez", "viennent"),
        ("serai venu(e)", "seras venu(e)", "sera venu(e)", "serons venu(e)s", "serez venu(e)(s)", "seront venu(e)s"),
    )),
    "pouvoir": ("能够", _irregular(
        ("peux", "peux", "peut", "pouvons", "pouvez", "peuvent"),
        ("ai pu", "as pu", "a pu", "avons pu", "avez pu", "ont pu"),
        ("pouvais", "pouvais", "pouvait", "pouvions", "pouviez", "pouvaient"),
        ("pourrai", "pourras", "pourra", "pourrons", "pourrez", "pourront"),
        ("pourrais", "pourrais", "pourrait", "pourrions", "pourriez", "pourraient"),
        ("puisse", "puisses", "puisse", "puissions", "puissiez", "puissent"),
        ("aurai pu", "auras pu", "aura pu", "aurons pu", "aurez pu", "auront pu"),
    )),
    "suivre": ("跟随；参加", _irregular(
        ("suis", "suis", "suit", "suivons", "suivez", "suivent"),
        ("ai suivi", "as suivi", "a suivi", "avons suivi", "avez suivi", "ont suivi"),
        ("suivais", "suivais", "suivait", "suivions", "suiviez", "suivaient"),
        ("suivrai", "suivras", "suivra", "suivrons", "suivrez", "suivront"),
        ("suivrais", "suivrais", "suivrait", "suivrions", "suivriez", "suivraient"),
        ("suive", "suives", "suive", "suivions", "suiviez", "suivent"),
        ("aurai suivi", "auras suivi", "aura suivi", "aurons suivi", "aurez suivi", "auront suivi"),
    )),
    "partir": ("离开", _irregular(
        ("pars", "pars", "part", "partons", "partez", "partent"),
        ("suis parti(e)", "es parti(e)", "est parti(e)", "sommes parti(e)s", "êtes parti(e)(s)", "sont parti(e)s"),
        ("partais", "partais", "partait", "partions", "partiez", "partaient"),
        ("partirai", "partiras", "partira", "partirons", "partirez", "partiront"),
        ("partirais", "partirais", "partirait", "partirions", "partiriez", "partiraient"),
        ("parte", "partes", "parte", "partions", "partiez", "partent"),
        ("serai parti(e)", "seras parti(e)", "sera parti(e)", "serons parti(e)s", "serez parti(e)(s)", "seront parti(e)s"),
    )),
    "finir": ("完成", _regular_ir("finir")),
    "réussir": ("成功；通过", _regular_ir("réussir")),
    "remplir": ("填写；装满", _regular_ir("remplir")),
    "visiter": ("参观", _regular_er("visiter")),
    "fermer": ("关闭", _regular_er("fermer")),
    "arriver": ("到达", _regular_er("arriver", "être")),
}


def _fold(value):
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char)).replace("’", "'")


def _contains_form(text, form):
    plain = re.sub(r"\([^)]*\)", "", _fold(form))
    return bool(plain and re.search(rf"(?<!\w){re.escape(plain)}(?!\w)", _fold(text)))


def _match_verb(item):
    prompt = item.get("prompt", "")
    cues = {_fold(value) for value in re.findall(r"\(([A-Za-zÀ-ÿ'’-]+)\)", prompt)}
    for infinitive in VERBS:
        if _fold(infinitive) in cues:
            return infinitive
    answer_text = " ".join((item.get("answer", ""), item.get("user_answer", "")))
    matches = []
    for infinitive, (_, tables) in VERBS.items():
        for tense, forms in tables.items():
            for form in forms.values():
                if _contains_form(answer_text, form):
                    matches.append((len(_fold(re.sub(r"\([^)]*\)", "", form))), infinitive, tense))
    return max(matches, default=(0, None, None))[1]


def conjugation_insights(mistakes):
    grouped = defaultdict(lambda: {"count": 0, "tenses": defaultdict(int), "examples": []})
    for item in mistakes:
        verb = _match_verb(item)
        if not verb:
            continue
        tables = VERBS[verb][1]
        tense = TENSE_BY_GRAMMAR.get(item.get("grammar_key"))
        if tense not in tables:
            tense = next(
                (name for name, forms in tables.items() if any(_contains_form(item.get("answer", ""), form) for form in forms.values())),
                None,
            )
        if not tense:
            continue
        entry = grouped[verb]
        entry["count"] += 1
        entry["tenses"][tense] += 1
        example = {"prompt": item.get("prompt", ""), "answer": item.get("answer", "")}
        if example not in entry["examples"] and len(entry["examples"]) < 2:
            entry["examples"].append(example)
    result = []
    for verb, entry in grouped.items():
        translation_zh, tables = VERBS[verb]
        tenses = [
            {"name": name, "mistake_count": count, "forms": tables[name]}
            for name, count in sorted(entry["tenses"].items(), key=lambda pair: (-pair[1], pair[0]))
        ]
        result.append({
            "verb": verb,
            "translation_zh": translation_zh,
            "mistake_count": entry["count"],
            "tenses": tenses,
            "examples": entry["examples"],
        })
    return sorted(result, key=lambda item: (-item["mistake_count"], item["verb"]))
