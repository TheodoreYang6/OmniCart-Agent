"""standard 档 check_completion —— 草案驱动收敛。

对齐 amap ``standard/nodes/completion.py``。
"""

from __future__ import annotations

from app.schemas.workflow import WorkflowState

__all__ = ["check_completion"]


async def check_completion(state: WorkflowState) -> WorkflowState:
    """standard 档的每条入口都是终止路径，所以无条件收尾。

    两条入口：
    - ``invoke_llm`` 本轮没发 tool_calls（``response_route == "completion"``）——
      LLM 不再调工具就是它认为信息够了，这**本身**就是终止信号；
    - ``execute_tools`` 在 ``transition == "finalize"``（预算耗尽 / 防循环）时转过来。

    不要写成“没有草稿就再来一轮”：那会在 LLM 返回空 content 且无工具时白烧整个
    轮次预算 —— 入参没变，再问一遍只会得到同样的空结果。草稿为空时终稿由 SSE 层
    的 ResponseAgent 基于 state 生成，这是既定的降级路径。
    """
    state.transition = "finalize"
    return state
