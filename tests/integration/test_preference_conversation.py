"""Phase 6-B3 偏好/会话工具族测试 —— 工具语义 + ShopActionAgent 路由 + 关键词冲突。"""

import pytest

from app.framework.tools import ToolContext
from app.providers.tools import get_tool_registry
from app.providers.tools.conversation import ConversationHistoryTool, ConversationResetTool
from app.providers.tools.preference import (
    PreferenceDeleteTool,
    PreferenceListTool,
    PreferenceSaveTool,
)

_ENTRIES = [
    {"entry_id": "e1", "raw_text": "预算都在500以内", "category": "通用", "enabled": True},
    {"entry_id": "e2", "raw_text": "不要推荐香菜味", "category": "食品饮料", "enabled": True},
]


class _FakeProfileSvc:
    def __init__(self):
        self.saved = []
        self.entries = list(_ENTRIES)

    async def parse_and_save(self, user_id, raw_text, entry_id=""):
        self.saved.append(raw_text)
        return {"entry_id": "e_new", "raw_text": raw_text, "category": "通用"}

    async def list_all_entries(self, user_id):
        return self.entries

    async def list_entries(self, user_id, category=""):
        return [e for e in self.entries if e["category"] == category]


class _FakePrefRepo:
    def __init__(self):
        self.deleted = []

    async def adelete(self, entry_id, user_id):
        self.deleted.append(entry_id)
        return entry_id in {e["entry_id"] for e in _ENTRIES}


class _FakeConvSvc:
    def __init__(self):
        self.snapshot_updates = []

    def get_messages(self, cid, limit=50):
        return [{"role": "user", "content": "推荐蓝牙耳机"},
                {"role": "assistant", "content": "推荐你看看这几款～"}]

    async def aupdate_context_snapshot(self, cid, update):
        self.snapshot_updates.append(update)

    async def get_context_snapshot(self, cid):
        return {}


@pytest.fixture
def fakes(monkeypatch):
    svc, repo, conv = _FakeProfileSvc(), _FakePrefRepo(), _FakeConvSvc()
    monkeypatch.setattr("app.services.user_profile_service.get_user_profile_service", lambda: svc)
    monkeypatch.setattr("app.repositories.user_preference_repo.get_user_preference_repo", lambda: repo)
    monkeypatch.setattr("app.services.conversation_service.get_conversation_service", lambda: conv)
    return svc, repo, conv


# ---- 工具语义 ----

async def test_preference_save(fakes):
    svc, _, _ = fakes
    res = await PreferenceSaveTool().run(ToolContext(user_id="u1"), raw_text="以后预算500以内")
    assert res.ok and "记住啦" in res.message
    assert svc.saved == ["以后预算500以内"]


async def test_preference_save_empty_rejected(fakes):
    res = await PreferenceSaveTool().run(ToolContext(user_id="u1"), raw_text="  ")
    assert not res.ok


async def test_preference_list(fakes):
    res = await PreferenceListTool().run(ToolContext(user_id="u1"))
    assert "2 条" in res.message and "预算都在500以内" in res.message
    assert len(res.data["entries"]) == 2


async def test_preference_delete(fakes):
    _, repo, _ = fakes
    res = await PreferenceDeleteTool().run(ToolContext(user_id="u1"), entry_id="e2")
    assert res.ok and repo.deleted == ["e2"]
    res2 = await PreferenceDeleteTool().run(ToolContext(user_id="u1"), entry_id="nope")
    assert not res2.ok


async def test_conversation_history(fakes):
    res = await ConversationHistoryTool().run(ToolContext(user_id="u1", conversation_id="c1"))
    assert "最近聊过" in res.message and "欧米" in res.message
    # 无会话 → 友好提示
    res2 = await ConversationHistoryTool().run(ToolContext(user_id="u1"))
    assert "刚开始聊" in res2.message


async def test_conversation_reset(fakes):
    _, _, conv = fakes
    res = await ConversationResetTool().run(ToolContext(user_id="u1", conversation_id="c1"))
    assert res.ok and "重新开始" in res.message
    assert conv.snapshot_updates[0]["focus_product"] is None
    assert conv.snapshot_updates[0]["last_products"] == []


