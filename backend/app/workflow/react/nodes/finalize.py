"""共享节点 finalize —— 收敛，不产终稿。

设计决定："图内不流，SSE 层流"。图跑到这里仅收敛受控工具状态与草案，
不把工具交互记录或草案写进最终回答上下文；逐 token 真流式由 SSE 层的
``ResponseAgent.generate_stream(state)`` 负责。

为什么不在图里产终稿：LangGraph 节点返回 state patch，没有向 SSE 逐 token 推送的
自然通道。仓内已有的 ``get_workflow_no_response`` 就是同一个取舍（图跑到 decision
停、SSE 层流式生成），这里沿用，避免为了"节点内流式"新建一层事件总线。
"""

from __future__ import annotations

from app.schemas.workflow import WorkflowState
from app.workflow.react.common import trace

__all__ = ["finalize"]


async def finalize(state: WorkflowState) -> WorkflowState:
    """结束 Loop，不向最终回答上下文写入任何中间文本。

    ``answer_draft`` 是循环最后一轮 LLM 的 ``content``。它**不能**直接当终稿：
    ReAct 循环里这个字段是模型的 scratchpad（"让我回顾一下第一次检索的结果……
    不过我已经有了足够的信息"），OpenAI function-calling 协议里思考与终稿共用同一个
    ``content`` 字段，无法区分。直接采用会把过程独白推给用户。

    终稿统一由 SSE 层的 ``ResponseAgent.generate_stream(state)`` 生成。它只消费
    ConversationContextAssembler 构造的 AnswerContext，并且是逐 token 真流式。
    """
    trace(state, "finalize",
          f"rounds={state.round_no} draft={'有' if state.answer_draft else '无'} "
          f"tools={sum(1 for m in state.messages if m.get('role') == 'tool')}")
    return state
