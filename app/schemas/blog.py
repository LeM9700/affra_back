import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BlogPostCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=200, pattern=r"^[a-z0-9-]+$")
    titre: str = Field(..., min_length=1, max_length=300)
    contenu_markdown: str | None = None
    meta_description: str | None = Field(None, max_length=160)
    og_image_url: str | None = Field(None, max_length=500)
    published_at: datetime | None = None
    published: bool = False


class BlogPostUpdate(BaseModel):
    titre: str | None = Field(None, min_length=1, max_length=300)
    contenu_markdown: str | None = None
    meta_description: str | None = Field(None, max_length=160)
    og_image_url: str | None = Field(None, max_length=500)
    published_at: datetime | None = None
    published: bool | None = None


class BlogPostPublic(BaseModel):
    id: uuid.UUID
    slug: str
    titre: str
    contenu_markdown: str | None
    meta_description: str | None
    og_image_url: str | None
    published_at: datetime | None
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class BlogPostListItem(BaseModel):
    id: uuid.UUID
    slug: str
    titre: str
    meta_description: str | None
    og_image_url: str | None
    published_at: datetime | None

    model_config = {"from_attributes": True}
