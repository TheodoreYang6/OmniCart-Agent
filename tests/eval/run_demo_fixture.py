"""P3-2: 端到端 Demo Fixture — 比赛演示可复现测试。

Usage:
    python tests/eval/run_demo_fixture.py
    python tests/eval/run_demo_fixture.py --base-url http://localhost:8006

每个 case 包含: query, expected_category, min_products, required_fields
所有 case 应通过（演示环境后端需运行中）。
"""

import json
import sys
import time
from pathlib import Path
from typing import Any

# 固定演示案例 — 覆盖品类、预算、场景、图像、对比
DEMO_CASES = [
    {
        "id": "demo_001",
        "name": "数码推荐-蓝牙耳机",
        "query": "推荐一款适合通勤使用的蓝牙耳机",
        "expected_category": "数码电子",
        "min_products": 1,
        "check_score_range": True,
    },
    {
        "id": "demo_002",
        "name": "美妆推荐-精华液",
        "query": "适合干皮的精华液推荐",
        "expected_category": "美妆护肤",
        "min_products": 1,
        "check_score_range": True,
    },
    {
        "id": "demo_003",
        "name": "预算约束-200元以内",
        "query": "200元以内的运动鞋",
        "expected_category": "服饰运动",
        "max_price": 200,
        "min_products": 1,
    },
    {
        "id": "demo_004",
        "name": "食品饮料-零食",
        "query": "办公室零食推荐",
        "expected_category": "食品饮料",
        "min_products": 1,
    },
    {
        "id": "demo_005",
        "name": "场景化搜索-出差",
        "query": "出差用的20000mAh充电宝",
        "expected_category": "数码电子",
        "min_products": 1,
    },
    {
        "id": "demo_006",
        "name": "空查询-边界测试",
        "query": "",
        "expect_answer": True,
        "allow_zero_products": True,
    },
]

REQUIRED_TOP_FIELDS = [
    "session_id", "conversation_id", "answer",
    "products", "decision_results", "evidence_list",
    "trace_steps", "harness_report",
    "used_memories", "blocked_memories", "memory_trace",
]

PRODUCT_FIELDS = ["product_id", "title", "brand", "category", "price"]
DECISION_FIELDS = [
    "product_id", "final_score", "display_score",
    "recommendation_level", "evidence_confidence",
]


def run_case(case: dict, base_url: str) -> dict[str, Any]:
    """Run a single demo case against the API and return the result."""
    import httpx

    result: dict[str, Any] = {
        "case_id": case["id"],
        "name": case["name"],
        "passed": False,
        "errors": [],
        "warnings": [],
    }

    try:
        with httpx.Client(timeout=30.0, trust_env=False) as client:
            resp = client.post(
                f"{base_url}/api/recommend/v2",
                json={
                    "user_query": case["query"],
                    "session_id": f"demo_fixture_{case['id']}",
                    "user_id": "demo_tester",
                },
            )
            if resp.status_code != 200:
                result["errors"].append(f"HTTP {resp.status_code}")
                return result

            data = resp.json()
            result["response"] = {
                "session_id": data.get("session_id", "")[:12],
                "product_count": len(data.get("products", [])),
                "decision_count": len(data.get("decision_results", [])),
                "evidence_count": len(data.get("evidence_list", [])),
                "trace_count": len(data.get("trace_steps", [])),
                "answer_len": len(data.get("answer", "")),
            }

            # 1. 顶层字段完整性
            for field in REQUIRED_TOP_FIELDS:
                if field not in data:
                    result["errors"].append(f"Missing top field: {field}")

            # 2. 商品数量检查
            products = data.get("products", [])
            if not case.get("allow_zero_products"):
                if len(products) < case.get("min_products", 1):
                    result["errors"].append(
                        f"Insufficient products: {len(products)} < {case['min_products']}"
                    )

            # 3. 品类检查
            if "expected_category" in case and products:
                match_count = sum(
                    1 for p in products
                    if p.get("category") == case["expected_category"]
                )
                if match_count == 0:
                    result["warnings"].append(
                        f"No product in expected category '{case['expected_category']}'"
                    )

            # 4. 价格约束检查
            if "max_price" in case and products:
                over_budget = [
                    p for p in products
                    if p.get("price", 0) > case["max_price"]
                ]
                if over_budget:
                    result["warnings"].append(
                        f"{len(over_budget)} products over max_price={case['max_price']}"
                    )

            # 5. 商品字段完整性
            for p in products:
                for field in PRODUCT_FIELDS:
                    if field not in p:
                        result["errors"].append(
                            f"Product {p.get('product_id', '?')} missing field: {field}"
                        )
                        break

            # 6. Decision 字段完整性 + 分数范围
            decisions = data.get("decision_results", [])
            for d in decisions:
                for field in DECISION_FIELDS:
                    if field not in d:
                        result["errors"].append(
                            f"Decision {d.get('product_id', '?')} missing field: {field}"
                        )
                score = d.get("display_score", -1)
                if case.get("check_score_range") and (score < 0 or score > 10):
                    result["errors"].append(
                        f"display_score {score} out of [0,10] for {d.get('product_id')}"
                    )

            # 7. 有 answer
            if case.get("expect_answer"):
                if not data.get("answer"):
                    result["errors"].append("Expected non-empty answer")

            result["passed"] = len(result["errors"]) == 0

    except Exception as e:
        result["errors"].append(f"Exception: {e}")

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Demo fixture runner")
    parser.add_argument("--base-url", default="http://127.0.0.1:8006")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    results = []
    passed = 0
    failed = 0
    t0 = time.perf_counter()

    for case in DEMO_CASES:
        r = run_case(case, args.base_url)
        results.append(r)
        if r["passed"]:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
        info = r.get("response", {})
        print(
            f"[{status}] {case['id']}: {case['name']} "
            f"| products={info.get('product_count', '?')} "
            f"| decisions={info.get('decision_count', '?')} "
            f"| evidence={info.get('evidence_count', '?')}"
        )
        if r["errors"]:
            for e in r["errors"]:
                print(f"  ERROR: {e}")
        if r["warnings"]:
            for w in r["warnings"]:
                print(f"  WARN: {w}")

    elapsed = time.perf_counter() - t0
    print(f"\n{'='*50}")
    print(f"Demo Fixture: {passed}/{len(DEMO_CASES)} passed ({elapsed:.1f}s)")
    if failed > 0:
        print(f"FAILED: {failed} case(s) — check errors above")
    else:
        print("ALL PASSED — 比赛演示可复现 ✓")
    print(f"{'='*50}")

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
