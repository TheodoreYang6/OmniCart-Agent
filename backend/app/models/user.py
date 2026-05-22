"""users 表 — SQLAlchemy ORM 模型。"""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Boolean

from app.models import Base


class UserModel(Base):
    __tablename__ = "users"

    user_id: str = Column(String(64), primary_key=True)
    username: str = Column(String(64), unique=True, nullable=False, index=True)
    password_hash: str = Column(String(256), nullable=False)
    email: str = Column(String(128), default="")
    phone: str = Column(String(32), default="")
    avatar_url: str = Column(String(512), default="")
    is_active: bool = Column(Boolean, default=True)
    token: str = Column(String(128), default="")
    created_at: datetime = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: datetime = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<User {self.user_id} {self.username}>"
