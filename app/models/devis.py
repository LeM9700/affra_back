import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Devis(Base):
    __tablename__ = "devis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Questionnaire IRVE
    type_client: Mapped[str | None] = mapped_column(String(50))       # maison|copropriete|entreprise
    possede_vehicule: Mapped[str | None] = mapped_column(String(50))  # oui|pas_encore|livraison_prochaine
    distance_quotidienne: Mapped[str | None] = mapped_column(String(30))  # 0_50|50_150|plus_150
    delai: Mapped[str | None] = mapped_column(String(30))             # rapidement|un_deux_mois|pas_urgent
    distance_tableau: Mapped[str | None] = mapped_column(String(30))  # 0_5m|5_15m|plus_15m|ne_sait_pas
    # Coordonnées
    prenom: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254))
    telephone: Mapped[str | None] = mapped_column(String(20))
    ville: Mapped[str | None] = mapped_column(String(100))
    # Gestion interne
    statut: Mapped[str] = mapped_column(String(30), default="nouveau")
    rgpd_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    subvention_type: Mapped[str | None] = mapped_column(String(30))
    subvention_statut: Mapped[str | None] = mapped_column(String(30))
    # Attribution : le devis est rattaché à un Lead (qui porte le Visitor et la décision financière).
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="SET NULL"), index=True
    )
