"""Incidents relevés par les services ML et remédiation."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Incident
from app.schemas import IncidentCreate


# Erreur métier, convertie en réponse HTTP par le router
class IncidentError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def create_incident(db: Session, data: IncidentCreate) -> Incident:
    incident = Incident(**data.model_dump())  # detected_at rempli par la base
    db.add(incident)
    db.commit()
    db.refresh(incident)
    return incident


# Du plus récent au plus ancien ; only_open=True pour les incidents non résolus
def list_incidents(db: Session, only_open: bool = False, limit: int = 100) -> list[Incident]:
    query = select(Incident).order_by(Incident.detected_at.desc(), Incident.id.desc()).limit(limit)
    if only_open:
        query = query.where(Incident.resolved_at.is_(None))
    return list(db.scalars(query).all())


# Un incident ne se résout qu'une fois : sinon le temps de reprise serait faussé
def resolve_incident(db: Session, incident_id: int, action_taken: str) -> Incident:
    incident = db.get(Incident, incident_id)
    if incident is None:
        raise IncidentError(404, "Incident introuvable")
    if incident.resolved_at is not None:
        raise IncidentError(409, "Incident déjà résolu")

    incident.resolved_at = datetime.now(timezone.utc)
    incident.action_taken = action_taken
    db.commit()
    db.refresh(incident)
    return incident
