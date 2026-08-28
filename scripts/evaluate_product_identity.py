"""Run the catalog entity benchmark and save an auditable JSONL quality report.

Usage: .venv\\Scripts\\python.exe scripts\\evaluate_product_identity.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select

from app.core.database import get_session_sync
from app.models.product_identity import ProductIdentityModel
from app.services.product_entity_eval_cases import ENTITY_EVAL_CASES
from app.services.product_entity_resolver import ProductEntityResolver


async def main() -> None:
    factory = get_session_sync()
    if factory is None:
        raise RuntimeError("PostgreSQL is not configured")
    async with factory() as session:
        focused_ids = list(
            (
                await session.execute(
                    select(ProductIdentityModel.product_id)
                    .where(ProductIdentityModel.product_line_key == "iphone")
                    .limit(3)
                )
            ).scalars()
        )
    if not focused_ids:
        raise RuntimeError("No iPhone identity rows; run build_product_identity_index.py first")

    resolver = ProductEntityResolver()
    report: list[dict] = []
    focused_index = 0
    for index, case in enumerate(ENTITY_EVAL_CASES, start=1):
        started = time.perf_counter()
        if case.get("focused"):
            product_id = focused_ids[focused_index % len(focused_ids)]
            focused_index += 1
            result = await resolver.resolve_product_id(product_id)
            query = f"target_product_id:{product_id}"
        else:
            query = case["query"]
            result = await resolver.resolve(query, case.get("visual"))
        actual = result.payload.get("match_type", "no_match")
        report.append(
            {
                "case": index,
                "group": case["group"],
                "query": query,
                "expected": case["expected"],
                "actual": actual,
                "passed": actual == case["expected"],
                "alias_hit": result.payload.get("matched_alias", ""),
                "resolved_product_ids": result.payload.get("resolved_product_ids", []),
                "retrieval_scope": result.payload.get("retrieval_scope", "broad"),
                "error_reason": "" if actual == case["expected"] else "resolution_mismatch",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            }
        )
    output = ROOT / "tmp" / "product_identity_eval.jsonl"
    output.parent.mkdir(exist_ok=True)
    output.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in report) + "\n", encoding="utf-8")
    passed = sum(bool(item["passed"]) for item in report)
    print(f"{passed}/{len(report)} passed ({passed / len(report):.1%}); report: {output}")
    if passed != len(report):
        for item in report:
            if not item["passed"]:
                print(f"FAIL #{item['case']}: {item['query']} -> {item['actual']} (expected {item['expected']})")
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
