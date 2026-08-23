# Mon français — système local TCF B1

Application locale de pratique quotidienne du français avec correction, historique, erreurs, grammaire, vocabulaire contextualisé et prononciation.

## Fonctionnalités

- 5 questions à choix multiple + 5 textes à compléter par jour ;
- questions et options uniquement en français ;
- correction avec explications en français et en chinois pour tous les choix ;
- 5 mots issus de contextes communautaires + 5 mots du quotidien ;
- une lecture B2 quotidienne adaptée d'une source RSS vérifiable, masquée avant confirmation, puis limitée à 8 minutes avec reprise du compte à rebours, remise anticipée et envoi automatique à échéance ;
- un sujet d'écriture B1–B2 avec compteur de mots, correction Mistral détaillée, barème strict sur 20 (quatre dimensions sur 5), erreurs réinjectées dans la révision, version corrigée, deux réponses modèles B2/C2 préparées avec le sujet, deux autres sur le thème choisi par l'apprenant, aide lexicale chinoise et conseils d'optimisation ;
- historique typé distinguant les 10 questions, la lecture et l'écriture ;
- historique SQLite, erreurs et statistiques par point de grammaire ;
- lecture locale hors ligne avec la voix macOS `Thomas (fr-FR)` : mots et exemples à la demande, phrases des exercices uniquement après publication de la correction ;
- préparation automatique quotidienne à 07:00 ;
- génération Mistral optionnelle avec double contrôle, sources communautaires récentes et repli hors ligne ;
- aucune dépendance Python externe ; les données RSS et prompts pédagogiques sont envoyés à Mistral lors de la préparation, et le texte de l'apprenant uniquement lorsqu'il demande explicitement une correction d'écriture.

## Génération Mistral sécurisée

La clé n'est jamais stockée dans le projet, la base, les logs ou les LaunchAgents. Elle est lue depuis le trousseau macOS :

```bash
security add-generic-password -U -a "$USER" -s "french-learning-mistral-api-key" -w
```

Le système utilise `mistral-medium-latest` pour générer les textes à compléter, le vocabulaire récent, une synthèse de lecture B2 et un sujet d'écriture, puis effectue une seconde passe de contrôle pédagogique. Les QCM quotidiens proviennent toujours de la banque humaine contrôlée. La lecture conserve une URL issue du RSS, est présentée comme une synthèse pédagogique adaptée et possède exactement quatre questions validées localement. En cas d'échec réseau ou de validation, toute la journée utilise les banques contrôlées hors ligne.

Une journée est générée une seule fois puis mise en cache. La préparation quotidienne réserve deux créneaux même si elle échoue. Chaque production écrite permet une seule correction finale et réserve un créneau avant l'appel ; un échec reste comptabilisé mais remet la tâche à l'état prêt afin de permettre une relance consciente. Le plafond commun est de 105 requêtes par mois : jusqu'à 62 pour 31 préparations quotidiennes, 31 corrections d'écriture et 12 créneaux de marge. Les tarifs Mistral peuvent évoluer ; le coût réel reste donc contrôlé par ce plafond dur et l'historique local d'usage, pas par une estimation figée.

La lecture suit un état serveur `ready → in_progress → completed`. Avant le démarrage, l'API ne transmet ni article ni questions. Après confirmation, le serveur fixe une échéance immuable de 8 minutes ; le navigateur affiche le temps restant à partir de cette échéance, conserve localement les choix en cas de rafraîchissement et envoie les réponses à 00:00. Une remise manuelle partielle est permise ; toute question vide est incorrecte. Si le navigateur est fermé, le serveur clôt l'exercice à la prochaine consultation, sans prolonger le temps.

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
