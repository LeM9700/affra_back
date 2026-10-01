import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import LeadStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Lead(Base):
    """Prospect, indépendant du canal (formulaire, téléphone…). Un devis est optionnel.

    marketing_* : instantané de la source au moment de la création du lead (le last-touch du
    visiteur continue d'évoluer ensuite ; le first-touch reste lisible via visitor).

    financial_attribution / attribution_confidence : décision financière COURANTE. Ces colonnes ne
    sont modifiées que par lead_service.record_decision(), qui journalise dans attribution_decisions.
    """

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_created_at", "created_at"),
        Index("ix_leads_financial_attribution", "financial_attribution"),
        Index("ix_leads_email_lower", text("lower(email)")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitors.id", ondelete="SET NULL"), index=True
    )

    prenom: Mapped[str | None] = mapped_column(String(100))
    nom: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254))
    telephone: Mapped[str | None] = mapped_column(String(20))
    ville: Mapped[str | None] = mapped_column(String(100))

    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    marketing_source: Mapped[str] = mapped_column(String(30), nullable=False)
    marketing_medium: Mapped[str | None] = mapped_column(String(100))
    marketing_campaign: Mapped[str | None] = mapped_column(String(150))

    financial_attribution: Mapped[str] = mapped_column(String(20), nullable=False)
    attribution_confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    current_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attribution_decisions.id", ondelete="SET NULL", use_alter=True)
    )

    status: Mapped[str] = mapped_column(String(20), default=LeadStatus.NOUVEAU.value, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class AttributionDecision(Base):
    """Journal append-only des décisions d'attribution financière (trigger SQL anti-UPDATE).

    created_by NULL = décision automatique du système (création du lead).
    """

    __tablename__ = "attribution_decisions"
    __table_args__ = (Index("ix_attribution_decisions_lead_created", "lead_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_decision: Mapped[str | None] = mapped_column(String(20))
    previous_confidence: Mapped[str | None] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
