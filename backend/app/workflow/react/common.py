"""ReAct 节点共享工具：trace 写入、工具结果摘要、工具中文名、ToolContext 构造。

从 ``agents/omni_agent.py`` 迁入。放在共享模块而非某个节点里，因为 prepare /
execute_tools / invoke_llm 三处都要用。
"""

from __future__ import annotations

import json

from app.framework.tools.protocols import ToolContext
from app.schemas.workflow import WorkflowState

__all__ = ["TOOL_CN", "build_tool_ctx", "status_text", "summarize_result", "trace"]

# 工具中文名（status 事件外显"思考-行动"）。迁自 omni_agent._TOOL_CN。
TOOL_CN = {
    "shopping.search": "深度检索商品",
    "shopping.detail": "查看商品详情",
    "shopping.product_dossier": "深入核对这件商品的信息",
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


def trace(state: WorkflowState, action: str, summary: str, *,
          latency_ms: int = 0, status: str = "success") -> None:
    """写一条 trace_steps。

    与 ``ToolRegistry._record_trace`` 是互补的两个通道，不重复：
    那个写 ``ctx.tool_trace`` + ``state.skill_executions``（Android
    SkillExecutionPanel 消费的遗留契约），这个写 ``state.trace_steps``
    （深度思考轨迹面板）。

    ``latency_ms`` 必须由调用方实测传入 —— 原 ``omni_agent._trace`` 把它硬编码成
    0，导致轨迹面板每一步耗时都显示 0。
    """
    state.trace_steps.append({
        "step_id": f"T{len(state.trace_steps) + 1:03d}",
        "agent_name": f"OmniAgent (round {state.round_no})",
        "action": action,
        "input_summary": "",
        "output_summary": summary,
        "latency_ms": latency_ms,
        "status": status,
    })


def summarize_result(res) -> str:
    """工具结果 -> role=tool 回填文本（<=600 字）。

    完整商品数据已由工具写回 state（见 ``providers/tools/shopping.py`` 把
    retrieved_products/evidence_list/decision_results 合并进父 state），
    文本通道只承担"让 LLM 知道发生了什么"，故可安全截断。

    迁自 omni_agent._summarize，含 confirmation_required 的用户话术映射 ——
    ``ToolRegistry.invoke`` 对 permission=order 且无 ``_confirmed`` 的调用返回
    该错误码，这里把它翻成让 LLM 引导用户确认的自然语言。
    """
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


def status_text(action: str) -> str:
    """trace 的 action -> 面向用户的 status 文案。"""
    if action in TOOL_CN:
        return f"欧米正在{TOOL_CN[action]}…"
    if action == "chitchat":
        return "欧米在听～"
    if action == "plan":
        return "欧米正在拆解任务…"
    if action == "conclude":
        return "欧米正在整理结论…"
    return ""


def build_tool_ctx(state: WorkflowState) -> ToolContext:
    """从 state 构造 ToolContext。

    ``blackboard`` 必须从请求级 contextvar 取：``ToolRegistry.invoke`` 靠
    ``ctx.blackboard`` 把 ``ToolResult.artifacts``（A2A 协同产物）落到黑板上，
    不传就会被静默丢弃 —— SSE 层已经 ``set_current_board(Blackboard())`` 建好了板，
    这里不接就白建。取不到（单测、脚本直调）时为 None，invoke 会跳过落盘。
    """
    try:
        from app.framework.blackboard import current_board

        board = current_board()
    except Exception:  # noqa: BLE001 — 黑板不可用不影响工具执行
        board = None
    return ToolContext(
        user_id=state.user_id,
        session_id=state.session_id,
        conversation_id=state.conversation_id,
        args_raw=state.user_query,
        state=state,
        blackboard=board,
    )
