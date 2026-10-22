# Moteurs de remédiation — Phenix

Les moteurs tournent sur le PC hôte. Le scoring ML s’exécute dans un conteneur temporaire qui lit Loki ; les actions Ansible sont exécutées dans WSL. Le RAG conseille les administrateurs et n’exécute aucune de ces actions.

## Composants et état

| Programme | Source d’alerte | Lancement | État |
|---|---|---|---|
| `moteur_ml.py` | Modèles SQL et brute force sur une collecte WAF partagée | Automatique via `start.ps1` | Nouveau raccordement commun à vérifier sur le poste |
| `moteur_sql.py` | Modèle SQL seul | Ancien lancement manuel | Conservé, ne pas lancer avec le moteur commun |
| `moteur_bruteforce.py` | Modèle sur les POST login, agrégés par IP sur 60 s | Ancien lancement manuel | Détection et incident validés localement ; ne pas lancer avec le moteur commun |
| `moteur.py` | Alerte simulée du squelette initial | Manuel, uniquement pour les essais de câblage | Conservé comme référence ; ne pas le confondre avec une détection réelle |
| `start_sql.py` | Lanceur du moteur commun actif | Appelé par `start.ps1` | Verrou entre les lancements qui passent par ce lanceur |

## Prérequis et démarrage

Sur Windows : Python avec `requests`, Docker Desktop avec intégration WSL, Ansible dans WSL, SOPS et Caddy. Les fichiers `model.joblib` doivent être présents dans `backend/ML/experiments/local-sql-v1/` pour le SQL et `local-bruteforce-v1/` pour le brute force. Ces artefacts sont locaux, ignorés par Git. Voir [préparation ML](../backend/ML/README.md).

Depuis la racine :

```powershell
.\infra\secrets\start.ps1
```

Le script démarre la plateforme et Caddy, attend `/health`, puis lance le moteur commun avec `--apply` dans le même terminal. Le mot de passe du compte `service_remediation` est récupéré en mémoire depuis la configuration du backend ; aucun mot de passe n’est ajouté au code. Le fichier SOPS déchiffré temporairement pour Compose est supprimé.

Le terminal reste occupé et affiche les cycles. Ctrl+C arrête le moteur ; les conteneurs et Caddy continuent de tourner. `docker compose down` n’arrête pas un moteur hôte encore ouvert : utiliser aussi Ctrl+C. Le moteur n’est pas un service Windows et ne redémarre pas automatiquement après fermeture du terminal.

### Relance manuelle et observation

Pour relancer le moteur commun seul, sans build de la plateforme :

```powershell
python remediation/moteur_ml.py --apply
```

Le mot de passe de démo est demandé si `DEMO_USER_PASSWORD` n’est pas présent dans l’environnement. Pour observer sans enregistrer d’incident ni lancer Ansible :

```powershell
python remediation/moteur_ml.py
```

Ajouter `--once` pour un cycle unique. Une seule collecte Loki alimente les deux modèles, sans réentraînement. Le terminal distingue `sql_injection` et `bruteforce`. Les alertes sont dédoublonnées par événement ; pour une même IP, un seul incident est en attente et une temporisation commune de cinq minutes limite les nouvelles actions. Si les deux familles signalent la même IP pendant cette période, la seconde reste visible en console sans second incident garanti. La description de l’incident conserve la première alerte prise en charge.

Arrêter les anciens moteurs SQL, brute force et simulé avant le démarrage commun. Le verrou du lanceur ne protège pas contre leurs lancements directs. Les anciens fichiers d’état restent conservés, sans migration automatique ; le moteur commun initialise `state-ml.json`. Les incidents déjà ouverts restent dans l’API et ne sont pas automatiquement rattachés au nouvel état.

## Boucle automatique

