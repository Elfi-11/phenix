# Installer la plateforme sur son PC

Projet RESILIENCE-ALPHA. Procédure pour installer la plateforme sur un PC. Le PC qui sert de point d'entrée est décrit au chapitre 10 et dans [pc-hote.md](pc-hote.md).

## 1. Ce qu'il faut avoir

| Outil | Pourquoi |
|---|---|
| Git | Récupérer le dépôt |
| Docker Desktop | Lancer les conteneurs |
| age et SOPS | Déchiffrer les secrets |
| Caddy | Proxy devant le WAF : garde l'IP réelle des clients (port 8080) |
| La clé d'équipe | Donnée par Yannick en privé, jamais par le dépôt ni dans un message |

## 2. Installer les outils (une seule fois)

Dans PowerShell :

```text
winget install Git.Git
winget install Docker.DockerDesktop
winget install FiloSottile.age
winget install SecretsOPerationS.SOPS
winget install CaddyServer.Caddy
```

Fermer puis rouvrir le terminal (ou redémarrer VS Code), sinon `age`, `sops` et `caddy` ne sont pas reconnus. Redémarrer le PC si Docker Desktop le demande.

## 3. Régler Docker Desktop

| Réglage | Où | Valeur |
|---|---|---|
| Moteur WSL 2 | Settings, General | « Use the WSL 2 based engine » activé |
| Démarrage automatique | Settings, General | « Start Docker Desktop when you sign in » activé (conseillé) |
| Intégration WSL | Settings, Resources, WSL integration | Seulement si tu utilises WSL : activer ta distribution, puis Apply & restart |
| Accès réseau à Docker | Settings, General | Ne pas activer « Expose daemon on tcp://localhost:2375 without TLS » |

Lancer Docker Desktop et attendre que l'icône indique « running ».

## 4. Récupérer le projet

```text
git clone https://github.com/Elfi-11/phenix.git
cd phenix
git checkout main
git pull
```

Pour travailler sur sa propre branche : `git checkout -b <ta-branche>`.

## 5. Déposer la clé d'équipe

1. Créer le dossier : `mkdir $env:USERPROFILE\.sops`
2. Enregistrer la clé reçue de Yannick dans `%USERPROFILE%\.sops\keys.txt`.
3. Ne jamais la commiter ni la coller dans un chat.

Test : `sops --version` et `age --version` doivent afficher un numéro de version.

## 6. Démarrer la plateforme

Toujours avec le script, jamais avec `docker compose up` direct (il prendrait les valeurs factices de `.env.example`) :

```text
.\infra\secrets\start.ps1
```

Le script déchiffre les secrets dans un fichier temporaire, lance les conteneurs, supprime le fichier, puis démarre Caddy sur le port 8080. La première fois, les images se construisent et le service `ollama-init` télécharge probablement le modèle d'IA local : compter jusqu'à une vingtaine de minutes avec une bonne connexion, et prévoir de la place sur le disque. Le service `rag` ne démarre qu'une fois ce téléchargement terminé. Ne pas interrompre le script.

## 7. Vérifier

```text
docker compose ps
Get-Process caddy
```

Tous les services doivent être `healthy` ou `running`, et `Get-Process caddy` doit lister un processus. Puis ouvrir :

| Adresse | Service |
|---|---|
| http://localhost:8080 | Application |
| http://localhost:8080/health | Test de santé de la chaîne d'entrée |
| http://localhost:3000 | Grafana (utilisateur `admin`) |
| http://localhost:9090 | Prometheus |

Le mot de passe Grafana est dans les secrets. Pour le lire : `.\infra\secrets\decrypt.ps1`, ouvrir `.env`, puis supprimer `.env` (`Remove-Item .env`).

## 8. Au quotidien

| Besoin | Commande |
|---|---|
| Voir l'état | `docker compose ps` |
| Lire les logs d'un service | `docker compose logs -f backend` |
| Tout arrêter (données conservées) | `docker compose down` |
| Reconstruire après une modification | `.\infra\secrets\start.ps1` |
| Récupérer le travail des autres | `git pull`, puis `.\infra\secrets\start.ps1` |

Après un redémarrage de Docker Desktop ou du PC, les conteneurs sont arrêtés : relancer `start.ps1`.

## 9. Modifier un secret

