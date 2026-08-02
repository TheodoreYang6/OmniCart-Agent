"""P0-1 会话连续性单测 —— cid 缺失时按 session 复用最近会话。"""

from types import SimpleNamespace

from app.services.conversation_service import ConversationService


class _FakeRepo:
    def __init__(self):
        self.created = 0
        self.by_session = {}   # session_id -> conv
        self.by_id = {}

    async def acreate(self, user_id, session_id, title=""):
        self.created += 1
        conv = SimpleNamespace(conversation_id=f"CONV-{self.created:04d}",
                               user_id=user_id, session_id=session_id)
        self.by_session[session_id] = conv
        self.by_id[conv.conversation_id] = conv
        return conv

    async def aget(self, conversation_id):
        return self.by_id.get(conversation_id)

    async def aget_latest_by_session(self, user_id, session_id):
        conv = self.by_session.get(session_id)
        if conv and user_id and conv.user_id != user_id:
            return None
        return conv


def _svc() -> ConversationService:
    svc = ConversationService.__new__(ConversationService)
    svc._repo = _FakeRepo()
    return svc


async def test_same_session_reuses_conversation():
    svc = _svc()
    r1 = await svc.aget_or_create(user_id="u1", session_id="s1", conversation_id="")
    r2 = await svc.aget_or_create(user_id="u1", session_id="s1", conversation_id="")
    r3 = await svc.aget_or_create(user_id="u1", session_id="s1", conversation_id="")
    assert r1["conversation_id"] == r2["conversation_id"] == r3["conversation_id"]
    assert r1["is_new"] is True and r2["is_new"] is False
    assert svc._repo.created == 1  # 只建一次


async def test_explicit_cid_takes_priority():
    svc = _svc()
    r1 = await svc.aget_or_create(user_id="u1", session_id="s1", conversation_id="")
    # 换 session 但显式回传 cid → 沿用
    r2 = await svc.aget_or_create(user_id="u1", session_id="s2",
                                  conversation_id=r1["conversation_id"])
    assert r2["conversation_id"] == r1["conversation_id"]


async def test_different_sessions_do_not_share():
    svc = _svc()
    r1 = await svc.aget_or_create(user_id="u1", session_id="s1", conversation_id="")
    r2 = await svc.aget_or_create(user_id="u1", session_id="s2", conversation_id="")
    assert r1["conversation_id"] != r2["conversation_id"]


async def test_session_lookup_failure_degrades_to_create():
    svc = _svc()

    async def _boom(user_id, session_id):
        raise RuntimeError("db down")

    svc._repo.aget_latest_by_session = _boom
    r = await svc.aget_or_create(user_id="u1", session_id="s1", conversation_id="")
    assert r["is_new"] is True  # 复用失败降级新建，不抛错