1. Lire les journaux WAF dans Loki et appliquer le modèle figé avec son seuil enregistré.
2. Dédupliquer les événements et mettre en attente une alerte par IP.
3. S’authentifier avec `service_remediation` et créer l’incident via `POST /api/incidents`.
4. Vérifier les adresses protégées. Si l’IP est locale ou protégée, conserver l’incident ouvert sans blocage.
5. Appeler `bash infra/ansible/run.sh block_ip ip=... reason=sql_injection` ou `reason=bruteforce`.
6. Si le blocage réussit, appeler `verify service=backend check_url=...`.
7. Clôturer avec `PATCH /api/incidents/{id}/resolve` uniquement si les deux actions réussissent.

Les actions sont transmises sous forme de liste d’arguments, sans `shell=True`. La liste blanche Ansible reste appliquée. Le moteur conserve l’identifiant d’incident entre les tentatives ; après trois essais espacés de 30 s, l’incident reste ouvert et nécessite un diagnostic. Une temporisation de cinq minutes par IP limite les rafales d’incidents. L’API n’ayant pas de clé d’idempotence pour leur création, une réponse perdue peut néanmoins provoquer un doublon.

## Validation du scenario SQL

### Depuis le PC hôte, sans PC attaquant

Dans `http://localhost:8080/docs`, se connecter puis renseigner **Authorize**. La route pédagogique authentifiée `GET /api/attackme/search` doit être activée dans l’environnement de démonstration.

1. Tester `q=SUCCESS` : recherche normale, sans alerte attendue pour cet exemple.
2. Remplacer le champ `q` par la valeur complète suivante :

```sql
SUCCESS' OR '1'='1' -- 
```

3. Observer les prochains cycles. En observation, une ligne affiche l’IP, le score et le seuil, sans création d’incident.
4. En mode actif, vérifier l’incident sur le dashboard avec un compte ADMIN. Avec `::1` ou `127.0.0.1`, le terminal indique que l’adresse est protégée ; l’incident reste ouvert.

C’est le comportement validé localement. Le score n’est pas une certitude sur l’attaque. Une nouvelle alerte peut être reconnue sans nouvel incident pendant la temporisation de l’IP.

### Depuis le PC attaquant sur le réseau

