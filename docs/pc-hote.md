# Procédure : PC hôte et actions de remédiation

Projet RESILIENCE-ALPHA. Procédure du PC hôte : point d'entrée du groupe et moteur de remédiation.

## 1. Objectif

Le PC hôte fait tourner la plateforme (Docker Desktop) et le moteur de remédiation. Le moteur déclenche les actions de remédiation en lançant les playbooks Ansible, qui tournent dans WSL2 et pilotent Docker Desktop.

Chaîne : moteur de remédiation, puis `run.sh`, puis Ansible (WSL2), puis Docker Desktop, puis les conteneurs.

Entrée du trafic : appareil du groupe, puis Caddy (port 8080, installé avec `winget install CaddyServer.Caddy`, lancé par `start.ps1`), puis WAF (`127.0.0.1:8081`), puis nginx. Installation complète : [installation.md](installation.md), chapitre 10.

## 2. Réglages de Docker Desktop (Windows)

| Réglage | Où | Valeur | Pourquoi |
|---|---|---|---|
| Intégration WSL | Settings, Resources, WSL integration | Activer « Enable integration with my default WSL distro » et activer la distribution utilisée, puis Apply & restart | Sans ce réglage, la commande `docker` est introuvable dans WSL et les playbooks échouent |
| Moteur WSL 2 | Settings, General | « Use the WSL 2 based engine » activé | Prérequis de l'intégration WSL |
| Démarrage automatique | Settings, General | « Start Docker Desktop when you sign in » activé | Après un redémarrage du PC, Docker et les conteneurs reviennent seuls |
| Accès réseau à Docker | Settings, General | **Ne pas activer** « Expose daemon on tcp://localhost:2375 without TLS » | Cet accès sans protection donnerait le contrôle de Docker à n'importe quel programme : contraire au durcissement |

Après un redémarrage de Docker Desktop, les conteneurs sont arrêtés : relancer la plateforme avec `start.ps1` (étape 3).

## 3. Préparer le PC hôte (une seule fois)

1. Docker Desktop installé et démarré, réglages du chapitre 2 appliqués.
2. Installer Ansible dans WSL (ouvrir WSL avec la commande `wsl`) :

```bash
sudo apt update && sudo apt install -y ansible python3
```

3. Récupérer le projet à jour et déposer la clé de l'équipe (reçue de Yannick, par un canal privé) dans `%USERPROFILE%\.sops\keys.txt` :

```powershell
git pull
```

4. Démarrer la plateforme (déchiffre les secrets, puis lance Docker Compose) :

```powershell
.\infra\secrets\start.ps1
docker compose ps
```

Tous les services doivent être `healthy`.

## 4. Vérifier que les actions fonctionnent

Dans WSL, depuis la racine du projet :

```bash
cd "/mnt/c/Users/<utilisateur>/<chemin>/phenix"
docker ps
bash infra/ansible/run.sh verify service=backend
```

`docker ps` doit lister les conteneurs. Le second test doit finir par `OK : backend est prêt et http://localhost:8080/health répond 200`.

## 5. Appeler les actions depuis le moteur

| Action | Rôle | Paramètres |
|---|---|---|
| `restart` | Redémarre un service, attend qu'il soit prêt, recharge nginx | `service=` |
| `verify` | Vérifie que le service est prêt et que la chaîne répond | `service=`, `check_url=` (optionnel) |
| `restore` | Restaure la base depuis un dump (état actuel sauvegardé avant) | `confirm=yes`, `dump=` (optionnel) |
| `isolate` | Retire un service du réseau, il reste démarré pour l'analyse | `service=` |
| `unisolate` | Reconnecte un service isolé | `service=` |
| `block_ip` | Bloque une adresse IP dans nginx (le client reçoit un 403) | `ip=`, `minutes=` (optionnel), `reason=` (optionnel) |
| `unblock_ip` | Lève le blocage d'une adresse | `ip=` |
| `list_blocked` | Affiche les adresses bloquées (vue admin) | aucun |
| `purge_expired` | Retire les blocages arrivés à expiration | aucun |

Services autorisés : `backend`, `frontend`, `nginx`, `db` (isolables : `backend`, `frontend`). Toute autre action ou tout autre service est refusé. Résultat : code de sortie `0` si l'action a réussi, autre valeur sinon (`2` pour une action inconnue).

Blocage d'IP : une seule adresse IPv4 à la fois (pas de plage). Sans `minutes`, le blocage dure jusqu'à `unblock_ip` (décision d'un admin). Avec `minutes`, une date de fin est écrite mais l'adresse n'est retirée que par `purge_expired`, que le moteur doit appeler régulièrement. Le motif ne contient que lettres, chiffres et `_ . : -` (pas d'espace). Ne sont jamais bloquées : `127.0.0.0/8`, `192.168.137.1` (ce PC), `172.16.0.0/12` (réseau Docker), `169.254.0.0/16`. Le fichier `infra/nginx/blocklist/blocklist.conf` est modifié par ces actions : ne pas le commiter avec des blocages (`git checkout -- infra/nginx/blocklist/blocklist.conf`).

Le moteur lance la commande avec une liste d'arguments (jamais une chaîne de shell, pour éviter les injections). Exemple en Python :

```python
import subprocess, platform

PROJECT_DIR = r"C:\Users\<utilisateur>\<chemin>\phenix"  # à adapter

def run_action(action, **params):
    args = [f"{k}={v}" for k, v in params.items()]
    cmd = ["bash", "infra/ansible/run.sh", action, *args]
    if platform.system() == "Windows":
        cmd = ["wsl", "--cd", PROJECT_DIR, *cmd]   # moteur lancé depuis Windows
        cwd = None
    else:
        cwd = "/mnt/c/Users/<utilisateur>/<chemin>/phenix"  # moteur dans WSL (à adapter)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
    return r.returncode == 0, r.stdout[-2000:]

ok, sortie = run_action("restart", service="backend")
```

## 6. Avant la démonstration

- Docker Desktop est lancé et la plateforme est `healthy`.
- `docker ps` fonctionne dans WSL.
- Chaque action a été testée une fois.
- Le point d'accès `RESILIENCE-G5` est allumé et le port 8080 est ouvert dans le pare-feu Windows.
- Caddy tourne (`Get-Process caddy`) et `http://localhost:8080/health` répond 200.
- La liste de blocage est vide : `bash infra/ansible/run.sh list_blocked` (sinon `unblock_ip`).

## 7. Problèmes déjà rencontrés

| Symptôme | Cause | Solution |
|---|---|---|
| `The command 'docker' could not be found in this WSL 2 distro` | Intégration WSL de Docker Desktop désactivée | Activer l'intégration (chapitre 2) |
| Conteneurs arrêtés après un redémarrage de Docker Desktop | Le moteur a redémarré | Relancer `.\infra\secrets\start.ps1` |
| `host not found in upstream "backend"` au rechargement de nginx | Le backend est en panne, son nom n'existe plus sur le réseau Docker | Réparer le backend, puis relancer l'action |
| Backend qui redémarre en boucle, `password authentication failed` | Mot de passe de `DATABASE_URL` différent de `POSTGRES_PASSWORD` | Lancer `.\infra\secrets\rotate.ps1` |
| Port 8080 muet | Caddy arrêté | `Get-Process caddy`, sinon relancer `start.ps1` |
| Erreur 502 après un redémarrage du backend | nginx garde l'ancienne adresse du backend | Corrigé dans `nginx.conf` (résolveur DNS) ; si une 502 persiste, `docker compose exec nginx nginx -s reload` |
