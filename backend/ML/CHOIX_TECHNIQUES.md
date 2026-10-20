# Choix techniques — Assistant RAG

L’assistant Phenix aide à comprendre un incident et à consulter les procédures du projet. Il s’appuie sur un corpus local et cite les documents utilisés. Il reste distinct de l’automate de remédiation et ne dispose pas d’outils pour intervenir sur le système.

## Composants retenus

| Composant | Choix | Raison |
| --- | --- | --- |
| Génération | `qwen3:4b-instruct` | Réponses jugées adaptées lors des premiers essais, avec une taille compatible avec la machine de développement. Modèle conservé pour la suite du projet. |
| Exécution | Ollama, intégré au Compose principal | Exécuter le modèle localement avec les autres composants du projet. |
| Recherche documentaire | LangChain et `embeddinggemma:300m` | Retrouver les passages du corpus pertinents pour la question avant de générer une réponse. |
| Index | Fichier JSON contenant les passages, leurs vecteurs et leurs métadonnées | Solution simple pour la taille actuelle du corpus, sans service de base vectorielle supplémentaire. |
| Documentation | Corpus local de procédures | Fournir des réponses fondées sur les informations du projet, en distinguant les contrôles connus des recommandations générales. |

## Premiers essais de modèles

Observations manuelles exploratoires, sans protocole comparatif ni mesure précise des temps de réponse.

| Modèle | Observations |
| --- | --- |
| Qwen 2.5 — 3B | Difficultés à produire une réponse concise et à respecter les citations ; confusions entre certaines informations du corpus. |
| Qwen 2.5 — 7B | Réponses plus satisfaisantes sur les questions essayées, mais encore longues et attente perçue comme plus importante. |
| Qwen 3 — 4B Instruct | Réponse pertinente avec une source sur un cas testé et abstention sur une information absente. Choix retenu pour poursuivre l’intégration. |

Ces essais ont aussi accompagné des ajustements du prompt et du corpus : les différences observées ne peuvent pas être attribuées au seul modèle. La priorité est désormais d’améliorer la documentation et de vérifier les réponses, plutôt que de poursuivre la comparaison des modèles.

## Limites et validation à poursuivre

- Le modèle ne connaît pas l’état réel des services : il explique les contrôles à effectuer.
- La vérification des références citées ne garantit pas que la réponse soit exacte ou entièrement étayée.
- Le corpus ne doit contenir aucun secret ; les actions nécessitant des privilèges restent du ressort d’un humain habilité ou d’un automate contrôlé.
- Le corpus élargi doit être testé sur les cas d’usage du projet, en relevant la pertinence des réponses, les sources, les abstentions et les temps de réponse.

Les commandes d’installation et d’utilisation figurent dans le README ; les sources et l’entretien du corpus sont décrits dans CORPUS.md.