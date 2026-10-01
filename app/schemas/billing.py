import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

MAX_LINE_AMOUNT_CENTS = 100_000_000_000  # 1 milliard d'euros : garde-fou contre les fautes de frappe


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class BillingInfo(_Strict):
    name: str = Field(..., min_length=1, max_length=200)
    address_line1: str = Field(..., min_length=1, max_length=200)
    address_line2: str | None = Field(None, max_length=200)
    postal_code: str = Field(..., pattern=r"^[0-9A-Za-z \-]{3,10}$")
    city: str = Field(..., min_length=1, max_length=100)
    country: str = Field("France", min_length=2, max_length=60)
    email: EmailStr | None = None
    siret: str | None = Field(None, pattern=r"^\d{14}$")
    vat_number: str | None = Field(None, pattern=r"^[A-Z]{2}[0-9A-Z]{2,13}$")


class InvoiceLineIn(_Strict):
    description: str = Field(..., min_length=1, max_length=500)
    quantity: Decimal = Field(..., gt=0, le=100_000, max_digits=12, decimal_places=2)
    unit: str | None = Field(None, max_length=20)
    unit_price_ht_cents: int = Field(..., ge=0, le=MAX_LINE_AMOUNT_CENTS, strict=True)
    vat_rate_bp: Literal[0, 550, 1000, 2000] = 2000


class InvoiceCreate(_Strict):
    """Numéro optionnel : sans numéro, numérotation automatique continue FA-AAAA-NNNN."""

    invoice_number: str | None = Field(None, pattern=r"^[A-Za-z0-9][A-Za-z0-9\-_/.]{0,39}$")
    invoice_date: date
    service_date: date | None = None
    due_date: date | None = None
    billing: BillingInfo
    lines: list[InvoiceLineIn] = Field(..., min_length=1, max_length=50)
    payment_terms: str | None = Field(None, max_length=500)
    notes: str | None = Field(None, max_length=1000)
    external_reference: str | None = Field(None, max_length=100)

    @model_validator(mode="after")
    def _check_dates(self) -> "InvoiceCreate":
        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
        if self.invoice_date > tomorrow:
            raise ValueError("invoice_date ne peut pas être dans le futur")
        if self.due_date and self.due_date < self.invoice_date:
            raise ValueError("due_date doit être postérieure à invoice_date")
        return self


class InvoiceLineOut(BaseModel):
    position: int
    description: str
    quantity: Decimal
    unit: str | None
    unit_price_ht_cents: int
    vat_rate_bp: int
    total_ht_cents: int

    model_config = {"from_attributes": True}


class CommissionOut(BaseModel):
    id: uuid.UUID
    invoice_amount_cents: int
    number_of_brackets: int
    commission_amount_cents: int
    status: str
    paid_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class VatBreakdown(BaseModel):
    vat_rate_bp: int
    base_ht_cents: int
    vat_cents: int


class InvoiceOut(BaseModel):
    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    service_date: date | None
    due_date: date
    customer_id: uuid.UUID
    lead_id: uuid.UUID
    total_ht_cents: int
    total_vat_cents: int
    total_ttc_cents: int
    vat_breakdown: list[VatBreakdown]
    billing_name: str
    billing_address_line1: str
    billing_address_line2: str | None
    billing_postal_code: str
    billing_city: str
    billing_country: str
    billing_email: str | None
    billing_siret: str | None
    billing_vat_number: str | None
    seller: dict[str, Any]
    payment_terms: str | None
    notes: str | None
    external_reference: str | None
    lines: list[InvoiceLineOut]
    commission: CommissionOut | None
    marketing_source: str
    financial_attribution: str
    created_at: datetime


class InvoiceCreateResult(BaseModel):
    invoice: InvoiceOut
    customer_created: bool


class InvoiceListItem(BaseModel):
    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    billing_name: str
    lead_id: uuid.UUID
    customer_id: uuid.UUID
    total_ht_cents: int
    total_ttc_cents: int
    commission_amount_cents: int | None
    commission_status: str | None


class InvoiceListResponse(BaseModel):
    items: list[InvoiceListItem]
    total: int
    limit: int
    offset: int


class CommissionListItem(BaseModel):
    id: uuid.UUID
    invoice_id: uuid.UUID
    invoice_number: str
    invoice_date: date
    customer_name: str
    lead_id: uuid.UUID
    marketing_source: str
    financial_attribution: str
    invoice_amount_cents: int
    number_of_brackets: int
    commission_amount_cents: int
    status: str
    paid_at: datetime | None


class CommissionListResponse(BaseModel):
    items: list[CommissionListItem]
    total: int
    limit: int
    offset: int


class SourceCount(BaseModel):
    source: str
    count: int


class AttributionStats(BaseModel):
    leads_total: int
    leads_digital: int
    leads_to_arbitrate: int
    customers_digital: int
    invoiced_attributed_ht_cents: int
    invoices_attributed: int
    brackets_total: int
    commission_total_cents: int
    commission_due_cents: int
    commission_paid_cents: int
    leads_by_source: list[SourceCount]
