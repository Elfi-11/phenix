# Assistant documentaire RAG — Phenix

Assistant local destiné aux opérateurs de la plateforme. Il recherche des passages
pertinents dans un corpus validé et génère une réponse courte en français avec des
références. Il utilise Ollama, les intégrations LangChain et un index JSON local.
Il explique des procédures sans les exécuter et ne consulte pas l'état des services.

## Commandes courantes depuis la racine

Toutes les commandes ci-dessous se lancent depuis le dossier `phenix`, où se trouve le `docker-compose.yml` principal, et non depuis `backend/ML`. Les services `rag` et `ollama` doivent y être définis. Aucun `-f compose.rag.yml` n’est nécessaire.

Après l’installation initiale et le téléchargement des modèles :

```bash
# Démarrer le serveur de modèles
docker compose up -d ollama

# Créer ou mettre à jour l’index après un changement du corpus
docker compose run --rm rag python -m rag ingest

# Poser une question
docker compose run --rm rag python -m rag ask "Comment vérifier la collecte Prometheus ?"

# Examiner les passages retrouvés sans générer de réponse
docker compose run --rm rag python -m rag retrieve "Comment vérifier la collecte Prometheus ?"
```

L’ingestion est actuellement **manuelle**. Elle est nécessaire après l’ajout, la modification ou la suppression de documents dans `backend/ML/corpus/`, mais pas avant chaque question. Le corpus est monté en lecture seule depuis le dépôt ; une modification documentaire ne nécessite pas de reconstruire l’image.

À terme, une vérification au démarrage pourra déclencher l’indexation uniquement si le corpus a changé. **Cette automatisation n’est pas encore implémentée.**

Le service `rag` reste un outil en ligne de commande. L’accès depuis un futur front nécessitera une API ; ces commandes ne créent pas de serveur HTTP.

## Architecture

Le RAG est intégré au **`docker-compose.yml` principal**, à la racine du dépôt.
Les commandes de cette page s'exécutent depuis cette racine.

| Élément | Rôle |
| --- | --- |
| Service `ollama` | Serveur local des modèles, démarré avec la plateforme |
| Service `rag` | Outil CLI construit depuis `backend/ML`, lancé pour une opération ponctuelle |
| `rag/` | Chargement, indexation, recherche documentaire et génération |
| `corpus/` | Documents sélectionnés, montés en lecture seule |
| `tests/` | Tests fonctionnels avec modèles simulés |
| [CHOIX_TECHNIQUES.md](CHOIX_TECHNIQUES.md) | Observations des essais, choix actuels et pistes de travail |

Modèles par défaut : **`qwen3:4b-instruct`** pour les réponses, sous la limite de
8 milliards de paramètres du sujet, et **`embeddinggemma:300m`** pour les embeddings.
L'image Ollama est fixée à `0.11.10`. La configuration fournie utilise le CPU,
sans allocation GPU. Les modèles sont téléchargés dans un volume, pas dans l'image.

L'indexation découpe les documents, calcule leurs embeddings et les stocke dans un
index JSON. La question est vectorisée et comparée aux passages par similarité
cosinus. LangChain assemble les passages retenus et la question dans le prompt
transmis au LLM. Cette opération ne réentraîne pas le modèle.

## Transition depuis le Compose RAG séparé

Pour un poste ayant utilisé `backend/ML/compose.rag.yml`, arrêter d'abord l'ancien
projet, avant de démarrer Ollama depuis le Compose principal :

```bash
docker compose -f backend/ML/compose.rag.yml down
```

Ne pas ajouter `-v`. Le Compose principal réutilise explicitement les volumes
`phenix-rag_ollama_models` et `phenix-rag_rag_index` créés par l'ancien projet.
Le premier conserve les modèles et le second l'index. Éviter de lancer les deux
projets en parallèle sur ces mêmes volumes.

Après la transition, retirer `backend/ML/compose.rag.yml` du dépôt pour conserver
une seule définition des services. Son arrêt doit être effectué avant son retrait.
La suppression du fichier Compose ne supprime pas les volumes.

## Installation et démarrage

