"""Phase 3 Blackboard 单测 —— publish/get/wait_for/subscribe/put/topics。"""

import asyncio

from app.framework.blackboard import Blackboard
from app.schemas.a2a import Artifact


async def test_publish_get_roundtrip():
    bb = Blackboard()
    art = await bb.publish("retrieval.done", {"count": 5}, producer="supervisor")
    assert art.artifact_type == "retrieval.done"
    got = bb.get("retrieval.done")
    assert got is art and got.content["count"] == 5
    assert bb.get("nonexistent") is None


async def test_history_preserves_order_and_latest_wins():
    bb = Blackboard()
    await bb.publish("t", {"v": 1}, producer="a")
    await bb.publish("t", {"v": 2}, producer="b")
    assert [a.content["v"] for a in bb.history] == [1, 2]
    assert bb.get("t").content["v"] == 2  # latest 覆盖
    assert bb.topics() == ["t"]           # 去重


async def test_wait_for_already_published_returns_immediately():
    bb = Blackboard()
    await bb.publish("memories.ready", {"memories": []}, producer="router")
    art = await bb.wait_for("memories.ready", timeout=0.01)
    assert art is not None


async def test_wait_for_future_publish():
    bb = Blackboard()

    async def _producer():
        await asyncio.sleep(0.02)
        await bb.publish("memories.ready", {"memories": [{"k": "v"}]}, producer="router")

    bb.spawn(_producer())
    art = await bb.wait_for("memories.ready", timeout=1.0)
    assert art is not None and art.content["memories"] == [{"k": "v"}]


async def test_wait_for_timeout_degrades_to_none():
    bb = Blackboard()
    art = await bb.wait_for("never.published", timeout=0.02)
    assert art is None


async def test_subscribe_callback_fired_and_exception_isolated():
    bb = Blackboard()
    received = []
    bb.subscribe("evt", lambda a: received.append(a.content["n"]))
    bb.subscribe("evt", lambda a: 1 / 0)  # 异常订阅方不影响总线
    await bb.publish("evt", {"n": 1}, producer="p")
    await bb.publish("evt", {"n": 2}, producer="p")
    assert received == [1, 2]


async def test_put_existing_artifact_topic_is_type():
    """registry.invoke 的 ToolResult.artifacts 落板通路。"""
    bb = Blackboard()
    await bb.put(Artifact(artifact_id="A-X", artifact_type="order.created",
                          producer_agent="tool:order.submit", content={"order_id": "O1"}))
    assert bb.get("order.created").content["order_id"] == "O1"
