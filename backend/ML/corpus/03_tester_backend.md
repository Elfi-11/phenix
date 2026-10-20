# Tester la réponse du backend via Nginx

Objectif : vérifier qu'une requête atteint le backend via Nginx.
Environnement : navigateur sur le PC hôte qui exécute Docker Desktop.
Prérequis : plateforme démarrée et route /api/ping disponible.

## Étapes
1. Ouvrir http://localhost:8080/docs dans le navigateur du PC hôte.
2. Déplier GET /api/ping, cliquer sur Try it out, puis Execute.
3. Lire le code et le corps de la réponse dans Server response.

## Résultat attendu
HTTP 200 et {"pong": true} confirment que le backend répond via Nginx.
Cela ne valide ni une connexion utilisateur, ni un paiement, ni la base de données.
GET /health possède un autre résultat attendu : HTTP 200 et {"status": "ok"}.

Le bot explique ce contrôle ; il ne peut pas confirmer l'état actuel du backend.
