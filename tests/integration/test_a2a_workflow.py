"""Phase 3 A2A 集成测试 —— 黑板在动态图 / 工具链两条路径上的端到端行为。

覆盖：记忆召回并行化（memories.ready）/ supervisor 事件流 / legacy 回归零影响 /
registry Artifact 落板 / ShopActionAgent 自动建板。
"""

import asyncio

import pytest

from app.schemas.workflow import WorkflowState


async def _run(query: str, **kw):
    from app.workflow.graph import run_workflow

    return await run_workflow(user_query=query, enable_checkpoint=False, **kw)


async def test_memory_recall_parallel_via_blackboard(monkeypatch):
    """动态模式：Router 后台召回 → Decision 经黑板消费（与检索/精排并行）。"""
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", True)

    async def fake_recall(**kw):
        await asyncio.sleep(0.05)  # 模拟召回延迟——不再阻塞 Router
        return [{"category": "数码电子", "preference": "喜欢降噪"}]

    monkeypatch.setattr("app.providers.memory.recall_used_memories", fake_recall)
    state = await _run("推荐一款蓝牙耳机", user_id="u_mem")
    assert state.used_memories and state.used_memories[0]["preference"] == "喜欢降噪"
    assert state.timing.get("a2a_events", 0) > 0


async def test_memory_recall_timeout_degrades_empty(monkeypatch):
    """召回超时 → Decision 降级空偏好，不阻塞主链。"""
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", True)

    async def slow_recall(**kw):
        await asyncio.sleep(5)  # 超过 decision wait_for 的 1.5s
        return [{"preference": "太慢了"}]

    monkeypatch.setattr("app.providers.memory.recall_used_memories", slow_recall)
    state = await _run("推荐一款蓝牙耳机", user_id="u_slow")
    assert state.used_memories == []
    assert state.answer  # 主链正常完成


async def test_supervisor_publishes_step_events(monkeypatch):
    """每个 capability 完成发布 <cap>.done；reflect 结束落 a2a 汇总。"""
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", True)
    state = await _run("推荐一款蓝牙耳机")
    # 事件数 >= 步骤数 + memories.ready（无 user_id 也发布空）
    assert state.timing.get("a2a_events", 0) >= len(state.completed_steps) + 1
    assert any(t.get("agent_name") == "Blackboard (A2A)" for t in state.trace_steps)


async def test_legacy_mode_untouched(monkeypatch):
    """flag off：无黑板、内联召回，行为与 Phase 3 之前一致。"""
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", False)

    async def fake_recall(**kw):
        return [{"preference": "inline"}]

    monkeypatch.setattr("app.providers.memory.recall_used_memories", fake_recall)
    state = await _run("推荐一款蓝牙耳机", user_id="u_legacy")
    assert state.used_memories == [{"preference": "inline"}]
    assert "a2a_events" not in state.timing


async def test_tool_artifacts_land_on_blackboard():
    """registry.invoke 自动把 ToolResult.artifacts 落黑板。"""
    from app.framework.blackboard import Blackboard
    from app.framework.tools import Tool, ToolContext, ToolResult, ToolSpec
    from app.providers.tools import get_tool_registry
    from app.schemas.a2a import Artifact

    class _ArtifactTool(Tool):
        spec = ToolSpec(name="test.a2a_dummy", category="test", description="dummy")

        async def run(self, ctx):
            return ToolResult(message="ok", artifacts=[Artifact(
                artifact_id="A-T1", artifact_type="order.created",
                producer_agent="tool:test", content={"order_id": "ORD-TEST"},
            )])

    reg = get_tool_registry()
    if reg.get_optional("test.a2a_dummy") is None:
        reg.register(_ArtifactTool())

    ctx = ToolContext(user_id="u1", blackboard=Blackboard())
    res = await reg.invoke("test.a2a_dummy", {}, ctx)
    assert res.ok
    art = ctx.blackboard.get("order.created")
    assert art is not None and art.content["order_id"] == "ORD-TEST"


async def test_shop_agent_auto_creates_blackboard():
    """ShopActionAgent.handle 自动挂请求级黑板。"""
    from app.agents.shop_action_agent import ShopActionAgent
    from app.framework.tools import ToolContext

    ctx = ToolContext(user_id="u1")
    res = await ShopActionAgent().handle("随便聊聊", ctx)
    assert ctx.blackboard is not None
    assert res.message  # 兜底提示正常返回