Prérequis : Docker avec Docker Compose, les fichiers de `backend/ML` présents,
et ressources suffisantes pour le modèle et les autres services. La configuration
des secrets de la plateforme reste celle du Compose principal ; elle n'est pas
injectée dans les services `ollama` et `rag`.

Les deux volumes IA sont déclarés **externes** : ils sont indépendants du nom du
projet principal et doivent exister avant le démarrage. Sur un poste neuf, les créer
une fois. Les commandes suivantes peuvent aussi être lancées sur un poste où ils
existent déjà ; elles réutilisent les volumes sans vider leur contenu :

```bash
docker volume create phenix-rag_ollama_models
docker volume create phenix-rag_rag_index
```

Construire les images et démarrer la plateforme :

```bash
docker compose up -d --build
```

Pour reconstruire et démarrer seulement la partie IA, lorsque les autres services
sont déjà en place :

```bash
docker compose up -d --build ollama rag
```

`ollama` reste démarré. `rag` affiche l'aide et se termine normalement avec le code 0 :
c'est un outil CLI, pas encore un serveur de chat. Le healthcheck Ollama vérifie que
le serveur répond, pas que les modèles sont téléchargés ni qu'une réponse est correcte.

### Préparation sur un nouveau poste

Télécharger les modèles après le démarrage d'Ollama :

```bash
docker compose exec ollama ollama pull qwen3:4b-instruct
docker compose exec ollama ollama pull embeddinggemma:300m
```

Ces téléchargements ne sont pas nécessaires sur le poste ayant déjà les deux
modèles dans le volume conservé. Vérifier leur présence avec :

```bash
docker compose exec ollama ollama list
```

Indexer les documents si l'index est absent ou si le corpus a changé :

```bash
docker compose run --rm rag python -m rag ingest
```

La construction des images ne télécharge pas les modèles et n'indexe pas les documents.
Une connexion Internet est nécessaire aux téléchargements initiaux ; les requêtes
aux modèles et la recherche documentaire sont ensuite locales.

## Utilisation

Rechercher les passages, sans génération :

```bash
docker compose run --rm rag python -m rag retrieve "Comment vérifier la collecte Prometheus ?"
```

Obtenir une réponse avec ses références :

```bash
docker compose run --rm rag python -m rag ask "Comment vérifier la collecte Prometheus ?"
```

`ask` affiche le texte et les noms des sources. `retrieve` et `ingest` produisent du
JSON. Les erreurs sont écrites en JSON sur stderr avec un code de sortie 1.
Une réponse sans référence reconnue est remplacée par un message de non-validation.

Pour essayer un autre modèle déjà téléchargé :

```bash
docker compose run --rm -e RAG_CHAT_MODEL=qwen2.5:7b rag python -m rag ask "Comment vérifier la collecte Prometheus ?"
```

Pour vérifier le serveur ou ses journaux :

```bash
docker compose ps ollama
docker compose logs --tail=100 ollama
```

`docker compose stop ollama` arrête le serveur IA. `docker compose down` arrête
la plateforme complète. Les volumes IA externes restent conservés par Compose ;
les volumes métier restent soumis à leurs propres règles. Pour un arrêt courant,
ne pas employer `down -v`.

## Corpus et mises à jour

Le corpus couvre les contrôles d’observabilité et des procédures d’incident : injections SQL, surcharge, problèmes d’accès, indisponibilités, sauvegardes et escalade humaine. Les fiches distinguent les éléments connus du projet des recommandations générales à adapter. Le scénario de paiement reste à vérifier avec le contrat API réellement disponible.

Les sources et les points à valider sont présentés dans [CORPUS.md](CORPUS.md). Chaque nouvelle procédure doit préciser son objectif, son environnement, ses prérequis, ses étapes et le résultat attendu.

Seul `backend/ML/corpus/` est lu : `.md`, `.txt` UTF-8 et PDF texte. Les fichiers
cachés et liens symboliques sont exclus. Les PDF scannés nécessitent un OCR préalable.
Ne pas y déposer de secrets, fichiers d'environnement ou journaux sensibles : un
secret inclus dans un Markdown ne serait pas automatiquement détecté.

