"""max 档 invoke_llm —— Plan-Execute 推理轮。

对齐 amap ``max/nodes/reasoning.py``：计划显式化，todo 状态放
``state.deliberation``（对应 amap 的 ``DeliberationState``）。

与 standard 档的差异只在本文件与 ``completion.py`` 两处，其余节点与拓扑完全共享。

为什么值得做：改造前 ``deep_think`` 只是把轮次预算从 3 抬到 8，多步强依赖任务
（"帮我配一套通勤穿搭并加购"）LLM 容易在中途丢掉后半段目标。计划显式化让每轮都能
对照 todo，且进度可通过 trace_steps 外显给用户。
"""

from __future__ import annotations

import json
import logging
import time

from app.schemas.workflow import WorkflowState
from app.workflow.react.common import trace
from app.workflow.react.standard.reasoning import (
    backfill_assistant_message,
    call_signature,
)

logger = logging.getLogger(__name__)

__all__ = ["invoke_llm", "progress_hint"]

_PLAN_SYSTEM = (
    "你是电商导购助手的任务规划器。把用户请求拆成最多 5 个可执行步骤，"
    "每步必须是能靠调用工具（检索商品/查购物车/查订单/记录偏好等）推进的具体动作。\n"
    "只输出 JSON 数组，不要任何解释：\n"
    '[{"id": "t1", "desc": "检索通勤风格上衣"}, {"id": "t2", "desc": "检索搭配的下装"}]\n'
    "怎么拆：\n"
    "- 有几个**独立的检索/查询目标**就拆几步（搭配成套=每件单品一步；对比 A 和 B=各一步）；\n"
    "- 单一目标的请求就给 1 步，不要为了凑数硬拆；\n"
    "- 不要把'整理结论''回答用户'当成一步 —— 那是计划跑完后自动做的；\n"
    "- 也不要把'展示商品卡'当成一步 —— 那是检索完顺手调 shopping.display 的事。"
)


def _parse_todos(raw: str) -> list[dict]:
    """解析计划 JSON（兼容 markdown 围栏，同 router_agent._parse_qu_json 的处理）。

    解析失败返回空列表 —— 调用方据此退化为 standard 语义，不阻断对话。
    """
    raw = (raw or "").strip()
    if "```" in raw:
        try:
            block = raw.split("```")[1]
            if block.startswith("json"):
                block = block[4:]
            raw = block.strip()
        except IndexError:
            return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    todos = []
    for i, item in enumerate(data[:5], 1):
        if isinstance(item, dict) and item.get("desc"):
            todos.append({"id": str(item.get("id") or f"t{i}"),
                          "desc": str(item["desc"])[:120], "done": False})
    return todos


async def _make_plan(state: WorkflowState) -> list[dict]:
    """让 LLM 产出 todo 列表。异常或解析失败返回空列表。"""
    from app.model_gateway.gateway import get_model_gateway

    try:
        raw = await get_model_gateway().chat(
            "tool_calling", state.user_query, system=_PLAN_SYSTEM)
    except Exception:  # noqa: BLE001 — 规划失败退化为 standard 语义，不阻断
        logger.warning("plan generation failed", exc_info=True)
        return []
    return _parse_todos(raw)


def progress_hint(state: WorkflowState) -> str:
    """当前 todo 进度，注入 system prompt 让 LLM 对照推进。"""
    todos = state.deliberation.todos
    if not todos:
        return ""
    lines = [f"{'[x]' if t.get('done') else '[ ]'} {t['id']} {t['desc']}" for t in todos]
    return ("\n\n[当前任务计划]\n" + "\n".join(lines)
            + "\n请推进第一个仍缺少关键事实的事项。已有候选商品、价格和依据即可交付时，"
              "不要机械完成剩余待办；直接给出最终回答，不要再调工具。")


async def invoke_llm(state: WorkflowState) -> WorkflowState:
    """首轮先产 todo 计划，之后每轮带进度推进。

    产计划不额外消耗一轮预算 —— 计划产出后在同一次节点执行内继续发起工具调用。
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
    if not state.deliberation.is_active() and state.round_no == 1:
        todos = await _make_plan(state)
        if todos:
            state.deliberation.todos = todos
            state.deliberation.plan_status = "in_progress"
            trace(state, "plan", "；".join(t["desc"] for t in todos),
                  latency_ms=round((time.perf_counter() - t0) * 1000))

    registry = get_tool_registry()
    system = build_omni_agent_prompt(deep_think=True) + progress_hint(state)

    t1 = time.perf_counter()
    choice = await get_model_gateway().chat_with_tools(
        "tool_calling", state.messages, registry.openai_schemas(llm_only=True),
        system=system)
    elapsed = round((time.perf_counter() - t1) * 1000)
    calls = (choice or {}).get("tool_calls") or []
    content = (choice or {}).get("content") or ""

    if not calls:
        state.answer_draft = content
        state.response_route = "completion"
        # LLM 不再调工具即视为计划走完，避免 check_completion 因残留未完成项空转
        if state.deliberation.is_active():
            for todo in state.deliberation.todos:
                todo["done"] = True
            state.deliberation.plan_status = "done"
        trace(state, "conclude", content[:80] or "(no content)", latency_ms=elapsed)
        return state

    sig = call_signature(calls)
    if sig in state.call_signatures:
        logger.warning("repeated tool calls, force stop at round %s", state.round_no)
        state.transition = "finalize"
        state.response_route = "completion"
        trace(state, "force_stop", "repeated tool calls", latency_ms=elapsed, status="failed")
        return state
    state.call_signatures.append(sig)

    backfill_assistant_message(state, calls, content)
    state.pending_tool_calls = calls
    state.response_route = "tool_use"
    trace(state, "invoke_llm", "调用 " + ", ".join(c.get("name", "") for c in calls),
          latency_ms=elapsed)
    return state
