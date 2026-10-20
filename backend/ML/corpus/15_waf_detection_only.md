# WAF Phenix : détection et blocage
Configuration du Compose partagé : service waf devant Nginx, MODSEC_RULE_ENGINE réglé sur DetectionOnly.
Dans ce mode, les règles peuvent produire des alertes sans empêcher la requête d'atteindre l'application. Une alerte ne prouve donc pas qu'une attaque a été bloquée ou qu'elle a réussi.
Accès : opérateur habilité pour consulter les journaux et le paramétrage effectif. Comparer l'heure de l'alerte, la requête et la réponse applicative ; expurger les données sensibles avant partage.
Le passage à un mode de blocage nécessite une décision de l'équipe et des essais autorisés, car des requêtes légitimes peuvent être affectées. L'assistant n'applique pas ce changement.
La configuration locale peut évoluer : vérifier le Compose effectivement déployé avant de conclure sur le mode actif.
