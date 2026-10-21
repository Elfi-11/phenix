# Suspicion d'injection SQL : premiers contrôles
Procédure générale pour le laboratoire ; détection et blocage automatiques non confirmés.
Accès : journaux applicatifs et WAF, consultés par un humain habilité.
1. Relever l'heure, la route et les identifiants de requête disponibles ; rechercher des alertes WAF et des erreurs SQL corrélées.
2. Vérifier l'impact sur les réponses API et les opérations métier. Une alerte WAF seule ne prouve ni une exploitation réussie ni une fuite.
3. Transmettre aux développeurs la route et les observations expurgées. Ne pas rejouer de charge d'attaque sur un environnement non autorisé.
Dans la configuration Phenix partagée, le WAF est en DetectionOnly : il peut signaler sans bloquer. L'assistant explique les vérifications ; il n'inspecte pas les journaux en direct.
