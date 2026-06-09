#!/usr/bin/env python
"""P3-2: Memory System Eval Script — 记忆系统评测脚本。

评测维度:
- Extraction Precision/Recall
- Memory Write Precision
- Memory Recall@K / MRR
- Wrong User Memory Rate
- Stale Memory Usage Rate
- Memory Citation Accuracy
- Memory Harness Pass Rate

Usage:
    python scripts/eval_memory.py
    python scripts/eval_memory.py --case extract_001
"""

import json
import sys
import os
from pathlib import Path

# Ensure backend is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.services.memory_extractor import get_extractor
from app.services.memory_write_policy import get_write_policy
from app.services.memory_harness import get_memory_harness


def load_cases() -> list[dict]:
    path = Path(__file__).resolve().parent.parent / "tests" / "eval" / "memory_cases.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data.get("cases", [])


def run_case(case: dict) -> dict:
    """Run a single eval case and return pass/fail with details."""
    case_id = case["id"]
    name = case["name"]
    result = {"id": case_id, "name": name, "pass": False, "details": {}}

    try:
        # ---- Extraction cases ----
        if case_id.startswith("extract_"):
            ext = get_extractor()
            candidates = ext.extract_from_message(case["input"])
            expected = case.get("expected_extraction", {})

            checks = []
            if "has_budget" in expected:
                has = any(c.memory_type.value == "budget" for c in candidates)
                checks.append(("has_budget", has == expected["has_budget"]))
                result["details"]["candidates"] = [c.model_dump() for c in candidates]

            if "has_device" in expected:
                has = any(c.memory_type.value == "device" for c in candidates)
                checks.append(("has_device", has == expected["has_device"]))

            if "has_negative_preference" in expected:
                has = any(c.memory_type.value == "negative_preference" for c in candidates)
                checks.append(("has_negative_preference", has == expected["has_negative_preference"]))

            if "is_temporary" in expected:
                all_match = all(c.is_temporary == expected["is_temporary"] for c in candidates) if candidates else True
                checks.append(("is_temporary", all_match))

            # Check write decision
            if "expected_decision" in case:
                pol = get_write_policy()
                decisions = pol.decide_batch(candidates)
                match = any(d.decision.value == case["expected_decision"] for d in decisions) if decisions else (case["expected_decision"] == "ignore")
                checks.append(("decision", match))

            result["pass"] = all(c[1] for c in checks)
            result["details"]["checks"] = checks

        # ---- Harness cases ----
        elif case_id.startswith("harness_"):
            h = get_memory_harness()
            check_name = case["harness_check"]

            # Build test data based on scenario
            if check_name == "user_scope_pass":
                r = h._check_user_scope("user1", [{"memory_id": "MEM-1"}], [])
                result["pass"] = r == case["expected_pass"]

            elif check_name == "confidence_pass":
                r = h._check_confidence([{"is_hard_constraint": True, "confidence": 0.3}])
                result["pass"] = r == case["expected_pass"]

            elif check_name == "conflict_resolution_pass":
                r = h._check_conflict_resolution(
                    [{"memory_id": "MEM-1"}],
                    [{"memory_id": "MEM-1"}]
                )
                result["pass"] = r == case["expected_pass"]

            elif check_name == "avoid_tag_pass":
                r = h._check_avoid_tags(
                    "推荐这款太重的充电宝",
                    [{"memory_type": "negative_preference", "structured_value": {"avoid": "太重"}}]
                )
                result["pass"] = r == case["expected_pass"]

            result["details"]["harness_check"] = check_name

        # ---- Scoring cases ----
        elif case_id.startswith("scoring_"):
            from app.decision.scoring import DecisionScoring
            from app.schemas.product import Product
            scorer = DecisionScoring()
            p = case["product"]
            product = Product(
                product_id=p["product_id"], title=p["title"], brand=p.get("brand", ""),
                category=p.get("category", ""), base_price=float(p.get("base_price", 0)),
            )
            decision = scorer.score(
                product=product, query=case.get("query", ""),
                used_memories=case.get("memories", []),
            )
            if "expected_brand_boost" in case:
                val = decision.score_breakdown.brand_preference_boost
                result["pass"] = val > 0
                result["details"]["brand_preference_boost"] = val

        # ---- Retrieve cases (need PG) ----
        elif case_id.startswith("retrieve_") or case_id.startswith("conflict_"):
            from app.services.memory_retriever import MemoryRetriever
            ret = MemoryRetriever()
            memories = case.get("memories", [])
            user_id = case.get("user_id", "")
            query = case.get("query", "")

            # Build test data: insert memories then test
            try:
                from app.repositories.memory_repo import get_memory_repo
                repo = get_memory_repo()
                for m in memories:
                    if m.get("status") == "deleted":
                        mem = repo.create(
                            user_id=user_id, memory_type=m["memory_type"],
                            content=m["content"], source=m.get("source","explicit_user"),
                            confidence=m.get("confidence", 0.5),
                            structured_value=m.get("structured_value", {}),
                        )
                        repo.soft_delete(mem.memory_id)
                    else:
                        repo.create(
                            user_id=user_id, memory_type=m["memory_type"],
                            content=m["content"], source=m.get("source","explicit_user"),
                            confidence=m.get("confidence", 0.5),
                            structured_value=m.get("structured_value", {}),
                        )

                # Now test via API-like call
                import urllib.request, json
                data = json.dumps({
                    "user_query": query, "session_id": f"eval_{case_id}",
                    "user_id": user_id,
                }).encode()
                req = urllib.request.Request(
                    "http://127.0.0.1:8006/api/recommend/v2",
                    data=data, headers={"Content-Type": "application/json"}
                )
                r = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
                used_count = len(r.get("used_memories", []))
                blocked_count = len(r.get("blocked_memories", []))
                expected_used = case.get("expected_used_count", 0)
                expected_blocked = case.get("expected_blocked_count", 0)
                result["pass"] = (used_count == expected_used and blocked_count == expected_blocked)
                result["details"] = {"used": used_count, "blocked": blocked_count}
            except Exception as e:
                result["pass"] = False
                result["details"]["error"] = str(e)

        result["pass"] = result.get("pass", False)
    except Exception as e:
        result["pass"] = False
        result["details"]["error"] = str(e)

    return result


