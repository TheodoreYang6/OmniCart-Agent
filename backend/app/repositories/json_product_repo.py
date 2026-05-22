"""JSON 文件产品仓库 — 从 ecommerce_agent_dataset/ 加载 100 件商品到内存。"""

import json
from pathlib import Path
from typing import Optional

from app.repositories.base_product_repo import (
    BaseProductRepository,
    _CATEGORY_DIRS,
    _DATASET_DIR,
)
from app.schemas.product import Product


class JsonProductRepository(BaseProductRepository):
    """从本地 JSON 文件加载产品数据，全部缓存在内存中。

    V0 默认实现。当 USE_POSTGRES=false 时使用。
    """

    def __init__(self, data_root: Path | None = None):
        self._root = data_root or _DATASET_DIR
        self._products: list[Product] = []
        self._by_id: dict[str, Product] = {}
        self._load()

    def _load(self):
        self._products.clear()
        self._by_id.clear()

        for dir_name in _CATEGORY_DIRS:
            data_dir = self._root / dir_name / "data"
            if not data_dir.is_dir():
                continue
            for json_file in sorted(data_dir.glob("*.json")):
                try:
                    raw = json.loads(json_file.read_text(encoding="utf-8"))
                    product = Product(**raw)
                    self._products.append(product)
                    self._by_id[product.product_id] = product
                except Exception:
                    continue

    def reload(self):
        self._load()

    # ---- 同步接口实现 ----

    def get_by_id(self, product_id: str) -> Optional[Product]:
        return self._by_id.get(product_id)

    def list_all(self) -> list[Product]:
        return list(self._products)

    def filter_by(
        self,
        category: str | None = None,
        sub_category: str | None = None,
        brand: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[Product]:
        results = self._products
        if category:
            results = [p for p in results if p.category == category]
        if sub_category:
            results = [p for p in results if p.sub_category == sub_category]
        if brand:
            results = [p for p in results if brand in p.brand]
        if price_max is not None:
            results = [p for p in results if p.base_price <= price_max]
        if price_min is not None:
            results = [p for p in results if p.base_price >= price_min]
        return results

    def search_text(self, query: str, top_k: int = 20) -> list[Product]:
        query_lower = query.lower()
        scored: list[tuple[Product, float]] = []

        for p in self._products:
            score = 0.0
            text_pool = [p.title, p.brand, p.category, p.sub_category]

            if p.rag_knowledge:
                text_pool.append(p.rag_knowledge.marketing_description)
                for faq in p.rag_knowledge.official_faq:
                    text_pool.append(faq.question)
                    text_pool.append(faq.answer)
                for rev in p.rag_knowledge.user_reviews:
                    text_pool.append(rev.content)

            full_text = " ".join(text_pool).lower()

            for kw in query_lower.split():
                if kw in full_text:
                    score += 1.0
            for i in range(len(query) - 1):
                bigram = query_lower[i:i + 2]
                if bigram in full_text:
                    score += 0.5

            if score > 0:
                scored.append((p, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [p for p, _ in scored[:top_k]]

    def get_categories(self) -> list[str]:
        return sorted(set(p.category for p in self._products))

    def get_sub_categories(self, category: str | None = None) -> list[str]:
        products = self.filter_by(category=category) if category else self._products
        return sorted(set(p.sub_category for p in products if p.sub_category))

    @property
    def total_count(self) -> int:
        return len(self._products)
