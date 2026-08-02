"""内置 Agent 清单 —— 供 AgentManager 装配（替换 graph.py 硬编码 new）。

返回 {name: agent} 映射。延迟导入各 Agent，避免在包加载期触发重依赖 / 潜在环。
"""

from __future__ import annotations

from typing import Any

__all__ = ["builtin"]


def builtin(repo: Any = None) -> dict[str, Any]:
    """返回工作流所需的全部 Agent 实例（按 graph 节点名索引）。"""
    from app.agents.decision_agent import DecisionAgent
    from app.agents.response_agent import ResponseAgent
    from app.agents.retrieval_agent import RetrievalAgent
    from app.agents.router_agent import RouterAgent
    from app.agents.visual_agent import VisualAgent

    return {
        "router": RouterAgent(),
        "visual": VisualAgent(),
        "retrieval": RetrievalAgent(repo=repo),
        "decision": DecisionAgent(repo=repo),
        "response": ResponseAgent(),
    }
