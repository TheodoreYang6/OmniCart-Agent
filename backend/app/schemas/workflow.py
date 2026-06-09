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
    scenario_keywords: list[str] = Field(default_factory=list)  # LLM 动态生成的场景特征词
    spec_keywords: list[str] = Field(default_factory=list)      # LLM 提取的用户关心的规格词
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
    conversation_id: str = ""  # P0: 可恢复聊天线程
    user_query: str = ""
    user_query_original: str | None = None  # 保存原始 query（memory hints 注入前）
    context_prompt: str = ""  # FollowUpEngine 上下文提示（仅 Response Agent 使用，不污染检索/精排）
    image_url: str | None = None

    # Router 输出
    intent: str = ""  # recommend / compare / risk_check / compatibility_check / alternative
    constraints: Constraints = Field(default_factory=Constraints)
    retrieval_plan: RetrievalPlan = Field(default_factory=RetrievalPlan)

    # Visual 输出
    visual_result: dict | None = None
    visual_matched_pids: list[str] = Field(default_factory=list)  # 精确匹配的商品ID，钉在推荐顶部

    # Retrieval 输出
    retrieved_products: list[dict] = Field(default_factory=list)
    evidence_list: list[dict] = Field(default_factory=list)

    # Decision 输出
    decision_results: list[dict] = Field(default_factory=list)
    # V2: LLM Evidence Evaluation 输出
    llm_overall_analysis: str = ""
    llm_user_warnings: list[str] = Field(default_factory=list)

    # Clarification (追问式品类筛选)
    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_options: list[dict] = Field(default_factory=list)

    # Response 输出
    answer: str = ""

    # Memory Trace (P0: 空壳, P2: 填充)
    used_memories: list[dict] = Field(default_factory=list)
    blocked_memories: list[dict] = Field(default_factory=list)
    memory_trace: dict = Field(default_factory=dict)

    # 可观测性
    trace_steps: list[dict] = Field(default_factory=list)
    skill_executions: list[dict] = Field(default_factory=list)
    harness_report: dict = Field(default_factory=dict)
    sufficiency_report: dict = Field(default_factory=dict)
    fallback_status: dict = Field(default_factory=dict)

    # 性能计时
    timing: dict = Field(default_factory=dict)

    # 错误处理
    error: str | None = None
