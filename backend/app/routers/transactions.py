"""Routes de paiement et consultation des transactions de l'utilisateur."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.crud import transactions as crud_transactions
from app.database import get_db
from app.models import User
from app.schemas import TransactionCreate, TransactionRead
from app.security import get_current_user

router = APIRouter(prefix="/transactions", tags=["transactions"])


# Payer : 201 si nouveau paiement, 200 si la même clé a déjà été traitée (retry)
@router.post("", response_model=TransactionRead, status_code=201)
def create_transaction(
    data: TransactionCreate,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        # IP client non enregistrée tant que la vraie IP derrière le WAF n'est pas fiable
        payment, created = crud_transactions.create_payment(db, data, user.id, client_ip=None)
    except crud_transactions.PaymentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Conflit de données : paiement non enregistré") from exc
    except OperationalError as exc:
        # Base injoignable (ex. pendant un incident) : le client peut réessayer avec la même clé
        raise HTTPException(status_code=503, detail="Base indisponible ; réessayer avec la même clé") from exc
    if not created:
        response.status_code = 200
    return payment


# Mon historique, du plus récent au plus ancien
@router.get("", response_model=list[TransactionRead])
def list_transactions(
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud_transactions.list_for_user(db, user.id, offset, limit)


# 404 si la transaction n'existe pas ou ne me concerne pas
@router.get("/{transaction_id}", response_model=TransactionRead)
def get_transaction(
    transaction_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    payment = crud_transactions.get_for_user(db, transaction_id, user.id)
    if payment is None:
        raise HTTPException(status_code=404, detail="Transaction introuvable")
    return payment