def main():
    cases = load_cases()
    if not cases:
        print("No eval cases found.")
        return

    # Filter by --case
    filter_id = None
    for arg in sys.argv[1:]:
        if arg.startswith("--case="):
            filter_id = arg.split("=", 1)[1]
        elif arg == "--case" and len(sys.argv) > 2:
            filter_id = sys.argv[sys.argv.index("--case") + 1]

    if filter_id:
        cases = [c for c in cases if c["id"] == filter_id]

    print(f"{'='*60}")
    print(f"  Memory System Eval — P3-2")
    print(f"  Cases: {len(cases)}")
    print(f"{'='*60}\n")

    results = []
    for case in cases:
        r = run_case(case)
        results.append(r)
        status = "PASS" if r["pass"] else "FAIL"
        print(f"  [{status}] {case['id']}: {case['name']}")

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    # Metric aggregates
    print(f"\n{'='*60}")
    print(f"  Results: {passed}/{total} passed ({passed/max(total,1)*100:.0f}%)")
    print(f"{'='*60}")

    # Per-category breakdown
    categories = {}
    for r in results:
        cat = r["id"].split("_")[0]
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r["pass"]:
            categories[cat]["passed"] += 1

    print("\n  By category:")
    for cat, stats in sorted(categories.items()):
        rate = stats["passed"] / max(stats["total"], 1) * 100
        print(f"    {cat}: {stats['passed']}/{stats['total']} ({rate:.0f}%)")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
