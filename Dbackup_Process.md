# Procédure de configuration DBackup

Cette procédure doit être suivie **intégralement, dans l'ordre**, à chaque nouvelle installation de DBackup (nouvelle machine : dev, staging, prod...).

---

## 0. Prérequis (PC Hôte Windows + Docker Desktop)

Le fichier `.env` à la racine du projet doit contenir :

```env
BACKUP_PATH=C:/Users/Admin/phenix-backups     # chemin hôte, avec des / (pas de \)
BACKUP_URL=https://localhost:3000
DBACKUP_ENCRYPTION_KEY=
DBACKUP_AUTH_SECRET=
```

Générer les deux secrets (PowerShell) :

```powershell
# DBACKUP_ENCRYPTION_KEY
python -c "import secrets; print(secrets.token_hex(32))"
# DBACKUP_AUTH_SECRET
python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

Générer des valeurs **différentes** pour chaque machine — ne jamais réutiliser les mêmes secrets d'un poste à l'autre.

---

## 1. Lancer DBackup

Le service `dbackup` est dans le profil Compose `backup` : un simple `docker compose up` l'ignore. Depuis la racine du projet :

```powershell
# DBackup seul
docker compose --profile backup up -d dbackup

# ou toute la stack + DBackup
docker compose --profile backup up -d --build
```

Docker crée automatiquement `${BACKUP_PATH}/data` et `${BACKUP_PATH}/backups`. Sous Docker Desktop (WSL2), **pas de `chown`** à faire : les droits sur les dossiers montés depuis Windows sont gérés par Docker Desktop.

**Vérification :**

```powershell
docker compose --profile backup ps
docker compose --profile backup logs -f dbackup
```

**Arrêt :**

```powershell
docker compose --profile backup stop dbackup
```

---

## 2. Se connecter à DBackup

Aller sur `https://localhost:3000` (**https**, pas http) et accepter le certificat auto-signé (« Avancé » → « Continuer »).
Au premier accès, créer le compte admin.

L'interface n'est accessible que depuis le PC Hôte (`127.0.0.1:3000`), elle n'est pas exposée au réseau du groupe.

> Les étapes suivantes (credentials, source, destination, jobs…) seront finalisées une fois la stratégie de sauvegarde définie en équipe.

---

## 3. Créer un Credential BDD

Menu **Security Vault → Credentials** → créer un credential avec les infos de connexion à la base de données (user, mot de passe) — reprendre les valeurs du `.env` du projet.

Host : **`db`**, port **`5432`** (nom du service dans le réseau Docker) — et non `localhost`.

---

## 4. Créer une Source

Menu **Sources** → créer une nouvelle source, en la rattachant au credential créé à l'étape 3.

---

## 5. Créer une Destination

Menu **Destinations → Add New Destination** :
- **Type** : Local Filesystem
- **Base Path** : `/backups`

 Attention : c'est le chemin **vu par le conteneur**, pas le chemin réel sur l'hôte. Ne jamais mettre le chemin hôte (ex: `/home/administrateur/...`) ici — DBackup ne le connaît pas, seul `/backups` (le point de montage défini dans le `docker-compose.yml`) est valide.

- Cliquer sur **Test Connection** pour valider avant de sauvegarder.

---

## 6. Créer une clé d'Encryption

Menu **Security Vault → Encryption → Create Key** :
- Donner un nom explicite au profil (ex: `Backup-Key-Prod` pour un serveur de prod, distinct du profil `Backup-Key` de dev).
- Une clé différente par environnement (dev/prod) est recommandée pour l'isolation : une fuite sur un environnement ne compromet pas l'autre.

**Dès la création : copier/exporter la clé et la stocker immédiatement** sur une clé USB dédiée (ou un gestionnaire de mots de passe), **jamais** sur le même disque que les backups.

