#!/usr/bin/env python
"""SSE 全链路体验驱动（诊断用，临时脚本）：发消息 → 收流 → 打印耗时/回答/动作/商品数。"""
import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8006"


def chat(msg: str, sid: str = "diag_s1", uid: str = "u_diag_001", cid: str = "", mode: str = "", target: str = ""):
    payload = {"session_id": sid, "user_id": uid, "conversation_id": cid, "message": msg}
    if mode:
        payload["mode"] = mode
    if target:
        payload["target_product_id"] = target
    t0 = time.perf_counter()
    first_token_ms = None
    result = {}
    try:
        with httpx.stream("POST", f"{BASE}/api/recommend/stream", json=payload, timeout=90) as r:
            event = ""
            for line in r.iter_lines():
                if line.startswith("event:"):
                    event = line[6:].strip()
                elif line.startswith("data:"):
                    data = line[5:].strip()
                    if event == "token" and first_token_ms is None:
                        first_token_ms = round((time.perf_counter() - t0) * 1000)
                    if event == "result" and data:
                        try:
                            result = json.loads(data)
                        except json.JSONDecodeError:
                            pass
    except Exception as e:
        print(f"!! REQUEST FAILED: {e}")
        return {}
    total_ms = round((time.perf_counter() - t0) * 1000)
    answer = (result.get("answer") or "").replace("\n", " ")
    actions = [a.get("type") for a in (result.get("actions") or [])]
    products = result.get("products") or []
    print(f"### Q: {msg}")
    print(f"    time: total={total_ms}ms first_token={first_token_ms}ms | products={len(products)} | actions={actions}")
    print(f"    A: {answer[:220]}")
    extra = {k: v for k, v in result.items()
             if k in ("shop_action", "conversation_id", "clarification_options") and v}
    if extra:
        print(f"    extra: {json.dumps(extra, ensure_ascii=False)[:150]}")
    print()
    return result


if __name__ == "__main__":
    for m in sys.argv[1:]:
        chat(m)
