"""Paiements atomiques et lecture des transactions de l'utilisateur."""
import uuid
from decimal import Decimal

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from app.models import Account, Transaction
from app.schemas import TransactionCreate

# Plafond imposé par la colonne NUMERIC(12, 2)
MAX_BALANCE = Decimal("9999999999.99")


# Erreur métier, convertie en réponse HTTP par le router
class PaymentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


# Transactions où le compte de l'utilisateur est émetteur ou destinataire
def _visible(user_id: int):
    my_account = select(Account.id).where(Account.user_id == user_id)
    return or_(Transaction.sender_account_id.in_(my_account), Transaction.receiver_account_id.in_(my_account))


def list_for_user(db: Session, user_id: int, offset: int = 0, limit: int = 50):
    query = (
        select(Transaction)
        .where(_visible(user_id))
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return db.scalars(query).all()


def get_for_user(db: Session, transaction_id: uuid.UUID, user_id: int):
    return db.scalar(select(Transaction).where(Transaction.id == transaction_id, _visible(user_id)))


# Renvoie (transaction, True si créée à l'instant). Débit, crédit et enregistrement en un seul commit.
def create_payment(db: Session, data: TransactionCreate, user_id: int, client_ip: str | None = None):
    try:
        # Émetteur = compte unique de l'utilisateur connecté, jamais choisi par le client
        sender_id = db.scalar(select(Account.id).where(Account.user_id == user_id))
        if sender_id is None:
            raise PaymentError(404, "Vous n'avez pas de compte")
        if sender_id == data.receiver_account_id:
            raise PaymentError(422, "Les comptes émetteur et destinataire doivent être distincts")

        # Verrou par clé d'idempotence : deux envois simultanés du même paiement passent l'un après l'autre
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "phenix.payment:" + data.idempotency_key},
        )

        # Paiement déjà fait avec cette clé (retry) : renvoyé tel quel, pas de second débit
        existing = db.scalar(select(Transaction).where(Transaction.idempotency_key == data.idempotency_key))
        if existing is not None:
            same = (
                existing.sender_account_id == sender_id
                and existing.receiver_account_id == data.receiver_account_id
                and existing.amount == data.amount
            )
            if not same:
                raise PaymentError(409, "Clé d'idempotence déjà utilisée pour une autre opération")
            db.commit()  # libère le verrou
            return existing, False

        # Verrou des deux comptes (par id croissant pour éviter les interblocages)
        accounts = db.scalars(
            select(Account)
            .where(Account.id.in_([sender_id, data.receiver_account_id]))
            .order_by(Account.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        by_id = {account.id: account for account in accounts}
        sender = by_id[sender_id]
        receiver = by_id.get(data.receiver_account_id)

        if receiver is None:
            raise PaymentError(404, "Compte destinataire introuvable")
        if sender.status != "ACTIVE" or receiver.status != "ACTIVE":
            raise PaymentError(409, "Un des comptes est gelé")
        if sender.balance < data.amount:
            raise PaymentError(409, "Solde insuffisant")
        if receiver.balance + data.amount > MAX_BALANCE:
            raise PaymentError(409, "Plafond du solde destinataire dépassé")

        sender.balance -= data.amount
        receiver.balance += data.amount
        payment = Transaction(
            idempotency_key=data.idempotency_key,
            sender_account_id=sender.id,
            receiver_account_id=receiver.id,
            amount=data.amount,
            status="SUCCESS",
            client_ip=client_ip,
        )
        db.add(payment)
        db.commit()
        return payment, True
    except Exception:
        db.rollback()  # tout ou rien : aucun débit sans crédit
        raise
