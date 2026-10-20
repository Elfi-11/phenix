# Phenix — Plateforme de paiement résiliente

Application de paiement **fictive** pour expérimenter la supervision, la cybersécurité, la détection d'anomalies et la remédiation automatique d'incidents.

## Stack

| Service | Techno | Rôle |
|---|---|---|
| Frontend | React + Vite | Interface |
| Backend | Python, FastAPI | API |
| Base de données | PostgreSQL 14 | Données |
| Reverse proxy | Nginx | Seul point d'entrée exposé (port 8080), journaux d'accès en JSON |
| Sauvegardes | `pg_dump` (service `pg_dump`) | Dump toutes les 5 min, 12 versions conservées |
| Métriques | Prometheus + cAdvisor | Métriques des services et des conteneurs |
| Logs | Loki + Promtail | Logs des conteneurs |
| Tableaux de bord | Grafana | Visualisation (métriques et logs) |
| Accès au socket Docker | docker-socket-proxy | Lecture seule, utilisé par Promtail |
| Admin BDD | pgAdmin (optionnel, profil `dev`) | Confort de développement |
| Secrets | SOPS + age | `.env.enc` chiffré dans le dépôt |

## Structure

```text
phenix/
├── docker-compose.yml
├── nginx.conf
├── .env.enc                  # secrets chiffrés (SOPS)
├── .env.example              # noms des variables, valeurs factices
├── .sops.yaml
├── backend/                  # API FastAPI (code dans app/)
├── frontend/                 # application React (code dans src/)
├── backups/                  # dumps de la base (ignoré par Git)
└── infra/
    ├── nginx/blocklist/      # adresses bloquées par la remédiation
    ├── observability/        # Prometheus, Loki, Promtail, Grafana
    └── secrets/              # scripts de chiffrement / déchiffrement
```

## Réseaux

| Réseau | Contenu | Accès |
|---|---|---|
| `dmz` | nginx | Publié sur le port 8080 |
| `app` | frontend, backend, nginx | Interne |
| `data` | backend, base, sauvegardes, pgAdmin | Interne |
| `ops` | supervision | Ports publiés sur 127.0.0.1 uniquement |

## Lancer le projet

**Prérequis :** Git, Docker Desktop, [SOPS](https://github.com/getsops/sops).

**1. Installer SOPS** (une seule fois)

```powershell
winget install --id SecretsOPerationS.SOPS -e
```

Fermer et rouvrir VS Code, puis vérifier :

```powershell
sops --version
```

**2. Installer la clé** (une seule fois, à demander à Yannick en privé, jamais dans Git)

```powershell
New-Item -ItemType Directory "$HOME\.sops"
```

Enregistrer la clé dans `%USERPROFILE%\.sops\keys.txt` (Linux/WSL : `~/.sops/keys.txt`).

**3. Récupérer le code**

```bash
git clone https://github.com/Elfi-11/phenix.git   # première fois
git pull                                          # ensuite
```

**4. Démarrer**

```powershell
# Windows
.\infra\secrets\start.ps1
```

```bash
# Linux / WSL
infra/secrets/start.sh
```

Le script remplace `docker compose up -d --build` : il déchiffre `.env.enc`, lance le build et les conteneurs avec les vrais secrets, puis supprime le fichier temporaire.
**Ne jamais lancer `docker compose up` directement** : il utiliserait les valeurs factices de `.env.example` et le backend planterait.

**5. Vérifier**

```powershell
docker compose ps
```

**6. Arrêter**

```powershell
docker compose down
```

Détails (modifier un secret, limites) : [infra/secrets/README.md](infra/secrets/README.md).

### En cas d'erreur

| Message | Solution |
|---|---|
| `sops n'est pas reconnu` | Fermer et rouvrir VS Code |
| `Clé introuvable` | Revoir l'étape 2 |
| `parsing time ... \x0d` | `Remove-Item .env.enc; git checkout -- .env.enc`, puis relancer l'étape 4 |
| Backend `Restarting`, `CHANGE_ME` dans `docker compose logs backend` | Démarré sans le script : relancer l'étape 4 |
| `container phenix-nginx-1 is unhealthy` | Attendre 30 s, puis relancer l'étape 4 |

## Accès

| URL | Service | Accessible depuis |
|---|---|---|
| http://localhost:8080 | Application | Réseau du groupe |
| http://localhost:8080/api/ | API | Réseau du groupe |
| http://localhost:8080/docs | Documentation de l'API | Réseau du groupe |
| http://localhost:3000 | Grafana (utilisateur `admin`) | Ce PC uniquement |
| http://localhost:9090 | Prometheus | Ce PC uniquement |
| http://localhost:5050 | pgAdmin (profil `dev`) | Ce PC uniquement |

pgAdmin ne démarre pas par défaut :

```bash
docker compose --profile dev up -d pgadmin
```

## Commandes utiles

```bash
docker compose ps                  # état des services
docker compose logs -f backend     # logs d'un service
docker compose down                # tout arrêter (les données sont conservées)
```

Pour reconstruire après une modification, relancer `start.ps1` (ou `start.sh`).

## Sauvegardes et restauration

Le service `pg_dump` sauvegarde la base toutes les 5 minutes dans `backups/` :
`dump_AAAAMMJJ_HHMMSS.sql` (les 12 derniers, soit 1 h d'historique) et `latest.sql` (le plus récent).

Restaurer un dump (par exemple `latest.sql`) :

```bash
docker compose cp backups/latest.sql db:/tmp/restore.sql
docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -f /tmp/restore.sql
```

Les dumps ne sont pas chiffrés : ils restent sur le PC hôte et sont ignorés par Git.

## Supervision

- **Métriques** : Prometheus lit les conteneurs (cAdvisor) et le backend (`/metrics`, à venir).
- **Logs** : Promtail envoie les logs des conteneurs à Loki. Les journaux nginx sont en JSON : dans Grafana, Explore, source Loki, requête `{service="nginx"} | json`.
- Les données sont conservées 7 jours.
