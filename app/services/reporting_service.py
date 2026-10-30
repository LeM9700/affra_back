"""Lectures du dashboard interne : listes paginées (1 requête + 1 COUNT), détails, KPI SQL."""
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import Select, and_, case, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.admin_user import AdminUser
from app.models.attribution import AttributionEvent, Visitor
from app.models.billing import Commission, Customer, CustomerInvoice
from app.models.devis import Devis
from app.models.enums import CommissionStatus, EventType, FinancialAttribution
from app.models.lead import AttributionDecision, Lead
from app.services.billing_service import vat_breakdown

# Pages vues comprises : un parcours actif dépasse vite la centaine d'événements.
LEAD_EVENTS_LIMIT = 300
VISITOR_EVENTS_LIMIT = 500


async def _paginate(db: AsyncSession, query: Select, limit: int, offset: int) -> tuple[list, int]:
    total = (await db.execute(select(func.count()).select_from(query.order_by(None).subquery()))).scalar_one()
    rows = (await db.execute(query.limit(limit).offset(offset))).all()
    return rows, total


# ---------------------------------------------------------------- Leads


async def list_leads(
    db: AsyncSession,
    *,
    search: str | None,
    financial_attribution: str | None,
    marketing_source: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    query = (
        select(Lead, Customer.id.label("customer_id"))
        .outerjoin(Customer, Customer.lead_id == Lead.id)
        .order_by(Lead.created_at.desc())
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(
            or_(
                Lead.prenom.ilike(pattern),
                Lead.nom.ilike(pattern),
                Lead.email.ilike(pattern),
                Lead.telephone.ilike(pattern),
                Lead.ville.ilike(pattern),
            )
        )
    if financial_attribution:
        query = query.where(Lead.financial_attribution == financial_attribution)
    if marketing_source:
        query = query.where(Lead.marketing_source == marketing_source)
    if status:
        query = query.where(Lead.status == status)

    rows, total = await _paginate(db, query, limit, offset)
    return [{**_lead_dict(lead), "customer_id": customer_id} for lead, customer_id in rows], total


def _lead_dict(lead: Lead) -> dict:
    return {c.key: getattr(lead, c.key) for c in Lead.__table__.columns}


def _event_dict(e: AttributionEvent) -> dict:
    return {
        "id": e.id,
        "event_type": e.event_type,
        "source": e.source,
        "medium": e.medium,
        "campaign": e.campaign,
        "referrer": e.referrer,
        "landing_page": e.landing_page,
        "page_path": e.page_path,
        "metadata": e.event_metadata,
        "devis_id": e.devis_id,
        "created_at": e.created_at,
    }


def _touch(visitor: Visitor, prefix: str) -> dict:
    return {
        "source": getattr(visitor, f"{prefix}_source"),
        "medium": getattr(visitor, f"{prefix}_medium"),
        "campaign": getattr(visitor, f"{prefix}_campaign"),
        "referrer": getattr(visitor, f"{prefix}_referrer"),
        "landing_page": getattr(visitor, f"{prefix}_landing_page"),
    }


async def get_lead_detail(db: AsyncSession, lead_id: uuid.UUID) -> dict | None:
    lead = await db.get(Lead, lead_id)
    if lead is None:
        return None

    visitor = await db.get(Visitor, lead.visitor_id) if lead.visitor_id else None

    event_filter = AttributionEvent.lead_id == lead.id
    if visitor is not None:
        event_filter = or_(event_filter, AttributionEvent.visitor_id == visitor.id)
    events = (
        await db.execute(
            select(AttributionEvent).where(event_filter).order_by(AttributionEvent.created_at.desc()).limit(LEAD_EVENTS_LIMIT)
        )
    ).scalars().all()

    decisions = (
        await db.execute(
            select(AttributionDecision, AdminUser.email)
            .outerjoin(AdminUser, AdminUser.id == AttributionDecision.created_by)
            .where(AttributionDecision.lead_id == lead.id)
            .order_by(AttributionDecision.created_at.desc())
        )
    ).all()

    devis = (
        await db.execute(select(Devis).where(Devis.lead_id == lead.id).order_by(Devis.created_at.desc()))
    ).scalars().all()

    customer = (await db.execute(select(Customer).where(Customer.lead_id == lead.id))).scalar_one_or_none()
    invoices = []
    if customer is not None:
        invoices = (
            await db.execute(
                select(CustomerInvoice, Commission)
                .outerjoin(Commission, Commission.invoice_id == CustomerInvoice.id)
                .where(CustomerInvoice.customer_id == customer.id)
                .order_by(CustomerInvoice.invoice_date.desc(), CustomerInvoice.created_at.desc())
            )
        ).all()

    return {
        **_lead_dict(lead),
        "customer_id": customer.id if customer else None,
        "visitor": None
        if visitor is None
        else {
            "id": visitor.id,
            "first_seen_at": visitor.first_seen_at,
            "last_seen_at": visitor.last_seen_at,
            "first_touch": _touch(visitor, "first"),
            "last_touch": _touch(visitor, "last"),
            "has_google_click_id": bool(visitor.gclid or visitor.gbraid or visitor.wbraid),
        },
        "events": [_event_dict(e) for e in events],
        "decisions": [
            {
                "id": d.id,
                "decision": d.decision,
                "confidence": d.confidence,
                "previous_decision": d.previous_decision,
                "previous_confidence": d.previous_confidence,
                "reason": d.reason,
                "created_by": d.created_by,
                "created_by_email": email,
                "created_at": d.created_at,
            }
            for d, email in decisions
        ],
        "devis": devis,
        "customer": customer,
        "invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date,
                "total_ht_cents": inv.total_ht_cents,
                "total_ttc_cents": inv.total_ttc_cents,
                "commission_amount_cents": com.commission_amount_cents if com else None,
                "commission_status": com.status if com else None,
            }
            for inv, com in invoices
        ],
    }


