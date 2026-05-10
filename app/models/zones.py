import uuid

from sqlalchemy import Boolean, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Zone(Base):
    __tablename__ = "zones"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ville: Mapped[str] = mapped_column(String(100), nullable=False)
    departement: Mapped[str] = mapped_column(String(10), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
