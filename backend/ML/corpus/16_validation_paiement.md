# Vérifier la reprise par un paiement de test
Scénario demandé par l'équipe ; disponibilité des routes et schémas à confirmer dans Swagger. Réservé aux comptes de démonstration et à un opérateur ou test autorisé.
Se connecter avec alice_client, relever le solde, puis payer un petit montant vers marchand_beta. Utiliser une idempotency_key UUID neuve pour une nouvelle opération ; lors d'une reprise de la même opération, conserver sa clé.
Vérifier le statut métier SUCCESS et la diminution exacte du solde avec une représentation monétaire précise. Relever durée et étape en échec ; prévoir un délai maximal court.
Le mot de passe vient de DEMO_USER_PASSWORD, jamais du corpus. Le test consomme le solde : prévoir sa gestion avec l'équipe.
Passer par le chemin utilisateur disponible. Les routes, champs et effets exacts doivent être validés avant d'automatiser ce scénario.
