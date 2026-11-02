import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InvoiceDocument(Base):
    """Facture émise hors du dashboard puis importée (PDF / image), en attente de revue ou confirmée.

    Le fichier d'origine est conservé tel quel dans le stockage R2 (clé `storage_key`), identifié par
    son empreinte SHA-256 : preuve en cas de désaccord, et refus d'un même fichier importé deux fois.
    `extraction` = données lues ; `analysis` = contrôles à l'import ; `confirmation` = données validées
    par l'humain, contrôles finaux et motifs des avertissements acceptés.
    """

    __tablename__ = "invoice_documents"
    __table_args__ = (Index("ix_invoice_documents_lead_created", "lead_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_invoices.id", ondelete="RESTRICT"), unique=True
    )
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING_REVIEW")
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False)
    extraction: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    analysis: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    confirmation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT")
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
