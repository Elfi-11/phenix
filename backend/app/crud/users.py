"""Accès base de données pour les utilisateurs."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from app.schemas import UserCreate
from app.security import hash_password


def get_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(User.username == username))


def create_user(db: Session, data: UserCreate) -> User:
    """Crée un utilisateur CLIENT. Lève IntegrityError si le username est déjà pris."""
    user = User(username=data.username, password_hash=hash_password(data.password), role="CLIENT")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
