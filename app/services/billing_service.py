"""Factures, clients et commissions.

Lead → (1re facture) → Customer : le Customer est créé automatiquement à la première facture,
puis réutilisé. Tout se passe dans la transaction de la requête (get_db) : en cas d'erreur,
aucun Customer / facture / commission partiel ne subsiste.

Commission : créée à l'émission d'une facture si la décision en vigueur du lead est
AFFRA_DIGITAL ; une facture < 1 000 € HT donne une commission NOT_DUE de 0 € (conservée pour l'audit).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import Commission, Customer, CustomerInvoice, InvoiceLine, InvoiceSequence
from app.models.enums import CommissionStatus, FinancialAttribution, LeadStatus
from app.models.lead import AttributionDecision, Lead
from app.schemas.billing import InvoiceCreate, InvoiceLineIn
from app.services.commission import compute_commission

DEFAULT_PAYMENT_DAYS = 30


class BillingError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class InvoiceTotals:
    line_totals_ht: list[int]
    vat_by_rate: dict[int, tuple[int, int]]  # rate_bp -> (base_ht, vat)
    total_ht_cents: int
    total_vat_cents: int
    total_ttc_cents: int


def _round_cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def compute_invoice_totals(lines: list[InvoiceLineIn]) -> InvoiceTotals:
    """Arithmétique Decimal uniquement. TVA calculée par taux sur la base HT cumulée du taux."""
    line_totals = [_round_cents(Decimal(line.quantity) * line.unit_price_ht_cents) for line in lines]
    bases: dict[int, int] = {}
    for line, total in zip(lines, line_totals):
        bases[line.vat_rate_bp] = bases.get(line.vat_rate_bp, 0) + total
    vat_by_rate = {
        rate: (base, _round_cents(Decimal(base) * rate / Decimal(10_000))) for rate, base in sorted(bases.items())
    }
    total_ht = sum(line_totals)
    total_vat = sum(vat for _, vat in vat_by_rate.values())
    return InvoiceTotals(line_totals, vat_by_rate, total_ht, total_vat, total_ht + total_vat)


def _status_for(amount_cents: int) -> CommissionStatus:
    return CommissionStatus.DUE if amount_cents > 0 else CommissionStatus.NOT_DUE


def build_commission(invoice: CustomerInvoice, decision_id: uuid.UUID | None) -> Commission:
    computation = compute_commission(invoice.total_ht_cents)
    return Commission(
        invoice_id=invoice.id,
        invoice_amount_cents=computation.invoice_amount_cents,
        number_of_brackets=computation.number_of_brackets,
        commission_amount_cents=computation.commission_amount_cents,
        status=_status_for(computation.commission_amount_cents).value,
        attribution_decision_id=decision_id,
    )


async def _next_invoice_number(db: AsyncSession, year: int) -> str:
    for _ in range(20):
        stmt = (
            pg_insert(InvoiceSequence)
            .values(year=year, last_value=1)
            .on_conflict_do_update(
                index_elements=[InvoiceSequence.year],
                set_={"last_value": InvoiceSequence.last_value + 1},
            )
            .returning(InvoiceSequence.last_value)
        )
        value = (await db.execute(stmt)).scalar_one()
        number = f"FA-{year}-{value:04d}"
        if not await _invoice_number_exists(db, number):
            return number
    raise BillingError("Impossible d'attribuer un numéro de facture", 409)


async def _invoice_number_exists(db: AsyncSession, number: str) -> bool:
    found = await db.execute(select(CustomerInvoice.id).where(CustomerInvoice.invoice_number == number))
    return found.first() is not None


async def create_invoice_for_lead(
    db: AsyncSession, lead_id: uuid.UUID, payload: InvoiceCreate, admin_id: uuid.UUID | None
) -> tuple[CustomerInvoice, Customer, Commission | None, bool]:
    # Verrou sur le lead : deux premières factures simultanées ne créent pas deux Customers.
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id).with_for_update())).scalar_one_or_none()
    if lead is None:
        raise BillingError("Lead introuvable", 404)

    totals = compute_invoice_totals(payload.lines)
    if totals.total_ht_cents <= 0:
        raise BillingError("Le montant HT de la facture doit être strictement positif", 422)

    billing = payload.billing
    customer = (await db.execute(select(Customer).where(Customer.lead_id == lead.id))).scalar_one_or_none()
    customer_created = customer is None
    if customer is None:
        customer = Customer(lead_id=lead.id, created_by=admin_id)
        db.add(customer)
    customer.billing_name = billing.name
    customer.billing_address_line1 = billing.address_line1
    customer.billing_address_line2 = billing.address_line2
    customer.billing_postal_code = billing.postal_code
    customer.billing_city = billing.city
    customer.billing_country = billing.country
    customer.billing_email = str(billing.email) if billing.email else None
    customer.billing_siret = billing.siret
    customer.billing_vat_number = billing.vat_number
    await db.flush()

    if payload.invoice_number:
        if await _invoice_number_exists(db, payload.invoice_number):
            raise BillingError(f"Le numéro de facture {payload.invoice_number} existe déjà", 409)
        number = payload.invoice_number
    else:
        number = await _next_invoice_number(db, payload.invoice_date.year)

    invoice = CustomerInvoice(
        customer_id=customer.id,
        invoice_number=number,
        invoice_date=payload.invoice_date,
        service_date=payload.service_date,
        due_date=payload.due_date or payload.invoice_date + timedelta(days=DEFAULT_PAYMENT_DAYS),
        total_ht_cents=totals.total_ht_cents,
        total_vat_cents=totals.total_vat_cents,
        total_ttc_cents=totals.total_ttc_cents,
        billing_name=billing.name,
        billing_address_line1=billing.address_line1,
        billing_address_line2=billing.address_line2,
        billing_postal_code=billing.postal_code,
        billing_city=billing.city,
        billing_country=billing.country,
        billing_email=str(billing.email) if billing.email else None,
        billing_siret=billing.siret,
        billing_vat_number=billing.vat_number,
        seller_snapshot=settings.seller_snapshot(),
        payment_terms=payload.payment_terms,
        notes=payload.notes,
        external_reference=payload.external_reference,
        created_by=admin_id,
    )
    db.add(invoice)
    try:
        await db.flush()
    except IntegrityError as exc:  # course sur le numéro (contrainte UNIQUE)
        raise BillingError(f"Le numéro de facture {number} existe déjà", 409) from exc

    for position, (line, total) in enumerate(zip(payload.lines, totals.line_totals_ht), start=1):
        db.add(
            InvoiceLine(
                invoice_id=invoice.id,
                position=position,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price_ht_cents=line.unit_price_ht_cents,
                vat_rate_bp=line.vat_rate_bp,
                total_ht_cents=total,
            )
        )

    commission = None
    if lead.financial_attribution == FinancialAttribution.AFFRA_DIGITAL.value:
        commission = build_commission(invoice, lead.current_decision_id)
        db.add(commission)

    lead.status = LeadStatus.CLIENT.value
    await db.flush()
    return invoice, customer, commission, customer_created


async def sync_commissions_for_lead(db: AsyncSession, lead: Lead, decision: AttributionDecision) -> None:
    """Applique une nouvelle décision aux factures déjà émises du lead.

    → AFFRA_DIGITAL : crée les commissions manquantes, réactive les commissions annulées.
    → autre         : annule les commissions DUE / NOT_DUE. Une commission PAID n'est jamais modifiée.
    """
    rows = (
        await db.execute(
            select(CustomerInvoice, Commission)
            .join(Customer, Customer.id == CustomerInvoice.customer_id)
            .outerjoin(Commission, Commission.invoice_id == CustomerInvoice.id)
            .where(Customer.lead_id == lead.id)
            .with_for_update(of=CustomerInvoice.__table__)
        )
    ).all()

    to_affra = decision.decision == FinancialAttribution.AFFRA_DIGITAL.value
    for invoice, commission in rows:
        if to_affra:
            if commission is None:
                db.add(build_commission(invoice, decision.id))
            elif commission.status == CommissionStatus.CANCELLED.value:
                commission.status = _status_for(commission.commission_amount_cents).value
                commission.attribution_decision_id = decision.id
        elif commission is not None and commission.status in (CommissionStatus.DUE.value, CommissionStatus.NOT_DUE.value):
            commission.status = CommissionStatus.CANCELLED.value
            commission.attribution_decision_id = decision.id
    await db.flush()


async def mark_commission_paid(db: AsyncSession, commission_id: uuid.UUID, admin_id: uuid.UUID) -> Commission:
    commission = (
        await db.execute(select(Commission).where(Commission.id == commission_id).with_for_update())
    ).scalar_one_or_none()
    if commission is None:
        raise BillingError("Commission introuvable", 404)
    if commission.status != CommissionStatus.DUE.value:
        raise BillingError(f"Seule une commission DUE peut être payée (statut actuel : {commission.status})", 409)
    commission.status = CommissionStatus.PAID.value
    commission.paid_at = datetime.now(timezone.utc)
    commission.paid_by = admin_id
    await db.flush()
    return commission


def vat_breakdown(lines: list[InvoiceLine]) -> list[dict[str, int]]:
    """Ventilation TVA d'une facture enregistrée (recalculée depuis les lignes figées)."""
    bases: dict[int, int] = {}
    for line in lines:
        bases[line.vat_rate_bp] = bases.get(line.vat_rate_bp, 0) + line.total_ht_cents
    return [
        {"vat_rate_bp": rate, "base_ht_cents": base, "vat_cents": _round_cents(Decimal(base) * rate / Decimal(10_000))}
        for rate, base in sorted(bases.items())
    ]
