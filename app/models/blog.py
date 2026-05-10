import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BlogPost(Base):
    __tablename__ = "blog_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    titre: Mapped[str] = mapped_column(String(300), nullable=False)
    contenu_markdown: Mapped[str | None] = mapped_column(Text)
    meta_description: Mapped[str | None] = mapped_column(String(160))
    og_image_url: Mapped[str | None] = mapped_column(String(500))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=_now)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
