"""PostgreSQL access for source-backed product facts.

The catalog can still run from its JSON fallback during local development, but
once the fact migration/backfill is deployed this repository becomes the
eligibility authority.  It intentionally returns ``None`` when the table is
not available so a partial migration cannot take recommendation traffic down.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.database import get_session_sync
from app.models.product_fact import ProductFactModel

logger = logging.getLogger(__name__)


class ProductFactRepository:
    async def facts_for_products(self, product_ids: list[str]) -> dict[str, list[dict]] | None:
        """Return persisted facts grouped by product, or ``None`` if unavailable."""
        product_ids = [str(pid) for pid in product_ids if pid]
        factory = get_session_sync()
        if not factory or not product_ids:
            return None
        try:
            async with factory() as session:
                rows = (await session.execute(
                    select(ProductFactModel).where(ProductFactModel.product_id.in_(product_ids))
                )).scalars().all()
        except Exception as exc:  # migration / connection failures use deterministic catalog fallback
            logger.info("product facts store unavailable; using catalog extraction: %s", exc)
            return None
        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row.product_id, []).append({
                "product_id": row.product_id,
                "fact_key": row.fact_key,
                "value_text": row.value_text,
                "value_number": row.value_number,
                "unit": row.unit,
                "source_type": row.source_type,
                "source_text": row.source_text,
                "source_ref": row.source_ref or {},
                "verified": bool(row.verified),
                "extractor": row.extractor,
            })
        return grouped
