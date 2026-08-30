"""Additional controlled offline reading exercises."""
from __future__ import annotations


def _reading(title, sentences, questions, vocabulary):
    return {
        "title": title,
        "article_fr": " ".join(sentences),
        "source_name": "Contenu hors ligne contrôlé",
        "source_url": None,
        "time_limit_seconds": 480,
        "questions": [
            {
                "prompt": prompt,
                "options": [answer, *distractors],
                "answer": answer,
                "explanation_fr": explanation_fr,
                "explanation_zh": explanation_zh,
            }
            for prompt, answer, distractors, explanation_fr, explanation_zh in questions
        ],
        "vocabulary": [
            {"word": word, "definition_fr": definition_fr, "definition_zh": definition_zh}
            for word, definition_fr, definition_zh in vocabulary
        ],
    }


def additional_offline_readings():
    return [
        _reading(
            "Les fontaines publiques retrouvent une place dans les villes",
            [
                "Pendant plusieurs décennies, de nombreuses fontaines à boire ont disparu des rues, car leur entretien semblait coûteux et leur usage diminuait.",
                "Les épisodes de chaleur plus fréquents conduisent aujourd'hui certaines communes à revoir cette décision.",
                "Un accès gratuit à l'eau permet aux passants de remplir une gourde et aide particulièrement les personnes qui travaillent dehors ou vivent sans logement stable.",
                "La réinstallation ne consiste pourtant pas à poser un robinet au hasard sur un trottoir.",
                "Les services municipaux étudient les trajets piétons, la proximité des transports et les zones où l'ombre manque.",
                "Ils choisissent aussi des équipements résistants, faciles à nettoyer et accessibles aux enfants comme aux personnes en fauteuil roulant.",
                "Pour éviter le gaspillage, certains modèles s'arrêtent automatiquement et signalent une fuite à distance.",
                "Des analyses régulières vérifient la qualité de l'eau, tandis qu'un calendrier public indique la date du dernier contrôle.",
                "La carte des fontaines peut être intégrée à une application locale, mais elle reste également affichée sur des panneaux pour les visiteurs sans téléphone.",
                "Les habitants contribuent au suivi en signalant un appareil endommagé ou difficile à utiliser.",
                "Le succès du dispositif dépend donc moins du nombre de fontaines installées que de leur emplacement, de leur fiabilité et de la rapidité des réparations.",
                "Ainsi, un équipement urbain ancien devient un outil concret d'adaptation à la chaleur et d'accès équitable à une ressource essentielle.",
            ],
            [
                ("Pourquoi certaines communes réinstallent-elles des fontaines ?", "Pour faciliter l'accès à l'eau pendant les périodes chaudes", ["Pour remplacer tous les commerces", "Pour décorer uniquement les places historiques", "Pour interdire les gourdes personnelles"], "La chaleur et l'accès gratuit à l'eau motivent le retour de ces équipements.", "高温天气和免费饮水需求推动了公共饮水设施的恢复。"),
                ("Quels critères influencent le choix de l'emplacement ?", "Les trajets, les transports et le manque d'ombre", ["La couleur des voitures", "Le prix des logements voisins", "Le nombre de publicités"], "Les services observent les usages réels de l'espace public.", "市政部门会根据步行路线、交通站点和遮阴情况选址。"),
                ("Comment certains modèles limitent-ils le gaspillage ?", "Ils s'arrêtent automatiquement et détectent les fuites", ["Ils vendent l'eau au litre", "Ils restent fermés en été", "Ils utilisent des bouteilles jetables"], "L'arrêt automatique et le signalement des fuites réduisent les pertes.", "自动停水和漏水报警可以减少浪费。"),
                ("De quoi dépend principalement le succès du dispositif ?", "De l'emplacement, de la fiabilité et des réparations", ["Du nombre maximal de fontaines", "De leur ancienneté", "De leur valeur décorative"], "La conclusion insiste sur la qualité du service plutôt que sur la quantité.", "结论强调位置、可靠性和维修速度，而不是单纯追求数量。"),
            ],
            [("une gourde", "Une bouteille réutilisable.", "可重复使用的水瓶。"), ("une fuite", "Une perte involontaire de liquide.", "泄漏。"), ("fiable", "Qui fonctionne de manière sûre et régulière.", "可靠的。"), ("équitable", "Qui offre des conditions justes à chacun.", "公平的。")],
        ),
        _reading(
            "Les vélos-cargos partagés facilitent les petits transports",
            [
                "Transporter des courses lourdes ou accompagner deux jeunes enfants conduit souvent les habitants à utiliser une voiture, même pour quelques kilomètres.",
                "Pour proposer une autre solution, des quartiers mettent désormais des vélos-cargos électriques en location partagée.",
                "Leur caisse avant peut accueillir des sacs, du matériel ou des sièges équipés de ceintures.",
                "Une assistance électrique réduit l'effort, mais le poids et la longueur du vélo demandent tout de même un apprentissage.",
                "Les gestionnaires organisent donc une courte séance d'essai avant la première réservation.",
                "Ils expliquent le freinage, les virages et la manière de répartir correctement la charge.",
                "Les utilisateurs réservent ensuite un créneau sur Internet ou auprès d'un accueil de quartier, puis récupèrent une clé dans un casier sécurisé.",
                "Le tarif reste modeste afin que le service puisse remplacer occasionnellement une voiture sans exiger un achat coûteux.",
                "Le principal défi concerne la disponibilité aux heures les plus demandées, notamment le samedi matin.",
                "Certaines associations limitent donc la durée des réservations et déplacent les vélos entre plusieurs stations selon les besoins observés.",
                "Elles suivent aussi les pannes et les trajets, sans enregistrer l'itinéraire précis des personnes.",
                "Lorsqu'il est bien entretenu et simple à réserver, le vélo-cargo partagé devient un service pratique plutôt qu'un symbole réservé aux cyclistes expérimentés.",
            ],
            [
                ("À quel besoin répond le vélo-cargo partagé ?", "Transporter des personnes ou du matériel sur de courtes distances", ["Parcourir uniquement de longues autoroutes", "Remplacer les trains régionaux", "Organiser des compétitions sportives"], "La caisse permet d'emporter des charges ou de jeunes enfants.", "货运自行车可用于短途运送物品或儿童。"),
                ("Pourquoi une séance d'essai est-elle proposée ?", "Parce que le poids et la longueur demandent un apprentissage", ["Parce que l'assistance électrique est interdite", "Parce que chaque trajet doit être chronométré", "Parce que le vélo ne possède pas de freins"], "La conduite diffère de celle d'un vélo ordinaire.", "其重量和长度不同于普通自行车，需要先学习驾驶。"),
                ("Quel problème apparaît aux heures de forte demande ?", "Le manque de vélos disponibles", ["L'absence totale de pistes dans le pays", "Le prix des sièges pour enfants", "L'interdiction des réservations"], "Plusieurs personnes souhaitent parfois réserver le même créneau.", "高峰时段可能没有足够的车辆可供预约。"),
                ("Quelle condition rend le service réellement pratique ?", "Un entretien régulier et une réservation simple", ["Une utilisation réservée aux experts", "Un suivi détaillé de chaque itinéraire", "Une caisse toujours vide"], "La conclusion relie l'utilité à la fiabilité et à la simplicité.", "结论认为定期维护和便捷预约是实用性的关键。"),
            ],
            [("une caisse", "Un compartiment destiné à contenir une charge.", "货箱。"), ("répartir", "Distribuer entre plusieurs places.", "分配；分散。"), ("un créneau", "Une période disponible dans un emploi du temps.", "可预约的时间段。"), ("occasionnellement", "De temps en temps.", "偶尔。")],
        ),
        _reading(
            "Des voitures silencieuses apparaissent dans les trains régionaux",
            [
                "Dans un train régional, les voyageurs n'ont pas tous la même manière d'occuper leur trajet.",
                "Certains discutent en groupe ou téléphonent, tandis que d'autres souhaitent lire, dormir ou préparer une réunion.",
                "Pour réduire les conflits, plusieurs réseaux expérimentent une voiture silencieuse clairement signalée.",
                "Dans cet espace, les appels sont interdits, les conversations doivent rester très brèves et les appareils sont utilisés avec des écouteurs.",
                "La règle ne s'applique pas au reste du train, où les échanges ordinaires continuent.",
                "Les responsables insistent donc sur le choix : chaque passager peut sélectionner l'ambiance qui correspond à son besoin.",
                "Une signalétique visible sur le quai et dans l'application évite que les voyageurs découvrent la règle après leur installation.",
                "Au début de l'expérimentation, des agents expliquent le fonctionnement sans distribuer immédiatement de sanction.",
                "Ils notent les remarques, le taux d'occupation et les situations qui restent difficiles, par exemple lorsqu'une famille ne trouve plus de places ailleurs.",
                "Les associations d'usagers demandent aussi que la voiture silencieuse reste accessible aux personnes à mobilité réduite.",
                "Après quelques mois, le réseau peut modifier l'emplacement ou les horaires du dispositif selon la fréquentation.",
                "L'objectif n'est pas d'imposer le silence à tous, mais d'organiser des usages différents dans un espace collectif limité.",
            ],
            [
                ("Pourquoi les réseaux testent-ils une voiture silencieuse ?", "Pour permettre plusieurs usages du trajet sans conflit", ["Pour supprimer tous les contrôleurs", "Pour raccourcir les lignes", "Pour réserver le train aux travailleurs"], "L'espace séparé répond aux besoins différents des voyageurs.", "安静车厢让不同出行需求共存并减少冲突。"),
                ("Où les conversations ordinaires restent-elles possibles ?", "Dans les autres voitures du train", ["Uniquement sur le quai", "Nulle part dans le réseau", "Seulement auprès du conducteur"], "La règle de silence est limitée à une voiture choisie.", "安静规则只适用于指定车厢，其他车厢仍可正常交谈。"),
                ("Pourquoi la signalétique doit-elle être visible avant l'embarquement ?", "Pour que les passagers choisissent leur ambiance à l'avance", ["Pour vendre des écouteurs", "Pour modifier le prix du billet", "Pour fermer les autres voitures"], "Une information précoce évite une découverte tardive de la règle.", "清晰标识让乘客上车前就能选择合适的车厢。"),
                ("Quel est l'objectif général du dispositif ?", "Organiser des usages différents dans un espace partagé", ["Imposer le silence à tous", "Interdire les voyages en famille", "Remplacer les trains par des bureaux"], "La conclusion présente une coexistence organisée plutôt qu'une interdiction générale.", "该措施旨在组织共享空间中的不同用途，而非要求所有人保持安静。"),
            ],
            [("un quai", "La zone où les voyageurs attendent le train.", "站台。"), ("une sanction", "Une conséquence imposée après le non-respect d'une règle.", "处罚。"), ("la fréquentation", "Le nombre de personnes qui utilisent un lieu.", "使用人数；客流量。"), ("un taux d'occupation", "La proportion de places utilisées.", "占用率。")],
        ),
        _reading(
            "Les jardins de pluie absorbent l'eau au cœur des quartiers",
            [
                "Lors d'un orage intense, l'eau ruisselle rapidement sur les toits, les routes et les parkings sans pouvoir pénétrer dans le sol.",
                "Les canalisations reçoivent alors un volume trop important et certaines rues peuvent être inondées en quelques minutes.",
                "Pour ralentir ce phénomène, des villes aménagent des jardins de pluie le long des trottoirs ou au pied des immeubles.",
                "Ces zones légèrement creusées recueillent temporairement l'eau qui arrive des surfaces voisines.",
                "Un mélange de terre, de sable et de graviers facilite ensuite son infiltration progressive.",
                "Les plantes choisies supportent à la fois de courtes périodes humides et plusieurs jours de sécheresse.",
                "Le dispositif ne remplace pas toutes les canalisations, mais il réduit la quantité d'eau qui y arrive au même moment.",
                "Il peut également rafraîchir la rue, offrir un abri aux insectes et rendre un espace minéral plus agréable.",
                "Son entretien reste toutefois indispensable : des déchets peuvent bloquer l'entrée de l'eau et certaines plantes doivent être remplacées.",
                "Les équipes observent aussi la vitesse d'infiltration afin de vérifier que le sol ne s'est pas compacté.",
                "Avant de multiplier ces jardins, la commune cartographie les points où l'eau s'accumule réellement pendant les pluies.",
                "Cette solution est donc efficace lorsqu'elle complète une stratégie plus large associant sols perméables, arbres et réseaux bien entretenus.",
            ],
            [
                ("Quel problème les jardins de pluie cherchent-ils à limiter ?", "L'arrivée trop rapide de l'eau dans les canalisations", ["Le manque de circulation automobile", "La croissance des arbres anciens", "La baisse du niveau des rivières en été"], "Ils retiennent temporairement une partie de l'eau de l'orage.", "雨水花园暂时储水，减少雨水短时间内涌入管网。"),
                ("Comment l'eau pénètre-t-elle progressivement dans le sol ?", "Grâce à un mélange de terre, de sable et de graviers", ["Grâce à une couche de béton", "Grâce à des pompes dans chaque plante", "Grâce à la fermeture des trottoirs"], "Les matériaux perméables facilitent l'infiltration.", "土壤、沙子和砾石的混合层有助于雨水逐步渗透。"),
                ("Pourquoi l'entretien reste-t-il nécessaire ?", "Parce que des déchets peuvent bloquer l'eau", ["Parce que les plantes doivent rester sèches", "Parce que le jardin remplace toutes les canalisations", "Parce que le sable doit être peint"], "Une entrée obstruée empêche le dispositif de fonctionner.", "垃圾可能堵塞进水口，因此需要维护。"),
                ("Dans quelle stratégie cette solution doit-elle s'inscrire ?", "Une combinaison de sols perméables, d'arbres et de réseaux entretenus", ["La suppression de tous les espaces verts", "L'élargissement systématique des routes", "L'arrosage permanent des parkings"], "La conclusion recommande plusieurs actions complémentaires.", "结论强调透水地面、树木和良好维护的管网应配合使用。"),
            ],
            [("ruisseler", "Couler à la surface du sol.", "在地表流淌。"), ("une infiltration", "Le passage progressif d'un liquide dans un matériau.", "渗透。"), ("se compacter", "Devenir plus dense et moins perméable.", "变得密实。"), ("perméable", "Qui laisse passer l'eau.", "可渗透的。")],
        ),
        _reading(
            "La chaleur des centres de données peut chauffer des bâtiments",
            [
                "Les serveurs informatiques fonctionnent jour et nuit et produisent une quantité importante de chaleur.",
                "Dans un centre de données classique, des systèmes de refroidissement évacuent cette énergie vers l'extérieur afin de protéger les équipements.",
                "Certains projets cherchent désormais à la récupérer pour chauffer des logements, une piscine ou des bureaux voisins.",
                "Un circuit transporte la chaleur vers une pompe qui augmente sa température avant de l'injecter dans un réseau local.",
                "Cette récupération peut réduire l'usage du gaz ou de l'électricité consacré au chauffage.",
                "Elle exige cependant une proximité suffisante entre le centre informatique et les bâtiments consommateurs.",
                "Transporter de l'eau chaude sur une longue distance entraîne des pertes et augmente le coût des travaux.",
                "La demande varie aussi selon les saisons : les serveurs chauffent en été, lorsque les logements en ont peu besoin.",
                "Les gestionnaires recherchent donc des usages réguliers, comme l'eau chaude d'une piscine ou certains procédés industriels.",
                "Un contrat doit préciser la quantité de chaleur disponible, le prix et la solution de secours en cas d'arrêt technique.",
                "Les collectivités vérifient également que le projet ne justifie pas une consommation informatique inutile simplement pour produire de la chaleur.",
                "Bien planifiée, cette coopération transforme une énergie perdue en ressource locale, sans faire disparaître la nécessité de réduire la consommation numérique.",
            ],
            [
                ("Que devient la chaleur dans un centre de données classique ?", "Elle est évacuée pour protéger les équipements", ["Elle est stockée dans les serveurs", "Elle produit directement des données", "Elle refroidit les logements voisins"], "Le refroidissement rejette normalement cette énergie vers l'extérieur.", "传统数据中心通常把热量排到室外以保护设备。"),
                ("Quel équipement augmente la température récupérée ?", "Une pompe à chaleur", ["Un panneau publicitaire", "Une batterie de téléphone", "Un compteur de données"], "La pompe rend la chaleur compatible avec le réseau local.", "热泵提高回收热量的温度，使其可用于本地供热。"),
                ("Pourquoi la proximité des bâtiments est-elle importante ?", "Parce qu'une longue distance provoque des pertes et des coûts", ["Parce que les serveurs doivent être visibles", "Parce que les habitants réparent les ordinateurs", "Parce que l'eau chaude ne circule jamais"], "Le transport éloigné diminue l'efficacité économique et énergétique.", "距离过远会造成热量损失并增加建设成本。"),
                ("Quelle précaution la conclusion conserve-t-elle ?", "Il faut aussi réduire la consommation numérique", ["Il faut produire davantage de chaleur informatique", "Il faut supprimer toutes les solutions de secours", "Il faut chauffer uniquement en été"], "La récupération ne doit pas remplacer les efforts de sobriété numérique.", "热量回收不能取代减少数字能源消耗的努力。"),
            ],
            [("évacuer", "Faire sortir d'un lieu.", "排出。"), ("une perte", "Une quantité d'énergie qui n'arrive pas à destination.", "损耗。"), ("un procédé", "Une méthode technique de production.", "工艺；技术方法。"), ("la sobriété", "La réduction volontaire d'une consommation.", "节制使用；降低消耗。")],
        ),
    ]
