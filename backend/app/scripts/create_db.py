"""Lancé à chaque démarrage du conteneur, avant Uvicorn : doit rester idempotent."""

from decimal import Decimal

import bcrypt
from sqlalchemy import func, select

from app.config import settings
from app.database import Base, SessionLocal, engine
from app.models import Account, User

# Comptes fictifs de démonstration : (username, rôle, solde initial ; None = pas de compte bancaire)
DEMO_USERS = [
    ("alice_client", "CLIENT", Decimal("1500.00")),
    ("bob_client", "CLIENT", Decimal("800.00")),
    ("marchand_beta", "MERCHANT", Decimal("0.00")),
    ("admin", "ADMIN", None),
    ("service_remediation", "SERVICE", None),
    # Compte dédié à la transaction de test automatique (gros solde : ne s'épuise pas) ; garder en dernier (le marchand reste id 3)
    ("selftest_client", "CLIENT", Decimal("1000000.00")),
]


def seed_demo_data():
    """Crée les utilisateurs et comptes de démo, uniquement si la table users est vide."""
    if not settings.demo_user_password:
        print("create_db: DEMO_USER_PASSWORD absent, pas de données de démo")
        return

    with SessionLocal() as db:
        if db.scalar(select(func.count()).select_from(User)):
            print("create_db: données de démo déjà présentes")
            return

        password_hash = bcrypt.hashpw(settings.demo_user_password.encode(), bcrypt.gensalt()).decode()
        for username, role, balance in DEMO_USERS:
            user = User(username=username, password_hash=password_hash, role=role)
            db.add(user)
            if balance is not None:
                db.flush()  # récupère user.id pour le compte
                db.add(Account(user_id=user.id, balance=balance))
        db.commit()
        print(f"create_db: {len(DEMO_USERS)} utilisateurs de démo créés")


def main():
    Base.metadata.create_all(bind=engine)
    print("create_db: tables OK")
    seed_demo_data()


if __name__ == "__main__":
    main()
