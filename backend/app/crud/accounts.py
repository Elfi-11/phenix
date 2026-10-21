"""Accès à la base : création, consultation et statut des comptes (un compte par utilisateur)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Account


# Erreur métier, convertie en réponse HTTP par le router
class AccountError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# Les droits de consultation sont vérifiés dans le router
def get_by_id(db: Session, account_id: int) -> Account | None:
    return db.get(Account, account_id)


# user_id est UNIQUE en base : au plus un compte
def get_for_user(db: Session, user_id: int) -> Account | None:
    return db.scalar(select(Account).where(Account.user_id == user_id))


# Renvoie (compte, True si créé à l'instant)
def create_for_user(db: Session, user_id: int) -> tuple[Account, bool]:
    account = get_for_user(db, user_id)
    if account is not None:
        return account, False

    # Solde et statut fixés côté serveur : le client ne peut pas s'attribuer d'argent
    account = Account(user_id=user_id, balance=Decimal("0.00"), status="ACTIVE")
    db.add(account)
    try:
        db.commit()
    except IntegrityError:
        # Deux créations simultanées : la contrainte UNIQUE a refusé la seconde, on renvoie l'existant
        db.rollback()
        return get_for_user(db, user_id), False
    return account, True


# Gel / dégel (ADMIN vérifié dans le router), sans toucher au solde
def update_status(
    db: Session,
    account_id: int,
    new_status: str,
) -> Account:
    try:
        # Verrou de ligne partagé avec les paiements ; populate_existing force la relecture en base
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
