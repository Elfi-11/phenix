# Règles d'alerte SIEM

Projet RESILIENCE-ALPHA — Yannick PINCHON, équipe Cyber 1 (Infra et défense), octobre 2026

Ce document décrit les règles de détection écrites dans Grafana/Loki, le format des logs sur lesquels elles s'appuient et la façon de les réutiliser côté ML.

## 1. Où sont les règles

| Élément | Valeur |
|---|---|
| Fichier | `infra/observability/grafana/provisioning/alerting/rules.yml` |
| Chargement | Automatique au démarrage de Grafana (provisioning) |
| Source de logs | Loki, source `uid: loki` |
| Conteneur surveillé | `phenix-waf-1` (journal d'accès du WAF) |
| Fréquence | Évaluation toutes les minutes, fenêtre de 5 minutes |
| Interface | Grafana, Alerting, Alert rules, dossier Phenix |

## 2. Format des logs du WAF

Une ligne par requête. Exemple :

```
172.23.0.1 - - [21/Oct/2026:09:59:52 +0000] "GET / HTTP/1.1" 403 548 "-" "Mozilla/5.0 ..." "192.168.137.144"
```

| Champ | Exemple | Remarque |
|---|---|---|
| IP Docker | `172.23.0.1` | À ignorer : c'est la passerelle Docker |
| Date | `21/Oct/2026:09:59:52 +0000` | |
| Méthode et chemin | `GET /` | |
| Statut HTTP | `403` | 403 refus, 404 introuvable, 5xx erreur serveur |
| Taille | `548` | octets |
| User-Agent | `Mozilla/5.0 ...` | |
| **IP réelle du client** | `192.168.137.144` | **Dernier champ entre guillemets.** C'est elle qu'il faut utiliser |

Labels Loki disponibles : `container`, `service`, `service_name`.
Une requête lancée depuis le PC hôte apparaît avec l'IP `::1` (bouclage).

Extraction en LogQL (utilisée dans les trois règles) :

```
{container="phenix-waf-1"} | pattern `<_> - - [<_>] "<method> <path> <_>" <status> <size> "<_>" "<_>" "<ip>"`
```

## 3. Les quatre règles

| Règle | Ce qu'elle détecte | Seuil | Gravité |
|---|---|---|---|
| Rafale de 403 | Une IP se fait refuser plus de 10 fois en 5 min (attaque bloquée par le WAF, ou IP déjà bloquée qui insiste) | plus de 10 | warning |
| Scan de chemins | Une IP provoque plus de 15 erreurs 404 en 5 min (recherche de pages cachées) | plus de 15 | warning |
| Erreurs 5xx | Plus de 5 erreurs serveur en 5 min, toutes IP confondues (service en panne ou attaque qui le fait tomber) | plus de 5 | critical |
| Injection SQL | Une requête contient un motif d'injection SQL (`UNION SELECT`, `' OR 1=1`, `' --`, `sleep(`, `benchmark(`, `information_schema`) | au moins 1 en 5 min | critical |

Chaque alerte, sauf les erreurs 5xx, porte le label `ip`. Une alerte déclenchée passe par les états `Normal`, `Pending` (seuil dépassé), puis `Firing` après 1 minute.

Le motif de la règle injection SQL (filtre de ligne, insensible à la casse) cherche dans l'URL telle qu'elle a été envoyée, donc avec les caractères encodés (`%27` pour l'apostrophe, `%20` pour l'espace) :

```
(?i)(union(%20|\+|\s)+(all(%20|\+|\s)+)?select|(%27|')(%20|\+|\s)*(or|and)(%20|\+|\s)|(or|and)(%20|\+|\s)+[0-9]+(%3D|=)[0-9]+|sleep[(]|sleep%28|benchmark[(]|benchmark%28|information_schema|(%27|')(%20|\+)*(--|%2D%2D|%23))
```

Requêtes complètes des trois premières règles :

```
sum by (ip) (count_over_time({container="phenix-waf-1"} | pattern `<_> - - [<_>] "<method> <path> <_>" <status> <size> "<_>" "<_>" "<ip>"` | status="403" [5m]))
sum by (ip) (count_over_time({container="phenix-waf-1"} | pattern `<_> - - [<_>] "<method> <path> <_>" <status> <size> "<_>" "<_>" "<ip>"` | status="404" [5m]))
sum(count_over_time({container="phenix-waf-1"} | pattern `<_> - - [<_>] "<method> <path> <_>" <status> <size> "<_>" "<_>" "<ip>"` | status=~"5.." [5m]))
```

## 4. Ce que le module ML peut en tirer

| Besoin | Piste |
|---|---|
| Données d'entraînement ou d'analyse | Lire les logs via l'API de Loki (`/loki/api/v1/query_range`) avec la requête d'extraction ci-dessus |
| Variables utiles par IP | nombre de requêtes, part de 403, part de 404, nombre de chemins différents, rythme par minute, User-Agent |
| Règles à affiner | Les seuils (10, 15, 5) sont des valeurs de départ ; le ML peut proposer des valeurs adaptées au trafic réel |
| Décision | Le ML signale une IP suspecte, le moteur de remédiation appelle l'action `block_ip` |

## 5. Lien avec la remédiation

Une IP jugée malveillante se bloque avec l'action Ansible `block_ip` (durée maximale 7 jours, IP protégées jamais bloquées). `unblock_ip` la débloque, `list_blocked` liste les blocages et `purge_expired` retire ceux qui sont expirés. Le blocage est écrit dans `infra/nginx/blocklist/blocklist.conf` puis nginx est rechargé.

## 6. Limites et points à décider

| Point | Détail |
|---|---|
| Notification | Les alertes ne sont visibles que dans Grafana pour l'instant ; aucun mail ni webhook n'est branché |
| Webhook vers le moteur | À brancher quand Léa et Richard fournissent l'URL et le format attendu |
| Seuils | Valeurs de départ, à ajuster avec le trafic réel |
| Injection SQL | Détection par motif dans l'URL : elle ne voit pas une injection placée dans le corps d'une requête POST, ni un motif encodé de façon inhabituelle. Les règles du WAF (identifiants 942xxx) la complètent quand il sera passé en blocage |
| Mode du WAF | `DetectionOnly` : le WAF journalise sans bloquer, donc peu de 403 d'origine WAF (décision à prendre avec Stéphanie) |
