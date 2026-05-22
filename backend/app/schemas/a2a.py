"""A2A-lite Agent Communication — AgentCard / AgentMessage / Artifact.

V1 轻量版：Agent 之间通过结构化消息协作，不实现完整 A2A 协议。
V2 扩展为标准 A2A Protocol。
"""

from pydantic import BaseModel, Field
from typing import Optional


class AgentCard(BaseModel):
    """Agent 身份和能力描述"""
    agent_id: str
    name: str
    description: str = ""
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)


class Artifact(BaseModel):
    """Agent 产出的结构化产物"""
    artifact_id: str
    artifact_type: str  # retrieval_result / decision_result / evidence_bundle / ...
    producer_agent: str
    content: dict = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class AgentMessage(BaseModel):
    """Agent 之间的标准化消息"""
    message_id: str = ""
    from_agent: str = ""
    to_agent: str = ""
    action: str = ""  # request / response / notify
    payload: dict = Field(default_factory=dict)
    artifacts: list[Artifact] = Field(default_factory=list)
    trace_step: dict = Field(default_factory=dict)
