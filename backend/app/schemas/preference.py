"""Preference Schemas。"""

from pydantic import BaseModel, Field


class PreferenceUpdate(BaseModel):
    category: str | None = None
    sub_category: str | None = None
    budget_max: float | None = None
    budget_min: float | None = None
    scenario: str | None = None
    must_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)


class PreferenceResponse(BaseModel):
    session_id: str
    preferences: dict
