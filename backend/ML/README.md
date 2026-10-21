# Assistant documentaire RAG — Phenix

Le RAG recherche dans `backend/ML/corpus/` et appelle Ollama localement pour produire une réponse courte avec références. Il explique les procédures sans intervenir sur les services. Aucun outil de navigation web n’est fourni au modèle.

## Préparation et exécution séparées

| Service | Réseau | Rôle |
| --- | --- | --- |
| `ollama-init` | `model_download`, accès externe | Démarre son propre serveur temporaire sur 127.0.0.1, télécharge les modèles absents, arrête ce serveur et termine |
| `ollama` | `rag`, `internal: true` | Serveur d’inférence local, démarré après la réussite de l’initialisation |
| `rag` | `rag`, `internal: true` | Recherche documentaire et génération via le serveur local |

Les modèles restent dans le volume existant `ollama_models`. Le téléchargeur n’a accès ni au corpus, ni à l’index, ni aux réseaux métier, ni aux secrets SOPS. Il ne partage aucun réseau avec les deux services d’exécution. Seul le stockage des modèles est partagé. Il ne télécharge pas les modèles déjà présents et ne met pas à jour leurs poids automatiquement.

Le réseau interne coupe la connectivité externe routée des services d’exécution. Cette configuration n’est pas une politique pare-feu complète du PC hôte : ne pas leur ajouter de réseau externe, de proxy de sortie, de réseau hôte ou de socket Docker. `model_download` autorise Internet au téléchargeur ; il ne limite pas les destinations à une liste de domaines. Le serveur temporaire écoute uniquement dans son propre conteneur et aucun port n’est publié.

## Appliquer la modification sur un poste existant

Le réseau Docker `rag` existant n’était pas interne. Il faut le recréer, car ce paramètre ne se modifie pas sur place. Conserver le même nom de projet Compose pour réutiliser les volumes.

Remplacer le `docker-compose.yml` à la racine, ce README dans `backend/ML/`, et y ajouter `check_rag_network.py`. Si le Compose a évolué entre-temps, reporter uniquement les modifications IA. Cette livraison conserve notamment l’entrée WAF de la version partagée sur `127.0.0.1:8081`.

Depuis PowerShell, à la racine du projet, attendre la fin des requêtes RAG puis arrêter et retirer uniquement les conteneurs IA :

```powershell
docker compose --env-file .env.example stop rag ollama ollama-init
docker compose --env-file .env.example rm -f rag ollama ollama-init
```

Cela conserve les volumes. Ne pas ajouter `-v`. Retirer ensuite l’ancien réseau IA du projet `phenix` :

```powershell
$ragNetworks = @(docker network ls --filter "label=com.docker.compose.project=phenix" --filter "label=com.docker.compose.network=rag" --format "{{.ID}}")
foreach ($networkId in $ragNetworks) { docker network rm $networkId }
```

Si vous utilisez un nom de projet différent, adapter `phenix`. Si Docker refuse car un conteneur utilise encore ce réseau, identifier ce conteneur avant de continuer, sans déconnecter les services métier au hasard. Ne pas utiliser de prune global.

Démarrer ensuite via votre script SOPS habituel :

```powershell
.\infra\secrets\start.ps1
```

Sous Linux/WSL : `infra/secrets/start.sh`. Ces scripts doivent lancer le Compose principal sans exclure les services IA. Les secrets restent gérés par le mécanisme de l’équipe ; ne pas démarrer les services métier avec les valeurs factices de `.env.example`.

## Premier démarrage et démarrages suivants

Sur un nouveau poste ou un volume de modèles vide, `ollama-init` télécharge `embeddinggemma:300m` et `qwen3:4b-instruct`. Il nécessite alors Internet. Le serveur d’inférence attend sa fin. Si un téléchargement échoue, l’initialisation échoue et le démarrage des dépendants est bloqué.

Avec les modèles déjà présents, l’initialisation ne fait que vérifier leur disponibilité locale. Les démarrages suivants n’ont pas besoin du registre de modèles, à condition que les images Docker et dépendances soient déjà présentes sur le PC. Un build Python ou le téléchargement d’une image restent des opérations distinctes pouvant utiliser Internet sur l’hôte.

```powershell
docker compose --env-file .env.example ps -a ollama ollama-init rag
docker compose --env-file .env.example logs --tail=30 ollama-init
docker compose --env-file .env.example exec ollama ollama list
```

`ollama-init` en `Exited (0)` est normal. `rag` affiche l’aide et se termine : il reste un outil CLI. `logs -f` suit les logs sans rendre la main ; Ctrl+C quitte ce suivi sans arrêter les conteneurs.

