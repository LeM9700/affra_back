import uuid

from pydantic import BaseModel, Field, model_validator

from app.services.slug import SLUG_PATTERN, slugify


class ZoneCreate(BaseModel):
    ville: str = Field(..., min_length=1, max_length=100)
    # Facultatif : déduit du nom si absent. À renseigner quand le nom affiché diffère du slug du front.
    slug: str | None = Field(None, max_length=120, pattern=SLUG_PATTERN)
    departement: str = Field(..., pattern=r"^(34|30)$")
    active: bool = True

    @model_validator(mode="after")
    def default_slug(self) -> "ZoneCreate":
        """Déduit le slug du nom de commune quand il n'est pas fourni."""
        if self.slug is None:
            self.slug = slugify(self.ville)
            if not self.slug:
                raise ValueError("Impossible de déduire un slug de ce nom de ville")
        return self


class ZoneUpdate(BaseModel):
    ville: str | None = Field(None, min_length=1, max_length=100)
    slug: str | None = Field(None, max_length=120, pattern=SLUG_PATTERN)
    departement: str | None = Field(None, pattern=r"^(34|30)$")
    active: bool | None = None


class ZonePublic(BaseModel):
    id: uuid.UUID
    ville: str
    slug: str
    departement: str
    active: bool

    model_config = {"from_attributes": True}
