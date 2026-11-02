"""Import de factures émises hors du dashboard (PDF / image) : upload, revue, confirmation, rejet."""

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.leads_admin import admin_uuid
from app.dependencies import get_db, verify_api_key, verify_jwt_token
from app.models.invoice_document import InvoiceDocument
from app.schemas.invoice_import import FileUrlOut, InvoiceDocumentConfirm, InvoiceDocumentOut, InvoiceDocumentReject
from app.services.invoice_import import service
from app.services.storage_service import PRESIGNED_URL_SECONDS, DocumentStorage, StorageNotConfiguredError, get_storage

lead_documents_router = APIRouter(dependencies=[Depends(verify_api_key), Depends(verify_jwt_token)])
documents_router = APIRouter(dependencies=[Depends(verify_api_key), Depends(verify_jwt_token)])


def storage_dependency() -> DocumentStorage:
    try:
        return get_storage()
    except StorageNotConfiguredError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Stockage des factures non configuré"
        ) from exc


def _http(exc: service.InvoiceImportError) -> HTTPException:
    detail: str | dict = exc.message if not exc.extra else {"message": exc.message, **exc.extra}
    return HTTPException(status_code=exc.status_code, detail=detail)


@lead_documents_router.post(
    "/{lead_id}/invoice-documents", response_model=InvoiceDocumentOut, status_code=status.HTTP_201_CREATED
)
async def upload_invoice_document(
    lead_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    storage: DocumentStorage = Depends(storage_dependency),
    admin_id: uuid.UUID = Depends(admin_uuid),
):
    """Lead → « Importer une facture » : le fichier est conservé, lu et contrôlé. Rien n'est facturé."""
    data = await file.read(service.MAX_FILE_BYTES + 1)
    try:
        return await service.import_document(
            db, storage, lead_id=lead_id, filename=file.filename, data=data, admin_id=admin_id
        )
    except service.InvoiceImportError as exc:
        raise _http(exc) from exc


@lead_documents_router.get("/{lead_id}/invoice-documents", response_model=list[InvoiceDocumentOut])
async def list_lead_documents(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return (
        (
            await db.execute(
                select(InvoiceDocument)
                .where(InvoiceDocument.lead_id == lead_id)
                .order_by(InvoiceDocument.created_at.desc())
            )
        )
        .scalars()
        .all()
    )


async def _document_or_404(db: AsyncSession, document_id: uuid.UUID) -> InvoiceDocument:
    document = await db.get(InvoiceDocument, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pièce introuvable")
    return document


@documents_router.get("/{document_id}", response_model=InvoiceDocumentOut)
async def get_document(document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _document_or_404(db, document_id)


@documents_router.get("/{document_id}/file-url", response_model=FileUrlOut)
async def document_file_url(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    storage: DocumentStorage = Depends(storage_dependency),
):
    """Lien temporaire (5 min) vers le fichier d'origine : le bucket n'est jamais public."""
    document = await _document_or_404(db, document_id)
    url = await storage.presigned_url(document.storage_key, document.original_filename, PRESIGNED_URL_SECONDS)
    return {"url": url, "expires_in": PRESIGNED_URL_SECONDS}


@documents_router.post("/{document_id}/confirm", response_model=InvoiceDocumentOut)
async def confirm_document(
    document_id: uuid.UUID,
    payload: InvoiceDocumentConfirm,
    db: AsyncSession = Depends(get_db),
    admin_id: uuid.UUID = Depends(admin_uuid),
):
    """Validation humaine : contrôles refaits sur les données validées ; crée la facture (source IMPORT)."""
    try:
        document, _checks = await service.confirm_document(
            db,
            document_id=document_id,
            payload=payload.invoice,
            acknowledgements=payload.acknowledgements,
            admin_id=admin_id,
        )
    except service.InvoiceImportError as exc:
        raise _http(exc) from exc
    except service.billing_service.BillingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return document


@documents_router.post("/{document_id}/reject", response_model=InvoiceDocumentOut)
async def reject_document(
    document_id: uuid.UUID,
    payload: InvoiceDocumentReject,
    db: AsyncSession = Depends(get_db),
    admin_id: uuid.UUID = Depends(admin_uuid),
):
    try:
        return await service.reject_document(db, document_id=document_id, reason=payload.reason, admin_id=admin_id)
    except service.InvoiceImportError as exc:
        raise _http(exc) from exc
