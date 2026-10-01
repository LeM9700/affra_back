"""Payloads PUBLICS d'attribution (émis par le navigateur via le proxy Next.js).

Validation stricte : champs inconnus refusés, longueurs bornées, metadata plate et limitée.
Aucun champ ne permet de fixer la source, le lead ou une donnée financière : tout est
dérivé côté serveur.
"""
import json
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

_CLICK_ID = r"^[A-Za-z0-9_\-\.]{1,255}$"
_META_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_FORBIDDEN_META_FRAGMENTS = (
    "token", "secret", "password", "passwd", "cookie", "session", "auth", "apikey", "api_key", "jwt", "credential",
)
MAX_METADATA_KEYS = 10
MAX_METADATA_VALUE_LENGTH = 200
MAX_METADATA_BYTES = 1024


def validate_metadata(value: dict[str, Any] | None) -> dict[str, Any]:
    if not value:
        return {}
    if len(value) > MAX_METADATA_KEYS:
        raise ValueError(f"metadata: {MAX_METADATA_KEYS} keys max")
    clean: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not _META_KEY.match(key):
            raise ValueError("metadata: invalid key")
        if any(fragment in key for fragment in _FORBIDDEN_META_FRAGMENTS):
            raise ValueError(f"metadata: forbidden key '{key}'")
        if item is None or isinstance(item, bool):
            clean[key] = item
        elif isinstance(item, int):
            if abs(item) > 10**12:
                raise ValueError("metadata: integer out of range")
            clean[key] = item
        elif isinstance(item, str):
            if len(item) > MAX_METADATA_VALUE_LENGTH:
                raise ValueError("metadata: value too long")
            clean[key] = item
        else:
            # Pas d'objets imbriqués, de listes ni de flottants.
            raise ValueError("metadata: only flat str/int/bool/null values are allowed")
    if len(json.dumps(clean, ensure_ascii=False).encode("utf-8")) > MAX_METADATA_BYTES:
        raise ValueError("metadata: too large")
    return clean


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class VisitIn(_StrictModel):
    anonymous_id: uuid.UUID
    client_event_id: uuid.UUID | None = None
    landing_page: str = Field(..., min_length=1, max_length=2048)
    referrer: str | None = Field(None, max_length=2048)
    utm_source: str | None = Field(None, max_length=100)
    utm_medium: str | None = Field(None, max_length=100)
    utm_campaign: str | None = Field(None, max_length=150)
    gclid: str | None = Field(None, pattern=_CLICK_ID)
    gbraid: str | None = Field(None, pattern=_CLICK_ID)
    wbraid: str | None = Field(None, pattern=_CLICK_ID)


class EventIn(_StrictModel):
    anonymous_id: uuid.UUID
    client_event_id: uuid.UUID
    event_type: Literal["QUOTE_STARTED", "PHONE_CLICK", "EMAIL_CLICK", "WHATSAPP_CLICK"]
    page_path: str | None = Field(None, max_length=2048)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata", mode="before")
    @classmethod
    def _check_metadata(cls, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("metadata must be an object")
        return validate_metadata(value)


class AttributionAck(BaseModel):
    accepted: bool = True
