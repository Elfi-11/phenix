# Échecs de connexion et suspicion de force brute
Procédure générale ; routes d'authentification et protections à confirmer dans Swagger.
Accès : documentation API et journaux expurgés, par un humain habilité.
Vérifier d'abord le format attendu de la requête et le compte de démonstration. Ne pas confondre authentification invalide, droits insuffisants et indisponibilité du service ; lire la réponse réelle de l'API.
Des échecs répétés peuvent justifier une investigation, sans prouver une force brute. Corréler les heures, routes et comptes concernés sans diffuser les identifiants sensibles.
Une limitation de tentatives ou une révocation de session relève de l'équipe habilitée et dépend des fonctions effectivement disponibles. Ne jamais coller de mot de passe ni de JWT dans le chat. Valider ensuite avec un compte de test autorisé.
