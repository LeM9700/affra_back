import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    """Client financier : créé automatiquement à la PREMIÈRE facture d'un lead (jamais à l'acceptation d'un devis).

    Les coordonnées de facturation sont les dernières utilisées ; chaque facture en garde son propre instantané.
    """

    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    lead_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leads.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    billing_name: Mapped[str] = mapped_column(String(200), nullable=False)
    billing_address_line1: Mapped[str] = mapped_column(String(200), nullable=False)
    billing_address_line2: Mapped[str | None] = mapped_column(String(200))
    billing_postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    billing_city: Mapped[str] = mapped_column(String(100), nullable=False)
    billing_country: Mapped[str] = mapped_column(String(60), nullable=False, default="France")
    billing_email: Mapped[str | None] = mapped_column(String(254))
    billing_siret: Mapped[str | None] = mapped_column(String(14))
    billing_vat_number: Mapped[str | None] = mapped_column(String(20))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class InvoiceSequence(Base):
    """Compteur annuel de numérotation automatique (FA-AAAA-NNNN), incrémenté atomiquement."""

    __tablename__ = "invoice_sequences"

    year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class CustomerInvoice(Base):
    """Facture émise. Immuable (trigger SQL) : pas d'UPDATE ni de DELETE.

    total_ht_cents est la base de calcul de la commission.
    seller_snapshot / billing_* : instantanés figés au moment de l'émission.
    """

    __tablename__ = "customer_invoices"
    __table_args__ = (
        Index("ix_customer_invoices_customer_date", "customer_id", "invoice_date"),
        Index("ix_customer_invoices_invoice_date", "invoice_date"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_number: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_ht_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_vat_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_ttc_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)

    billing_name: Mapped[str] = mapped_column(String(200), nullable=False)
    billing_address_line1: Mapped[str] = mapped_column(String(200), nullable=False)
    billing_address_line2: Mapped[str | None] = mapped_column(String(200))
    billing_postal_code: Mapped[str] = mapped_column(String(10), nullable=False)
    billing_city: Mapped[str] = mapped_column(String(100), nullable=False)
    billing_country: Mapped[str] = mapped_column(String(60), nullable=False)
    billing_email: Mapped[str | None] = mapped_column(String(254))
    billing_siret: Mapped[str | None] = mapped_column(String(14))
    billing_vat_number: Mapped[str | None] = mapped_column(String(20))

    seller_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payment_terms: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    # Points d'extension V2 (webhook / import CSV / API logiciel de facturation).
    external_reference: Mapped[str | None] = mapped_column(String(100))
    source_system: Mapped[str] = mapped_column(String(30), nullable=False, default="MANUAL")

    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)

    lines: Mapped[list["InvoiceLine"]] = relationship(
        order_by="InvoiceLine.position", lazy="raise", cascade="save-update"
    )


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(20))
    unit_price_ht_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vat_rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)  # points de base : 2000 = 20 %
    total_ht_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Commission(Base):
    """Une commission par facture (invoice_id UNIQUE), calculée sur le seul montant HT de CETTE facture.

    Montants figés (trigger SQL) ; seuls status / paid_* / attribution_decision_id évoluent.
    """

    __tablename__ = "commissions"
    __table_args__ = (Index("ix_commissions_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_invoices.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    invoice_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    number_of_brackets: Mapped[int] = mapped_column(Integer, nullable=False)
    commission_amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # Décision d'attribution qui justifie le statut courant de la commission.
    attribution_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attribution_decisions.id", ondelete="RESTRICT")
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    paid_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
