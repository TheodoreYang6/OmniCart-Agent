#!/usr/bin/env python3
"""深度思考（OmniAgent Loop）vs pipeline 对比评测（spec: docs/specs/omni-harness D5）。

同一组 query 分别跑 deep_think=true/false，对比：
- 商品产出（数量/是否为空）、回答规则断言（关键词命中）、端到端延迟、（Loop）工具轮次。
作为观察基线（非转正门槛），报告落 data/eval_runs/agent-loop-{tag}.json。

用法（需后端已在 8000 端口运行、建议先 redis-cli FLUSHDB）:
    python scripts/eval_agent_loop.py --tag baseline
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "http://localhost:8000/api/recommend/stream"

# 四类 case：推荐 / 约束推荐 / 购物操作（无关键词门控命中） / 多步组合
CASES = [
    {"id": "rec_simple", "q": "推荐一款蓝牙耳机", "expect_products": True,
     "answer_kw": ["耳机"]},
    {"id": "rec_constraint", "q": "想要口碑好的儿童保温杯，预算200以内", "expect_products": True,
     "answer_kw": ["保温杯"]},
    {"id": "shop_action", "q": "帮我把最推荐的那款放进购物车里", "expect_products": False,
     "answer_kw": []},  # 观察 LLM 是否选 cart 工具（trace 断言）
    {"id": "multi_step", "q": "对比一下华为和苹果的降噪耳机哪个值得买", "expect_products": True,
     "answer_kw": ["华为", "苹果"]},
    {"id": "faq_deep", "q": "膳魔师儿童保温杯的真空层厚度是多少，保温效果实测怎么样", "expect_products": True,
     "answer_kw": ["膳魔师"]},
    {"id": "chitchat", "q": "你好呀", "expect_products": False, "answer_kw": []},
]


def _sse_call(q: str, deep: bool, user: str, timeout: int = 150) -> dict:
    body = json.dumps({"user_id": user, "message": q, "deep_think": deep}).encode()
    req = urllib.request.Request(URL, data=body, headers={
        "Content-Type": "application/json", "Accept": "text/event-stream"})
    t0 = time.perf_counter()
    raw = urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace")
    elapsed = round(time.perf_counter() - t0, 1)
    result = {}
    for m in re.finditer(r"event: result\ndata: (.*)\n", raw):
        try:
            result = json.loads(m.group(1))
        except Exception:  # noqa: BLE001
            pass
    statuses = re.findall(r'event: status\ndata: \{"text": "([^"]*)"', raw)
    return {"elapsed_s": elapsed, "result": result, "statuses": statuses,
            "token_frames": raw.count("event: token")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    args = ap.parse_args()

    rows = []
    for c in CASES:
        row = {"id": c["id"], "query": c["q"]}
        for mode, deep in (("pipeline", False), ("deep_think", True)):
            try:
                r = _sse_call(c["q"], deep, user=f"eval_{mode}_{c['id']}")
            except Exception as e:  # noqa: BLE001
                row[mode] = {"error": str(e)[:120]}
                continue
            res = r["result"]
            answer = str(res.get("answer", ""))
            products = res.get("products") or []
            trace = res.get("trace_steps") or []
            tool_rounds = len([t for t in trace if "OmniAgent" in str(t.get("agent_name", ""))])
            row[mode] = {
                "elapsed_s": r["elapsed_s"],
                "products": len(products),
                "answer_len": len(answer),
                "kw_hit": all(k in answer for k in c["answer_kw"]) if c["answer_kw"] else None,
                "products_ok": (len(products) > 0) == c["expect_products"] or not c["expect_products"],
                "loop_steps": tool_rounds if deep else None,
                "statuses": r["statuses"][:6] if deep else None,
            }
            print(f"  {c['id']:<14} {mode:<10} {r['elapsed_s']:>6}s "
                  f"products={len(products)} kw={row[mode]['kw_hit']}")
        rows.append(row)

    report = {"tag": args.tag, "cases": rows}
    out = ROOT / "data" / "eval_runs" / f"agent-loop-{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"报告: {out}")


if __name__ == "__main__":
    main()
