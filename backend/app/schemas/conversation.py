"""Conversation & ConversationMessage Pydantic schemas."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    user_id: str = ""
    session_id: str = ""
    title: str = ""


class ConversationUpdate(BaseModel):
    title: str | None = None
    status: str | None = None  # active / archived
    summary: str | None = None


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    conversation_id: str
    user_id: str
    session_id: str
    title: str
    status: str = "active"
    summary: str | None = None
    last_message: str = ""  # Memory Lite: 最后一条消息预览
    context_snapshot: dict = Field(default_factory=dict)  # Memory Lite: 购物任务上下文
    created_at: datetime | None = None
    updated_at: datetime | None = None

class MessageCreate(BaseModel):
    conversation_id: str
    user_id: str = ""
    session_id: str = ""
    role: str  # user / assistant / system
    content: str
    image_url: str | None = None
    product_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: str
    conversation_id: str
    user_id: str
    session_id: str
    role: str
    content: str
    image_url: str | None = None
    product_refs: list = Field(default_factory=list)
    evidence_refs: list = Field(default_factory=list)
    memory_refs: list = Field(default_factory=list)
    created_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
