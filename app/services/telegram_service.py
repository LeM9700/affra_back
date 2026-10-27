"""Alertes opérateur via l'API Bot Telegram."""
import logging

import httpx

from app.config import settings
from app.models.devis import Devis

logger = logging.getLogger(__name__)

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
REQUEST_TIMEOUT_SECONDS = 5.0

# Libellés lisibles des réponses du questionnaire (valeurs validées par DevisCreate).
_LABELS = {
    "type_client": {"maison": "Maison", "copropriete": "Copropriété", "entreprise": "Entreprise"},
    "possede_vehicule": {"oui": "Oui", "pas_encore": "Pas encore", "livraison_prochaine": "Livraison prochaine"},
    "distance_quotidienne": {"0_50": "0–50 km", "50_150": "50–150 km", "plus_150": "+150 km"},
    "delai": {"rapidement": "Rapidement", "un_deux_mois": "1–2 mois", "pas_urgent": "Pas urgent"},
    "distance_tableau": {"0_5m": "0–5 m", "5_15m": "5–15 m", "plus_15m": "+15 m", "ne_sait_pas": "Ne sait pas"},
}


class TelegramNotificationError(Exception):
    """Échec d'envoi Telegram. Le message ne contient jamais l'URL (qui embarque le token du bot)."""


def _label(field: str, value: str | None) -> str:
    if not value:
        return "—"
    return _LABELS[field].get(value, value)


def format_devis_message(devis: Devis) -> str:
    """Construit le message texte envoyé au gérant pour une nouvelle demande de devis.

    Texte brut (sans parse_mode) : aucune saisie du prospect ne peut être interprétée comme du formatage.

    Args:
        devis: La demande de devis nouvellement enregistrée.

    Returns:
        Le corps du message Telegram.
    """
    return (
        "🔔 Nouvelle demande de devis\n"
        "\n"
        f"👤 {devis.prenom or '—'}\n"
        f"📞 {devis.telephone or '—'}\n"
        f"✉️ {devis.email}\n"
        f"📍 {devis.ville or '—'}\n"
        "\n"
        f"🏠 Type : {_label('type_client', devis.type_client)}\n"
        f"🚗 Véhicule : {_label('possede_vehicule', devis.possede_vehicule)}"
        f" ({_label('distance_quotidienne', devis.distance_quotidienne)}/jour)\n"
        f"⏱ Délai : {_label('delai', devis.delai)}\n"
        f"🔌 Distance tableau : {_label('distance_tableau', devis.distance_tableau)}\n"
        "\n"
        f"👉 Dashboard : {settings.dashboard_url}\n"
        f"ID : {devis.id}"
    )


async def send_devis_notification(devis: Devis) -> None:
    """Envoie l'alerte « nouveau devis » dans le chat Telegram du gérant.

    Ne fait rien si TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID n'est pas configuré.

    Args:
        devis: La demande de devis nouvellement enregistrée.

    Raises:
        TelegramNotificationError: Si Telegram est injoignable ou refuse le message.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured — skipping operator notification")
        return

    url = TELEGRAM_API_URL.format(token=settings.telegram_bot_token)
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": format_devis_message(devis),
        "link_preview_options": {"is_disabled": True},
    }
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
    except httpx.HTTPError as exc:
        # `from None` : la cause httpx contient l'URL, donc le token.
        raise TelegramNotificationError(f"Telegram unreachable: {type(exc).__name__}") from None

    if response.status_code != 200:
        try:
            description = response.json().get("description", "")
        except ValueError:
            description = ""
        raise TelegramNotificationError(f"Telegram rejected message: HTTP {response.status_code} {description}")
