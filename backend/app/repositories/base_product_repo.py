"""产品仓库抽象基类 — 所有产品存储实现必须继承此类。"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from app.schemas.product import Product

# 品类目录名 → 中文分类名
_CATEGORY_DIRS = {
    "1_美妆护肤": "美妆护肤",
    "2_数码电子": "数码电子",
    "3_服饰运动": "服饰运动",
    "4_食品生活": "食品饮料",
    "5_家居用品": "家居用品",
    "6_母婴用品": "母婴用品",
    "7_运动户外": "运动户外",
    "8_个护清洁": "个护清洁",
}

_DATASET_DIR = Path(__file__).parent.parent.parent.parent / "ecommerce_agent_dataset"


class BaseProductRepository(ABC):
    """产品仓库抽象基类。

    定义同步接口 — 所有实现（JSON / PostgreSQL / 其他）必须实现这些方法。
    PG 实现内部用 loop.run_until_complete 桥接异步查询。
    """

    @abstractmethod
    def get_by_id(self, product_id: str) -> Optional[Product]:
        ...

    @abstractmethod
    def list_all(self) -> list[Product]:
        ...

    @abstractmethod
    def filter_by(
        self,
        category: str | None = None,
        sub_category: str | None = None,
        brand: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[Product]:
        ...

    @abstractmethod
    def search_text(self, query: str, top_k: int = 20) -> list[Product]:
        ...

    @abstractmethod
    def get_categories(self) -> list[str]:
        ...

    @abstractmethod
    def get_sub_categories(self, category: str | None = None) -> list[str]:
        ...

    @property
    @abstractmethod
    def total_count(self) -> int:
        ...

    def resolve_image_url(self, product_id: str, base_url: str = "") -> str:
        """V4: 返回新图片 API 路径。"""
        product = self.get_by_id(product_id)
        if not product or not product.image_path:
            return ""
        return f"/api/products/{product_id}/image"
