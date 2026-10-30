"""Notifications au gérant : nouvelle demande de devis, demande de rappel."""
import logging

from app.middleware.rate_limit import telegram_callback_limiter
from app.models.devis import Devis
from app.services import email_service, telegram_service
from app.services.attribution_service import CallbackSummary

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


async def notify_callback_request(summary: CallbackSummary) -> None:
    """Prévient le gérant (Telegram) d'une demande de rappel.

    Best-effort, en tâche de fond après le commit. Une demande rejouée (déjà reçue) n'est pas
    renotifiée, et un plafond global d'alertes protège le chat du gérant contre une vague de spam.

    Args:
        summary: Instantané de la demande.
    """
    if not summary.created:
        return
    if not telegram_callback_limiter.allow("global"):
        logger.warning("Telegram callback alerts capped — visitor id=%s not notified", summary.visitor_id)
        return
    try:
        await telegram_service.send_callback_notification(summary)
    except Exception:
        logger.exception("Callback notification failed for visitor id=%s", summary.visitor_id)
