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

**Prérequis :** Git, Docker Desktop, [age](https://github.com/FiloSottile/age) et [SOPS](https://github.com/getsops/sops).

1. Récupérer le dépôt.

```bash
git clone https://github.com/Elfi-11/phenix.git
cd phenix
```

2. Déposer la clé de l'équipe (à demander à Yannick, jamais dans Git) dans `~/.sops/keys.txt`
   (Windows : `%USERPROFILE%\.sops\keys.txt`).

3. Démarrer. Le script déchiffre `.env.enc` dans un fichier temporaire, lance les conteneurs puis supprime le fichier.

```powershell
# Windows
.\infra\secrets\start.ps1
```

```bash
# Linux / WSL
infra/secrets/start.sh
```

Toujours démarrer avec ce script : un `docker compose up` direct utiliserait les valeurs factices de `.env.example`.

Détails (modifier un secret, limites) : [infra/secrets/README.md](infra/secrets/README.md).

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
