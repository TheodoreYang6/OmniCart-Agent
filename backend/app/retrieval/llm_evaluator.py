"""LLM 证据评估器 — 让 LLM 直接阅读商品 rag_knowledge 并评判。

与旧 keyword_match 的本质区别:
- 旧: jieba 分词 → 关键词命中计数 → 分数
- 新: LLM 逐件阅读 (描述 + FAQ + 评价) → 基于证据给出相关性和推荐理由

一次 LLM 调用评估全部候选商品，支持横向对比。
"""

import json
import logging
import re
import time
from typing import Optional

from app.core.cache import cached, make_key
from app.core.config import REDIS_CACHE_TTL_SEARCH
from app.model_gateway.gateway import get_model_gateway

logger = logging.getLogger(__name__)

# 评估用 System Prompt
EVALUATOR_SYSTEM = """你是一个资深购物决策专家。用户会告诉你他的购物需求，你需要逐件评估候选商品。

## 评估原则
1. **证据驱动**: 每个判断必须引用商品的具体证据（描述、FAQ、用户评价），不能凭空猜测
2. **用户视角**: 从用户的具体需求出发，而不是泛泛地评价商品好坏
3. **风险意识**: 如果评价中有人提到过敏、质量问题、不适用等，必须在风险中标注
4. **横向对比**: 在所有商品评估完后，给出排名和对比分析
5. **诚实**: 商品不适合就是不合适，不要因为评分高就强行推荐

## 评分锚点
- 0.85-1.0: 完美匹配，证据充分支持
- 0.70-0.85: 较好匹配，多数需求满足
- 0.55-0.70: 部分匹配，有可取之处但存在不足
- 0.40-0.55: 勉强相关，基本不推荐
- 0.00-0.40: 不相关或不适合

## 输出格式
只输出JSON，不要任何其他内容:
{
  "evaluations": [
    {
      "product_id": "商品ID",
      "relevance": 0.0-1.0,
      "reasoning": "基于证据的简短理由（2-3句话，必须引用具体评价或FAQ）",
      "strengths": ["优点1", "优点2"],
      "risks": ["风险1（如有）"],
      "best_for": "最适合哪类用户/场景",
      "verdict": "strong_recommend|recommend|consider|avoid"
    }
  ],
  "ranked_product_ids": ["p_id1", "p_id2", ...],
  "overall_analysis": "整体分析（2-3句话，说明排名逻辑和关键发现）",
  "user_warnings": ["需要提醒用户注意的事项"]
}"""


