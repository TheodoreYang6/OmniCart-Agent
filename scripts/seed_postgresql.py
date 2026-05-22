#!/usr/bin/env python
"""JSON → PostgreSQL 产品迁移脚本。

将 ecommerce_agent_dataset/ 中的 100 件商品导入 PostgreSQL products 表。
幂等：已存在的 product_id 会自动更新。

用法:
    python scripts/seed_postgresql.py

前置条件:
    - .env 中 DATABASE_URL 已配置
    - PostgreSQL 服务已启动
"""

import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.core.config import DATABASE_URL, USE_POSTGRES
from app.models import Base
from app.repositories.json_product_repo import JsonProductRepository
from app.models.product import ProductModel
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert


async def main_async():
    if not USE_POSTGRES:
        print("DATABASE_URL is empty — 请先在 .env 中配置 DATABASE_URL")
        sys.exit(1)

    print(f"连接 PostgreSQL: {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # 建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("表结构已就绪（create_all）")

    # 从 JSON 加载产品
    json_repo = JsonProductRepository()
    products = json_repo.list_all()
    print(f"从 JSON 加载 {len(products)} 件产品")

    # 批量写入 PostgreSQL
    count = 0
    async with session_factory() as session:
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

    # 确认
    async with session_factory() as session:
        result = await session.execute(
            select(func.count()).select_from(ProductModel)
        )
        total = result.scalar()
    print(f"迁移完成！共 {total} 件商品写入 PostgreSQL")

    # 按品类统计
    async with session_factory() as session:
        result = await session.execute(
            select(ProductModel.category, func.count())
            .group_by(ProductModel.category)
            .order_by(ProductModel.category)
        )
        for cat, cnt in result:
            print(f"  {cat}: {cnt} 件")

    await engine.dispose()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
