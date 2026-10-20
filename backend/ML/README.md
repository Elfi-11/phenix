# Assistant documentaire RAG — Phenix

Assistant local de consultation des procédures, avec réponses en français et sources. Il explique les contrôles sans les exécuter et ne connaît pas l’état réel des services.

## Démarrage depuis la racine du projet

Le RAG utilise le `docker-compose.yml` principal. Sous Windows, lancer la plateforme avec le script SOPS de l’équipe, depuis PowerShell à la racine :

```powershell
.\infra\secrets\start.ps1
```

Sous Linux/WSL :

```bash
infra/secrets/start.sh
```

Ces scripts doivent lancer le Compose principal sans exclure les services IA. Ne pas remplacer le démarrage général par `docker compose up` sans le mécanisme SOPS : les services métier ont besoin des secrets déchiffrés. La clé reste hors du dépôt, à l’emplacement indiqué dans le README principal.

### Préparation automatique des modèles

1. `ollama` démarre et son contrôle de santé devient positif.
2. `ollama-init` vérifie la présence de `embeddinggemma:300m` et `qwen3:4b-instruct` ; il télécharge uniquement les modèles absents.
3. `rag` peut démarrer lorsque l’initialisation s’est terminée avec succès.

Le premier démarrage peut prendre plusieurs minutes et nécessite Internet pour les téléchargements. Les démarrages suivants réutilisent les modèles présents, sans mise à jour automatique de leurs poids. `ollama-init` en état `Exited (0)` est normal. `rag` affiche l’aide puis se termine également : il s’agit d’un outil CLI, pas d’un serveur HTTP.

## Indexer les documents et poser une question

Toutes les commandes suivantes partent de la racine du dépôt, après le démarrage SOPS et la fin de l’initialisation des modèles.

```powershell
# Première ingestion, ou après modification du corpus
docker compose --env-file .env.example run --rm --no-deps rag python -m rag ingest

# Réponse avec ses sources
docker compose --env-file .env.example run --rm --no-deps rag python -m rag ask "Comment vérifier la collecte Prometheus ?"

# Passages retrouvés, sans génération
docker compose --env-file .env.example run --rm --no-deps rag python -m rag retrieve "Comment vérifier la collecte Prometheus ?"
```

Pour ces opérations IA uniquement, `--env-file .env.example` fournit les valeurs factices nécessaires à la lecture du Compose et évite les avertissements sur les variables métier. `--no-deps` empêche de démarrer ou de recréer les dépendances : Ollama doit déjà être prêt. Ces commandes ne démarrent pas les services métier et ne remplacent pas le script SOPS. Les services IA ne reçoivent pas les secrets métier.

Le fichier `.env.example` doit contenir les noms de variables attendus par le Compose, avec des valeurs factices ; sinon des avertissements peuvent subsister. Ne pas écrire les vrais secrets dans ce fichier.

L’ingestion reste **manuelle**. Elle crée l’index documentaire, sans réentraîner le modèle. Elle est nécessaire si l’index manque ou après ajout, modification ou suppression d’un document. Le téléchargement automatique des modèles ne déclenche pas l’ingestion. Une indexation conditionnelle au démarrage pourra être ajoutée ultérieurement.

## Persistance

| Élément | Emplacement | Après suppression |
| --- | --- | --- |
| Modèles | Volume Compose `ollama_models` | Retéléchargés par `ollama-init` au prochain démarrage complet |
| Index documentaire | Volume Compose `rag_index` | Relancer `ingest` |
| Corpus | `backend/ML/corpus/`, monté en lecture seule | Restaurer les fichiers du dépôt si supprimés |

**Dans cette version du Compose, les volumes IA sont gérés par Compose et ne sont plus externes.** Ils sont créés automatiquement. Un `docker compose down` les conserve ; `docker compose down -v` supprime les volumes gérés du projet, y compris ceux des données métier. Ne pas utiliser `-v` pour un arrêt courant.

Les anciens volumes externes `phenix-rag_*` ne sont pas réutilisés explicitement par cette configuration. Un changement de nom de projet Compose peut aussi sélectionner d’autres volumes. Ne pas supprimer les anciens volumes avant d’avoir vérifié les données à conserver.

## Maintenance et diagnostic

```powershell
# Voir les modèles installés
docker compose --env-file .env.example exec ollama ollama list

# Lire les résultats de l’initialisation et les erreurs du serveur
docker compose --env-file .env.example logs --tail=80 ollama-init ollama

# Réessayer la préparation si un téléchargement a échoué, serveur Ollama démarré
docker compose --env-file .env.example run --rm --no-deps ollama-init

# Reconstruire le code RAG après une modification de Python ou des dépendances
docker compose --env-file .env.example build rag
```

Une modification du corpus ne nécessite pas de build : relancer seulement `ingest`. Une modification des modèles retenus nécessite de garder cohérents le service `ollama-init`, les variables `RAG_CHAT_MODEL` / `RAG_EMBEDDING_MODEL` et la documentation. Un changement de modèle d’embeddings nécessite aussi une nouvelle ingestion.

Un HTTP 404 sur `/api/chat` peut signaler un modèle de génération absent ; vérifier son nom configuré et `ollama list`. Le contrôle de santé du serveur seul ne prouve pas que les modèles sont disponibles. Un appel `/api/embed` réussi ne valide pas la génération de réponse.

## Organisation et limites

- `rag/` : chargement, indexation, recherche et génération avec LangChain et Ollama.
- `corpus/` : documents `.md`, `.txt` UTF-8 et PDF texte ; aucun secret ni journal sensible.
- `tests/` : vérifications avec modèles simulés.
- [CHOIX_TECHNIQUES.md](CHOIX_TECHNIQUES.md) : composants retenus et premiers essais.
- [CORPUS.md](CORPUS.md) : sources et entretien de la documentation.

Les modèles sont exécutés localement, sur CPU dans cette configuration. Le RAG et Ollama utilisent le réseau dédié `rag`, sans port publié, socket Docker ou accès configuré aux réseaux métier. Les modèles sont stockés dans le volume du serveur ; l’image du client d’initialisation ne les embarque pas.

Les références citées ne garantissent pas la justesse de chaque affirmation. Les réponses doivent être vérifiées sur les cas du projet. Le RAG n’a pas d’outil de remédiation, d’API HTTP, d’interface web ni de mémoire de conversation ; une API reste à prévoir pour le futur front.

## Références

- Dépendances Compose : https://docs.docker.com/compose/how-tos/startup-order/
- Commandes Ollama : https://docs.ollama.com/cli