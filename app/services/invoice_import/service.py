"""Orchestration de l'import d'une facture émise hors du dashboard.

1. import : fichier vérifié (type réel, taille, empreinte) → stockage R2 → lecture (PDF direct,
   sinon IA, sinon saisie manuelle) → contrôles → pièce « en attente de revue » ;
2. confirmation : l'humain valide (ou corrige) les données ; les contrôles sont refaits sur ce qu'il
   a validé, comparé aux totaux lus dans le PDF ; tout avertissement accepté exige un motif écrit ;
   la facture est alors créée (source IMPORT) avec sa commission éventuelle ;
3. rejet : la pièce est écartée avec un motif (le fichier reste conservé, pour la traçabilité).
"""

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.billing import Customer, CustomerInvoice
from app.models.devis import Devis
from app.models.invoice_document import InvoiceDocument
from app.models.lead import Lead
from app.schemas.billing import InvoiceCreate
from app.services import billing_service
from app.services.invoice_import import ai_extractor
from app.services.invoice_import.analysis import (
    Check,
    Draft,
    DraftLine,
    LeadContext,
    analyze,
    checks_to_json,
    has_blocking,
    warnings_of,
)
from app.services.invoice_import.models import ExtractedInvoice
from app.services.invoice_import.pdf_reader import UnreadablePdfError, read_pdf
from app.services.invoice_import.template_fac import looks_like_fac_template, parse_fac_text
from app.services.storage_service import DocumentStorage

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 10 * 1024 * 1024
MIN_REASON_LENGTH = 10
_EXTENSIONS = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png"}
ALLOWED_VAT_BP = {0, 550, 1000, 2000}


class InvoiceImportError(Exception):
    def __init__(self, message: str, status_code: int = 400, extra: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}


def detect_content_type(data: bytes) -> str | None:
    """Type réel d'après les premiers octets (l'extension et le Content-Type annoncés sont ignorés)."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def _safe_filename(name: str | None, content_type: str) -> str:
    base = "".join(ch for ch in (name or "") if ch.isalnum() or ch in " ._-()").strip()[:200]
    return base or f"facture.{_EXTENSIONS[content_type]}"


async def _extract(data: bytes, content_type: str) -> ExtractedInvoice:
    if content_type == "application/pdf":
        try:
            pdf = read_pdf(data)
        except UnreadablePdfError as exc:
            raise InvoiceImportError(
                "PDF illisible ou protégé : exportez-le à nouveau depuis le logiciel.", 422
            ) from exc
        if pdf.has_text_layer and looks_like_fac_template(pdf.text):
            return parse_fac_text(pdf.text, pdf.client_block, paid_stamp=pdf.paid_stamp)
    try:
        return await ai_extractor.extract_with_ai(data, content_type)
    except ai_extractor.AiExtractionUnavailable as exc:
        logger.info("Invoice AI extraction unavailable: %s", exc)
        return ExtractedInvoice(
            method="NONE",
            warnings=[f"Lecture automatique impossible ({exc}) : saisissez la facture à partir du PDF."],
        )


def _draft_from_extraction(inv: ExtractedInvoice) -> Draft:
    return Draft(
        invoice_number=inv.invoice_number,
        invoice_date=inv.invoice_date,
        client_name=inv.client_name,
        client_postal_code=inv.client_postal_code,
        client_city=inv.client_city,
        lines=[
            DraftLine(ln.quantity, ln.unit_price_ht_cents, ln.discount_bp, ln.vat_rate_bp, ln.total_ht_cents)
            for ln in inv.lines
        ],
        document_total_ht_cents=inv.total_ht_cents,
        document_total_vat_cents=inv.total_vat_cents,
        document_total_ttc_cents=inv.total_ttc_cents,
    )


def _draft_from_payload(payload: InvoiceCreate, extraction: dict) -> Draft:
    """Ce que l'humain a validé, comparé aux totaux imprimés sur le document."""
    return Draft(
        invoice_number=payload.invoice_number,
        invoice_date=payload.invoice_date,
        client_name=payload.billing.name,
        client_postal_code=payload.billing.postal_code,
        client_city=payload.billing.city,
        lines=[
            DraftLine(Decimal(ln.quantity), ln.unit_price_ht_cents, ln.discount_bp, ln.vat_rate_bp, None)
            for ln in payload.lines
        ],
        document_total_ht_cents=extraction.get("total_ht_cents"),
        document_total_vat_cents=extraction.get("total_vat_cents"),
        document_total_ttc_cents=extraction.get("total_ttc_cents"),
    )


