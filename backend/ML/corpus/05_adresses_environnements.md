# Choisir une adresse selon l'environnement
Configuration Docker Phenix connue ; accès depuis le PC qui héberge Docker.
Le navigateur de ce PC utilise http://localhost:8080 pour le site et sa documentation API, http://localhost:9090 pour Prometheus et http://localhost:3000 pour Grafana.
Dans Docker, backend:8000 et nginx sont des noms de services, accessibles uniquement depuis des conteneurs partageant les réseaux nécessaires. http://backend:8000/metrics est une adresse interne de collecte, pas un lien pour le navigateur du PC.
localhost désigne toujours l'environnement qui effectue la requête : dans un conteneur, ce n'est pas le PC hôte.
Le RAG et Ollama sont sur leur réseau dédié ; ne pas supposer qu'ils peuvent joindre le backend. Sur un autre PC, ces URL localhost désignent cet autre PC.
