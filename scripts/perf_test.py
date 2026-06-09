#!/usr/bin/env python
"""最小性能测试脚本 — 对 /api/recommend/v2 发请求并输出各节点耗时。

用法:
  python scripts/perf_test.py                  # 默认模式
  OMNICART_FAST_MODE=true python scripts/perf_test.py  # FAST_MODE
"""

import os
import sys
import time
import json
import io
import urllib.request
from pathlib import Path

# Fix Windows GBK encoding
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_DIR = Path(__file__).resolve().parent.parent
API_URL = os.getenv("OMNICART_API_URL", "http://127.0.0.1:8006/api/recommend/v2")

QUERIES = [
    "出差用的充电宝，要能带上飞机",
    "我是敏感肌，想买抗初老精华，这款适合吗",
    "我预算一万以内，拍照多但不拍4K，iPhone 17 Pro选哪个版本",
    "我175cm，夏天通勤怕热，想买白T，这款适合吗",
]


def run_one(query: str) -> dict | None:
    body = json.dumps({"user_query": query, "session_id": f"perf-{hash(query) % 10000}"}).encode("utf-8")
    req = urllib.request.Request(API_URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  ERROR: {e}")
        return None
    total_ms = round((time.perf_counter() - t0) * 1000)
    timing = data.get("timing", {})
    timing["total_ms"] = total_ms
    decisions = data.get("decision_results", [])
    top = decisions[0] if decisions else {}
    return {
        "products": len(data.get("products", [])),
        "top_product": top.get("product_id", "-"),
        "final_score": top.get("final_score", 0),
        "display_score": top.get("display_score", 0),
        "evidence_confidence": top.get("evidence_confidence", 0),
        "recommendation_level": top.get("recommendation_level", "-"),
        "support_count": len(top.get("support_evidence_ids", [])),
        "answer": data.get("answer", "")[:80],
        "timing": timing,
    }


def main():
    fast = os.getenv("OMNICART_FAST_MODE", "false").lower() == "true"
    mode = "FAST_MODE" if fast else "NORMAL"
    print(f"\nOmniCart V4 Perf Test — {mode}")
    print(f"API: {API_URL}")
    print(f"{'='*80}")

    all_timings = []
    for i, q in enumerate(QUERIES):
        print(f"\n[{i+1}/{len(QUERIES)}] {q[:60]}")
        result = run_one(q)
        if result is None:
            continue
        t = result["timing"]
        all_timings.append(t)
        print(f"  top: {result['top_product']} score={result['display_score']} "
              f"level={result['recommendation_level']} conf={result['evidence_confidence']:.0%} "
              f"support={result['support_count']}")
        print(f"  timing: total={t.get('total_ms','-')}ms "
              f"retrieval={t.get('retrieval_ms','-')}ms "
              f"rerank={t.get('rerank_ms','-')}ms "
              f"decision={t.get('decision_ms','-')}ms "
              f"response={t.get('response_ms','-')}ms")

    if all_timings:
        print(f"\n{'='*80}")
        print("AVERAGES:")
        for key in ["retrieval_ms", "rerank_ms", "decision_ms", "response_ms", "total_ms"]:
            vals = [t.get(key, 0) for t in all_timings if t.get(key)]
            if vals:
                avg = sum(vals) / len(vals)
                print(f"  {key:<20s} {avg:.0f}ms")

    decision_vals = [t.get("decision_ms", 0) for t in all_timings if t.get("decision_ms")]
    if decision_vals:
        avg_decision = sum(decision_vals) / len(decision_vals)
        if avg_decision < 50:
            print(f"\nPASS: decision_ms avg={avg_decision:.0f}ms < 50ms")
        else:
            print(f"\nFAIL: decision_ms avg={avg_decision:.0f}ms >= 50ms")


if __name__ == "__main__":
    main()
