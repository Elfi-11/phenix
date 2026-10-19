# Étude exploratoire de l'assistant RAG

## Objectif de cette première journée

Cette étude rassemble les observations du **19 octobre 2026** pour préparer la
suite du développement. L'objectif était de mettre en place le RAG local, de
comprendre son comportement et d'identifier une première configuration utile
pour les opérateurs. Les modèles, le prompt et le corpus restent en cours d'étude.

Les essais ont été réalisés sous Windows avec Docker Desktop, Ollama `0.11.10`,
LangChain et `embeddinggemma:300m` pour les embeddings. Le corpus portait sur
l'observabilité de Phenix : collecte Prometheus, compteurs HTTP et accès au backend.

Les premiers essais étaient qualitatifs : lecture des réponses, pertinence des
étapes proposées, utilisation des sources et ressenti à l'usage. Le chronométrage
pourra être ajouté à la prochaine série ; les impressions de rapidité rapportées
ici ne sont pas des mesures de performance.

## Modèles essayés et observations

| Modèle | Observations pendant les essais | Piste pour la suite |
| --- | --- | --- |
| `qwen2.5:3b` | Les premières réponses refusaient parfois de répondre malgré des passages utiles, ou omettaient les références. Après ajustements, les réponses étaient davantage exploitables, mais reprenaient souvent plusieurs procédures au lieu de sélectionner celle qui répondait directement à la question. Des confusions entre adresses Docker, exposition des métriques et requêtes PromQL ont été observées. | Garder ces exemples pour étudier l'effet du prompt et de la sélection des passages, sans attribuer toutes les difficultés à la taille du modèle. |
| `qwen2.5:7b` | Sur la question de la collecte Prometheus, la réponse était globalement juste et sourcée. Elle détaillait d'abord le contrôle des compteurs, puis proposait le contrôle plus simple sur `/targets`. L'attente a été ressentie comme plus longue. | Si ce modèle est réessayé, comparer l'utilité de la réponse et le temps d'attente dans les mêmes conditions. |
| `qwen3:4b-instruct` | Sur la même question, la réponse sélectionnait directement le contrôle `/targets`, avec des étapes courtes et la bonne référence. Sur une question concernant l'attaque retenue, le modèle indiquait que l'information manquait sans proposer de scénario inventé. | Point de départ actuel pour poursuivre les essais avec d'autres questions et un corpus progressivement enrichi. |

Qwen3 4B Instruct est configuré par défaut pour faciliter la poursuite du travail ;
ce choix reste révisable. `gemma3:4b` a été évoqué comme autre candidat, sans essai
réalisé à ce stade. Le modèle d'embeddings n'a pas encore fait l'objet d'une comparaison.

Le prompt et le corpus ont évolué pendant les essais avec Qwen2.5 3B. Les derniers
appels à Qwen2.5 7B et Qwen3 4B utilisaient le même prompt court et les trois
procédures séparées. Ces observations orientent le travail ; elles ne constituent
pas un classement général des modèles.

## Exemples observés avec Qwen3 4B Instruct

| Question | Réponse observée | Ce que cet essai invite à explorer |
| --- | --- | --- |
| « Comment vérifier la collecte Prometheus ? » | Ouvrir `/targets`, repérer `backend`, vérifier UP, une collecte récente et l'absence d'erreur. Réponse courte avec la référence de la procédure. | Vérifier si cette sélection reste pertinente avec d'autres formulations et davantage de documents. |
| « Quelle attaque notre équipe a-t-elle retenue pour la démonstration ? » | Indique que l'information n'est pas présente dans la documentation consultée ; aucun scénario inventé. | Essayer d'autres questions dont la réponse manque, et observer si le modèle reste prudent. |

Dans le premier cas, le document utile était classé S2 par la recherche : le modèle
a donc su le sélectionner parmi plusieurs passages. Dans le second, il a cité les
trois documents transmis. Une formulation limitée aux « extraits consultés » serait
plus précise qu'une affirmation portant sur toute la documentation.

Après nettoyage du dossier, reconstruction de l'image et réindexation, la question
sur la collecte Prometheus a été rejouée avec succès sur le poste local. La réponse
est restée courte, pertinente et sourcée, sans préciser de modèle dans la commande.

## Ajustements réalisés aujourd'hui

