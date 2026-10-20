"""Paiements atomiques PostgreSQL et lecture limitée aux participants."""
import uuid
from decimal import Decimal

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.models import Account, Transaction
from app.schemas import TransactionCreate


class PaymentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def _visible(user_id: int):
    accounts = select(Account.id).where(Account.user_id == user_id)
    return or_(Transaction.sender_account_id.in_(accounts), Transaction.receiver_account_id.in_(accounts))


def list_for_user(db: Session, user_id: int, offset: int = 0, limit: int = 50):
    return db.scalars(select(Transaction).where(_visible(user_id)).order_by(
        Transaction.created_at.desc(), Transaction.id.desc()
    ).offset(offset).limit(limit)).all()


def get_for_user(db: Session, transaction_id: uuid.UUID, user_id: int):
    return db.scalar(select(Transaction).where(Transaction.id == transaction_id, _visible(user_id)))


def create_payment(db: Session, data: TransactionCreate, user_id: int, client_ip: str | None = None):
    """Possède le commit/rollback de la session de requête ; aucune écriture préalable attendue.

    Le verrou consultatif sérialise une même clé, même pour deux émetteurs différents
    (la contrainte existante est globale). Les comptes sont verrouillés par id croissant.
    Le moteur PostgreSQL doit conserver son isolation READ COMMITTED par défaut.
    """
    try:
        if data.sender_account_id == data.receiver_account_id:
            raise PaymentError(422, "Les comptes émetteur et destinataire doivent être distincts")
        # Paramètres liés : aucune concaténation de données utilisateur dans le SQL.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": "phenix.payment:" + data.idempotency_key})
        sender_owner = db.scalar(select(Account.user_id).where(Account.id == data.sender_account_id))
        if sender_owner != user_id:
            raise PaymentError(403, "Compte émetteur non autorisé")
        existing = db.scalar(select(Transaction).where(Transaction.idempotency_key == data.idempotency_key))
        if existing is not None:
            if (existing.sender_account_id != data.sender_account_id
                    or existing.receiver_account_id != data.receiver_account_id
                    or existing.amount != data.amount):
                raise PaymentError(409, "Clé d'idempotence déjà utilisée pour une autre opération")
            db.commit()  # libère le verrou ; aucune nouvelle écriture
            return existing, False
        accounts = db.scalars(select(Account).where(Account.id.in_(
            [data.sender_account_id, data.receiver_account_id]
        )).order_by(Account.id).with_for_update().execution_options(populate_existing=True)).all()
        by_id = {account.id: account for account in accounts}
        sender = by_id.get(data.sender_account_id)
        receiver = by_id.get(data.receiver_account_id)
        # Revérifie le propriétaire après acquisition du verrou.
        if sender is None or sender.user_id != user_id:
            raise PaymentError(403, "Compte émetteur non autorisé")
        if receiver is None:
            raise PaymentError(404, "Compte destinataire introuvable")
        if sender.status != "ACTIVE" or receiver.status != "ACTIVE":
            raise PaymentError(409, "Un des comptes est gelé")
        if sender.balance < data.amount:
            raise PaymentError(409, "Solde insuffisant")
        if receiver.balance + data.amount > Decimal("9999999999.99"):
            raise PaymentError(409, "Plafond du solde destinataire dépassé")
        sender.balance -= data.amount
        receiver.balance += data.amount
        payment = Transaction(idempotency_key=data.idempotency_key,
                              sender_account_id=sender.id, receiver_account_id=receiver.id,
                              amount=data.amount, status="SUCCESS", client_ip=client_ip)
        db.add(payment)
        db.commit()  # débit, crédit et transaction validés ensemble
        return payment, True
    except Exception:
        db.rollback()
        raise