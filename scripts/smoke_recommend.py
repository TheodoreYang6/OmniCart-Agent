"""Quick smoke test for the V0 recommend pipeline.

Run: python scripts/smoke_recommend.py
Requires: backend running on 127.0.0.1:8006
"""

import json
import sys

import httpx


def main():
    queries = [
        "预算200以内，适合iPhone 15出差用的充电宝",
        "能给MacBook充电的大功率充电宝推荐",
        "坐飞机可以带的便携充电宝",
    ]

    base = "http://127.0.0.1:8006"
    all_passed = True
    client = httpx.Client(timeout=30.0, trust_env=False)

    for q in queries:
        print(f"\n{'='*60}")
        print(f"Query: {q}")
        try:
            resp = client.post(
                f"{base}/api/recommend",
                json={"user_query": q},
            )
            resp.raise_for_status()
            data = resp.json()
            n = len(data.get("products", []))
            answer_preview = data.get("answer", "")[:100]
            print(f"  Status: {resp.status_code}")
            print(f"  Products: {n}")
            print(f"  Answer: {answer_preview}...")
            if n == 0:
                print("  WARNING: No products returned")
                all_passed = False
        except Exception as e:
            print(f"  FAILED: {e}")
            all_passed = False

    print(f"\n{'='*60}")
    if all_passed:
        print("Smoke test PASSED")
    else:
        print("Smoke test has WARNINGS/FAILURES")
        sys.exit(1)


if __name__ == "__main__":
    main()
