"""Endpoints publics d'attribution (appelés par le proxy Next.js, jamais directement par le navigateur).

- X-API-Key obligatoire (comme tous les endpoints /api/v1) ;
- corps limité à MAX_BODY_BYTES, schémas stricts (extra=forbid), metadata bornée ;
- rate limit par IP visiteur (X-Client-IP posé par le serveur Next.js) ;
- idempotents via client_event_id ;
- la source est toujours classée côté serveur ; aucun champ financier n'est accepté.
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key
from app.middleware.rate_limit import (
    check_attribution_rate_limit,
    check_callback_rate_limit,
    get_client_ip,
)
from app.models.enums import EventType
from app.schemas.attribution import AttributionAck, CallbackIn, EventIn, VisitIn
from app.services import attribution_service
from app.services.attribution_classifier import TouchSignals
from app.services.notification_service import notify_callback_request

MAX_BODY_BYTES = 4096


async def limit_body_size(request: Request) -> None:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")
    # Corps réel (chunked / content-length mensonger) — Starlette le met en cache pour la validation.
    if len(await request.body()) > MAX_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Payload too large")


async def rate_limit(request: Request) -> None:
    await check_attribution_rate_limit(get_client_ip(request))


router = APIRouter(dependencies=[Depends(verify_api_key), Depends(limit_body_size), Depends(rate_limit)])


@router.post("/visit", response_model=AttributionAck, status_code=status.HTTP_202_ACCEPTED)
async def record_visit(payload: VisitIn, db: AsyncSession = Depends(get_db)):
    await attribution_service.record_visit(
        db,
        anonymous_id=payload.anonymous_id,
        client_event_id=payload.client_event_id,
        signals=TouchSignals(
            utm_source=payload.utm_source,
            utm_medium=payload.utm_medium,
            utm_campaign=payload.utm_campaign,
            referrer=payload.referrer,
            landing_page=payload.landing_page,
            gclid=payload.gclid,
            gbraid=payload.gbraid,
            wbraid=payload.wbraid,
        ),
    )
    return AttributionAck()


@router.post("/event", response_model=AttributionAck, status_code=status.HTTP_202_ACCEPTED)
async def record_event(payload: EventIn, db: AsyncSession = Depends(get_db)):
    visitor = await attribution_service.get_or_create_visitor(db, payload.anonymous_id)
    await attribution_service.record_event(
        db,
        event_type=EventType(payload.event_type),
        visitor=visitor,
        client_event_id=payload.client_event_id,
        page_path=payload.page_path,
        metadata=payload.metadata,
    )
    return AttributionAck()


@router.post("/callback", response_model=AttributionAck, status_code=status.HTTP_202_ACCEPTED)
async def request_callback(
    request: Request,
    payload: CallbackIn,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Bouton « Être appelé » : le visiteur devient un prospect identifié (nom + téléphone), pas un lead."""
    await check_callback_rate_limit(get_client_ip(request))
    summary = await attribution_service.record_callback_request(
        db,
        anonymous_id=payload.anonymous_id,
        client_event_id=payload.client_event_id,
        name=payload.nom,
        phone_e164=payload.telephone,
        page_path=payload.page_path,
    )
    # Après le commit de get_db : on ne notifie que des demandes réellement enregistrées.
    background_tasks.add_task(notify_callback_request, summary)
    return AttributionAck()
