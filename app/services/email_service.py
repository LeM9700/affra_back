import logging

import resend

from app.config import settings
from app.models.devis import Devis

logger = logging.getLogger(__name__)

resend.api_key = settings.resend_api_key


async def send_operator_notification(devis: Devis) -> None:
    if not settings.operator_email or not settings.resend_api_key:
        logger.warning("Email not configured — skipping operator notification")
        return

    body = f"""
<h2>Nouvelle demande de devis — AFFRA Réseaux</h2>
<table>
  <tr><td><strong>Prénom</strong></td><td>{devis.prenom}</td></tr>
  <tr><td><strong>Email</strong></td><td>{devis.email}</td></tr>
  <tr><td><strong>Téléphone</strong></td><td>{devis.telephone}</td></tr>
  <tr><td><strong>Ville</strong></td><td>{devis.ville}</td></tr>
  <tr><td><strong>Type client</strong></td><td>{devis.type_client}</td></tr>
  <tr><td><strong>Possède un véhicule ?</strong></td><td>{devis.possede_vehicule}</td></tr>
  <tr><td><strong>Distance quotidienne</strong></td><td>{devis.distance_quotidienne}</td></tr>
  <tr><td><strong>Délai souhaité</strong></td><td>{devis.delai}</td></tr>
  <tr><td><strong>Distance tableau électrique</strong></td><td>{devis.distance_tableau}</td></tr>
</table>
<p><em>ID : {devis.id}</em></p>
"""

    try:
        resend.Emails.send({
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
<p>Bonjour {devis.prenom},</p>
<p>Nous avons bien reçu votre demande concernant l'installation d'une solution de recharge électrique à {devis.ville}.</p>
<p>Un conseiller AFFRA Réseaux vous rappelle sous 24h pour vous proposer la solution la plus adaptée à votre besoin et à votre budget.</p>
<br>
<p>Cordialement,<br>L'équipe AFFRA Réseaux</p>
"""

    try:
        resend.Emails.send({
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
        resend.Emails.send({
            "from": "noreply@affra-reseaux.fr",
            "to": to,
            "subject": subject,
            "html": html_body,
        })
    except Exception as e:
        logger.error("Failed to send custom email to %s: %s", to, e)
        raise
