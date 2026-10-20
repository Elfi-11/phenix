"""Routes d'authentification : inscription, connexion (JWT), utilisateur courant."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crud import users as crud_users
from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, Token, UserCreate, UserRead
from app.security import authenticate_user, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

# Les échecs de connexion partent dans les logs du conteneur → Promtail → Loki (règles SIEM brute force)
logger = logging.getLogger("phenix.auth")


def _client_ip(request: Request) -> str | None:
    # Nginx transmet l'IP d'origine dans X-Real-IP
    return request.headers.get("x-real-ip") or (request.client.host if request.client else None)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if crud_users.get_by_username(db, data.username) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nom d'utilisateur déjà pris")
    try:
        return crud_users.create_user(db, data)
    except IntegrityError:  # deux inscriptions simultanées avec le même username
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Nom d'utilisateur déjà pris")


@router.post("/login", response_model=Token)
def login(data: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.username, data.password)
    if user is None:
        logger.warning("AUTH_FAILURE username=%s ip=%s", data.username, _client_ip(request))
        # Même message que l'utilisateur existe ou non (ne pas révéler les usernames valides)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiants invalides",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=create_access_token(user))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)):
    return user
