# Ajouter une procédure au corpus RAG
Configuration du RAG Phenix avec Ollama ; opérateur du projet, sur le PC hôte depuis la racine du dépôt.
Placer une fiche Markdown courte dans backend/ML/corpus. Décrire un seul objectif, l'environnement, les prérequis, les étapes et le résultat attendu. Distinguer configuration vérifiée et recommandation générale ; ne jamais inclure de secret.
Exécuter `docker compose run --rm rag python -m rag ingest` après chaque modification du corpus pour reconstruire l'index.
Puis lancer `docker compose run --rm rag python -m rag ask "Comment vérifier la collecte Prometheus ?"`.
Vérifier la pertinence de la réponse et de ses sources ; leur présence seule ne garantit pas l'exactitude. Le modèle ne découvre pas automatiquement l'état du système ni les fichiers hors du corpus.
