# -*- coding: utf-8 -*-
"""Memory Lite P2-1: Context Builder - follow-up detection and context construction.

Rule-based (no LLM), detects 5 follow-up patterns:
1. ordinal_ref: "the second one?" -> locate product from last recommendation
2. last_ref: "the previous one" -> reference last product
3. budget_update: "change to under 200" -> update budget constraint
4. cart_intent: "add the first one to cart" -> locate product + cart action
5. compare: "which is better compared to the last one?" -> comparison mode
"""

import re
import logging

logger = logging.getLogger(__name__)

_CN_NUM = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4,
    "六": 5, "七": 6, "八": 7, "九": 8, "十": 9,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4,
    "１": 0, "２": 1, "３": 2, "４": 3, "５": 4,
    "第一": 0, "第二": 1, "第三": 2, "第四": 3, "第五": 4,
}

_ORDINAL_PATTERN = re.compile(
    r"第\s*([一二三四五六七八九十"
    r"12345１２３４５])\s*[个款种]"
)

_LAST_REF_PATTERN = re.compile(
    r"(刚才|上次|上一).{0,3}[个款种些]|"
    r"[这那]个[东西]|"
    r"前面.{0,3}[个款种]|"
    r"^.{0,2}(它|这个|那个)"
)

_BUDGET_PATTERN = re.compile(
    r"(换成|改成|换|不超过|"
    r"不要超过|控制在|预算)"
    r".{0,5}?(\d+)\s*(元|块|以内|以下|之内|内)"
)

_CART_PATTERN = re.compile(
    r"(加入购物车|加购|"
    r"加进购物车|买了|下单|结算)"
)

_COMPARE_PATTERN = re.compile(
    r"(和|跟|与).{0,5}"
    r"(上一个|刚才|前面).{0,3}"
    r"(比|对比|比较)|"
    r"(哪个|哪款|哪一个).{0,5}"
    r"(更适合|更好|更划算)"
)


class ContextBuilder:

    def build(self, conversation_id: str, current_query: str,
              user_id: str = "", session_id: str = "") -> dict:
        result = {
            "is_follow_up": False,
            "follow_up_type": None,
            "resolved_product_id": None,
            "resolved_product_index": None,
            "updated_budget": None,
            "updated_constraints": {},
            "context_prompt": "",
            "cart_intent_product_id": None,
        }

        if not conversation_id:
            return result

        try:
            from app.services.conversation_service import get_conversation_service
            svc = get_conversation_service()
            ctx = svc.get_context(conversation_id, limit=6)
        except Exception as e:
            logger.debug(f"ContextBuilder load failed: {e}")
            return result

        snapshot = ctx.get("context_snapshot", {})
        last_product_ids = snapshot.get("last_recommended_product_ids", [])
        last_answer = snapshot.get("last_answer", "")
        last_query = snapshot.get("last_query", "")

        # Pattern 1: ordinal reference
        ord_match = _ORDINAL_PATTERN.search(current_query)
        if ord_match and last_product_ids:
            idx = _CN_NUM.get(ord_match.group(1), -1)
            if 0 <= idx < len(last_product_ids):
                result["is_follow_up"] = True
                result["follow_up_type"] = "ordinal_ref"
                result["resolved_product_index"] = idx
                result["resolved_product_id"] = last_product_ids[idx]

        # Pattern 2: last reference
        if not result["is_follow_up"] and _LAST_REF_PATTERN.search(current_query):
            if last_product_ids:
                result["is_follow_up"] = True
                result["follow_up_type"] = "last_ref"
                result["resolved_product_index"] = 0
                result["resolved_product_id"] = last_product_ids[0]

        # Pattern 3: budget update
        budget_match = _BUDGET_PATTERN.search(current_query)
        if budget_match:
            budget = float(budget_match.group(2))
            result["is_follow_up"] = True
            if not result["follow_up_type"]:
                result["follow_up_type"] = "budget_update"
            result["updated_budget"] = budget
            result["updated_constraints"]["budget_max"] = budget

        # Pattern 4: cart intent
        if _CART_PATTERN.search(current_query):
            if not result["is_follow_up"]:
                result["is_follow_up"] = True
                result["follow_up_type"] = "cart_intent"
            if result["resolved_product_id"]:
                result["cart_intent_product_id"] = result["resolved_product_id"]
            elif last_product_ids:
                result["cart_intent_product_id"] = last_product_ids[0]

        # Pattern 5: compare intent
        if not result["is_follow_up"] and _COMPARE_PATTERN.search(current_query):
            if last_product_ids:
                result["is_follow_up"] = True
                result["follow_up_type"] = "compare"
                result["resolved_product_id"] = last_product_ids[0]

        # Build context prompt
        result["context_prompt"] = self._build_prompt(
            follow_up_type=result["follow_up_type"],
            resolved_product_id=result["resolved_product_id"],
            resolved_index=result["resolved_product_index"],
            last_answer=last_answer,
            last_query=last_query,
            last_product_ids=last_product_ids,
            current_query=current_query,
            snapshot=snapshot,
            updated_budget=result["updated_budget"],
        )

        return result

    def _build_prompt(self, follow_up_type, resolved_product_id, resolved_index,
                      last_answer, last_query, last_product_ids, current_query,
                      snapshot, updated_budget=None):
        parts = []

        if follow_up_type == "ordinal_ref" and resolved_product_id:
            idx = (resolved_index or 0) + 1
            parts.append(
                f"[Follow-up: ordinal_ref] User refers to product #{idx} "
                f"from the last recommendation (ID: {resolved_product_id}). "
                f"Answer about this specific product."
            )

        elif follow_up_type == "last_ref" and resolved_product_id:
            parts.append(
                f"[Follow-up: last_ref] User refers to the previous product "
                f"(ID: {resolved_product_id}). Answer about this product."
            )

        elif follow_up_type == "budget_update":
            budget = updated_budget or "unknown"
            parts.append(
                f"[Follow-up: budget_update] User updated budget to {budget} CNY max. "
                f"Re-rank products within this budget."
            )

        elif follow_up_type == "cart_intent":
            pid = resolved_product_id or "unknown"
            parts.append(
                f"[Follow-up: cart_intent] User wants to add product "
                f"(ID: {pid}) to cart. Confirm and proceed."
            )

        elif follow_up_type == "compare" and resolved_product_id:
            parts.append(
                f"[Follow-up: compare] User wants to compare product "
                f"(ID: {resolved_product_id}) with alternatives."
            )

        if last_answer:
            parts.append(f"[Last Answer] {last_answer[:300]}")

        if last_query:
            parts.append(f"[Last User Query] {last_query[:200]}")

        if last_product_ids:
            parts.append(f"[Last Product IDs] {', '.join(last_product_ids[:5])}")

        return "\n".join(parts)


_builder: ContextBuilder | None = None


def get_context_builder() -> ContextBuilder:
    global _builder
    if _builder is None:
        _builder = ContextBuilder()
    return _builder
