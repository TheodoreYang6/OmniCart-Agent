# -*- coding: utf-8 -*-
"""P2: FollowUpEngine — 统一追问检测引擎。

合并 ContextBuilder (精确模式检测) + RouterAgent._enhance_with_session (模糊追问继承)。
在 Workflow 之前执行，同时输出 context_prompt + updated_constraints。

检测优先级 (高→低):
  1. ordinal_ref:    "第二个怎么样？" → 精确定位商品
  2. last_ref:       "刚才那个能上飞机吗？" → 引用上轮商品
  3. budget_update:  "换成200以内的" → 更新预算
  4. cart_intent:    "加入购物车" → 标记加购意图
  5. compare:        "和刚才那个比哪个好？" → 对比模式
  6. vague_followup: "便宜一点"/"好一点" → 继承品类
  7. budget_only:    "100以内" (无品类词) → 设预算 + 继承品类
"""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---- 中文数字映射 ----

_CN_NUM = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4,
    "六": 5, "七": 6, "八": 7, "九": 8, "十": 9,
    "1": 0, "2": 1, "3": 2, "4": 3, "5": 4,
    "１": 0, "２": 1, "３": 2, "４": 3, "５": 4,
    "第一": 0, "第二": 1, "第三": 2, "第四": 3, "第五": 4,
}

# ---- 正则模式 ----

_ORDINAL_PATTERN = re.compile(
    r"第\s*([一二三四五六七八九十12345１２３４５])\s*[个款种]"
)

_LAST_REF_PATTERN = re.compile(
    r"(刚才|上次|上一).{0,3}[个款种些]|"
    r"[这那]个[东西]|"
    r"前面.{0,3}[个款种]|"
    r"^.{0,2}(它|这个|那个)"
)

_BUDGET_PATTERN = re.compile(
    r"(换成|改成|换|不超过|不要超过|控制在|预算)"
    r".{0,5}?(\d+)\s*(元|块|以内|以下|之内|内)"
)

_CART_PATTERN = re.compile(
    r"(加入购物车|加购|加进购物车|买了|下单|结算)"
)

_COMPARE_PATTERN = re.compile(
    r"(和|跟|与).{0,5}(上一个|刚才|前面).{0,3}(比|对比|比较)|"
    r"(哪个|哪款|哪一个).{0,5}(更适合|更好|更划算)"
)

# ---- 模糊追问关键词（继承品类但不改变预算） ----

_VAGUE_FOLLOWUP_MARKERS = [
    "便宜", "贵", "好一点", "更好", "别的", "其他", "另一个",
    "有没有", "还有", "换一个", "哪个", "怎么样", "多少钱",
    "不要太贵", "贵了", "超预算",
]

# ---- 纯预算信号（含价格修饰但无品类 → 一定是在当前品类内调预算） ----

_BUDGET_SIGNAL_WORDS = ["以下", "以内", "以上", "左右", "预算"]