1. Démarrer le moteur en observation sur le PC hôte. Depuis le PC attaquant, lancer le [script SQL](../attaque/README.md#injection-sql) avec l’URL réelle de l’hôte.
2. Confirmer que l’IP détectée correspond au PC attaquant. Si elle correspond à un proxy ou à l’hôte, corriger la chaîne de transmission avant d’activer le blocage.
3. Relancer le moteur avec `--apply`, puis refaire une tentative. Vérifier incident, `block_ip`, `verify`, puis résolution automatique.
4. Depuis le PC attaquant, constater le refus d’une nouvelle requête. Depuis un client légitime, confirmer la réussite de la transaction de test du dashboard.

Un contrôle `/health` réussi ne prouve ni le refus effectif du PC attaquant ni la réussite d’un paiement. Après la démonstration, débloquer l’IP de test : depuis WSL à la racine, `bash infra/ansible/run.sh unblock_ip ip=...`, puis `list_blocked`. Ne pas supposer une expiration automatique du blocage.

## Validation brute force

Le modèle doit avoir été préparé selon le [README ML](../backend/ML/README.md). Lancer le moteur commun en observation avant le [script de connexions échouées](../attaque/README.md#brute-force-sur-le-login). Vérifier les réponses 401, l’IP et les alertes. Puis tester le mode actif et les mêmes preuves de blocage et de paiement. Un test local conserve la protection de localhost ; il ne démontre pas le blocage distant.

Les lignes backend `AUTH_FAILURE` restent utiles à l’analyse, mais le modèle livré lit les statuts WAF. Les règles SIEM ne sont pas utilisées comme décision par ces deux moteurs ML.

## Configuration et état local

| Variable | Usage |
|---|---|
| `PHENIX_PROJECT_DIR` | Racine du dépôt ; découverte depuis le code par défaut |
| `PHENIX_API` | API côté hôte, par défaut `http://localhost:8080` |
| `SERVICE_USER` | Compte API, par défaut `service_remediation` |
| `DEMO_USER_PASSWORD` | Secret du compte de service, sinon saisie interactive |
| `LOKI_DOCKER_NETWORK` | Réseau du conteneur de scoring ; découvert par `start.ps1`, défaut manuel `phenix_ops` |
| `DETECTOR_IMAGE` | Image de scoring, défaut `phenix-detector` |
| `LOKI_URL`, `LOKI_QUERY` | Adresse et sélection des logs, défaut Loki interne et accès WAF |
| `CHECK_URL` | URL de santé vue depuis Ansible ; sinon passerelle WSL découverte sur Windows |
| `PROTECTED_IPS` | IP protégées supplémentaires, séparées par des virgules |

Le parseur extrait l’IP finale des logs WAF : sa fiabilité dépend des proxies, pas du modèle. Les protections du moteur complètent celles d’Ansible.

Ignorer dans Git :

```gitignore
/remediation/state-*.json
/remediation/state-*.tmp
/remediation/*-runtime.lock
```

Les états permettent la reprise et le dédoublonnage. Ne pas les supprimer pendant l’exécution. Le fichier `.lock` peut rester après arrêt : le verrou réel est libéré par le système. Les fenêtres SQL sont relues pour absorber certains retards Loki, sans garantie d’exhaustivité. Le brute force évalue les 60 dernières secondes ; une interruption peut faire manquer une rafale ancienne.

## Débloquer une IP après un test

Le blocage concerne l’adresse IP du poste, pas le compte utilisateur.
Résoudre un incident via l’API ne retire pas le blocage dans Nginx.

Depuis PowerShell, à la racine du projet, remplacer l’IP d’exemple par
celle du poste à débloquer :

```powershell
wsl --cd "$((Get-Location).Path)" bash infra/ansible/run.sh unblock_ip ip=192.168.137.158
```

Vérifier la liste des blocages restants :

```powershell
wsl --cd "$((Get-Location).Path)" bash infra/ansible/run.sh list_blocked
```

Depuis le poste débloqué, vérifier l’accès à
`http://192.168.137.1:8080/health`, en adaptant l’adresse du PC hôte.

L’ancien incident peut ensuite être clôturé via
`PATCH /api/incidents/{id}/resolve`, avec le compte SERVICE :

```json
{
  "action_taken": "Fin du test : IP débloquée manuellement via Ansible et accès vérifié."
}
```

Le moteur conserve une temporisation de cinq minutes par IP après le
traitement précédent. Le déblocage et la résolution de l’incident ne
réinitialisent pas ce délai. Attendre son expiration avant un nouvel
essai complet.

Si une attaque continue pendant le déblocage, le moteur actif peut
rebloquer l’IP après expiration de la temporisation. Arrêter le script
d’attaque avant le nettoyage.

## Diagnostic et limites

| Symptôme | Vérification |
|---|---|
| Détection dans le terminal, aucun incident | Mode observation, temporisation par IP ou erreur API |
| Incident ouvert pour `::1` | Protection locale normale ; aucun blocage exécuté |
| `verify` refuse localhost depuis WSL | Accessibilité de la passerelle et valeur de `CHECK_URL` |
| Modèle absent/incompatible | Chemin de l’artefact, version de scikit-learn et reconstruction de l’image |
| Aucun log ou erreur de collecte | Loki, réseau Docker, labels sélectionnés et format WAF |
| Erreur 401 du compte de service | Mot de passe et compte SERVICE réellement configurés |

La détection intervient après journalisation. Une première injection peut avoir abouti ; bloquer l’IP n’annule pas une lecture de données et ne corrige pas la route vulnérable. La chaîne réalise un confinement. Le délai affiché dans l’incident mesure sa création jusqu’à sa résolution, pas nécessairement depuis le début de l’attaque. La disponibilité métier doit être constatée via la transaction de test.

## Échec d’un détecteur

Une erreur de chargement, de parsing ou de scoring de l’un des modèles invalide le cycle commun ; le curseur n’avance pas et aucune nouvelle décision n’est appliquée pour ce cycle. Les incidents en attente ne sont pas traités pendant un échec de collecte/scoring. Les deux modèles doivent donc être disponibles. Le prochain cycle réessaie et affiche l’erreur. Les détecteurs séparés restent disponibles pour diagnostic après arrêt du moteur commun.
