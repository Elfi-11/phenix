# IA — Phenix

Ce dossier contient deux fonctions distinctes : l’assistant documentaire RAG et les détecteurs ML raccordés à la remédiation. Les commandes ci-dessous se lancent depuis la racine du dépôt.

| Partie | Emplacement | Rôle |
|---|---|---|
| Assistant RAG | `rag/`, `corpus/` | Expliquer les procédures avec des sources ; aucune action système |
| Détection SQL | `detector/sql.py`, `detector/live.py` | Analyser les paramètres des requêtes WAF collectées dans Loki |
| Détection brute force | `detector/bruteforce.py` | Analyser les connexions et échecs par IP sur 60 secondes |
| Expériences | `experiments/` | Modèles et résultats locaux, ignorés par Git |
| Analyse | `notebooks/` | Exploration et restitution des résultats |

## Démarrage

```powershell
.\infra\secrets\start.ps1
```

Sous Windows, ce script démarre la plateforme, prépare les services RAG et lance le moteur SQL actif sur le PC hôte. Il construit l’image `phenix-detector` mais ne réentraîne pas les modèles. Prérequis : modèle SQL dans `backend/ML/experiments/local-sql-v1/model.joblib`, Python avec `requests`, Ansible dans WSL et accès à Docker Desktop. Le brute force reste manuel.

Ctrl+C arrête le moteur SQL ; le site et les conteneurs restent démarrés. Relance seule : `python remediation/moteur_sql.py --apply`. Procédures et modes : [remédiation](../../remediation/README.md).

## Assistant RAG

L’assistant recherche dans `corpus/` puis utilise Ollama localement pour produire une réponse courte avec références. Le dashboard l’appelle via `POST /api/assistant/ask` (ADMIN), relayé vers `rag:8000/ask`. Une réponse peut prendre 30 s à 1 min sur CPU. Chaque question est indépendante, sans mémoire conversationnelle.

`ollama-init` télécharge seulement les modèles absents : `embeddinggemma:300m` et `qwen3:4b-instruct`. Il termine normalement en `Exited (0)`. Les modèles persistent dans `ollama_models`. Les services d’inférence utilisent les réseaux internes `rag` et `assistant` ; seul le téléchargeur utilise `model_download` avec sortie externe. Le RAG n’a accès ni à la base, ni aux secrets, ni à Docker et ne lance pas Ansible.

Une première indexation est nécessaire après préparation des modèles. Depuis la racine :

```powershell
docker compose --env-file .env.example run --rm --no-deps rag python -m rag ingest
docker compose --env-file .env.example run --rm --no-deps rag python -m rag ask "Comment vérifier la collecte Prometheus ?"
docker compose --env-file .env.example run --rm --no-deps rag python -m rag retrieve "Comment vérifier la collecte Prometheus ?"
```

Ces commandes utilisent `.env.example` uniquement pour lire la configuration Compose des opérations IA. Ollama doit déjà tourner ; `--no-deps` évite de relancer ses dépendances. Démarrer les services métier avec le script SOPS, pas avec les valeurs factices.

Après modification du corpus, relancer `ingest` sans build. L’index reste dans `rag_index`. Une modification du code ou des dépendances nécessite un build. `docker compose down` conserve les volumes ; `down -v` peut supprimer modèles, index et données métier.

Contrôles utiles :

```powershell
docker compose --env-file .env.example logs --tail=30 ollama-init
docker compose --env-file .env.example exec ollama ollama list
docker network inspect phenix_rag --format '{{.Internal}}'
docker compose --env-file .env.example run --rm --no-deps --volume ./backend/ML/check_rag_network.py:/workspace/check_rag_network.py:ro rag python /workspace/check_rag_network.py
```

Adapter le préfixe `phenix` si le projet Compose porte un autre nom. Le réseau doit être interne ; le contrôle vérifie Ollama et l’échec de connexions externes, sans prouver à lui seul un filtrage exhaustif. Ne pas ajouter de réseau externe aux services d’inférence. Le téléchargement initial, les images et les builds peuvent nécessiter Internet.

