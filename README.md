# Phenix — Plateforme de paiement résiliente

Application de paiement **fictive** pour expérimenter la supervision, la cybersécurité, la détection d'anomalies et la remédiation automatique d'incidents.

## Stack

| Service | Techno | Rôle |
|---|---|---|
| Frontend | React + Vite | Interface |
| Backend | Python, FastAPI | API |
| Base de données | PostgreSQL 14 | Données |
| Proxy d'entrée | Caddy (sur le PC hôte, hors Docker) | Seul point d'entrée du réseau (port 8080), ajoute l'IP réelle du client (`X-Forwarded-For`) |
| WAF | ModSecurity + OWASP CRS (`owasp/modsecurity-crs`) | Inspecte les requêtes (configuration actuelle : DetectionOnly), publié sur `127.0.0.1:8081` seulement |
| Reverse proxy | Nginx | Derrière le WAF, route vers le frontend et l'API, journaux d'accès en JSON |
| Sauvegardes | `pg_dump` (service `pg_dump`) | Dump toutes les 5 min, 12 versions conservées |
| Métriques | Prometheus + cAdvisor | Métriques des services et des conteneurs |
| Logs | Loki + Promtail | Logs des conteneurs |
| Transaction de test | service `selftest` | Paiement de 1 € automatique toutes les 10 s (preuve de reprise) |
| Assistant | service `rag` (Ollama + LangChain) | Répond aux opérateurs à partir des procédures (RAG), via le dashboard |
| Remédiation | `remediation/` + playbooks Ansible | Moteur SQL raccordé au ML ; moteur brute force expérimental ; actions Ansible sur le PC hôte |
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
├── attaque/                  # scripts SQL et brute force de démonstration
├── remediation/              # moteurs sur le PC hôte et suivi des incidents
├── backups/                  # dumps de la base (ignoré par Git)
└── infra/
    ├── caddy/                # proxy d'entrée (Caddyfile)
    ├── nginx/blocklist/      # adresses bloquées par la remédiation
    ├── observability/        # Prometheus, Loki, Promtail, Grafana
    └── secrets/              # scripts de chiffrement / déchiffrement
```

## Réseaux

| Réseau | Contenu | Accès |
|---|---|---|
| `dmz` | WAF | Publié sur `127.0.0.1:8081` (Caddy écoute sur le port 8080 du PC hôte) |
| `app` | frontend, backend, nginx | Interne |
| `data` | backend, base, sauvegardes, pgAdmin | Interne |
| `ops` | supervision | Interfaces publiées sur 127.0.0.1 uniquement |
| `rag` | Ollama et assistant | Interne |
| `assistant` | backend et assistant | Interne |
| `model_download` | initialisation des modèles | Sortie externe pour les téléchargements |

## Lancer le projet

**Prérequis :** Git, Docker Desktop, [SOPS](https://github.com/getsops/sops), [Caddy](https://caddyserver.com), Python avec `requests` sur Windows et Ansible dans WSL avec accès à Docker Desktop. Le modèle SQL doit être fourni dans `backend/ML/experiments/local-sql-v1/model.joblib` (dossier ignoré par Git). Voir [ML](backend/ML/README.md) et [remédiation](remediation/README.md).

**1. Installer SOPS et Caddy** (une seule fois)

```powershell
winget install --id SecretsOPerationS.SOPS -e
winget install --id CaddyServer.Caddy -e
```

Fermer et rouvrir VS Code, puis vérifier :

```powershell
sops --version
caddy version
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

Sous Windows, `start.ps1` construit aussi l’image du détecteur, démarre Compose avec SOPS et Caddy (port 8080), attend `/health`, puis lance le moteur SQL **actif** dans le terminal. Le mot de passe de service est transmis en mémoire et le fichier temporaire déchiffré est supprimé. Le modèle est chargé sans réentraînement. Le moteur brute force reste manuel.

Le terminal reste occupé : Ctrl+C arrête le moteur sans arrêter le site. Pour relancer uniquement la remédiation SQL : `python remediation/moteur_sql.py --apply`. Ne pas démarrer un deuxième moteur en parallèle. Le lancement automatique décrit ici concerne `start.ps1` ; ne pas supposer que `start.sh` inclut le même raccordement.
**Ne jamais lancer `docker compose up` directement** : il utiliserait les valeurs factices de `.env.example` et le backend planterait.

