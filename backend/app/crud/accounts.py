"""Accès à la base : création, consultation et statut des comptes."""

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Account


# Erreur métier transmise au router, qui la convertira en réponse HTTP.
class AccountError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# Recherche par identifiant.
# Les droits de consultation sont contrôlés dans le router.
def get_by_id(db: Session, account_id: int) -> Account | None:
    return db.get(Account, account_id)


# Le fonctionnement retenu prévoit un compte par utilisateur.
# On signale les doublons plutôt que de choisir arbitrairement un compte.
def get_for_user(db: Session, user_id: int) -> Account | None:
    accounts = db.scalars(
        select(Account).where(Account.user_id == user_id)
    ).all()

    if len(accounts) > 1:
        raise AccountError(
            409,
            "Plusieurs comptes existent pour cet utilisateur",
        )

    return accounts[0] if accounts else None


# Création du compte de l'utilisateur connecté.
# Le booléen indique au router si le compte vient d'être créé.
def create_for_user(db: Session, user_id: int) -> tuple[Account, bool]:
    try:
        # Verrou PostgreSQL conservé jusqu'au commit ou au rollback.
        # Deux appels simultanés pour le même utilisateur sont traités
        # successivement, pour éviter de créer deux comptes par cette fonction.
        db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtextextended(:key, 0))"
            ),
            {"key": f"phenix.account:{user_id}"},
        )

        # Si le compte existe déjà, on le retourne sans le modifier.
        # Le commit libère le verrou, même sans nouvelle écriture.
        account = get_for_user(db, user_id)

        if account is not None:
            db.commit()
            return account, False

        # Le propriétaire, le solde initial et le statut sont fixés
        # côté serveur : le client ne peut pas s'attribuer de l'argent.
        account = Account(
            user_id=user_id,
            balance=Decimal("0.00"),
            status="ACTIVE",
        )
        db.add(account)
        db.commit()
        return account, True

    except Exception:
        # Annule les écritures éventuelles et libère le verrou.
        db.rollback()
        raise


# Modification administrative du statut, sans toucher au solde.
# Le router vérifie le rôle ADMIN et le schéma valide le nouveau statut.
def update_status(
    db: Session,
    account_id: int,
    new_status: str,
) -> Account:
    try:
        # Le verrou de ligne coordonne le changement de statut avec
        # les paiements, qui verrouillent également les comptes.
        # populate_existing recharge les valeurs même si le compte
        # était déjà présent dans la session SQLAlchemy.
        account = db.scalar(
            select(Account)
            .where(Account.id == account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        if account is None:
            raise AccountError(404, "Compte introuvable")

        account.status = new_status
        db.commit()
        return account

    except Exception:
        db.rollback()
        raise