"""Tool 框架核心契约 — ToolSpec / ToolContext / ToolResult / Tool。

对齐业界 function-calling 标准的 "tool" 概念：可执行、带 JSON Schema 参数、
可被 LLM 动态选择、可追踪。区别于 prompt-based skill（见 ``app.framework.skills``，
基于自然语言 prompt 模板/行为模式，另行实现）。执行统一经 :class:`ToolRegistry`
（弹性 + 权限 + trace）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import BaseModel, Field

from app.schemas.a2a import Artifact

__all__ = ["ToolSpec", "ToolContext", "ToolResult", "Tool"]


class ToolSpec(BaseModel):
    """工具身份 + 契约。``parameters`` 为 OpenAI function-calling 兼容 JSON Schema。"""

    name: str                       # 命名空间.动作，如 "cart.remove"
    description: str = ""
    parameters: dict = Field(default_factory=dict)
    category: str = ""              # shopping / cart / order / preference / conversation
    permission: str = "read"        # read（自动）/ write（自动+trace）/ order（需确认）
    timeout_ms: int = 8000
    llm_exposed: bool = True        # 是否暴露给 LLM 函数调用（强依赖会话上下文/确认流的工具置 False）


@dataclass
class ToolContext:
    """单次调用上下文 —— 运行时引用，不序列化，故用 dataclass。"""

    user_id: str = ""
    session_id: str = ""
    conversation_id: str = ""
    args_raw: str = ""              # 原始 query（供 ordinal 解析等）
    state: object | None = None     # WorkflowState | None（存在则镜像 trace）
    blackboard: object | None = None  # 未来接入，本阶段为 None
    tool_trace: list = field(default_factory=list)


class ToolResult(BaseModel):
    """工具执行结果。"""

    ok: bool = True
    data: dict = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)  # A2A 协同
    message: str = ""               # 面向用户文本（可空）
    actions: list[dict] = Field(default_factory=list)  # quick_reply/address_form/sku_option
    error: str = ""


class Tool(ABC):
    """工具基类 —— 所有工具必须继承并声明 ``spec`` + 实现 ``run``。"""

    spec: ToolSpec

    @property
    def name(self) -> str:
        """供 ComponentRegistry 按名注册（读 spec.name）。"""
        return self.spec.name

    def should_activate(self, ctx: "ToolContext", **kwargs) -> bool:
        return True

    @abstractmethod
    async def run(self, ctx: "ToolContext", **kwargs) -> "ToolResult": ...