Ne pas lancer une seconde préparation manuelle pendant que le serveur d’inférence utilise le même volume. Pour changer les modèles ou réparer un modèle supprimé : terminer les requêtes, arrêter les conteneurs IA, puis relancer le démarrage SOPS afin de refaire la préparation avant l’inférence.

## Ingestion et questions depuis la racine

Une fois les modèles prêts et Ollama démarré :

```powershell
docker compose --env-file .env.example run --rm --no-deps rag python -m rag ingest
docker compose --env-file .env.example run --rm --no-deps rag python -m rag ask "Comment vérifier la collecte Prometheus ?"
docker compose --env-file .env.example run --rm --no-deps rag python -m rag retrieve "Comment vérifier la collecte Prometheus ?"
```

Pour ces opérations IA uniquement, `--env-file .env.example` fournit les valeurs factices nécessaires à la lecture du Compose. `--no-deps` évite de relancer les dépendances, dont le téléchargeur ; Ollama doit déjà être démarré. Les variables du fichier d’exemple ne sont pas injectées dans les services IA. Le fichier d’exemple doit contenir les noms de variables attendus ; sinon des avertissements peuvent subsister.

Le corpus est monté en lecture seule depuis le dépôt. Après ajout, modification ou suppression d’un document, relancer `ingest`, sans build. L’ingestion demeure manuelle et conserve son index dans `rag_index`. Changer le code Python ou les dépendances nécessite un build, par exemple `docker compose --env-file .env.example build rag`.

Les volumes sont gérés par Compose : `down` les conserve, `down -v` peut les supprimer, y compris les données métier. La migration ci-dessus ne supprime aucun volume.

## Vérifier l’isolation sur le poste

Inspecter le réseau d’inférence, en adaptant `phenix` si nécessaire :

```powershell
docker network inspect phenix_rag --format '{{.Internal}}'
```

Attendu : `true`. Vérifier les réseaux du serveur :

```powershell
$ollamaId = docker compose --env-file .env.example ps -q ollama
docker inspect $ollamaId --format '{{json .NetworkSettings.Networks}}'
```

Il doit être uniquement sur `phenix_rag`, pas sur `model_download`.

Contrôle depuis un conteneur RAG :

```powershell
docker compose --env-file .env.example run --rm --no-deps --volume ./backend/ML/check_rag_network.py:/workspace/check_rag_network.py:ro rag python /workspace/check_rag_network.py
```

Le script vérifie que l’API locale Ollama répond et tente deux connexions TCP externes (aucune donnée applicative envoyée). Les connexions externes doivent échouer.

Pour refaire ce contrôle depuis l’espace réseau du serveur Ollama, avec Python fourni par l’image RAG :

```powershell
$ollamaId = docker compose --env-file .env.example ps -q ollama
$ragImage = docker compose --env-file .env.example images -q rag | Select-Object -First 1
docker run --rm --network "container:$ollamaId" --mount "type=bind,source=$((Get-Location).Path)/backend/ML/check_rag_network.py,target=/workspace/check_rag_network.py,readonly" $ragImage python /workspace/check_rag_network.py --base-url http://127.0.0.1:11434
```

Ces essais complètent l’inspection de la configuration ; l’échec de deux connexions ne constitue pas à lui seul une preuve exhaustive de filtrage réseau. Terminer par une question RAG, qui doit fonctionner malgré l’absence de sortie Internet.

## Corpus et limites des réponses

Seul `corpus/` est indexé (`.md`, `.txt` UTF-8 et PDF texte ; pas de fichiers cachés ni de liens symboliques). Ne jamais y déposer de secrets ou de journaux sensibles. Voir [CORPUS.md](CORPUS.md) et [CHOIX_TECHNIQUES.md](CHOIX_TECHNIQUES.md).

L’isolation réseau ne force pas mathématiquement une réponse à provenir des documents : le modèle conserve ses connaissances préentraînées. Les consignes de réponse fondée sur le contexte, les références et l’abstention restent nécessaires. La vérification des citations n’est pas une preuve de fidélité sémantique. Tester aussi une question absente du corpus.

Le RAG ne consulte pas l’état réel des services, ne lance pas Ansible et n’a actuellement ni API HTTP, ni interface web, ni mémoire conversationnelle. Son futur raccordement au front devra préserver l’isolation réseau.

## Validation de cette livraison

Le YAML et la préservation des autres services/volumes ont été vérifiés. Le script d’initialisation a été testé avec un faux client Ollama pour les cas modèles présents, modèles manquants, téléchargement en échec et serveur indisponible. Docker n’est pas disponible dans l’environnement de génération : les contrôles réels ci-dessus restent à exécuter sur le poste.

Références :
- https://docs.docker.com/reference/compose-file/networks/#internal
- https://docs.docker.com/compose/how-tos/startup-order/