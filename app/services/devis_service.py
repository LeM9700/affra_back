import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attribution import Visitor
from app.models.devis import Devis
from app.models.enums import EventType
from app.models.lead import Lead
from app.schemas.devis import DevisCreate
from app.services import attribution_service, lead_service
from app.services.email_service import send_operator_notification, send_prospect_confirmation
from app.services.sheets_service import append_devis_to_sheet

logger = logging.getLogger(__name__)


async def _attach_attribution(
    db: AsyncSession, devis: Devis, anonymous_id: uuid.UUID | None
) -> tuple[Lead | None, Visitor | None]:
    """Devis → Visitor → Lead + événement QUOTE_SUBMITTED.

    Isolé dans un SAVEPOINT : un échec d'attribution ne doit jamais faire échouer la demande de devis.
    """
    try:
        async with db.begin_nested():
            visitor = await attribution_service.get_or_create_visitor(db, anonymous_id) if anonymous_id else None
            lead = await lead_service.attach_devis_to_lead(db, devis, visitor)
            await attribution_service.record_event(
                db,
                event_type=EventType.QUOTE_SUBMITTED,
                visitor=visitor,
                lead_id=lead.id,
                devis_id=devis.id,
                page_path="/devis",
            )
        return lead, visitor
    except Exception:
        logger.exception("Attribution failed for devis id=%s — devis kept without lead", devis.id)
        await db.refresh(devis)  # objets expirés par le rollback du savepoint
        return None, None


async def create_devis(db: AsyncSession, payload: DevisCreate) -> Devis:
    devis = Devis(
        type_client=payload.type_client,
        possede_vehicule=payload.possede_vehicule,
        distance_quotidienne=payload.distance_quotidienne,
        delai=payload.delai,
        distance_tableau=payload.distance_tableau,
        prenom=payload.prenom,
        email=str(payload.email),
        telephone=payload.telephone,
        ville=payload.ville,
        rgpd_consent_at=datetime.now(timezone.utc),
    )
    db.add(devis)
    await db.flush()

    lead, visitor = await _attach_attribution(db, devis, payload.anonymous_id)

    # Send emails + Google Sheets (best-effort — don't block on failure)
    try:
        await send_operator_notification(devis)
        await send_prospect_confirmation(devis)
    except Exception:
        pass  # Logged by email_service

    try:
        await append_devis_to_sheet(devis, lead=lead, visitor=visitor)
    except Exception:
        pass  # Logged by sheets_service

    return devis
