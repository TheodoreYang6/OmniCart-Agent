"""OmniAgent —— 薄壳适配器（Phase 7 的手写 ReAct 循环已退役）。

编排逻辑已全部迁入 ``app.workflow.react`` 的双档同构图（standard / max，
移植 amap chat_agent 的编排结构）。本模块只剩一件事：把图的状态流翻译成
调用方原有的事件流，让既有调用方（评测脚本、集成测试）不必改写。

**与退役前的行为差异（刻意的）**：图内不做逐 token 流式（设计决定"图内不流，
SSE 层流"），所以不再产 ``token`` 事件；终稿由 ``finalize`` 落在
``state.answer`` 上，本壳以单个 ``answer`` 事件外显。SSE 层
（``api/agent_stream.py``）不走本壳，它直接驱动图并自己做流式，
所以用户侧的逐字输出不受影响。
"""

from __future__ import annotations

import logging

from app.framework.tools.protocols import ToolContext
from app.schemas.workflow import WorkflowState

logger = logging.getLogger(__name__)

__all__ = ["OmniAgent"]


class OmniAgent:
    """ReAct 薄壳：msg + ctx -> 事件流（status / tool_result / answer / done）。"""

    async def run_events(self, msg: str, ctx: ToolContext, deep_think: bool = False):
        """驱动 ReAct 图，把 trace_steps 增量翻译成事件。

        ``deep_think`` 决定档位：max（Plan-Execute，先产 todo）vs standard（纯 ReAct）。
        事件从 ``state.trace_steps`` 增量派生 —— 图节点返回 state patch，没有向外
        逐条推事件的通道，而 trace 本就按步记录了"做了什么"，拿它当事件源即可，
        不必为此新建一层事件总线。
        """
        from app.workflow.react import get_react_workflow, run_config
        from app.workflow.react.common import TOOL_CN, status_text

        mode = "max" if deep_think else "standard"
        state = getattr(ctx, "state", None)
        if not isinstance(state, WorkflowState):
            state = WorkflowState(user_id=ctx.user_id, session_id=ctx.session_id,
                                  conversation_id=ctx.conversation_id, user_query=msg)
        state.user_query = state.user_query or msg
        state.mode = mode

        seen = 0
        latest = state
        async for chunk in get_react_workflow(mode).astream(state, config=run_config(mode)):
            for node_out in chunk.values():
                if not isinstance(node_out, dict):
                    continue
                latest = WorkflowState(**node_out)
                for step in (latest.trace_steps or [])[seen:]:
                    action = step.get("action", "")
                    if action in TOOL_CN:
                        # 工具步同时外显"正在做什么"与"做完了什么"，与退役前一致：
                        # 调用方（如 test_loop_actions_passthrough）依赖 tool_result
                        # 携带 actions 来恢复规格选择按钮。
                        yield {"type": "status", "round": latest.round_no,
                               "tool": action, "text": status_text(action)}
                        yield {"type": "tool_result", "round": latest.round_no,
                               "tool": action, "ok": step.get("status") == "success",
                               "summary": (step.get("output_summary") or "")[:120],
                               "actions": list(latest.tool_actions or [])}
                    elif (text := status_text(action)):
                        yield {"type": "status", "round": latest.round_no,
                               "tool": "", "text": text}
                seen = len(latest.trace_steps or [])

        # 回写到调用方持有的 state（图内跑的是副本，调用方靠原对象读结果）
        if state is not latest:
            for field in type(latest).model_fields:
                setattr(state, field, getattr(latest, field))

        # draft 是循环最后一轮的 LLM content —— 分析线索，**不是**终稿。
        # 终稿由调用方（SSE 层的 ResponseAgent.generate_stream）基于单一
        # AnswerContext 生成；这里的草案只保留给旧调用方兼容，不能作为终稿。
        draft = (latest.answer_draft or "").strip()
        if draft:
            yield {"type": "answer", "rounds": latest.round_no, "content": draft}
        yield {"type": "done", "rounds": latest.round_no, "content": draft}
