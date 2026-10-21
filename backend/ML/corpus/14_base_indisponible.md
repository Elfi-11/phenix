# Base de données indisponible : premiers contrôles
Configuration Phenix, service PostgreSQL nommé db. Intervention humaine avec accès Docker autorisé, sur le PC hôte à la racine du dépôt.
Exécuter `docker compose ps db backend`, puis `docker compose logs --tail=50 db` et `docker compose logs --tail=50 backend`. Rechercher une erreur de connexion, un manque de ressources ou un problème de démarrage sans diffuser les secrets.
Vérifier la configuration de connexion via les canaux sécurisés de l'équipe ; ne pas demander le contenu du .env dans le chat.
Ne pas supprimer le volume de données pour résoudre une panne de connexion. Une réinitialisation peut faire perdre les données.
Un contrôle de santé réussi ne valide pas une transaction métier. Après correction autorisée, vérifier les appels API concernés puis une opération métier de test.
