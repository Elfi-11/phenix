# Vérifier les compteurs HTTP du backend

Objectif : vérifier que les appels utilisateur sont comptabilisés.
Environnement : navigateur sur le PC hôte qui exécute Docker Desktop.
Prérequis : cible backend UP dans Prometheus et route /api/ping disponible.

## Étapes
1. Ouvrir http://localhost:9090 ; dans Graph, saisir la requête PromQL
   http_requests_total{job="backend"}, cliquer sur Execute, puis Table.
2. Noter le compteur de la série handler="/api/ping", method="GET", status="2xx".
3. Dans http://localhost:8080/docs, exécuter GET /api/ping trois fois.
4. Attendre la prochaine collecte Prometheus, puis réexécuter la requête PromQL.

## Résultat attendu
Sans autre appel ni redémarrage, le compteur augmente de trois.
Un compteur stable sans nouvelle requête est normal : cela ne prouve pas une panne.
PromQL se saisit dans Prometheus, pas sur l'adresse d'exposition des métriques.

Cette procédure ne fournit aucun état en direct.
