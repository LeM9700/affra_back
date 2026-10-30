"""Enregistrement des visites et des points de contact.

Règles :
- first_* n'est écrit qu'une fois (première visite reçue) et n'est jamais écrasé ;
- last_* est mis à jour à chaque visite NON directe (« dernière source pertinente ») ;
  une visite directe ne remplace donc pas une source connue, mais initialise last_* s'il est vide ;
- client_event_id rend chaque événement idempotent (double beacon, rejeu réseau).
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attribution import AttributionEvent, Visitor
from app.models.enums import EventType, MarketingSource
from app.models.lead import Lead
from app.services.attribution_classifier import (
    Classification,
    TouchSignals,
    classify,
    sanitize_page_path,
    sanitize_referrer,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def get_or_create_visitor(db: AsyncSession, anonymous_id: uuid.UUID, *, lock: bool = True) -> Visitor:
    """INSERT … ON CONFLICT DO NOTHING puis SELECT (FOR UPDATE) : sûr en cas de requêtes concurrentes."""
    now = _now()
    await db.execute(
        pg_insert(Visitor)
        .values(id=uuid.uuid4(), anonymous_id=anonymous_id, first_seen_at=now, last_seen_at=now, created_at=now, updated_at=now)
        .on_conflict_do_nothing(index_elements=[Visitor.anonymous_id])
    )
    query = select(Visitor).where(Visitor.anonymous_id == anonymous_id).execution_options(populate_existing=True)
    if lock:
        query = query.with_for_update()
    return (await db.execute(query)).scalar_one()


async def find_visitor(db: AsyncSession, anonymous_id: uuid.UUID | None) -> Visitor | None:
    if anonymous_id is None:
        return None
    return (await db.execute(select(Visitor).where(Visitor.anonymous_id == anonymous_id))).scalar_one_or_none()


def apply_touch(visitor: Visitor, classification: Classification, referrer: str | None, landing_page: str | None) -> None:
    """Met à jour first/last touch d'un visiteur (fonction pure sur l'objet, testable)."""
    if visitor.first_source is None:
        visitor.first_source = classification.source.value
        visitor.first_medium = classification.medium
        visitor.first_campaign = classification.campaign
        visitor.first_referrer = referrer
        visitor.first_landing_page = landing_page

    if visitor.last_source is None or not classification.is_direct_or_unknown:
        visitor.last_source = classification.source.value
        visitor.last_medium = classification.medium
        visitor.last_campaign = classification.campaign
        visitor.last_referrer = referrer
        visitor.last_landing_page = landing_page


async def _insert_event(db: AsyncSession, values: dict[str, Any]) -> bool:
    """Insère un événement ; False si client_event_id déjà connu (idempotence)."""
    values.setdefault("id", uuid.uuid4())
    values.setdefault("created_at", _now())
    values.setdefault("event_metadata", {})  # attribut ORM (colonne SQL : "metadata")
    stmt = pg_insert(AttributionEvent).values(**values)
    if values.get("client_event_id") is not None:
        stmt = stmt.on_conflict_do_nothing(index_elements=["client_event_id"])
    result = await db.execute(stmt.returning(AttributionEvent.id))
    return result.scalar_one_or_none() is not None


async def record_visit(
    db: AsyncSession,
    *,
    anonymous_id: uuid.UUID,
    signals: TouchSignals,
    client_event_id: uuid.UUID | None = None,
) -> Visitor:
    referrer = sanitize_referrer(signals.referrer)
    landing_page = sanitize_page_path(signals.landing_page)
    classification = classify(signals, settings.site_hosts_set)

    visitor = await get_or_create_visitor(db, anonymous_id)
    apply_touch(visitor, classification, referrer, landing_page)
    visitor.last_seen_at = _now()
    if signals.gclid:
        visitor.gclid = signals.gclid
    if signals.gbraid:
        visitor.gbraid = signals.gbraid
    if signals.wbraid:
        visitor.wbraid = signals.wbraid
    await db.flush()

    await _insert_event(
        db,
        {
            "client_event_id": client_event_id,
            "visitor_id": visitor.id,
            "event_type": EventType.LANDING.value,
            "source": classification.source.value,
            "medium": classification.medium,
            "campaign": classification.campaign,
            "referrer": referrer,
            "landing_page": landing_page,
            "page_path": sanitize_page_path(signals.landing_page, keep_query=False),
        },
    )
    return visitor


async def record_event(
    db: AsyncSession,
    *,
    event_type: EventType,
    visitor: Visitor | None,
    client_event_id: uuid.UUID | None = None,
    page_path: str | None = None,
    metadata: dict[str, Any] | None = None,
    lead_id: uuid.UUID | None = None,
    devis_id: uuid.UUID | None = None,
) -> bool:
    """Événement attribué au last-touch courant du visiteur (UNKNOWN si aucun)."""
    if visitor is not None:
        visitor.last_seen_at = _now()
    return await _insert_event(
        db,
        {
            "client_event_id": client_event_id,
            "visitor_id": visitor.id if visitor else None,
            "lead_id": lead_id,
            "devis_id": devis_id,
            "event_type": event_type.value,
            "source": (visitor.last_source if visitor and visitor.last_source else MarketingSource.UNKNOWN.value),
            "medium": visitor.last_medium if visitor else None,
            "campaign": visitor.last_campaign if visitor else None,
            "referrer": visitor.last_referrer if visitor else None,
            "landing_page": visitor.last_landing_page if visitor else None,
            "page_path": sanitize_page_path(page_path, keep_query=False),
            "event_metadata": metadata or {},
        },
    )


async def link_visitor_events_to_lead(db: AsyncSession, visitor_id: uuid.UUID, lead_id: uuid.UUID) -> None:
    """Rattache au lead l'historique des événements encore orphelins de ce visiteur."""
    await db.execute(
        update(AttributionEvent)
        .where(AttributionEvent.visitor_id == visitor_id, AttributionEvent.lead_id.is_(None))
        .values(lead_id=lead_id)
    )


# Nombre de pages récentes reprises dans l'alerte Telegram d'une demande de rappel.
CALLBACK_RECENT_PAGES = 5


@dataclass(frozen=True)
class CallbackSummary:
    """Instantané d'une demande de rappel, pour la notification envoyée après le commit."""

    visitor_id: uuid.UUID
    name: str
    phone: str
    source: str | None
    first_source: str | None
    recent_pages: list[str]
    page_views: int
    lead_id: uuid.UUID | None
    created: bool


async def record_callback_request(
    db: AsyncSession,
    *,
    anonymous_id: uuid.UUID,
    client_event_id: uuid.UUID,
    name: str,
    phone_e164: str,
    page_path: str | None,
) -> CallbackSummary:
    """Le visiteur demande à être rappelé : il devient un prospect identifié (pas un lead).

    - l'identité la plus récente remplace la précédente (le visiteur a pu corriger son numéro) ;
    - la date de consentement est celle de la demande ;
    - un événement CALLBACK_REQUESTED est ajouté au parcours (idempotent via client_event_id) ;
    - si le visiteur est déjà un lead, son téléphone est complété sans jamais être écrasé.

    Args:
        db: Session de la requête.
        anonymous_id: Valeur du cookie affra_vid.
        client_event_id: Identifiant unique de la demande (rejeu réseau sans doublon).
        name: Nom validé.
        phone_e164: Téléphone normalisé (+33…).
        page_path: Page d'où la demande a été envoyée.

    Returns:
        Le résumé à notifier ; `created` vaut False si la demande avait déjà été reçue.
    """
    now = _now()
    visitor = await get_or_create_visitor(db, anonymous_id)
    visitor.contact_name = name
    visitor.contact_phone = phone_e164
    visitor.contact_consent_at = now
    visitor.identified_at = visitor.identified_at or now
    await db.flush()

    created = await record_event(
        db,
        event_type=EventType.CALLBACK_REQUESTED,
        visitor=visitor,
        client_event_id=client_event_id,
        page_path=page_path,
    )

    lead = (
        await db.execute(select(Lead).where(Lead.visitor_id == visitor.id).order_by(Lead.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    if lead is not None and not lead.telephone:
        lead.telephone = phone_e164
        await db.flush()

    pages = (
        await db.execute(
            select(AttributionEvent.page_path)
            .where(
                AttributionEvent.visitor_id == visitor.id,
                AttributionEvent.event_type == EventType.PAGE_VIEW.value,
                AttributionEvent.page_path.is_not(None),
            )
            .order_by(AttributionEvent.created_at.desc())
            .limit(CALLBACK_RECENT_PAGES)
        )
    ).scalars().all()
    page_views = await db.scalar(
        select(func.count(AttributionEvent.id)).where(
            AttributionEvent.visitor_id == visitor.id, AttributionEvent.event_type == EventType.PAGE_VIEW.value
        )
    )
    return CallbackSummary(
        visitor_id=visitor.id,
        name=name,
        phone=phone_e164,
        source=visitor.last_source,
        first_source=visitor.first_source,
        recent_pages=list(pages),
        page_views=page_views or 0,
        lead_id=lead.id if lead else None,
        created=created,
    )
