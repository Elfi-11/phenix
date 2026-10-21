"""Routes des comptes (un compte par utilisateur)."""
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.crud import accounts as crud_accounts
from app.database import get_db
from app.models import User
from app.schemas import AccountRead, AccountStatusUpdate
from app.security import get_current_user, require_role

router = APIRouter(prefix="/accounts", tags=["accounts"])


# Crée le compte de l'utilisateur connecté (201), ou renvoie l'existant (200)
@router.post("", response_model=AccountRead, status_code=201)
def create_account(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account, created = crud_accounts.create_for_user(db, user.id)
    if not created:
        response.status_code = 200
    return account


# Mon compte et mon solde (déclaré avant /{account_id}, sinon "me" serait lu comme un id)
@router.get("/me", response_model=AccountRead)
def my_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = crud_accounts.get_for_user(db, user.id)
    if account is None:
        raise HTTPException(status_code=404, detail="Compte introuvable")
    return account


# Propriétaire ou ADMIN ; 404 dans les deux cas d'échec pour ne pas révéler les comptes des autres
@router.get("/{account_id}", response_model=AccountRead)
def read_account(
    account_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = crud_accounts.get_by_id(db, account_id)
    if account is None or (account.user_id != user.id and user.role != "ADMIN"):
        raise HTTPException(status_code=404, detail="Compte introuvable")
    return account


# Gel / dégel réservé aux ADMIN (un compte gelé ne peut plus payer ni recevoir)
@router.patch("/{account_id}/status", response_model=AccountRead)
def change_account_status(
    account_id: int,
    data: AccountStatusUpdate,
    admin: User = Depends(require_role("ADMIN")),
    db: Session = Depends(get_db),
):
    try:
        return crud_accounts.update_status(db, account_id, data.status)
    except crud_accounts.AccountError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
