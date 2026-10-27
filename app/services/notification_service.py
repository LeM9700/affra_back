"""Notifications déclenchées par une nouvelle demande de devis."""
import logging

from app.models.devis import Devis
from app.services import email_service, telegram_service

logger = logging.getLogger(__name__)


async def notify_new_devis(devis: Devis) -> None:
    """Prévient le gérant (email + Telegram) et confirme au prospect.

    Best-effort : chaque canal est isolé, l'échec de l'un ne bloque jamais les autres.
    Appelé en tâche de fond par la route, donc après le commit du devis.

    Args:
        devis: La demande de devis déjà enregistrée en base.
    """
    channels = (
        email_service.send_operator_notification,
        telegram_service.send_devis_notification,
        email_service.send_prospect_confirmation,
    )
    for send in channels:
        try:
            await send(devis)
        except Exception:
            logger.exception("Notification %s failed for devis id=%s", send.__name__, devis.id)
