import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.billing import InvoiceCreate


class CheckOut(BaseModel):
    code: str
    level: Literal["ok", "warning", "blocking"]
    message: str


class InvoiceDocumentOut(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    invoice_id: uuid.UUID | None
    status: Literal["PENDING_REVIEW", "CONFIRMED", "REJECTED"]
    original_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    extraction_method: Literal["PDF_TEXT", "AI", "NONE"]
    extraction: dict[str, Any]
    analysis: list[CheckOut]
    confirmation: dict[str, Any] | None
    rejection_reason: str | None
    created_at: datetime
    reviewed_at: datetime | None

    model_config = {"from_attributes": True}


class InvoiceDocumentConfirm(BaseModel):
    """Facture validée par l'humain + un motif par code d'avertissement accepté."""

    model_config = ConfigDict(extra="forbid")

    invoice: InvoiceCreate
    acknowledgements: dict[str, str] = Field(default_factory=dict, max_length=30)

    @field_validator("acknowledgements")
    @classmethod
    def _bounded(cls, value: dict[str, str]) -> dict[str, str]:
        for code, reason in value.items():
            if len(code) > 40 or len(reason) > 500:
                raise ValueError("motif trop long (500 caractères maximum)")
        return value


class InvoiceDocumentReject(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(..., min_length=5, max_length=500)


class FileUrlOut(BaseModel):
    url: str
    expires_in: int