async def _context(
    db: AsyncSession, lead: Lead, draft: Draft, *, document_siret: str | None, paid: bool, warnings: list[str]
) -> LeadContext:
    villes = [v for v in (await db.execute(select(Devis.ville).where(Devis.lead_id == lead.id))).scalars() if v]
    customer = (await db.execute(select(Customer).where(Customer.lead_id == lead.id))).scalar_one_or_none()
    postal_codes = [customer.billing_postal_code] if customer and customer.billing_postal_code else []

    number_taken = False
    if draft.invoice_number:
        number_taken = (
            await db.execute(select(CustomerInvoice.id).where(CustomerInvoice.invoice_number == draft.invoice_number))
        ).first() is not None

    same_amount_same_day = False
    total_ttc = draft.document_total_ttc_cents
    if customer is not None and draft.invoice_date and total_ttc:
        same_amount_same_day = (
            await db.execute(
                select(CustomerInvoice.id).where(
                    CustomerInvoice.customer_id == customer.id,
                    CustomerInvoice.invoice_date == draft.invoice_date,
                    CustomerInvoice.total_ttc_cents == total_ttc,
                )
            )
        ).first() is not None

    return LeadContext(
        prenom=lead.prenom,
        nom=lead.nom,
        ville=lead.ville,
        code_postaux=postal_codes,
        villes_devis=villes,
        created_on=lead.created_at.date(),
        today=datetime.now(timezone.utc).date(),
        seller_siret=settings.seller_siret,
        document_seller_siret=document_siret,
        number_taken=number_taken,
        same_amount_same_day=same_amount_same_day,
        paid_stamp=paid,
        extraction_warnings=warnings,
    )


def build_prefill(inv: ExtractedInvoice) -> dict:
    """Valeurs proposées pour le formulaire de facture du dashboard (modifiables par l'humain)."""
    notes = ", ".join(
        part
        for part in (
            f"Devis {inv.external_quote_ref}" if inv.external_quote_ref else "",
            f"client {inv.external_customer_ref}" if inv.external_customer_ref else "",
        )
        if part
    )
    return {
        "invoice_number": inv.invoice_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "billing": {
            "name": inv.client_name or "",
            "address_line1": inv.client_address_line1 or "",
            "postal_code": inv.client_postal_code or "",
            "city": inv.client_city or "",
            "country": inv.client_country or "France",
        },
        "lines": [
            {
                "description": ln.description,
                "quantity": str(ln.quantity),
                "unit": ln.unit,
                "unit_price_ht_cents": ln.unit_price_ht_cents,
                "discount_bp": ln.discount_bp if 0 <= ln.discount_bp <= 10_000 else 0,
                "vat_rate_bp": ln.vat_rate_bp if ln.vat_rate_bp in ALLOWED_VAT_BP else 2000,
            }
            for ln in inv.lines
        ],
        "payment_terms": inv.payment_terms,
        "notes": f"Facture importée ({notes})." if notes else "Facture importée.",
        "external_reference": inv.invoice_number,
    }


async def import_document(
    db: AsyncSession,
    storage: DocumentStorage,
    *,
    lead_id: uuid.UUID,
    filename: str | None,
    data: bytes,
    admin_id: uuid.UUID,
) -> InvoiceDocument:
    """Reçoit le fichier, le conserve, le lit et le contrôle. Rien n'est facturé à ce stade."""
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise InvoiceImportError("Lead introuvable", 404)
    if not data:
        raise InvoiceImportError("Fichier vide", 422)
    if len(data) > MAX_FILE_BYTES:
        raise InvoiceImportError("Fichier trop volumineux (10 Mo maximum)", 413)
    content_type = detect_content_type(data)
    if content_type is None:
        raise InvoiceImportError("Format non pris en charge : PDF, JPEG ou PNG uniquement", 415)

    sha = hashlib.sha256(data).hexdigest()
    existing = (await db.execute(select(InvoiceDocument).where(InvoiceDocument.sha256 == sha))).scalar_one_or_none()
    if existing is not None:
        raise InvoiceImportError(
            "Ce fichier a déjà été importé", 409, {"document_id": str(existing.id), "lead_id": str(existing.lead_id)}
        )

    key = f"invoices/{lead.id}/{sha}.{_EXTENSIONS[content_type]}"
    await storage.put(key, data, content_type)

    extraction = await _extract(data, content_type)
    draft = _draft_from_extraction(extraction)
    ctx = await _context(
        db,
        lead,
        draft,
        document_siret=extraction.seller_siret,
        paid=extraction.paid_stamp,
        warnings=extraction.warnings,
    )
    checks = analyze(draft, ctx)

    document = InvoiceDocument(
        lead_id=lead.id,
        sha256=sha,
        storage_key=key,
        original_filename=_safe_filename(filename, content_type),
        content_type=content_type,
        size_bytes=len(data),
        status="PENDING_REVIEW",
        extraction_method=extraction.method,
        extraction={**extraction.to_json(), "prefill": build_prefill(extraction)},
        analysis=checks_to_json(checks),
        uploaded_by=admin_id,
    )
    db.add(document)
    await db.flush()
    return document


