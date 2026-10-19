# Assistant documentaire RAG — Phenix

Assistant local destiné aux opérateurs de la plateforme. Il recherche des passages
pertinents dans un corpus validé et génère une réponse courte en français avec des
références. Il utilise Ollama, les intégrations LangChain et un index JSON local.
Il n'exécute aucune remédiation et ne consulte pas l'état des services en direct.

## Architecture

| Composant | Rôle |
| --- | --- |
| `rag/` | Chargement documentaire, indexation, recherche et génération |
| `corpus/` | Ressources indexées : Markdown, texte UTF-8 et PDF texte |
| `tests/` | Tests fonctionnels avec doubles de modèles, sans Ollama |
| `compose.rag.yml` | Services `ollama` et `rag`, projet Docker `phenix-rag` |
| `Dockerfile`, `requirements.txt` | Construction de l'image Python du RAG |
| [Choix techniques et observations](CHOIX_TECHNIQUES.md) | Modèles comparés, résultats observés et protocole de validation |

Modèles par défaut : **`qwen3:4b-instruct`** pour les réponses et
**`embeddinggemma:300m`** pour les embeddings multilingues. Le modèle de génération
respecte la limite de huit milliards de paramètres du sujet.

L'indexation découpe les documents en passages, calcule leurs embeddings et les
stocke dans l'index. Une question est vectorisée pour retrouver les passages par
similarité cosinus. LangChain assemble ces passages et la question dans le prompt
transmis au LLM. Cette opération ne réentraîne pas le modèle.

## Installation

Prérequis : Docker avec Docker Compose, ressources suffisantes pour les modèles
et connexion Internet pour les premiers téléchargements. Toutes les commandes
ci-dessous s'exécutent depuis `backend/ML`.

```bash
docker compose -f compose.rag.yml up -d ollama
docker compose -f compose.rag.yml exec ollama ollama pull qwen3:4b-instruct
docker compose -f compose.rag.yml exec ollama ollama pull embeddinggemma:300m
docker compose -f compose.rag.yml build rag
docker compose -f compose.rag.yml run --rm rag python -m rag ingest
```

Attendre la fin de chaque commande. Si le service Ollama est encore en démarrage,
attendre qu'il soit disponible avant de relancer le téléchargement. L'image Ollama
est fixée à `0.11.10`. Le Compose fourni utilise le CPU ; aucun GPU n'est configuré.
Après installation, la recherche et la génération sont locales.

## Utilisation

Rechercher les passages sans appeler le modèle de génération :

```bash
docker compose -f compose.rag.yml run --rm rag python -m rag retrieve "Comment vérifier la collecte Prometheus ?"
```

Obtenir une réponse avec ses références :

```bash
docker compose -f compose.rag.yml run --rm rag python -m rag ask "Comment vérifier la collecte Prometheus ?"
```

`ask` affiche le texte et les fichiers cités. `retrieve` affiche les passages,
leurs métadonnées et leurs scores en JSON ; `ingest` affiche le nombre de fichiers
et de passages indexés. Les erreurs sont écrites en JSON sur stderr avec un code
de sortie 1. Une réponse sans référence reconnue est remplacée par un message
de non-validation ; cela ne signifie pas nécessairement que la recherche a échoué.

Changer temporairement de modèle, après son téléchargement :

```bash
docker compose -f compose.rag.yml run --rm -e RAG_CHAT_MODEL=qwen2.5:7b rag python -m rag ask "Comment vérifier la collecte Prometheus ?"
```

Arrêter les services sans supprimer les modèles ni l'index :

```bash
docker compose -f compose.rag.yml down
```

## Corpus et mises à jour

Les trois procédures initiales couvrent la collecte Prometheus, les compteurs HTTP
et la réponse du backend via Nginx. Ajouter dans `corpus/` les procédures validées
par l'équipe, avec un objectif, l'environnement concerné, les prérequis, les étapes,
le résultat attendu et les limites. Les procédures de reprise et le scénario
principal restent à documenter en fonction de l'implémentation.

Seul `corpus/` est lu. Les fichiers cachés et les liens symboliques sont exclus.
Ne pas y déposer de secrets, fichiers d'environnement ou journaux sensibles.
Un secret placé dans un fichier Markdown ne serait pas automatiquement détecté.
Les PDF scannés nécessitent un OCR préalable ; contrôler l'extraction des PDF complexes.