| Modification | Action depuis la racine du dépôt |
| --- | --- |
| Documents ajoutés, modifiés ou supprimés | `docker compose run --rm rag python -m rag ingest` |
| Code Python, prompt ou dépendances RAG | `docker compose build rag` |
| Paramètres du service `rag` dans Compose | Pris en compte au prochain `docker compose run` |
| Configuration du serveur Ollama dans Compose | `docker compose up -d ollama` |
| Modèle de génération | Télécharger le modèle et changer `RAG_CHAT_MODEL` |
| Modèle d'embeddings, ses poids ou découpage | Reconstruire l'index avec `ingest` |

Un contrôle d'empreintes bloque les questions sur un corpus modifié tant que
l'index n'a pas été reconstruit. L'index est stocké dans le volume `rag_index`,
les modèles dans `ollama_models`, et les documents dans le dépôt.

## Configuration et réseau

Les variables sont définies dans le service `rag` du Compose principal. Les valeurs
de repli pour une exécution Python directe sont dans `rag/config.py`.

| Variable | Valeur dans Docker |
| --- | --- |
| `OLLAMA_BASE_URL` | `http://ollama:11434` |
| `RAG_CHAT_MODEL` | `qwen3:4b-instruct` |
| `RAG_EMBEDDING_MODEL` | `embeddinggemma:300m` |
| `RAG_CORPUS_DIR` | `/workspace/corpus` |
| `RAG_INDEX_PATH` | `/workspace/data/index.json` |

Les services IA partagent un réseau dédié `rag`. Aucun port Ollama n'est publié,
aucun accès aux réseaux `app`, `data` ou `ops`, à la base métier, aux fichiers de
secrets ni au socket Docker n'est configuré. Ce réseau n'est pas déclaré `internal`
afin de permettre à Ollama de télécharger les modèles ; ce n'est pas un blocage
général des connexions sortantes.

| Adresse | Environnement | Usage |
| --- | --- | --- |
| `http://localhost:9090/targets` | Navigateur du PC hôte de la plateforme | État des cibles Prometheus |
| `http://localhost:8080/docs` | Navigateur du même PC hôte | Swagger via l'entrée web de la plateforme |
| `http://backend:8000/metrics` | Réseau `app` de la plateforme | Collecte des métriques du backend |
| `http://ollama:11434` | Réseau `rag` | Appels aux modèles |

`localhost` désigne la machine ou le conteneur effectuant l'appel. Le nom `backend`
n'est pas disponible par cette configuration depuis le réseau `rag`. PromQL se
saisit dans Prometheus, pas sur `/metrics`. Un état UP valide la collecte, pas un
paiement ; un compteur stable sans nouvel appel est normal.

## Vérifications et limites

Découpage : 1000 caractères, chevauchement de 150 ; au plus 4 passages par question,
seuil cosinus initial 0.35. Le seuil reste à calibrer et peut être précisé avec
`--min-similarity` après la question. Il ne représente pas une probabilité de vérité.
Génération : température 0, contexte de 4096 tokens, plafond de 600 tokens générés,
timeout client de 180 secondes. La limite de 80 mots est une consigne au modèle.

Les contrôles de références ne prouvent pas la justesse de chaque affirmation.
Les consignes sur les secrets et les injections de prompt ne garantissent pas
l'absence de fuite ou d'hallucination ; le corpus et les réponses doivent être relus.
Le RAG ne dispose d'aucun outil d'exécution d'actions système. Il n'a actuellement
ni interface web, ni API HTTP, ni mémoire de conversation.

Exécuter les tests avec des modèles simulés dans un conteneur temporaire :

```bash
docker compose run --rm -v ./backend/ML/tests:/workspace/tests:ro rag sh -c "pip install pytest && python -m pytest -q"
```

Ces tests ne mesurent ni la pertinence des vrais embeddings, ni la fidélité des
réponses du LLM, ni les performances matérielles. Les observations des modèles
sont décrites dans [CHOIX_TECHNIQUES.md](CHOIX_TECHNIQUES.md).