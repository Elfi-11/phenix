"""Lancé à chaque démarrage du conteneur, avant Uvicorn : doit rester idempotent."""

from app.database import Base, engine

# Importer ici les modules de modèles pour qu'ils soient enregistrés dans Base.metadata
# ex : from app.models import user, transaction  # noqa: F401


def main():
    Base.metadata.create_all(bind=engine)
    print("create_db: tables OK")


if __name__ == "__main__":
    main()