| Modification | Action |
| --- | --- |
| Documents ajoutés, modifiés ou supprimés | Relancer `ingest` |
| Code Python, prompt ou dépendances | Relancer `build rag` |
| Modèle de génération | Télécharger le modèle et changer `RAG_CHAT_MODEL` |
| Modèle d'embeddings, ses poids ou le découpage | Reconstruire l'index avec `ingest` |

Le corpus est monté en lecture seule depuis le PC hôte. L'index est conservé dans
le volume `rag_index` et les modèles dans `ollama_models`. Ils ne sont pas inclus
dans l'image du RAG. Ne pas utiliser `down -v` pour un arrêt courant.
Un contrôle d'empreintes bloque les questions lorsque le corpus a changé depuis
l'indexation, jusqu'à reconstruction de l'index.

## Configuration

Les variables du service sont définies dans `compose.rag.yml`. Les valeurs de
repli pour une exécution Python directe sont dans `rag/config.py`.

| Variable | Valeur dans Docker |
| --- | --- |
| `OLLAMA_BASE_URL` | `http://ollama:11434` |
| `RAG_CHAT_MODEL` | `qwen3:4b-instruct` |
| `RAG_EMBEDDING_MODEL` | `embeddinggemma:300m` |
| `RAG_CORPUS_DIR` | `/workspace/corpus` |
| `RAG_INDEX_PATH` | `/workspace/data/index.json` |

Découpage : 1000 caractères par passage, chevauchement de 150. Recherche : au plus
4 passages, seuil cosinus initial de 0.35. Le seuil peut être précisé avec
`--min-similarity` après la question. Il reste à calibrer : un score n'est pas une
probabilité de pertinence ou de véracité. Génération : température 0, contexte de
4096 tokens, plafond de 600 tokens générés, timeout client de 180 secondes.
La consigne de 80 mots est donnée au modèle, sans contrôle strict du nombre de mots.

### Réseau et environnements

Le Compose RAG possède son propre réseau, sans port Ollama publié et sans accès
configuré à la base métier ni au socket Docker. Le nom `backend` appartient au
réseau de la plateforme principale ; sa résolution n'est pas garantie depuis le RAG.

| Adresse | Environnement | Usage |
| --- | --- | --- |
| `http://localhost:9090/targets` | Navigateur du PC hôte de la plateforme | Vérifier les cibles Prometheus |
| `http://localhost:8080/docs` | Navigateur du même PC hôte | Appeler les routes via Swagger/Nginx |
| `http://backend:8000/metrics` | Réseau Docker de la plateforme principale | Collecte des métriques backend |
| `http://ollama:11434` | Réseau Docker du RAG | Appels aux modèles |

`localhost` désigne la machine ou le conteneur qui effectue l'appel. Depuis un autre
PC, l'adresse et les ports autorisés de l'hôte doivent être déterminés avec l'équipe
infrastructure. Une expression PromQL se saisit dans Prometheus, pas sur `/metrics`.
UP valide la collecte ; il ne valide pas un paiement. Un compteur stable sans nouvel
appel est normal. Les observations historiques ne représentent pas un état en direct.

## Validation et limites

La vérification des références contrôle leur présence et leur appartenance aux
passages fournis ; elle ne prouve pas que chaque affirmation est soutenue par ces
passages. Les consignes sur les secrets et les injections de prompt ne garantissent
pas l'absence de fuite ou d'hallucination : le corpus doit être sélectionné et les
réponses évaluées. Le RAG n'a aucun outil d'exécution d'actions système.

Les résultats et limites des essais manuels sont consignés dans
[Choix techniques et observations](CHOIX_TECHNIQUES.md). Il n'y a actuellement ni interface web, ni API HTTP,
ni mémoire de conversation. Chaque question démarre un conteneur temporaire.

Exécuter les tests sans installer de dépendances de test dans l'image définitive :

```bash
docker compose -f compose.rag.yml run --rm -v ./tests:/workspace/tests:ro rag sh -c "pip install pytest && python -m pytest -q"
```

Ces tests utilisent des doubles de modèles ; ils ne mesurent pas la qualité des
vrais embeddings, les réponses du LLM ni les performances matérielles.