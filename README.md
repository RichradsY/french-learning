# Mon français — système local TCF B1

Application locale de pratique quotidienne du français avec correction, historique, erreurs, grammaire, vocabulaire contextualisé et prononciation.

## Fonctionnalités

- 5 questions à choix multiple + 5 textes à compléter par jour ;
- questions et options uniquement en français ;
- correction avec explications en français et en chinois pour tous les choix ;
- 5 mots issus de contextes communautaires + 5 mots du quotidien ;
- historique SQLite, erreurs et statistiques par point de grammaire ;
- lecture `fr-FR` des mots, exemples et questions via le navigateur ;
- préparation automatique quotidienne à 07:00 ;
- génération Mistral optionnelle avec double contrôle, sources communautaires récentes et repli hors ligne ;
- aucune dépendance Python externe ; seules les données publiques RSS et le prompt pédagogique sont envoyés à Mistral.

## Génération Mistral sécurisée

La clé n'est jamais stockée dans le projet, la base, les logs ou les LaunchAgents. Elle est lue depuis le trousseau macOS :

```bash
security add-generic-password -U -a "$USER" -s "french-learning-mistral-api-key" -w
```

Le système utilise `mistral-medium-latest` pour générer les textes à compléter et le vocabulaire récent, puis effectue une seconde passe de contrôle pédagogique. Les QCM proviennent toujours de la banque humaine contrôlée et suivent une rotation “jamais vu / moins récemment vu”, car une relecture LLM seule ne garantit pas l'absence de distracteurs sémantiquement interchangeables. Les structures sont ensuite validées localement : quantité, langue, réponses, explications bilingues, catégories et sources. En cas d'échec réseau ou de validation, toute la séance utilise la banque contrôlée hors ligne.

Une séance est générée une seule fois puis mise en cache. Avant chaque tentative en ligne, le garde-fou réserve deux créneaux de requête et les conserve même si la génération ou l'audit échoue ; un échec ne peut donc pas contourner le budget. Le plafond est de 70 créneaux par mois, soit au plus 35 tentatives quotidiennes à deux requêtes (génération puis audit). Une génération contrôlée observée pendant l'installation a consommé environ 16 000 tokens au total ; au tarif officiel constaté en août 2026, l'ordre de grandeur mensuel reste très inférieur au crédit de 12 €, mais les tarifs peuvent changer.

## Démarrage immédiat

Prérequis : Python 3.11 ou plus récent.

```bash
cd "/Users/ysx/Desktop/French Learning"
python3 -m french_learning serve
```

Ouvrir ensuite : http://127.0.0.1:8765

Arrêt : `Ctrl+C`.

## Démarrage automatique sur macOS

La commande suivante installe deux LaunchAgents utilisateur : le serveur local et la préparation quotidienne à 07:00.

```bash
cd "/Users/ysx/Desktop/French Learning"
python3 -m french_learning install-scheduler
```

Fichiers installés :

- `~/Library/LaunchAgents/com.local.french-learning.server.plist`
- `~/Library/LaunchAgents/com.local.french-learning.daily.plist`

Vérification :

```bash
launchctl print gui/$(id -u)/com.local.french-learning.server
launchctl print gui/$(id -u)/com.local.french-learning.daily
curl http://127.0.0.1:8765/api/health
```

Désinstallation manuelle :

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.local.french-learning.server.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.local.french-learning.daily.plist
rm ~/Library/LaunchAgents/com.local.french-learning.{server,daily}.plist
```

## Commandes utiles

Préparer la séance sans démarrer le serveur (opération idempotente) :

```bash
python3 -m french_learning generate-today
```

Forcer le mode hors ligne :

```bash
python3 -m french_learning generate-today --offline
python3 -m french_learning serve --offline
```

Exécuter tous les tests :

```bash
python3 -m unittest discover -s tests -v
```

Utiliser une autre base ou un autre port :

```bash
python3 -m french_learning serve --db /chemin/apprentissage.db --port 9000
```

Le serveur refuse volontairement les adresses non locales.

## Données, sauvegarde et restauration

La base réelle est `data/learning.db` (ignorée par Git).

Sauvegarde à froid : arrêter l'application, puis copier `data/learning.db`. Pour restaurer, arrêter l'application et remettre la copie au même emplacement. SQLite utilise WAL pendant l'exécution ; évitez de copier le seul fichier `.db` pendant que le serveur écrit.

## Structure

```text
french_learning/
  content.py       contenu B1 contrôlé et sélection déterministe
  repository.py    schéma et requêtes SQLite
  service.py       génération, redaction et correction
  mistral_provider.py génération IA, RSS, audit et validation stricte
  web.py           API HTTP locale et fichiers statiques
  scheduler.py     planification interne et LaunchAgents
  static/          interface HTML/CSS/JavaScript
tests/             tests unitaires et d'intégration HTTP
docs/              conception et traçabilité des exigences
data/               base locale, non versionnée
```

## Sources communautaires

Le générateur en ligne lit les titres RSS publics récents de `r/france` et, en repli, de France Info. Ces titres sont traités comme données non fiables, jamais comme instructions. Chaque mot communautaire conserve le nom et l'URL de sa source. Si Mistral est indisponible, la banque éditoriale locale fournit des mots traçables.

## Git

Voir les versions :

```bash
git log --oneline --decorate
```

Voir les changements locaux :

```bash
git status --short
git diff
```
