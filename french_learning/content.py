"""Controlled B1–C1 content pools and deterministic daily selection."""
from __future__ import annotations

import hashlib
import random
import re
import unicodedata
from copy import deepcopy
from difflib import SequenceMatcher


def _mcq(prompt, options, answer, grammar_key, fr, zh, reasons):
    return {
        "kind": "mcq", "prompt": prompt, "options": options, "answer": answer,
        "accepted": [answer], "grammar_key": grammar_key,
        "explanation_fr": fr, "explanation_zh": zh,
        "option_explanations": {
            option: reasons[index] for index, option in enumerate(options)
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

MCQ.extend([
    _mcq("À peine ___ son exposé que les questions ont commencé.", ["avait-il terminé", "il avait terminé", "a-t-il terminé", "terminait-il"], "avait-il terminé", "inversion", "Après « à peine » en tête, l'inversion soutenue et le plus-que-parfait marquent l'antériorité.", "句首 à peine 在正式语体中引起倒装，愈过去时表示先发生的动作。", ["Inversion et antériorité correctes.", "L'inversion attendue manque.", "Le passé composé marque mal l'antériorité.", "L'imparfait décrit un déroulement."]),
    _mcq("Quoiqu'elle ___ les risques, elle a maintenu sa décision.", ["connût", "connaissait", "connaîtra", "connaîtrait"], "connût", "subjonctif", "« Quoique » demande ici le subjonctif imparfait dans un registre soutenu.", "quoique 表示让步；正式书面语中可使用虚拟式未完成过去时 connût。", ["Subjonctif imparfait soutenu correct.", "Indicatif incorrect après « quoique ».", "Futur incompatible avec le récit.", "Conditionnel sans valeur ici."]),
    _mcq("Il décrit cette ville comme s'il y ___ toute sa vie.", ["avait vécu", "a vécu", "vivrait", "vive"], "avait vécu", "plus-que-parfait", "« Comme si » introduit ici une comparaison irréelle passée au plus-que-parfait.", "comme si 表示与事实不符的过去比较时，使用愈过去时 avait vécu。", ["Plus-que-parfait de l'irréel correct.", "Passé composé trop factuel.", "Conditionnel incorrect après « comme si ».", "Subjonctif incorrect ici."]),
    _mcq("Le rapport, ___ hier au comité, sera publié demain.", ["remis", "remettant", "ayant remis", "remettre"], "remis", "participes", "Le participe passé détaché « remis » a une valeur passive.", "过去分词 remis 作同位修饰语表达被动，并与阳性单数 rapport 一致。", ["Participe passé passif correct.", "Participe présent actif incorrect.", "Participe composé actif incorrect.", "Infinitif sans fonction ici."]),
    _mcq("C'est à cette conclusion ___ les chercheurs sont parvenus.", ["que", "dont", "où", "laquelle"], "que", "mise-en-relief", "La structure « c'est à X que » met le complément en relief.", "强调结构 c'est à X que 用于突出由 à 引出的成分。", ["Corrélatif correct de la structure.", "« dont » remplace un complément en de.", "« où » exprime lieu ou temps.", "« laquelle » exigerait une préposition."]),
    _mcq("Elle a beau ___ les enjeux, personne ne l'écoute.", ["expliquer", "explique", "expliquant", "d'expliquer"], "expliquer", "concession", "La locution concessive « avoir beau » est suivie directement de l'infinitif.", "avoir beau + 不定式表示“尽管做……仍然……”，后面不加介词。", ["Infinitif direct correct.", "Forme conjuguée impossible ici.", "Participe présent impossible ici.", "La préposition de est incorrecte."]),
    _mcq("Pour peu que le contexte ___, cette mesure deviendrait pertinente.", ["change", "changera", "changerait", "changeait"], "change", "subjonctif", "« Pour peu que » signifie « à condition que » et demande le subjonctif.", "pour peu que 表示“只要、倘若”，后接虚拟式。", ["Subjonctif présent correct.", "Futur incorrect après la locution.", "Conditionnel incorrect dans la subordonnée.", "Imparfait indicatif incorrect."]),
    _mcq("Il aurait accepté la proposition s'il en ___ les conséquences.", ["avait mesuré", "mesurait", "aurait mesuré", "a mesuré"], "avait mesuré", "hypothese-passee", "L'irréel du passé associe « si + plus-que-parfait » au conditionnel passé.", "过去非现实条件使用 si + 愈过去时，主句使用过去条件式。", ["Plus-que-parfait correct après si.", "Imparfait pour une hypothèse présente.", "Conditionnel interdit après si.", "Passé composé trop factuel."]),
    _mcq("Les mesures ___ le rapport fait référence restent contestées.", ["auxquelles", "lesquelles", "dont", "que"], "auxquelles", "pronoms-relatifs", "« Faire référence à » exige « auxquelles » pour reprendre « les mesures ».", "faire référence à 要求介词 à；阴性复数 mesures 用 auxquelles。", ["À + lesquelles est correct.", "La préposition à manque.", "« dont » correspond à de.", "« que » remplace un COD."]),
    _mcq("Non seulement elle a identifié le problème, mais elle ___ une solution.", ["a aussi proposé", "a proposé aussi que", "a-t-elle proposé", "aussi proposait"], "a aussi proposé", "connecteurs", "« Non seulement..., mais aussi... » additionne deux faits parallèles.", "non seulement… mais aussi… 表示递进并列；aussi 位于助动词和过去分词之间。", ["Structure parallèle correcte.", "« que » n'a aucun complément.", "Inversion interrogative injustifiée.", "Ordre et temps incorrects."]),
    _mcq("Il convient de ___ que ces résultats restent provisoires.", ["souligner", "remarquer de", "insister", "préciser à"], "souligner", "registre", "La tournure soutenue « il convient de » est suivie d'un infinitif.", "正式表达 il convient de + 不定式意为“应当……”；souligner que 表示“强调”。", ["Collocation correcte.", "« remarquer » ne prend pas de ici.", "« insister » demande sur.", "« préciser » ne prend pas à ici."]),
    _mcq("La décision a été prise ___ d'une longue concertation.", ["à l'issue", "au terme que", "en raison", "faute"], "à l'issue", "locutions", "« À l'issue de » signifie « à la fin de ».", "à l'issue de 意为“在……结束时”，后接名词。", ["Locution complète correcte.", "« au terme » demanderait de.", "« en raison » demanderait de et exprimerait la cause.", "« faute » demanderait de."]),
    _mcq("Il s'en est fallu de peu que le projet ___.", ["échoue", "a échoué", "échouerait", "échouait"], "échoue", "subjonctif", "« Il s'en faut de peu que » exprime un résultat presque réalisé au subjonctif.", "il s'en est fallu de peu que 表示“差一点就……”，后接虚拟式。", ["Subjonctif présent correct.", "Passé composé indicatif incorrect.", "Conditionnel incorrect.", "Imparfait indicatif incorrect."]),
    _mcq("Cette hypothèse est crédible, ___ plusieurs indices convergent.", ["d'autant plus que", "bien que", "faute de", "quitte à"], "d'autant plus que", "connecteurs", "« D'autant plus que » renforce une affirmation par une raison.", "d'autant plus que 意为“更何况、尤其因为”，用于补充强化理由。", ["Renforcement causal correct.", "« bien que » marque la concession.", "« faute de » précède un nom.", "« quitte à » introduit un risque."]),
    _mcq("Encore faut-il que les moyens nécessaires ___ disponibles.", ["soient", "sont", "seront", "seraient"], "soient", "inversion", "« Encore faut-il que » introduit une réserve et commande le subjonctif.", "encore faut-il que 表示“不过还得……”，是正式倒装结构，后接虚拟式。", ["Subjonctif correct.", "Indicatif présent incorrect.", "Futur simple incorrect.", "Conditionnel incorrect."]),
    _mcq("Ce ___ nous avons besoin, c'est d'une méthode fiable.", ["dont", "que", "à quoi", "lequel"], "dont", "pronoms-relatifs", "« Avoir besoin de » est repris par « dont » dans cette phrase clivée.", "avoir besoin de 中的 de 由 dont 替代；ce dont… c'est… 是强调结构。", ["Reprise de de correcte.", "« que » reprendrait un COD.", "« à quoi » reprendrait à.", "« lequel » exige une préposition."]),
    _mcq("Il n'est pas exclu qu'une autre interprétation ___ retenue.", ["puisse être", "peut être", "pourra être", "pourrait être"], "puisse être", "subjonctif", "« Il n'est pas exclu que » exprime une possibilité incertaine au subjonctif.", "il n'est pas exclu que 表示“不排除……”，后接虚拟式 puisse être。", ["Subjonctif passif correct.", "Indicatif trop affirmatif.", "Futur simple incorrect.", "Conditionnel non attendu ici."]),
    _mcq("Faute d'___ une réponse à temps, nous avons reporté la réunion.", ["avoir reçu", "recevoir", "ayant reçu", "être reçu"], "avoir reçu", "cause", "« Faute de » prend l'infinitif passé pour une absence antérieure.", "faute de + 过去不定式表示“由于之前没有做成……”。", ["Infinitif passé correct.", "Infinitif présent sans antériorité.", "Participe composé impossible ici.", "Infinitif passif incorrect."]),
])

MCQ.extend([
    _mcq("Ce dossier mérite d'___ examiné plus attentivement.", ["être", "avoir", "été", "étant"], "être", "participes", "« Mériter de » est suivi de l'infinitif passif « être examiné ».", "mériter de 后接不定式；dossier 是被审查的对象，因此使用被动式 être examiné。", ["Infinitif passif correct.", "« avoir examiné » aurait un sens actif.", "Le participe passé seul ne convient pas.", "Le participe présent ne complète pas « mérite de »."]),
    _mcq("Plus les délais raccourcissent, plus la coordination ___ essentielle.", ["devient", "deviendrait", "devenue", "devenir"], "devient", "comparatif", "La structure corrélative « plus..., plus... » prend ici l'indicatif présent.", "plus… plus… 表示“越……越……”；描述一般变化时使用直陈式现在时。", ["Indicatif présent correct.", "Le conditionnel ajouterait une hypothèse absente.", "Le participe ne forme pas le verbe.", "L'infinitif ne peut être le noyau de la proposition."]),
    _mcq("L'équipe s'est engagée à ce que chaque demande ___ sous quarante-huit heures.", ["soit traitée", "est traitée", "sera traitée", "serait traitée"], "soit traitée", "subjonctif", "« S'engager à ce que » demande le subjonctif, ici à la voix passive.", "s'engager à ce que 后接虚拟式；demande 是被处理的对象，使用 soit traitée。", ["Subjonctif passif correct.", "Indicatif présent incorrect après cette locution.", "Futur simple non attendu dans la subordonnée.", "Conditionnel sans valeur ici."]),
    _mcq("N'eût été son intervention, le désaccord se serait prolongé.", ["Sans son intervention", "Grâce à son absence", "Après son intervention", "Malgré son accord"], "Sans son intervention", "hypothese-passee", "« N'eût été » exprime une condition passée irréelle et signifie ici « sans ».", "n'eût été 是正式的过去非现实条件表达，相当于“若不是……”。", ["Reformulation correcte de la condition irréelle.", "Le sens causal est inversé.", "La simple succession temporelle ne suffit pas.", "Cette concession change le sens."]),
    _mcq("À supposer que cette piste ___, quelles seraient les conséquences ?", ["soit retenue", "est retenue", "sera retenue", "serait retenue"], "soit retenue", "subjonctif", "« À supposer que » introduit une hypothèse et commande le subjonctif.", "à supposer que 表示假设，后接虚拟式 soit retenue。", ["Subjonctif passif correct.", "Indicatif trop affirmatif.", "Futur incorrect après la locution.", "Conditionnel non attendu dans la subordonnée."]),
])

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

FILL.extend([
    _fill("À peine la séance avait-elle commencé que plusieurs participants ___. (intervenir)", "sont intervenus", "inversion", "Le second événement ponctuel se met au passé composé.", "à peine… que… 表示“刚……就……”；后发生的瞬时动作使用复合过去时。"),
    _fill("Il parle de cette période comme s'il l'___ lui-même. (vivre)", "avait vécue", "plus-que-parfait", "« Comme si » introduit l'irréel du passé et le participe s'accorde avec « l' ».", "comme si 后用愈过去时；l' 指阴性 période，因此 vécue 要配合。"),
    _fill("___ les contraintes, l'équipe a livré le projet à temps.", "Malgré", "concession", "« Malgré » introduit un nom et exprime une concession.", "malgré + 名词表示“尽管……”。"),
    _fill("Le comité recommande que cette mesure ___ sans délai. (appliquer)", "soit appliquée", "subjonctif", "« Recommander que » demande le subjonctif passif.", "recommander que 后接虚拟式；mesure 是动作承受者，用 soit appliquée。"),
    _fill("Si les données avaient été complètes, nous ___ une autre conclusion. (tirer)", "aurions tiré", "hypothese-passee", "L'irréel du passé associe plus-que-parfait et conditionnel passé.", "过去非现实条件：si 从句用愈过去时，结果句用过去条件式。"),
    _fill("C'est précisément ce point ___ il convient d'insister.", "sur lequel", "pronoms-relatifs", "« Insister sur » impose la préposition devant le pronom relatif.", "insister sur 表示“强调”；指代 point 时使用 sur lequel。"),
    _fill("Les propositions, ___ par plusieurs experts, seront réexaminées. (formuler)", "formulées", "participes", "Le participe passé détaché a une valeur passive et s'accorde avec « propositions ».", "过去分词作同位修饰语表示被动，并与阴性复数 propositions 配合。"),
    _fill("Il a poursuivi son projet, ___ les critiques répétées.", "en dépit de", "concession", "« En dépit de » est une locution prépositive de concession.", "en dépit de 意为“尽管、不顾”，后接名词。"),
    _fill("Elle a reformulé son argument ___ personne ne puisse l'interpréter de travers.", "afin que", "but", "Avec deux sujets différents, « afin que » est suivi du subjonctif.", "主语不同时，用 afin que + 虚拟式表达目的；de travers 表示“错误地”。"),
    _fill("Il n'est pas certain que ces mesures ___ à résoudre le problème. (suffire)", "suffisent", "subjonctif", "Le doute exprimé appelle le subjonctif.", "il n'est pas certain que 表达不确定，后接虚拟式；suffire à 表示“足以……”。"),
    _fill("La réforme vise une ___ progressive des procédures. (simplifier)", "simplification", "nominalisation", "Le nom « simplification » condense l'action dans un groupe nominal.", "simplifier 的名词化形式是 simplification；名词化常用于正式书面语。"),
    _fill("Il a reconnu son erreur, non sans ___ les circonstances. (rappeler)", "rappeler", "locutions", "« Non sans + infinitif » ajoute une action secondaire.", "non sans + 不定式表示“并非没有……、同时还是……”。"),
    _fill("Les résultats sont ___ plus convaincants qu'ils ont été reproduits ailleurs.", "d'autant", "connecteurs", "« D'autant plus... que... » renforce un jugement par une justification.", "d'autant plus… que… 意为“更加……，因为……”。"),
    _fill("Pour peu que l'on ___ le temps de l'examiner, cette solution paraît solide. (prendre)", "prenne", "subjonctif", "« Pour peu que » introduit une condition minimale au subjonctif.", "pour peu que 表示“只要”，后接虚拟式 prenne。"),
    _fill("La directrice a demandé si le rapport ___ avant vendredi. (pouvoir)", "pourrait être achevé", "discours-indirect", "Après un verbe passé, le futur devient conditionnel au discours indirect.", "间接引语中，过去时动词后的将来时后移为条件式；rapport 使用被动式。"),
    _fill("___ de preuves suffisantes, l'accusation a été abandonnée.", "Faute", "cause", "« Faute de » exprime qu'un élément nécessaire manque.", "faute de 表示“由于缺少……”，常见于正式语体。"),
    _fill("Quelque pertinentes que ___ ces objections, elles ne changent pas la conclusion. (être)", "soient", "concession", "« Quelque + adjectif + que » exprime la concession au subjonctif.", "quelque + 形容词 + que 表示“无论多么……”，后接虚拟式。"),
    _fill("Il s'en est fallu de peu que nous ___ la correspondance. (manquer)", "manquions", "subjonctif", "« Il s'en faut de peu que » est suivi du subjonctif.", "il s'en est fallu de peu que 表示“差一点就……”，后接虚拟式。"),
])

FILL.extend([
    _fill("Bien loin de ___ le débat, cette annonce l'a relancé. (clore)", "clore", "locutions", "« Bien loin de + infinitif » marque un résultat opposé à celui attendu.", "bien loin de + 不定式表示“非但没有……反而……”。"),
    _fill("Il importe que chacun ___ accès aux mêmes informations. (avoir)", "ait", "subjonctif", "La tournure impersonnelle « il importe que » demande le subjonctif.", "il importe que 表示重要性，后接虚拟式 ait。"),
    _fill("Après avoir ___ les deux propositions, le comité rendra son avis. (comparer)", "comparé", "participes", "« Après avoir + participe passé » exprime une action achevée avant la suivante.", "après avoir + 过去分词表示先于主句完成的动作。"),
    _fill("C'est en ___ régulièrement que l'on progresse. (pratiquer)", "pratiquant", "mise-en-relief", "« C'est en + gérondif que » met en relief le moyen employé.", "c'est en + 现在分词 que 强调实现结果的方式。"),
    _fill("Elle a quitté la salle sans que personne ne s'en ___. (apercevoir)", "aperçoive", "subjonctif", "« Sans que » est suivi du subjonctif ; le « ne » est ici explétif.", "sans que 后接虚拟式；此处 ne 是赘词，不表示否定。"),
])

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
    "inversion": ("L'inversion soutenue", "Certaines locutions placées en tête entraînent l'inversion du sujet.", "某些置于句首的正式表达会引起主谓倒装。", "À peine était-il arrivé que le train repartait."),
    "plus-que-parfait": ("Le plus-que-parfait", "Exprime un fait antérieur à un autre fait passé.", "表示先于另一个过去动作发生的事情。", "Il avait déjà quitté les lieux."),
    "participes": ("Les formes participiales", "Les participes condensent une proposition active ou passive.", "分词结构可压缩主动或被动从句。", "Informée à temps, elle a réagi."),
    "mise-en-relief": ("La mise en relief", "Les structures clivées attirent l'attention sur un constituant.", "分裂句结构用于突出某个成分。", "C'est ce point que je souligne."),
    "concession": ("La concession", "Présente un obstacle qui n'empêche pas le résultat.", "表示某个障碍并未阻止结果发生。", "Malgré la pluie, nous sommes sortis."),
    "hypothese-passee": ("L'hypothèse passée", "Combine plus-que-parfait et conditionnel passé pour l'irréel.", "过去非现实假设结合愈过去时和过去条件式。", "Si j'avais su, je serais venu."),
    "registre": ("Le registre soutenu", "Certaines tournures appartiennent surtout à l'écrit formel.", "某些表达主要用于正式书面语。", "Il convient de préciser ce point."),
    "locutions": ("Les locutions figées", "Ces groupes de mots fonctionnent comme une seule unité grammaticale.", "固定短语作为一个整体发挥语法作用。", "À l'issue de la réunion, nous déciderons."),
    "cause": ("Exprimer la cause", "Des locutions précisent la présence ou l'absence d'une cause.", "不同短语可表达原因或某种条件的缺失。", "Faute de temps, nous avons abrégé."),
    "nominalisation": ("La nominalisation", "Transforme une action en nom pour densifier l'écrit.", "把动作转化为名词，使书面表达更凝练。", "La simplification améliore la procédure."),
    "discours-indirect": ("Le discours indirect", "Les temps se décalent après un verbe introducteur au passé.", "引述动词为过去时时，间接引语中的时态相应后移。", "Elle a demandé s'il viendrait."),
    "expression-ecrite": ("La précision de l’expression écrite", "Regroupe les corrections ponctuelles qui ne relèvent pas d’une catégorie grammaticale plus précise.", "汇总无法归入更具体语法类别的局部书面表达问题。", "Je relis mon texte pour préciser chaque formulation."),
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

COMMUNITY_VOCAB.extend([
    ("mutualisation", "nom féminin", "mise en commun de moyens", "资源共享", "La mutualisation du matériel réduit les dépenses des associations.", "共享设备可以降低协会的开支。", "Vie associative", "https://www.associations.gouv.fr/"),
    ("résilience", "nom féminin", "capacité à faire face à une difficulté", "韧性；恢复力", "La résilience du quartier dépend aussi de ses réseaux d'entraide.", "社区韧性也取决于互助网络。", "Vie locale", "https://www.vie-publique.fr/"),
    ("végétalisation", "nom féminin", "action d'ajouter des plantes à un espace", "绿化", "La végétalisation de la cour apporte de l'ombre en été.", "庭院绿化能在夏季提供阴凉。", "Transition écologique", "https://www.ecologie.gouv.fr/"),
    ("accessibilité", "nom féminin", "possibilité d'accéder facilement à un lieu ou service", "无障碍；可及性", "L'accessibilité du bâtiment sera améliorée cette année.", "今年将改善建筑的无障碍条件。", "Services publics", "https://www.service-public.fr/"),
    ("médiation", "nom féminin", "intervention facilitant le dialogue", "调解；协调", "Une médiation a permis de rétablir le dialogue entre les habitants.", "一次调解帮助居民恢复了对话。", "Cohésion sociale", "https://www.vie-publique.fr/"),
    ("recyclerie", "nom féminin", "lieu où des objets sont récupérés et réemployés", "再利用中心", "La recyclerie remet en état des meubles donnés par les habitants.", "再利用中心修复居民捐赠的家具。", "Réemploi", "https://www.ecologie.gouv.fr/"),
    ("covoiturage", "nom masculin", "partage d'un trajet en voiture", "拼车", "Le covoiturage facilite les déplacements depuis les villages voisins.", "拼车方便了周边村庄的出行。", "Mobilités", "https://www.ecologie.gouv.fr/"),
    ("permanence", "nom féminin", "période où un service accueille le public", "值班接待时间", "Une permanence juridique est organisée chaque mardi.", "每周二安排法律咨询接待。", "Accès au droit", "https://www.service-public.fr/"),
    ("nuisance", "nom féminin", "élément qui gêne la vie quotidienne", "干扰；公害", "Les riverains souhaitent réduire les nuisances sonores nocturnes.", "附近居民希望减少夜间噪声干扰。", "Vie locale", "https://www.service-public.fr/"),
    ("aménagement", "nom masculin", "organisation pratique d'un espace", "空间规划", "Le nouvel aménagement réserve davantage de place aux piétons.", "新的空间规划为行人留出更多位置。", "Urbanisme", "https://www.ecologie.gouv.fr/"),
    ("collecte", "nom féminin", "ramassage organisé de dons ou de déchets", "收集；募捐", "Une collecte de vêtements aura lieu devant la mairie.", "市政府门前将举行衣物募集。", "Solidarité", "https://www.service-public.fr/"),
    ("compostage", "nom masculin", "transformation des déchets organiques en compost", "堆肥", "Le compostage collectif diminue le volume des poubelles.", "集体堆肥可减少垃圾量。", "Déchets", "https://www.ecologie.gouv.fr/"),
    ("mobilité", "nom féminin", "manière de se déplacer sur un territoire", "出行；流动性", "Le plan de mobilité encourage le vélo et la marche.", "出行计划鼓励骑车和步行。", "Transports", "https://www.ecologie.gouv.fr/"),
    ("rénovation", "nom féminin", "travaux destinés à améliorer un bâtiment", "翻新；改造", "La rénovation de l'école réduira sa consommation d'énergie.", "学校改造将降低能源消耗。", "Bâtiments", "https://www.ecologie.gouv.fr/"),
    ("inclusion", "nom féminin", "participation de chacun sans exclusion", "包容；融入", "Le projet favorise l'inclusion des personnes isolées.", "该项目促进孤立人群融入社会。", "Cohésion sociale", "https://www.vie-publique.fr/"),
    ("transition", "nom féminin", "passage progressif vers une nouvelle organisation", "转型；过渡", "La transition énergétique modifie les priorités de la commune.", "能源转型正在改变市镇的优先事项。", "Énergie", "https://www.ecologie.gouv.fr/"),
    ("consultation", "nom féminin", "recueil de l'avis du public", "意见征询", "La consultation en ligne restera ouverte pendant un mois.", "线上意见征询将开放一个月。", "Participation citoyenne", "https://www.vie-publique.fr/"),
    ("subvention", "nom féminin", "aide financière accordée à un projet", "补助金", "L'association demande une subvention pour son atelier culturel.", "该协会为文化工作坊申请补助。", "Vie associative", "https://www.associations.gouv.fr/"),
    ("ressourcerie", "nom féminin", "structure qui collecte et revend des objets réemployés", "资源再利用商店", "La ressourcerie propose des objets réparés à prix modéré.", "资源再利用商店以适中价格出售修复物品。", "Réemploi", "https://www.ecologie.gouv.fr/"),
    ("piétonnisation", "nom féminin", "transformation d'une rue en espace réservé aux piétons", "步行街改造", "La piétonnisation du centre suscite des avis contrastés.", "市中心步行街改造引发不同意见。", "Urbanisme", "https://www.vie-publique.fr/"),
])

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


DAILY_VOCAB.extend([
    ("prévoir", "verbe", "organiser à l'avance", "预先安排", "Nous prévoyons une solution en cas de pluie.", "我们预先准备了下雨时的方案。"),
    ("reporter", "verbe", "remettre à une date ultérieure", "推迟", "Ils ont reporté la réunion à vendredi.", "他们把会议推迟到周五。"),
    ("vérifier", "verbe", "contrôler qu'une chose est correcte", "检查；核实", "Vérifie l'adresse avant de partir.", "出发前核实一下地址。"),
    ("partager", "verbe", "utiliser ou donner avec d'autres", "分享；共用", "Nous partageons les frais du voyage.", "我们共同承担旅行费用。"),
    ("conseiller", "verbe", "recommander une action", "建议", "Le médecin lui conseille de se reposer.", "医生建议他休息。"),
    ("éviter", "verbe", "faire en sorte qu'une chose ne se produise pas", "避免", "Je pars tôt pour éviter les embouteillages.", "我早出发以避开堵车。"),
    ("se rendre", "verbe pronominal", "aller dans un lieu", "前往", "Elle se rend au travail à vélo.", "她骑自行车去上班。"),
    ("profiter", "verbe", "tirer avantage d'une situation", "利用；享受", "Profitons du soleil pour marcher.", "趁着阳光好，我们去散步吧。"),
    ("améliorer", "verbe", "rendre meilleur", "改善", "Cette habitude améliore ma concentration.", "这个习惯改善了我的专注力。"),
    ("disponible", "adjectif", "libre ou prêt à être utilisé", "有空的；可用的", "Cette salle est disponible après quinze heures.", "这个房间下午三点后可用。"),
    ("convenir", "verbe", "être adapté ou acceptable", "适合；商定", "Cette heure convient à toute l'équipe.", "这个时间适合整个团队。"),
    ("hésiter", "verbe", "avoir du mal à choisir", "犹豫", "J'hésite entre les deux itinéraires.", "我在两条路线之间犹豫。"),
    ("proposer", "verbe", "présenter une idée ou une possibilité", "提出；建议", "Elle propose de déjeuner dehors.", "她提议在外面吃午饭。"),
    ("découvrir", "verbe", "voir ou apprendre pour la première fois", "发现；初次了解", "Nous découvrons un nouveau quartier.", "我们正在探索一个新街区。"),
    ("organiser", "verbe", "préparer de manière structurée", "组织；安排", "Il organise ses tâches pour la semaine.", "他安排一周的任务。"),
    ("accompagner", "verbe", "aller avec quelqu'un", "陪同", "Je peux t'accompagner jusqu'à la gare.", "我可以陪你到车站。"),
    ("maintenir", "verbe", "conserver dans le même état", "维持", "Il est difficile de maintenir ce rythme.", "很难维持这个节奏。"),
    ("dépendre", "verbe", "être déterminé par autre chose", "取决于", "Le résultat dépend de notre préparation.", "结果取决于我们的准备。"),
    ("permettre", "verbe", "rendre une action possible", "使能够；允许", "Ce raccourci permet de gagner du temps.", "这条捷径可以节省时间。"),
    ("rappeler", "verbe", "faire revenir une information à l'esprit", "提醒；使想起", "Rappelle-moi de confirmer la réservation.", "提醒我确认预订。"),
])


def content_hash(question):
    raw = f"{question['kind']}|{question['prompt']}|{question['answer']}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


CHINESE_USAGE_BY_GRAMMAR = {
    "passe-compose": "avant de + 不定式表示“在做……之前”；复合过去时突出已完成动作。",
    "conditionnel": "si + 未完成过去时搭配条件式现在时，表达与当前事实相反的假设。",
    "pronoms-relatifs": "先确认动词要求的介词，再选择 dont、auquel、sur lequel 等关系代词。",
    "temps-prepositions": "depuis 强调从过去持续至今；pendant 表示有边界的时段。",
    "subjonctif": "必要、怀疑、愿望和部分让步连词后常用虚拟式。",
    "negation": "复合时态中否定成分通常围绕助动词；pas encore 表示“还没有”。",
    "pronoms-complements": "直接宾语用 le/la/les；间接宾语 à + 人常用 lui/leur。",
    "connecteurs": "连接词要区分时间、因果、让步和递进，不能只按中文直译替换。",
    "comparatif": "bon 的形容词比较级是 meilleur；mieux 是副词 bien 的比较级。",
    "prepositions": "注意固定动词搭配以及 à/de 与定冠词的缩合。",
    "futur-anterieur": "先将来时表示在另一个未来时间点之前已经完成。",
    "but": "同一主语用 pour/afin de；不同主语用 pour que/afin que + 虚拟式。",
    "articles-partitifs": "du、de la、de l' 表示未计量的部分数量，否定后通常变为 de。",
    "inversion": "à peine、encore 等位于句首时常见正式倒装。",
    "plus-que-parfait": "愈过去时表示“过去的过去”，常与 comme si 或叙事先后关系连用。",
    "participes": "过去分词可表达被动并发生性数配合；现在分词通常表达主动。",
    "mise-en-relief": "c'est… que/qui 和 ce dont… c'est… 用来突出信息焦点。",
    "concession": "malgré/en dépit de 后接名词；bien que/quoique 后接虚拟式。",
    "hypothese-passee": "si + 愈过去时，主句用过去条件式，表达未实现的过去。",
    "registre": "il convient de 等表达主要用于正式书面语。",
    "locutions": "固定短语要整体记忆，包括其后的介词和动词形式。",
    "cause": "faute de 表示“因为缺少”；en raison de 表示中性原因。",
    "nominalisation": "正式写作常用名词化压缩信息，但要避免堆叠抽象名词。",
    "discours-indirect": "过去时引述动词后，未来时通常后移为条件式。",
}


def add_chinese_usage_help(questions):
    for question in questions:
        if "词汇与用法" not in question["explanation_zh"]:
            usage = CHINESE_USAGE_BY_GRAMMAR[question["grammar_key"]]
            question["explanation_zh"] = f"{question['explanation_zh']}\n词汇与用法：{usage}"
    return questions


def _fold_prompt(value):
    decomposed = unicodedata.normalize("NFKD", str(value).casefold())
    without_accents = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents).split())


