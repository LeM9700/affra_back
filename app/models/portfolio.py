import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    titre: Mapped[str] = mapped_column(String(300), nullable=False)
    type_client: Mapped[str | None] = mapped_column(String(50))
    type_borne: Mapped[str | None] = mapped_column(String(100))
    puissance_kw: Mapped[float | None] = mapped_column(Numeric(6, 1))
    ville: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    image_urls: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    subvention_obtenue: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
