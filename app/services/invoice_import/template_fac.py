"""Lecture du modèle de facture du logiciel de facturation d'AFFRA RESEAUX.

Repères du modèle : numéros FAC0000xxxx (facture), DEV0000xxxx (devis), CLT0000xxxx (client),
ART0000xxxx (article), tableau « Libellé Qté Unité PU HT Rem. Montant HT TVA », totaux en page 2.
Fonction pure sur le texte : testable sans PDF.
"""

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.services.invoice_import.models import ExtractedInvoice, ExtractedLine

MAX_DESCRIPTION = 2000
_AMOUNT = r"-?\d[\d   ]*,\d{2}"
_LINE = re.compile(
    rf"^(?P<code>ART\d+)\s*-\s*(?P<label>.+?)\s+(?P<qty>\d+(?:,\d+)?)\s+(?P<unit>\S+)\s+"
    rf"(?P<pu>{_AMOUNT})\s*€\s+(?P<rem>\d+(?:,\d+)?)\s*%\s+(?P<total>{_AMOUNT})\s*€\s+(?P<tva>\d+(?:,\d+)?)\s*%\s*$"
)
# Lignes qui terminent la description d'un article (pied de page, tableau suivant, en-tête répété).
_STOP = re.compile(
    r"^(ART\d+\s*-|Type de vente|Détail de la TVA|Page \d+ de \d+|AFFRA RESEAUX - |- IBAN|- N° TVA|FACTURE$|Total HT)",
    re.IGNORECASE,
)
_CIVILITY = re.compile(r"^(Monsieur|Madame|M\.|Mme|Mlle)\s+", re.IGNORECASE)


def _cents(raw: str) -> int:
    cleaned = re.sub(r"[   €]", "", raw).replace(",", ".")
    return int((Decimal(cleaned) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _bp(raw: str) -> int:
    return int((Decimal(raw.replace(",", ".")) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d/%m/%Y").date()
    except ValueError:
        return None


def _find(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1).strip() if match else None


def looks_like_fac_template(text: str) -> bool:
    """Le texte vient-il du modèle FAC du logiciel de facturation ?"""
    return bool(re.search(r"N° : FAC\d+", text)) and "Libellé" in text and "Total TTC" in text


def _parse_client(block: list[str], invoice: ExtractedInvoice) -> None:
    if not block:
        invoice.warnings.append("Bloc client introuvable : nom et adresse à saisir.")
        return
    invoice.client_name = _CIVILITY.sub("", block[0]).strip() or None
    rest = block[1:]
    postal_index = next((i for i, line in enumerate(rest) if re.match(r"^\d{5}\s+\S", line)), None)
    if postal_index is None:
        invoice.warnings.append("Code postal du client introuvable.")
        invoice.client_address_line1 = rest[0] if rest else None
        return
    invoice.client_address_line1 = " ".join(rest[:postal_index]) or None
    postal, _, city = rest[postal_index].partition(" ")
    invoice.client_postal_code = postal
    invoice.client_city = city.strip().title() or None
    invoice.client_country = (rest[postal_index + 1].title() if postal_index + 1 < len(rest) else None) or "France"


def _parse_lines(text: str, invoice: ExtractedInvoice) -> None:
    current: ExtractedLine | None = None
    extra: list[str] = []

    def flush() -> None:
        if current is not None:
            details = "\n".join(extra).strip()
            full = f"{current.description}\n{details}" if details else current.description
            current.description = full[:MAX_DESCRIPTION]
            invoice.lines.append(current)

    for raw in text.splitlines():
        line = raw.strip()
        match = _LINE.match(line)
        if match:
            flush()
            extra = []
            try:
                current = ExtractedLine(
                    code=match["code"],
                    description=match["label"].strip(),
                    quantity=Decimal(match["qty"].replace(",", ".")),
                    unit=match["unit"],
                    unit_price_ht_cents=_cents(match["pu"]),
                    discount_bp=_bp(match["rem"]),
                    total_ht_cents=_cents(match["total"]),
                    vat_rate_bp=_bp(match["tva"]),
                )
            except (InvalidOperation, ValueError):
                current = None
                invoice.warnings.append(f"Ligne illisible : {line[:80]}")
            continue
        if current is None:
            continue
        if _STOP.match(line):
            flush()
            current = None
            extra = []
            continue
        if line:
            extra.append(line)
    flush()
    if not invoice.lines:
        invoice.warnings.append("Aucune ligne de facture reconnue : lignes à saisir.")


def parse_fac_text(text: str, client_block: list[str], *, paid_stamp: bool = False) -> ExtractedInvoice:
    """Extrait les champs d'une facture du modèle FAC.

    Args:
        text: Texte de la facture (tampon déjà retiré).
        client_block: Lignes du destinataire (colonne de droite).
        paid_stamp: Tampon « ACQUITTÉE » détecté.

    Returns:
        Les champs reconnus ; ce qui manque est signalé dans `warnings`.
    """
    invoice = ExtractedInvoice(method="PDF_TEXT", paid_stamp=paid_stamp)
    invoice.invoice_number = _find(r"N° : (FAC\d+)", text)
    invoice.invoice_date = _date(_find(r"Date d'émission : (\d{2}/\d{2}/\d{4})", text))
    invoice.external_quote_ref = _find(r"En référence : (DEV\d+)", text)
    invoice.external_customer_ref = _find(r"N° client : (CLT\d+)", text)
    invoice.seller_siret = _find(r"Siret : (\d{14})", text)
    invoice.seller_vat_number = _find(r"N° TVA (FR[0-9A-Z]{11})", text)
    invoice.payment_terms = _find(r"^Règlement\s+(.+)$", text)
    invoice.due_date = _date(_find(rf"Echéance\(s\)\s+{_AMOUNT}\s*€\s+au\s+(\d{{2}}/\d{{2}}/\d{{4}})", text))

    for name, pattern in (
        ("total_ht_cents", rf"Total HT\s+({_AMOUNT})\s*€"),
        ("total_vat_cents", rf"(?:^|\s)TVA\s+({_AMOUNT})\s*€"),
        ("total_ttc_cents", rf"Total TTC\s+({_AMOUNT})\s*€"),
    ):
        raw = _find(pattern, text)
        setattr(invoice, name, _cents(raw) if raw else None)
        if raw is None:
            invoice.warnings.append(f"{name.replace('_cents', '').replace('_', ' ').upper()} introuvable.")

    _parse_client(client_block, invoice)
    _parse_lines(text, invoice)
    if invoice.invoice_number is None:
        invoice.warnings.append("Numéro de facture introuvable.")
    if invoice.invoice_date is None:
        invoice.warnings.append("Date d'émission introuvable.")
    return invoice
