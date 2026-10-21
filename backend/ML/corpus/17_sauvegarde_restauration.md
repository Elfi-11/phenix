# Sauvegarde et restauration de PostgreSQL
Configuration Phenix : le service pg_dump prévoit des exports dans le dossier backups du PC hôte. La présence d'un fichier ne garantit pas sa restauration.
Accès : opérateur habilité ; décision du responsable avant remplacement de données.
Pour une restauration, identifier la base visée, la sauvegarde disponible et sa date. Évaluer les données perdues depuis cette date et préserver l'état actuel si possible.
Tester d'abord la restauration dans un environnement isolé selon la procédure validée par l'équipe. Aucune commande de remplacement de la base n'est fournie ici : les paramètres et la procédure restent à confirmer.
Après restauration autorisée, vérifier la cohérence des données et une opération métier de test. Le chatbot n'accède pas aux sauvegardes et ne restaure aucune base.