async def _locked_pending(db: AsyncSession, document_id: uuid.UUID) -> InvoiceDocument:
    document = (
        await db.execute(select(InvoiceDocument).where(InvoiceDocument.id == document_id).with_for_update())
    ).scalar_one_or_none()
    if document is None:
        raise InvoiceImportError("Pièce introuvable", 404)
    if document.status != "PENDING_REVIEW":
        raise InvoiceImportError("Cette pièce a déjà été traitée", 409)
    return document


async def confirm_document(
    db: AsyncSession,
    *,
    document_id: uuid.UUID,
    payload: InvoiceCreate,
    acknowledgements: dict[str, str],
    admin_id: uuid.UUID,
) -> tuple[InvoiceDocument, list[Check]]:
    """Validation humaine : contrôles refaits, motifs exigés, puis création de la facture IMPORT."""
    document = await _locked_pending(db, document_id)
    lead = await db.get(Lead, document.lead_id)
    if not payload.invoice_number:
        raise InvoiceImportError("Le numéro de la facture d'origine est obligatoire pour un import", 422)

    extraction = document.extraction
    draft = _draft_from_payload(payload, extraction)
    ctx = await _context(
        db,
        lead,
        draft,
        document_siret=extraction.get("seller_siret"),
        paid=bool(extraction.get("paid_stamp")),
        warnings=[],
    )
    checks = analyze(draft, ctx)
    read_number = extraction.get("invoice_number")
    if read_number and payload.invoice_number != read_number:
        checks.append(Check("number_changed", "warning", f"Numéro modifié : {read_number} lu sur le document."))
    if extraction.get("method") in ("AI", "NONE"):
        checks.append(
            Check(
                "manual_review", "warning", "Facture lue par IA ou saisie à la main : contrôle visuel du PDF effectué ?"
            )
        )

    if has_blocking(checks):
        raise InvoiceImportError(
            "La facture comporte des incohérences bloquantes", 422, {"checks": checks_to_json(checks)}
        )
    missing = sorted(
        {c.code for c in warnings_of(checks)}
        - {code for code, reason in acknowledgements.items() if len(reason.strip()) >= MIN_REASON_LENGTH}
    )
    if missing:
        raise InvoiceImportError(
            f"Motif ({MIN_REASON_LENGTH} caractères minimum) requis pour chaque avertissement accepté",
            422,
            {"checks": checks_to_json(checks), "missing_acknowledgements": missing},
        )

    invoice, _customer, _commission, _created = await billing_service.create_invoice_for_lead(
        db,
        document.lead_id,
        payload,
        admin_id,
        source_system="IMPORT",
        external_customer_ref=extraction.get("external_customer_ref"),
        external_quote_ref=extraction.get("external_quote_ref"),
    )
    document.status = "CONFIRMED"
    document.invoice_id = invoice.id
    document.reviewed_by = admin_id
    document.reviewed_at = datetime.now(timezone.utc)
    document.confirmation = {
        "submitted": payload.model_dump(mode="json"),
        "checks": checks_to_json(checks),
        "acknowledgements": {
            code: acknowledgements[code].strip() for code in sorted({c.code for c in warnings_of(checks)})
        },
    }
    await db.flush()
    return document, checks


async def reject_document(
    db: AsyncSession, *, document_id: uuid.UUID, reason: str, admin_id: uuid.UUID
) -> InvoiceDocument:
    """Écarte une pièce (mauvais fichier, doublon, facture d'un autre client…). Le fichier reste conservé."""
    document = await _locked_pending(db, document_id)
    document.status = "REJECTED"
    document.rejection_reason = reason.strip()
    document.reviewed_by = admin_id
    document.reviewed_at = datetime.now(timezone.utc)
    await db.flush()
    return document
