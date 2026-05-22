"""V1 A2A-lite Dispatcher — Agent 间结构化消息分发。

V1 同进程内轻量通信：Agent 通过 AgentMessage + Artifact 交换结构化数据。
V2 扩展为标准 A2A Protocol（gRPC/HTTP）。
"""

from typing import Optional
from app.schemas.a2a import AgentMessage, Artifact


class A2ADispatcher:
    """A2A-lite 消息分发器 — 同进程内存队列。"""

    def __init__(self):
        self._messages: list[AgentMessage] = []
        self._cards: dict[str, dict] = {}

    def register_agent(self, agent_id: str, name: str, description: str = "",
                       capabilities: list[str] | None = None):
        self._cards[agent_id] = {
            "agent_id": agent_id, "name": name, "description": description,
            "capabilities": capabilities or [],
        }

    def send(self, from_agent: str, to_agent: str, action: str,
             payload: dict | None = None, artifacts: list[Artifact] | None = None) -> AgentMessage:
        import uuid
        msg = AgentMessage(
            message_id=f"msg_{uuid.uuid4().hex[:10]}",
            from_agent=from_agent, to_agent=to_agent, action=action,
            payload=payload or {}, artifacts=artifacts or [],
        )
        self._messages.append(msg)
        return msg

    def get_messages(self, limit: int = 50) -> list[AgentMessage]:
        return self._messages[-limit:]

    def get_agent_card(self, agent_id: str) -> Optional[dict]:
        return self._cards.get(agent_id)

    def list_agents(self) -> list[dict]:
        return list(self._cards.values())

    def create_artifact(self, artifact_type: str, producer: str,
                        content: dict, evidence_ids: list[str] | None = None,
                        confidence: float = 1.0) -> Artifact:
        import uuid
        return Artifact(
            artifact_id=f"art_{uuid.uuid4().hex[:10]}",
            artifact_type=artifact_type, producer_agent=producer,
            content=content, evidence_ids=evidence_ids or [],
            confidence=confidence,
        )


# 全局单例
_dispatcher = A2ADispatcher()


def get_dispatcher() -> A2ADispatcher:
    return _dispatcher