class FollowUpEngine:
    """统一追问检测 + 上下文构建。"""

    def detect(
        self,
        conversation_id: str = "",
        session_id: str = "",
        current_query: str = "",
        snapshot: dict | None = None,
    ) -> dict:
        """检测追问模式，返回约束更新 + 上下文提示。

        snapshot: 调用方可预取的 context_snapshot（async 路径）；
        未传入时回退同步 PG 读（兼容旧调用方）。

        Returns:
            {
                "is_follow_up": bool,
                "follow_up_type": str | None,
                "resolved_product_id": str | None,
                "updated_constraints": dict,   # {category, sub_category, budget_max, ...}
                "context_prompt": str,
                "cart_intent_product_id": str | None,
            }
        """
        result = {
            "is_follow_up": False,
            "follow_up_type": None,
            "resolved_product_id": None,
            "updated_constraints": {},
            "context_prompt": "",
            "cart_intent_product_id": None,
        }

        # ---- Memory Lite: 一次读取 context_snapshot (约束 + 产品 + 查询 + 摘要) ----
        last_product_ids = []
        last_query = ""
        last_answer = ""
        session_constraints = {}
        conversation_summary = ""
        pending_question = None
        if conversation_id:
            try:
                if snapshot is None:
                    from app.services.conversation_service import get_conversation_service
                    svc = get_conversation_service()
                    snapshot = svc.get_context_snapshot_sync(conversation_id)
                snapshot = snapshot or {}
                # 产品引用 — 兼容新旧格式: [{id,title,brand}] 或 ["P001","P003"]
                last_products_raw = snapshot.get("last_products") or snapshot.get("last_recommended_product_ids", [])
                last_product_ids = []
                last_product_map = {}  # product_id → {title, brand}
                for item in last_products_raw:
                    if isinstance(item, dict):
                        pid = item.get("product_id", "")
                        if pid:
                            last_product_ids.append(pid)
                            last_product_map[pid] = item
                    elif isinstance(item, str):
                        last_product_ids.append(item)
                last_answer = snapshot.get("last_answer", "")
                last_query = snapshot.get("last_query", "")
                # 上下文压缩摘要 + 待回答问题
                conversation_summary = snapshot.get("conversation_summary", "") or ""
                pending_question = snapshot.get("pending_question")
                # 约束 (替代原 PreferenceMemory 读取)
                acc = snapshot.get("constraints", {})
                cur = snapshot.get("current_turn", {})
                session_constraints = dict(acc)
                for k, v in cur.items():
                    if v:
                        session_constraints[k] = v
            except Exception as e:
                logger.debug(f"FollowUpEngine: context_snapshot load skipped: {e}")

        # ---- 检测是否有品类词（换话题了） ----
        explicit_cat = self._detect_category(current_query)

        # =========================================
        # Pattern 1: 序数引用 "第二个怎么样？"
        # =========================================
        ord_match = _ORDINAL_PATTERN.search(current_query)
        if ord_match and last_product_ids:
            idx = _CN_NUM.get(ord_match.group(1), -1)
            if 0 <= idx < len(last_product_ids):
                result["is_follow_up"] = True
                result["follow_up_type"] = "ordinal_ref"
                result["resolved_product_id"] = last_product_ids[idx]

        # =========================================
        # Pattern 1b: 品牌名指代 "Sony那个戴着舒服吗"
        # =========================================
        if not result["is_follow_up"] and last_product_map:
            for pid, info in last_product_map.items():
                brand = info.get("brand", "")
                title = info.get("title", "")
                if brand and brand.lower() in current_query.lower():
                    result["is_follow_up"] = True
                    result["follow_up_type"] = "brand_ref"
                    result["resolved_product_id"] = pid
                    break
                if title and len(title) >= 4 and title[:4].lower() in current_query.lower():
                    result["is_follow_up"] = True
                    result["follow_up_type"] = "title_ref"
                    result["resolved_product_id"] = pid
                    break

        # =========================================
        # Pattern 2: 上次引用 "刚才那个"/"这个"
        # =========================================
        if not result["is_follow_up"] and _LAST_REF_PATTERN.search(current_query):
            if last_product_ids:
                result["is_follow_up"] = True
                result["follow_up_type"] = "last_ref"
                result["resolved_product_id"] = last_product_ids[0]

        # =========================================
        # Pattern 3: 预算更新 "换成200以内的"
        # =========================================
        budget_match = _BUDGET_PATTERN.search(current_query)
        if budget_match:
            budget = float(budget_match.group(2))
            result["is_follow_up"] = True
            if not result["follow_up_type"]:
                result["follow_up_type"] = "budget_update"
            result["updated_constraints"]["budget_max"] = budget

        # =========================================
        # Pattern 4: 购物车意图 "加入购物车"
        # =========================================
        if _CART_PATTERN.search(current_query):
            if not result["is_follow_up"]:
                result["is_follow_up"] = True
                result["follow_up_type"] = "cart_intent"
            if result["resolved_product_id"]:
                result["cart_intent_product_id"] = result["resolved_product_id"]
            elif last_product_ids:
                result["cart_intent_product_id"] = last_product_ids[0]

        # =========================================
        # Pattern 5: 对比意图 "和刚才那个比"
        # =========================================
        if not result["is_follow_up"] and _COMPARE_PATTERN.search(current_query):
            if last_product_ids:
                result["is_follow_up"] = True
                result["follow_up_type"] = "compare"
                result["resolved_product_id"] = last_product_ids[0]

        # =========================================
        # Pattern 6: 模糊追问 "便宜一点"/"好一点" (没换品类)
        # =========================================
        is_vague = any(m in current_query for m in _VAGUE_FOLLOWUP_MARKERS)
        if not result["is_follow_up"] and is_vague and not explicit_cat:
            result["is_follow_up"] = True
            result["follow_up_type"] = "vague_followup"
            self._inherit_constraints(result, session_constraints)

        # =========================================
        # Pattern 7: 纯预算/价格修饰 (无品类词 → 在当前品类)  "100以内"
        # =========================================
        has_budget_signal = any(w in current_query for w in _BUDGET_SIGNAL_WORDS)
        has_budget_amount = self._detect_budget(current_query) is not None
        is_budget_only = (has_budget_signal or has_budget_amount) and not explicit_cat
        if not result["is_follow_up"] and is_budget_only and session_constraints:
            result["is_follow_up"] = True
            if not result["follow_up_type"]:
                result["follow_up_type"] = "budget_only"
            self._inherit_constraints(result, session_constraints)
            # 从 query 中提取预算金额
            b = self._detect_budget(current_query)
            if b:
                result["updated_constraints"]["budget_max"] = b

        # =========================================
        # 构建 context_prompt
        # =========================================
        # 用户明显切换品类时，清空上轮上下文避免旧品类干扰
        _switched_category = bool(explicit_cat and session_constraints.get("category")
                                  and explicit_cat != session_constraints.get("category"))
        result["context_prompt"] = self._build_prompt(
            result=result,
            last_answer="" if _switched_category else last_answer,
            last_query="" if _switched_category else last_query,
            last_product_ids=[] if _switched_category else last_product_ids,
            conversation_summary=conversation_summary,
            pending_question=pending_question,
        )

        return result

    # ---- 继承 session 约束 ----

    def _inherit_constraints(self, result: dict, session: dict):
        """将 session 累积约束写入 updated_constraints（不覆盖已设置的值）。"""
        uc = result["updated_constraints"]
        for key in ("category", "sub_category", "scenario", "budget_max", "budget_min"):
            if key not in uc or uc[key] is None:
                v = session.get(key)
                if v:
                    uc[key] = v

    # ---- 品类检测 (复用 rules) ----

    @staticmethod
    def _detect_category(query: str) -> Optional[str]:
        try:
            from app.decision.rules import detect_category
            return detect_category(query)
        except Exception:
            return None

    # ---- 预算检测 (复用 rules) ----

    @staticmethod
    def _detect_budget(query: str) -> Optional[float]:
        try:
            from app.decision.rules import detect_budget
            return detect_budget(query)
        except Exception:
            return None

    # ---- 构建上下文提示 ----

    @staticmethod
    def _build_prompt(result: dict, last_answer: str, last_query: str,
                      last_product_ids: list, conversation_summary: str = "",
                      pending_question: str | None = None) -> str:
        parts = []
        ft = result["follow_up_type"]
        pid = result["resolved_product_id"]
        budget = result["updated_constraints"].get("budget_max")

        # ---- Layer 2 (冷): 历史对话压缩摘要 ----
        if conversation_summary:
            parts.append(f"[对话历史] {conversation_summary}")

        # ---- 追问类型标记 ----
        if ft == "ordinal_ref" and pid:
            parts.append(
                f"[Follow-up] 用户询问上轮推荐中的商品 ({pid})。"
                f"请围绕这个具体商品回答。"
            )
        elif ft == "last_ref" and pid:
            parts.append(
                f"[Follow-up] 用户引用上轮商品 ({pid})。"
                f"请围绕这个商品回答。"
            )
        elif ft == "budget_update" and budget:
            parts.append(
                f"[Follow-up] 用户将预算调整为 {budget} 元以内。"
                f"请在此预算内推荐。"
            )
        elif ft == "cart_intent":
            parts.append(
                f"[Follow-up] 用户想将商品 ({pid or '上轮第一个'}) 加入购物车。"
                f"请确认并操作。"
            )
        elif ft == "compare" and pid:
            parts.append(
                f"[Follow-up] 用户想对比商品 ({pid}) 与替代品。"
                f"请提供对比分析。"
            )
        elif ft in ("vague_followup", "budget_only"):
            uc = result["updated_constraints"]
            details = []
            if uc.get("category"):
                details.append(f"品类={uc['category']}")
            if uc.get("budget_max"):
                details.append(f"预算≤{uc['budget_max']}")
            parts.append(
                f"[Follow-up] 用户在当前上下文下追问（{'，'.join(details) if details else '继承上轮约束'}）。"
            )

        # ---- 问答链: 欧米问了问题，用户正在回答 ----
        if pending_question and result["is_follow_up"]:
            parts.append(f"[问答链] 上轮欧米问: {pending_question}")

        # ---- Layer 1 (热): 最近一轮原文 ----
        if last_answer:
            parts.append(f"[上次回答] {last_answer[:200]}")
        if last_query:
            parts.append(f"[上次提问] {last_query[:200]}")
        if last_product_ids:
            parts.append(f"[上轮商品ID] {', '.join(last_product_ids[:5])}")

        return "\n".join(parts)


# ---- Singleton ----

_engine: FollowUpEngine | None = None


def get_followup_engine() -> FollowUpEngine:
    global _engine
    if _engine is None:
        _engine = FollowUpEngine()
    return _engine
