# Phenix — Plateforme de paiement résiliente

Application de paiement **fictive** pour expérimenter la supervision, la cybersécurité, la détection d'anomalies et la remédiation automatique d'incidents.

## Stack

| Service | Techno |
|---|---|
| Frontend | React + Vite |
| Backend | Python, FastAPI |
| Base de données | PostgreSQL |
| Reverse proxy | Nginx |
| Supervision | Prometheus, Loki, Grafana |
| Sauvegardes | pg_dump (automatique) |
| Admin BDD | pgAdmin (dev uniquement) |

## Structure

```text
phenix/
├── docker-compose.yml
├── nginx.conf
├── backend/            # API FastAPI (code dans app/)
├── frontend/           # application React (code dans src/)
├── infra/
│   └── observability/  # config Prometheus, Promtail, Grafana
└── backups/            # dumps de la base (non versionné)
```

## Lancer le projet

**Prérequis :** Git et Docker Desktop.

```bash
git clone https://github.com/Elfi-11/phenix.git
cd phenix
```

Créer le fichier `.env` à la racine (valeurs à demander à l'équipe, ne jamais le committer), puis :

```bash
docker compose up -d --build
```

Avec pgAdmin (développement) :

```bash
docker compose --profile dev up -d --build
```

## Accès

| URL | Service |
|---|---|
| http://localhost:8080 | Application |
| http://localhost:8080/api/ | API |
| http://localhost:8080/docs | Documentation de l'API |
| http://localhost:3000 | Grafana |
| http://localhost:9090 | Prometheus |
| http://localhost:5050 | pgAdmin (profil `dev`) |

## Commandes utiles

```bash
docker compose ps                  # état des services
docker compose logs -f backend     # logs d'un service
docker compose up -d --build       # reconstruire après une modif
docker compose down                # tout arrêter
```

## Sauvegardes

Le service `pg_dump` sauvegarde la base toutes les 5 minutes dans `backups/latest.sql`.
