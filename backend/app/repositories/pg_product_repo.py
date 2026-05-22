"""PostgreSQL 产品仓库 — 使用 SQLAlchemy 2.0 async + asyncpg 驱动。"""

import asyncio
from typing import Optional

import nest_asyncio
from sqlalchemy import select, func, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import get_session_sync
from app.models.product import ProductModel
from app.repositories.base_product_repo import BaseProductRepository
from app.schemas.product import Product

_nest_patched = False


class PgProductRepository(BaseProductRepository):
    """PostgreSQL 产品仓库。

    所有公开方法均为同步（满足 BaseProductRepository 接口），
    内部通过 nest_asyncio + loop.run_until_complete 桥接异步查询。
    """

    def _run(self, coro):
        global _nest_patched
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        if not _nest_patched:
            nest_asyncio.apply(loop)
            _nest_patched = True

        return loop.run_until_complete(coro)

    # ---- 异步实现 ----

    async def _aget_by_id(self, product_id: str) -> Optional[Product]:
        factory = get_session_sync()
        if factory is None:
            return None
        async with factory() as session:
            row = await session.get(ProductModel, product_id)
            if row is None:
                return None
            return self._row_to_product(row)

    async def _alist_all(self) -> list[Product]:
        factory = get_session_sync()
        if factory is None:
            return []
        async with factory() as session:
            result = await session.execute(select(ProductModel))
            return [self._row_to_product(r) for r in result.scalars()]

    async def _afilter_by(
        self,
        category: str | None = None,
        sub_category: str | None = None,
        brand: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[Product]:
        factory = get_session_sync()
        if factory is None:
            return []
        stmt = select(ProductModel)
        if category:
            stmt = stmt.where(ProductModel.category == category)
        if sub_category:
            stmt = stmt.where(ProductModel.sub_category == sub_category)
        if brand:
            stmt = stmt.where(ProductModel.brand.ilike(f"%{brand}%"))
        if price_max is not None:
            stmt = stmt.where(ProductModel.base_price <= price_max)
        if price_min is not None:
            stmt = stmt.where(ProductModel.base_price >= price_min)

        async with factory() as session:
            result = await session.execute(stmt)
            return [self._row_to_product(r) for r in result.scalars()]

    async def _asearch_text(self, query: str, top_k: int = 20) -> list[Product]:
        """PostgreSQL 全文搜索。汇总 title + brand + marketing_description + reviews + FAQ。"""
        factory = get_session_sync()
        if factory is None:
            return []

        query_terms = " & ".join(q for q in query.split() if len(q) > 1)
        if not query_terms:
            query_terms = query

        async with factory() as session:
            stmt = (
                select(ProductModel)
                .where(
                    text(
                        "to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(brand,'') || ' ' || "
                        "coalesce(rag_knowledge->>'marketing_description','')) "
                        "@@ to_tsquery('simple', :q)"
                    ).bindparams(q=query_terms)
                )
                .limit(top_k)
            )
            result = await session.execute(stmt)
            rows = [self._row_to_product(r) for r in result.scalars()]
            if not rows:
                # 降级：ILIKE 模糊匹配
                ilike_stmt = (
                    select(ProductModel)
                    .where(
                        func.concat(
                            ProductModel.title, " ",
                            ProductModel.brand, " ",
                            func.coalesce(
                                ProductModel.rag_knowledge["marketing_description"]
                                .as_string(), ""
                            ),
                        ).ilike(f"%{query}%")
                    )
                    .limit(top_k)
                )
                result = await session.execute(ilike_stmt)
                rows = [self._row_to_product(r) for r in result.scalars()]
            return rows

    async def _aget_categories(self) -> list[str]:
        factory = get_session_sync()
        if factory is None:
            return []
        async with factory() as session:
            result = await session.execute(
                select(ProductModel.category).distinct().order_by(ProductModel.category)
            )
            return sorted(set(result.scalars()))

    async def _aget_sub_categories(self, category: str | None = None) -> list[str]:
        factory = get_session_sync()
        if factory is None:
            return []
        stmt = select(ProductModel.sub_category).distinct().order_by(ProductModel.sub_category)
        if category:
            stmt = stmt.where(ProductModel.category == category)
        async with factory() as session:
            result = await session.execute(stmt)
            return sorted(set(s for s in result.scalars() if s))

    async def _atotal_count(self) -> int:
        factory = get_session_sync()
        if factory is None:
            return 0
        async with factory() as session:
            result = await session.execute(
                select(func.count()).select_from(ProductModel)
            )
            return result.scalar() or 0

    async def abulk_upsert(self, products: list[Product]) -> int:
        """批量写入产品（seed 脚本用）。"""
        factory = get_session_sync()
        if factory is None:
            return 0
        count = 0
        async with factory() as session:
            for p in products:
                stmt = pg_insert(ProductModel).values(
                    product_id=p.product_id,
                    title=p.title,
                    brand=p.brand,
                    category=p.category,
                    sub_category=p.sub_category,
                    base_price=p.base_price,
                    image_path=p.image_path,
                    skus=[s.model_dump() for s in p.skus] if p.skus else [],
                    rag_knowledge=p.rag_knowledge.model_dump() if p.rag_knowledge else {},
                ).on_conflict_do_update(
                    index_elements=["product_id"],
                    set_={
                        "title": p.title,
                        "brand": p.brand,
                        "category": p.category,
                        "sub_category": p.sub_category,
                        "base_price": p.base_price,
                        "image_path": p.image_path,
                        "skus": [s.model_dump() for s in p.skus] if p.skus else [],
                        "rag_knowledge": p.rag_knowledge.model_dump() if p.rag_knowledge else {},
                    },
                )
                await session.execute(stmt)
                count += 1
            await session.commit()
        return count

    # ---- 同步接口 ----

    def get_by_id(self, product_id: str) -> Optional[Product]:
        return self._run(self._aget_by_id(product_id))

    def list_all(self) -> list[Product]:
        return self._run(self._alist_all())

    def filter_by(
        self,
        category: str | None = None,
        sub_category: str | None = None,
        brand: str | None = None,
        price_max: float | None = None,
        price_min: float | None = None,
    ) -> list[Product]:
        return self._run(self._afilter_by(category, sub_category, brand, price_max, price_min))

    def search_text(self, query: str, top_k: int = 20) -> list[Product]:
        return self._run(self._asearch_text(query, top_k))

    def get_categories(self) -> list[str]:
        return self._run(self._aget_categories())

    def get_sub_categories(self, category: str | None = None) -> list[str]:
        return self._run(self._aget_sub_categories(category))

    @property
    def total_count(self) -> int:
        return self._run(self._atotal_count())

    # ---- 内部 ----

    @staticmethod
    def _row_to_product(row: ProductModel) -> Product:
        return Product(
            product_id=row.product_id,
            title=row.title,
            brand=row.brand,
            category=row.category,
            sub_category=row.sub_category,
            image_path=row.image_path or "",
            base_price=float(row.base_price),
            skus=row.skus or [],
            rag_knowledge=row.rag_knowledge or {},
        )
