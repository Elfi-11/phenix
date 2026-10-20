"""Routes HTTP des comptes et contrôle des droits d'accès."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.crud import accounts as crud_accounts
from app.database import get_db
from app.models import User
from app.schemas import AccountRead, AccountStatusUpdate
from app.security import get_current_user, require_role


# main.py ajoute le préfixe /api : ces routes deviennent /api/accounts.
router = APIRouter(prefix="/accounts", tags=["accounts"])


# Crée le compte de l'utilisateur identifié par son JWT.
# Aucun corps de requête : le propriétaire et le solde sont fixés côté serveur.
@router.post("", response_model=AccountRead, status_code=201)
def create_account(
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        account, created = crud_accounts.create_for_user(db, user.id)
    except crud_accounts.AccountError as exc:
        # Convertit une erreur métier du CRUD en réponse HTTP explicite.
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    # 201 : nouveau compte ; 200 : compte déjà existant, renvoyé sans modification.
    if not created:
        response.status_code = 200

    return account


# Retourne le compte de l'utilisateur connecté, notamment pour lire son solde.
# Déclarer /me avant /{account_id} évite que "me" soit interprété comme un entier.
@router.get("/me", response_model=AccountRead)
def my_account(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        account = crud_accounts.get_for_user(db, user.id)
    except crud_accounts.AccountError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc

    # Un utilisateur inscrit n'a pas nécessairement déjà créé son compte.
    if account is None:
        raise HTTPException(status_code=404, detail="Compte introuvable")

    return account


# Consultation par identifiant : réservée au propriétaire ou à un administrateur.
@router.get("/{account_id}", response_model=AccountRead)
def read_account(
    account_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = crud_accounts.get_by_id(db, account_id)

    # Même réponse pour un compte absent ou inaccessible :
    # on ne révèle pas l'existence du compte d'un autre utilisateur.
    if account is None or (
        account.user_id != user.id and user.role != "ADMIN"
    ):
        raise HTTPException(status_code=404, detail="Compte introuvable")

    return account


# Gel/dégel réservé aux administrateurs.
# AccountStatusUpdate accepte uniquement ACTIVE ou FROZEN.
# Les routes de paiement refusent les nouveaux paiements impliquant un compte gelé.
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
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc