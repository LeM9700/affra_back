"""Enregistrement des visites et des points de contact.

Règles :
- first_* n'est écrit qu'une fois (première visite reçue) et n'est jamais écrasé ;
- last_* est mis à jour à chaque visite NON directe (« dernière source pertinente ») ;
  une visite directe ne remplace donc pas une source connue, mais initialise last_* s'il est vide ;
- client_event_id rend chaque événement idempotent (double beacon, rejeu réseau).
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.attribution import AttributionEvent, Visitor
from app.models.enums import EventType, MarketingSource
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
