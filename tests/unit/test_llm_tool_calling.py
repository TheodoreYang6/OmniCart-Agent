"""Phase 6-B1 LLM 函数调用单测 —— 响应解析 / dispatcher LLM 分支 / MOCK 惰性 / agent 兜底接入。"""

import pytest

from app.framework.tools import Tool, ToolContext, ToolResult, ToolSpec
from app.framework.tools.dispatcher import ToolDispatcher
from app.framework.tools.registry import ToolRegistry
from app.model_gateway.qwen_chat import QwenChat


# ---- _parse_tool_message ----

def test_parse_tool_message_normal():
    data = {"choices": [{"message": {
        "content": None,
        "tool_calls": [{"id": "c1", "function": {
            "name": "cart.remove", "arguments": '{"ordinal": 2}'}}],
    }}]}
    out = QwenChat._parse_tool_message(data)
    assert out["tool_calls"] == [{"id": "c1", "name": "cart.remove", "args": {"ordinal": 2}}]
    assert out["content"] == ""


def test_parse_tool_message_bad_arguments_degrades():
    data = {"choices": [{"message": {"tool_calls": [
        {"id": "c1", "function": {"name": "cart.view", "arguments": "{not json"}},
        {"id": "c2", "function": {"name": "order.list", "arguments": "[1,2]"}},  # 非 dict
    ]}}]}
    out = QwenChat._parse_tool_message(data)
    assert out["tool_calls"][0]["args"] == {}
    assert out["tool_calls"][1]["args"] == {}


def test_parse_tool_message_content_only_and_empty():
    assert QwenChat._parse_tool_message(
        {"choices": [{"message": {"content": "你好呀"}}]}
    ) == {"content": "你好呀", "tool_calls": []}
    assert QwenChat._parse_tool_message({}) == {"content": "", "tool_calls": []}


# ---- dispatcher LLM 分支 ----

class _EchoTool(Tool):
    spec = ToolSpec(name="test.echo", category="test", description="echo",
                    parameters={"type": "object", "properties": {"n": {"type": "integer"}}})

    async def run(self, ctx, n: int = 0):
        return ToolResult(message=f"echo-{n}")


def _make_registry() -> ToolRegistry:
    r = ToolRegistry(kind="tool")
    r.register(_EchoTool())
    return r


class _FakeGateway:
    def __init__(self, result=None, raise_exc=False):
        self._result = result or {"content": "", "tool_calls": []}
        self._raise = raise_exc
        self.calls = 0

    async def chat_with_tools(self, capability, messages, tools, system=""):
        self.calls += 1
        if self._raise:
            raise RuntimeError("boom")
        return self._result


@pytest.fixture
def llm_on(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_LLM_TOOL_CALLING", True)


def _patch_gateway(monkeypatch, gw):
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)


async def test_llm_branch_selects_and_invokes(llm_on, monkeypatch):
    gw = _FakeGateway({"content": "", "tool_calls": [
        {"id": "c1", "name": "test.echo", "args": {"n": 7}}]})
    _patch_gateway(monkeypatch, gw)
    res = await ToolDispatcher(_make_registry()).dispatch("帮我看看那个东西", ToolContext(user_id="u1"))
    assert res.ok and res.message == "echo-7"
    assert gw.calls == 1


async def test_llm_branch_unknown_tool_no_match(llm_on, monkeypatch):
    gw = _FakeGateway({"content": "", "tool_calls": [{"id": "c1", "name": "not.exists", "args": {}}]})
    _patch_gateway(monkeypatch, gw)
    res = await ToolDispatcher(_make_registry()).dispatch("随便说说", ToolContext())
    assert not res.ok and res.error == "no_match"


async def test_llm_branch_empty_calls_no_match(llm_on, monkeypatch):
    gw = _FakeGateway()  # 空 tool_calls（MOCK 惰性同形态）
    _patch_gateway(monkeypatch, gw)
    res = await ToolDispatcher(_make_registry()).dispatch("随便说说", ToolContext())
    assert not res.ok and res.error == "no_match"


async def test_llm_branch_exception_degrades(llm_on, monkeypatch):
    gw = _FakeGateway(raise_exc=True)
    _patch_gateway(monkeypatch, gw)
    res = await ToolDispatcher(_make_registry()).dispatch("随便说说", ToolContext())
    assert not res.ok and res.error == "no_match"


async def test_flag_off_skips_llm(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_LLM_TOOL_CALLING", False)
    gw = _FakeGateway({"content": "", "tool_calls": [{"id": "c1", "name": "test.echo", "args": {}}]})
    _patch_gateway(monkeypatch, gw)
    res = await ToolDispatcher(_make_registry()).dispatch("随便说说", ToolContext())
    assert not res.ok and gw.calls == 0


async def test_rule_hit_bypasses_llm(llm_on, monkeypatch):
    """关键词命中 → 直达，不消耗 LLM 调用。"""
    gw = _FakeGateway()
    _patch_gateway(monkeypatch, gw)
    from app.providers.tools import get_tool_registry

    res = await ToolDispatcher(get_tool_registry()).dispatch("清空购物车", ToolContext(user_id="u_llm"))
    assert gw.calls == 0            # 未消耗 LLM 调用
    assert res.error != "no_match"  # 规则路由已接管（工具内部成败与否取决于仓库环境）


# ---- MOCK 惰性（真实 gateway 对象 + MOCK provider）----

async def test_mock_gateway_returns_empty_calls():
    from app.model_gateway.gateway import get_model_gateway

    out = await get_model_gateway().chat_with_tools(
        "tool_calling", [{"role": "user", "content": "删除第二个"}],
        [{"type": "function", "function": {"name": "cart.remove", "parameters": {}}}])
    assert out["tool_calls"] == []


# ---- ShopActionAgent 兜底接入 ----

async def test_shop_agent_llm_fallback(llm_on, monkeypatch):
    from app.agents.shop_action_agent import ShopActionAgent

    class _ListTool(Tool):
        spec = ToolSpec(name="order.list", category="order", description="list",
                        parameters={"type": "object", "properties": {}})

        async def run(self, ctx, limit: int = 20):
            return ToolResult(message="你的订单在这里")

    reg = ToolRegistry(kind="tool")
    reg.register(_ListTool())
    monkeypatch.setattr("app.providers.tools.get_tool_registry", lambda: reg)
    gw = _FakeGateway({"content": "", "tool_calls": [
        {"id": "c1", "name": "order.list", "args": {}}]})
    _patch_gateway(monkeypatch, gw)

    res = await ShopActionAgent().handle("帮我瞅瞅我买过哪些东西", ToolContext(user_id="u1"))
    assert res.message == "你的订单在这里"
    assert gw.calls == 1


async def test_shop_agent_flag_off_falls_to_prompt(monkeypatch):
    from app.agents.shop_action_agent import ShopActionAgent

    monkeypatch.setattr("app.core.config.ENABLE_LLM_TOOL_CALLING", False)
    res = await ShopActionAgent().handle("帮我瞅瞅我买过哪些东西", ToolContext(user_id="u1"))
    assert "问欧米" in res.message  # 原兜底文案
