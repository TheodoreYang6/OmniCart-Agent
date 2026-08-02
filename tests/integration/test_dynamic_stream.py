"""P0-2 真流式动态图集成测试 —— no_response 路径按 flag 选动态图，response 步延迟到 SSE 层。"""

import pytest

from app.schemas.workflow import WorkflowState  # noqa: F401


async def _run_nr(query: str, **kw):
    from app.workflow.graph import run_workflow

    return await run_workflow(user_query=query, enable_checkpoint=False,
                              use_cache=False, no_response=True, **kw)


@pytest.fixture
def dyn(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", True)


def _has_step(state, cap: str) -> bool:
    return any(cap in sid for sid in state.completed_steps)


async def test_stream_chitchat_response_deferred(dyn):
    state = await _run_nr("你好呀")
    assert state.plan.get("stream_response") is True
    assert state.answer == ""          # response 交由 SSE 层生成
    assert len(state.completed_steps) == 1  # 仅 response（deferred 也记 completed）
    assert any(t.get("output_summary") == "deferred to SSE stream" for t in state.trace_steps)


async def test_stream_recommend_full_chain_no_answer(dyn):
    state = await _run_nr("推荐一款蓝牙耳机")
    assert state.plan  # planner 运行
    for cap in ("retrieval", "reranker", "evidence_check", "decision"):
        assert _has_step(state, cap), cap
    assert state.answer == ""          # 生成延迟到 SSE 层
    assert state.retrieved_products    # 商品已就绪供流式生成消费


async def test_stream_compare_uses_compare_retrieval(dyn):
    state = await _run_nr("对比airpods和huawei freebuds pro5")
    assert state.plan.get("meta", {}).get("compare_targets") == ["airpods", "huawei freebuds pro5"]
    assert _has_step(state, "compare_retrieval")
    assert "对比检索结果" in state.context_prompt  # 命中提示供 SSE 层 generate_stream 消费
    assert state.answer == ""


async def test_stream_flag_off_legacy_unchanged(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", False)
    state = await _run_nr("推荐一款蓝牙耳机")
    assert not state.plan              # legacy no_response 图无 planner
    assert state.answer == ""
    assert not any("Planner" in (t.get("agent_name") or "") for t in state.trace_steps)
