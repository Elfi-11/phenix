"""Route volontairement vulnérable, construite pour la démonstration du workshop.
Ne fait pas partie de l'application métier : sert uniquement de cible d'attaque."""
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.security import get_current_user

router = APIRouter(prefix="/attackme", tags=["attackme (demo workshop)"])


# Recherche de transactions par statut — construite sans paramètres liés, exprès.
@router.get("/search")
def search_transactions(
    q: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Vulnérable par construction : démonstration d'injection SQL du workshop RESILIENCE-ALPHA
    sql = f"SELECT * FROM transactions WHERE status = '{q}'"
    return db.execute(text(sql)).mappings().all()