"""Visual Agent 的数据结构"""
from pydantic import BaseModel, Field


class VisualEvidence(BaseModel):
    field: str
    value: str
    confidence: float = 0.5
    evidence_id: str = ""


class VisualResult(BaseModel):
    product_name: str | None = None
    brand: str | None = None
    category: str | None = None       # 新增：商品类别
    specs: str | None = None           # 新增：关键规格
    price: float | None = None
    capacity: str | None = None        # 保留兼容
    power: str | None = None           # 保留兼容
    ports: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    evidence_list: list[VisualEvidence] = Field(default_factory=list)
    raw_response: str = ""
    fallback_level: int = 0
