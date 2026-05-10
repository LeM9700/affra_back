import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TestimonialCreate(BaseModel):
    initiales: str = Field(..., min_length=3, max_length=10)
    ville: str = Field(..., min_length=1, max_length=100)
    departement: str = Field(..., pattern=r"^(13|30|34)$")
    type_client: str = Field(..., pattern=r"^(maison|copropriete|entreprise|autre)$")
    type_projet: str | None = Field(None, max_length=120)
    resultat: str | None = Field(None, max_length=160)
    temoignage: str = Field(..., min_length=40, max_length=2000)
    source_channel: str = Field("formulaire_web", pattern=r"^(formulaire_web|email|whatsapp|sms|autre)$")
    consent_publication: bool = True
    website: str | None = Field(None, max_length=0)


class TestimonialStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(pending|approved|rejected)$")


class TestimonialPublic(BaseModel):
    id: uuid.UUID
    initiales: str
    ville: str
    departement: str
    type_client: str
    type_projet: str | None
    resultat: str | None
    temoignage: str
    source_channel: str
    consent_publication: bool
    status: str
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class TestimonialSeoItem(BaseModel):
    id: uuid.UUID
    initiales: str
    ville: str
    departement: str
    type_client: str
    type_projet: str | None
    resultat: str | None
    temoignage: str
    published_at: datetime | None

    model_config = {"from_attributes": True}
