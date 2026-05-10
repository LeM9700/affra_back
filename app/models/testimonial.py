import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Testimonial(Base):
    __tablename__ = "testimonials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    initiales: Mapped[str] = mapped_column(String(10), nullable=False)
    ville: Mapped[str] = mapped_column(String(100), nullable=False)
    departement: Mapped[str] = mapped_column(String(3), nullable=False)
    type_client: Mapped[str] = mapped_column(String(30), nullable=False)
    type_projet: Mapped[str | None] = mapped_column(String(120))
    resultat: Mapped[str | None] = mapped_column(String(160))
    temoignage: Mapped[str] = mapped_column(Text, nullable=False)
    source_channel: Mapped[str] = mapped_column(String(30), default="formulaire_web")
    consent_publication: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=_now)
