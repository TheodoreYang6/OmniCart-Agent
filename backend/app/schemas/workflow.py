"""V1 Workflow State — LangGraph Agent 编排的全局状态."""

from typing import Optional
from pydantic import BaseModel, Field


class RetrievalPlan(BaseModel):
    """Router Agent 生成的检索计划"""
    channels: list[str] = Field(default_factory=list)  # ["text", "review", "policy", "compatibility"]
    category: str | None = None
    sub_category: str | None = None
    top_k: int = 10
    priority: str = "balanced"  # speed / coverage / balanced


class Constraints(BaseModel):
    """从用户查询中抽取的结构化约束"""
    category: str | None = None
    sub_category: str | None = None
    budget_max: float | None = None
    budget_min: float | None = None
    scenario: str | None = None
    must_tags: list[str] = Field(default_factory=list)
    exclude_tags: list[str] = Field(default_factory=list)


class TraceStep(BaseModel):
    """单个 Agent 执行步骤"""
    step_id: str = ""
    agent_name: str = ""
    action: str = ""
    input_summary: str = ""
    output_summary: str = ""
    latency_ms: int = 0
    status: str = "pending"  # pending / running / success / failed / skipped / fallback


class WorkflowState(BaseModel):
    """LangGraph 工作流全局状态"""
    session_id: str = ""
    user_id: str = ""  # V2: 关联用户长期偏好记忆
    user_query: str = ""
    image_url: str | None = None

    # Router 输出
    intent: str = ""  # recommend / compare / risk_check / compatibility_check / alternative
    constraints: Constraints = Field(default_factory=Constraints)
    retrieval_plan: RetrievalPlan = Field(default_factory=RetrievalPlan)

    # Visual 输出
    visual_result: dict | None = None

    # Retrieval 输出
    retrieved_products: list[dict] = Field(default_factory=list)
    evidence_list: list[dict] = Field(default_factory=list)

    # Decision 输出
    decision_results: list[dict] = Field(default_factory=list)

    # Response 输出
    answer: str = ""

    # 可观测性
    trace_steps: list[dict] = Field(default_factory=list)
    skill_executions: list[dict] = Field(default_factory=list)
    harness_report: dict = Field(default_factory=dict)
    sufficiency_report: dict = Field(default_factory=dict)
    fallback_status: dict = Field(default_factory=dict)

    # 错误处理
    error: str | None = None