# ---- ShopActionAgent 路由 ----

async def _agent_handle(msg, fakes):
    from app.agents.shop_action_agent import ShopActionAgent

    return await ShopActionAgent().handle(msg, ToolContext(user_id="u1", conversation_id="c1"))


async def test_agent_routes_pref_list(fakes):
    res = await _agent_handle("我的偏好有哪些", fakes)
    assert "预算都在500以内" in res.message


async def test_agent_routes_pref_save(fakes):
    svc, _, _ = fakes
    res = await _agent_handle("记住我以后只买国产品牌", fakes)
    # P1-2: 句首触发词剥离后再入库
    assert res.ok and svc.saved == ["以后只买国产品牌"]


async def test_pref_save_strips_trigger_prefix(fakes):
    svc, _, _ = fakes
    res = await PreferenceSaveTool().run(ToolContext(user_id="u1"),
                                         raw_text="记住我以后买东西预算都在500以内")
    assert res.ok
    assert svc.saved == ["以后买东西预算都在500以内"]


async def test_parse_and_save_falls_back_to_general_category(monkeypatch):
    """P1-2: 无品类归属的全局偏好落“通用”而非拒存。"""
    from app.services.user_profile_service import UserProfileService, get_user_profile_service

    svc = get_user_profile_service()

    async def fake_parse(self, raw_text):
        return {"budget_max": 500}  # 无 category

    captured = {}

    class _Repo:
        async def asave(self, user_id, raw_text, parsed, entry_id=""):
            captured.update(parsed)
            from types import SimpleNamespace
            return SimpleNamespace(to_dict=lambda: {"entry_id": entry_id, **parsed})

    monkeypatch.setattr(UserProfileService, "_parse_with_qwen", fake_parse)
    monkeypatch.setattr("app.services.user_profile_service.get_user_preference_repo", lambda: _Repo())
    out = await svc.parse_and_save("u1", "预算都在500以内", entry_id="e_edit")
    assert out is not None
    assert captured.get("category") == "通用"


async def test_agent_pref_delete_ordinal_not_stolen_by_cart(fakes):
    """关键词冲突：'删除第2条偏好' 含 '删除第'，必须走偏好而非 cart.remove。"""
    _, repo, _ = fakes
    res = await _agent_handle("删除第2条偏好", fakes)
    assert res.ok and repo.deleted == ["e2"]


async def test_agent_pref_delete_out_of_range(fakes):
    res = await _agent_handle("删除第9条偏好", fakes)
    assert not res.ok and "只有 2 条" in res.message


async def test_agent_routes_conversation(fakes):
    _, _, conv = fakes
    res = await _agent_handle("我们刚才聊了什么", fakes)
    assert "最近聊过" in res.message
    res2 = await _agent_handle("清空上下文重新来", fakes)
    assert res2.ok and conv.snapshot_updates


# ---- 治理 ----

async def test_alist_by_category_includes_general(monkeypatch):
    """P1-2: 指定品类查询同时召回“通用”条目（SQL IN 条件断言）。"""
    from types import SimpleNamespace

    from app.repositories.user_preference_repo import UserPreferenceRepository

    repo = UserPreferenceRepository()
    captured = {}

    class _FakeSession:
        async def execute(self, stmt):
            compiled = stmt.compile()
            captured["sql"] = str(compiled)
            captured["params"] = dict(compiled.params)
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    async def _fake_gen():
        yield _FakeSession()

    monkeypatch.setattr(repo, "_aget_session", _fake_gen)
    out = await repo.alist_by_category("u1", "数码电子")
    assert out == []
    assert "IN" in captured["sql"].upper()
    # IN 参数为 expanding list（如 {'category_1': ['数码电子', '通用']}），扁平化后断言
    flat = []
    for v in captured["params"].values():
        flat.extend(v if isinstance(v, (list, tuple)) else [v])
    assert "数码电子" in flat and "通用" in flat


def test_new_tools_registered_and_llm_exposed():
    reg = get_tool_registry()
    for name in ("preference.save", "preference.list", "preference.delete",
                 "conversation.history", "conversation.reset"):
        tool = reg.get_optional(name)
        assert tool is not None, name
        assert tool.spec.llm_exposed is True
