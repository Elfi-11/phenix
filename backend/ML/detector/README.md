# Détecteur d’anomalies — première expérience

Détecteur Isolation Forest sur télémétrie numérique agrégée à la minute. Cette V1 apprend et rejoue des CSV ; elle ne collecte pas encore Prometheus/Loki et ne déclenche pas Ansible. Elle reste indépendante du RAG, de son image et de ses dépendances.

## Installation dans le dépôt

Copier les nouveaux dossiers `detector/`, `data/`, `experiments/` et le fichier `Dockerfile.detector` dans `backend/ML/`. Ne pas remplacer le Dockerfile, le README ou requirements.txt du RAG. Le CSV inclus est le fichier synthétique fourni par l’équipe.

Le modèle de l’expérience fournie a été entraîné avec Python 3.12 et scikit-learn 1.8.0. Pour reproduire l’environnement Python de l’essai, l’image utilise Python 3.12. Les dépendances directes sont fixées dans `detector/requirements.txt` ; leurs dépendances transitives et l’image de base ne sont pas intégralement verrouillées.

## Exécution Docker depuis la racine

Ce détecteur hors ligne ne dépend pas du Compose principal, d’Ollama ni des secrets SOPS. Les commandes suivantes ne démarrent pas la plateforme métier.

```powershell
docker build -f backend/ML/Dockerfile.detector -t phenix-detector backend/ML
```

Entraîner une nouvelle expérience (commande complète sur une seule ligne) :

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path)/backend/ML/data,target=/workspace/data,readonly" --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector train --csv data/alphapay_telemetry_fr_realistic.csv --out experiments/local-v1
```

Dans PowerShell, depuis la racine, ces montages utilisent le dossier courant. Créer le dossier `backend/ML/experiments` s’il manque. Choisir un nouveau nom de dossier pour chaque essai : le programme refuse d’écraser une expérience existante.

Appliquer le modèle à des observations, ici en rejouant le CSV synthétique pour vérifier le fonctionnement (ce rejeu inclut des données déjà vues, ce n’est donc PAS une évaluation indépendante) :

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path)/backend/ML/data,target=/workspace/data,readonly" --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector score --csv data/alphapay_telemetry_fr_realistic.csv --model experiments/local-v1/model.joblib --out experiments/local-v1/replay.csv
```

Alternative Python, depuis `backend/ML`, avec un environnement dédié au détecteur :

```bash
python -m pip install -r detector/requirements.txt
python -m detector train --csv data/alphapay_telemetry_fr_realistic.csv --out experiments/local-v1
python -m detector score --csv data/alphapay_telemetry_fr_realistic.csv --model experiments/local-v1/model.joblib --out experiments/local-v1/replay.csv
```

## Données et préparation

Entrées du modèle, dans un ordre fixe : `req_per_sec`, `latency_ms`, `error_rate_pct`, `cpu_usage_pct`, `auth_failures_per_min`.

`timestamp` sert au tri et au découpage, jamais à l’apprentissage. `is_anomaly` sert à vérifier la normalité du train, à sélectionner les observations normales de calibration et à évaluer les résultats ; il n’est jamais donné à Isolation Forest. On parle donc d’apprentissage non supervisé sur période normale sélectionnée avec les annotations, pas d’un protocole totalement dépourvu d’étiquettes.

`balance_integrity_status` est exclu : sa définition opérationnelle reste inconnue et sa valeur est constante sur le train normal. On ne suppose pas qu’Isolation Forest saura détecter un changement d’une variable jamais variable à l’entraînement.

Les données sont triées par date, sans mélange aléatoire. Les doublons temporels, trous dans la cadence minute, valeurs manquantes, non finies ou hors domaine prévu entraînent un refus explicite. Aucun remplissage automatique par zéro, aucune normalisation apprise sur le test. Les arbres utilisent directement les valeurs numériques ; pas de lissage ni de variables temporelles dans cette V1.

Les dates du CSV n’indiquent pas de fuseau horaire : aucun UTC n’est inventé. Le fuseau et le sens des horodatages (début ou fin de fenêtre) doivent être définis avant le raccordement réel.

