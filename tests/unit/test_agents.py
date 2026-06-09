"""Unit tests for V1 Agents."""

import pytest
from app.schemas.workflow import WorkflowState, Constraints, RetrievalPlan
from app.agents.router_agent import RouterAgent, _rule_based_parse
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.decision_agent import DecisionAgent
from app.agents.response_agent import ResponseAgent


class TestRouterAgent:
    def test_card(self):
        agent = RouterAgent()
        assert agent.card.name == "Router Agent"
        assert "intent_recognition" in agent.card.capabilities

    @pytest.mark.asyncio
    async def test_execute_recommend(self):
        agent = RouterAgent()
        state = WorkflowState(session_id="t1", user_query="推荐一款蓝牙耳机")
        result = await agent.execute(state)
        assert result.intent in ("recommend", "compare", "alternative", "risk_check", "compatibility_check")
        assert len(result.trace_steps) >= 1

    @pytest.mark.asyncio
    async def test_execute_risk_check(self):
        agent = RouterAgent()
        state = WorkflowState(session_id="t2", user_query="这个精华对敏感肌安全吗")
        result = await agent.execute(state)
        assert result.intent == "risk_check"
        assert "review" in result.retrieval_plan.channels

    def test_rule_based_parse_budget(self):
        result = _rule_based_parse("推荐一款500以内的蓝牙耳机")
        assert result["budget_max"] == 500.0
        assert result["category"] == "数码电子"


class TestRetrievalAgent:
    def test_card(self):
        agent = RetrievalAgent()
        assert agent.card.name == "Retrieval Agent"

    @pytest.mark.asyncio
    async def test_execute(self):
        agent = RetrievalAgent()
        state = WorkflowState(
            session_id="t1",
            user_query="蓝牙耳机",
            constraints=Constraints(category="数码电子"),
            retrieval_plan=RetrievalPlan(channels=["text"], category="数码电子", top_k=3),
        )
        result = await agent.execute(state)
        assert len(result.retrieved_products) > 0
        assert len(result.evidence_list) > 0
        assert result.trace_steps[-1]["status"] == "success"


class TestDecisionAgent:
    def test_card(self):
        agent = DecisionAgent()
        assert agent.card.name == "Decision Agent"

    @pytest.mark.asyncio
    async def test_execute(self):
        agent = DecisionAgent()
        state = WorkflowState(
            session_id="t1",
            user_query="蓝牙耳机",
            constraints=Constraints(category="数码电子"),
            retrieved_products=[
                {"product_id": "p_digital_007", "score": 18.6, "title": "Test"},
            ],
        )
        result = await agent.execute(state)
        assert len(result.decision_results) >= 0
        assert result.trace_steps[-1]["status"] == "success"


class TestResponseAgent:
    def test_card(self):
        agent = ResponseAgent()
        assert agent.card.name == "Response Agent"

    @pytest.mark.asyncio
    async def test_execute_empty(self):
        agent = ResponseAgent()
        state = WorkflowState(
            session_id="t1",
            user_query="蓝牙耳机",
            retrieved_products=[],
            decision_results=[],
        )
        result = await agent.execute(state)
        assert len(result.answer) > 0
        assert result.trace_steps[-1]["status"] in ("success", "fallback")