class LlmEvaluator:
    """LLM 证据评估器 — 一次调用完成所有候选商品的评判和排名。"""

    def __init__(self):
        self._gateway = get_model_gateway()

    async def evaluate(
        self,
        query: str,
        constraints: dict | None = None,
        candidates: list[dict] | None = None,
        top_n: int = 10,
    ) -> dict:
        """LLM 评估候选商品。

        Args:
            query: 用户原始查询
            constraints: 约束条件 {category, sub_category, budget_max, budget_min, scenario}
            candidates: 候选商品列表（来自语义检索）
            top_n: 最多评估前 N 件

        Returns:
            {
                "evaluations": [{product_id, relevance, reasoning, strengths, risks, best_for, verdict}],
                "ranked_product_ids": [...],
                "overall_analysis": "...",
                "user_warnings": [...]
            }
        """
        if not candidates:
            return {"evaluations": [], "ranked_product_ids": [], "overall_analysis": "", "user_warnings": []}

        candidates = candidates[:top_n]

        cache_key = make_key("llm_eval", query,
                             json.dumps(constraints or {}, ensure_ascii=False, sort_keys=True),
                             json.dumps([c.get("product_id", "") for c in candidates], ensure_ascii=False))

        async def _do_evaluate() -> dict:
            return await self._evaluate_impl(query, constraints, candidates)

        return await cached(cache_key, REDIS_CACHE_TTL_SEARCH, _do_evaluate,
                          serializer=lambda v: json.dumps(v, ensure_ascii=False),
                          deserializer=lambda s: json.loads(s))

    async def _evaluate_impl(
        self,
        query: str,
        constraints: dict | None,
        candidates: list[dict],
    ) -> dict:
        prompt = self._build_prompt(query, constraints, candidates)

        try:
            t0 = time.perf_counter()
            raw = await self._gateway.chat("chat_generation", prompt, EVALUATOR_SYSTEM)
            elapsed = time.perf_counter() - t0
            logger.info(f"LLM evaluation completed in {elapsed:.1f}s, input ~{len(prompt)} chars")

            result = self._parse_result(raw, candidates)
            return result
        except Exception as e:
            logger.error(f"LLM evaluation failed: {e}")
            return self._fallback_evaluation(candidates)

    def _build_prompt(
        self,
        query: str,
        constraints: dict | None,
        candidates: list[dict],
    ) -> str:
        constraints = constraints or {}
        lines = [
            "## 用户需求",
            f"用户说: {query}",
        ]

        if constraints.get("category"):
            lines.append(f"品类: {constraints['category']}")
        if constraints.get("sub_category"):
            lines.append(f"子品类: {constraints['sub_category']}")
        if constraints.get("budget_max"):
            lines.append(f"预算上限: ¥{constraints['budget_max']}")
        if constraints.get("budget_min"):
            lines.append(f"预算下限: ¥{constraints['budget_min']}")
        if constraints.get("scenario"):
            lines.append(f"使用场景: {constraints['scenario']}")

        lines.append("")
        lines.append(f"## 候选商品 (共{len(candidates)}件)")
        lines.append("")

        for i, item in enumerate(candidates, 1):
            lines.append(self._format_product(i, item))

        return "\n".join(lines)

    def _format_product(self, index: int, item: dict) -> str:
        """将一件商品格式化为 LLM 可读的文本块。"""
        rk = item.get("rag_knowledge") or {}
        lines = [
            f"### 商品 {index}: {item.get('product_id', '')}",
            f"名称: {item.get('title', '')}",
            f"品牌: {item.get('brand', '')}",
            f"品类: {item.get('category', '')} / {item.get('sub_category', '')}",
            f"价格: ¥{item.get('price', 0):.0f}",
        ]

        # 描述（截取前150字，减小 prompt 体积）
        desc = rk.get("marketing_description", "") if isinstance(rk, dict) else ""
        if desc:
            lines.append(f"描述: {desc[:150]}")

        # FAQ（最多3条，答案截取前60字）
        faqs = rk.get("official_faq", []) if isinstance(rk, dict) else []
        if faqs:
            lines.append("常见问题:")
            for faq in faqs[:3]:
                q = faq.get("question", "") if isinstance(faq, dict) else ""
                a = faq.get("answer", "") if isinstance(faq, dict) else ""
                lines.append(f"  Q: {q}")
                lines.append(f"  A: {a[:60]}")

        # 评价（最多3条，内容截取前50字）
        reviews = rk.get("user_reviews", []) if isinstance(rk, dict) else []
        if reviews:
            ratings = [r.get("rating", 3) if isinstance(r, dict) else 3 for r in reviews]
            avg = sum(ratings) / len(ratings) if ratings else 0
            lines.append(f"用户评价 (均分{avg:.1f}/5, {len(reviews)}条):")
            for rev in reviews[:3]:
                nickname = rev.get("nickname", "") if isinstance(rev, dict) else ""
                rating = rev.get("rating", 3) if isinstance(rev, dict) else 3
                content = rev.get("content", "") if isinstance(rev, dict) else ""
                lines.append(f"  [{nickname} {rating}★] {content[:50]}")

        lines.append("")
        return "\n".join(lines)

    def _parse_result(self, raw: str, candidates: list[dict]) -> dict:
        """解析 LLM JSON 输出，失败时降级。"""
        raw = raw.strip()

        # 提取 JSON 块
        if "```" in raw:
            blocks = raw.split("```")
            for block in blocks:
                block = block.strip()
                if block.startswith("json"):
                    block = block[4:]
                if block.startswith("{"):
                    raw = block
                    break

        # 尝试找 JSON 起始位置
        json_start = raw.find("{")
        if json_start > 0:
            raw = raw[json_start:]

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # 尝试修复常见 JSON 错误
            cleaned = re.sub(r",\s*}", "}", raw)
            cleaned = re.sub(r",\s*]", "]", cleaned)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                logger.warning(f"LLM JSON 解析失败，使用降级评估。raw preview: {raw[:200]}")
                return self._fallback_evaluation(candidates)

    def _fallback_evaluation(self, candidates: list[dict]) -> dict:
        """LLM 不可用时的降级评估 — 基于向量相似度分数的简单排序。"""
        evals = []
        for c in candidates:
            score = c.get("score", 0.5)
            evals.append({
                "product_id": c.get("product_id", ""),
                "relevance": max(0.3, min(1.0, score)),
                "reasoning": f"基于语义相似度评分: {score:.3f}",
                "strengths": [],
                "risks": [],
                "best_for": "",
                "verdict": "consider",
            })

        ranked = sorted(evals, key=lambda x: x["relevance"], reverse=True)
        return {
            "evaluations": evals,
            "ranked_product_ids": [e["product_id"] for e in ranked],
            "overall_analysis": "LLM 评估不可用，基于语义相似度排序。",
            "user_warnings": ["当前为降级模式，推荐结果仅供参考。"],
        }
