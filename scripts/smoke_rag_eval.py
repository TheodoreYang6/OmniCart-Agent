"""RAG 生成评测冒烟测试 — 需要后端运行中 (MOCK_MODE=true 也能跑)。

用法:
    cd backend && python ../scripts/smoke_rag_eval.py

功能:
    1. 用 3 条 query 跑快速 RAG 评测
    2. 验证三项指标值在合理范围 (0.0~1.0)
    3. 验证 API 响应结构完整
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import httpx


BASE = "http://127.0.0.1:8006"


async def main():
    print("─" * 60)
    print("RAG 生成评测冒烟测试")
    print("─" * 60)

    # 1. 健康检查
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/api/health")
        assert r.status_code == 200, f"Backend not running at {BASE}"
        print(f"  Backend: {r.json()['status']}")

    # 2. 小数据量快速评测 (3 条 query)
    async with httpx.AsyncClient(timeout=180) as client:
        print("\n  运行 RAG 评测 (3 queries)...")
        r = await client.post(
            f"{BASE}/api/eval/rag/run",
            params={"top_k": 5, "enable_rerank": True, "context_products": 3, "dataset_limit": 3},
        )
        assert r.status_code == 200, f"RAG eval failed: {r.status_code}"
        result = r.json()

        # 验证结构
        assert "run_id" in result, "Missing run_id"
        assert "avg_faithfulness" in result, "Missing avg_faithfulness"
        assert "avg_context_precision" in result, "Missing avg_context_precision"
        assert "avg_context_recall" in result, "Missing avg_context_recall"

        faith = result["avg_faithfulness"]
        prec = result["avg_context_precision"]
        recall = result["avg_context_recall"]

        print(f"  Faithfulness:         {faith:.4f}")
        print(f"  Context Precision:    {prec:.4f}")
        print(f"  Context Recall:       {recall:.4f}")

        # 验证范围
        assert 0.0 <= faith <= 1.0, f"Faithfulness out of range: {faith}"
        assert 0.0 <= prec <= 1.0, f"Context Precision out of range: {prec}"
        assert 0.0 <= recall <= 1.0, f"Context Recall out of range: {recall}"

        print(f"\n  Details: {len(result.get('details', []))} queries evaluated")

    # 3. 查看历史
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{BASE}/api/eval/rag/results?limit=3")
        assert r.status_code == 200
        runs = r.json()
        print(f"  History runs: {runs['total_runs']}")

    # 4. 实验端点快速验证 (仅 1 query, 有限参数)
    async with httpx.AsyncClient(timeout=180) as client:
        print("\n  运行参数实验 (1 query, 2 configs)...")
        r = await client.post(
            f"{BASE}/api/eval/rag/experiment",
            params={"dataset_limit": 1},
        )
        assert r.status_code == 200, f"Experiment failed: {r.status_code}"
        exp = r.json()
        assert "best_config" in exp
        best = exp["best_config"]
        print(f"  Best config: {best}")

    print("\n─" * 60)
    print("ALL SMOKE TESTS PASSED")
    print("─" * 60)


if __name__ == "__main__":
    asyncio.run(main())
