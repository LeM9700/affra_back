import asyncio
import logging
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from app.config import settings
from app.models.devis import Devis

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
]


def _get_sheet() -> gspread.Worksheet:
    creds = Credentials.from_service_account_file(
        settings.google_service_account_json, scopes=SCOPES
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(settings.google_sheets_spreadsheet_id)
    sheet = spreadsheet.sheet1

    # Auto-create headers if sheet is empty
    if not sheet.get_all_values():
        sheet.append_row(HEADERS, value_input_option="USER_ENTERED")

    return sheet


def _append_row_sync(devis: Devis) -> None:
    """Synchronous — called via asyncio.to_thread."""
    sheet = _get_sheet()
    row = [
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
    ]
    sheet.append_row(row, value_input_option="USER_ENTERED")


async def append_devis_to_sheet(devis: Devis) -> None:
    """Append a devis row to the configured Google Sheet (best-effort, non-blocking)."""
    if not settings.google_sheets_spreadsheet_id or not settings.google_service_account_json:
        return
    try:
        await asyncio.to_thread(_append_row_sync, devis)
        logger.info("Google Sheets: devis id=%s appended", devis.id)
    except Exception:
        logger.exception("Google Sheets append failed — devis id=%s", devis.id)