## Protocole fixé avant le premier essai

| Partie | Période | Usage |
| --- | --- | --- |
| Train | 6–9 octobre 2026 | Ajuster la forêt sur 5 760 minutes normales |
| Calibration | 10–13 octobre | Fixer le seuil sur les seules minutes annotées normales |
| Validation | 14–16 octobre | Observer les résultats sans ajuster cette V1 |
| Test | 17–19 octobre | Évaluation finale de la V1, un épisode de 40 minutes |

Chaque incident reste entier dans une partie. La fonction de découpage vérifie qu’une frontière ne coupe pas deux minutes anormales consécutives. Ce protocole est spécifique à ce premier CSV de 14 jours ; il faut définir un nouveau protocole pour une autre collecte.

Forêt : 200 arbres, sous-échantillons de 256 observations, graine 42. Score = opposé de `score_samples` : plus haut signifie plus inhabituel. Le seuil est le quantile 99,5 % des scores normaux de calibration, choisi comme première tolérance exploratoire aux fausses alertes. La décision est `score > seuil`, sans seuils métier du type CPU > x. Ce score n’est pas une probabilité d’attaque. Aucun réglage n’a été effectué après lecture du test ; toute évolution évaluée sur ces mêmes jours ne sera plus un test inédit.

## Sorties

- `model.joblib` : forêt et métadonnées, utilisables pour l’inférence. Charger uniquement vos propres artefacts de confiance ; joblib repose sur pickle.
- `metrics.json` : paramètres, versions, empreinte SHA-256 du CSV et résultats par partie.
- `*_predictions.csv` : annotations, scores et prédictions par minute pour chaque partie.
- `replay.csv` et `replay.alerts.jsonl` : scores d’un rejeu et événements proposés, sans exécution.

Les alertes ont le type `ML_ANOMALY_DETECTED`, mais ne sont pas encore insérées dans l’API incidents : le contrat de raccordement reste à réaliser. `target_service` et `recommended_action` valent null, car le CSV ne permet pas d’identifier la cible ou le remède. Un événement est écrit par minute signalée ; aucune déduplication ou temporisation n’est encore appliquée.

## Vérifications et prochaine étape

Depuis `backend/ML` avec les dépendances installées :

```bash
python -m unittest detector.test_detector -v
```

Les six tests vérifient le découpage, le refus d’entrées invalides, l’exclusion des étiquettes, et l’équivalence de l’inférence avec les scores enregistrés. Ils utilisent l’expérience `synthetic-v1` livrée. Ils ne prouvent pas la pertinence sur d’autres données.

Le code Python a été exécuté ici ; la construction Docker et les montages PowerShell restent à vérifier sur le poste Windows.

Ensuite : définir les agrégations réelles, collecter du trafic ordinaire varié et plusieurs répétitions d’incidents, mesurer les fausses alertes et le délai réel, puis seulement définir la politique de remédiation. Les définitions suivantes manquent encore : latence moyenne/p95, codes comptés comme erreurs, CPU d’un conteneur ou du PC et normalisation, mesure du débit et sources des échecs auth.

## Raccordement Ansible à venir

Les fichiers Ansible transmis à nouveau sont identiques aux précédents. Le moteur hôte pourra invoquer `infra/ansible/run.sh` avec une liste d’arguments, après validation stricte des clés et valeurs. La V1 du détecteur ne reçoit ni socket Docker ni secrets et ne construit aucune commande à partir du CSV.

`verify` contrôle actuellement le conteneur et un HTTP 200 sur `/health` : compléter par le scénario de paiement pour prouver la reprise métier. Le wrapper `run.sh` fourni accepte encore toute clé `key=value`, pas uniquement les paramètres attendus ; corriger cette validation avant une utilisation automatique. Le choix d’un redémarrage, d’un isolement ou d’une restauration demande des éléments de diagnostic supplémentaires ; aucune de ces actions ne découle du seul score.

Résultats et limites : voir `experiments/synthetic-v1/RESULTATS.md`.
Référence : https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html