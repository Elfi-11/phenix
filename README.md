# Phenix — Plateforme de paiement résiliente

Application de paiement **fictive** pour expérimenter la supervision, la cybersécurité, la détection d'anomalies et la remédiation automatique d'incidents.

## Stack

| Service | Techno |
|---|---|
| Frontend | React + Vite |
| Backend | Python, FastAPI |
| Base de données | PostgreSQL |
| Reverse proxy | Nginx |
| Admin BDD | pgAdmin |
| Sauvegardes | DBackup (optionnel) |

## Structure

```text
phenix/
├── docker-compose.yml
├── nginx.conf
├── .env.example
├── backend/     # API FastAPI (code dans app/)
└── frontend/    # application React (code dans src/)
```

## Lancer le projet

**Prérequis :** Git et Docker Desktop.

```bash
git clone https://github.com/Elfi-11/phenix.git
cd phenix
cp .env
docker compose up -d --build
```

## Accès

| URL | Service |
|---|---|
| http://localhost:8080 | Application |
| http://localhost:8080/api/ | API |
| http://localhost:8080/docs | Documentation de l'API |
| http://localhost:8080/pgadmin/ | pgAdmin |

## Commandes utiles

```bash
docker compose ps                  # état des services
docker compose logs -f backend     # logs d'un service
docker compose up -d --build       # reconstruire après une modif
docker compose down                # tout arrêter
```

## Sauvegardes

DBackup ne se lance pas par défaut :

```bash
docker compose --profile backup up -d dbackup
```

Interface : https://localhost:3000 — détails dans [Dbackup_Process.md](Dbackup_Process.md).
