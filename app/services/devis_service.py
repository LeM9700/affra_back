from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.devis import Devis
from app.schemas.devis import DevisCreate
from app.services.email_service import send_operator_notification, send_prospect_confirmation
from app.services.sheets_service import append_devis_to_sheet


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

    # Send emails + Google Sheets (best-effort — don't block on failure)
    try:
        await send_operator_notification(devis)
        await send_prospect_confirmation(devis)
    except Exception:
        pass  # Logged by email_service

    try:
        await append_devis_to_sheet(devis)
    except Exception:
        pass  # Logged by sheets_service

    return devis
