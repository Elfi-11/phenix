# Corpus de procédures Phenix

Première base documentaire — 20 octobre 2026. Modèle conservé : qwen3:4b-instruct.

## Installation
Copier les fichiers de `corpus/` vers `backend/ML/corpus/` sans supprimer les autres fichiers de votre dépôt. Les trois premières fiches reprennent les contrôles précédemment documentés ; conserver votre version si elle a évolué. Relire les fiches de configuration par rapport au Compose effectivement utilisé.

Depuis la racine du dépôt :
```sh
docker compose run --rm rag python -m rag ingest
docker compose run --rm rag python -m rag ask "Que faire en cas de suspicion d’injection SQL ?"
```
Si le corpus est copié dans l'image et non monté en volume, reconstruire le service avant l'ingestion : `docker compose build rag`. S'il est monté en volume, la réindexation suffit.

## Couverture et niveau de preuve
| Fiches | Objet | Nature |
| --- | --- | --- |
| 01–03 | Collecte Prometheus, compteurs HTTP, ping backend | Contrôles déjà documentés dans le projet |
| 04–05 | Rôle du bot et adresses | Périmètre prévu et configuration partagée |
| 06–12 | Qualification, SQLi, surcharge, authentification, fuite, droits | Procédures générales à adapter ; attaques et automatismes non confirmés |
| 13–15 | API, PostgreSQL, WAF | Diagnostic fondé sur les services du Compose partagé |
| 16 | Transaction de vérification | Scénario demandé ; contrat API à confirmer |
| 17–20 | Sauvegardes, secrets, journaux, escalade | Procédures humaines ; détails de déploiement à confirmer |
| 21 | Maintenance du corpus | Commandes du RAG intégré au Compose principal |

Les fiches sont volontairement courtes pour conserver leurs limites et prérequis dans les extraits récupérés. Ce document de référence reste hors de `corpus/` afin de ne pas perturber la recherche.

## Références
Les recommandations sont adaptées au laboratoire ; elles ne prouvent pas leur implémentation dans Phenix.
- Injection SQL et correction : https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- Disponibilité : https://cheatsheetseries.owasp.org/cheatsheets/Denial_of_Service_Cheat_Sheet.html
- Autorisations : https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- Journaux : https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- Configuration et tests : Compose partagé par l'équipe, contrôles manuels précédents et scénario de passation du paiement.

## Vérification à effectuer dans le projet
Tester les questions suivantes : collecte Prometheus, différence entre UP et paiement réussi, SQLi, WAF qui alerte sans bloquer, base indisponible, demande de redémarrage au bot, demande de mot de passe et question absente du corpus.
Attendre une réponse courte, des sources pertinentes, la bonne distinction hôte/conteneur et une intervention humaine explicite si nécessaire. Le bot doit dire ce qui manque plutôt que compléter avec une configuration inventée.

Cette livraison vérifie la structure des documents, pas les réponses du modèle avec ce corpus élargi. Le seuil de recherche actuel et le nombre d'extraits peuvent nécessiter un ajustement après essais. Aucune durée de réponse ni fiabilité globale n'est déduite ici.
