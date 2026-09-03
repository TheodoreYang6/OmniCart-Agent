"""ToolRegistry —— 在通用 :class:`ComponentRegistry` 上做工具语义封装。

职责：
- 按名注册/取（复用 ComponentRegistry），按 ``category`` 过滤；
- 导出 OpenAI function-calling ``tools`` schema（供 LLM 动态选工具）；
- 统一执行 ``invoke``：权限校验 → 弹性超时（复用 resilience）→ 追踪
  （写 ``ctx.tool_trace`` 并镜像到 ``state.skill_executions`` —— 遗留跨端契约字段名）
  → 可选 Artifact 落黑板。
"""

from __future__ import annotations

import logging
import time

from app.framework.registry import ComponentRegistry
from app.framework.tools.protocols import Tool, ToolContext, ToolResult

logger = logging.getLogger(__name__)

__all__ = ["ToolRegistry"]


class ToolRegistry(ComponentRegistry):
    """工具注册中心（``kind="tool"``）。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # P2-3 schema_overrides 运营位（对齐 amap AgentToolPackagesConfig.schema_overrides_path）：
        # 只覆盖 LLM 可见的 description/parameters，运行时参数校验仍走 ToolSpec ——
        # “给模型看的”与“代码执行的”分离，prompt 调优不动代码。
        self._schema_overrides: dict[str, dict] = {}

    def set_schema_overrides(self, overrides: dict[str, dict]) -> None:
        """注入覆盖表 {tool_name: {"description"?: str, "parameters"?: dict}}（装配时调）。"""
        unknown = [n for n in overrides if self.get_optional(n) is None]
        if unknown:
            logger.warning(f"schema_overrides 引用未注册工具（忽略）: {unknown}")
        self._schema_overrides = {n: v for n, v in overrides.items() if n not in unknown}

    def by_category(self, category: str) -> list[Tool]:
        return [t for t in self.get_all() if getattr(t, "spec", None) and t.spec.category == category]

    def openai_schemas(self, names: list[str] | None = None, llm_only: bool = False) -> list[dict]:
        """导出为 OpenAI function-calling ``tools`` schema。

        ``llm_only=True``：只导出可由 LLM 直选的工具 —— 过滤 ``llm_exposed=False``
        与 ``permission=="order"``（需确认流的动作不给 LLM 直接触发）。
        """
        tools = [self.get(n) for n in names] if names else self.get_all()
        if llm_only:
            tools = [t for t in tools if t.spec.llm_exposed and t.spec.permission != "order"]
        schemas = []
        for t in tools:
            ov = self._schema_overrides.get(t.spec.name, {})
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": t.spec.name,
                        "description": ov.get("description", t.spec.description),
                        "parameters": ov.get("parameters") or t.spec.parameters or {"type": "object", "properties": {}},
                    },
                }
            )
        return schemas

    async def invoke(self, name: str, args: dict, ctx: ToolContext) -> ToolResult:
        """统一执行入口：权限 → 弹性超时 → 追踪 → 黑板。"""
        tool = self.get_optional(name)
        if tool is None:
            return ToolResult(ok=False, error=f"unknown_tool:{name}")

        # 权限：order 级需显式确认（下单确认预留；本阶段无 order 工具上线）
        if tool.spec.permission == "order" and not (args or {}).get("_confirmed"):
            return ToolResult(ok=False, error="confirmation_required")

        # 剥离控制键（以 _ 开头），避免作为业务参数传入 run
        call_args = {k: v for k, v in (args or {}).items() if not k.startswith("_")}

        t0 = time.perf_counter()
        try:
            from app.model_gateway.resilience import call_with_timeout

            res = await call_with_timeout(tool.run(ctx, **call_args), tool.spec.timeout_ms / 1000)
        except Exception as e:  # noqa: BLE001
            res = ToolResult(ok=False, error=str(e))

        self._record_trace(ctx, name, tool, call_args, res, t0)

        if ctx.blackboard is not None and res.artifacts:
            for a in res.artifacts:
                try:
                    await ctx.blackboard.put(a)
                except Exception:  # noqa: BLE001
                    logger.debug("blackboard put skipped")
        return res

    @staticmethod
    def _record_trace(ctx, name, tool, call_args, res, t0) -> None:
        """写工具执行记录到 ctx.tool_trace，并镜像到 state.skill_executions（遗留契约字段名）。"""
        from app.schemas.workflow import ToolExecution

        rec = ToolExecution(
            skill_name=name,
            category=tool.spec.category,
            args=call_args,
            status="success" if res.ok else "failed",
            latency_ms=round((time.perf_counter() - t0) * 1000),
            result_summary=(res.message or res.error or "")[:100],
        ).model_dump()
        ctx.tool_trace.append(rec)
        state = getattr(ctx, "state", None)
        # skill_executions 为遗留跨端契约字段名（Android SkillExecutionPanel / recommend 消费），保持不变
        if state is not None and hasattr(state, "skill_executions"):
            state.skill_executions.append(rec)
