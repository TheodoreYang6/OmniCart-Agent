"""Build deterministic catalog identities and aliases from current products.

Run after Alembic migration 013. Re-running is safe: generated rows are rebuilt,
while future manually curated aliases (source=manual) are retained.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import get_session_sync
from app.models.product import ProductModel
from app.models.product_identity import ProductAliasModel, ProductIdentityModel
from app.services.product_entity_resolver import build_identity_record, normalize_identity


def _manual_aliases(identity: dict) -> list[tuple[str, str]]:
    """Return curated high-frequency aliases matching one generated identity."""
    path = ROOT / "data" / "product_alias_overrides.json"
    if not path.exists():
        return []
    overrides = json.loads(path.read_text(encoding="utf-8"))
    rows: list[tuple[str, str]] = []
    for item in overrides:
        selector = item.get("selector", {})
        if all(str(identity.get(key, "")) == str(value) for key, value in selector.items()):
            rows.extend(
                (str(alias["display"]), str(alias.get("type", "manual")))
                for alias in item.get("aliases", [])
                if alias.get("display")
            )
    return rows


async def main() -> None:
    factory = get_session_sync()
    if factory is None:
        raise RuntimeError("PostgreSQL is not configured")
    async with factory() as session:
        products = (await session.execute(select(ProductModel))).scalars().all()
        await session.execute(delete(ProductAliasModel).where(ProductAliasModel.source == "generated"))
        await session.execute(delete(ProductIdentityModel).where(ProductIdentityModel.source == "generated"))
        aliases = 0
        for product in products:
            identity, rows = build_identity_record(product)
            await session.execute(
                insert(ProductIdentityModel)
                .values(**identity)
                .on_conflict_do_update(index_elements=["product_id"], set_=identity)
            )
            for display, alias_type in rows:
                normalized = normalize_identity(display)
                if not normalized:
                    continue
                await session.execute(
                    insert(ProductAliasModel)
                    .values(
                        product_id=product.product_id,
                        alias_normalized=normalized,
                        alias_display=display[:512],
                        alias_type=alias_type,
                        source="generated",
                    )
                    .on_conflict_do_nothing(index_elements=["product_id", "alias_normalized"])
                )
                aliases += 1
            # Curated forms are never deleted by a generated rebuild. They are
            # intentionally auditable in data/product_alias_overrides.json.
            for display, alias_type in _manual_aliases(identity):
                normalized = normalize_identity(display)
                if not normalized:
                    continue
                await session.execute(
                    insert(ProductAliasModel)
                    .values(
                        product_id=product.product_id,
                        alias_normalized=normalized,
                        alias_display=display[:512],
                        alias_type=alias_type,
                        source="manual",
                    )
                    .on_conflict_do_update(
                        index_elements=["product_id", "alias_normalized"],
                        set_={"alias_display": display[:512], "alias_type": alias_type, "source": "manual"},
                    )
                )
        await session.commit()
    print(f"Built {len(products)} identities and {aliases} generated aliases.")


if __name__ == "__main__":
    asyncio.run(main())
