from pydantic import BaseModel, Field


class SkuProperty(BaseModel):
    """SKU 属性键值对，如 {'存储': '256GB', '颜色': '宇宙橙'}"""
    # 使用 dict 类型兼容任意属性名
    pass


class Sku(BaseModel):
    sku_id: str
    properties: dict[str, str] = Field(default_factory=dict)
    price: float


class FaqItem(BaseModel):
    question: str
    answer: str


class ReviewItem(BaseModel):
    nickname: str
    rating: int  # 1-5
    content: str


class RagKnowledge(BaseModel):
    marketing_description: str = ""
    official_faq: list[FaqItem] = Field(default_factory=list)
    user_reviews: list[ReviewItem] = Field(default_factory=list)


class Product(BaseModel):
    product_id: str
    title: str
    brand: str
    category: str  # 美妆护肤 / 数码电子 / 服饰运动 / 食品饮料
    sub_category: str = ""
    base_price: float
    image_path: str = ""  # 数据集内相对路径
    skus: list[Sku] = Field(default_factory=list)
    rag_knowledge: RagKnowledge | None = None
