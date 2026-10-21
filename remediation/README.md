# Moteur de remédiation (squelette)

Projet RESILIENCE-ALPHA. Ce composant ferme la boucle **détection → action → reprise**
sans intervention humaine. Il tourne sur le **PC hôte**.

> ⚠️ **Squelette de départ.** Les étapes 1 à 5 (dialogue avec l'API et Ansible) sont
> écrites. Il reste à brancher la **vraie détection** : la fonction `detecter_alertes()`
> (Léa / Richard). Pour l'instant elle est simulée.

## Ce qu'il fait, pour chaque alerte

1. Récupère un token (compte `service_remediation`, rôle SERVICE)
2. `POST /api/incidents` — enregistre l'incident
3. `bash infra/ansible/run.sh block_ip ip=...` — exécute l'action corrective
4. `bash infra/ansible/run.sh verify service=backend` — vérifie la reprise
5. `PATCH /api/incidents/{id}/resolve` — clôture et calcule le temps de reprise

Le dashboard admin affiche l'incident, puis sa résolution avec le temps de reprise.

## À adapter avant de lancer

Dans `moteur.py`, en haut :

| Variable | À mettre |
|---|---|
| `SERVICE_PASSWORD` | Le mot de passe de démo (`DEMO_USER_PASSWORD` des secrets) |
| `PROJECT_DIR` | Le chemin du dépôt sur le PC hôte (pour WSL) |

Puis, la vraie détection : remplacer `detecter_alertes()` (voir le bloc commenté « À FAIRE »).
- **Piste ML** : scorer les dernières métriques Prometheus, et renvoyer une alerte si le score dépasse le seuil.
- **Piste SIEM** : interroger Loki/Grafana, et renvoyer une alerte quand une règle est « firing ».

Une alerte a ce format :
```python
{"event_type": "ML_ANOMALY_DETECTED", "severity": "CRITICAL", "source": "ML",
 "target_service": "backend", "description": "...", "ip": "192.168.137.50"}
```

## Prérequis (PC hôte)

1. Plateforme démarrée (`.\infra\secrets\start.ps1`)
2. Ansible utilisable dans WSL (voir [../docs/pc-hote.md](../docs/pc-hote.md))
3. `pip install requests`

## Lancer

```powershell
python remediation/moteur.py
```

En l'état (détection simulée), il crée **un** incident de test, lance `block_ip` sur une
IP fictive, vérifie, puis résout. On doit voir l'incident apparaître puis se résoudre sur
le dashboard admin : c'est la preuve que la boucle fonctionne de bout en bout.

## Sécurité (à mettre dans le dossier)

- Le moteur utilise le compte **SERVICE** : il ne peut que créer/résoudre des incidents via l'API, rien d'autre.
- Il n'exécute que les actions de la **liste blanche** Ansible (`run.sh`), jamais de commande libre.
- Les IP protégées (PC hôte, réseau Docker…) ne sont jamais bloquées (géré côté Ansible).