**5. Vérifier**

```powershell
docker compose ps
```

**6. Arrêter**

Arrêter d’abord le moteur avec Ctrl+C dans son terminal, puis les conteneurs :

```powershell
docker compose down
```

Caddy reste un processus Windows distinct ; pour l’arrêter aussi : `Get-Process caddy -ErrorAction SilentlyContinue | Stop-Process`.

Détails (modifier un secret, limites) : [infra/secrets/README.md](infra/secrets/README.md).

Durcissement : [docs/durcissement.md](docs/durcissement.md). Installation complète sur un PC : [docs/installation.md](docs/installation.md). PC qui sert de point d'entrée et lance les actions de remédiation : [docs/pc-hote.md](docs/pc-hote.md).

### En cas d'erreur

| Message | Solution |
|---|---|
| `sops n'est pas reconnu` | Fermer et rouvrir VS Code |
| `Clé introuvable` | Revoir l'étape 2 |
| `parsing time ... \x0d` | `Remove-Item .env.enc; git checkout -- .env.enc`, puis relancer l'étape 4 |
| Backend `Restarting`, `CHANGE_ME` dans `docker compose logs backend` | Démarré sans le script : relancer l'étape 4 |
| `container phenix-nginx-1 is unhealthy` | Attendre 30 s, puis relancer l'étape 4 |
| `caddy n'est pas reconnu` | Fermer et rouvrir VS Code |
| Le port 8080 ne répond pas | Caddy arrêté : `Get-Process caddy`, sinon relancer l'étape 4 |
| Backend `Restarting`, `password authentication failed` | Base créée une première fois sans les secrets : `docker compose down`, `docker volume rm phenix_postgres-data`, puis relancer l'étape 4 (les comptes de démo sont recréés) |
| Grafana refuse le mot de passe (401) | Grafana démarré une première fois sans les secrets : `docker compose exec grafana grafana cli admin reset-admin-password "<GRAFANA_ADMIN_PASSWORD>"` |

## Point d'entrée (Caddy)

Chaîne : client, puis Caddy (8080), puis WAF (`127.0.0.1:8081`), puis nginx, puis l'application.

Docker Desktop sur Windows remplace l'IP du client par `172.20.0.1`. Caddy remet l'IP réelle dans `X-Forwarded-For` et écrase celui qu'un client enverrait. Le WAF n'étant publié que sur `127.0.0.1`, Caddy ne peut pas être contourné. Nginx retient l'IP du client grâce à `real_ip_header X-Forwarded-For` et `real_ip_recursive on`.

Test : depuis un téléphone sur le point d'accès, ouvrir l'application puis lancer `docker compose logs nginx --tail 3` : `src_ip` doit être l'IP du téléphone.

## Accès

| URL | Service | Accessible depuis |
|---|---|---|
| http://localhost:8080 | Application | PC hôte ; sur le réseau, remplacer localhost par l’IP du PC hôte |
| http://localhost:8080/api/ | API | Même règle d’adresse |
| http://localhost:8080/docs | Documentation de l'API | Même règle d’adresse |
| http://localhost:3000 | Grafana (utilisateur `admin`) | Ce PC uniquement |
| http://localhost:9090 | Prometheus | Ce PC uniquement |
| http://localhost:5050 | pgAdmin (profil `dev`) | Ce PC uniquement |

## Application

### Pages

| Page | Accès |
|---|---|
| `/` | Connexion (puis redirection selon le rôle) |
| `/inscription` | Création de compte (toujours un `CLIENT`) |
| `/dashboard` | Supervision, réservée aux `ADMIN` : état de l'API, transaction de test, trafic (requêtes et erreurs par seconde, 15 min), incidents et temps de reprise (rafraîchis toutes les 5 s), assistant RAG en chatbox |

Le token JWT est gardé en mémoire uniquement : un rechargement de la page déconnecte.

### Rôles et comptes de démo

Créés automatiquement au premier démarrage (base vide), tous avec le mot de passe `DEMO_USER_PASSWORD` des secrets.