async def list_unlinked_phone_clicks(db: AsyncSession, hours: int, limit: int) -> list[AttributionEvent]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    return list(
        (
            await db.execute(
                select(AttributionEvent)
                .where(
                    AttributionEvent.event_type == EventType.PHONE_CLICK.value,
                    AttributionEvent.lead_id.is_(None),
                    AttributionEvent.created_at >= since,
                )
                .order_by(AttributionEvent.created_at.desc())
                .limit(limit)
            )
        ).scalars()
    )


# ---------------------------------------------------------------- Prospects


ProspectKind = Literal["all", "identified", "contact"]


def _identity(visitor: Visitor) -> dict | None:
    if visitor.contact_phone is None:
        return None
    return {
        "name": visitor.contact_name,
        "phone": visitor.contact_phone,
        "consent_at": visitor.contact_consent_at,
        "identified_at": visitor.identified_at,
    }


async def list_prospects(
    db: AsyncSession,
    *,
    days: int,
    kind: ProspectKind = "all",
    search: str | None = None,
    visitor_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    """Une ligne par visiteur SANS lead, actif sur la période, du plus récent au plus ancien.

    kind :
    - « all » : tous les visiteurs (anonymes et identifiés) ;
    - « identified » : prospects identifiés (demande de rappel : nom + téléphone) ;
    - « contact » : visiteurs ayant cliqué pour nous contacter ou demandé un rappel.

    Les leads et clients n'y figurent pas : leur parcours est sur leur fiche lead.
    """
    from app.services.lead_service import CONTACT_EVENT_VALUES  # import tardif : évite un import circulaire

    ev = AttributionEvent
    since = datetime.now(timezone.utc) - timedelta(days=days)
    contact_values = (*CONTACT_EVENT_VALUES, EventType.CALLBACK_REQUESTED.value)
    is_contact = ev.event_type.in_(contact_values)
    query = (
        select(
            Visitor,
            func.max(ev.created_at).label("last_event_at"),
            func.count(ev.id).label("events_count"),
            func.count(ev.id).filter(ev.event_type == EventType.PAGE_VIEW.value).label("page_views"),
            func.count(ev.id).filter(ev.event_type == EventType.LANDING.value).label("visits"),
            func.count(ev.id).filter(ev.event_type == EventType.PHONE_CLICK.value).label("phone_clicks"),
            func.count(ev.id).filter(ev.event_type == EventType.EMAIL_CLICK.value).label("email_clicks"),
            func.count(ev.id).filter(ev.event_type == EventType.WHATSAPP_CLICK.value).label("whatsapp_clicks"),
            func.count(ev.id).filter(ev.event_type == EventType.QUOTE_STARTED.value).label("quote_started"),
            func.count(ev.id).filter(ev.event_type == EventType.CALLBACK_REQUESTED.value).label("callback_requests"),
            func.count(ev.id).filter(is_contact).label("contact_actions"),
        )
        .join(ev, ev.visitor_id == Visitor.id)
        .where(ev.created_at >= since, ~exists(select(Lead.id).where(Lead.visitor_id == Visitor.id)))
        .group_by(Visitor.id)
        .order_by(func.max(ev.created_at).desc(), Visitor.id)
    )
    if kind == "identified":
        query = query.where(Visitor.contact_phone.is_not(None))
    elif kind == "contact":
        query = query.having(func.count(ev.id).filter(is_contact) > 0)
    if search:
        term = search.strip()
        digits = "".join(ch for ch in term if ch.isdigit())
        conditions = [Visitor.contact_name.ilike(f"%{term}%")]
        if len(digits) >= 4:
            # 06 12… ou +33 6 12… : on compare sur les 9 derniers chiffres significatifs.
            conditions.append(Visitor.contact_phone.contains(digits.lstrip("0")[-9:]))
        query = query.where(or_(*conditions))
    if visitor_id:
        query = query.where(Visitor.id == visitor_id)

    rows, total = await _paginate(db, query, limit, offset)
    ids = [row[0].id for row in rows]
    last_events: dict[uuid.UUID, tuple[str, str | None]] = {}
    if ids:
        latest = await db.execute(
            select(ev.visitor_id, ev.event_type, ev.page_path)
            .where(ev.visitor_id.in_(ids))
            .distinct(ev.visitor_id)
            .order_by(ev.visitor_id, ev.created_at.desc())
        )
        last_events = {vid: (etype, page) for vid, etype, page in latest.all()}

    items = []
    for row in rows:
        visitor = row[0]
        last_type, last_page = last_events.get(visitor.id, ("", None))
        items.append(
            {
                "visitor_id": visitor.id,
                "first_seen_at": visitor.first_seen_at,
                "last_event_at": row.last_event_at,
                "last_event_type": last_type,
                "last_page_path": last_page,
                "events_count": row.events_count,
                "page_views": row.page_views,
                "visits": row.visits,
                "phone_clicks": row.phone_clicks,
                "email_clicks": row.email_clicks,
                "whatsapp_clicks": row.whatsapp_clicks,
                "quote_started": row.quote_started,
                "callback_requests": row.callback_requests,
                "contact_actions": row.contact_actions,
                "identity": _identity(visitor),
                "first_touch": _touch(visitor, "first"),
                "last_touch": _touch(visitor, "last"),
            }
        )
    return items, total


async def get_visitor_detail(db: AsyncSession, visitor_id: uuid.UUID) -> dict | None:
    """Fiche visiteur : identité, provenance, lead éventuel et chronologie complète (la plus récente d'abord)."""
    visitor = await db.get(Visitor, visitor_id)
    if visitor is None:
        return None
    lead_row = (
        await db.execute(
            select(Lead.id, Lead.status, Customer.id)
            .outerjoin(Customer, Customer.lead_id == Lead.id)
            .where(Lead.visitor_id == visitor.id)
            .order_by(Lead.created_at.desc())
            .limit(1)
        )
    ).first()
    events = (
        await db.execute(
            select(AttributionEvent)
            .where(AttributionEvent.visitor_id == visitor.id)
            .order_by(AttributionEvent.created_at.desc())
            .limit(VISITOR_EVENTS_LIMIT)
        )
    ).scalars().all()
    counts = dict(
        (
            await db.execute(
                select(AttributionEvent.event_type, func.count(AttributionEvent.id))
                .where(AttributionEvent.visitor_id == visitor.id)
                .group_by(AttributionEvent.event_type)
            )
        ).all()
    )
    return {
        "id": visitor.id,
        "first_seen_at": visitor.first_seen_at,
        "last_seen_at": visitor.last_seen_at,
        "first_touch": _touch(visitor, "first"),
        "last_touch": _touch(visitor, "last"),
        "has_google_click_id": bool(visitor.gclid or visitor.gbraid or visitor.wbraid),
        "identity": _identity(visitor),
        "lead_id": lead_row[0] if lead_row else None,
        "lead_status": lead_row[1] if lead_row else None,
        "customer_id": lead_row[2] if lead_row else None,
        "event_counts": counts,
        "events_total": sum(counts.values()),
        "events": [_event_dict(e) for e in events],
    }


# ---------------------------------------------------------------- Factures


async def get_invoice_out(db: AsyncSession, invoice_id: uuid.UUID) -> dict | None:
    row = (
        await db.execute(
            select(CustomerInvoice, Customer, Lead, Commission)
            .join(Customer, Customer.id == CustomerInvoice.customer_id)
            .join(Lead, Lead.id == Customer.lead_id)
            .outerjoin(Commission, Commission.invoice_id == CustomerInvoice.id)
            .options(selectinload(CustomerInvoice.lines))
            .where(CustomerInvoice.id == invoice_id)
        )
    ).first()
    if row is None:
        return None
    invoice, customer, lead, commission = row
    data = {c.key: getattr(invoice, c.key) for c in CustomerInvoice.__table__.columns}
    data.update(
        lead_id=lead.id,
        seller=invoice.seller_snapshot,
        lines=invoice.lines,
        vat_breakdown=vat_breakdown(invoice.lines),
        commission=commission,
        marketing_source=lead.marketing_source,
        financial_attribution=lead.financial_attribution,
    )
    return data


async def list_invoices(
    db: AsyncSession, *, search: str | None, lead_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[dict], int]:
    query = (
        select(CustomerInvoice, Customer.lead_id, Commission.commission_amount_cents, Commission.status)
        .join(Customer, Customer.id == CustomerInvoice.customer_id)
        .outerjoin(Commission, Commission.invoice_id == CustomerInvoice.id)
        .order_by(CustomerInvoice.invoice_date.desc(), CustomerInvoice.created_at.desc())
    )
    if search:
        pattern = f"%{search}%"
        query = query.where(or_(CustomerInvoice.invoice_number.ilike(pattern), CustomerInvoice.billing_name.ilike(pattern)))
    if lead_id:
        query = query.where(Customer.lead_id == lead_id)
    rows, total = await _paginate(db, query, limit, offset)
    return [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "billing_name": inv.billing_name,
            "lead_id": inv_lead_id,
            "customer_id": inv.customer_id,
            "total_ht_cents": inv.total_ht_cents,
            "total_ttc_cents": inv.total_ttc_cents,
            "commission_amount_cents": amount,
            "commission_status": com_status,
        }
        for inv, inv_lead_id, amount, com_status in rows
    ], total


