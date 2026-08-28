"""Tool 框架单测 — 注册 / 执行 / 追踪 / 超时 / schema / 治理清单。

无外部依赖：使用内置 dummy 工具，覆盖 ToolRegistry 全部路径。
"""

import asyncio

import pytest

from app.framework.registry import DuplicateComponentError
from app.framework.tools import Tool, ToolContext, ToolRegistry, ToolResult, ToolSpec


class _EchoTool(Tool):
    spec = ToolSpec(
        name="test.echo", category="test", description="echo",
        parameters={"type": "object", "properties": {"msg": {"type": "string"}}},
    )

    async def run(self, ctx, msg=""):
        return ToolResult(message=f"echo:{msg}", data={"msg": msg})


class _BoomTool(Tool):
    spec = ToolSpec(name="test.boom", category="test")

    async def run(self, ctx):
        raise RuntimeError("boom")


class _SlowTool(Tool):
    spec = ToolSpec(name="test.slow", category="test", timeout_ms=20)

    async def run(self, ctx):
        await asyncio.sleep(0.2)
        return ToolResult(message="done")


class _OrderTool(Tool):
    spec = ToolSpec(name="test.order", category="test", permission="order")

    async def run(self, ctx):
        return ToolResult(message="ordered")


def _reg() -> ToolRegistry:
    r = ToolRegistry(kind="tool")
    r.register(_EchoTool())
    r.register(_BoomTool())
    r.register(_SlowTool())
    r.register(_OrderTool())
    return r


def test_register_and_get():
    r = _reg()
    assert r.get("test.echo").spec.name == "test.echo"
    assert {t.spec.name for t in r.by_category("test")} == {
        "test.echo", "test.boom", "test.slow", "test.order",
    }


def test_duplicate_raises():
    r = ToolRegistry(kind="tool")
    r.register(_EchoTool())
    with pytest.raises(DuplicateComponentError):
        r.register(_EchoTool())


async def test_invoke_success_writes_trace():
    r = _reg()
    ctx = ToolContext(user_id="u1", args_raw="hi")
    res = await r.invoke("test.echo", {"msg": "hi"}, ctx)
    assert res.ok and res.message == "echo:hi"
    assert ctx.tool_trace[0]["skill_name"] == "test.echo"  # 遗留契约 key
    assert ctx.tool_trace[0]["status"] == "success"


async def test_invoke_mirrors_state():
    from types import SimpleNamespace

    r = _reg()
    state = SimpleNamespace(skill_executions=[])
    ctx = ToolContext(user_id="u1", state=state)
    await r.invoke("test.echo", {"msg": "x"}, ctx)
    assert state.skill_executions and state.skill_executions[0]["skill_name"] == "test.echo"


async def test_invoke_strips_control_keys():
    r = _reg()
    ctx = ToolContext(user_id="u1")
    # _confirmed 不应作为业务参数传入 run（否则 echo 会 TypeError）
    res = await r.invoke("test.echo", {"msg": "ok", "_confirmed": True}, ctx)
    assert res.ok and res.message == "echo:ok"


async def test_invoke_failure():
    r = _reg()
    ctx = ToolContext(user_id="u1")
    res = await r.invoke("test.boom", {}, ctx)
    assert not res.ok and "boom" in res.error
    assert ctx.tool_trace[0]["status"] == "failed"


async def test_invoke_timeout():
    r = _reg()
    ctx = ToolContext(user_id="u1")
    res = await r.invoke("test.slow", {}, ctx)
    assert not res.ok
    assert ctx.tool_trace[0]["status"] == "failed"


async def test_invoke_unknown():
    r = _reg()
    ctx = ToolContext(user_id="u1")
    res = await r.invoke("test.nope", {}, ctx)
    assert not res.ok and res.error.startswith("unknown_tool")


async def test_order_permission_requires_confirm():
    r = _reg()
    ctx = ToolContext(user_id="u1")
    denied = await r.invoke("test.order", {}, ctx)
    assert not denied.ok and denied.error == "confirmation_required"
    allowed = await r.invoke("test.order", {"_confirmed": True}, ctx)
    assert allowed.ok and allowed.message == "ordered"


def test_openai_schemas():
    r = _reg()
    schemas = r.openai_schemas(["test.echo"])
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "test.echo"
    assert "parameters" in schemas[0]["function"]


def test_builtin_governance_unique():
    from app.providers.tools import builtin

    names = [t.spec.name for t in builtin()]
    assert len(names) == len(set(names))  # 名称唯一
    assert len(names) == 23, names        # 改这个数字前先确认工具是有意增删的
    assert "cart.remove" in names and "shopping.search" in names
    # 选品工具：卡片与答文候选集的唯一真源，缺了会退回"卡片讲 A、回答讲 B"
    assert "shopping.display" in names
    assert "shopping.product_dossier" in names
    assert "order.preview" in names and "order.submit" in names
    assert "order.list" in names and "order.detail" in names
    assert "order.cancel" in names and "order.track" in names and "order.pay" in names
    assert "shopping.check_inventory" in names
    # Phase 6-B3: 偏好 & 会话族
    assert "preference.save" in names and "preference.list" in names and "preference.delete" in names
    assert "conversation.history" in names and "conversation.reset" in names


def test_openai_schemas_llm_only_whitelist():
    """B1+Phase7：LLM 白名单——提交类动作永不暴露；cart.add/order.preview 已对 ReAct 开放。"""
    from app.providers.tools import builtin

    r = ToolRegistry(kind="tool")
    for t in builtin():
        r.register(t)
    schemas = r.openai_schemas(llm_only=True)
    names = {s["function"]["name"] for s in schemas}
    # 提交类动作（permission=order）永不暴露
    assert {"order.submit", "order.pay", "order.cancel"}.isdisjoint(names)
    # Phase 7：ReAct 多轮携带上下文，cart.add/order.preview 开放给 Loop
    assert "cart.add" in names and "order.preview" in names
    # 可直选工具在列，且参数 schema 完整
    assert "cart.remove" in names and "order.list" in names and "shopping.search" in names
    remove_schema = next(s for s in schemas if s["function"]["name"] == "cart.remove")
    assert "ordinal" in remove_schema["function"]["parameters"]["properties"]