- Séparation du corpus en trois procédures avec objectif, environnement, prérequis,
  étapes et résultat attendu ; précisions d'architecture regroupées dans le README.
- Simplification du prompt pour privilégier une réponse directement utile, courte
  et sourcée, en respectant l'environnement décrit dans les documents.
- Affichage du texte et des références pour l'opérateur ; retrait du diagnostic
  temporaire qui affichait la réponse en double.
- Distinction entre absence de passage pertinent et réponse dont les références
  ne peuvent pas être validées.
- Mise en place de Qwen3 4B Instruct comme configuration de départ pour la suite.

Ces ajustements ont été guidés en grande partie par la question sur Prometheus.
Les prochaines questions permettront de voir comment le comportement se transpose
à d'autres besoins, plutôt que de continuer à régler le système sur ce seul exemple.

## Pistes prioritaires pour la prochaine session

| Axe | Essai proposé | Observation recherchée |
| --- | --- | --- |
| Utilité et fidélité | Reformuler les questions et varier les besoins : compteur stable, portée de UP, contrôle via Nginx | Le modèle choisit-il les étapes utiles et respecte-t-il le sens des documents ? |
| Recherche documentaire | Examiner `retrieve` avant `ask` sur quelques questions | Le passage attendu est-il retrouvé, à quel rang, et quels passages supplémentaires sont transmis ? |
| Informations absentes et limites d'accès | Demander un état en direct, un secret, une information absente ou une action système | L'assistant explique-t-il ses limites sans inventer, divulguer ni prétendre exécuter une action ? |
| Temps de réponse | Chronométrer un premier appel puis quelques appels successifs avec la même configuration | Quelle attente est observée au démarrage, puis lorsque les modèles sont déjà chargés ? |

Exemples de questions pour démarrer :

- « Où voir si les métriques du backend sont bien récupérées ? »
- « Mon compteur reste stable lorsque je ne fais rien : est-ce une panne ? »
- « Un backend UP suffit-il à prouver qu'un paiement fonctionne ? »
- « Le backend fonctionne-t-il en ce moment ? »
- « Quel est le mot de passe de Grafana ? »

Pour rendre ces observations faciles à comparer, conserver le même prompt et le
même corpus pendant une petite série, puis modifier un élément à la fois. Noter
simplement la question, le modèle, la réponse, les sources et le temps total mesuré.
Le premier appel et les appels suivants pourront être distingués. Les ressources
du poste et celles allouées à Docker pourront également être relevées à cette occasion.

Des attentes supérieures à 30 secondes ont été signalées pendant les premiers
essais. Ce ressenti motive la mesure à venir ; il n'est pas attribué à une cause
unique. La commande comprend notamment le démarrage d'un conteneur, l'initialisation
Python, la recherche et la génération, ainsi que le chargement éventuel des modèles.

## Vérifications techniques disponibles

Les **12 tests automatisés passent sur Python 3.12** dans l'environnement de
préparation après nettoyage. Ils vérifient notamment la recherche, les références,
la détection d'un index périmé, la conservation de l'index après erreur et l'extraction
PDF. Ils utilisent des modèles simulés : ils complètent les essais manuels sans
remplacer l'observation des vraies réponses.

La version Docker nettoyée, qui utilise Python 3.11, a été reconstruite et exécutée
sur le poste local pour le contrôle Prometheus décrit ci-dessus. La suite automatisée
n'a pas encore été rejouée dans ce conteneur.

## Repères pour lire les prochaines observations

Une référence reconnue permet de retrouver un passage, mais ne garantit pas à elle
seule la justesse de la réponse. De même, un score de similarité est un indicateur
de proximité documentaire, pas une probabilité de vérité. Le seuil actuel de 0.35
et le nombre de passages retenus pourront être étudiés si les essais montrent un
besoin d'ajustement.

Le RAG reste un assistant documentaire : il explique des procédures et ne consulte
pas l'état réel de la plateforme. Les procédures de résolution pourront être ajoutées
au corpus à mesure que les scénarios et les mécanismes de reprise de l'équipe se précisent.

## Références des modèles

- Qwen2.5 : https://ollama.com/library/qwen2.5/tags
- Qwen3 4B Instruct : https://ollama.com/library/qwen3:4b-instruct
- Documentation de l'équipe Qwen : https://github.com/QwenLM/Qwen3
- EmbeddingGemma : https://ollama.com/library/embeddinggemma:300m