Seul le corpus prévu est indexé : Markdown, texte UTF-8 et PDF texte. Ne pas y déposer de secrets. Les connaissances préentraînées du LLM subsistent : les sources, l’abstention et la fidélité au contexte doivent être vérifiées. L’assistant ne consulte pas l’état réel des services. Voir [CORPUS.md](CORPUS.md) et [CHOIX_TECHNIQUES.md](CHOIX_TECHNIQUES.md).

## Modèles de détection

Le modèle SQL utilise une représentation TF-IDF de caractères et une régression logistique sur le texte normalisé des paramètres. Le modèle brute force utilise une régression logistique avec normalisation sur quatre variables : tentatives, échecs 401, proportion d’échecs et fréquence sur la durée active dans une fenêtre de 60 s par IP. Il lit les POST `/api/auth/login` du WAF, sans collecter de mots de passe et sans dépendre des lignes `AUTH_FAILURE`.

Les modèles sont entraînés hors ligne ; leurs seuils sont choisis sur calibration. Les résultats synthétiques ne garantissent pas les performances réelles. Le SQL a été essayé sur de vrais logs avec création d’un incident local ; le brute force attend cet essai. Les attaques lentes, distribuées ou inconnues et les IP partagées restent des limites.

Pour reproduire l’expérience SQL synthétique, choisir des dossiers de sortie neufs. Ces commandes sont séparées du démarrage opérationnel ; elles ne remplacent pas silencieusement le modèle déjà validé :

```powershell
docker build -f backend/ML/Dockerfile.detector -t phenix-detector backend/ML
docker run --rm --network none --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector.sql generate --out experiments/synthetic-sql-v1
docker run --rm --network none --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector.sql train --dataset experiments/synthetic-sql-v1 --out experiments/local-sql-v1
```

Si ces dossiers existent, conserver les résultats et choisir d’autres noms ; le moteur devra alors pointer vers l’artefact retenu. Les prédictions, métriques et poids de caractères facilitent l’analyse, mais les motifs du générateur peuvent produire des résultats trop favorables. Conserver la séparation entraînement/calibration/évaluation et compléter par des essais réels.

Préparer le modèle brute force expérimental, une seule fois dans un nouveau dossier :

```powershell
docker build -f backend/ML/Dockerfile.detector -t phenix-detector backend/ML
docker run --rm --network none --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector.bruteforce train --out experiments/local-bruteforce-v1
```

Le dossier de sortie existant n’est pas écrasé. L’entraînement crée `model.joblib` et `metrics.json`. Les modèles sous `experiments/` ne sont pas transmis par Git : fournir les artefacts retenus dans le livrable ou les reproduire explicitement sur le PC hôte. Ne charger que les artefacts de confiance produits par l’équipe.

Essais et actions automatiques : [remédiation](../../remediation/README.md). Scripts de démonstration : [attaques](../../attaque/README.md). Les notebooks et résultats conservés décrivent le protocole retenu ; la documentation détaillée de rendu reste séparée du dépôt.

## Diagnostic rapide

| Symptôme | Contrôle |
|---|---|
| RAG : index absent | Lancer `ingest` après disponibilité d’Ollama |
| Ollama : modèle absent | Lire les logs `ollama-init` ; vérifier le volume et la fin de l’initialisation |
| RAG : réponse insuffisante | Vérifier les passages avec `retrieve` et le contenu du corpus |
| RAG : réponse lente | Inférence CPU et traitement séquentiel ; patienter avant de multiplier les appels |
| Détecteur : modèle absent | Vérifier le chemin local et la fourniture de l’artefact ignoré par Git |
| Brute force : aucun signal | Vérifier les POST login et statuts 401 dans le WAF, l’IP et la fenêtre temporelle |

Sur un ancien poste dont `rag` n’est pas interne, une migration du réseau reste nécessaire : arrêter et retirer seulement les conteneurs IA concernés, retirer leur ancien réseau devenu inutilisé puis relancer le script SOPS avec le même nom de projet. Conserver les volumes et identifier tout conteneur qui empêche la suppression du réseau avant de poursuivre. Cette opération ponctuelle ne fait pas partie du démarrage courant.