**Télécharger également le Recovery Kit** associé à ce profil (bouton dédié dans Security Vault → Encryption). Ce ZIP contient la clé, un script Node.js autonome de déchiffrement, et des scripts d'aide par plateforme (Windows/Linux/macOS). Il permet de déchiffrer et restaurer un backup **même si DBackup ou son serveur ne sont plus accessibles**. À stocker au même endroit que la clé (USB dédiée), pas seulement la clé seule.
 Si cette clé (ou le Recovery Kit) est perdue, les backups chiffrés avec deviennent définitivement illisibles.

---

## 7. Créer les jobs

Créer deux jobs dans le menu **Jobs**, chacun rattaché à la Source (étape 4), la Destination (étape 5) et l'Encryption Profile (étape 6) :

| Job | Planification (cron) | Déclenchement |
|---|---|---|
| `12h30 Production Backup` | `30 12 * * 1-5` | Automatique, lundi-vendredi à 12h30 |
| `Turn Off Production Backup` | — | Manuel via API, déclenché à l'extinction (voir étape 10) |

Cron `30 12 * * 1-5` : minute 30, heure 12, tous les mois, tous les jours du mois, jours de semaine 1 à 5 (lundi à vendredi).

Si la machine est éteinte à l'heure prévue, le job est simplement sauté (pas d'erreur, pas de rattrapage).

---

## 8. Activer la sauvegarde de la configuration DBackup elle-même

Menu **System Settings → Configuration Backup** :
- Activer **Enable Automated Backups**.
- **Destination Storage** : sélectionner la Destination créée à l'étape 5 (ou une destination distincte, idéalement, pour ne pas tout perdre en cas de crash du même disque).
- **Encryption Profile (Vault)** : sélectionner le profil créé à l'étape 6 (ne pas laisser sur "No Encryption", surtout si "Include Credentials & Secrets" est activé).
- **Retention Count** : nombre de fichiers de config à conserver (ex: 10).
- Le **Schedule** est géré dans **System Tasks** (chercher "Automated Configuration Backup").

Cette sauvegarde permet de restaurer toute la configuration DBackup (adaptateurs, jobs, users, settings) en cas de crash du serveur, sans dépendre d'un snapshot de la base de données interne.

---

> ⚠️ **Étapes 9 à 13 : procédure Linux (systemd), non applicable telle quelle au PC Hôte Windows.**
> Elles sont conservées comme référence. L'équivalent Windows du backup à l'extinction reste à définir en équipe.

## 9. Créer une clé API (pour le trigger au shutdown)

