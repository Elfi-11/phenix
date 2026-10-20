"""Mots de passe (bcrypt), tokens JWT et dépendances d'authentification FastAPI."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User
from app.schemas import Role, TokenPayload

# Lit l'en-tête "Authorization: Bearer <token>" (et ajoute le bouton "Authorize" dans Swagger)
bearer_scheme = HTTPBearer(auto_error=False)

# Hash factice : utilisé quand l'utilisateur n'existe pas, pour que le login prenne
# le même temps dans tous les cas (empêche de deviner les usernames existants)
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt()).decode()


# --- Mots de passe -------------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:  # hash mal formé en base
        return False


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    """Renvoie l'utilisateur si username + mot de passe sont corrects, sinon None."""
    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


# --- JWT -----------------------------------------------------------------------------------------


def create_access_token(user: User) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": user.username, "role": user.role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Lève jwt.InvalidTokenError (signature, expiration…) ou ValidationError (contenu inattendu)."""
    data = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    return TokenPayload(**data)


# --- Dépendances FastAPI -------------------------------------------------------------------------

_unauthorized = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentification requise ou token invalide",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """À mettre sur toute route protégée : `user: User = Depends(get_current_user)`."""
    if credentials is None:
        raise _unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
    except (jwt.InvalidTokenError, ValidationError):
        raise _unauthorized

    # On relit l'utilisateur en base : un compte supprimé ne doit plus pouvoir utiliser son token
    user = db.scalar(select(User).where(User.username == payload.sub))
    if user is None:
        raise _unauthorized
    return user


def require_role(*roles: Role):
    """Restreint une route à certains rôles : `Depends(require_role("ADMIN"))`."""

    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès refusé")
        return user

    return checker
