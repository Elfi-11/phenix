# Scénarios d’attaque — Phenix

Deux scénarios sont conservés pour la plateforme fictive de l’équipe : injection SQL et brute force sur le login. Les scripts servent à produire des requêtes identifiables dans les logs et à tester la détection puis le confinement automatique.

| Scénario | Script | Détecteur associé | État |
|---|---|---|---|
| SQL | `injection_sql.ps1` | Modèle SQL sur le texte des paramètres WAF | Détection et incident validés depuis le PC hôte ; test réseau complet à réaliser |
| Brute force | `attaque_login.py` | Modèle distinct sur les fenêtres de login par IP | Modèle préparé sur données synthétiques ; essai réel à réaliser |

Ces essais se limitent à l’environnement de démonstration autorisé de l’équipe. Le RAG est un assistant documentaire indépendant et ne déclenche pas les attaques ou les actions.

## Préparation commune

Le PC hôte démarre la plateforme avec `infra/secrets/start.ps1`, qui lance aussi le moteur SQL actif. Avant un essai en observation ou un essai brute force, arrêter ce moteur avec Ctrl+C et lancer le moteur choisi selon le [README remédiation](../remediation/README.md). Ne pas laisser deux moteurs actifs simultanément.

Pour une démonstration réseau, connecter le PC attaquant au point d’accès prévu par l’équipe (actuellement documenté `RESILIENCE-G5`) et vérifier l’adresse réelle du PC hôte. `http://192.168.137.1:8080` est la valeur initiale des scripts, à adapter si nécessaire. L’URL `/health` doit répondre. Depuis le PC attaquant, `localhost` désignerait ce PC, pas l’hôte.

Pour un test local sur l’hôte, utiliser `http://localhost:8080`. Il permet de vérifier les alertes et les incidents ; les adresses locales protégées ne doivent pas être bloquées.

## Injection SQL

### Script depuis le PC attaquant

La route pédagogique authentifiée `GET /api/attackme/search` doit être activée pour la démonstration. Vérifier sa présence dans Swagger ; si elle est désactivée, se coordonner avec l’équipe backend.

Dans `injection_sql.ps1`, adapter les URL du PC hôte. Le script crée un compte de démonstration, se connecte puis envoie une injection UNION visant la lecture de données utilisateurs. Une inscription déjà réalisée peut provoquer une erreur lors d’un second lancement : distinguer l’inscription, le login et la requête de test. Conserver l’utilisation du jeton d’authentification mais retirer son affichage isolé. Ne pas inclure de jetons ou de données extraites dans les captures partagées.

Depuis la racine du dépôt, sur le PC attaquant :

```powershell
.\attaque\injection_sql.ps1
```

Sur l’hôte, commencer avec le moteur SQL en observation et confirmer l’IP détectée. Passer ensuite au mode actif pour le test complet.

### Test local via Swagger

Dans `http://localhost:8080/docs`, s’authentifier puis utiliser **Authorize**. Sur `/api/attackme/search`, tester `q=SUCCESS`, puis :

```sql
SUCCESS' OR '1'='1' -- 
```

En observation, le moteur affiche l’IP, le score et le seuil sans incident. En mode actif, un incident doit apparaître sur le dashboard ADMIN ; `::1` ou `127.0.0.1` sont protégées et l’incident reste ouvert. Procédure complète : [validation SQL](../remediation/README.md#validation-du-scenario-sql).

La première requête peut déjà avoir été exécutée avant sa détection dans les logs. L’absence de modification de la base ne prouve pas l’absence de lecture de données. Ce scénario démontre le confinement de la source, pas l’annulation d’une fuite.

## Brute force sur le login

Le script envoie volontairement des mots de passe erronés à `/api/auth/login`. Installer Python et `requests` sur le poste qui l’exécute :

```powershell
python -m pip install requests
```

Depuis la racine :

```powershell
python attaque/attaque_login.py --cible http://192.168.137.1:8080
```

Par défaut : 60 tentatives sur `alice_client`, espacées de 0,2 s. Options :

```powershell
python attaque/attaque_login.py --essais 30 --delai 0.2 --cible http://localhost:8080
python attaque/attaque_login.py --cible http://192.168.137.1:8080 --utilisateur bob_client
```

Le premier exemple est le test local. Démarrer auparavant le moteur brute force **en observation**, après arrêt du moteur SQL. Le modèle compte les POST login et les réponses 401 par IP pendant 60 s. Les lignes `AUTH_FAILURE` du backend sont aussi disponibles pour l’analyse, mais ne sont pas l’entrée de ce modèle. Ne pas annoncer une règle SIEM brute force raccordée sans l’avoir vérifiée.

## Résultats à vérifier

| Étape | Résultat attendu |
|---|---|
| Observation | Détection dans le terminal avec l’IP attendue ; aucune action système |
| Mode actif | Incident visible dans le dashboard administrateur |
| Essai local | IP locale protégée, incident laissé ouvert |
| Essai réseau actif | `block_ip` puis `verify` réussis et incident clôturé |
| Après blocage distant | Nouvelle requête de l’attaquant refusée, paiement légitime toujours réussi |

Un 403 est cohérent avec un blocage, mais vérifier aussi les journaux et la liste de blocage pour identifier sa cause. Une erreur réseau seule ne prouve pas le blocage. `/health` ne remplace pas la transaction de test du dashboard.

## Réinitialiser entre essais

Sur le PC hôte, depuis WSL à la racine du dépôt :

```bash
bash infra/ansible/run.sh unblock_ip ip=<IP_DU_PC_ATTAQUANT>
bash infra/ansible/run.sh list_blocked
```

Remplacer le paramètre par l’IP du poste de test. Le moteur temporise les nouvelles actions pour une même IP pendant cinq minutes ; garder ce comportement en tête lors des répétitions. Sans durée configurée, un blocage reste jusqu’au déblocage explicite. Avec une durée, vérifier le mécanisme `purge_expired` réellement exécuté.