| Compte | Rôle | Solde | Usage |
|---|---|---|---|
| `alice_client` | `CLIENT` | 1 500 € | Payer |
| `bob_client` | `CLIENT` | 800 € | Payer |
| `marchand_beta` | `MERCHANT` | 0 € | Recevoir les paiements |
| `admin` | `ADMIN` | pas de compte bancaire | Dashboard, gel des comptes |
| `service_remediation` | `SERVICE` | pas de compte bancaire | ML et moteur de remédiation : créer et résoudre des incidents uniquement |
| `selftest_client` | `CLIENT` | 1 000 000 € | Transaction de test automatique (gros solde pour ne pas s'épuiser) |

Seul le rôle `CLIENT` peut être créé depuis l'interface. Un compte bancaire au plus par utilisateur (contrainte `UNIQUE` en base) ; seuls `CLIENT` et `MERCHANT` peuvent payer et consulter un compte.

### Routes de l'API

Documentation interactive : http://localhost:8080/docs. Routes protégées : en-tête `Authorization: Bearer <token>`.

| Route | Accès | Rôle |
|---|---|---|
| `POST /api/auth/register` | Public | Créer un compte `CLIENT` |
| `POST /api/auth/login` | Public | Obtenir un token (30 min) |
| `GET /api/auth/me` | Connecté | Utilisateur courant et son rôle |
| `GET /api/accounts/me` | `CLIENT`, `MERCHANT` | Mon compte et mon solde |
| `PATCH /api/accounts/{id}/status` | `ADMIN` | Geler / dégeler un compte |
| `POST /api/transactions` | `CLIENT`, `MERCHANT` | Payer : `idempotency_key`, `receiver_account_id`, `amount` (le compte émetteur est celui de l'utilisateur) |
| `GET /api/transactions` | `CLIENT`, `MERCHANT` | Mon historique |
| `POST /api/incidents` | `SERVICE` | Signaler un incident |
| `PATCH /api/incidents/{id}/resolve` | `SERVICE` | Déclarer le service rétabli (calcule le temps de reprise) |
| `GET /api/incidents` | `ADMIN`, `SERVICE` | Liste des incidents (`?only_open=true`) |
| `GET /api/metrics/traffic` | `ADMIN` | Trafic des 15 dernières minutes, relayé depuis Prometheus |
| `POST /api/assistant/ask` | `ADMIN` | Question à l'assistant RAG (`{ "question": "..." }`), relayée au service `rag` ; réponse en 30 s à 1 min |
| `GET /api/selftest` | `ADMIN` | Dernier résultat de la transaction de test automatique (relayé du service `selftest`) |
| `GET /api/attackme/search` | Connecté | **Faille volontaire (injection SQL) pour la démonstration.** Peut exposer des données selon la requête et les droits SQL. À désactiver hors démo : retirer `api.include_router(attackme.router)` dans `backend/app/main.py` |

Paiement rejoué avec la même `idempotency_key` (retry après incident) : renvoyé tel quel (200), sans second débit.

### Transaction de test automatique (preuve de reprise)

Le service `selftest` tente un vrai paiement de 1 € (`selftest_client` → marchand) toutes les 10 s, via l'API. C'est une vérification **active** du métier : si ce paiement passe, l'API, la base, l'authentification et la logique de paiement fonctionnent réellement — un conteneur « healthy » ne le prouve pas. Le résultat (`🟢 Réussie` / `🔴 Échouée`) s'affiche sur le dashboard et bascule en direct pendant un incident puis après la remédiation (Axe 1). Le service expose son dernier résultat sur un réseau interne ; seul le backend le lit, et le relaie aux `ADMIN`.

### Assistant RAG dans le dashboard

Chaîne : chatbox du dashboard, `POST /api/assistant/ask` (backend, `ADMIN`), puis service `rag` (`POST /ask`, réseau Docker interne `assistant`), puis Ollama (réseau interne `rag`). Le RAG n'est joignable que par le backend et n'a accès ni à la base, ni aux secrets, ni à Docker : il conseille, il n'agit pas. Une réponse prend 30 s à 1 min sur CPU. Prérequis : modèles téléchargés (`ollama-init`) et index construit (`ingest`). Détails : [backend/ML/README.md](backend/ML/README.md).

## pgAdmin (optionnel)

pgAdmin ne démarre pas par défaut (outil d'admin, jamais exposé). Pour le lancer avec les secrets, puis effacer le `.env` en clair :

```powershell
.\infra\secrets\decrypt.ps1 -Force; $env:ENV_FILE=".env"; docker compose --env-file .env --profile dev up -d --no-deps pgadmin; Remove-Item .env; Remove-Item Env:ENV_FILE
```

Afficher les identifiants (sans créer de fichier) :

```powershell
sops decrypt --input-type dotenv --output-type dotenv .env.enc | Select-String "PGADMIN|POSTGRES"
```

Ouvrir http://localhost:5050 (connexion avec `PGADMIN_EMAIL` / `PGADMIN_PASSWORD`), puis ajouter un serveur : hôte `db`, port `5432`, identifiants `POSTGRES_*`. Arrêter : `docker compose stop pgadmin`.

## Commandes utiles

```bash
docker compose ps                  # état des services
docker compose logs -f backend     # logs d'un service
docker compose down                # arrêter les conteneurs, données conservées ; moteur/Caddy séparés
```

Pour reconstruire après une modification, relancer `start.ps1` (ou `start.sh`).

## Détection et scénarios

| Composant | Fonctionnement | État |
|---|---|---|
| RAG | Corpus local → recherche → Ollama → réponse avec sources | Intégré au dashboard, sans action système |
| SQL | Logs WAF dans Loki → modèle entraîné → incident → Ansible | Détection et incident validés localement ; blocage distant et paiement après action à vérifier sur le réseau |
| Brute force | Fenêtres de login par IP → modèle distinct → même type de remédiation | Entraînement synthétique et tests logiciels réalisés ; essai sur trafic réel à réaliser |
| SIEM | Règles Grafana sur les journaux | Supervision complémentaire, distincte de la décision du modèle SQL |

Le moteur SQL démarre avec `start.ps1`. Le RAG conseille l’opérateur ; les moteurs de remédiation exécutent des actions autorisées. Les scripts d’attaque SQL et brute force sont conservés dans [attaque/](attaque/README.md). Lancement, test local via Swagger et test réseau : [remédiation](remediation/README.md). Données, modèles et RAG : [ML](backend/ML/README.md).

## Actions de remédiation (Ansible)

Actions lancées dans WSL, à la racine du dépôt : `bash infra/ansible/run.sh <action> key=value`. Prérequis WSL : `sudo apt install -y ansible python3`.

| Action | Rôle | Paramètres |
|---|---|---|
| `restart` | Redémarre un service, attend qu'il soit sain, recharge nginx | `service=` |
| `verify` | Vérifie qu'un service et la chaîne d'entrée répondent | `service=` |
| `restore` | Restaure la base depuis un dump (état actuel sauvegardé avant) | `confirm=yes`, `dump=` |
| `isolate` | Retire un service du réseau sans l'arrêter | `service=` |
| `unisolate` | Reconnecte le service | `service=` |
| `block_ip` | Bloque une adresse IP dans nginx (le client reçoit un 403) | `ip=`, `minutes=` (optionnel), `reason=` (optionnel) |
| `unblock_ip` | Lève le blocage | `ip=` |
| `list_blocked` | Affiche les adresses bloquées (vue admin) | aucun |
| `purge_expired` | Retire les blocages expirés | aucun |

Seuls les services `backend`, `frontend`, `nginx` et `db` sont autorisés. Blocage d'IP : une adresse à la fois ; sans `minutes`, le blocage dure jusqu'à `unblock_ip` ; avec `minutes`, il n'est retiré que par `purge_expired`. Ne sont jamais bloquées : `127.0.0.0/8`, `192.168.137.1`, `172.16.0.0/12`, `169.254.0.0/16`. Ne pas commiter `infra/nginx/blocklist/blocklist.conf` modifié. Détails : [infra/ansible/README.md](infra/ansible/README.md).

## Alertes Grafana

Quatre règles surveillent les logs du WAF (fichier `infra/observability/grafana/provisioning/alerting/rules.yml`, chargé au démarrage de Grafana) : rafale de 403 depuis une même IP, scan de chemins (404), erreurs 5xx et tentative d'injection SQL. Elles se consultent dans Grafana, Alerting, Alert rules, dossier Phenix. Détail : [docs/regles-siem.md](docs/regles-siem.md).

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

- **Métriques** : Prometheus lit les conteneurs (cAdvisor) et le backend (`/metrics`).
- **Logs** : Promtail envoie les logs des conteneurs à Loki. Les journaux nginx sont en JSON : dans Grafana, Explore, source Loki, requête `{service="nginx"} | json`.
- Les données sont conservées 7 jours.
