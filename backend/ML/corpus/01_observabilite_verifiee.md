# Vérifier la collecte Prometheus

Objectif : vérifier que Prometheus récupère les métriques du backend.
Environnement : navigateur sur le PC hôte qui exécute Docker Desktop.
Prérequis : la plateforme et Prometheus sont démarrés.

## Étapes
1. Ouvrir http://localhost:9090/targets dans le navigateur du PC hôte.
2. Repérer la cible backend.
3. Vérifier son état UP, une dernière collecte récente et l'absence d'erreur.

## Résultat attendu
UP indique que la collecte des métriques du backend réussit.
DOWN indique un échec de collecte : lire le message d'erreur de cette cible.
Ce contrôle ne prouve pas qu'un paiement ou que la base fonctionne.
Il n'est pas nécessaire d'appeler directement le backend depuis le navigateur.

Cette procédure décrit un contrôle à effectuer, pas l'état actuel du service.