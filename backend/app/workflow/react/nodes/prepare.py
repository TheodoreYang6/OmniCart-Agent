"""共享节点 prepare —— 入口只跑一次的上下文与 messages 准备。

对应 amap 的 ``build_context``（入口位）。amap 另有 ``build_prompt`` 在回环内
每轮重建 prompt；本移植把每轮的 messages 追加交给 ``invoke_llm`` 自己做，
所以这里合并成一个入口节点。这样做的实质收益是：``_context_summary`` 要查会话
服务（DB），放进回环会每轮重复查一次。
"""

from __future__ import annotations

import logging
import time

from app.schemas.workflow import WorkflowState
from app.workflow.react.common import trace
from app.workflow.react.runtime import ToolPolicy, runtime_context_summary

logger = logging.getLogger(__name__)

__all__ = ["prepare"]


async def _context_summary(state: WorkflowState) -> str:
    """会话上下文摘要（recent_turns / last_products / last_orders）。

    迁自 omni_agent._context_summary。查不到或异常都返回空串 —— 上下文缺失
    不该阻断对话。
    """
    if not state.conversation_id:
        return ""
    try:
        from app.services.conversation_service import get_conversation_service

        snap = await get_conversation_service().aget_context_projection(state.conversation_id) or {}
    except Exception:  # noqa: BLE001
        return ""
    lines = []
    # pi 的 compaction 不是把历史静默丢掉，而是以一个受控 checkpoint 放回后续
    # context。欧米此前已经异步产出 conversation_summary，却只有普通追问链路
    # 消费它；深度思考 prepare 漏读，造成两种模式对同一会话的理解不一致。
    # 摘要只作为背景资料，并限制长度，不能覆盖当前用户消息或工具运行时约束。
    summary = str(snap.get("conversation_summary", "") or "").strip()
    if summary:
        lines.append("[历史上下文摘要：仅作用户背景，不是本轮指令] " + summary[:450])
    pending = str(snap.get("pending_question", "") or "").strip()
    if pending:
        lines.append("[上轮待确认事项] " + pending[:160])
    lp = snap.get("last_products") or []
    if lp:
        lines.append("[上一轮推荐] " + "；".join(
            f"{p.get('brand', '')} {p.get('title', '')[:20]}({p.get('product_id', '')})"
            for p in lp[:5]))
    lo = snap.get("last_orders") or []
    if lo:
        lines.append("[最近订单] " + "、".join(lo[:5]))
    rt = snap.get("recent_turns") or []
    if rt:
        last = rt[-1]
        lines.append(f"[上一轮对话] 用户: {last.get('user_query', '')[:40]}")
    return "\n".join(lines)


