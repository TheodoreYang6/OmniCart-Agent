"""standard 档 invoke_llm —— 纯 ReAct 推理轮。

对齐 amap ``standard/nodes/reasoning.py``。max 档复用本模块的
``call_signature`` / ``backfill_assistant_message``（两档的协议回填与防循环
签名逻辑相同，差异只在计划驱动，见 ``max/reasoning.py``）。
"""

from __future__ import annotations

import json
import logging
import time

from app.schemas.workflow import WorkflowState
from app.workflow.react.common import trace

logger = logging.getLogger(__name__)

__all__ = ["backfill_assistant_message", "call_signature", "invoke_llm"]


def call_signature(calls: list[dict]) -> str:
    """本轮工具调用的规范化签名，用于防循环比对。

    ``sort_keys`` 保证参数顺序不影响签名 —— 同样的调用换个 key 顺序不该被当成
    新调用。
    """
    return json.dumps([[c.get("name"), c.get("args")] for c in calls],
                      ensure_ascii=False, sort_keys=True)


def backfill_assistant_message(state: WorkflowState, calls: list[dict], content: str) -> None:
    """按 OpenAI 协议把本轮 tool_calls 回填进 assistant 消息。

    迁自 omni_agent.py:124-133。``content or None`` 是刻意的：OpenAI 协议下
    带 tool_calls 的 assistant 消息 content 允许为 null，传空串有些网关会报错。
    """
    state.messages.append({
        "role": "assistant",
        "content": content or None,
        "tool_calls": [{
            "id": c.get("id") or f"call_{state.round_no}_{i}",
            "type": "function",
            "function": {
                "name": c.get("name", ""),
                "arguments": json.dumps(c.get("args") or {}, ensure_ascii=False),
            },
        } for i, c in enumerate(calls)],
    })


async def invoke_llm(state: WorkflowState) -> WorkflowState:
    """一轮 chat_with_tools。写 ``response_route`` 供路由函数读。

    迁自 omni_agent.py:97-133。三条出口：
    - 无 tool_calls -> content 即终稿草案，进 check_completion 收尾；
    - 调用签名与历史重复 -> 强制收尾（防循环，见下）；
    - 有新 tool_calls -> 进 execute_tools。
    """
    if state.intent == "chitchat" and not state.image_url:
        # 闲聊无需工具：置 completion 路由，图空转到 finalize，终稿交 ResponseAgent
        # 的闲聊分支（它有专门的 chitchat prompt）。不调 LLM 是刻意的 ——
        # 带着 18 个工具 schema 去问"你好"纯属浪费，还容易诱发无意义的检索。
        state.response_route = "completion"
        trace(state, "chitchat", "闲聊短路，跳过工具循环")
        return state

    from app.model_gateway.gateway import get_model_gateway
    from app.prompts.agent_prompts import build_omni_agent_prompt
    from app.providers.tools import get_tool_registry

    t0 = time.perf_counter()
    registry = get_tool_registry()
    choice = await get_model_gateway().chat_with_tools(
        "tool_calling", state.messages,
        registry.openai_schemas(llm_only=True),
        system=build_omni_agent_prompt(deep_think=state.mode == "max"),
    )
    elapsed = round((time.perf_counter() - t0) * 1000)
    calls = (choice or {}).get("tool_calls") or []
    content = (choice or {}).get("content") or ""

    if not calls:
        # 自然结束：LLM 认为信息够了，content 即终稿草案
        state.answer_draft = content
        state.response_route = "completion"
        trace(state, "conclude", content[:80] or "(no content)", latency_ms=elapsed)
        return state

    # 防循环：本轮调用签名与历史完全重复 -> 强制收尾。
    # LLM 偶尔会在拿到结果后仍重复同一组调用，不拦会一直烧到预算上限。
    sig = call_signature(calls)
    if sig in state.call_signatures:
        logger.warning("repeated tool calls, force stop at round %s", state.round_no)
        state.transition = "finalize"
        state.response_route = "completion"
        trace(state, "force_stop", "repeated tool calls", latency_ms=elapsed,
              status="failed")
        return state
    state.call_signatures.append(sig)

    backfill_assistant_message(state, calls, content)
    state.pending_tool_calls = calls
    state.response_route = "tool_use"
    trace(state, "invoke_llm", "调用 " + ", ".join(c.get("name", "") for c in calls),
          latency_ms=elapsed)
    return state
