import asyncio
import logging
from html import escape

import resend

from app.config import settings
from app.models.devis import Devis

logger = logging.getLogger(__name__)

resend.api_key = settings.resend_api_key


async def _send(params: dict) -> None:
    """Envoie via Resend dans un thread : le SDK est synchrone et bloquerait l'event loop."""
    await asyncio.to_thread(resend.Emails.send, params)


def _e(value: object) -> str:
    """Échappe une saisie utilisateur avant insertion dans du HTML (anti-injection de liens/balises)."""
    return escape(str(value)) if value is not None else ""


async def send_operator_notification(devis: Devis) -> None:
    if not settings.operator_email or not settings.resend_api_key:
        logger.warning("Email not configured — skipping operator notification")
        return

    body = f"""
<h2>Nouvelle demande de devis — AFFRA Réseaux</h2>
<table>
  <tr><td><strong>Prénom</strong></td><td>{_e(devis.prenom)}</td></tr>
  <tr><td><strong>Email</strong></td><td>{_e(devis.email)}</td></tr>
  <tr><td><strong>Téléphone</strong></td><td>{_e(devis.telephone)}</td></tr>
  <tr><td><strong>Ville</strong></td><td>{_e(devis.ville)}</td></tr>
  <tr><td><strong>Type client</strong></td><td>{_e(devis.type_client)}</td></tr>
  <tr><td><strong>Possède un véhicule ?</strong></td><td>{_e(devis.possede_vehicule)}</td></tr>
  <tr><td><strong>Distance quotidienne</strong></td><td>{_e(devis.distance_quotidienne)}</td></tr>
  <tr><td><strong>Délai souhaité</strong></td><td>{_e(devis.delai)}</td></tr>
  <tr><td><strong>Distance tableau électrique</strong></td><td>{_e(devis.distance_tableau)}</td></tr>
</table>
<p><em>ID : {devis.id}</em></p>
"""

    try:
        await _send({
            "from": "noreply@affra-reseaux.fr",
            "to": settings.operator_email,
            "subject": f"Nouveau devis — {devis.prenom} ({devis.ville})",
            "html": body,
        })
    except Exception as e:
        logger.error("Failed to send operator notification: %s", e)
        raise


async def send_prospect_confirmation(devis: Devis) -> None:
    if not devis.email or not settings.resend_api_key:
        return

    body = f"""
<h2>Votre demande a bien été reçue</h2>
<p>Bonjour {_e(devis.prenom)},</p>
<p>Nous avons bien reçu votre demande concernant l'installation d'une solution de recharge électrique à {_e(devis.ville)}.</p>
<p>Un conseiller AFFRA Réseaux vous rappelle sous 24h pour vous proposer la solution la plus adaptée à votre besoin et à votre budget.</p>
<br>
<p>Cordialement,<br>L'équipe AFFRA Réseaux</p>
"""

    try:
        await _send({
            "from": "noreply@affra-reseaux.fr",
            "to": devis.email,
            "subject": "Votre demande de devis AFFRA Réseaux",
            "html": body,
        })
    except Exception as e:
        logger.error("Failed to send prospect confirmation: %s", e)
        raise


async def send_custom_email(to: str, subject: str, html_body: str) -> None:
    if not settings.resend_api_key:
        logger.warning("Resend not configured — skipping custom email to %s", to)
        return

    try:
        await _send({
            "from": "noreply@affra-reseaux.fr",
            "to": to,
            "subject": subject,
            "html": html_body,
        })
    except Exception as e:
        logger.error("Failed to send custom email to %s: %s", to, e)
        raise
