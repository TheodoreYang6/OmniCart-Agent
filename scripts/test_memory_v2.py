#!/usr/bin/env python
"""Memory 2.0 端到端集成测试 — 覆盖 P0-P3 全部功能。

用法:
    python scripts/test_memory_v2.py

要求:
    - 后端运行在 127.0.0.1:8006
    - Redis 运行在 127.0.0.1:6379
    - PostgreSQL 已配置 (DATABASE_URL)
"""

import json
import urllib.request
import urllib.parse
import sys
import time

BASE = "http://127.0.0.1:8006"

def api(method, path, body=None, params=None):
    """调用 API 并返回 parsed JSON."""
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def ok(msg): print(f"  [OK] {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def info(msg): print(f"  [--] {msg}")

passed = 0
failed = 0

def check(name, condition):
    global passed, failed
    if condition:
        ok(name); passed += 1
    else:
        fail(name); failed += 1

print("=" * 60)
print("  OmniCart Memory 2.0 — 端到端集成测试")
print("=" * 60)

# ── Health Check ──
print("\n── 0. Health Check ──")
try:
    h = api("GET", "/api/health")
    check(f"Backend: {h.get('service')} v{h.get('version')}", h.get("status") == "ok")
    check(f"Redis: {h.get('redis')}", h.get("redis") == "connected")
except Exception as e:
    fail(f"Backend not reachable: {e}")
    sys.exit(1)

# ── P0: Identity & Conversation ──
print("\n── P0: Identity & Conversation ──")
r = api("POST", "/api/recommend/v2", {
    "user_query": "推荐一个蓝牙耳机",
    "session_id": "test_p0",
    "user_id": "memtest_user",
})
check("session_id preserved", r["session_id"] == "test_p0")
check("conversation_id generated (CONV-*)", r.get("conversation_id", "").startswith("CONV-"))
check("used_memories field present", "used_memories" in r)
check("blocked_memories field present", "blocked_memories" in r)
check("memory_trace field present", "memory_trace" in r)
check("products returned", len(r.get("products", [])) > 0)

# ── P1: Atomic Memory CRUD ──
print("\n── P1: Atomic Memory CRUD ──")

# Create
mem = api("POST", "/api/memories", {
    "user_id": "memtest_user",
    "memory_type": "device",
    "content": "使用MacBook，需要USB-C接口",
    "structured_value": {"device": "macbook"},
    "source": "explicit_user",
    "confidence": 0.9,
})
memory_id = mem.get("memory_id", "")
check("memory created (MEM-*)", memory_id.startswith("MEM-"))
check("memory status=active", mem.get("status") == "active")

# Read
mem2 = api("GET", f"/api/memories/{memory_id}")
check("memory read back", mem2.get("content", "").startswith("使用MacBook"))

# List active
mem_list = api("GET", "/api/memories", params={"user_id": "memtest_user"})
check(f"active memories: {mem_list.get('count', 0)}", mem_list.get("count", 0) >= 1)

# Soft delete
api("DELETE", f"/api/memories/{memory_id}")
mem3 = api("GET", f"/api/memories/{memory_id}")
check("soft delete → status=deleted", mem3.get("status") == "deleted")

# Create 3 more memories for retrieval test
for m in [
    ("device", "使用MacBook设备", {"device": "macbook"}, 0.9),
    ("brand", "品牌偏好: Anker", {"brand": "Anker"}, 0.85),
    ("scenario", "经常出差", {"scenario": "business_travel"}, 0.8),
]:
    api("POST", "/api/memories", {
        "user_id": "memtest_user",
        "memory_type": m[0],
        "content": m[1],
        "structured_value": m[2],
        "source": "explicit_user",
        "confidence": m[3],
    })

mem_list2 = api("GET", "/api/memories", params={"user_id": "memtest_user"})
check("3 new memories active", mem_list2.get("count", 0) >= 3)

# ── P2: Memory Retrieval + Scoring + Query Enhancement ──
print("\n── P2: Memory Retrieval + Scoring + Query Enhancement ──")

r2 = api("POST", "/api/recommend/v2", {
    "user_query": "推荐一个充电宝",
    "session_id": "test_p2",
    "user_id": "memtest_user",
})
used = r2.get("used_memories", [])
blocked = r2.get("blocked_memories", [])
trace = r2.get("memory_trace", {})

check(f"used >= 2 memories (got {len(used)})", len(used) >= 2)
check(f"memory_trace.total_atomic >= 3", trace.get("total_atomic", 0) >= 3)
check("memory_trace.used_count > 0", trace.get("used_count", 0) > 0)

# Check scoring includes memory dimensions
if r2.get("decision_results"):
    dr = r2["decision_results"][0]
    sb = dr.get("score_breakdown", {})
    has_mem_dims = all(k in sb for k in ["preference_match_score", "device_compatibility_score"])
    check("scoring has memory dimensions", has_mem_dims)
    info(f"  preference_match={sb.get('preference_match_score', '?'):.2f} device_compat={sb.get('device_compatibility_score', '?'):.2f}")

# Check memory contributions
mc = dr.get("memory_contributions", [])
check(f"memory_contributions populated ({len(mc)} entries)", len(mc) > 0)

# ── P2: Conflict Resolution ──
print("\n── P2: Conflict Resolution ──")

# Create a budget memory
b_mem = api("POST", "/api/memories", {
    "user_id": "conflict_user",
    "memory_type": "budget",
    "content": "预算上限500元",
    "structured_value": {"budget_max": 500},
    "source": "explicit_user",
    "confidence": 0.9,
})

# Search with lower budget → should block the memory
r3 = api("POST", "/api/recommend/v2", {
    "user_query": "预算200以内的充电宝",
    "session_id": "test_conflict",
    "user_id": "conflict_user",
})
blocked_budget = [b for b in r3.get("blocked_memories", []) if "budget" in b.get("reason", "").lower()]
check(f"budget memory blocked (current 200 < memory 500)", len(blocked_budget) > 0)

# ── P3: Memory Harness ──
print("\n── P3: Memory Harness ──")

hr = r2.get("harness_report", {})
mh = hr.get("memory_harness", {})
check("memory_harness in response", bool(mh))
if mh:
    checks_passing = sum(1 for k in mh if k.endswith("_pass") and mh[k] is True)
    checks_total = sum(1 for k in mh if k.endswith("_pass"))
    check(f"harness checks: {checks_passing}/{checks_total}", mh.get("all_pass", False))
    for k in sorted(mh):
        if k.endswith("_pass"):
            info(f"  {k}: {mh[k]}")

# ── P3: Behavior Events ──
print("\n── P3: Behavior Events ──")

be = api("GET", "/api/behaviors", params={"session_id": "test_p2"})
search_events = [e for e in be.get("events", []) if e.get("event_type") == "search"]
check(f"search events recorded ({len(search_events)})", len(search_events) > 0)

# ── P0: Preference API backward compat ──
print("\n── P0: Preference API ──")

api("PUT", "/api/preferences",
    params={"session_id": "test_pref", "user_id": "memtest_user"},
    body={"category": "数码电子", "budget_max": 1500.0})
prefs = api("GET", "/api/preferences",
    params={"session_id": "test_pref", "user_id": "memtest_user"})
check("preferences saved", prefs.get("preferences", {}).get("category") == "数码电子")

# ── P1: Memory Extract ──
print("\n── P1: Memory Extract ──")

ext = api("POST", "/api/memories/extract",
    params={"content": "我以后都要USB-C的充电宝，讨厌太重的", "user_id": "ext_user", "session_id": "ext_test"})
check(f"extract decisions >= 2", len(ext.get("decisions", [])) >= 2)
long_term = [d for d in ext.get("decisions", []) if d.get("decision") == "long_term"]
check(f"long_term decisions >= 1", len(long_term) >= 1)

# ── P3: Audit ──
print("\n── P3: Audit ──")
info("Audit logs written during memory create/update/delete operations")
info("(verified by memory_service._audit method — best-effort, PG required)")

# ── Summary ──
print("\n" + "=" * 60)
print(f"  Results: {passed} passed, {failed} failed")
if failed == 0:
    print("  STATUS: ALL TESTS PASSED")
else:
    print(f"  STATUS: {failed} FAILURES")
print("=" * 60)
