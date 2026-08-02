"""前端网格展示的数量修整 —— 答文与卡片列表一致性的共享口径。

前端聊天内商品卡每行 3 个（sm:grid-cols-3）。末行只落单 1 个时（length % 3 == 1）
视觉最丑（用户实拍反馈：7 个排成 3/3/1"好丑"）；而末行 2 个（5→3/2、8→3/3/2）可接受。

本函数被两处共用，保证口径一致（否则会重现"回答讲了 4 款、卡片只列 3 款"）：
- context/compiler.py 与 response_agent._context_products：喂给 LLM 的候选集
- api/agent_stream.py SSE 出口：实际下发的 products

约定传入列表已按优先级（得分/引用序）降序，修整砍掉的是最低优先级项。
"""

from __future__ import annotations

__all__ = ["trim_for_grid", "GRID_COLS"]

GRID_COLS = 3  # 与前端 MessageBubble 的 sm:grid-cols-3 对齐


def trim_for_grid(items: list, cols: int = GRID_COLS) -> list:
    """末行只落单 1 个时砍掉最后一项：4→3、7→6、10→9；5/8 等末行 2 个保留。

    长度 ≤ cols 时不处理（1/2/3 个本就正常，砍了反而丢信息）。
    """
    if len(items) > cols and len(items) % cols == 1:
        return items[:-1]
    return list(items)
