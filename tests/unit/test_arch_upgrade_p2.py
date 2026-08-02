"""P2 架构升级单测 —— schema_overrides 运营位 / mode 三档派发。

spec: docs/specs/amap-arch-upgrade/spec.md §3.1 / §6
"""

from app.framework.tools import ToolRegistry
from app.providers.tools import builtin
from app.schemas.workflow import WorkflowState


def _fresh_registry() -> ToolRegistry:
    reg = ToolRegistry(kind="tool")
    reg.register_all(builtin())
    return reg


# ---- P2-3 schema_overrides ----

def test_schema_overrides_replaces_llm_visible_description_only():
    reg = _fresh_registry()
    reg.set_schema_overrides({"shopping.search": {"description": "运营调优后的搜索描述"}})
    schemas = {s["function"]["name"]: s["function"] for s in reg.openai_schemas(llm_only=True)}
    assert schemas["shopping.search"]["description"] == "运营调优后的搜索描述"
    # 运行时校验走 ToolSpec，spec 本体不被污染
    assert reg.get("shopping.search").spec.description != "运营调优后的搜索描述"
    # 未覆盖工具不受影响
    assert schemas["cart.add"]["description"] == reg.get("cart.add").spec.description


def test_schema_overrides_unknown_tool_ignored():
    reg = _fresh_registry()
    reg.set_schema_overrides({"no.such.tool": {"description": "x"}})
    # 不抛异常，未知项被忽略
    assert reg.openai_schemas(llm_only=True)


def test_schema_overrides_parameters_override():
    reg = _fresh_registry()
    custom = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
    reg.set_schema_overrides({"shopping.search": {"parameters": custom}})
    schemas = {s["function"]["name"]: s["function"] for s in reg.openai_schemas(llm_only=True)}
    assert schemas["shopping.search"]["parameters"] == custom


# ---- P2-1 mode 三档 ----

def test_workflow_state_mode_default_standard():
    assert WorkflowState().mode == "standard"


def test_mode_lite_replaces_fast_mode_magic_string():
    # lite 档由显式字段承载，context_prompt 不再嵌 [FAST_MODE] 标记
    st = WorkflowState(mode="lite", context_prompt="正常上下文")
    assert st.mode == "lite"
    assert "[FAST_MODE]" not in st.context_prompt