def prompts_are_too_similar(first, second):
    first = _fold_prompt(first)
    second = _fold_prompt(second)
    if not first or not second:
        return False
    first_tokens = set(first.split())
    second_tokens = set(second.split())
    union = first_tokens | second_tokens
    jaccard = len(first_tokens & second_tokens) / len(union) if union else 0
    sequence = SequenceMatcher(None, first, second).ratio()
    return jaccard >= 0.6 or sequence >= 0.66


def _select(pool, count, usage, seed, avoid_prompts=()):
    candidates = deepcopy(pool)
    random.Random(seed).shuffle(candidates)
    candidates.sort(key=lambda item: usage.get(content_hash(item), ""))
    chosen = []
    blocked_prompts = list(avoid_prompts)
    selection_tiers = (
        (True, False),
        (False, False),
        (True, True),
        (False, True),
    )
    for require_unseen, allow_similar in selection_tiers:
        for candidate in candidates:
            if candidate in chosen:
                continue
            unseen = content_hash(candidate) not in usage
            if unseen != require_unseen:
                continue
            similar = any(
                prompts_are_too_similar(candidate["prompt"], previous)
                for previous in blocked_prompts
            )
            if similar and not allow_similar:
                continue
            chosen.append(candidate)
            blocked_prompts.append(candidate["prompt"])
            if len(chosen) == count:
                break
        if len(chosen) == count:
            break
    for item in chosen:
        item["content_hash"] = content_hash(item)
    return chosen


def distribute_correct_options(questions, seed):
    """Deterministically balance MCQ answers across A–D and shuffle distractors."""
    multiple_choice = [question for question in questions if question.get("options")]
    rng = random.Random(seed)
    positions = []
    while len(positions) < len(multiple_choice):
        cycle = list(range(4))
        rng.shuffle(cycle)
        positions.extend(cycle)
    for question, correct_position in zip(multiple_choice, positions):
        answer = question["answer"]
        distractors = sorted(option for option in question["options"] if option != answer)
        rng.shuffle(distractors)
        distractors.insert(correct_position, answer)
        question["options"] = distractors
    return questions


def generate_content(
    study_date, question_usage, vocabulary_usage, recent_prompts=()
):
    multiple_choice = _select(
        MCQ, 5, question_usage, f"{study_date}:mcq", recent_prompts
    )
    questions = multiple_choice + _select(
        FILL,
        5,
        question_usage,
        f"{study_date}:fill",
        [*recent_prompts, *(item["prompt"] for item in multiple_choice)],
    )
    add_chinese_usage_help(questions)
    distribute_correct_options(questions, f"{study_date}:daily-options")
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
