# Essai contextuel — validation exploratoire

Ajouter context.py et test_context.py dans le dossier detector existant. Aucun remplacement du CLI V2, aucune nouvelle dépendance et aucune modification du Compose. Ajouter le notebook dans notebooks. Le dossier experiments fourni contient les résultats locaux et reste ignoré par Git.

## Principe

Une régression Ridge sur le trafic et son carré apprend conjointement la latence, la CPU, les erreurs et les échecs d'authentification normaux. Le score est le plus grand écart absolu standardisé parmi les quatre résidus et le volume de trafic. Les centres et dispersions robustes sont appris sur le train normal uniquement. La dispersion minimale numérique évite une division par zéro ; elle ne définit pas un seuil métier.

Le seuil global utilise le quantile 99,5 % des scores de calibration normale, comme la V2. Les annotations servent à identifier le train/calibration normaux et à évaluer : elles ne sont pas des entrées de la régression. Ce sont des relations apprises, pas des règles d'attaque prédéfinies. La représentation et l'agrégation maximum restent des choix humains explicites.

## Exécution depuis la racine — PowerShell

```powershell
docker build -f backend/ML/Dockerfile.detector -t phenix-detector backend/ML
```

```powershell
docker run --rm --mount "type=bind,source=$((Get-Location).Path)/backend/ML/data,target=/workspace/data,readonly" --mount "type=bind,source=$((Get-Location).Path)/backend/ML/experiments,target=/workspace/experiments" phenix-detector python -m detector.context --csv data/synthetic-v2/telemetry.csv --out experiments/local-v2-context
```

Le dossier de sortie doit être nouveau ou vide. Dans le notebook, remplacer EXPERIMENT par local-v2-context pour examiner ce nouvel entraînement, ou conserver synthetic-v2-context pour examiner les résultats fournis.

```powershell
docker run --rm phenix-detector python -m unittest detector.test_context detector.test_detector -v
```

## Résultat observé, 21 octobre 2026

Même découpage V2 : dix jours de train, sept de calibration, cinq de validation. Un seul candidat contextuel essayé avec les paramètres indiqués ; aucun ajustement du seuil ou du générateur après le résultat. Le test historique est exclu du scoring de cet essai. Il avait déjà été consulté pour V2 : prévoir de nouvelles observations indépendantes pour l'évaluation finale.

| Validation, 7 200 minutes | V2 Isolation Forest | Variante contextuelle |
| --- | ---: | ---: |
| Minutes anormales détectées | 0/123 | 117/123 |
| Minutes anormales manquées | 123 | 6 |
| Minutes de fausses alertes | 20 | 1 |
| Épisodes détectés | 0/4 | 4/4 |

Délai : 0, 0, 6 et 0 minutes sur les quatre épisodes, sans mesure de délai en direct. Précision 99,15 %, rappel 95,12 % sur cette seule validation synthétique.

Ces résultats bénéficient potentiellement des relations régulières du générateur, connu pendant la conception. Ils ne prouvent ni une généralisation aux logs réels, ni une performance sur des attaques différentes. La CPU peut saturer et les relations réelles être plus complexes. Aucun historique temporel n'est encore exploité, aucun diagnostic de cause ni action de remédiation n'est produit.

Ce module est un essai distinct : son artefact joblib utilise un score positif spécifique et ne doit pas être envoyé au CLI score d'Isolation Forest. Le notebook lit uniquement les métriques et CSV. Charger uniquement les modèles joblib locaux de confiance. L'adaptation au contrat d'alerte de l'équipe viendra séparément.
