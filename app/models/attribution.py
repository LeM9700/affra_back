import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Visitor(Base):
    """Navigateur identifié par le cookie first-party `affra_vid` (UUID aléatoire, aucune donnée personnelle).

    first_* : posé à la première visite connue, jamais écrasé ensuite.
    last_*  : dernière source pertinente (une visite DIRECT n'écrase pas une source connue).
    first_source est NULL tant qu'aucune visite n'a été reçue (visiteur créé par un événement).
    """

    __tablename__ = "visitors"
    __table_args__ = (Index("ix_visitors_last_seen_at", "last_seen_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    anonymous_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), unique=True, nullable=False)

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    first_source: Mapped[str | None] = mapped_column(String(30))
    first_medium: Mapped[str | None] = mapped_column(String(100))
    first_campaign: Mapped[str | None] = mapped_column(String(150))
    first_referrer: Mapped[str | None] = mapped_column(String(500))
    first_landing_page: Mapped[str | None] = mapped_column(String(500))

    last_source: Mapped[str | None] = mapped_column(String(30))
    last_medium: Mapped[str | None] = mapped_column(String(100))
    last_campaign: Mapped[str | None] = mapped_column(String(150))
    last_referrer: Mapped[str | None] = mapped_column(String(500))
    last_landing_page: Mapped[str | None] = mapped_column(String(500))

    gclid: Mapped[str | None] = mapped_column(String(255))
    gbraid: Mapped[str | None] = mapped_column(String(255))
    wbraid: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class AttributionEvent(Base):
    """Journal append-only des points de contact (touchpoints).

    source/medium/campaign = source attribuée au moment de l'événement (classification serveur
    pour LANDING, last-touch du visiteur pour les autres).
    """

    __tablename__ = "attribution_events"
    __table_args__ = (
        Index("ix_attribution_events_visitor_created", "visitor_id", "created_at"),
        Index("ix_attribution_events_type_created", "event_type", "created_at"),
        Index("ix_attribution_events_lead_id", "lead_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Idempotence : UUID généré par le navigateur pour chaque événement (rejeu / double beacon).
    client_event_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), unique=True)

    visitor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("visitors.id", ondelete="CASCADE")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"))
    devis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("devis.id", ondelete="SET NULL"))

    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    medium: Mapped[str | None] = mapped_column(String(100))
    campaign: Mapped[str | None] = mapped_column(String(150))
    referrer: Mapped[str | None] = mapped_column(String(500))
    landing_page: Mapped[str | None] = mapped_column(String(500))
    page_path: Mapped[str | None] = mapped_column(String(500))

    # "metadata" est réservé par SQLAlchemy Declarative → attribut event_metadata, colonne "metadata".
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
