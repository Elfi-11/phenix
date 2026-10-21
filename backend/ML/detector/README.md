# Détecteur Phenix — expérience V2 sur données enrichies

Cette V2 enrichit les **données synthétiques**, sans modifier les paramètres de la forêt ni le quantile de calibration. Elle ne remplace pas automatiquement le modèle V1 : la comparaison montre un compromis défavorable sur les anomalies discrètes (voir V2.md). Aucun appel Ansible, accès aux secrets ou accès au Docker du PC n’est effectué.

## Installer

Copier le dossier `backend` de cette livraison dans le dépôt : remplacer les fichiers correspondants de `detector/` et ajouter le nouveau jeu `data/synthetic-v2/` ainsi que le notebook V2. Conserver les données V1 et les expériences `local-v1` et `synthetic-v1` existantes.

Le `Dockerfile.detector` reste séparé de l’image RAG. Son fichier `Dockerfile.detector.dockerignore` est inclus. Les modèles/résultats de référence V2 sont fournis dans `experiments/reference-v2`, dossier déjà ignoré par votre `.gitignore`. Le code et la documentation n’en dépendent pas pour les tests.

## Générateur et protocole

Le script `detector/generate.py` est un **nouveau générateur**, pas celui utilisé par l’équipe pour la V1, qui n’a pas été fourni. Les distributions sont des hypothèses explicites, pas des mesures réelles de Phenix. La graine 20261021 permet la reproduction.

28 jours fictifs, 40 320 observations à la minute :

| Partie | Dates fictives, novembre 2026 | Usage |
| --- | --- | --- |
| Train | 1–10 | Dix jours normaux, bruit, cycles jour/semaine et pics légitimes |
| Calibration | 11–17 | Seuil sur les seules observations annotées normales ; trois incidents exclus du calcul du seuil |
| Validation | 18–22 | Quatre incidents nouveaux pour l’expérience |
| Test | 23–28 | Cinq incidents ; résultat de comparaison désormais connu |

Les quatre parties ont des flux aléatoires distincts. Aucun épisode n’est partagé entre deux parties. Les mêmes familles de génération existent dans plusieurs parties : cela ne prouve pas une généralisation à des attaques inconnues.

L’activité normale comprend deux hausses légitimes par jour, de durées et amplitudes variables, ainsi que du bruit et une variation entre journées. Elle n’est plus plafonnée à 48 requêtes/s et 52 % CPU. Les douze incidents simulent des symptômes : surcharge, échecs d’authentification, dérive progressive de latence, hausse d’erreurs. Certains affectent une seule variable ou commencent par des valeurs compatibles avec la normale. Leurs noms ne constituent ni un diagnostic d’attaque ni une action de remédiation attendue.

Le manifeste `data/synthetic-v2/manifest.json` précise graine, dates d’épisodes, définitions et empreinte du CSV. Les annotations viennent des fenêtres d’incident injectées, jamais du résultat d’Isolation Forest. Il n’y a pas de recherche des données donnant le meilleur résultat ni de changement de graine après évaluation.

## Contrat de données

Cinq entrées numériques : débit moyen/minute exprimé en requêtes/s, latence moyenne simulée en ms (pas p95), proportion simulée de 5xx en %, CPU simulé normalisé à 100 % et nombre d’échecs auth/minute. Les valeurs réelles devront reprendre ces définitions et préciser le périmètre CPU.

`timestamp` sert uniquement au découpage ; `is_anomaly` vérifie la normalité du train, sélectionne les observations normales de calibration et évalue. Aucun des deux n’entre dans le modèle. `balance_integrity_status` reste constant à 1, pour compatibilité, et exclu. Les dates sont fictives et sans fuseau ; pas de prétention à UTC.

Le chargeur refuse mesures absentes/non finies, valeurs hors domaine et trous temporels. Aucun remplissage silencieux par zéro. Pas de transformations apprises sur la validation ou le test.

## Refaire l’entraînement depuis PowerShell à la racine

Construire l’image, sans toucher au Compose principal :

```powershell
docker build -f backend/ML/Dockerfile.detector -t phenix-detector backend/ML
```

Le CSV enrichi est déjà fourni. Lancer une nouvelle expérience, sans écraser la référence :

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path)/backend/ML/data,target=/workspace/data,readonly" --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector train --csv data/synthetic-v2/telemetry.csv --out experiments/local-v2 --train-days 10 --calibration-days 7 --validation-days 5
```

Toutes les commandes longues sont à coller sur une seule ligne. Choisir un autre dossier si `local-v2` existe déjà. Le programme refuse les sorties non vides. Les durées sont explicites ; sans les options, les valeurs par défaut 4/4/3 restent compatibles avec la V1.

Pour régénérer un autre exemplaire du jeu avec la même graine, dans un nouveau dossier (inutile avant le premier entraînement) :

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path)/backend/ML/data,target=/workspace/data" phenix-detector python -m detector.generate --out data/synthetic-v2-regenerated --seed 20261021
```

Pour comparer les deux modèles figés sur les mêmes périodes V2, après entraînement local, en supposant la V1 dans `local-v1` :

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path)/backend/ML/data,target=/workspace/data,readonly" --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector.compare --csv data/synthetic-v2/telemetry.csv --v1-model experiments/local-v1/model.joblib --v2-dir experiments/local-v2 --out experiments/local-v2/comparison.json
```

Lire les résultats avec `notebooks/analyse_detection_v2.ipynb` ; il pointe par défaut sur `local-v2`. Les sorties préaffichées viennent de l’expérience de référence exécutée ici : relancer les cellules pour lire l’essai de votre poste. L’ancien notebook V1 reste inchangé.

## Tests autonomes

```powershell
docker run --rm phenix-detector python -m unittest detector.test_detector -v
```

Huit tests couvrent la reproductibilité, les annotations, le découpage et son indépendance des observations futures, les entrées invalides, l’inférence sans étiquettes et le refus d’écrasement. Ils construisent leurs propres petites données/modèles et n’exigent plus de modèle versionné dans Git.

## Sorties et limites

`model.joblib`, `metrics.json` et les CSV par période sont produits comme en V1. Les paramètres du découpage sont ajoutés aux métadonnées. `score` reste disponible pour des CSV non annotés ; il émet des scores et alertes JSONL sans action recommandée ni service cible. Ne charger que des joblib de confiance, avec la même version de scikit-learn.

La forêt est toujours de 200 arbres, sous-échantillons de 256, graine 42 ; seuil au quantile 99,5 % de la calibration normale, décision `score > seuil`. Le score n’est pas une probabilité d’attaque. Tous les changements de performance ne peuvent pas être attribués au seul volume de données : la distribution et le protocole ont également changé.

La validation et le test V2 sont désormais connus. Une évolution des paramètres après ces observations devra être présentée comme exploratoire, puis évaluée sur de nouvelles données ou collectes. Cette V2 n’est pas prête à déclencher des remédiations : les incidents manqués sont nombreux.

Validation locale de cette livraison : génération, entraînement, comparaison, notebook et huit tests exécutés en Python. Docker et les montages Windows restent à vérifier sur le poste. Les réseaux et services RAG n’ont pas été modifiés.
