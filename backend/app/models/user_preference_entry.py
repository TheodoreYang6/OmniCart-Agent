"""UserPreferenceEntry — 独立偏好条目，一条一行，category 索引检索。"""

from datetime import datetime, timezone
from sqlalchemy import String, Text, Float, Boolean, DateTime, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models import Base


def _utcnow():
    return datetime.now(timezone.utc)


class UserPreferenceEntry(Base):
    __tablename__ = "user_preference_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_id: Mapped[str] = mapped_column(String(32), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    sub_category: Mapped[str] = mapped_column(String(64), default="")
    brands: Mapped[list] = mapped_column(JSONB, default=list)
    devices: Mapped[list] = mapped_column(JSONB, default=list)
    scenarios: Mapped[list] = mapped_column(JSONB, default=list)
    budget_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    budget_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    avoid_tags: Mapped[list] = mapped_column(JSONB, default=list)
    must_tags: Mapped[list] = mapped_column(JSONB, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "user_id": self.user_id,
            "raw_text": self.raw_text,
            "category": self.category or "",
            "sub_category": self.sub_category or "",
            "brands": self.brands or [],
            "devices": self.devices or [],
            "scenarios": self.scenarios or [],
            "budget_min": self.budget_min,
            "budget_max": self.budget_max,
            "avoid_tags": self.avoid_tags or [],
            "must_tags": self.must_tags or [],
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else "",
            "updated_at": self.updated_at.isoformat() if self.updated_at else "",
        }
