"""QU V2 bundle 端到端（MOCK + 动态编排 flag on）+ Loop 拆分路径 + 评测脚本冒烟。"""

import pytest

from app.schemas.workflow import WorkflowState


@pytest.fixture
def dyn(monkeypatch):
    monkeypatch.setattr("app.core.config.ENABLE_DYNAMIC_ORCHESTRATION", True)


async def test_bundle_e2e_multi_query_grouped_answer(dyn):
    """"上衣裤子鞋搭一套" → MockChat QU 拆 3 路 → multi_query 分组检索 → 分组 context → 出答案。"""
    from app.workflow.graph import run_workflow

    state = await run_workflow(user_query="我想买衣服，上衣和裤子鞋给我搭配一套",
                               enable_checkpoint=False)
    assert state.plan.get("intent") == "bundle"
    assert any("multi_query_retrieval" in sid for sid in state.completed_steps)
    assert "[分组检索]" in (state.context_prompt or "")
    assert state.answer
    # 三组命中统计均在分组 context（MOCK 嵌入下三路商品高度重叠，去重后 group_role
    # 可能归并到首组；多组合并正确性由 test_multi_query_retrieval 单测覆盖）
    for role in ("上衣", "裤子", "鞋"):
        assert f"{role}:" in state.context_prompt
    assert any(p.get("group_role") for p in state.retrieved_products)


async def test_bundle_loop_path_multi_search(monkeypatch):
    """OmniAgent 路径：QU 注入子目标 → MockProvider 逐目标发多个 shopping.search。"""
    from app.agents.omni_agent import OmniAgent
    from app.framework.tools import ToolContext

    state = WorkflowState(user_id="u_qu", user_query="上衣裤子鞋搭配一套")
    ctx = ToolContext(user_id="u_qu", state=state)
    events = []
    async for ev in OmniAgent().run_events("上衣裤子鞋搭配一套", ctx):
        events.append(ev)
    search_calls = [e for e in events if e["type"] == "tool_result" and e["tool"] == "shopping.search"]
    assert len(search_calls) >= 2  # 逐子目标分别检索（上衣/裤子/鞋）
    assert events[-1]["type"] == "done"


async def test_qu_eval_script_smoke(tmp_path, monkeypatch):
    """评测脚本 MOCK 冒烟：跑 8 条出报告结构（真实 key 下产出真基线）。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import eval_qu

    report = await eval_qu.run(limit=8)
    assert report["cases"] == 8
    assert 0 <= report["intent_acc"] <= 1
    assert "details" in report and len(report["details"]) == 8
