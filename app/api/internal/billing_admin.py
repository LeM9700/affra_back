import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.leads_admin import admin_uuid
from app.dependencies import get_db, verify_api_key, verify_jwt_token
from app.models.enums import CommissionStatus
from app.schemas.billing import (
    AttributionStats,
    CommissionListResponse,
    CommissionOut,
    InvoiceListResponse,
    InvoiceOut,
)
from app.schemas.lead import PhoneClickOut, ProspectListResponse
from app.services import billing_service, reporting_service

invoices_router = APIRouter(dependencies=[Depends(verify_api_key), Depends(verify_jwt_token)])
commissions_router = APIRouter(dependencies=[Depends(verify_api_key), Depends(verify_jwt_token)])
attribution_router = APIRouter(dependencies=[Depends(verify_api_key), Depends(verify_jwt_token)])


# Les factures sont immuables : ni PATCH ni DELETE (les avoirs sont hors périmètre V1).
@invoices_router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, max_length=100),
    lead_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items, total = await reporting_service.list_invoices(db, search=search, lead_id=lead_id, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@invoices_router.get("/{invoice_id}", response_model=InvoiceOut)
async def get_invoice(invoice_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    data = await reporting_service.get_invoice_out(db, invoice_id)
    if data is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice not found")
    return data


@commissions_router.get("", response_model=CommissionListResponse)
async def list_commissions(
    db: AsyncSession = Depends(get_db),
    commission_status: CommissionStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items, total = await reporting_service.list_commissions(
        db, status=commission_status.value if commission_status else None, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@commissions_router.post("/{commission_id}/pay", response_model=CommissionOut)
async def pay_commission(
    commission_id: uuid.UUID, db: AsyncSession = Depends(get_db), admin_id: uuid.UUID = Depends(admin_uuid)
):
    try:
        return await billing_service.mark_commission_paid(db, commission_id, admin_id)
    except billing_service.BillingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@attribution_router.get("/stats", response_model=AttributionStats)
async def attribution_stats(
    db: AsyncSession = Depends(get_db),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
):
    return await reporting_service.compute_stats(db, date_from, date_to)


@attribution_router.get("/prospects", response_model=ProspectListResponse)
async def prospects(
    db: AsyncSession = Depends(get_db),
    days: int = Query(60, ge=1, le=395),
    visitor_id: uuid.UUID | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Visiteurs qui ont cliqué sur téléphone / email / WhatsApp ou commencé un devis, sans lead associé."""
    items, total = await reporting_service.list_prospects(
        db, days=days, visitor_id=visitor_id, limit=limit, offset=offset
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@attribution_router.get("/phone-clicks", response_model=list[PhoneClickOut])
async def unlinked_phone_clicks(
    db: AsyncSession = Depends(get_db),
    hours: int = Query(72, ge=1, le=24 * 30),
    limit: int = Query(50, ge=1, le=200),
):
    """Clics téléphone non encore rattachés à un lead — pour relier un appel reçu à son parcours web."""
    return await reporting_service.list_unlinked_phone_clicks(db, hours, limit)
