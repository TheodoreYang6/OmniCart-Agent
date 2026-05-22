"""addresses 表 — SQLAlchemy ORM 模型。"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Boolean

from app.models import Base


class AddressModel(Base):
    __tablename__ = "addresses"

    address_id: str = Column(String(64), primary_key=True)
    user_id: str = Column(String(64), nullable=False, index=True)
    name: str = Column(String(64), nullable=False)
    phone: str = Column(String(32), nullable=False)
    province: str = Column(String(32), default="")
    city: str = Column(String(32), default="")
    district: str = Column(String(32), default="")
    detail: str = Column(String(256), default="")
    is_default: bool = Column(Boolean, default=False)
    created_at: datetime = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<Address {self.address_id} {self.name}>"
