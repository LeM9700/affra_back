import asyncio
import json
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings
from app.models.attribution import Visitor
from app.models.devis import Devis
from app.models.lead import Lead

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "Date",
    "Prénom",
    "Email",
    "Téléphone",
    "Ville",
    "Type client",
    "Possède véhicule",
    "Distance quotidienne",
    "Délai",
    "Distance tableau",
    # Attribution (ajoutées en fin de ligne pour ne pas décaler les colonnes existantes).
    # Copie de confort : PostgreSQL reste la source de vérité.
    "Lead ID",
    "Visitor ID",
    "Source",
    "Attribution financière",
    "Confiance",
    "First touch",
]


def _get_credentials() -> Credentials:
    value = settings.google_service_account_json.strip()
    if value.startswith("{"):
        return Credentials.from_service_account_info(json.loads(value), scopes=SCOPES)
    return Credentials.from_service_account_file(value, scopes=SCOPES)


def _get_sheet() -> gspread.Worksheet:
    creds = _get_credentials()
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
    sheet = spreadsheet.sheet1

    # Auto-create headers if sheet is empty ; complète l'en-tête existant avec les nouvelles colonnes
    first_row = sheet.row_values(1)
    if not first_row:
        sheet.append_row(HEADERS, value_input_option="USER_ENTERED")
    elif len(first_row) < len(HEADERS) and first_row == HEADERS[: len(first_row)]:
        sheet.update(range_name="A1", values=[HEADERS], value_input_option="USER_ENTERED")

    return sheet


def build_row(devis: Devis, lead: Lead | None = None, visitor: Visitor | None = None) -> list:
    return [
        datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M"),
        devis.prenom,
        devis.email,
        devis.telephone,
        devis.ville,
        devis.type_client,
        devis.possede_vehicule,
        devis.distance_quotidienne,
        devis.delai,
        devis.distance_tableau,
        str(lead.id) if lead else "",
        str(visitor.id) if visitor else "",
        lead.marketing_source if lead else "",
        lead.financial_attribution if lead else "",
        lead.attribution_confidence if lead else "",
        (visitor.first_source or "") if visitor else "",
    ]


def _append_row_sync(row: list) -> None:
    """Synchronous — called via asyncio.to_thread."""
    sheet = _get_sheet()
    sheet.append_row(row, value_input_option="USER_ENTERED")


async def append_devis_to_sheet(devis: Devis, lead: Lead | None = None, visitor: Visitor | None = None) -> None:
    """Append a devis row to the configured Google Sheet (best-effort, non-blocking)."""
    if not settings.google_sheets_spreadsheet_id or not settings.google_service_account_json:
        return
    try:
        # Ligne construite ici (thread principal) : pas d'accès ORM depuis le thread worker.
        await asyncio.to_thread(_append_row_sync, build_row(devis, lead, visitor))
        logger.info("Google Sheets: devis id=%s appended", devis.id)
    except Exception:
        logger.exception("Google Sheets append failed — devis id=%s", devis.id)
