"""OmniAgent —— ReAct 单主循环（Claude Code 式，Phase 7 阶段一）。

`while 轮次预算: chat_with_tools(messages, 工具箱) -> 执行 tool_calls -> role=tool 回填 -> 继续`

- LLM 自主决定查不查商品、查什么、查几次（深度检索 shopping.search 只是工具箱一员）；
- Loop 只做信息收集与动作执行，不产终稿——最终回答由 SSE 层
  `ResponseAgent.generate_stream(state)` 真流式生成（工具结果经 state 与 context_prompt 传递）；
- 护栏：轮次预算（普通/deep_think）、llm_exposed 白名单、permission=order 的
  `_confirmed` 拦截（LLM 收到 confirmation_required 回填后引导用户确认）、
  重复调用防循环、单工具异常回填错误继续。
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.framework.tools.protocols import ToolContext

logger = logging.getLogger(__name__)

__all__ = ["OmniAgent"]

# 工具中文名（status 事件外显"思考-行动"）
_TOOL_CN = {
    "shopping.search": "深度检索商品",
    "shopping.detail": "查看商品详情",
    "shopping.compare": "对比商品",
    "shopping.check_inventory": "查询库存",
    "cart.view": "查看购物车",
    "cart.add": "加入购物车",
    "cart.remove": "移除购物车商品",
    "cart.update_qty": "修改数量",
    "cart.clear": "清空购物车",
    "order.list": "查询订单",
    "order.detail": "查看订单详情",
    "order.track": "查询物流",
    "order.preview": "生成订单预览",
    "preference.save": "记录偏好",
    "preference.list": "查看偏好",
    "preference.delete": "删除偏好",
    "conversation.history": "回顾对话",
    "conversation.reset": "重置上下文",
}


class OmniAgent:
    """ReAct 主循环：msg + ctx -> 事件流（status/tool_result/done）。"""

    async def run_events(self, msg: str, ctx: ToolContext, deep_think: bool = False):
        from app.core.config import AGENT_LOOP_DEEP_ROUNDS, AGENT_LOOP_MAX_ROUNDS
        from app.model_gateway.gateway import get_model_gateway
        from app.providers.tools import get_tool_registry
        from app.prompts.agent_prompts import build_omni_agent_prompt

        registry = get_tool_registry()
        schemas = registry.openai_schemas(llm_only=True)
        max_rounds = AGENT_LOOP_DEEP_ROUNDS if deep_think else AGENT_LOOP_MAX_ROUNDS
        system = build_omni_agent_prompt(deep_think=deep_think)

        context_summary = await self._context_summary(ctx)
        first_user = f"{context_summary}\n\n[用户消息]\n{msg}" if context_summary else msg

        # QU V2：结构化意图理解注入（与 workflow 同缓存 key，同 query 零成本），
        # LLM 不必每次自己悟拆分；QU 异常静默跳过（Loop 自主性兜底）
        try:
            from app.agents.router_agent import aunderstand_query

            qu = await aunderstand_query(msg) or {}
            intent = qu.get("intent") or ""
            if intent and intent != "chitchat":
                parts = [f"intent={intent}"]
                roles = [str(s.get("role") or s.get("query") or "")
                         for s in (qu.get("sub_queries") or []) if isinstance(s, dict)]
                roles = [r for r in roles if r]
                if roles:
                    parts.append("子目标：" + "/".join(roles) + "（分别检索后逐组说明）")
                first_user = "[意图理解] " + "；".join(parts) + "\n" + first_user
        except Exception:  # noqa: BLE001
            pass

        messages: list[dict] = [{"role": "user", "content": first_user}]

        state = getattr(ctx, "state", None)
        prev_calls: set[str] = set()
        gateway = get_model_gateway()

        for round_no in range(1, max_rounds + 1):
            # 收口轮（spec D2，对齐 amap check_completion 显式收口）：预算最后一轮
            # 不再给工具，改用 chat_stream 真流式产终稿（逐 token 直推 SSE）
            if round_no == max_rounds:
                async for ev in self._conclude_stream(gateway, messages, state, round_no):
                    yield ev
                return

            choice = await gateway.chat_with_tools("tool_calling", messages, schemas, system=system)
            calls = (choice or {}).get("tool_calls") or []
            content = (choice or {}).get("content") or ""

            if not calls:
                # 自然结束：content 即终稿（spec D2 终稿权在 Loop，不再经 ResponseAgent 统稿）；
                # 同时写 context_prompt 供降级统稿路径（answer 空时）保持一致
                if state is not None and content:
                    state.answer = content
                    state.context_prompt = (state.context_prompt or "") + \
                        f"\n[欧米的分析结论（基于工具调用结果，回答须与之一致）]\n{content[:600]}"
                self._trace(state, round_no, "conclude", content[:80] or "(no content)")
                yield {"type": "answer", "rounds": round_no, "content": content}
                yield {"type": "done", "rounds": round_no, "content": content}
                return

            # 防循环：本轮调用签名与上一轮完全重复 -> 强制结束
            sig = json.dumps([[c.get("name"), c.get("args")] for c in calls],
                             ensure_ascii=False, sort_keys=True)
            if sig in prev_calls:
                logger.warning("OmniAgent repeated tool calls, force stop")
                self._trace(state, round_no, "force_stop", "repeated tool calls")
                yield {"type": "done", "rounds": round_no, "content": content}
                return
            prev_calls.add(sig)

            # assistant 侧回填原 tool_calls（OpenAI 协议）
            messages.append({
                "role": "assistant",
                "content": content or None,
                "tool_calls": [{
                    "id": c.get("id") or f"call_{round_no}_{i}",
                    "type": "function",
                    "function": {"name": c.get("name", ""),
                                 "arguments": json.dumps(c.get("args") or {}, ensure_ascii=False)},
                } for i, c in enumerate(calls)],
            })

            # 同轮多工具：全为只读（permission=read）时并行执行（对比场景 LLM 常一轮发
            # 多个 shopping.search，串行是 multi_step 25.6s 的主因）；含写操作则保持串行，
            # 避免购物车/订单类状态变更的顺序不确定。
            def _is_read(c) -> bool:
                t = registry.get_optional(c.get("name", ""))
                return t is not None and getattr(t.spec, "permission", "") == "read"

            if len(calls) > 1 and all(_is_read(c) for c in calls):
                for c in calls:
                    cn = _TOOL_CN.get(c.get("name", ""), c.get("name", ""))
                    yield {"type": "status", "round": round_no, "tool": c.get("name", ""),
                           "text": f"欧米正在{cn}…"}
                results = await asyncio.gather(
                    *(registry.invoke(c.get("name", ""), c.get("args") or {}, ctx) for c in calls),
                    return_exceptions=True)
                for i, (c, res) in enumerate(zip(calls, results, strict=True)):
                    if isinstance(res, Exception):  # 单工具异常回填错误继续
                        from app.framework.tools.protocols import ToolResult as _TR

                        res = _TR(ok=False, error=str(res)[:200])
                    summary = self._summarize(res)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": c.get("id") or f"call_{round_no}_{i}",
                        "content": summary,
                    })
                    self._trace(state, round_no, c.get("name", ""), summary[:80])
                    yield {"type": "tool_result", "round": round_no, "tool": c.get("name", ""),
                           "ok": res.ok, "summary": summary[:120],
                           "actions": list(getattr(res, "actions", None) or [])}
            else:
                for i, c in enumerate(calls):
                    name = c.get("name", "")
                    args = c.get("args") or {}
                    cn = _TOOL_CN.get(name, name)
                    yield {"type": "status", "round": round_no, "tool": name,
                           "text": f"欧米正在{cn}…"}
                    res = await registry.invoke(name, args, ctx)
                    summary = self._summarize(res)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": c.get("id") or f"call_{round_no}_{i}",
                        "content": summary,
                    })
                    self._trace(state, round_no, name, summary[:80])
                    yield {"type": "tool_result", "round": round_no, "tool": name,
                           "ok": res.ok, "summary": summary[:120],
                           "actions": list(getattr(res, "actions", None) or [])}

            await self._publish_round(round_no, [c.get("name") for c in calls])

        # 预算耗尽（理论上不可达：收口轮已在循环内 return）：兼容兜底
        logger.info(f"OmniAgent budget exhausted after {max_rounds} rounds")
        self._trace(state, max_rounds, "budget_exhausted", f"{max_rounds} rounds")
        yield {"type": "done", "rounds": max_rounds, "content": ""}

    async def _conclude_stream(self, gateway, messages: list[dict], state, round_no: int):
        """收口轮：messages 转写 transcript prompt，chat_stream 逐 token 产终稿。

        gateway.chat_stream 仅收单 prompt，故把工具交互记录（每条已限 600 字）
        序列化为上下文；完整商品数据已在 state 旁路，不依赖文本通道。"""
        transcript = []
        for m in messages:
            role = m.get("role", "")
            if role == "tool":
                transcript.append(f"[工具结果] {m.get('content', '')}")
            elif role == "assistant" and m.get("tool_calls"):
                names = [tc["function"]["name"] for tc in m["tool_calls"]]
                transcript.append(f"[已调用工具] {', '.join(names)}")
            elif role == "user":
                transcript.append(f"[用户] {m.get('content', '')}")
        prompt = ("\n".join(transcript)
                  + "\n\n[收口] 工具预算已用尽。请基于以上工具结果，直接给出最终回答："
                    "自然口语、引用具体商品与参数、不要提及工具调用过程。")
        yield {"type": "status", "round": round_no, "tool": "",
               "text": "欧米正在整理结论…"}
        full = ""
        try:
            async for tok in gateway.chat_stream("chat_generation", prompt):
                full += tok
                yield {"type": "token", "text": tok}
        except Exception as e:  # noqa: BLE001 — 流式失败交给 SSE 层降级统稿
            logger.warning(f"conclude stream failed: {e}")
        if state is not None and full.strip():
            state.answer = full.strip()
        self._trace(state, round_no, "conclude_stream", (full or "(stream failed)")[:80])
        yield {"type": "done", "rounds": round_no, "content": full}

    # ================================================================
    # helpers
    # ================================================================

    @staticmethod
    def _summarize(res) -> str:
        """工具结果 -> 回填文本（≤600 字；完整数据已写回 state，不依赖文本通道）。"""
        if not res.ok:
            err = res.error or res.message or "unknown_error"
            if err == "confirmation_required":
                return "该操作需要用户本人确认后才能执行，请向用户展示待确认内容并请其确认。"
            return f"[工具失败] {(res.message or err)[:200]}"
        parts = []
        if res.message:
            parts.append(res.message)
        if res.data:
            try:
                parts.append(json.dumps(res.data, ensure_ascii=False, default=str)[:300])
            except Exception:  # noqa: BLE001
                pass
        return ("\n".join(parts) or "(空结果)")[:600]

    @staticmethod
    async def _context_summary(ctx: ToolContext) -> str:
        """会话上下文摘要（recent_turns / last_products / last_orders）。"""
        if not ctx.conversation_id:
            return ""
        try:
            from app.services.conversation_service import get_conversation_service

            snap = await get_conversation_service().get_context_snapshot(ctx.conversation_id) or {}
        except Exception:  # noqa: BLE001
            return ""
        lines = []
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

    @staticmethod
    def _trace(state, round_no: int, action: str, summary: str) -> None:
        if state is None:
            return
        state.trace_steps.append({
            "step_id": f"T{len(state.trace_steps) + 1:03d}",
            "agent_name": f"OmniAgent (round {round_no})",
            "action": action,
            "input_summary": "",
            "output_summary": summary,
            "latency_ms": 0,
            "status": "success",
        })

    @staticmethod
    async def _publish_round(round_no: int, tools: list) -> None:
        try:
            from app.framework.blackboard import current_board

            bb = current_board()
            if bb is not None:
                await bb.publish("agent_loop.round", {"round": round_no, "tools": tools},
                                 producer="omni_agent")
        except Exception:  # noqa: BLE001
            pass
