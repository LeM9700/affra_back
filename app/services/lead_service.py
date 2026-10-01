"""Leads et décisions d'attribution financière.

Décision initiale automatique (created_by = NULL, « système ») :
- parcours digital enregistré (first OU last touch ∈ sources digitales) → AFFRA_DIGITAL / SUPPORTED ;
- sinon (direct, inconnu, pas de cookie)                               → DISPUTED (« à arbitrer ») / UNKNOWN.

Toute modification ultérieure passe par record_decision() : une nouvelle ligne est ajoutée à
attribution_decisions (append-only), jamais d'écrasement silencieux.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attribution import AttributionEvent, Visitor
from app.models.devis import Devis
from app.models.enums import (
    DIGITAL_SOURCES,
    AttributionConfidence,
    EventType,
    FinancialAttribution,
    LeadChannel,
    MarketingSource,
)
from app.models.lead import AttributionDecision, Lead
from app.schemas.lead import LeadCreate
from app.services import attribution_service, billing_service


class LeadError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def initial_decision(visitor: Visitor | None) -> tuple[FinancialAttribution, AttributionConfidence, str]:
    if visitor is not None:
        touches = [s for s in (visitor.first_source, visitor.last_source) if s]
        digital = [s for s in touches if MarketingSource(s) in DIGITAL_SOURCES]
        if digital:
            return (
                FinancialAttribution.AFFRA_DIGITAL,
                AttributionConfidence.SUPPORTED,
                f"Automatique : parcours digital enregistré (first touch {visitor.first_source or '—'}, "
                f"last touch {visitor.last_source or '—'}).",
            )
        return (
            FinancialAttribution.DISPUTED,
            AttributionConfidence.UNKNOWN,
            f"Automatique : aucune source digitale identifiable (first touch {visitor.first_source or '—'}, "
            f"last touch {visitor.last_source or '—'}). Arbitrage manuel requis.",
        )
    return (
        FinancialAttribution.DISPUTED,
        AttributionConfidence.UNKNOWN,
        "Automatique : aucun identifiant visiteur (affra_vid) associé. Arbitrage manuel requis.",
    )


async def record_decision(
    db: AsyncSession,
    lead: Lead,
    decision: FinancialAttribution,
    confidence: AttributionConfidence,
    reason: str,
    created_by: uuid.UUID | None,
) -> AttributionDecision:
    is_initial = lead.current_decision_id is None
    if not is_initial and lead.financial_attribution == decision.value and lead.attribution_confidence == confidence.value:
        raise LeadError("Décision identique à la décision en vigueur", 409)

    entry = AttributionDecision(
        lead_id=lead.id,
        decision=decision.value,
        confidence=confidence.value,
        previous_decision=None if is_initial else lead.financial_attribution,
        previous_confidence=None if is_initial else lead.attribution_confidence,
        reason=reason,
        created_by=created_by,
    )
    db.add(entry)
    await db.flush()

    lead.financial_attribution = decision.value
    lead.attribution_confidence = confidence.value
    lead.current_decision_id = entry.id
    await db.flush()

    if not is_initial:
        await billing_service.sync_commissions_for_lead(db, lead, entry)
    return entry


async def _create_lead(
    db: AsyncSession,
    *,
    visitor: Visitor | None,
    channel: LeadChannel,
    decision: tuple[FinancialAttribution, AttributionConfidence, str],
    created_by: uuid.UUID | None,
    marketing_source: str | None = None,
    **contact: str | None,
) -> Lead:
    financial, confidence, reason = decision
    lead = Lead(
        visitor_id=visitor.id if visitor else None,
        channel=channel.value,
        marketing_source=marketing_source
        or (visitor.last_source if visitor and visitor.last_source else MarketingSource.UNKNOWN.value),
        marketing_medium=visitor.last_medium if visitor else None,
        marketing_campaign=visitor.last_campaign if visitor else None,
        financial_attribution=financial.value,
        attribution_confidence=confidence.value,
        **contact,
    )
    db.add(lead)
    await db.flush()
    await record_decision(db, lead, financial, confidence, reason, created_by)
    if visitor is not None:
        await attribution_service.link_visitor_events_to_lead(db, visitor.id, lead.id)
    return lead


async def attach_devis_to_lead(db: AsyncSession, devis: Devis, visitor: Visitor | None) -> Lead:
    """Rattache un devis au lead existant de même email, sinon crée le lead (canal FORM)."""
    existing = (
        await db.execute(
            select(Lead)
            .where(func.lower(Lead.email) == devis.email.lower())
            .order_by(Lead.created_at.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if existing is not None:
        lead = existing
        # Complète sans jamais écraser ; la décision financière en vigueur n'est pas modifiée.
        if lead.visitor_id is None and visitor is not None:
            lead.visitor_id = visitor.id
        lead.telephone = lead.telephone or devis.telephone
        lead.ville = lead.ville or devis.ville
        lead.prenom = lead.prenom or devis.prenom
        if visitor is not None:
            await attribution_service.link_visitor_events_to_lead(db, visitor.id, lead.id)
    else:
        lead = await _create_lead(
            db,
            visitor=visitor,
            channel=LeadChannel.FORM,
            decision=initial_decision(visitor),
            created_by=None,
            prenom=devis.prenom,
            email=devis.email,
            telephone=devis.telephone,
            ville=devis.ville,
        )

    devis.lead_id = lead.id
    await db.flush()
    return lead


async def create_manual_lead(db: AsyncSession, payload: LeadCreate, admin_id: uuid.UUID) -> Lead:
    visitor: Visitor | None = None
    click: AttributionEvent | None = None
    if payload.phone_click_event_id:
        click = (
            await db.execute(
                select(AttributionEvent).where(AttributionEvent.id == payload.phone_click_event_id).with_for_update()
            )
        ).scalar_one_or_none()
        if click is None or click.event_type != EventType.PHONE_CLICK.value:
            raise LeadError("Clic téléphone introuvable", 404)
        if click.lead_id is not None:
            raise LeadError("Ce clic téléphone est déjà rattaché à un lead", 409)
        if click.visitor_id:
            visitor = await db.get(Visitor, click.visitor_id)

    observed = (visitor.last_source if visitor else None) or (click.source if click else None)
    if observed and observed != MarketingSource.UNKNOWN.value:
        marketing_source = observed
    else:
        marketing_source = (payload.declared_source or MarketingSource.UNKNOWN).value

    lead = await _create_lead(
        db,
        visitor=visitor,
        channel=payload.channel,
        decision=(payload.financial_attribution, payload.attribution_confidence, payload.reason),
        created_by=admin_id,
        marketing_source=marketing_source,
        prenom=payload.prenom,
        nom=payload.nom,
        email=str(payload.email) if payload.email else None,
        telephone=payload.telephone,
        ville=payload.ville,
        notes=payload.notes,
    )
    if click is not None:
        click.lead_id = lead.id
        await db.flush()
    return lead
