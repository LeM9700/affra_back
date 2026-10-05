import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db, verify_api_key, verify_jwt_token
from app.models.billing import Customer
from app.models.enums import FinancialAttribution, LeadStatus, MarketingSource
from app.models.lead import Lead
from app.schemas.billing import InvoiceCreate, InvoiceCreateResult, InvoiceOut
from app.schemas.lead import (
    AttributionDecisionCreate,
    LeadCreate,
    LeadDetail,
    LeadListResponse,
    LeadUpdate,
)
from app.services import billing_service, lead_service, reporting_service

router = APIRouter(dependencies=[Depends(verify_api_key), Depends(verify_jwt_token)])


def admin_uuid(user_id: str = Depends(verify_jwt_token)) -> uuid.UUID:
    try:
        return uuid.UUID(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from exc


async def _detail_or_404(db: AsyncSession, lead_id: uuid.UUID) -> dict:
    detail = await reporting_service.get_lead_detail(db, lead_id)
    if detail is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return detail


@router.get("", response_model=LeadListResponse)
async def list_leads(
    db: AsyncSession = Depends(get_db),
    search: str | None = Query(None, max_length=100),
    financial_attribution: FinancialAttribution | None = Query(None),
    marketing_source: MarketingSource | None = Query(None),
    lead_status: LeadStatus | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    items, total = await reporting_service.list_leads(
        db,
        search=search,
        financial_attribution=financial_attribution.value if financial_attribution else None,
        marketing_source=marketing_source.value if marketing_source else None,
        status=lead_status.value if lead_status else None,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("", response_model=LeadDetail, status_code=status.HTTP_201_CREATED)
async def create_lead(payload: LeadCreate, db: AsyncSession = Depends(get_db), admin_id: uuid.UUID = Depends(admin_uuid)):
    try:
        lead = await lead_service.create_manual_lead(db, payload, admin_id)
    except lead_service.LeadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return await _detail_or_404(db, lead.id)


@router.get("/{lead_id}", response_model=LeadDetail)
async def get_lead(lead_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await _detail_or_404(db, lead_id)


@router.patch("/{lead_id}", response_model=LeadDetail)
async def update_lead(lead_id: uuid.UUID, payload: LeadUpdate, db: AsyncSession = Depends(get_db)):
    lead = await db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    if payload.status is not None:
        is_customer = (await db.execute(select(Customer.id).where(Customer.lead_id == lead_id))).first() is not None
        if is_customer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Ce lead est un client : son statut ne peut plus être modifié"
            )
    for field, value in payload.model_dump(exclude_unset=True, mode="json").items():
        setattr(lead, field, value)
    await db.flush()
    return await _detail_or_404(db, lead_id)


@router.post("/{lead_id}/attribution", response_model=LeadDetail, status_code=status.HTTP_201_CREATED)
async def decide_attribution(
    lead_id: uuid.UUID,
    payload: AttributionDecisionCreate,
    db: AsyncSession = Depends(get_db),
    admin_id: uuid.UUID = Depends(admin_uuid),
):
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id).with_for_update())).scalar_one_or_none()
    if lead is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    try:
        await lead_service.record_decision(
            db, lead, payload.financial_attribution, payload.attribution_confidence, payload.reason, admin_id
        )
    except lead_service.LeadError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return await _detail_or_404(db, lead_id)


@router.post("/{lead_id}/invoices", response_model=InvoiceCreateResult, status_code=status.HTTP_201_CREATED)
async def add_invoice(
    lead_id: uuid.UUID,
    payload: InvoiceCreate,
    db: AsyncSession = Depends(get_db),
    admin_id: uuid.UUID = Depends(admin_uuid),
):
    """Lead → Ajouter une facture. Crée le Customer à la première facture et la commission si AFFRA_DIGITAL."""
    try:
        invoice, _customer, _commission, created = await billing_service.create_invoice_for_lead(
            db, lead_id, payload, admin_id
        )
    except billing_service.BillingError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    data = await reporting_service.get_invoice_out(db, invoice.id)
    return {"invoice": InvoiceOut.model_validate(data), "customer_created": created}
