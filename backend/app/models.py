import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('CLIENT', 'MERCHANT', 'ADMIN', 'SERVICE')", name="ck_users_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True)
    # Hash bcrypt/argon2 stocké en base (jamais le mot de passe en clair)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="CLIENT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_accounts_balance_positive"),
        CheckConstraint("status IN ('ACTIVE', 'FROZEN')", name="ck_accounts_status"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    # Un seul compte par utilisateur, garanti par la base (choix de conception du prototype)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), unique=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_transactions_amount_positive"),
        CheckConstraint("sender_account_id <> receiver_account_id", name="ck_transactions_distinct_accounts"),
        CheckConstraint(
            "status IN ('PENDING', 'SUCCESS', 'FAILED', 'REJECTED_FRAUD')", name="ck_transactions_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Fourni par le client : un même paiement renvoyé (retry pendant/après incident) n'est débité qu'une fois
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    sender_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    receiver_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    # PENDING = paiement commencé mais pas finalisé (repérable s'il a été interrompu par un incident)
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    client_ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Incident(Base):
    """Suivi des incidents pour le dashboard. Les logs de sécurité bruts restent dans Loki (SIEM)."""

    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "event_type IN ('AUTH_FAILURE', 'WAF_BLOCK', 'ML_ANOMALY_DETECTED', 'REMEDIATION_TRIGGERED')",
            name="ck_incidents_event_type",
        ),
        CheckConstraint("severity IN ('INFO', 'WARNING', 'CRITICAL')", name="ck_incidents_severity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20))  # ML, WAF, AUTH...
    target_service: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    action_taken: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # NULL = non résolu ; resolved_at - detected_at = temps de reprise réel (comparé au RTO du PCA/PRA)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
