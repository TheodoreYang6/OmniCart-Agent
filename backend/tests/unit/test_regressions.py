"""回归测试：本轮缺陷修复的关键路径。"""

import asyncio
from types import SimpleNamespace

from app.repositories.pg_cart_repo import MemCartRepository
from app.schemas.cart import CartItemCreate


def test_mem_cart_batch_remove_removes_requested_items():
    repo = MemCartRepository()
    repo.add_item(CartItemCreate(product_id="p1", quantity=1), user_id="u1")
    repo.add_item(CartItemCreate(product_id="p2", quantity=2), user_id="u1")
    repo.add_item(CartItemCreate(product_id="p3", quantity=1), user_id="u1")

    ids = [item.cart_item_id for item in repo.get_cart("u1").items[:2]]
    removed = repo.batch_remove(ids, "u1")

    assert removed == 2
    assert len(repo.get_cart("u1").items) == 1


def test_owned_conversation_id_enforces_ownership(monkeypatch):
    from app.api import preference

    class FakeConversation:
        def __init__(self, conversation_id, user_id):
            self.conversation_id = conversation_id
            self.user_id = user_id

    class FakeRepo:
        def __init__(self):
            self.conversations = {
                "cid_owned": FakeConversation("cid_owned", "user_a"),
                "cid_other": FakeConversation("cid_other", "user_b"),
            }

        def get(self, conversation_id):
            return self.conversations.get(conversation_id)

        def get_latest_by_session(self, user_id, session_id):
            if session_id == "sess_a" and user_id == "user_a":
                return self.conversations["cid_owned"]
            return None

    monkeypatch.setattr(preference, "get_conversation_repo", lambda: FakeRepo())

    actor = SimpleNamespace(user_id="user_a")
    assert preference._owned_conversation_id(actor, "cid_owned", "") == "cid_owned"
    assert preference._owned_conversation_id(actor, "cid_other", "") is None
    assert preference._owned_conversation_id(actor, "", "sess_a") == "cid_owned"
    assert preference._owned_conversation_id(actor, "", "missing") is None


def test_recommend_guide_profile_prefill_does_not_raise_unbound(monkeypatch):
    from app.api import recommend
    from app.core.identity import Actor

    class FakeProfileService:
        async def get_profile(self, user_id):
            return {
                "enabled": True,
                "categories": ["数码电子"],
                "budget_max": 2000,
                "budget_min": None,
            }

    class FakeGuide:
        should_recommend = False
        answer = "还需要确认预算"
        options = []
        locked_category = "数码电子"
        locked_sub_category = ""
        locked_concern = ""
        budget_max = 2000
        budget_min = None

    def fake_get_constraint_guide():
        return SimpleNamespace(guide=lambda **kwargs: FakeGuide())

    monkeypatch.setattr(
        "app.services.user_profile_service.get_user_profile_service",
        lambda: FakeProfileService(),
    )
    monkeypatch.setattr(
        "app.services.constraint_guide.get_constraint_guide",
        fake_get_constraint_guide,
    )

    actor = Actor(user_id="user_a", kind="user", token="token")
    req = recommend.GuideRequest(user_query="你好", user_id="user_a")

    result = asyncio.run(recommend.recommend_guide(req, actor=actor))

    assert result.should_recommend is False
    assert result.locked_category == "数码电子"
