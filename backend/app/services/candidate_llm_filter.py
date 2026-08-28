"""V9 闭集候选 LLM Filter。

模型只能在已经过向量聚合和 rerank 的 Top 12 中做购物判断。解析、ID、预算与
明确避雷项都由服务端复核；任何不可靠响应都稳定退回 rerank 顺序。
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.core.config import ENABLE_V9_LLM_FILTER, V9_FILTER_TIMEOUT
from app.model_gateway.gateway import get_model_gateway
from app.prompts.agent_prompts import CANDIDATE_FILTER_SYSTEM, build_candidate_filter_prompt

_LIST_FIELDS = ("primary", "alternative", "conditional", "exclude")


def plan_snapshot(plan: Any, constraints: Any | None = None) -> dict[str, Any]:
    """Pydantic / dict 统一为模型可读、可审计的小输入。"""
    def get(name: str, default=None):
        return plan.get(name, default) if isinstance(plan, dict) else getattr(plan, name, default)
    def cget(name: str, default=None):
        return constraints.get(name, default) if isinstance(constraints, dict) else getattr(constraints, name, default)
    return {
        "intent": get("intent", "recommend"),
        "must_constraints": list(get("must_constraints", []) or cget("must_tags", []) or []),
        "soft_preferences": list(get("soft_preferences", []) or []),
        "avoid_constraints": list(get("avoid_constraints", []) or cget("exclude_tags", []) or []),
        "evidence_focus": list(get("evidence_focus", []) or []),
        "answer_goal": get("answer_goal", "推荐合适商品"),
        "category": cget("category", get("category", None)),
        "budget_max": cget("budget_max", get("budget_hint", None)),
    }


def candidate_summary(candidate: dict[str, Any], rank: int) -> dict[str, Any]:
    chunks = candidate.get("matched_chunks") or []
    evidence = []
    seen = set()
    for chunk in chunks:
        payload = chunk.get("payload", chunk) if isinstance(chunk, dict) else {}
        typ = str(payload.get("chunk_type") or chunk.get("chunk_type") or "")
        text = str(payload.get("text") or chunk.get("text") or "")[:180]
        if typ and typ not in seen and text:
            evidence.append({"type": typ, "text": text})
            seen.add(typ)
    facts = candidate.get("product_facts") or []
    return {
        "product_id": candidate.get("product_id", ""), "rank": rank,
        "identity": {key: candidate.get(key) for key in ("title", "brand", "category", "sub_category", "price")},
        "facts": [{"key": f.get("fact_key", f.get("key", "")),
                    "value": f.get("value_text", f.get("value", "")),
                    "verified": bool(f.get("verified", False))} for f in facts[:8]],
        "evidence": evidence[:5],
        "rerank_relevance": round(float(candidate.get("relevance_score", 0) or 0), 4),
    }


def _parse_json(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else raw
        raw = raw.removeprefix("json").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {}


def deterministic_filter(candidates: list[dict], plan: dict[str, Any], reason: str = "") -> dict[str, Any]:
    """模型不可用时不丢候选，保留 rerank 前列并诚实标注降级。"""
    budget = plan.get("budget_max")
    allowed = [p for p in candidates if budget is None or float(p.get("price", 0) or 0) <= float(budget)]
    selected = allowed or candidates
    primary = [{"product_id": p.get("product_id", ""),
                "reason": "与本次需求的语义和商品信息匹配，建议先看这款。",
                "evidence_types": [c.get("chunk_type", "identity") for c in (p.get("matched_chunks") or [])[:2]]}
               for p in selected[:3] if p.get("product_id")]
    alternative = [{"product_id": p.get("product_id", ""),
                    "reason": "可作为同类备选，具体条件请查看商品信息。", "evidence_types": []}
                   for p in selected[3:9] if p.get("product_id")]
    return {"primary": primary, "alternative": alternative, "conditional": [], "exclude": [],
            "missing_group": "", "status": "fallback", "fallback_reason": reason}


def validate_filter_result(raw: dict[str, Any], candidates: list[dict], plan: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {str(p.get("product_id")) for p in candidates if p.get("product_id")}
    if not raw or not allowed:
        return None
    output: dict[str, Any] = {field: [] for field in _LIST_FIELDS}
    used: set[str] = set()
    budget = plan.get("budget_max")
    price = {str(p.get("product_id")): float(p.get("price", 0) or 0) for p in candidates}
    for field in _LIST_FIELDS:
        items = raw.get(field, [])
        if not isinstance(items, list):
            return None
        for item in items:
            if not isinstance(item, dict):
                return None
            pid = str(item.get("product_id") or "")
            if pid not in allowed or pid in used:
                continue
            # 预算是服务器硬校验。模型可说明超预算，但不得把它放进推荐区。
            if field in ("primary", "alternative", "conditional") and budget is not None and price[pid] > float(budget):
                output["exclude"].append({"product_id": pid, "reason": "超出本次预算"})
                used.add(pid)
                continue
            used.add(pid)
            output[field].append({
                "product_id": pid, "reason": str(item.get("reason") or "")[:180],
                "evidence_types": [str(x) for x in (item.get("evidence_types") or [])[:5]],
            })
    # 模型把全部候选排除却没有报告缺组，是不合格的推荐输出。
    if not any(output[key] for key in ("primary", "alternative", "conditional")) and not str(raw.get("missing_group") or ""):
        return None
    output["missing_group"] = str(raw.get("missing_group") or "")[:180]
    output["status"] = "model"
    return output


class CandidateLLMFilter:
    async def filter(self, *, query: str, plan: Any, constraints: Any, candidates: list[dict]) -> dict[str, Any]:
        snapshot = plan_snapshot(plan, constraints)
        intent = snapshot["intent"]
        if (not ENABLE_V9_LLM_FILTER or len(candidates) < 2 or
                intent not in {"recommend", "bundle", "gift", "alternative"}):
            return deterministic_filter(candidates, snapshot, "filter_skipped")
        prompt = build_candidate_filter_prompt(
            query, snapshot, [candidate_summary(c, i + 1) for i, c in enumerate(candidates)])
        try:
            raw_text = await asyncio.wait_for(
                get_model_gateway().chat("chat_generation", prompt, CANDIDATE_FILTER_SYSTEM),
                timeout=V9_FILTER_TIMEOUT,
            )
            result = validate_filter_result(_parse_json(raw_text), candidates, snapshot)
            if result is not None:
                return result
            return deterministic_filter(candidates, snapshot, "invalid_filter_output")
        except Exception as exc:  # fail-open: rerank 是上一层已经验证过的候选顺序
            return deterministic_filter(candidates, snapshot, f"filter_unavailable:{type(exc).__name__}")
