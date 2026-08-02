#!/usr/bin/env python3
"""组件治理校验 —— 借鉴 amap 的 tools/agent 治理 CI 门禁。

校验各 ``builtin()`` 清单能被对应注册表干净装配（名称唯一、契约完整）：
- recall sources：名称唯一 + stage 合法 + 实现 search。
- memory providers / context providers / agents：名称唯一。

用法（仓库根）：
    PYTHONPATH=backend python scripts/check_governance.py

任一校验失败以非零码退出，可作为 CI 门禁（对齐 amap ``check-*-governance`` 系列）。
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _dups(names: list[str]) -> list[str]:
    return sorted({n for n in names if names.count(n) > 1})


def _check_recall(errors: list[str]) -> None:
    from app.framework.retrieval.source import STAGE_ENRICH, STAGE_FALLBACK, STAGE_RECALL
    from app.providers.recall import builtin

    sources = builtin()
    names = [s.name for s in sources]
    if d := _dups(names):
        errors.append(f"[recall] 重名召回源: {d}")
    valid_stages = {STAGE_RECALL, STAGE_FALLBACK, STAGE_ENRICH}
    for s in sources:
        if s.stage not in valid_stages:
            errors.append(f"[recall] 源 {s.name!r} stage 非法: {s.stage!r}")
        if not callable(getattr(s, "search", None)):
            errors.append(f"[recall] 源 {s.name!r} 未实现 search")
    print(f"  recall sources: {names}")


def _check_memory(errors: list[str]) -> None:
    from app.providers.memory import builtin

    names = [p.name for p in builtin()]
    if d := _dups(names):
        errors.append(f"[memory] 重名 Provider: {d}")
    print(f"  memory providers: {names}")


def _check_context(errors: list[str]) -> None:
    from app.providers.context import builtin

    names = [p.name for p in builtin()]
    if d := _dups(names):
        errors.append(f"[context] 重名 Provider: {d}")
    print(f"  context providers: {names}")


def _check_agents(errors: list[str]) -> None:
    from app.providers.agents import builtin

    agents = builtin()
    names = list(agents.keys())
    expected = {"router", "visual", "retrieval", "decision", "response"}
    missing = expected - set(names)
    if missing:
        errors.append(f"[agents] 缺少必需 Agent: {sorted(missing)}")
    print(f"  agents: {names}")


def _check_tools(errors: list[str]) -> None:
    from app.framework.tools.registry import ToolRegistry
    from app.providers.tools import builtin

    tools = builtin()
    names = [t.spec.name for t in tools]
    if d := _dups(names):
        errors.append(f"[tools] 重名工具: {d}")
    for t in tools:
        if not isinstance(t.spec.parameters, dict):
            errors.append(f"[tools] 工具 {t.spec.name!r} parameters 非 dict")
        if not callable(getattr(t, "run", None)):
            errors.append(f"[tools] 工具 {t.spec.name!r} 未实现 run")
        # LLM 可见工具的 schema 必须是 object 型（OpenAI tools 协议要求）
        if t.spec.llm_exposed and t.spec.parameters and t.spec.parameters.get("type") != "object":
            errors.append(f"[tools] 工具 {t.spec.name!r} llm_exposed 但 schema type 非 object")
    # order 权限工具不得出现在 LLM 白名单 schema 中
    reg = ToolRegistry(kind="tool")
    for t in tools:
        reg.register(t)
    llm_names = {s["function"]["name"] for s in reg.openai_schemas(llm_only=True)}
    banned = {t.spec.name for t in tools if t.spec.permission == "order" or not t.spec.llm_exposed}
    if leak := llm_names & banned:
        errors.append(f"[tools] LLM 白名单泄漏受限工具: {sorted(leak)}")
    # Phase 7: OmniAgent Loop 工具箱必须包含核心能力，且提交类动作不可见
    for required in ("shopping.search", "cart.add", "order.preview"):
        if required not in llm_names:
            errors.append(f"[tools] Loop 工具箱缺失核心工具: {required!r}")
    for forbidden in ("order.submit", "order.pay", "order.cancel"):
        if forbidden in llm_names:
            errors.append(f"[tools] 提交类动作不得暴露给 LLM: {forbidden!r}")
    print(f"  tools: {names}")
    print(f"  llm_exposed: {sorted(llm_names)}")


def _check_orchestration(errors: list[str]) -> None:
    """RulePlanner 全部模板引用的 capability 均已注册（tool: 前缀查 ToolRegistry）。"""
    import asyncio as _asyncio

    from app.framework.orchestration import RulePlanner
    from app.framework.orchestration.capabilities import get_capability
    from app.providers.tools import get_tool_registry
    from app.schemas.workflow import WorkflowState

    import app.workflow.graph  # noqa: F401 — 触发 capability 注册（注册表已下沉 framework）

    planner = RulePlanner()
    caps: set[str] = set()
    for intent in ("chitchat", "risk_check", "compare", "recommend", "alternative"):
        for img in (None, "http://x/img.jpg"):
            plan = _asyncio.run(planner.plan(WorkflowState(intent=intent, image_url=img)))
            caps.update(s.capability for s in plan.steps)
    # compare 带目标分解的分支（compare_retrieval）也要覆盖
    plan = _asyncio.run(planner.plan(WorkflowState(
        intent="compare", user_query="索尼和Bose的耳机对比哪个好")))
    caps.update(s.capability for s in plan.steps)
    registry = get_tool_registry()
    for cap in sorted(caps):
        if cap.startswith("tool:"):
            if registry.get_optional(cap[len("tool:"):]) is None:
                errors.append(f"[orchestration] 计划引用未注册工具: {cap!r}")
        elif get_capability(cap) is None:
            errors.append(f"[orchestration] 计划引用未注册 capability: {cap!r}")
    # LLM Planner 封闭词表必须⊆已注册 capability（防词表与注册漂移）
    from app.framework.orchestration import PIPELINE_CAPABILITIES

    for cap in sorted(PIPELINE_CAPABILITIES):
        if get_capability(cap) is None:
            errors.append(f"[orchestration] LLM 词表能力未注册: {cap!r}")
    print(f"  orchestration capabilities: {sorted(caps)}")


def _check_skills(errors: list[str]) -> None:
    """语义技能（PromptSkill）：名称唯一、模板非空且占位符合法。"""
    from app.providers.skills import builtin as skills_builtin

    skills = skills_builtin()
    names = [s.spec.name for s in skills]
    if d := _dups(names):
        errors.append(f"[skills] 重名技能: {d}")
    for s in skills:
        if not (s.spec.template or "").strip():
            errors.append(f"[skills] 技能 {s.spec.name!r} 模板为空")
    print(f"  skills: {names}")


def _check_unregistered(errors: list[str]) -> None:
    """孤儿组件防呆（P1-4，宪法 §3）：扫 providers/ 下所有 @component 类，
    与各 builtin() 清单求差集 —— 写了装饰器忘登记 builtin() 会静默失效，此处拦住。

    把 amap 自动发现的收益（不漏）嫁接到显式清单的骨架（可控）上。
    """
    import importlib
    import inspect
    import pkgutil

    import app.providers as providers_pkg

    # 1) 扫描定义：providers 包下所有挂 __component_kind__ 的类（import 触发装饰器）
    defined: dict[str, str] = {}  # name -> kind
    for mod_info in pkgutil.walk_packages(providers_pkg.__path__, prefix="app.providers."):
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception as exc:  # noqa: BLE001 — 单模块失败记错不阻断扫描
            errors.append(f"[registry] 模块 {mod_info.name} import 失败: {exc}")
            continue
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            kind = getattr(cls, "__component_kind__", None)
            name = getattr(cls, "__component_name__", None)
            if kind and name and cls.__module__.startswith("app.providers"):
                defined[name] = kind

    # 2) 聚合已登记：各 builtin() 清单的组件名
    registered: set[str] = set()
    from app.providers.agents import builtin as agents_builtin
    from app.providers.context import builtin as context_builtin
    from app.providers.memory import builtin as memory_builtin
    from app.providers.recall import builtin as recall_builtin
    from app.providers.skills import builtin as skills_builtin
    from app.providers.tools import builtin as tools_builtin

    registered |= {s.name for s in recall_builtin()}
    registered |= {p.name for p in memory_builtin()}
    registered |= {p.name for p in context_builtin()}
    registered |= set(agents_builtin().keys())
    registered |= {t.spec.name for t in tools_builtin()}
    registered |= {s.spec.name for s in skills_builtin()}
    # 非 builtin 清单、但有显式工厂装配路径的组件（白名单需附装配点证据）：
    # - llm_rerank_fusion: workflow/graph.py 模块级单例直接持有
    # - llm_keyword:       providers/recall/__init__.py default_rewriter() 工厂
    registered |= {"llm_rerank_fusion", "llm_keyword"}

    if orphans := {n for n in defined if n not in registered}:
        errors.append(
            f"[registry] 已定义未登记 builtin() 的孤儿组件: "
            f"{sorted((n, defined[n]) for n in orphans)}")
    print(f"  孤儿检测: 定义 {len(defined)} / 登记 {len(registered)} / 孤儿 {len(orphans) if orphans else 0}")


def main() -> int:
    errors: list[str] = []
    print("组件治理校验:")
    for check in (_check_recall, _check_memory, _check_context, _check_agents, _check_tools,
                  _check_orchestration, _check_skills, _check_unregistered):
        try:
            check(errors)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[{check.__name__}] 装配异常: {exc}")

    if errors:
        print("\n治理校验失败:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("\n✅ 组件治理校验通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
