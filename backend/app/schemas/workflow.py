"""V1 Workflow State — LangGraph Agent 编排的全局状态."""

from typing import Optional
from pydantic import BaseModel, Field


class SubQuery(BaseModel):
    """QU 语义拆分后的子查询（如“上衣/裤子/鞋”三路）"""
    role: str = ""                    # 子目标角色（上衣/裤子/鞋）
    query: str = ""                   # 检索友好词
    category: str | None = None
    budget_hint: float | None = None  # 总预算分配建议


class RetrievalPlan(BaseModel):
    """Router Agent 生成的检索计划"""
    channels: list[str] = Field(default_factory=list)  # ["text", "review", "policy", "compatibility"]
    category: str | None = None
    sub_category: str | None = None
    top_k: int = 10
    priority: str = "balanced"  # speed / coverage / balanced
    sub_queries: list[SubQuery] = Field(default_factory=list)  # QU V2 多目标拆分
    rating_min: float | None = None  # 口碑下限（avg_rating 服务端过滤，spec omni-harness D3）
    chunk_focus: str | None = None  # 聚焦块类型 rev/faq（原子检索：只搜评价/FAQ 块）


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
    gift_profile: dict | None = None  # QU V2 送礼画像 {recipient, occasion}，仅 gift 意图时有值


class TraceStep(BaseModel):
    """单个 Agent 执行步骤"""
    step_id: str = ""
    agent_name: str = ""
    action: str = ""
    input_summary: str = ""
    output_summary: str = ""
    latency_ms: int = 0
    status: str = "pending"  # pending / running / success / failed / skipped / fallback


class ToolExecution(BaseModel):
    """单次工具执行记录（填充 WorkflowState.skill_executions —— 遗留跨端契约字段名）。

    字段名（skill_name 等）保持遗留契约不变，供 Android SkillExecutionPanel / recommend 消费。
    """
    skill_name: str = ""
    category: str = ""
    args: dict = Field(default_factory=dict)
    status: str = "success"  # success / failed / skipped
    latency_ms: int = 0
    result_summary: str = ""


class WorkflowState(BaseModel):
    """LangGraph 工作流全局状态"""
    session_id: str = ""
    user_id: str = ""  # V2: 关联用户长期偏好记忆
    conversation_id: str = ""  # P0: 可恢复聊天线程
    mode: str = "standard"  # P2-1 三档派发: lite(跳LLM轻链路)/standard/max(动态编排)，替代 [FAST_MODE] magic string
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
    # 回答引用的商品 id（按入 prompt 顺序）——SSE 层据此置顶 products，
    # 保证自然语言回答与商品卡片列表强一致（spec §3）
    answer_cited_pids: list[str] = Field(default_factory=list)
    memory_trace: dict = Field(default_factory=dict)

    # 可观测性
    trace_steps: list[dict] = Field(default_factory=list)
    skill_executions: list[dict] = Field(default_factory=list)  # 遗留契约名: 内容为 ToolExecution（工具执行记录）
    harness_report: dict = Field(default_factory=dict)
    sufficiency_report: dict = Field(default_factory=dict)
    fallback_status: dict = Field(default_factory=dict)

    # 动态编排 (Phase 4+5: Planner / Supervisor / Reflect)
    plan: dict = Field(default_factory=dict)              # ExecutionPlan.model_dump()
    completed_steps: list[str] = Field(default_factory=list)
    reflect_count: int = 0

    # 性能计时
    timing: dict = Field(default_factory=dict)

    # 错误处理
    error: str | None = None
