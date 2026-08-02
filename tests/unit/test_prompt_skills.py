"""Phase 6-B4 PromptSkill 测试 —— 框架契约 / 首个技能 / Agent 触发与降级。"""

import pytest

from app.framework.skills import PromptSkill, PromptSkillSpec
from app.framework.tools import ToolContext
from app.providers.skills import ProductCopywriterSkill, builtin, get_skill_registry


class _FakeGw:
    def __init__(self, resp="欧米觉得这款超值！🎧 快来看看吧～", raise_exc=False):
        self.prompts, self._resp, self._raise = [], resp, raise_exc

    async def chat(self, capability, prompt, system=""):
        self.prompts.append((capability, prompt))
        if self._raise:
            raise RuntimeError("boom")
        return self._resp


# ---- 框架契约 ----

async def test_prompt_skill_renders_template_and_calls_gateway(monkeypatch):
    gw = _FakeGw()
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)

    class _S(PromptSkill):
        spec = PromptSkillSpec(name="t.s", template="给{name}打个招呼", capability="chat_generation")

    out = await _S().run(name="小明")
    assert out == gw._resp
    cap, prompt = gw.prompts[0]
    assert cap == "chat_generation" and prompt == "给小明打个招呼"


async def test_prompt_skill_missing_placeholder_raises(monkeypatch):
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: _FakeGw())

    class _S(PromptSkill):
        spec = PromptSkillSpec(name="t.s2", template="需要{must_have}")

    with pytest.raises(KeyError):
        await _S().run(wrong_key="x")   # 缺占位符 → KeyError（调用方降级）


def test_skill_registry_and_builtin():
    names = [s.spec.name for s in builtin()]
    assert names == ["copywriter.product"]
    reg = get_skill_registry()
    assert reg.get("copywriter.product") is not None
    assert ProductCopywriterSkill.spec.kind == "prompt"
    assert "{product_info}" in ProductCopywriterSkill.spec.template


# ---- Agent 触发与降级 ----

async def _handle(msg, monkeypatch, snap=None):
    from app.agents.shop_action_agent import ShopActionAgent

    class _Conv:
        async def get_context_snapshot(self, cid):
            return snap or {}

    monkeypatch.setattr("app.services.conversation_service.get_conversation_service", lambda: _Conv())
    return await ShopActionAgent().handle(msg, ToolContext(user_id="u1", conversation_id="c1"))


async def test_agent_copywriter_uses_focus_product(monkeypatch):
    gw = _FakeGw()
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    snap = {"focus_product": {"product_id": "P1", "brand": "华为", "title": "FreeBuds Pro 5", "price": 999}}
    res = await _handle("帮我写个文案", monkeypatch, snap)
    assert res.ok and "种草文案" in res.message and "超值" in res.message
    assert "华为 FreeBuds Pro 5" in gw.prompts[0][1]   # 商品信息进了模板
    assert res.data["skill"] == "copywriter.product"


async def test_agent_copywriter_ordinal_from_last_products(monkeypatch):
    gw = _FakeGw()
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway", lambda: gw)
    snap = {"last_products": [
        {"product_id": "P1", "brand": "索尼", "title": "降噪耳机", "price": 899},
        {"product_id": "P2", "brand": "QCY", "title": "MeloBuds", "price": 199},
    ]}
    res = await _handle("给第二个写个文案", monkeypatch, snap)
    assert res.ok and "QCY" in gw.prompts[0][1]


async def test_agent_copywriter_no_target_prompts(monkeypatch):
    res = await _handle("写个文案", monkeypatch, {})
    assert "先告诉我写哪个商品" in res.message


async def test_agent_copywriter_gateway_failure_degrades(monkeypatch):
    monkeypatch.setattr("app.model_gateway.gateway.get_model_gateway",
                        lambda: _FakeGw(raise_exc=True))
    snap = {"focus_product": {"product_id": "P1", "brand": "b", "title": "t", "price": 1}}
    res = await _handle("写个文案", monkeypatch, snap)
    assert not res.ok and "生成失败" in res.message
