import uuid

from pydantic import BaseModel, Field


class ZoneCreate(BaseModel):
    ville: str = Field(..., min_length=1, max_length=100)
    departement: str = Field(..., pattern=r"^(34|30)$")
    active: bool = True


class ZoneUpdate(BaseModel):
    ville: str | None = None
    departement: str | None = None
    active: bool | None = None


class ZonePublic(BaseModel):
    id: uuid.UUID
    ville: str
    departement: str
    active: bool

    model_config = {"from_attributes": True}
