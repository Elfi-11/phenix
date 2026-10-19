"""Schémas Pydantic : formats des requêtes (…Create / …Update) et des réponses (…Read) de l'API."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress, computed_field

Role = Literal["CLIENT", "MERCHANT", "ADMIN"]
AccountStatus = Literal["ACTIVE", "FROZEN"]
TransactionStatus = Literal["PENDING", "SUCCESS", "FAILED", "REJECTED_FRAUD"]
EventType = Literal["AUTH_FAILURE", "WAF_BLOCK", "ML_ANOMALY_DETECTED", "REMEDIATION_TRIGGERED"]
Severity = Literal["INFO", "WARNING", "CRITICAL"]

# Montant : positif, 2 décimales max, tient dans NUMERIC(12, 2)
Amount = Field(gt=0, max_digits=12, decimal_places=2)


class ReadModel(BaseModel):
    """Base des schémas de réponse : construits directement depuis les objets SQLAlchemy."""

    model_config = ConfigDict(from_attributes=True)


# --- Auth / utilisateurs -------------------------------------------------------------------------


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    # bcrypt ne prend en compte que les 72 premiers octets
    password: str = Field(min_length=8, max_length=72)
    # Pas de champ `role` : un utilisateur ne choisit pas son rôle (attribué côté serveur, CLIENT par défaut)


class LoginRequest(BaseModel):
    # Pas de contraintes de format : un login invalide doit renvoyer 401, pas 422 (ne rien révéler des règles)
    username: str = Field(max_length=50)
    password: str = Field(max_length=72)


class UserRead(ReadModel):
    id: int
    username: str
    role: Role
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"


class TokenPayload(BaseModel):
    """Contenu du JWT une fois décodé."""

    sub: str  # username
    role: Role
    exp: int


# --- Comptes -------------------------------------------------------------------------------------


class AccountRead(ReadModel):
    id: int
    user_id: int
    balance: Decimal
    status: AccountStatus
    updated_at: datetime


class AccountStatusUpdate(BaseModel):
    """Gel / dégel d'un compte (réservé admin ou moteur de remédiation)."""

    status: AccountStatus


# --- Transactions --------------------------------------------------------------------------------


class TransactionCreate(BaseModel):
    # Généré par le client (ex: UUID) et renvoyé tel quel en cas de retry
    idempotency_key: str = Field(min_length=8, max_length=64)
    # À vérifier côté serveur : le compte émetteur doit appartenir à l'utilisateur connecté
    sender_account_id: int
    receiver_account_id: int
    amount: Decimal = Amount
    # Pas de `client_ip` ni de `status` : déterminés par le serveur, jamais par le client


class TransactionRead(ReadModel):
    id: uuid.UUID
    idempotency_key: str
    sender_account_id: int
    receiver_account_id: int
    amount: Decimal
    status: TransactionStatus
    client_ip: IPvAnyAddress | None
    created_at: datetime


# --- Incidents (ML, WAF, remédiation, dashboard) -------------------------------------------------


class IncidentCreate(BaseModel):
    event_type: EventType
    severity: Severity
    source: str = Field(max_length=20)  # ML, WAF, AUTH...
    target_service: str | None = Field(default=None, max_length=50)
    description: str


class IncidentResolve(BaseModel):
    """Envoyé par le moteur de remédiation une fois le service rétabli et vérifié."""

    action_taken: str


class IncidentRead(ReadModel):
    id: int
    event_type: EventType
    severity: Severity
    source: str
    target_service: str | None
    description: str
    action_taken: str | None
    detected_at: datetime
    resolved_at: datetime | None

    @computed_field
    @property
    def recovery_seconds(self) -> float | None:
        """Temps de reprise réel, à comparer au RTO défini dans le PCA/PRA."""
        if self.resolved_at is None:
            return None
        return (self.resolved_at - self.detected_at).total_seconds()
