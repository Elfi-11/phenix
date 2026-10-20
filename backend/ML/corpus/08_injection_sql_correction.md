# Injection SQL : corriger la cause
Recommandation générale ; intervention des développeurs habilités, pas du chatbot.
Prérequis : identifier le traitement de base concerné à partir du diagnostic.
Utiliser des requêtes paramétrées pour les valeurs utilisateur, sans concaténation SQL. Pour les noms de colonnes ou de tables non paramétrables, choisir dans une liste autorisée. Limiter les droits du compte applicatif aux besoins du service.
Une règle WAF peut contribuer au confinement, mais ne remplace pas la correction du code. Ne pas annoncer un blocage tant que son activation et son efficacité ne sont pas vérifiées.
Validation : dans le laboratoire autorisé, vérifier le comportement du traitement corrigé et les opérations métier légitimes. Conserver une trace de la correction et des résultats, sans exposer de données sensibles.
