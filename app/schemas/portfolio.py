import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class PortfolioItemCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=200, pattern=r"^[a-z0-9-]+$")
    titre: str = Field(..., min_length=1, max_length=300)
    type_client: str | None = Field(None, max_length=50)
    type_borne: str | None = Field(None, max_length=100)
    puissance_kw: Decimal | None = None
    ville: str | None = Field(None, max_length=100)
    description: str | None = None
    image_urls: list[str] | None = None
    subvention_obtenue: str | None = Field(None, max_length=100)
    published: bool = False


class PortfolioItemUpdate(BaseModel):
    titre: str | None = Field(None, min_length=1, max_length=300)
    type_client: str | None = None
    type_borne: str | None = None
    puissance_kw: Decimal | None = None
    ville: str | None = None
    description: str | None = None
    image_urls: list[str] | None = None
    subvention_obtenue: str | None = None
    published: bool | None = None


class PortfolioItemPublic(BaseModel):
    id: uuid.UUID
    slug: str
    titre: str
    type_client: str | None
    type_borne: str | None
    puissance_kw: Decimal | None
    ville: str | None
    description: str | None
    image_urls: list[str] | None
    subvention_obtenue: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
