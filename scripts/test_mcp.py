#!/usr/bin/env python
"""MCP Tool 连通性测试 — 逐个执行 8 个 Tool 验证输入输出"""

import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.mcp.tools import handle_tool, TOOL_DEFINITIONS


async def test_all():
    print(f"OmniCart MCP Server Test — {len(TOOL_DEFINITIONS)} tools\n")
    passed = 0

    tests = [
        ("product_text_search", {"query": "蓝牙耳机", "top_k": 3}),
        ("product_detail", {"product_id": "p_digital_007"}),
        ("review_search", {"product_id": "p_digital_026", "max_rating": 5}),
        ("policy_lookup", {"product_id": "p_digital_028", "keyword": "飞机"}),
        ("compatibility_check", {"product_id": "p_digital_007", "user_devices": ["iPhone 15", "MacBook Pro"]}),
        ("structured_filter", {"category": "数码电子", "price_max": 200}),
        ("decision_score", {"product_id": "p_digital_026", "user_query": "推荐蓝牙耳机", "budget_max": 200}),
        ("list_categories", {}),
    ]

    for name, args in tests:
        try:
            result = await handle_tool(name, args)
            data = json.loads(result)
            ok = "error" not in data
            status = "PASS" if ok else f"FAIL: {data.get('error', '')[:60]}"
            preview = result[:100].replace("\n", " ")
            print(f"  [{status}] {name}({json.dumps(args, ensure_ascii=False)[:80]})")
            print(f"         -> {preview}...")
            if ok:
                passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {str(e)[:100]}")

    print(f"\n{passed}/{len(tests)} tools passed")


if __name__ == "__main__":
    asyncio.run(test_all())
