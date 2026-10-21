# Durcissement de la plateforme

Projet RESILIENCE-ALPHA. État du durcissement après l'audit du 21 octobre 2026 : ce qui est en place, ce qui reste à décider, et les risques acceptés.

## 1. Chaîne d'entrée

Client, puis Caddy (port 8080 du PC hôte), puis WAF (`127.0.0.1:8081`), puis nginx, puis l'application. Caddy remplace `X-Forwarded-For` par l'IP réelle du client : un client ne peut pas la falsifier. Le WAF n'étant publié que sur `127.0.0.1`, Caddy ne peut pas être contourné. Nginx retient l'IP du client grâce à `real_ip_header X-Forwarded-For` et `real_ip_recursive on`.

## 2. En place

| Domaine | Mesure |
|---|---|
| Réseau | Réseaux `app` et `data` internes ; base non publiée ; un seul point d'entrée sur le réseau ; supervision sur `127.0.0.1` |
| Docker | Seul `docker-proxy` monte le socket Docker (lecture seule, `POST=0`) ; images en version fixe |
| Conteneurs | `no-new-privileges` sur les services applicatifs et de supervision ; backend en non-root, système de fichiers en lecture seule, toutes les capacités retirées |
| nginx | `server_tokens off`, requêtes limitées à 1 Mo, en-têtes `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, délais sur `/api/`, résolution DNS à chaque requête |
| Secrets | SOPS + age, aucun secret en clair dans le dépôt |
| Remédiation | Actions Ansible en liste blanche ; blocage d'IP limité à une adresse, avec adresses protégées et restauration en cas d'échec |

## 3. À décider en équipe

| Point | Propriétaire | Détail |
|---|---|---|
| WAF en `DetectionOnly` | Stéphanie | Il journalise sans bloquer. Passer en blocage ou documenter comme choix de démonstration |
| Limitation de débit | Marina | `limit_req` sur `/api/` contre la force brute du login (utile maintenant que l'IP est correcte) |
| `/docs` et `/openapi.json` | Marina | Documentation de l'API lisible depuis le réseau du groupe ; à retirer ou à accepter pour la démonstration |
| `rag` et `ollama` | Léa, Richard | Pas d'utilisateur non-root ; réseau `rag` non interne (nécessaire seulement au téléchargement des modèles) |
| Frontend | Marina | Image nginx classique, exécutée en root ; risque faible (réseau interne, fichiers statiques) |
| Python 3.10 | Marina | Fin de support en octobre 2026 |

## 4. Choix pour le moteur de remédiation

Le moteur reste sur le PC hôte et appelle `bash infra/ansible/run.sh <action>`. Seules les actions de la liste blanche sont possibles. Aucun conteneur ne reçoit le socket Docker : un proxy Docker avec `POST` autorisé permettrait de créer un conteneur qui monte le disque de l'hôte, donc il protégerait très peu.

## 5. Risques acceptés et limites

- `cadvisor` monte le disque de l'hôte en lecture seule : nécessaire à son fonctionnement.
- Pas de TLS entre le client et le point d'entrée.
- Une seule clé partagée pour les secrets ; les dumps de la base ne sont pas chiffrés ; les secrets restent visibles dans l'environnement des conteneurs (`docker inspect`).
- Le blocage d'IP est fait par nginx, pas par le WAF. Une durée (`minutes=`) n'est appliquée que si `purge_expired` est appelé régulièrement.
- Le moteur de remédiation reste très privilégié sur l'hôte : il est limité par la liste blanche des actions.

## 6. Contrôles

```text
docker ps --format "{{.Names}}  {{.Ports}}"
docker compose exec nginx nginx -t
curl.exe -s -o NUL -w "%{http_code}" http://localhost:8080/health
bash infra/ansible/run.sh list_blocked
```

Seul Caddy doit être joignable depuis le réseau du groupe : à vérifier avec `nmap -p- 192.168.137.1` depuis le PC attaquant.