# ---------------------------------------------------------------- Commissions


async def list_commissions(
    db: AsyncSession, *, status: str | None, limit: int, offset: int
) -> tuple[list[dict], int]:
    query = (
        select(Commission, CustomerInvoice, Lead)
        .join(CustomerInvoice, CustomerInvoice.id == Commission.invoice_id)
        .join(Customer, Customer.id == CustomerInvoice.customer_id)
        .join(Lead, Lead.id == Customer.lead_id)
        .order_by(CustomerInvoice.invoice_date.desc(), Commission.created_at.desc())
    )
    if status:
        query = query.where(Commission.status == status)
    rows, total = await _paginate(db, query, limit, offset)
    return [
        {
            "id": com.id,
            "invoice_id": inv.id,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "customer_name": inv.billing_name,
            "lead_id": lead.id,
            "marketing_source": lead.marketing_source,
            "financial_attribution": lead.financial_attribution,
            "invoice_amount_cents": com.invoice_amount_cents,
            "number_of_brackets": com.number_of_brackets,
            "commission_amount_cents": com.commission_amount_cents,
            "status": com.status,
            "paid_at": com.paid_at,
        }
        for com, inv, lead in rows
    ], total


# ---------------------------------------------------------------- KPI


async def compute_stats(db: AsyncSession, date_from: date | None, date_to: date | None) -> dict:
    """Agrégations SQL. Le périmètre « attribué » = commissions non annulées (une par facture AFFRA_DIGITAL).

    date_from / date_to filtrent les leads sur created_at et les factures sur invoice_date.
    """
    affra = FinancialAttribution.AFFRA_DIGITAL.value

    lead_filters = []
    if date_from:
        lead_filters.append(Lead.created_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc))
    if date_to:
        lead_filters.append(
            Lead.created_at < datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
        )

    lead_row = (
        await db.execute(
            select(
                func.count(Lead.id),
                func.count(Lead.id).filter(Lead.financial_attribution == affra),
                func.count(Lead.id).filter(Lead.financial_attribution == FinancialAttribution.DISPUTED.value),
            ).where(*lead_filters)
        )
    ).one()

    by_source = (
        await db.execute(
            select(Lead.marketing_source, func.count(Lead.id))
            .where(*lead_filters)
            .group_by(Lead.marketing_source)
            .order_by(func.count(Lead.id).desc())
        )
    ).all()

    invoice_filters = [Commission.status != CommissionStatus.CANCELLED.value]
    if date_from:
        invoice_filters.append(CustomerInvoice.invoice_date >= date_from)
    if date_to:
        invoice_filters.append(CustomerInvoice.invoice_date <= date_to)

    com_row = (
        await db.execute(
            select(
                func.coalesce(func.sum(Commission.invoice_amount_cents), 0),
                func.count(Commission.id),
                func.coalesce(func.sum(Commission.number_of_brackets), 0),
                func.coalesce(func.sum(Commission.commission_amount_cents), 0),
                func.coalesce(
                    func.sum(case((Commission.status == CommissionStatus.DUE.value, Commission.commission_amount_cents), else_=0)), 0
                ),
                func.coalesce(
                    func.sum(case((Commission.status == CommissionStatus.PAID.value, Commission.commission_amount_cents), else_=0)), 0
                ),
                func.count(func.distinct(CustomerInvoice.customer_id)),
            )
            .join(CustomerInvoice, CustomerInvoice.id == Commission.invoice_id)
            .where(and_(*invoice_filters))
        )
    ).one()

    return {
        "leads_total": lead_row[0],
        "leads_digital": lead_row[1],
        "leads_to_arbitrate": lead_row[2],
        "customers_digital": com_row[6],
        "invoiced_attributed_ht_cents": int(com_row[0]),
        "invoices_attributed": com_row[1],
        "brackets_total": int(com_row[2]),
        "commission_total_cents": int(com_row[3]),
        "commission_due_cents": int(com_row[4]),
        "commission_paid_cents": int(com_row[5]),
        "leads_by_source": [{"source": s, "count": c} for s, c in by_source],
    }
