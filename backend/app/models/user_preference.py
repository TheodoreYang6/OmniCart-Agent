"""user_preferences 表 — SQLAlchemy ORM 模型。"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB

from app.models import Base


class UserPreferenceModel(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_user_preferences_session_user"),
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    session_id: str = Column(String(64), nullable=False, index=True)
    user_id: str = Column(String(64), nullable=True)
    preferences: dict = Column(JSONB, nullable=False, default=dict)
    created_at: datetime = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<UserPreference session={self.session_id}>"
