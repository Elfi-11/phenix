# Accès interdit et suspicion d'élévation de privilèges
Recommandation générale ; politique des rôles Phenix à confirmer avec l'équipe.
Accès : développeur ou administrateur habilité.
Comparer l'identité, le rôle attendu et la ressource demandée à la politique prévue. Une réponse d'accès interdit peut être normale ; un accès réussi à une ressource non autorisée exige une investigation.
Vérifier les autorisations côté serveur pour chaque opération et ressource, avec un refus par défaut. Masquer un bouton dans l'interface ne constitue pas un contrôle d'accès.
Si un accès illégitime est confirmé, faire décider des restrictions et révocations nécessaires par le responsable. Le chatbot ne s'attribue pas de privilèges.
Validation : tests autorisés montrant que le rôle légitime fonctionne et que le rôle non autorisé est refusé.