Menu **Access Management → API Keys → Create API Key** :
- **Name** : `shutdown-trigger`
- **Expiration Date** : laisser vide (ne jamais expirer, usage système permanent)
- **Permissions** : cocher uniquement :
  - Jobs → View Jobs
  - Jobs → Execute Jobs Manually
  - History → View Execution History (indispensable pour le polling de l'étape 11 — sans elle, la vérification du statut renvoie une erreur 403)
  - Rien d'autre (principe du moindre privilège)

**Copier/exporter la clé immédiatement** et la stocker en lieu sûr (clé USB dédiée ou gestionnaire de mots de passe), au même titre que les clés d'encryption.
 Ne jamais coller une clé API en clair dans un chat, un ticket, ou tout autre canal non maîtrisé — si ça arrive par erreur, révoquer la clé et en régénérer une immédiatement.

---

## 10. Récupérer l'ID du job "Turn Off Production Backup"

```bash
curl -k https://localhost:3000/api/jobs -H "Authorization: Bearer TA_CLE_API"
```

Si `curl` n'est pas disponible sur la machine, utiliser `wget` :
```bash
wget --no-check-certificate --header="Authorization: Bearer TA_CLE_API" -O- https://localhost:3000/api/jobs
```

Repérer dans la réponse JSON l'objet dont `"name": "Turn Off Production Backup"`, et noter son `"id"`.

---

## 11. Créer le script de déclenchement (avec attente de la fin réelle du job)
 **Point critique** : un simple appel `POST /jobs/{id}/run` ne fait que **mettre le job en file d'attente** — il ne garantit pas que le backup soit terminé. Si le conteneur DBackup s'arrête juste après (ce qui arrive lors d'un shutdown, Docker s'arrêtant en même temps que le reste), l'exécution est interrompue avant la fin (`"Execution was interrupted by an unexpected application shutdown"`). Le script doit donc **attendre la fin réelle** du job (polling) avant de laisser l'extinction continuer.

```bash
sudo nano /usr/local/bin/dbackup-shutdown-trigger.py
```

Contenu (remplacer `ID_DU_JOB` et `TA_CLE_API`) :

```python
import urllib.request
import json
import ssl
import time

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

api_key = "TA_CLE_API"
job_id = "ID_DU_JOB"
base_url = "https://localhost:3000/api"
headers = {"Authorization": f"Bearer {api_key}"}

# 1. Déclencher le job
req = urllib.request.Request(f"{base_url}/jobs/{job_id}/run", method="POST", headers=headers)
resp = urllib.request.urlopen(req, context=ctx)
data = json.loads(resp.read())
execution_id = data["executionId"]

# 2. Attendre la fin réelle (max 10 minutes de sécurité)
max_wait = 600
elapsed = 0
while elapsed < max_wait:
    req = urllib.request.Request(f"{base_url}/executions/{execution_id}", headers=headers)
    resp = urllib.request.urlopen(req, context=ctx)
    status_data = json.loads(resp.read())
    status = status_data.get("data", {}).get("status")
    if status in ("Success", "Failed", "Partial", "Cancelled"):
        break
    time.sleep(3)
    elapsed += 3
```
 **Deux pièges rencontrés sur ce endpoint, à surveiller en priorité si le service traîne anormalement longtemps (proche des 600s) :**

1. **Le statut est niché dans `data`, pas à la racine du JSON.** La réponse de `GET /api/executions/{executionId}` a la forme `{"success":true,"data":{"id":"...","status":"Success",...}}`. Un appel `status_data.get("status")` renvoie donc toujours `None`, et la condition ne matche jamais, quelle que soit l'orthographe utilisée — le script tourne alors en boucle jusqu'au timeout de 600s sans jamais détecter la fin du job. Il faut bien utiliser `status_data.get("data", {}).get("status")`.
2. **Les vraies valeurs de statut sont `"Success"` (avec deux "s"), `"Failed"`, `"Partial"`, `"Cancelled"` — pas `"Completed"`.** Une faute de frappe sur ce mot (ex: `"Succes"`) produit le même symptôme que le piège n°1.

Pour vérifier la vraie structure retournée en cas de doute, interroger directement l'API avec `curl` et lire le JSON brut :
```bash
curl -k https://localhost:3000/api/executions/UN_EXECUTION_ID -H "Authorization: Bearer TA_CLE_API"
```

**Sécuriser le script** (il contient la clé API en clair) :
```bash
sudo chmod 700 /usr/local/bin/dbackup-shutdown-trigger.py
sudo chown root:root /usr/local/bin/dbackup-shutdown-trigger.py
```
Vérifier avec `ls -la` que le résultat est bien `-rwx------ root root` — sinon n'importe quel utilisateur du système peut lire la clé API en ouvrant le fichier.

**Tester le script manuellement avant de le brancher sur systemd :**
```bash
python3 /usr/local/bin/dbackup-shutdown-trigger.py
```
Aucune erreur ne doit s'afficher, et l'exécution doit se terminer rapidement (quelques secondes, pas 10 minutes) si le job est rapide.

---

## 12. Créer le service systemd de déclenchement au shutdown

```bash
sudo nano /etc/systemd/system/dbackup-shutdown.service
```

Contenu :

```ini
[Unit]
Description=Trigger DBackup avant extinction
DefaultDependencies=no
After=docker.service
Before=shutdown.target reboot.target halt.target
Conflicts=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
ExecStart=/bin/true
ExecStop=/usr/bin/python3 /usr/local/bin/dbackup-shutdown-trigger.py
RemainAfterExit=true
TimeoutStopSec=630

[Install]
WantedBy=multi-user.target
```

Points clés de cette config :

- **`After=docker.service`** : cette ligne définit uniquement un **ordre de démarrage** — elle dit à systemd "ne démarre ce service qu'une fois Docker démarré". La conséquence indirecte, mais essentielle pour nous, c'est qu'à l'**extinction**, systemd inverse cet ordre : notre service sera arrêté **avant** Docker, pas après. C'est indispensable ici, car sans cette ligne, rien ne garantit lequel des deux (Docker ou notre service) s'arrête en premier — si Docker s'éteint avant nous, le conteneur DBackup n'est plus joignable, et le script échoue avec une erreur `Connection refused`, sans qu'aucune trace ne remonte dans les logs (le service semble juste "rater" son exécution silencieusement).

- **`Before=shutdown.target reboot.target halt.target`** : même logique d'ordre, mais vis-à-vis des cibles génériques d'arrêt du système (extinction, reboot, halt). Ça garantit que notre service a fini de s'exécuter **avant** que le système considère la séquence d'extinction comme terminée. Sans elle, notre service pourrait continuer de tourner alors que le reste du système est déjà en train de couper l'alimentation, le réseau, etc.

- **`Conflicts=shutdown.target reboot.target halt.target`** : c'est ce qui rend l'arrêt du service **obligatoire**, pas juste ordonné. `Before=` seul ne force rien : il ne fait que dire "si ce service s'arrête, que ce soit avant telle cible" — mais un service qui reste actif indéfiniment pourrait très bien ne jamais recevoir l'ordre de s'arrêter du tout. `Conflicts=` déclare une incompatibilité explicite entre notre service et ces cibles : dès qu'une extinction démarre, systemd **doit** arrêter notre service pour l'atteindre, ce qui déclenche réellement `ExecStop`. En résumé : `Conflicts=` force le "quoi" (le service doit s'arrêter), `Before=` cadre le "quand" (dans le bon ordre, avant la fin de la séquence).

- **`ExecStop` appelle le script Python**, pas directement `curl` — pour deux raisons cumulées. D'abord, `curl` n'est pas forcément installé sur toutes les machines (constaté sur le poste de prod). Ensuite et surtout, un simple appel `curl` ne fait que **déclencher** le job (`POST /jobs/{id}/run`) et rend immédiatement la main à systemd, sans jamais vérifier que le backup a réellement fini de s'exécuter. Si Docker s'arrête juste après ce déclenchement, le job est interrompu en plein milieu. Le script Python, lui, reste actif tant que le job n'a pas atteint un état final (voir étape 11) — c'est cette attente active qui retient systemd de continuer l'extinction trop tôt.

- **`TimeoutStopSec=630`** : légèrement supérieur au `max_wait=600` du script Python. Ce n'est qu'un **garde-fou de sécurité** en cas de blocage anormal du script (API qui ne répond jamais, bug dans la boucle de polling) — sans cette limite, un script bloqué pourrait empêcher indéfiniment l'extinction de la machine. En fonctionnement normal, le script se termine dès que le job passe en `Success`/`Failed`/`Partial`/`Cancelled`, généralement en quelques secondes, sans jamais atteindre ce timeout. Si l'extinction traîne systématiquement plusieurs minutes, c'est le signe que le script ne détecte pas correctement la fin du job (voir les pièges de l'étape 11) — pas que ce timeout est mal réglé.

Activer le service :
```bash
sudo systemctl daemon-reload
sudo systemctl enable dbackup-shutdown.service
sudo systemctl start dbackup-shutdown.service
```

- `daemon-reload` : force systemd à relire les fichiers `.service` du disque (sinon le nouveau fichier reste invisible pour systemd).
- `enable` : active le service automatiquement au bon moment (ici, avant extinction, via `Before=shutdown.target`).
- `start` : **indispensable** — systemd n'appelle `ExecStop` que lors d'une transition d'un état "actif" vers "inactif". Si le service est déjà inactif (par exemple après un test manuel avec `systemctl stop`), il n'y a plus rien à arrêter, donc `ExecStop` ne se redéclenche pas au shutdown suivant tant qu'on n'a pas refait un `start`.

---

## 13. Vérifier avant de tester, puis tester UNIQUEMENT via le bouton d'extinction
 **Leçon retenue en pratique : ne jamais valider ce trigger avec une commande CLI (`systemctl stop`, `shutdown -h now`).** Ces commandes simulent l'arrêt mais ne reproduisent pas exactement les conditions d'un vrai clic sur "Éteindre" depuis l'interface graphique — c'est pourtant ce geste, et uniquement lui, que fera l'utilisateur final. Un test qui « marche » en CLI peut donner un faux sentiment de fiabilité alors que le comportement réel (au clic bouton) reste à vérifier. La seule validation qui compte est un vrai clic sur "Éteindre".

**Avant de tester, vérifier les 3 éléments dans l'ordre (permet d'éliminer la plupart des causes d'échec sans avoir à éteindre la machine) :**

**1. Le script — contenu et permissions**
```bash
sudo cat /usr/local/bin/dbackup-shutdown-trigger.py
```
Vérifier que `job_id` et `api_key` sont bien les vraies valeurs de la machine, et que la ligne de statut est bien `status_data.get("data", {}).get("status")` (voir les pièges de l'étape 11).
```bash
ls -la /usr/local/bin/dbackup-shutdown-trigger.py
```
Doit afficher `-rwx------ root root`.

**2. Le fichier `.service` — contenu complet**
```bash
cat /etc/systemd/system/dbackup-shutdown.service
```
Vérifier la présence de `After=docker.service`, `Before=shutdown.target reboot.target halt.target`, `Conflicts=shutdown.target reboot.target halt.target`, et que `ExecStop` pointe bien vers le script Python (pas `curl`).

**3. Recharger et remettre le service dans un état propre**
```bash
sudo systemctl daemon-reload
sudo systemctl reset-failed dbackup-shutdown.service
sudo systemctl start dbackup-shutdown.service
sudo systemctl status dbackup-shutdown.service
```
Le statut doit afficher **`active (exited)`** — pas `failed`, pas `inactive`. `enable` (fait une seule fois à la création, voir étape 12) doit aussi apparaître dans `Loaded:`.

**Une fois ces 3 points validés, faire le vrai test : éteindre la machine via le bouton "Éteindre" de l'interface graphique.** Ne pas utiliser `systemctl stop` ni `shutdown` en ligne de commande pour ce test final.

Une fois la machine relancée, deux vérifications :
1. Dans **History** (DBackup), l'exécution "Turn Off Production Backup" doit apparaître avec le statut **Success** et le badge portant le nom de la clé API (ex: `shutdown-trigger`) dans la colonne Trigger.
2. Vérifier le timing réel avec :
   ```bash
   sudo journalctl -u dbackup-shutdown.service -b -1 --no-pager
   ```
   L'écart entre `Stopping...` et `Deactivated successfully`/`Stopped` doit être de quelques secondes seulement. Si l'écart va jusqu'à plusieurs minutes (proche du `TimeoutStopSec`), le script n'a pas détecté la fin du job — revérifier le point 1 (statut niché dans `data`, orthographe exacte des valeurs).

**Note sur les logs persistants** : si `journalctl -b -1` renvoie "No entries" alors qu'un test vient d'être fait, vérifier que `/var/log/journal` existe :
```bash
sudo ls -la /var/log/journal
```
Si absent, les logs ne persistent qu'en mémoire et sont perdus à chaque reboot :
```bash
sudo mkdir -p /var/log/journal
sudo systemctl restart systemd-journald
```

**Après chaque test réussi via le bouton, le service repasse automatiquement en état où il faut refaire un `start` avant le prochain test** (rappel étape 12 : `ExecStop` ne se redéclenche que lors d'une transition actif → inactif). Avant toute nouvelle extinction de test, reprendre au point 3 ci-dessus (`daemon-reload` + `reset-failed` + `start` + vérifier `active (exited)`).

---

## 14. Restauration (à documenter)

> Section en attente — process de restauration pas encore validé.
>
> À couvrir :
> - Restauration standard via l'UI DBackup (bouton Restore, déchiffrement automatique via l'Encryption Profile toujours présent dans le Vault).
> - Restauration "à froid" via le Recovery Kit (étape 6) : décompresser le ZIP, utiliser le script Node.js pour déchiffrer + décompresser (GZIP/Brotli) le backup, puis importer le dump obtenu avec l'outil CLI natif de la base de données (ex: `psql`, `mysql`, `mongorestore`...).

---

## Points de vigilance récapitulatifs

- **Base Path** = toujours le chemin **conteneur** (`/backups`), jamais le chemin hôte.
- **Lancement** : toujours avec `--profile backup`, sinon le service `dbackup` est ignoré.
- **Permissions** : `chown 1001:1001` uniquement sur un hôte Linux — inutile sous Docker Desktop Windows.
- **Secrets du `.env`** (`DBACKUP_ENCRYPTION_KEY`, `DBACKUP_AUTH_SECRET`) à générer (voir étape 0), différents par machine.
- **Clés (Encryption + API)** : à noter immédiatement à la création (souvent affichées une seule fois), stockées sur support externe dédié, jamais sur le même disque que les backups.
- **Recovery Kit** : à télécharger en plus de la clé d'encryption, indispensable pour une restauration hors DBackup.
- **Une clé d'encryption différente par environnement** (dev / prod) recommandée pour l'isolation.
- **Configuration Backup** (System Settings) à activer pour pouvoir restaurer la config DBackup elle-même en cas de crash.
- **Fuseau horaire** : si le "Next Run" d'un job affiche une heure décalée par rapport au cron configuré, régler le fuseau horaire dans System Settings → General (privilégier ce réglage plutôt que la variable d'environnement `TZ` du `docker-compose.yml`).
- **Trigger au shutdown — un simple `curl`/appel API ne suffit pas** : il ne fait que déclencher le job sans attendre sa fin, ce qui peut laisser le backup interrompu si Docker s'arrête juste après. Toujours utiliser le script Python avec polling (étape 11), qui attend le vrai statut `Success`/`Failed`/`Partial`/`Cancelled` avant de laisser l'extinction continuer.
- **`After=docker.service` obligatoire** dans le fichier `.service` du trigger shutdown, sinon l'ordre d'arrêt entre ce service et Docker n'est pas garanti (échec silencieux, sans trace dans les logs).
- **Le service doit être actif (`start`) avant chaque test** — `ExecStop` ne se déclenche que lors d'une transition actif → inactif ; un service déjà inactif (après un `systemctl stop` de test) ne redéclenchera pas `ExecStop` au shutdown suivant sans un nouveau `start`.
- **Sécuriser le script de trigger** (`chmod 700`, propriétaire `root`) car il contient la clé API en clair — sinon n'importe quel utilisateur du système peut la lire.
- **Ne jamais faire circuler une clé API ou d'encryption en clair** hors de l'environnement sécurisé (chat, ticket, etc.) — révoquer et régénérer immédiatement si ça arrive par erreur.
- **Valider le trigger shutdown uniquement via un vrai clic sur "Éteindre"** (interface graphique) — `systemctl stop` ou `shutdown` en CLI simulent l'arrêt mais ne garantissent pas que le comportement réel (celui que vivra l'utilisateur final) est identique. Avant chaque nouveau test de ce type, remettre le service actif (`daemon-reload` + `reset-failed` + `start`, voir étape 13).