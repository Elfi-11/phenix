"""Routes des incidents : écrites par les services (SERVICE), lues par le dashboard (ADMIN)."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.crud import incidents as crud_incidents
from app.database import get_db
from app.models import User
from app.schemas import IncidentCreate, IncidentRead, IncidentResolve
from app.security import require_role

router = APIRouter(prefix="/incidents", tags=["incidents"])


# Le ML ou le moteur de remédiation signale une anomalie
@router.post("", response_model=IncidentRead, status_code=201)
def create_incident(
    data: IncidentCreate,
    service: User = Depends(require_role("SERVICE")),
    db: Session = Depends(get_db),
):
    return crud_incidents.create_incident(db, data)


# Dashboard : tous les incidents, ou seulement les ouverts (?only_open=true)
@router.get("", response_model=list[IncidentRead])
def list_incidents(
    only_open: bool = False,
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_role("ADMIN", "SERVICE")),
    db: Session = Depends(get_db),
):
    return crud_incidents.list_incidents(db, only_open, limit)


# Le moteur de remédiation déclare le service rétabli ; le temps de reprise est calculé
@router.patch("/{incident_id}/resolve", response_model=IncidentRead)
def resolve_incident(
    incident_id: int,
    data: IncidentResolve,
    service: User = Depends(require_role("SERVICE")),
    db: Session = Depends(get_db),
):
    try:
        return crud_incidents.resolve_incident(db, incident_id, data.action_taken)
    except crud_incidents.IncidentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc