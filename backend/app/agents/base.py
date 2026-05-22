"""V1 BaseAgent — 所有 Agent 的抽象基类。

每个 Agent 实现:
- card: AgentCard 身份描述
- execute(): 核心执行逻辑，接收 WorkflowState，返回更新后的 WorkflowState
- _record_trace(): 记录执行步骤到 trace_steps
"""

import time
from abc import ABC, abstractmethod

from app.schemas.a2a import AgentCard
from app.schemas.workflow import WorkflowState


class BaseAgent(ABC):
    """Agent 基类 — 所有 Agent 必须继承"""

    def __init__(self):
        self._card: AgentCard | None = None

    @property
    def card(self) -> AgentCard:
        if self._card is None:
            self._card = self._build_card()
        return self._card

    @abstractmethod
    def _build_card(self) -> AgentCard:
        """子类定义 Agent 身份卡片"""
        ...

    @abstractmethod
    def execute(self, state: WorkflowState) -> WorkflowState:
        """子类实现核心逻辑，接收状态并返回更新后的状态"""
        ...

    def _start_trace(self, state: WorkflowState, action: str, input_summary: str) -> float:
        """记录 trace 开始，返回开始时间"""
        self._t0 = time.perf_counter()
        self._current_action = action
        self._current_input = input_summary
        return self._t0

    def _finish_trace(self, state: WorkflowState, output_summary: str, status: str = "success") -> WorkflowState:
        """记录 trace 结束，追加 trace_step"""
        elapsed = round((time.perf_counter() - self._t0) * 1000)
        step_num = len(state.trace_steps) + 1

        state.trace_steps.append({
            "step_id": f"T{step_num:03d}",
            "agent_name": self.card.name,
            "action": self._current_action,
            "input_summary": self._current_input[:120],
            "output_summary": output_summary[:200],
            "latency_ms": elapsed,
            "status": status,
        })
        return state

    def _error_trace(self, state: WorkflowState, error: str) -> WorkflowState:
        """异常时记录 trace"""
        return self._finish_trace(state, f"Error: {error[:150]}", status="failed")
