"""Relais du statut de la transaction de test automatique (réservé ADMIN)."""
import json
import urllib.request

from fastapi import APIRouter, Depends

from app.config import settings
from app.security import require_role

router = APIRouter(prefix="/selftest", tags=["selftest"], dependencies=[Depends(require_role("ADMIN"))])


# Dernier résultat du paiement de test : { ok, http_status, at, detail }
@router.get("")
def selftest_status():
    try:
        with urllib.request.urlopen(f"{settings.selftest_url}/status", timeout=3) as res:
            return json.load(res)
    except Exception:
        # Le service de test est lui-même injoignable : état inconnu
        return {"ok": None, "http_status": None, "at": None, "detail": "service de test indisponible"}
