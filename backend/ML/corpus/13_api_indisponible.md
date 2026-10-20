# Site ou API indisponible : diagnostic Docker
Configuration Phenix ; commandes sur le PC hôte, depuis la racine du dépôt, par un opérateur autorisé.
1. Exécuter `docker compose ps backend db nginx waf` pour relever l'état des services.
2. Consulter `docker compose logs --tail=50 backend` et les journaux du service concerné. Masquer les secrets avant tout partage.
3. Comparer avec le test GET /api/ping via http://localhost:8080/docs et avec la cible backend dans Prometheus.
Un état Running ou une collecte UP ne prouve pas que les paiements fonctionnent. Un échec côté site peut venir du WAF, de Nginx, du backend ou d'une dépendance.
Préserver les observations et identifier la cause avant de proposer une action. Le chatbot n'exécute pas Docker ; toute intervention appartient à un humain habilité.
