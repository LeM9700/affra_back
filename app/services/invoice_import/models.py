"""Données extraites d'une facture importée (avant validation humaine)."""

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Literal

ExtractionMethod = Literal["PDF_TEXT", "AI", "NONE"]


@dataclass
class ExtractedLine:
    description: str
    quantity: Decimal
    unit: str | None
    unit_price_ht_cents: int
    discount_bp: int  # remise en points de base : 1000 = 10 %
    total_ht_cents: int
    vat_rate_bp: int
    code: str | None = None


@dataclass
class ExtractedInvoice:
    method: ExtractionMethod
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    external_quote_ref: str | None = None
    external_customer_ref: str | None = None
    seller_siret: str | None = None
    seller_vat_number: str | None = None
    client_name: str | None = None
    client_address_line1: str | None = None
    client_postal_code: str | None = None
    client_city: str | None = None
    client_country: str | None = None
    lines: list[ExtractedLine] = field(default_factory=list)
    total_ht_cents: int | None = None
    total_vat_cents: int | None = None
    total_ttc_cents: int | None = None
    payment_terms: str | None = None
    paid_stamp: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        """Version sérialisable (JSONB) : dates ISO, quantités en texte."""

        def convert(value: Any) -> Any:
            if isinstance(value, Decimal):
                return str(value)
            if isinstance(value, date):
                return value.isoformat()
            if isinstance(value, list):
                return [convert(v) for v in value]
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            return value

        return convert(asdict(self))
