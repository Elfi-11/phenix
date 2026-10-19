import argparse
import json
import sys
from rag.config import Config
from rag.index import build, search
from rag.assistant import answer, embedding_client


def main():
    parser = argparse.ArgumentParser(description="RAG documentaire Phenix, local et sans action système")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ingest", help="Créer ou reconstruire l'index du corpus")
    for name in ("ask", "retrieve"):
        p = sub.add_parser(name, help="Répondre avec sources" if name == "ask" else "Voir uniquement les passages retrouvés")
        p.add_argument("question")
        p.add_argument("--min-similarity", type=float, default=0.35)
    args = parser.parse_args()
    config = Config(min_similarity=getattr(args, "min_similarity", 0.35))
    if not -1 <= config.min_similarity <= 1:
        parser.error("Le seuil cosinus doit être entre -1 et 1")
    try:
        if args.command == "ingest":
            result = build(config, embedding_client(config))
        elif args.command == "retrieve":
            result = search(config, embedding_client(config), args.question)
        else:
            result = answer(config, args.question)
        if args.command == "ask":
            if result["status"] == "unverified_citations":
                print(
                    "La réponse générée n’a pas pu être validée : "
                    "ses références sont absentes ou incorrectes."
                )
            else:
                print(result["answer"])

                for source in result["sources"]:
                    print(f"[{source['id']}] {source['source']}")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        # Les réponses brutes d'un service distant ne sont pas affichées.
        message = str(exc) if type(exc) is ValueError else f"Erreur {type(exc).__name__} : vérifier Ollama, les modèles et la configuration."
        print(json.dumps({"status": "error", "message": message}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()