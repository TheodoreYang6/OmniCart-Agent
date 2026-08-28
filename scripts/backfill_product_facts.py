#!/usr/bin/env python
"""Backfill source-backed product facts from the raw catalog into PostgreSQL."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.config import USE_POSTGRES
from app.core.database import get_session_sync
from app.models.product_fact import ProductFactModel
from app.repositories.json_product_repo import JsonProductRepository
from app.services.product_facts import extract_product_facts


async def main_async(category: str = "", dry_run: bool = False) -> int:
    products = JsonProductRepository().list_all()
    if category:
        products = [p for p in products if p.category == category]
    rows = [fact for p in products for fact in extract_product_facts(p)]
    print(f"products={len(products)} facts={len(rows)} category={category or 'ALL'}")
    if dry_run or not USE_POSTGRES:
        return 0
    factory = get_session_sync()
    if factory is None:
        raise RuntimeError("PostgreSQL is not configured")
    async with factory() as session:
        product_ids = [p.product_id for p in products]
        if product_ids:
            from sqlalchemy import delete
            await session.execute(delete(ProductFactModel).where(ProductFactModel.product_id.in_(product_ids)))
        session.add_all([
            ProductFactModel(product_id=f.product_id, fact_key=f.fact_key, value_text=f.value_text,
                             value_number=f.value_number, unit=f.unit, source_type=f.source_type,
                             source_text=f.source_text, source_ref=f.source_ref or {}, verified=f.verified,
                             extractor=f.extractor)
            for f in rows
        ])
        await session.commit()
    return len(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--category", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main_async(args.category, args.dry_run))
