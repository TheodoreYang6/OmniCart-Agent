"""RAG 生成侧评测指标: Faithfulness / Context Precision / Context Recall.

基于 LLM-as-Judge 实现，使用项目已有 ModelGateway (qwen-turbo)。
不引入 RAGAS 等外部库，直接复用项目基础设施。

指标说明:
- Faithfulness:  生成回答中的声明是否能从检索上下文中找到支撑
- Context Precision: 检索到的文档中有多少真正与问题相关 (rank-aware)
- Context Recall:    回答所需的关键信息是否都在检索上下文中
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.model_gateway.gateway import get_model_gateway
from app.prompts.eval_prompts import (
    CONTEXT_PRECISION_SYSTEM,
    CONTEXT_RECALL_SYSTEM,
    FAITHFULNESS_SYSTEM,
    build_context_precision_user,
    build_context_recall_user,
    build_faithfulness_user,
)

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────

def _build_context_text(retrieved_products: list[dict], max_products: int = 10) -> str:
    """将检索到的商品列表压缩为评估用的上下文字符串, 包含FAQ和评论."""
    if not retrieved_products:
        return "(无检索结果)"

    parts = []
    for i, p in enumerate(retrieved_products[:max_products], 1):
        pid = p.get("product_id", "?")
        title = p.get("title", "")
        brand = p.get("brand", "")
        category = p.get("category", "")
        sub = p.get("sub_category", "")
        price = p.get("price", 0)

        rk = p.get("rag_knowledge")
        if not isinstance(rk, dict):
            rk = {}

        desc = (rk.get("marketing_description", "") or "")[:300]

        # FAQ (最多3条,答案截断80字)
        faq_lines = []
        for faq in (rk.get("official_faq", []) or [])[:3]:
            if isinstance(faq, dict):
                q = faq.get("question", "")[:80]
                a = faq.get("answer", "")[:80]
                faq_lines.append(f"  Q: {q}\n  A: {a}")

        # 评论 (最多3条,截断60字)
        review_lines = []
        for rev in (rk.get("user_reviews", []) or [])[:3]:
            if isinstance(rev, dict):
                nick = rev.get("nickname", "")
                rating = rev.get("rating", 0)
                content = (rev.get("content", "") or "")[:60]
                review_lines.append(f"  [{nick} {rating}★] {content}")

        # 匹配chunk片段
        chunk_texts = []
        for mc in p.get("matched_chunks", [])[:3]:
            ct = mc.get("payload", {}).get("text", "")
            if ct:
                chunk_texts.append(ct[:200])

        lines = [
            f"[文档{i}] {title}",
            f"品牌: {brand} | 品类: {category}/{sub} | 价格: ¥{price:.0f}",
            f"描述: {desc}" if desc else "",
        ]
        if faq_lines:
            lines.append("FAQ:")
            lines.extend(faq_lines)
        if review_lines:
            lines.append("用户评论:")
            lines.extend(review_lines)
        if chunk_texts:
            lines.append("匹配片段: " + " | ".join(chunk_texts))
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _parse_json(raw: str) -> dict:
    """从 LLM 输出中提取 JSON, 做容错处理。"""
    raw = raw.strip()
    if "```" in raw:
        for block in raw.split("```"):
            block = block.strip()
            if block.startswith("json"):
                block = block[4:]
            if block.startswith("{"):
                raw = block
                break
    json_start = raw.find("{")
    if json_start > 0:
        raw = raw[json_start:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*}", "}", raw)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning(f"JSON解析失败, raw preview: {raw[:300]}")
            return {}


def _build_response_context(retrieved_products: list[dict], user_query: str, context_n: int = 5) -> str:
    """构建给Response LLM的上下文(用于评测中的回答生成)。"""
    ctx_parts = [f"## 用户需求\n{user_query}\n\n## 候选商品"]
    for i, p in enumerate(retrieved_products[:context_n], 1):
        rk = p.get("rag_knowledge") or {}
        desc = ""
        if isinstance(rk, dict):
            desc = (rk.get("marketing_description", "") or "")[:200]
        ctx_parts.append(
            f"{i}. {p.get('brand','')} {p.get('title','')} | "
            f"¥{p.get('price',0):.0f} | {p.get('category','')}/{p.get('sub_category','')}"
        )
        if desc:
            ctx_parts.append(f"   描述: {desc}")
    return "\n".join(ctx_parts)


def compute_retrieval_metrics(
    retrieved_ids: list[str],
    relevant_ids: set[str],
    relevance_grades: dict[str, int],
) -> dict:
    """同步计算传统检索指标: Recall@K / MRR / NDCG@K.

    Args:
        retrieved_ids: 检索结果的product_id列表(有序)
        relevant_ids: ground truth相关商品ID集合
        relevance_grades: {product_id: grade 0-3}

    Returns:
        {recall_at_5, recall_at_10, mrr, ndcg_at_10}
    """
    if not retrieved_ids:
        return {"recall_at_5": 0.0, "recall_at_10": 0.0, "mrr": 0.0, "ndcg_at_10": 0.0}

    # Recall@K
    def _recall_at_k(k: int) -> float:
        if not relevant_ids:
            return 0.0
        hits = set(retrieved_ids[:k]) & relevant_ids
        return round(len(hits) / len(relevant_ids), 4)

    # MRR
    def _mrr() -> float:
        if not relevant_ids:
            return 0.0
        for i, pid in enumerate(retrieved_ids):
            if pid in relevant_ids:
                return round(1.0 / (i + 1), 4)
        return 0.0

    # NDCG@K
    def _ndcg_at_k(k: int) -> float:
        if not relevance_grades:
            return 0.0
        import math
        dcg = 0.0
        for i, pid in enumerate(retrieved_ids[:k]):
            rel = relevance_grades.get(pid, 0)
            dcg += (2 ** rel - 1) / math.log2(i + 2)

        ideal_rels = sorted(relevance_grades.values(), reverse=True)[:k]
        idcg = sum((2 ** rel - 1) / math.log2(i + 2) for i, rel in enumerate(ideal_rels))
        return round(dcg / idcg, 4) if idcg > 0 else 0.0

    return {
        "recall_at_5": _recall_at_k(5),
        "recall_at_10": _recall_at_k(10),
        "mrr": _mrr(),
        "ndcg_at_10": _ndcg_at_k(10),
    }


# ── Core Metrics ─────────────────────────────────────────────────

async def compute_faithfulness(
    answer: str,
    retrieved_products: list[dict],
    gateway=None,
) -> dict:
    """计算 Faithfulness (忠实度)。

    流程: LLM提取声明 → 逐条验证是否被上下文支撑 → 计分

    Returns:
        {score: float, statements: list, summary: str, latency_ms: int}
    """
    if not answer or not answer.strip():
        return {"score": 0.0, "statements": [], "summary": "回答为空", "latency_ms": 0}

    if not retrieved_products:
        return {"score": 0.0, "statements": [], "summary": "无检索上下文", "latency_ms": 0}

    gw = gateway or get_model_gateway()
    context = _build_context_text(retrieved_products)

    prompt = build_faithfulness_user(answer, context)

    t0 = time.perf_counter()
    try:
        raw = await gw.chat("chat_generation", prompt, FAITHFULNESS_SYSTEM)
        result = _parse_json(raw)
        latency = int((time.perf_counter() - t0) * 1000)

        statements = result.get("statements", [])
        if statements:
            supported = sum(1 for s in statements if s.get("supported"))
            score = round(supported / len(statements), 4)
        else:
            score = result.get("faithfulness", 0.0)

        return {
            "score": score,
            "statements": statements,
            "summary": result.get("summary", ""),
            "latency_ms": latency,
        }
    except Exception as e:
        logger.error(f"Faithfulness计算失败: {e}")
        return {"score": 0.0, "statements": [], "summary": str(e), "latency_ms": 0}


async def compute_context_precision(
    query: str,
    retrieved_products: list[dict],
    relevant_product_ids: list[str],
    gateway=None,
    top_k: int = 10,
) -> dict:
    """计算 Context Precision (上下文精准度, rank-aware)。

    使用 Average Precision 公式,考虑排序位置:
    AP = Σ(P@k × rel@k) / total_relevant_in_ground_truth

    优先用 ground truth relevant_product_ids 做精确匹配;
    如未提供则用 LLM 逐条判定相关度。

    Returns:
        {score: float, verdicts: list, is_llm_judged: bool, latency_ms: int}
    """
    if not retrieved_products:
        return {"score": 0.0, "verdicts": [], "is_llm_judged": False, "latency_ms": 0}

    candidates = retrieved_products[:top_k]
    candidate_ids = [p.get("product_id", "") for p in candidates]

    # 快速路径: 有标注时直接用 ground truth 计算
    if relevant_product_ids:
        rel_set = set(relevant_product_ids)
        verdicts = [{"product_id": pid, "relevant": 1 if pid in rel_set else 0} for pid in candidate_ids]

        # AP = Σ(P@k × rel@k) / |relevant|, 分母用ground truth全部相关商品数
        relevant_count = 0
        precision_sum = 0.0
        for k, v in enumerate(verdicts, 1):
            if v["relevant"]:
                relevant_count += 1
                precision_sum += relevant_count / k

        total_relevant = max(len(relevant_product_ids), 1)
        score = round(precision_sum / total_relevant, 4)

        return {
            "score": score,
            "verdicts": verdicts,
            "is_llm_judged": False,
            "latency_ms": 0,
        }

    # LLM 路径: 无标注时用 LLM 判断
    gw = gateway or get_model_gateway()
    context = _build_context_text(candidates, max_products=top_k)

    prompt = build_context_precision_user(query, context)

    t0 = time.perf_counter()
    try:
        raw = await gw.chat("chat_generation", prompt, CONTEXT_PRECISION_SYSTEM)
        result = _parse_json(raw)
        latency = int((time.perf_counter() - t0) * 1000)

        verdicts = result.get("verdicts", [])
        if not verdicts:
            return {"score": 0.0, "verdicts": [], "is_llm_judged": True, "latency_ms": latency}

        # AP 计算 (rank-aware)
        relevant_count = 0
        precision_sum = 0.0
        for k, v in enumerate(verdicts[:top_k], 1):
            if v.get("relevant"):
                relevant_count += 1
                precision_sum += relevant_count / k

        total_relevant = max(sum(1 for v in verdicts if v.get("relevant")), 1)
        score = round(precision_sum / total_relevant, 4)

        return {
            "score": score,
            "verdicts": verdicts,
            "is_llm_judged": True,
            "latency_ms": latency,
        }
    except Exception as e:
        logger.error(f"Context Precision计算失败: {e}")
        return {"score": 0.0, "verdicts": [], "is_llm_judged": True, "latency_ms": 0}


async def compute_context_recall(
    key_info_points: list[str],
    retrieved_products: list[dict],
    gateway=None,
) -> dict:
    """计算 Context Recall (上下文召回率)。

    检查 key_info_points 中有多少能在检索上下文中找到。

    Returns:
        {score: float, checks: list, summary: str, latency_ms: int}
    """
    if not key_info_points:
        return {"score": 1.0, "checks": [], "summary": "无关键信息点标注", "latency_ms": 0}

    if not retrieved_products:
        return {"score": 0.0, "checks": [], "summary": "无检索上下文", "latency_ms": 0}

    gw = gateway or get_model_gateway()
    context = _build_context_text(retrieved_products)

    info_list = "\n".join(f"- {p}" for p in key_info_points)

    prompt = build_context_recall_user(info_list, context)

    t0 = time.perf_counter()
    try:
        raw = await gw.chat("chat_generation", prompt, CONTEXT_RECALL_SYSTEM)
        result = _parse_json(raw)
        latency = int((time.perf_counter() - t0) * 1000)

        checks = result.get("checks", [])
        if checks:
            covered = sum(1 for c in checks if c.get("covered"))
            score = round(covered / len(checks), 4)
        else:
            score = 0.0

        return {
            "score": score,
            "checks": checks,
            "summary": result.get("recall_analysis", ""),
            "latency_ms": latency,
        }
    except Exception as e:
        logger.error(f"Context Recall计算失败: {e}")
        # 降级: 用文本子串匹配做简单检测
        context_lower = context.lower()
        covered = 0
        checks = []
        for point in key_info_points:
            keywords = [c for c in point if len(c) >= 2]
            hits = sum(1 for kw in keywords if kw in context_lower)
            is_covered = hits >= 2
            if is_covered:
                covered += 1
            checks.append({"info_point": point, "covered": is_covered, "evidence_fragment": "(降级关键词匹配)"})

        score = round(covered / len(key_info_points), 4) if key_info_points else 0.0
        return {
            "score": score,
            "checks": checks,
            "summary": f"降级关键词匹配: {covered}/{len(key_info_points)}",
            "latency_ms": 0,
        }


# ── Unified Evaluation ──────────────────────────────────────────

async def evaluate_one(
    query_data: dict,
    state_or_products: Any,
    answer: str = "",
    gateway=None,
) -> dict:
    """对单条 query 计算全部6个指标 (3检索 + 3生成)。

    Args:
        query_data: 含 user_query/key_info_points/relevant_product_ids/relevance_grades
        state_or_products: WorkflowState 或 检索结果列表
        answer: 生成的回答文本
        gateway: 复用的ModelGateway

    Returns:
        {query_id, user_query, faithfulness, context_precision, context_recall,
         recall_at_5, recall_at_10, mrr, ndcg_at_10, ...}
    """
    from app.schemas.workflow import WorkflowState

    if isinstance(state_or_products, WorkflowState):
        state = state_or_products
        retrieved = state.retrieved_products
        answer = state.answer or answer
    elif isinstance(state_or_products, list):
        retrieved = state_or_products
    else:
        retrieved = []

    query_id = query_data.get("query_id", "")
    user_query = query_data.get("user_query", "")
    key_info_points = query_data.get("key_info_points", [])
    relevant_product_ids = query_data.get("relevant_product_ids", [])
    relevance_grades = query_data.get("relevance_grades", {})

    gw = gateway or get_model_gateway()

    # 同步: 检索指标
    retrieved_ids = [p.get("product_id", "") for p in (retrieved or [])]
    retrieval_metrics = compute_retrieval_metrics(
        retrieved_ids,
        set(relevant_product_ids),
        relevance_grades,
    )

    # 异步: 生成指标 (3个并行)
    faith_task = compute_faithfulness(answer, retrieved, gw)
    precision_task = compute_context_precision(user_query, retrieved, relevant_product_ids, gw)
    recall_task = compute_context_recall(key_info_points, retrieved, gw)

    faith, precision, recall = await faith_task, await precision_task, await recall_task

    return {
        "query_id": query_id,
        "user_query": user_query,
        "answer_preview": answer[:200] if answer else "(无回答)",
        "retrieved_count": len(retrieved),
        # 检索指标
        "recall_at_5": retrieval_metrics["recall_at_5"],
        "recall_at_10": retrieval_metrics["recall_at_10"],
        "mrr": retrieval_metrics["mrr"],
        "ndcg_at_10": retrieval_metrics["ndcg_at_10"],
        # 生成指标
        "faithfulness": faith["score"],
        "faithfulness_detail": faith,
        "context_precision": precision["score"],
        "context_precision_detail": precision,
        "context_recall": recall["score"],
        "context_recall_detail": recall,
    }
