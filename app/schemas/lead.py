import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import (
    AttributionConfidence,
    FinancialAttribution,
    LeadChannel,
    LeadStatus,
    MarketingSource,
)

_PHONE = r"^\+?[0-9 .\-]{6,20}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LeadCreate(_Strict):
    """Création manuelle (appel téléphonique, email…).

    Sans click téléphone associé, la source est celle déclarée par le prospect.
    """

    prenom: str | None = Field(None, max_length=100)
    nom: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    telephone: str | None = Field(None, pattern=_PHONE)
    ville: str | None = Field(None, max_length=100)
    channel: LeadChannel = LeadChannel.PHONE
    notes: str | None = Field(None, max_length=5000)

    # Origine web (au plus une des deux) : un prospect entier, ou un événement de contact précis.
    visitor_id: uuid.UUID | None = None
    phone_click_event_id: uuid.UUID | None = None
    declared_source: MarketingSource | None = None

    financial_attribution: FinancialAttribution
    attribution_confidence: AttributionConfidence
    reason: str = Field(..., min_length=5, max_length=1000)

    @model_validator(mode="after")
    def _contact_required(self) -> "LeadCreate":
        if self.visitor_id and self.phone_click_event_id:
            raise ValueError("visitor_id et phone_click_event_id sont exclusifs")
        if not (self.email or self.telephone):
            raise ValueError("email ou téléphone requis")
        if not (self.prenom or self.nom):
            raise ValueError("prénom ou nom requis")
        return self


class LeadUpdate(_Strict):
    """Coordonnées et suivi. L'attribution financière n'est PAS modifiable ici (cf. /attribution)."""

    prenom: str | None = Field(None, max_length=100)
    nom: str | None = Field(None, max_length=100)
    email: EmailStr | None = None
    telephone: str | None = Field(None, pattern=_PHONE)
    ville: str | None = Field(None, max_length=100)
    status: LeadStatus | None = None
    notes: str | None = Field(None, max_length=5000)


class AttributionDecisionCreate(_Strict):
    financial_attribution: FinancialAttribution
    attribution_confidence: AttributionConfidence
    reason: str = Field(..., min_length=5, max_length=1000)


class LeadListItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    prenom: str | None
    nom: str | None
    email: str | None
    telephone: str | None
    ville: str | None
    channel: str
    marketing_source: str
    financial_attribution: str
    attribution_confidence: str
    status: str
    customer_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class LeadListResponse(BaseModel):
    items: list[LeadListItem]
    total: int
    limit: int
    offset: int


class TouchOut(BaseModel):
    source: str | None
    medium: str | None
    campaign: str | None
    referrer: str | None
    landing_page: str | None


class VisitorOut(BaseModel):
    id: uuid.UUID
    first_seen_at: datetime
    last_seen_at: datetime
    first_touch: TouchOut
    last_touch: TouchOut
    has_google_click_id: bool


class EventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    source: str
    medium: str | None
    campaign: str | None
    referrer: str | None
    landing_page: str | None
    page_path: str | None
    metadata: dict[str, Any]
    devis_id: uuid.UUID | None
    created_at: datetime


class DecisionOut(BaseModel):
    id: uuid.UUID
    decision: str
    confidence: str
    previous_decision: str | None
    previous_confidence: str | None
    reason: str
    created_by: uuid.UUID | None
    created_by_email: str | None
    created_at: datetime


class DevisSummary(BaseModel):
    id: uuid.UUID
    created_at: datetime
    statut: str
    type_client: str | None
    ville: str | None

    model_config = {"from_attributes": True}


class CustomerOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    billing_name: str
    billing_address_line1: str
    billing_address_line2: str | None
    billing_postal_code: str
    billing_city: str
    billing_country: str
    billing_email: str | None
    billing_siret: str | None
    billing_vat_number: str | None

    model_config = {"from_attributes": True}


class LeadInvoiceSummary(BaseModel):
    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    total_ht_cents: int
    total_ttc_cents: int
    commission_amount_cents: int | None
    commission_status: str | None


class LeadDetail(LeadListItem):
    marketing_medium: str | None
    marketing_campaign: str | None
    notes: str | None
    updated_at: datetime
    visitor: VisitorOut | None
    events: list[EventOut]
    decisions: list[DecisionOut]
    devis: list[DevisSummary]
    customer: CustomerOut | None
    invoices: list[LeadInvoiceSummary]


class PhoneClickOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    source: str
    medium: str | None
    page_path: str | None
    visitor_id: uuid.UUID | None


class ProspectItem(BaseModel):
    """Visiteur ayant agi (clic contact, devis commencé) mais pas encore rattaché à un lead."""

    visitor_id: uuid.UUID
    first_seen_at: datetime
    last_event_at: datetime
    last_event_type: str
    last_page_path: str | None
    events_count: int
    phone_clicks: int
    email_clicks: int
    whatsapp_clicks: int
    quote_started: int
    first_touch: TouchOut
    last_touch: TouchOut


class ProspectListResponse(BaseModel):
    items: list[ProspectItem]
    total: int
    limit: int
    offset: int
