"""V1 Workflow State — LangGraph Agent 编排的全局状态."""

from typing import Optional
from pydantic import BaseModel, Field


class SubQuery(BaseModel):
    """QU 语义拆分后的子查询（如“上衣/裤子/鞋”三路）"""
    role: str = ""                    # 子目标角色（上衣/裤子/鞋）
    query: str = ""                   # 检索友好词
    category: str | None = None
    budget_hint: float | None = None  # 总预算分配建议
    # V9 Router Plan：每个子目标保留完整的检索与交付意图，不让后续工具靠字符串猜测。
    entity_terms: list[str] = Field(default_factory=list)
    must_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    avoid_constraints: list[str] = Field(default_factory=list)
    evidence_focus: list[str] = Field(default_factory=list)
    answer_goal: str = ""
    ambiguity: str = ""


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
    # 单目标也采用与 sub_queries 一致的字段，供 shopping.search 一次调用直接消费。
    entity_terms: list[str] = Field(default_factory=list)
    must_constraints: list[str] = Field(default_factory=list)
    soft_preferences: list[str] = Field(default_factory=list)
    avoid_constraints: list[str] = Field(default_factory=list)
    evidence_focus: list[str] = Field(default_factory=list)
    answer_goal: str = ""
    ambiguity: str = ""


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


class Deliberation(BaseModel):
    """max 档 Plan-Execute 的计划状态（对齐 amap DeliberationState）。

    todos 每项形状：``{"id": "t1", "desc": "...", "done": False}``。
    """
    plan_status: str = ""  # "" | "in_progress" | "done"
    todos: list[dict] = Field(default_factory=list)

    def is_active(self) -> bool:
        return bool(self.todos)


class RetrievalGroup(BaseModel):
    """An independently owned user need inside a compound shopping request."""
    group_id: str = ""
    role: str = ""
    query: str = ""
    hard_constraints: dict = Field(default_factory=dict)
    product_ids: list[str] = Field(default_factory=list)
    evidence_product_ids: list[str] = Field(default_factory=list)
    status: str = "pending"  # pending / matched / missing / failed
    missing_reason: str = ""


class WorkflowState(BaseModel):
    """LangGraph 工作流全局状态"""
    session_id: str = ""
    user_id: str = ""  # V2: 关联用户长期偏好记忆
    conversation_id: str = ""  # P0: 可恢复聊天线程
    mode: str = "standard"  # P2-1 三档派发: lite(跳LLM轻链路)/standard/max(动态编排)，替代 [FAST_MODE] magic string
    user_query: str = ""
    user_query_original: str | None = None  # 保存原始 query（memory hints 注入前）
    # 迁移期兼容字段：只承载追问/检索阶段的短约束，不能写入工具全文，也不是最终
    # 回答模型的上下文来源。终稿统一由 ConversationContextAssembler 构建。
    context_prompt: str = ""
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
    retrieval_groups: list[RetrievalGroup] = Field(default_factory=list)
    structured_retrieval_report: dict = Field(default_factory=dict)
    # V9 每次 shopping.search 独立保存候选快照；深度思考的后续调用不得覆盖前一组。
    candidate_groups: list[dict] = Field(default_factory=list)
    candidate_trace: list[dict] = Field(default_factory=list)
    llm_filter_result: dict = Field(default_factory=dict)
    evidence_packs: dict[str, list[dict]] = Field(default_factory=dict)

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
    # 用户可见推荐简报：首选卡与答文共用的唯一商品集。
    primary_product_ids: list[str] = Field(default_factory=list)
    alternative_product_ids: list[str] = Field(default_factory=list)
    recommendation_brief: list[dict] = Field(default_factory=list)
    # 最终回答只消费 ConversationContextAssembler 生成的单一投影。
    # manifest 仅用于服务端审计/评测，绝不能当作模型输入或客户端推理过程。
    answer_context: str = ""
    answer_context_manifest: dict = Field(default_factory=dict)
    scoring_trace: dict = Field(default_factory=dict)
    # 商品实体解析：指定商品/问欧米/拍照场景会以此限制后续候选范围。
    product_resolution: dict = Field(default_factory=dict)
    retrieval_scope: str = "broad"  # broad / exact_product / product_family / ambiguous
    resolved_product_ids: list[str] = Field(default_factory=list)
    # 单品深度档案：完整内容留在 state，避免被 ReAct 工具消息截断。
    focus_product_id: str = ""
    product_dossiers: dict[str, dict] = Field(default_factory=dict)
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

    # ---- ReAct 图循环状态（原 OmniAgent.run_events 的函数局部变量）----
    # 图节点之间只能经 state 传递，所以这些必须从局部变量上提。
    messages: list[dict] = Field(default_factory=list)  # OpenAI 协议对话历史
    round_no: int = 0
    # 防循环：已出现的调用签名。用 list 而非 set —— state 要能序列化进
    # LangGraph checkpointer，set 不是 JSON 类型。
    call_signatures: list[str] = Field(default_factory=list)
    pending_tool_calls: list[dict] = Field(default_factory=list)
    # ---- 受控工具运行时（借鉴 pi 的 tool-call ledger / hook 边界）----
    # 账本是请求级可序列化审计记录；模型只接收由 runtime 压缩过的工具结果。
    tool_ledger: list[dict] = Field(default_factory=list)
    tool_budget: dict = Field(default_factory=dict)
    tool_runtime_stop_reason: str = ""
    tool_runtime_mode: str = ""  # "normal" | "deep"，为空时兼容旧调用方
    # 仅在受控 ToolRuntime 的隔离快照中使用；关联 Router 分组与工具结果。
    # 不进入模型上下文或客户端协议。
    tool_runtime_group_id: str = ""
    answer_draft: str = ""  # 循环内产出的终稿草案（finalize 才落到 answer）
    # 工具产出的交互动作（sku_option 规格选择 / address_form / quick_reply）。
    # 必须逐轮累计并透传给前端：不透传会让多规格商品加购时的规格选择按钮消失，
    # 用户只能约定俗成地用纯对话选。
    tool_actions: list[dict] = Field(default_factory=list)

    # ---- LLM 显式选品（shopping.display 的产出）----
    # 卡片与答文候选集的唯一真源。为空表示 LLM 未选品，下游按既有逻辑降级
    # （SSE 层从终稿反推引用集）。
    selected_products: list[dict] = Field(default_factory=list)
    selected_reason: str = ""

    # ---- 路由决策字段（节点写、路由函数只读，对齐 amap）----
    transition: str = ""      # "" | "next_turn" | "finalize"
    response_route: str = ""  # "" | "tool_use" | "completion"
    deliberation: Deliberation = Field(default_factory=Deliberation)

    # 错误处理
    error: str | None = None