1. `.\infra\secrets\decrypt.ps1` crée un `.env` lisible.
2. Modifier le `.env`.
3. `.\infra\secrets\encrypt.ps1` rechiffre.
4. `Remove-Item .env`
5. `git add .env.enc`, commit et push.

Un nouveau secret doit aussi être ajouté (nom seulement) dans `.env.example`.

## 10. Seulement pour le PC hôte (point d'entrée et remédiation)

Le PC hôte reçoit le trafic du groupe et fait tourner le moteur de remédiation. Les autres PC n'ont pas besoin de ce chapitre.

**Chaîne d'entrée :** appareil du groupe, puis Caddy (port 8080), puis WAF (`127.0.0.1:8081`), puis nginx, puis l'application. Caddy ajoute l'IP réelle du client (`X-Forwarded-For`) : sans lui, Docker Desktop la remplace par `172.20.0.1`.

1. Créer le point d'accès : Paramètres, Réseau et Internet, Point d'accès sans fil mobile. Nom `RESILIENCE-G5`, bande 5 GHz si possible, mot de passe solide. Activer. `ipconfig` doit montrer `192.168.137.1`.
2. Ouvrir le port d'entrée (PowerShell administrateur) :

```text
New-NetFirewallRule -DisplayName "Resilience entree" -Direction Inbound -Protocol TCP -LocalPort 8080 -Action Allow
```

3. Démarrer avec `.\infra\secrets\start.ps1` (il lance aussi Caddy avec `infra\caddy\Caddyfile`).
4. Dans Docker Desktop, activer l'intégration WSL (chapitre 3), puis dans WSL : `sudo apt update && sudo apt install -y ansible python3`
5. Tester depuis la racine du projet, dans WSL :

```text
docker ps
bash infra/ansible/run.sh verify service=backend
```

Le second test doit finir par « OK : backend est prêt ».

6. Tester l'accès depuis un téléphone connecté à `RESILIENCE-G5` : `http://192.168.137.1:8080/health` doit répondre 200. Puis vérifier l'IP vue par la chaîne :

```text
docker compose logs nginx --tail 3
```

`src_ip` doit être l'IP du téléphone (`192.168.137.x`) et non `172.x`. (Dépend de la configuration `real_ip` du WAF.)

**Arrêter ou relancer Caddy :** `Get-Process caddy | Stop-Process`, puis `.\infra\secrets\start.ps1`. Tant que Caddy est arrêté, le port 8080 ne répond plus et l'action `verify` échoue.

## 11. Problèmes fréquents

| Symptôme | Cause | Solution |
|---|---|---|
| `age` ou `sops` non reconnu | Terminal ouvert avant l'installation | Rouvrir le terminal |
| `no identity matched any of the recipients` | Clé absente ou fausse | Vérifier `%USERPROFILE%\.sops\keys.txt` |
| `start.ps1` semble bloqué (plus de 10 minutes) | `ollama-init` télécharge le modèle d'IA | Attendre ; suivre avec `docker compose logs -f ollama-init` |
| Conteneurs arrêtés | Docker Desktop redémarré | Relancer `start.ps1` |
| Backend qui redémarre en boucle (`password authentication failed`) | Mot de passe de la base différent de `DATABASE_URL` | Prévenir Yannick (`rotate.ps1`) |
| Erreur 502 après un redémarrage du backend | nginx garde l'ancienne adresse | `docker compose exec nginx nginx -s reload` |
| Port 8080 ne répond pas depuis `localhost` ou le téléphone | Caddy arrêté | `Get-Process caddy`, sinon relancer `start.ps1` |
| `caddy` non reconnu | Terminal ouvert avant l'installation | Rouvrir le terminal |
| `bind: Only one usage of each socket address` sur 8080 | Ancienne publication du WAF ou autre programme sur 8080 | Vérifier que le WAF est publié en `127.0.0.1:8081`, puis relancer `start.ps1` |
| `src_ip` = `172.20.0.1` | WAF pas encore configuré pour `X-Forwarded-For` | Prévenir Stéphanie |
| `docker` introuvable dans WSL | Intégration WSL désactivée | Chapitre 3 |
| Erreur de fin de ligne dans un script `.sh` | Fichier modifié sous Windows | Vérifier `.gitattributes` (`*.sh text eol=lf`) |