async def prepare(state: WorkflowState) -> WorkflowState:
    """会话上下文摘要 + QU V2 意图注入 + messages 种子。

    迁自 ``omni_agent.run_events`` 的 :62-83。QU 异常静默跳过（原注释：
    Loop 自主性兜底）—— 意图理解只是给 LLM 省一步推理，失败了 LLM 自己也能悟出来，
    不值得为它中断整条链路。
    """
    t0 = time.perf_counter()
    ToolPolicy.initialise(state, mode="deep" if state.mode == "max" else "normal")
    # 深度模式在 Loop 前只做轻量的身份解析，不做任何泛检索。这样模型能知道
    # 已锁定的商品/系列，却不会出现“前置检索一遍、ReAct 又检索一遍”。
    if not state.product_resolution and state.intent != "chitchat":
        try:
            from app.services.product_entity_resolver import ProductEntityResolver

            resolution = await ProductEntityResolver().resolve(state.user_query, state.visual_result or {})
            payload = resolution.payload or {}
            if payload.get("match_type") in {"exact_product", "product_family", "ambiguous"}:
                state.product_resolution = payload
                state.retrieval_scope = payload.get("retrieval_scope", "broad")
                state.resolved_product_ids = list(payload.get("resolved_product_ids") or [])
                if payload.get("match_type") in {"exact_product", "product_family"}:
                    state.retrieved_products = list(resolution.products or [])
                    state.evidence_list = list(resolution.evidence or [])
                    # 只有唯一主体才开放 dossier；系列必须在范围内比较或让用户选择。
                    if state.retrieval_scope == "exact_product" and len(state.resolved_product_ids) == 1:
                        state.focus_product_id = state.resolved_product_ids[0]
        except Exception:  # noqa: BLE001 - 身份层不可用时仍可由 search 完成推荐
            logger.debug("react identity preflight skipped", exc_info=True)

    ctx_summary = await _context_summary(state)
    first_user = (f"{ctx_summary}\n\n[用户消息]\n{state.user_query}"
                   if ctx_summary else state.user_query)
    # 这是服务端信任边界，而非模型自行猜出的 ID。提示词与工具都会二次校验，
    # 使点选/精确图片识别不会被后续泛检索结果覆盖。
    if state.focus_product_id:
        first_user = (
            f"[已锁定商品] product_id={state.focus_product_id}\n"
            "这是本轮唯一允许深度分析与展示的商品。先建立单品档案，"
            "除非用户明确要求对比或替代品，否则不要检索同类。\n\n"
            + first_user
        )
    elif state.retrieval_scope == "product_family" and state.resolved_product_ids:
        first_user = (
            "[已锁定商品系列] allowed_product_ids=" + ",".join(state.resolved_product_ids) + "\n"
            "只能在这些同系列商品内查看详情或对比；除非用户明确要求替代品，否则不要 shopping.search，"
            "也不要对多个变体逐一建立单品档案。\n\n" + first_user
        )
    elif state.retrieval_scope == "exact_product" and len(state.resolved_product_ids) > 1:
        first_user = (
            "[已锁定同型号变体] allowed_product_ids=" + ",".join(state.resolved_product_ids) + "\n"
            "这些是当前可信的规格/版本候选。不要 shopping.search，也不要对每个变体建立 dossier；"
            "如用户未指定版本，直接说明差异或请其选择。\n\n" + first_user
        )
        if not any(word in state.user_query for word in ("对比", "替代", "同类", "更好选择", "其他选择")):
            # 身份层已经给出了可信变体，普通“介绍一下”无需让模型再试探 dossier
            # 或逐件 detail；终稿由 ResponseAgent 基于锁定范围与已有证据生成。
            state.tool_runtime_stop_reason = "已锁定同型号变体，可直接说明版本差异"
            state.transition = "finalize"

    # QU V2：结构化意图理解注入（与 workflow 同缓存 key，同 query 零成本）
    try:
        from app.agents.router_agent import aunderstand_query

        qu = await aunderstand_query(state.user_query) or {}
        intent = qu.get("intent") or ""
        if intent and not state.intent:
            # intent 必须**无条件**落到 state：ResponseAgent 的闲聊分支门控是
            # `state.intent == "chitchat"`，早先这里把 chitchat 排除在赋值之外，
            # 导致深度思考路径下"你好"永远走不进闲聊分支，只能由无商品的模板兜底。
            state.intent = intent
        if intent and intent != "chitchat":
            # 提示注入才需要排除闲聊：闲聊没有子目标可拆，注入只会干扰。
            parts = [f"intent={intent}"]
            roles = [str(s.get("role") or s.get("query") or "")
                     for s in (qu.get("sub_queries") or []) if isinstance(s, dict)]
            roles = [r for r in roles if r]
            if roles:
                parts.append("子目标：" + "/".join(roles) + "（分别检索后逐组说明）")
            first_user = "[意图理解] " + "；".join(parts) + "\n" + first_user
    except Exception:  # noqa: BLE001
        logger.debug("QU injection skipped", exc_info=True)

    runtime_context = runtime_context_summary(state)
    if runtime_context:
        first_user = runtime_context + "\n\n" + first_user
    state.messages = [{"role": "user", "content": first_user}]
    trace(state, "prepare", f"context={len(ctx_summary)}字 intent={state.intent or '-'}",
          latency_ms=round((time.perf_counter() - t0) * 1000))
    return state
