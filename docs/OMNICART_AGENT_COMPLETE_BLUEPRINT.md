# OmniCart Agent Competition Edition

版本：v5.0  
项目定位：字节跳动 Agent 挑战赛参赛项目  
中文定位：OmniCart Agent 是一个基于 Qwen 全栈模型、多模态证据 RAG、Multi-Agent 编排、Skill 工具化能力层与可验证决策机制的电商购物决策 Agent。  
English Positioning: OmniCart Agent is a Qwen-powered multimodal shopping decision agent that combines visual understanding, evidence-grounded RAG, skill-based tool use, A2A-lite collaboration, and explainable decision scoring for verifiable e-commerce recommendation.

## 1. 项目定位与愿景

OmniCart Agent 不是普通电商客服机器人，也不是简单商品问答系统，而是面向“购买前决策”的 Android 原生电商智能导购客户端。它以传统购物 App 的四个底部入口承载完整购物链路，并将原有多模态购物决策 Agent 保留为核心页面“豆仔智能”。

它帮助用户在购买前完成：

- 商品识别
- 需求理解
- 商品检索
- 商品对比
- 兼容性判断
- 评论风险总结
- 政策规则检索
- 替代推荐
- 可解释购买建议
- 商品浏览、商品详情、购物车管理和个人偏好管理

系统不再把 Agent 看作一个实时聊天窗口，而是把一次购物咨询建模为一条可控制、可审计、可回放、可验证的多 Agent 决策链路。同时，Android 客户端提供商品展示、豆仔智能、购物车、个人中心四个主页面，让项目从单页智能问答 Demo 升级为可交付的智能电商客户端。

参赛版的目标是做出一个能跑、能测、能展示、能解释、能回放、能验证的项目，而不是覆盖完整企业客服、售后、订单、支付、账号操作和真实交易系统。

项目核心问题是：

```text
这个商品适不适合我？
为什么适合或不适合？
有哪些风险？
有没有更合适的替代品？
如果我的约束变化，推荐会如何变化？
这些判断依据来自哪些证据？
系统的决策过程能不能被复盘和验证？
```

最终形态不是“会聊天的导购”，也不是普通购物 App，而是“具备完整购物链路的 Android 原生智能导购 Agent 产品”。豆仔智能仍是核心创新入口，商品展示、购物车和个人中心为用户提供真实可用的电商使用闭环。

Android App 固定为四个主页面：

| 主页面 | 定位 | 边界 |
|---|---|---|
| 商品展示 | 基础电商能力 | 展示数据集商品、搜索筛选、商品详情、加入购物车、问豆仔。 |
| 豆仔智能 | 核心 AI Agent 页面 | 承载文本导购、图片导购、证据 RAG、决策评分、Trace、Harness 和受控购物车 action。 |
| 购物车 | 基础电商能力 | 管理商品数量、选择状态、合计价格和模拟结算。 |
| 个人中心 | 基础电商能力 | 管理登录状态、用户信息、收货地址和个人偏好。 |

豆仔智能可以通过受控 action 将推荐商品加入购物车，但不能直接操作数据库；付款只能做 mock checkout / 模拟结算，不接入真实支付。

## 2. 参赛版范围边界

### 2.1 V1 必做能力

V1 是参赛必须完成版本，聚焦购物决策主链路：

- 文本导购
- Android 底部四 Tab 主框架：商品展示、豆仔智能、购物车、个人中心
- 商品展示、商品搜索、商品详情和基础购物车能力
- Demo 用户、轻量登录、地址和用户偏好管理
- 登录、用户信息、收货地址、个人偏好与 `user_id` 绑定
- 豆仔智能通过受控 Agent Action 将推荐商品加入购物车
- 模拟结算 / 模拟订单，不接入真实支付
- 商品图片或商品截图上传
- Android Native Client 作为 V1 参赛主交付端
- Kotlin + Jetpack Compose + Material 3 移动端交互展示
- Qwen-VL / Qwen3-VL 图片与截图解析
- 5 个核心 Agent Workflow
- Context Compiler
- Preference Memory Card
- Skill Registry
- MCP-compatible ToolManager
- A2A-lite AgentMessage / Artifact
- Adaptive Multimodal Evidence Retrieval
- Evidence Sufficiency Checker
- Evidence Graph Lite
- Visual Evidence Grounding
- Constraint Solver
- Counterfactual Recommendation
- Tool Governance / MCP Security Lite
- Declarative workflow.yaml
- Tiered Multimodal Fallback
- Hierarchical Shopping Knowledge Index
- Qwen Reranker 精排
- Explainable Decision Scoring
- Decision Harness 验证
- State Checkpoint
- Async Retrieval
- Response Guard
- Evidence Panel
- Agent Trace Panel
- Skill Execution Panel
- Harness Validation Panel
- Demo Pack / Mock Mode
- Baseline 对比评测

以上 V1 能力都采用轻量可落地实现，不做复杂企业级平台。

### 2.2 V1 不做主线的能力

以下能力不作为 V1 必做项，避免参赛版范围膨胀：

- Web 前端 / Next.js / React / TailwindCSS 主线交付
- WebView、React Native、Expo、Flutter 等跨平台或 Web 套壳客户端
- iOS Swift + SwiftUI 客户端（仅作为 V2/V3 可选扩展规划）
- 标准 MCP Server / Client
- 标准 A2A 分布式协议
- Computer Use / Browser Use
- 语音导购
- 完整 Neo4j GraphRAG
- 跨会话长期记忆
- Human-in-the-loop 审批系统
- Langfuse / Phoenix 完整观测平台
- 在线学习 / Bandit 排序
- 订单、支付、退款、售后全流程
- 复杂消息队列和企业级数据链路

### 2.3 V2 / V3 扩展能力

V2 / V3 可作为答辩扩展规划展示：

- 标准 MCP Server / Client
- 标准 A2A 协议
- Computer Use / Browser Use
- Qwen-Omni 语音导购
- Neo4j GraphRAG
- 用户长期偏好记忆
- 更复杂的 Context Engineering
- 在线反馈学习 / Bandit 排序
- Langfuse / Phoenix 可观测性
- 更大规模商品数据接入
- 更完整 Evaluation Dashboard

## 3. 核心创新点

### 3.1 Qwen-only Model Stack

统一使用 Qwen 系列模型完成对话生成、意图理解、视觉理解、文本向量化、多模态向量化、重排序与后续语音扩展。工程上通过 Model Gateway 调用能力名，避免在业务逻辑中写死具体模型名称。

### 3.2 Multimodal Evidence RAG

构建文本证据链、视觉证据链和结构化证据链，使推荐结果绑定 `evidence_ids`，降低幻觉和无依据推荐。

### 3.3 Context Engineering / Context Compiler

不把检索到的商品、评论、政策、图片解析结果无序塞给大模型，而是把用户意图、约束、视觉结果、证据、评分、风险、偏好记忆和 Harness 状态编译成结构化上下文。

### 3.4 Workflow-controlled Multi-Agent

采用固定购物决策 Workflow 控制主流程，局部由 Agent 动态规划和工具选择，兼顾控制性与灵活性。

### 3.5 Skill-based Agent Capability Layer

将工具调用封装为面向任务的 Skill，例如商品截图解析、评论风险挖掘、政策检查、兼容性判断和决策评分。

### 3.6 MCP-compatible Tool Layer

V1 实现 MCP-compatible ToolManager，对工具进行统一描述、统一调用、统一日志、统一返回格式；V2 再扩展为标准 MCP Server。

### 3.7 A2A-lite Agent Communication

V1 实现轻量 AgentCard、AgentMessage、Artifact 结构化通信格式；V2 再扩展为标准 A2A 协议。

### 3.8 Adaptive Retrieval + Evidence Sufficiency

由 Router Agent 根据任务类型生成 Retrieval Plan，动态决定检索链、Top-K 和证据需求。Response 前检查证据是否足够，不足则继续检索或澄清。

### 3.9 Constraint Solver + Decision Scoring

硬约束先过滤，软偏好再评分。预算、品类、接口兼容、航空规则、MacBook 功率等硬约束优先于加权打分。

### 3.10 Decision Harness + Demo Pack

用 Harness 验证 Schema、证据、评分、约束、政策、风险和可回放性；用 Demo Pack / Mock Mode 保证比赛现场稳定演示。

## 4. 总体技术架构

总体流程：

```text
用户文本/图片/截图输入
  -> Workflow Engine 创建 AgentState
  -> Router Agent 识别任务、约束和 Retrieval Plan
  -> Preference Memory Card 合并会话偏好
  -> Visual Agent 解析图片/截图并生成 Visual Evidence
  -> Skill Layer 编排任务能力
  -> MCP-compatible ToolManager 调用原子工具
  -> Adaptive Retrieval 执行多模态证据检索
  -> Evidence Sufficiency Checker 检查证据是否足够
  -> Evidence Graph Lite 解释关系路径
  -> Constraint Solver 执行硬约束判断
  -> Qwen Reranker 精排候选
  -> Decision Agent 计算可解释评分
  -> Decision Harness 验证证据、约束、评分和风险
  -> Context Compiler 编译 Response 上下文
  -> Response Agent 生成证据绑定回答
  -> Response Guard 最终守门
  -> Android 原生客户端展示 Product Cards + Evidence + Trace + Skill + Harness + Context
```

V1 核心技术栈：

| 层级 | 技术选择 | 解决的问题 |
|---|---|---|
| Android Client | Kotlin / Jetpack Compose / Material 3 | V1 参赛主交付端，提供商品展示、豆仔智能、购物车、个人中心四 Tab，并展示商品卡片、证据、评分、Trace、Skill、Harness、Context |
| Backend | FastAPI | 提供推荐、上传、Demo、评测、用户、商品、购物车、地址、偏好和受控 Agent Action API |
| Agent Orchestration | LangGraph | 固定购物决策 Workflow 与状态流转 |
| Runtime | 自研轻量 Agent Runtime | 管理 AgentState、Checkpoint、Skill、Tool、Harness |
| Model Layer | Qwen-only Model Gateway | 统一调用对话、视觉、embedding、rerank 能力 |
| Vector Database | Qdrant | 存储商品文本、评论、FAQ、图片或视觉描述向量 |
| Structured Store | PostgreSQL / SQLite / JSON | 存储商品、评论、政策、兼容性规则、用户、购物车、地址、偏好、模拟订单和轻量图关系 |
| Cache | Redis | 缓存视觉解析、检索结果和 Demo Pack |
| Data Processing | Python scripts | 构建索引、导入数据、运行评测 |

V1 明确废弃 Web 主线方案，不再使用 Web、WebView、Next.js、React、TailwindCSS、React Native、Expo 或 Flutter 作为最终交付端。调试优先使用 FastAPI Swagger、Postman、scripts 和 Android Demo Mode，不再规划 Web debug dashboard。
| Deployment | Docker Compose | 本地一键运行和比赛演示 |

V1 不引入复杂分布式系统。所有异步协作优先使用 Python `asyncio`，所有工具输出统一为结构化 JSON。

## 5. Agent Runtime Architecture

### 从聊天式 Agent 到可验证决策系统

OmniCart Agent 不采用“一个 Prompt + 一个聊天窗口”的简单模式，而是设计为一个可控制、可审计、可回放、可验证的 Agent Runtime。

用户的一次购物咨询会被转换为一条带状态、带证据、带评分、带工具调用记录、带验证结果的决策链路。

Runtime 包含以下层：

### 5.1 Workflow Layer

负责规定购物决策主流程，确保任务不失控。

固定流程：

```text
route -> visual_parse -> retrieval -> sufficiency_check -> decision -> harness_validation -> context_compile -> response -> response_guard
```

Workflow 决定“先做什么、后做什么、哪些节点必须经过验证”。Agent 只能在允许的节点内做局部规划。

### 5.2 Router Layer

负责识别用户意图，生成局部执行计划和 Retrieval Plan。

它会判断：

- 是否需要视觉解析
- 是否需要兼容性检查
- 是否需要政策检索
- 是否需要评论风险挖掘
- 是否需要二次检索
- 是否需要多轮澄清

### 5.3 Agent Layer

包含 5 个核心 Agent：

- Router Agent
- Visual Agent
- Retrieval Agent
- Decision Agent
- Response Agent

每个 Agent 接收结构化 AgentMessage，输出 Artifact，不直接把自然语言当作跨 Agent 通信格式。

### 5.4 Skill Layer

封装面向任务的组合能力。

例如 `flight_powerbank_check` 可以组合：

```text
visual_parse + spec_extract + policy_lookup + compatibility_check + review_risk_search + decision_score
```

Skill 是可注册、可复用、可验证的能力模块。

### 5.5 Tool Layer

通过 MCP-compatible ToolManager 统一管理原子工具。

原子工具包括：

- 商品文本检索
- 图片检索
- 评论检索
- 政策检索
- 兼容性规则查询
- 结构化过滤
- 评分计算
- 证据校验
- Demo Replay

### 5.6 State Layer

维护：

- AgentState
- Preference Memory Card
- Checkpoint
- Stateful Shopping Decision Tree

V1 保存关键节点状态：

- after_visual_parse
- after_retrieval
- after_decision
- after_response

### 5.7 Context Layer

负责把用户 query、constraints、visual_result、evidence_list、decision_results、risk_factors、Preference Memory Card 和 Harness 状态编译为 Response Agent 可用的结构化上下文。

### 5.8 Harness Layer

负责验证、回放和评测。

它检查：

- schema 是否正确
- evidence_ids 是否存在
- 分数是否按公式计算
- 约束是否满足
- 政策问题是否引用政策证据
- 风险问题是否包含风险提醒
- Demo Pack 是否可回放

### 5.9 Presentation Layer

通过 Android 原生客户端展示：

- Bottom Navigation 四个主入口
- 商品展示
- 豆仔智能
- 购物车
- 个人中心
- Product Cards
- ChatScreen
- Context Panel
- Retrieval Plan Panel
- Evidence Panel
- Visual Evidence Viewer
- Evidence Graph Path
- Agent Trace
- Skill Execution
- Harness Validation

Presentation Layer 只负责交互与展示：采集文本输入、选择或预览图片、调用后端 API、渲染后端返回的商品、证据、Trace、Skill、Harness 和 fallback 状态。复杂推理、RAG、Agent Workflow、Decision Scoring 与 Harness 校验都在后端完成。

Android 客户端主框架：

| Tab | 页面 | 定位 |
|---|---|---|
| 商品展示 | ProductHomeScreen | 浏览数据集商品、搜索筛选、查看商品详情、加入购物车、进入豆仔智能咨询当前商品。 |
| 豆仔智能 | DouzaiChatScreen | 原多模态购物决策 Agent 核心页面，完成文本导购、图片导购、商品对比、风险总结、兼容性判断、政策检索和可解释推荐。 |
| 购物车 | CartScreen | 管理已选商品，支持增删改数量、多选、全选、价格合计、模拟结算和展示“由豆仔推荐加入”。 |
| 个人中心 | ProfileScreen | 展示 Demo 用户、登录状态、用户信息、地址、设备、预算、品牌偏好和避雷项。 |

### 5.10 Commerce Service Layer

基础电商能力是为了让 OmniCart Agent 更像真实可交付产品，不改变后端 Agent Runtime 主架构，也不能喧宾夺主。

V1 允许新增轻量 Commerce Service：

- User：用户注册、登录、当前用户、Demo 用户、token 鉴权、用户偏好记录。
- Product：商品列表、商品详情、商品搜索、商品分类筛选，读取数据集中已有商品信息。
- Cart：查询购物车、加入购物车、修改数量、删除商品、多选、全选、模拟结算、豆仔智能加入购物车。
- Address：查询、新增、编辑、删除、设置默认收货地址。
- Preference：查询和更新用户偏好，与 Preference Memory Card 对齐。
- Agent Action：豆仔智能通过结构化 action 发起受控购物车操作，例如 `add_to_cart`、`remove_from_cart`、`update_cart_quantity`。

Agent 不直接操作数据库。所有购物车动作必须通过后端受控 Tool / Service 完成，并写入 Trace 或消息记录。比赛版不接入真实支付，只支持 mock checkout / 模拟付款 / 模拟订单。
用户信息、地址、偏好、购物车和模拟订单必须绑定 `user_id`，避免 Demo 用户、登录用户和后续多用户数据混淆。

### 5.11 自动化边界

OmniCart Agent 的自动化边界由可验证性决定。

凡是预算、参数、兼容性、政策规则、评论证据等可验证任务，交给 Agent 自动完成；缺乏证据支撑的主观判断必须降级为澄清问题或低置信度提示。

## 6. 控制-信任设计原则

在 Agent 系统中，自动化程度越高，越需要可验证机制约束其行为。

OmniCart Agent 采用“高控制 + 高可信”的设计路线：

- 底层购物决策流程由 Workflow 固定
- 关键节点由 Agent 动态决策
- 所有推荐结论必须经过 Evidence Guard、Constraint Solver、Decision Scoring、Harness Validation 和 Response Guard 检查

明确约束：

- 不采用完全开放式 ReAct
- 不让 LLM 随意决定最终推荐
- 不允许 Response Agent 生成没有证据支撑的购买结论
- 不允许 Tool 返回自然语言黑盒结果，工具输出必须是结构化 JSON
- 不允许风险类问题缺少风险提醒
- 不允许政策类问题缺少政策证据
- 不允许硬约束失败商品排在最终推荐首位

### ReAct / Plan / Workflow 的关系

OmniCart Agent 采用 Workflow-controlled Agent Execution：

- Workflow 负责固定购物决策主流程
- Plan 由 Router Agent 针对当前用户任务生成局部执行计划
- ReAct 只在 Retrieval Agent 的受限工具集合中使用，用于动态选择检索工具
- Response Agent 不负责自由决策，只负责基于 `evidence_ids` 和 `DecisionResult` 生成解释

这种设计能让项目既有 Agent 的灵活性，又能在比赛现场清楚解释每一步为什么可控。

## 7. Qwen-only Model Stack

参赛版宣传上采用 Qwen-only Model Stack。工程实现上通过 Model Gateway 保持模型可插拔，避免具体 API 名称变化导致系统不可用。

### 7.1 能力映射

| 能力名 | 用途 | 默认 Qwen 能力 |
|---|---|---|
| `chat_generation` | 多轮对话、推荐解释、最终回答生成 | Qwen-Plus / Qwen-Max |
| `intent_understanding` | 购物意图识别、预算/品类/品牌/用途/约束抽取 | Qwen-Plus / Qwen-Max |
| `visual_understanding` | 商品图、详情页截图、参数图、对比图理解 | Qwen-VL / Qwen3-VL |
| `text_embedding` | 商品标题、参数、评论、FAQ、政策文本向量化 | Qwen3-Embedding |
| `vision_embedding` | 商品图片、截图、多模态内容向量化 | Qwen multimodal embedding capability |
| `text_reranking` | 文本候选结果精排 | Qwen3-Reranker |
| `vision_reranking` | 图文候选结果精排 | Qwen multimodal reranking capability |
| `voice_interaction` | 后续语音导购扩展 | Qwen-Omni，仅 V2 可选 |

### 7.2 Fallback 策略

`vision_embedding` 如果接口不可用：

```text
Qwen-VL 视觉解析结果 -> 结构化视觉文本 -> Qwen3-Embedding
```

`vision_reranking` 如果接口不可用：

```text
规则分数 + 文本 reranker
```

模型 API 失败时：

```text
缓存结果 -> Demo Pack -> 可解释降级提示
```

### 7.3 Model Gateway 伪代码

业务代码只调用能力名：

```python
model = model_gateway.get_model("visual_understanding")
result = model.invoke(image, prompt)

embedder = model_gateway.get_model("text_embedding")
vectors = embedder.embed(texts)

reranker = model_gateway.get_model("text_reranking")
ranked = reranker.rerank(query, candidates)
```

不要在业务逻辑中直接写死具体模型名称。

## 8. Multi-Agent 架构设计

V1 只保留 5 个核心 Agent。每个 Agent 都有明确输入、输出、Skill、Tool、Artifact、可验证性和失败处理。

### 8.1 Router Agent

职责：

- 判断用户任务类型
- 识别文本导购、图片导购、商品对比、多轮追问、兼容性判断、风险咨询等意图
- 提取预算、品类、品牌、用途、设备型号、使用场景、限制条件
- 生成 Retrieval Plan
- 决定是否调用 Visual Agent、Retrieval Agent、Decision Agent 等

输入：

- user_query
- image_url
- session_context
- Preference Memory Card

输出：

- intent
- constraints
- local_plan
- retrieval_plan
- required_skills

可调用 Skill：

- product_retrieve
- policy_check
- compatibility_check

可调用 Tool：

- none by default，Router 只做规划，不直接检索

生成 Artifact：

- `RoutingPlan`
- `RetrievalPlan`

是否可验证：

- 可验证。检查 intent、constraints、retrieval_plan 和 required_skills 是否符合 schema。

失败处理：

- 如果意图不明确，生成澄清问题。
- 如果缺少关键参数，进入低置信度路径。

### 8.2 Visual Agent

职责：

- 处理用户上传的商品图、详情页截图、参数图、对比图
- 调用 Qwen-VL / Qwen3-VL 解析商品名称、品牌、价格、参数、卖点、接口、容量、功率、风险提示
- 生成字段级 Visual Evidence
- 将图片结果结构化为 `visual_result`

输入：

- image_url
- user_query
- RoutingPlan

输出：

- visual_result
- visual_evidence
- fallback_status

可调用 Skill：

- product_visual_parse

可调用 Tool：

- visual_parse
- evidence_validator

生成 Artifact：

- `VisualResult`
- `VisualEvidenceList`

是否可验证：

- 部分可验证。可验证字段完整性、置信度和 evidence_refs。

失败处理：

- 如果置信度低，触发澄清。
- 如果图片解析失败，进入 Tiered Multimodal Fallback。

### 8.3 Retrieval Agent

职责：

- 执行 Adaptive Multimodal Evidence RAG
- 包含文本召回、图片召回、评论召回、FAQ/政策召回、结构化属性过滤、兼容性规则检索
- 输出候选商品、证据列表、风险证据、政策证据

输入：

- intent
- constraints
- visual_result
- retrieval_plan
- user_query

输出：

- retrieved_products
- evidence_list
- tool_call_records
- evidence_sufficiency_result

可调用 Skill：

- product_retrieve
- review_risk_mining
- policy_check
- compatibility_check

可调用 Tool：

- product_text_search
- product_image_search
- review_search
- faq_policy_search
- compatibility_rule_query
- structured_filter

生成 Artifact：

- `RetrievalResult`
- `EvidenceSufficiencyResult`

是否可验证：

- 可验证。检查证据存在性、工具返回 schema、召回结果是否带 source。

失败处理：

- 单路检索失败不阻断整体流程。
- 无证据时返回低置信度结果，不强行推荐。
- 证据不足时触发 retrieve_more 或 ask_clarification。

### 8.4 Decision Agent

职责：

- 执行 Constraint Solver
- 对候选商品进行决策评分
- 综合预算匹配、场景匹配、参数匹配、评论可信度、视觉相似度、库存/可用性和风险惩罚
- 输出排序结果、评分明细、推荐理由、风险因素、反事实解释和替代商品

输入：

- retrieved_products
- evidence_list
- constraints
- visual_result
- Preference Memory Card

输出：

- constraint_results
- decision_results
- counterfactual_explanations

可调用 Skill：

- decision_score

可调用 Tool：

- decision_score_calculator
- evidence_validator

生成 Artifact：

- `DecisionResultList`
- `ConstraintResultList`

是否可验证：

- 可验证。检查 `final_score` 是否由公式计算，检查 hard constraints 是否生效。

失败处理：

- 如果评分字段缺失，使用保守默认值并标注低置信度。
- 如果风险证据缺失，不允许输出“强推荐”。

### 8.5 Response Agent

职责：

- 基于 Context Compiler 输出的结构化上下文生成最终回答
- 每个推荐必须包含推荐理由、满足的需求、风险提醒、不适合人群、对比优势、引用证据
- 至少包含一个“如果……那么……”形式的反事实解释
- 控制回答风格，避免无证据生成和夸大推荐

输入：

- compiled_context
- decision_results
- evidence_list
- trace_steps
- harness_report

输出：

- final_response

可调用 Skill：

- none by default，Response 只解释，不再执行检索或评分

可调用 Tool：

- evidence_validator

生成 Artifact：

- `FinalResponse`

是否可验证：

- 可验证。检查回答中的证据引用、风险提醒、政策引用和评分解释一致性。

失败处理：

- 如果 Response Guard 失败，返回结构化错误或低置信度回答。
- 如果缺少关键证据，提示用户补充信息。

## 9. A2A-lite Agent Communication

V1 参赛版中 5 个 Agent 位于同一个后端服务内，因此不实现完整分布式 A2A 协议，而是实现 A2A-lite 结构化通信机制。

A2A-lite 的目标是让 Agent 之间不再传递随意自然语言，而是通过 AgentCard、AgentMessage 和 Artifact 传递结构化任务与结果。

### 9.1 AgentCard 示例

```json
{
  "agent_id": "visual_agent",
  "name": "Visual Agent",
  "description": "解析商品图片、截图和详情页图文信息",
  "capabilities": [
    "image_understanding",
    "ocr_extraction",
    "product_attribute_extraction"
  ],
  "input_modalities": ["image", "text"],
  "output_artifacts": ["VisualResult"],
  "tools": ["qwen_vl_parse"],
  "trust_level": "medium",
  "verifiable": true
}
```

### 9.2 AgentMessage 示例

```json
{
  "message_id": "msg_001",
  "from_agent": "router_agent",
  "to_agent": "visual_agent",
  "task_type": "parse_product_screenshot",
  "payload": {
    "image_url": "demo/powerbank.png",
    "user_query": "我用 iPhone 15 和 MacBook，经常出差坐飞机，这个能买吗？"
  },
  "expected_artifact": "VisualResult",
  "trace_id": "trace_001"
}
```

### 9.3 Artifact 示例

```json
{
  "artifact_id": "artifact_visual_001",
  "artifact_type": "VisualResult",
  "producer_agent": "visual_agent",
  "content": {
    "product_name": "某品牌磁吸充电宝",
    "capacity": "20000mAh",
    "power": "22.5W",
    "ports": ["USB-C", "USB-A"],
    "price": 129
  },
  "confidence": 0.86,
  "evidence_refs": ["image_region_1", "image_region_2"]
}
```

### 9.4 A2A-lite 价值

- 任务分派结构化
- 结果工件化
- Trace 可追踪
- Harness 可验证
- 为 V2 对接标准 A2A 协议保留扩展空间

## 10. Skill-based Capability Layer

### 10.1 Skill 与 Tool 的区别

Tool 是原子能力，例如商品文本检索、评论检索、政策查询、兼容性规则查询、评分计算。

Skill 是面向任务的组合能力，可以封装多个 Tool 调用、上下文处理、结果校验和输出格式化。

示例：

```text
Tool:
- product_text_search
- policy_lookup
- review_search
- compatibility_rule_query
- decision_score_calculator

Skill:
- flight_powerbank_check
  = visual_parse + spec_extract + policy_lookup + compatibility_check + review_risk_search + decision_score
```

### 10.2 Skill Registry 示例

```json
{
  "skill_id": "flight_powerbank_check",
  "name": "Flight Powerbank Purchase Check",
  "description": "判断充电宝是否适合出差、飞机携带和指定设备充电",
  "input_schema": {
    "user_query": "string",
    "visual_result": "object",
    "user_devices": "array",
    "constraints": "object"
  },
  "output_schema": {
    "policy_evidence": "array",
    "compatibility_result": "object",
    "risk_factors": "array",
    "decision_result": "object"
  },
  "required_tools": [
    "visual_parse",
    "policy_lookup",
    "compatibility_check",
    "review_risk_search",
    "decision_score"
  ],
  "verifiable": true,
  "validation_rules": [
    "must_include_policy_evidence",
    "must_include_device_compatibility",
    "must_include_risk_factors"
  ]
}
```

### 10.3 V1 核心 Skill

V1 首期实现 6 个核心 Skill：

1. `product_visual_parse`  
   解析商品截图，抽取标题、品牌、价格、容量、接口、功率、卖点。

2. `product_retrieve`  
   基于文本、图片和结构化约束召回候选商品。

3. `review_risk_mining`  
   从评论中提取发热、虚标、太重、充电慢、兼容性差等风险。

4. `policy_check`  
   检索平台政策、航空携带规则、售后规则等外部约束。

5. `compatibility_check`  
   判断商品与用户设备、接口、功率、使用场景是否匹配。

6. `decision_score`  
   综合证据、规则和风险计算最终推荐分数。

Skill Layer 的作用是将 Agent 能力从临时 Prompt 升级为可注册、可复用、可验证的任务能力模块。

## 11. MCP-compatible Tool Layer

MCP 解决的是“工具多，需要统一接口”的问题。

OmniCart Agent 中存在商品检索、评论检索、政策查询、兼容性规则查询、向量数据库检索、评分计算、Demo Replay 等多类工具。如果每个 Agent 直接调用不同工具，会导致接口混乱、权限不可控、结果难追踪。

因此，V1 实现 MCP-compatible ToolManager，对所有工具进行统一描述、统一调用、统一日志、统一返回格式。V2 再将 ToolManager 封装为标准 MCP Server。

V1 不是完整 MCP Server，而是 MCP-compatible abstraction。

### 11.1 Tool Manifest 示例

```json
{
  "tool_name": "policy_lookup",
  "description": "查询商品相关政策规则，例如航空携带限制、平台售后政策",
  "input_schema": {
    "category": "string",
    "keywords": "array",
    "constraints": "object"
  },
  "output_schema": {
    "evidence_list": "array",
    "confidence": "number"
  },
  "permission_level": "read_only",
  "risk_level": "low",
  "requires_confirmation": false,
  "allowed_agents": ["retrieval_agent"],
  "output_schema_required": true,
  "timeout_ms": 3000,
  "cacheable": true,
  "manifest_hash": "sha256:xxxx"
}
```

### 11.2 V1 MCP-compatible Tools

1. `product_text_search`
2. `product_image_search`
3. `review_search`
4. `faq_policy_search`
5. `compatibility_rule_query`
6. `structured_filter`
7. `decision_score_calculator`
8. `evidence_validator`
9. `demo_replay_loader`

所有工具输出都必须是结构化 JSON，不能只返回自然语言字符串。

### 11.3 ToolCallRecord 字段

```json
{
  "tool_name": "policy_lookup",
  "input_summary": "category=power_bank, keywords=[flight, capacity]",
  "output_summary": "found 2 policy evidences",
  "latency_ms": 94,
  "status": "success",
  "error_message": null,
  "trace_id": "trace_001"
}
```

## 12. Context Engineering：购物决策上下文编译

大模型应用的关键不只是模型能力，而是如何组织上下文。

OmniCart Agent 不会把检索到的商品、评论、政策、图片解析结果全部无序塞给大模型，而是通过 Context Compiler 将用户意图、约束条件、视觉解析结果、检索证据、评分结果、风险因素、历史偏好和 Harness 验证结果编译为结构化上下文，再交给 Response Agent 生成最终答案。

### 12.1 Context Compiler 职责

- 汇总用户 query
- 汇总 Router Agent 抽取的 constraints
- 汇总 Visual Agent 解析出的 visual_result
- 汇总 Retrieval Agent 返回的 evidence_list
- 汇总 Decision Agent 输出的 decision_results
- 汇总 risk_factors
- 汇总 Preference Memory Card
- 汇总 Harness Validation 状态
- 控制上下文长度
- 去除低置信度、重复、冲突证据
- 生成 Response Agent 可用的 structured prompt

### 12.2 上下文结构示例

```json
{
  "user_query": "我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？",
  "constraints": {
    "devices": ["iPhone 15", "MacBook"],
    "scenario": ["business_trip", "flight"],
    "needs": ["portable", "safe", "usb_c"]
  },
  "visual_result": {},
  "top_products": [],
  "evidence_summary": [],
  "risk_summary": [],
  "decision_results": [],
  "preference_memory_card": {},
  "harness_status": "passed"
}
```

### 12.3 V1 实现

目录：

```text
backend/app/context/
  context_compiler.py
  prompt_builder.py
  token_budget_controller.py
  context_schema.py
```

实现范围：

- `context_compiler.py` 负责聚合结构化上下文
- `prompt_builder.py` 负责生成 Response Agent prompt
- `token_budget_controller.py` 负责按优先级裁剪证据
- `context_schema.py` 定义 CompiledContext

### 12.4 V2 扩展

- 更复杂的上下文压缩
- 基于用户偏好的个性化上下文编译
- 多轮对话上下文长期管理

Android 客户端展示：

- Context Panel 展示当前系统理解的用户约束、偏好和主要证据。

## 13. Preference Memory Card：会话级购物偏好记忆

OmniCart Agent V1 不做复杂长期记忆系统，但需要实现会话级 Preference Memory Card，用于保存用户在当前对话中明确表达过的预算、设备、使用场景、偏好和避雷项，使系统能够在多轮追问中复用约束，而不是每一轮从零开始。

### 13.1 Preference Memory Card 示例

```json
{
  "preferred_budget": "200-300",
  "devices": ["iPhone 15", "MacBook"],
  "scenario": ["business_trip", "flight"],
  "avoid": ["too_heavy", "overheat", "fake_capacity"],
  "preferred_features": ["usb_c", "portable", "safe"]
}
```

### 13.2 作用

- 支持多轮追问
- 支持状态恢复
- 支持后续推荐沿用用户约束
- 支持 Decision Scoring 中的 `scenario_fit` 和 constraint satisfaction
- 不涉及跨会话隐私存储，V1 只保存在 session state 中

### 13.3 V1 实现

目录：

```text
backend/app/memory/
  preference_card.py
  session_memory.py
```

实现方式：

- session-level memory
- 存入 AgentState
- 可在 Android 客户端 Context Panel 展示“当前系统已理解的购物偏好”

### 13.4 V2 扩展

- 跨会话用户长期偏好
- 用户可编辑偏好画像
- 隐私与权限控制

## 14. Adaptive Retrieval：自适应多模态证据检索

多路召回不能每次都固定检索同样的 Top-K。不同购物任务需要不同检索策略。

OmniCart Agent 由 Router Agent 生成 Retrieval Plan，动态决定调用哪些检索链、每条链检索多少证据、是否需要继续检索或澄清用户问题。

### 14.1 Retrieval Policy Router

输入：

- user_query
- intent
- constraints
- visual_result
- task_type

输出：

```json
{
  "retrieval_plan": [
    "visual_parse",
    "product_text_search",
    "review_risk_search",
    "policy_lookup",
    "compatibility_rule_query"
  ],
  "adaptive_top_k": {
    "product": 10,
    "review": 8,
    "policy": 3,
    "compatibility": 5
  },
  "need_policy_evidence": true,
  "need_risk_evidence": true,
  "need_visual_evidence": true
}
```

### 14.2 不同任务的检索策略

1. 文本导购  
   商品文本 + 评论 + 结构化过滤。

2. 图片导购  
   视觉解析 + 图片检索 + 商品文本 + 评论风险。

3. 充电宝出差场景  
   视觉解析 + 商品检索 + 航空政策 + 兼容性规则 + 评论风险。

4. 商品对比  
   商品参数 + 评论 + 对比证据。

5. 风险咨询  
   评论风险 + 政策 + 售后规则。

### 14.3 V1 实现

目录：

```text
backend/app/retrieval/
  retrieval_policy.py
  adaptive_router.py
```

实现范围：

- rule-based retrieval policy
- `asyncio.gather` 并行调用 retriever
- `adaptive_top_k` 配置

### 14.4 V2 扩展

- 由 LLM 学习生成 retrieval plan
- 基于评测反馈优化检索策略
- 自动判断证据不足并二次检索

Android 客户端展示：

- Retrieval Plan Panel 展示本次任务调用了哪些检索链和每条链 Top-K。

## 15. Retrieval Reflection：证据充分性自检

系统在生成最终答案前，需要检查当前证据是否足以支持回答。

对于缺少政策证据、缺少兼容性证据、缺少评论风险证据或视觉识别置信度过低的情况，系统不能直接生成强结论，而应继续检索或向用户发起澄清。

### 15.1 Evidence Sufficiency Checker

输入：

- user_query
- task_type
- evidence_list
- decision_results
- constraints

输出：

```json
{
  "sufficient": false,
  "missing_evidence": ["airline_policy", "macbook_power_requirement"],
  "next_action": "retrieve_more"
}
```

### 15.2 next_action

- `retrieve_more`：继续检索
- `ask_clarification`：向用户澄清
- `proceed`：证据足够，进入 Response Agent

### 15.3 V1 实现

目录：

```text
backend/app/verification/
  evidence_sufficiency.py
  retrieval_reflection.py
```

实现方式：

- 规则判断必须证据类型
- 轻量 LLM 判断证据是否足够
- 结果写入 Harness Report

### 15.4 V2 扩展

- 更强的 Verifier Agent / Judge Agent
- 自动二次检索策略学习

## 16. Evidence Graph Lite：轻量商品证据图谱

OmniCart Agent V1 不引入完整 Neo4j 图数据库，但可以使用 PostgreSQL 关系表或 NetworkX 构建轻量 Evidence Graph Lite，用于表达商品、参数、评论、政策、设备、风险和替代商品之间的关系。

### 16.1 关系类型

- Product -> has_spec -> Spec
- Product -> has_review -> ReviewEvidence
- Product -> compatible_with -> Device
- Product -> constrained_by -> Policy
- Product -> has_risk -> RiskFactor
- Product -> alternative_to -> Product
- Product -> suitable_for -> Scenario

### 16.2 用途

1. 查替代商品
2. 查互补商品
3. 查兼容设备
4. 查商品风险路径
5. 支持可解释推荐路径展示

### 16.3 Evidence Path Example

```text
iPhone 15 -> USB-C -> 充电宝 A -> 评论证据 -> 风险较低
```

### 16.4 V1 实现

目录：

```text
backend/app/graph/
  evidence_graph.py
  graph_builder.py
  path_explainer.py
```

实现方式：

- 用 PostgreSQL 表或 NetworkX
- 支持路径查询
- 支持推荐原因路径展示

### 16.5 V2 扩展

- Neo4j
- 更完整 GraphRAG
- 跨类目商品关系推理

Android 客户端展示：

- Evidence Graph Path 展示推荐原因路径。

## 17. Visual Evidence Grounding：视觉证据定位

商品截图解析不能只输出文字结果，还应该尽量保留视觉证据来源。

Visual Agent 在解析商品截图时，应输出字段值、置信度和截图区域引用，使 Evidence Panel 能展示“容量、功率、接口、价格这些结论来自截图的哪个区域”。

### 17.1 VisualEvidence 示例

```json
{
  "field": "capacity",
  "value": "20000mAh",
  "bbox": [120, 340, 260, 380],
  "confidence": 0.89,
  "evidence_id": "V001"
}
```

### 17.2 V1 实现

目录：

```text
backend/app/vision/
  visual_grounding.py
  visual_evidence.py
```

实现策略：

- 如果模型支持 bbox，则直接使用
- 如果不支持 bbox，则记录 image_region 或 visual_evidence_id
- V1 重点实现字段级视觉证据引用

### 17.3 V2 扩展

- 可视化高亮框
- 鼠标悬停证据定位
- 多图证据对齐

Android 客户端：

```text
android-client/app/src/main/java/com/omnicart/agent/feature/evidence/
  VisualEvidenceViewer.kt
```

Evidence Panel 显示：

- 参数来源：商品截图 V001
- 置信度：0.89
- 内容：20000mAh

## 18. Product Constraint Solver：商品约束求解器

Decision Scoring 不能只做加权评分。购物决策中有一类硬约束必须先满足，例如预算上限、品类、接口兼容性、航空携带限制、MacBook 供电功率需求等。

系统应先用 Constraint Solver 判断商品是否通过硬约束，再对通过硬约束或部分通过的候选商品做软评分。

### 18.1 Hard Constraints

- 品类必须匹配
- 价格不能明显超预算
- 接口必须兼容
- 涉及航空携带时不能违反政策
- MacBook 场景需要满足最低功率要求

### 18.2 Soft Preferences

- 品牌偏好
- 轻便性
- 评论口碑
- 发热风险
- 外观相似度
- 性价比

### 18.3 Constraint Result 示例

```json
{
  "product_id": "P001",
  "hard_constraints": {
    "category_match": "pass",
    "budget_limit": "pass",
    "device_compatibility": "pass",
    "flight_policy": "uncertain",
    "macbook_power": "fail"
  },
  "decision": "not_recommended_for_macbook",
  "reason": "功率不足，不适合作为 MacBook 主力供电方案。"
}
```

### 18.4 规则

- hard constraint fail 的商品不能排在最终推荐首位
- uncertain 的商品必须提示风险或要求用户确认
- soft score 只在硬约束通过或部分通过后计算

目录：

```text
backend/app/decision/
  constraint_solver.py
  hard_filter.py
  soft_ranker.py
```

## 19. Counterfactual Recommendation：反事实推荐解释

优秀的导购系统不仅要告诉用户“推荐什么”，还要告诉用户“为什么不是另一个商品”“如果你的约束变化，推荐会如何变化”。

OmniCart Agent 在 V1 主 Demo 中输出轻量反事实解释。

### 19.1 主 Demo 示例

- 如果你只给 iPhone 15 充电：当前商品可以考虑。
- 如果你还想给 MacBook 供电：建议选择 65W 以上输出功率的型号。
- 如果你更重视上飞机便携：建议选择容量和重量更低的型号。
- 如果你更重视价格：可以接受当前商品，但需要注意评论中的发热反馈。

### 19.2 V1 实现

- 模板化 counterfactual explanation
- 基于 constraints、ConstraintResult 和 score_breakdown 生成
- Response Agent 最终回答中至少包含一个“如果……那么……”解释

### 19.3 V2 扩展

- 基于用户偏好和商品图谱动态生成复杂反事实推荐
- 支持多约束敏感性分析

## 20. Tool Governance 与 MCP Security Lite

工具越多，Agent 越容易出现工具误用、权限失控、结果不可验证、工具描述污染等问题。

OmniCart Agent 在 V1 的 MCP-compatible ToolManager 中加入轻量 Tool Governance 机制，保证工具可控、可审计、可验证。

### 20.1 扩展 Tool Manifest

```json
{
  "tool_name": "policy_lookup",
  "description": "查询商品相关政策规则，例如航空携带限制、平台售后政策",
  "input_schema": {},
  "output_schema": {},
  "permission_level": "read_only",
  "risk_level": "low",
  "requires_confirmation": false,
  "allowed_agents": ["retrieval_agent"],
  "output_schema_required": true,
  "timeout_ms": 3000,
  "cacheable": true,
  "manifest_hash": "sha256:xxxx"
}
```

### 20.2 V1 Tool Governance

1. Tool allowlist  
   只允许 Agent 调用白名单工具。

2. Allowed agents  
   每个工具声明允许哪些 Agent 调用。

3. Read-only by default  
   V1 所有工具默认只读，不允许下单、支付、修改账号。

4. Output schema validation  
   所有工具返回必须通过 schema 校验。

5. Timeout and retry  
   每个工具必须有 `timeout_ms` 和失败处理。

6. Tool call logging  
   所有工具调用写入 ToolCallRecord。

7. Prompt injection pattern filter  
   对外部文本证据做简单注入模式过滤。

8. Manifest hash  
   记录工具 manifest hash，防止工具描述被悄悄修改。

### 20.3 目录

```text
backend/app/security/
  tool_governance.py
  manifest_checker.py
  prompt_injection_filter.py
```

V1 不做复杂安全系统，但必须体现工具治理意识。V2 可扩展为更完整的 MCP Server 安全审计、工具签名、权限隔离和语义审查。

## 21. Declarative Shopping Workflow：声明式购物决策流程

为了避免 Agent 工作流散落在代码里，OmniCart Agent 使用轻量 `workflow.yaml` 描述主 Demo 的执行流程，使流程可读、可改、可审计。

### 21.1 workflow.yaml 示例

```yaml
name: powerbank_purchase_advice
description: "充电宝截图购买决策流程"
steps:
  - id: route
    agent: router_agent
  - id: visual_parse
    agent: visual_agent
    when: has_image
  - id: retrieve
    agent: retrieval_agent
    parallel:
      - product_text_search
      - review_risk_search
      - policy_lookup
      - compatibility_rule_query
  - id: check_evidence
    verifier: evidence_sufficiency_checker
  - id: score
    agent: decision_agent
  - id: validate
    harness: decision_harness
  - id: compile_context
    service: context_compiler
  - id: respond
    agent: response_agent
  - id: guard_response
    verifier: response_guard
```

### 21.2 V1 实现

V1 可以先将 `workflow.yaml` 作为配置文件和文档化流程，不必实现完整 workflow DSL。`workflow_engine.py` 读取关键配置，驱动固定主流程。

目录：

```text
backend/app/workflows/
  powerbank_purchase_advice.yaml
  text_shopping_advice.yaml
  product_comparison.yaml
```

### 21.3 V2 扩展

- 更复杂分支
- 循环
- 条件执行
- 并行调度

## 22. Tiered Multimodal Fallback：分层多模态兜底

多模态链路容易受到图片模糊、模型 API 延迟、视觉解析失败、字段抽取不完整等因素影响。

OmniCart Agent 采用分层兜底机制，保证系统不会因为一次图片解析失败就整体失败。

### 22.1 Fallback Levels

Level 1：Qwen-VL 直接解析商品截图。  
Level 2：Qwen-VL 输出结构化文本后走文本检索。  
Level 3：OCR / 截图文本 fallback。  
Level 4：提示用户补充商品名称、链接或关键参数。  
Level 5：Demo Pack / Mock Mode 兜底。

每次 fallback 都要写入 TraceStep 和 Harness Report。

### 22.2 目录

```text
backend/app/vision/
  multimodal_fallback.py

android-client/app/src/main/java/com/omnicart/agent/feature/
  product/RiskTag.kt
  demo/DemoModeSwitch.kt
```

Android 客户端展示当前使用了哪一级 fallback。

## 23. Hierarchical Shopping Knowledge Index：分层商品知识索引

商品知识不应该全部混在一个向量库里。OmniCart Agent 将知识分为不同层级和索引，以提高检索准确性和可解释性。

### 23.1 索引层级

1. Category Guide Index  
   类目级购买指南，例如充电宝选购要看容量、功率、重量、接口、航空政策。

2. Product Index  
   商品级 SKU 信息，例如标题、参数、价格、品牌、卖点。

3. Review Index  
   评论级真实反馈，例如发热、虚标、重量、充电慢。

4. Policy Index  
   政策级规则，例如航空携带、售后、退换、质保。

5. Compatibility Index  
   兼容性级规则，例如 iPhone 15、MacBook、USB-C、PD 输出功率。

### 23.2 实现

Retrieval Policy Router 根据任务类型选择不同索引。

V1 用不同 Qdrant collection 或 metadata filter 实现。V2 可结合 Evidence Graph Lite 和 GraphRAG。

目录：

```text
backend/app/indexing/
  build_category_index.py
  build_product_index.py
  build_review_index.py
  build_policy_index.py
  build_compatibility_index.py
```

## 24. Response Guard：最终回答守门机制

Response Guard 位于 Response Agent 之后、返回用户之前，用于检查最终答案是否存在无证据结论、遗漏风险、评分解释不一致、政策问题未引用政策证据等问题。

### 24.1 检查项

- 是否所有推荐商品都有 evidence_ids
- 是否所有风险提醒都有证据来源
- 是否政策类问题引用了 policy evidence
- 是否 final_score 与 score_breakdown 一致
- 是否存在夸大宣传或绝对化表达
- 是否在低置信度情况下给出了澄清或保守建议

### 24.2 V1 实现

V1 中 Response Guard 可以作为 Harness Validator 的一部分。

目录：

```text
backend/app/verification/
  response_guard.py
```

### 24.3 V2 扩展

- 独立 Verifier Agent / Judge Agent
- 更复杂的事实一致性校验

## 25. Multimodal Evidence RAG 设计

OmniCart 的 RAG 是 Multimodal Evidence RAG，而不是普通向量检索。

### 25.1 Text Evidence Chain

包含：

- 商品标题
- 商品参数
- 商品卖点
- 评论
- 问答
- FAQ
- 平台政策
- 购买建议文本

### 25.2 Visual Evidence Chain

包含：

- 商品主图
- 详情页截图
- 商品包装图
- 参数图
- 对比图
- 用户上传截图

### 25.3 Structured Evidence Chain

包含：

- 价格
- 品牌
- 品类
- 库存
- 兼容设备
- 接口类型
- 功率
- 容量
- 适用场景
- 航空携带限制
- 售后规则

### 25.4 完整 RAG 流程

```text
用户输入文本/图片
  -> Router Agent 判断任务类型
  -> Visual Agent 解析图片信息
  -> Query Constructor 构造多路检索查询
  -> Text Retriever 检索商品文本、评论、FAQ、政策
  -> Visual Retriever 检索相似商品图片或截图
  -> Structured Filter 根据价格、品类、品牌、设备型号、使用场景过滤
  -> Evidence Merger 合并文本证据、视觉证据和结构化证据
  -> Evidence Sufficiency Checker 检查证据充分性
  -> Qwen Reranker 精排
  -> Constraint Solver 判断硬约束
  -> Decision Agent 评分
  -> Response Agent 生成证据驱动的推荐答案
  -> Harness Validation 验证证据、评分、约束、风险
```

系统回答必须绑定 `evidence_ids`，不能让大模型凭空推荐。最终输出应包含商品、评分、证据、风险和推荐理由。

## 26. Decision Scoring 机制

评分机制使用 0 到 1 的工程尺度，便于后端计算、Android 客户端展示和 Harness 校验。

### 26.1 子分数

| 字段 | 含义 |
|---|---|
| `budget_fit` | 预算匹配度 |
| `scenario_fit` | 使用场景匹配度 |
| `spec_match` | 参数匹配度 |
| `review_confidence` | 评论口碑可信度 |
| `visual_similarity` | 视觉相似度 |
| `availability_score` | 库存/可购买性 |
| `risk_penalty` | 风险惩罚项，0 到 1，越大表示风险越高 |

### 26.2 公式

```text
raw_score =
  0.22 * budget_fit
+ 0.24 * scenario_fit
+ 0.20 * spec_match
+ 0.14 * review_confidence
+ 0.10 * visual_similarity
+ 0.10 * availability_score
- 0.15 * risk_penalty

final_score = clip(raw_score, 0, 1)
display_score = round(final_score * 10, 1)
```

约束：

- 后端统一使用 0 到 1 的 `final_score`
- Android 客户端展示为 0 到 10 分
- `risk_penalty` 是正数，表示风险强度，在公式中被扣除
- 评分不是由大模型直接拍脑袋生成，而是由检索证据、结构化规则和 reranker 分数组合计算得到
- 大模型只负责解释评分依据，不负责随意决定最终排序

### 26.3 DecisionResult 示例

```json
{
  "product_id": "P001",
  "final_score": 0.87,
  "display_score": 8.7,
  "score_breakdown": {
    "budget_fit": 0.92,
    "scenario_fit": 0.88,
    "spec_match": 0.85,
    "review_confidence": 0.81,
    "visual_similarity": 0.76,
    "availability_score": 1.0,
    "risk_penalty": 0.18
  },
  "evidence_ids": ["E101", "R032", "P009"],
  "risk_factors": ["机身偏重", "部分评论反馈发热"],
  "recommendation_reason": "预算匹配度高，接口和功率满足 iPhone 15 日常充电需求，但不适合作为 MacBook 主力供电方案。"
}
```

## 27. Decision Harness 验证机制

Harness 是 OmniCart Agent 的受控执行与验证环境。它负责以固定输入、固定商品数据、固定政策规则和固定 Golden Query 驱动 Agent 执行，并记录每一步 Agent 消息、工具调用、证据引用、评分结果和最终回答。

Harness 的目标不是替代线上运行，而是用于比赛演示、回归测试、错误定位和决策链路验证。

### 27.1 Harness 验证项

1. Schema Validation  
   检查 AgentState、Evidence、DecisionResult、TraceStep、Artifact 是否符合 schema。

2. Evidence Validation  
   检查最终回答中引用的 `evidence_ids` 是否真实存在。

3. Score Validation  
   检查 `final_score` 是否由 `score_breakdown` 按公式计算得到。

4. Constraint Validation  
   检查推荐商品是否满足预算、品类、设备型号、场景约束。

5. Policy Validation  
   对涉及政策的问题，检查是否引用了政策证据。

6. Risk Validation  
   对高风险商品，检查回答是否包含风险提醒。

7. Replay Validation  
   使用相同 Demo Pack 输入，检查系统是否能复现稳定输出。

### 27.2 Harness Report 示例

```json
{
  "run_id": "harness_run_001",
  "query_id": "golden_023",
  "status": "passed",
  "checks": {
    "schema_validation": "passed",
    "evidence_validation": "passed",
    "score_validation": "passed",
    "constraint_validation": "passed",
    "policy_validation": "passed",
    "risk_validation": "passed",
    "replay_validation": "passed"
  },
  "failed_reasons": [],
  "latency_ms": 4820
}
```

答辩时可以强调：我们不仅让 Agent 会回答，还让它的每一次购物建议都能被验证、回放和审计。

## 28. Stateful Shopping Decision Tree

一次购物咨询不是一条线性对话，而是一棵可以分支、回滚、恢复的购物决策树。系统通过 State Checkpoint 保存关键节点状态，使用户在多轮追问中无需从零开始。

示例：

```text
用户：这个充电宝能买吗？
系统：适合 iPhone，但不适合作为 MacBook 主力供电。
用户：那有没有能给 MacBook 用的？
系统复用上一轮 user_devices、policy_evidence、risk_preferences 和 candidate_products，继续检索替代商品。
```

### 28.1 V1 轻量 Checkpoint

V1 只实现轻量 checkpoint：

- after_visual_parse
- after_retrieval
- after_decision
- after_response

### 28.2 Checkpoint 示例

```json
{
  "state_id": "state_001",
  "parent_state_id": null,
  "branch_id": "main",
  "checkpoint_type": "after_retrieval",
  "agent_state": {},
  "created_at": "2026-05-20T12:00:00Z"
}
```

V2 再扩展为更完整的用户长期偏好记忆和跨会话状态管理。

## 29. 核心数据结构 Schema

### 29.1 AgentState

```json
{
  "session_id": "S001",
  "user_query": "我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？",
  "image_url": "demo/images/powerbank_screenshot.png",
  "intent": {
    "intent_type": "screenshot_purchase_advice",
    "category": "power_bank"
  },
  "constraints": {
    "devices": ["iPhone 15", "MacBook"],
    "scenario": ["business_trip", "flight"],
    "budget_max": 300
  },
  "preference_memory_card": {},
  "retrieval_plan": {},
  "visual_result": {},
  "retrieved_products": [],
  "evidence_list": [],
  "decision_results": [],
  "compiled_context": {},
  "final_response": null,
  "trace_steps": [],
  "skill_executions": [],
  "tool_call_records": [],
  "harness_report": null,
  "checkpoints": []
}
```

### 29.2 Product

```json
{
  "product_id": "P001",
  "title": "10000mAh 磁吸充电宝",
  "brand": "DemoBrand",
  "category": "power_bank",
  "price": 199,
  "specs": {
    "capacity": "10000mAh",
    "wired_power": "30W",
    "wireless_power": "15W",
    "ports": ["USB-C"]
  },
  "scenarios": ["commute", "business_trip", "flight"],
  "image_urls": ["data/images/P001_main.png"],
  "stock_status": "in_stock",
  "tags": ["magnetic", "iphone_compatible", "portable"]
}
```

### 29.3 Evidence

```json
{
  "evidence_id": "R032",
  "source_type": "review",
  "source_id": "review_032",
  "product_id": "P001",
  "content": "有用户反馈长时间快充时机身偏热，但磁吸稳定。",
  "modality": "text",
  "confidence": 0.84,
  "metadata": {
    "aspect": "overheat",
    "sentiment": "negative"
  }
}
```

### 29.4 TraceStep

```json
{
  "step_id": "T003",
  "agent_name": "Retrieval Agent",
  "action": "retrieve_policy_and_reviews",
  "input_summary": "query devices=iPhone 15, MacBook; scenario=flight",
  "output_summary": "found 3 product candidates, 5 review evidences, 2 policy evidences",
  "latency_ms": 382,
  "status": "success"
}
```

### 29.5 SkillExecution

```json
{
  "skill_id": "policy_check",
  "status": "success",
  "input_summary": "category=power_bank, scenario=flight",
  "output_artifact": "artifact_policy_001",
  "latency_ms": 118,
  "validation_result": "passed"
}
```

### 29.6 ToolCallRecord

```json
{
  "tool_name": "faq_policy_search",
  "input_summary": "flight policy for 20000mAh power bank",
  "output_summary": "2 policy evidences returned",
  "latency_ms": 73,
  "status": "success",
  "trace_id": "trace_001"
}
```

### 29.7 AgentMessage

```json
{
  "message_id": "msg_001",
  "from_agent": "router_agent",
  "to_agent": "visual_agent",
  "task_type": "parse_product_screenshot",
  "payload": {
    "image_url": "demo/powerbank.png"
  },
  "expected_artifact": "VisualResult",
  "trace_id": "trace_001"
}
```

### 29.8 Artifact

```json
{
  "artifact_id": "artifact_visual_001",
  "artifact_type": "VisualResult",
  "producer_agent": "visual_agent",
  "content": {
    "product_name": "某品牌磁吸充电宝",
    "capacity": "20000mAh",
    "power": "22.5W"
  },
  "confidence": 0.86,
  "evidence_refs": ["image_region_1"]
}
```

### 29.9 Commerce 数据模型

V1 阶段新增轻量电商数据模型，服务商品展示、购物车、个人中心和豆仔智能受控购物动作。实现可以使用 SQLite / PostgreSQL / JSON mock 数据，不强制引入复杂数据库。

User：

```json
{
  "user_id": "U001",
  "username": "demo_user",
  "phone": "13800000000",
  "password_hash": "hashed_password",
  "avatar_url": "data/images/avatar_demo.png",
  "created_at": "relative_timestamp"
}
```

UserPreference：

```json
{
  "user_id": "U001",
  "devices": ["iPhone 15", "MacBook"],
  "budget_range": "200-300",
  "preferred_categories": ["power_bank"],
  "preferred_brands": [],
  "avoid_tags": ["too_heavy", "overheat", "fake_capacity"],
  "scenarios": ["business_trip", "flight"]
}
```

Address：

```json
{
  "address_id": "ADDR001",
  "user_id": "U001",
  "receiver_name": "Demo User",
  "phone": "13800000000",
  "province": "广东省",
  "city": "深圳市",
  "district": "南山区",
  "detail": "科技园 Demo 地址",
  "is_default": true
}
```

CartItem：

```json
{
  "cart_item_id": "CART001",
  "user_id": "U001",
  "product_id": "P001",
  "quantity": 1,
  "selected": true,
  "added_by": "douzai_agent",
  "added_reason": "豆仔根据用户 MacBook 供电需求推荐加入购物车",
  "created_at": "relative_timestamp"
}
```

MockOrder：

```json
{
  "order_id": "O001",
  "user_id": "U001",
  "items": ["CART001"],
  "total_price": 199,
  "address_id": "ADDR001",
  "status": "mock_paid",
  "created_at": "relative_timestamp"
}
```

## 30. 系统目录结构

后端目录：

```text
backend/
  app/
    main.py

    runtime/
      agent_runtime.py
      workflow_engine.py
      state_manager.py
      checkpoint_store.py

    agents/
      router_agent.py
      visual_agent.py
      retrieval_agent.py
      decision_agent.py
      response_agent.py

    a2a/
      agent_card.py
      message.py
      artifact.py
      dispatcher.py

    context/
      context_compiler.py
      prompt_builder.py
      token_budget_controller.py
      context_schema.py

    memory/
      preference_card.py
      session_memory.py

    skills/
      registry.py
      base.py
      product_visual_parse.py
      product_retrieve.py
      review_risk_mining.py
      policy_check.py
      compatibility_check.py
      decision_score.py

    tools/
      manager.py
      manifest.py
      product_text_search.py
      product_image_search.py
      review_search.py
      policy_lookup.py
      compatibility_rule_query.py
      structured_filter.py
      decision_score_calculator.py
      evidence_validator.py
      demo_replay_loader.py

    mcp_compatible/
      server_adapter.py
      tool_schema.py
      resource_schema.py

    retrieval/
      text_retriever.py
      visual_retriever.py
      structured_retriever.py
      evidence_merger.py
      reranker.py
      retrieval_policy.py
      adaptive_router.py

    verification/
      evidence_sufficiency.py
      retrieval_reflection.py
      response_guard.py

    graph/
      evidence_graph.py
      graph_builder.py
      path_explainer.py

    vision/
      visual_grounding.py
      visual_evidence.py
      multimodal_fallback.py

    decision/
      scoring.py
      risk_analyzer.py
      compatibility_checker.py
      constraint_solver.py
      hard_filter.py
      soft_ranker.py

    security/
      tool_governance.py
      manifest_checker.py
      prompt_injection_filter.py

    workflows/
      powerbank_purchase_advice.yaml
      text_shopping_advice.yaml
      product_comparison.yaml

    indexing/
      build_category_index.py
      build_product_index.py
      build_review_index.py
      build_policy_index.py
      build_compatibility_index.py

    harness/
      runner.py
      validators.py
      replay.py
      golden_loader.py
      report.py

    schemas/
      agent_state.py
      product.py
      user.py
      cart.py
      address.py
      preference.py
      order.py
      evidence.py
      decision_result.py
      trace_step.py
      skill.py
      tool.py
      a2a_message.py
      artifact.py
      checkpoint.py

    model_gateway/
      gateway.py
      qwen_chat.py
      qwen_vision.py
      qwen_embedding.py
      qwen_reranker.py

    api/
      auth.py
      users.py
      products.py
      cart.py
      addresses.py
      agent_actions.py
      chat.py
      recommend.py
      demo.py
      evaluation.py

    services/
      user_service.py
      product_service.py
      cart_service.py
      address_service.py
      preference_service.py
      agent_action_service.py

    repositories/
      user_repo.py
      product_repo.py
      cart_repo.py
      address_repo.py
      vector_repo.py
```

Android 原生客户端目录：

```text
android-client/
  settings.gradle.kts
  build.gradle.kts
  app/
    build.gradle.kts
    src/main/
      AndroidManifest.xml
      java/com/omnicart/agent/
        MainActivity.kt
        MainScaffold.kt
        core/
          config/AppConfig.kt
          network/ApiClient.kt
          network/OmniCartApi.kt
          network/NetworkResult.kt
          model/RecommendRequest.kt
          model/RecommendResponse.kt
          model/Product.kt
          model/User.kt
          model/CartItem.kt
          model/Address.kt
          model/UserPreference.kt
          model/MockOrder.kt
          model/Evidence.kt
          model/DecisionResult.kt
          model/TraceStep.kt
          model/SkillExecution.kt
          model/HarnessReport.kt
          model/FallbackStatus.kt
          theme/Color.kt
          theme/Theme.kt
          theme/Type.kt
        feature/
          product/ProductHomeScreen.kt
          product/ProductList.kt
          product/ProductCard.kt
          product/ProductDetailScreen.kt
          product/CategoryChip.kt
          product/SearchBar.kt
          douzai/DouzaiChatScreen.kt
          douzai/DouzaiViewModel.kt
          douzai/DouzaiUiState.kt
          douzai/ChatInputBar.kt
          douzai/MessageBubble.kt
          upload/ImagePickerButton.kt
          upload/ImagePreview.kt
          product/ScoreBreakdown.kt
          product/RiskTag.kt
          cart/CartScreen.kt
          cart/CartItemRow.kt
          cart/CartSummaryBar.kt
          cart/MockCheckoutSheet.kt
          profile/ProfileScreen.kt
          profile/LoginScreen.kt
          profile/AddressListScreen.kt
          profile/PreferenceScreen.kt
          evidence/EvidencePanel.kt
          evidence/EvidenceItem.kt
          evidence/VisualEvidenceViewer.kt
          trace/AgentTracePanel.kt
          trace/TraceStepItem.kt
          skill/SkillExecutionPanel.kt
          skill/SkillExecutionItem.kt
          harness/HarnessValidationPanel.kt
          harness/HarnessCheckItem.kt
          context/ContextPanel.kt
          context/RetrievalPlanPanel.kt
          demo/DemoModeSwitch.kt
          demo/DemoScenarioSelector.kt
        navigation/AppNavGraph.kt
        navigation/BottomNavBar.kt
        util/UiText.kt
```

`frontend/` 目录从 V1 主线中移除。历史文档或历史代码中出现的 `frontend/`、Next.js、React、TailwindCSS 统一视为 deprecated，不再新增或维护。

新增目录职责：

- `context/`：上下文编译、prompt 构造、token budget 控制。
- `memory/`：会话级 Preference Memory Card。
- `retrieval/retrieval_policy.py`：根据任务生成检索策略。
- `verification/`：证据充分性、检索反思、最终回答守门。
- `graph/`：Evidence Graph Lite 与推荐路径解释。
- `vision/`：视觉证据定位与多模态 fallback。
- `decision/constraint_solver.py`：硬约束优先判断。
- `security/`：工具治理、manifest 校验、注入过滤。
- `workflows/`：声明式购物流程配置。
- `indexing/`：分层商品知识索引构建。

## 31. 关键模块实现方案

### 31.1 Recommendation API

```text
POST /api/recommend
```

Android 客户端依赖该 API 作为稳定契约。客户端不得承担复杂推理逻辑，只负责采集文本/图片输入、调用接口和展示后端结果。

请求：

```json
{
  "user_query": "string",
  "image_url": "string | null",
  "demo_mode": true
}
```

响应：

```json
{
  "session_id": "S001",
  "answer": "推荐回答文本",
  "products": [],
  "evidence_list": [],
  "decision_results": [],
  "trace_steps": [],
  "skill_executions": [],
  "harness_report": {},
  "fallback_status": {}
}
```

后端负责生成 `products`、`evidence_list`、`decision_results`、`trace_steps`、`skill_executions`、`harness_report` 和 `fallback_status`。Android 客户端只能按 schema 渲染这些结果，不能在本地重算推荐分、伪造证据或绕过 Harness。

### 31.1.1 Commerce API

基础电商 API 服务四 Tab Android 客户端，不替代 Agent Runtime：

```text
用户 API
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/users/me
PUT  /api/users/me/preferences

商品 API
GET  /api/products
GET  /api/products/{product_id}
GET  /api/products/search

购物车 API
GET    /api/cart
POST   /api/cart/items
PUT    /api/cart/items/{cart_item_id}
DELETE /api/cart/items/{cart_item_id}
PUT    /api/cart/items/select
POST   /api/cart/checkout/mock

地址 API
GET    /api/addresses
POST   /api/addresses
PUT    /api/addresses/{address_id}
DELETE /api/addresses/{address_id}
PUT    /api/addresses/{address_id}/default

豆仔智能 API
POST /api/recommend
POST /api/agent/actions
```

`/api/agent/actions` 用于豆仔智能发起受控购物车动作：

```json
{
  "action_type": "add_to_cart",
  "product_id": "P001",
  "quantity": 1,
  "reason": "豆仔根据用户需求推荐并加入购物车"
}
```

允许的 action 类型包括 `add_to_cart`、`remove_from_cart`、`update_cart_quantity`。所有 action 必须绑定 `user_id`、写入 Trace 或消息记录，并通过 `agent_action_service.py` 调用 Cart Service。Agent 不允许直接写数据库，不允许执行真实下单或支付。

### 31.2 Workflow Engine

负责按固定流程执行：

```text
route -> visual -> retrieval -> sufficiency -> constraint -> decision -> harness -> context -> response -> guard
```

它不让 Agent 任意跳转，也不允许 Response Agent 绕过 Decision Agent。

### 31.3 Skill Registry

负责：

- 注册 Skill
- 校验输入输出 schema
- 记录 SkillExecution
- 将 Skill 调用结果写入 AgentState

### 31.4 ToolManager

负责：

- 加载 Tool Manifest
- 执行工具
- 超时控制
- 缓存
- Tool Governance
- 记录 ToolCallRecord
- 统一错误格式

### 31.5 Evidence Merger

负责：

- 合并文本、视觉、结构化证据
- 去重
- 过滤低置信度证据
- 标记冲突证据
- 绑定 product_id
- 生成 evidence_ids
- 输出给 Decision Agent、Context Compiler 和 Response Agent

### 31.6 Harness Runner

负责：

- 运行 golden query
- 执行 schema、evidence、score、constraint、policy、risk、replay 校验
- 输出 Harness Report

## 32. 异步协作设计

为了降低端到端延迟，OmniCart Agent 对相互独立的检索任务采用异步并行执行机制。

用户上传截图后，系统可以并行执行：

- Visual Agent 解析截图
- Text Retriever 检索商品文本
- Policy Retriever 查询航空携带政策
- Review Retriever 检索评论风险
- Compatibility Retriever 查询设备兼容性规则

V1 使用 Python `async` / `asyncio.gather` 实现轻量并行，不引入复杂消息队列。V2 再考虑任务队列或分布式执行。

伪流程：

```python
results = await asyncio.gather(
    text_retriever.search(query),
    policy_retriever.search(policy_query),
    review_retriever.search(review_query),
    compatibility_retriever.search(device_constraints),
)
```

异步结果统一进入 Evidence Merger，避免每个检索器直接影响最终回答。

## 33. Android 原生客户端展示设计

V1 参赛主交付形态是 Android Native Client。Android 客户端不是推理引擎，只负责交互展示、图片选择/上传、调用后端 API、购物车交互、个人信息展示，以及展示 ProductCard / Evidence / Trace / Skill / Harness / Fallback。复杂推理、Multimodal Evidence RAG、Agent Workflow、Decision Scoring 和 Decision Harness 均由后端完成。

### 33.0 Bottom Navigation 主框架

App 底部固定四个 Tab，使用 Jetpack Compose Navigation + Material 3 NavigationBar：

| Tab | 页面 | 主要能力 |
|---|---|---|
| 商品展示 | ProductHomeScreen | 商品列表、分类筛选、搜索、商品详情、加入购物车、问豆仔。 |
| 豆仔智能 | DouzaiChatScreen | 文本导购、图片导购、商品对比、评论风险总结、兼容性判断、政策检索、Evidence / Score / Trace / Harness。 |
| 购物车 | CartScreen | 查看购物车、增减数量、删除、多选、全选、价格合计、模拟结算、展示“由豆仔推荐加入”。 |
| 个人中心 | ProfileScreen | Demo 用户、登录状态、用户信息、地址、设备、预算、品牌偏好、避雷项。 |

每个 Tab 使用扁平化 Icon，当前选中页面高亮。豆仔智能 Tab 可以轻微强调，但不能破坏整体一致性。

### 33.1 商品展示页

商品展示页用于展示数据集中已有商品，是用户浏览商品、查看商品详情、进入智能咨询和加入购物车的基础入口。

Android 展示方式：

- 商品瀑布流 / 列表。
- ProductCard。
- CategoryChip。
- SearchBar。
- ProductDetailScreen。
- “加入购物车”按钮。
- “问豆仔”按钮。

### 33.2 豆仔智能页

DouzaiChatScreen 是原项目核心 AI Agent 页面，采用 Jetpack Compose + Material 3 实现。

页面结构：

- 顶部标题“豆仔智能”与 Demo Mode 开关
- 中间聊天流、图片预览、推荐商品卡片
- 底部文本输入、图片选择按钮、发送按钮

支持：

- 文本输入
- Android Photo Picker 图片选择
- ImagePreview 图片预览
- 预置 Demo 一键触发
- Mock Mode 开关
- 通过受控 action 将推荐商品加入购物车

豆仔智能可以理解轻量购物动作，例如“把第一个推荐商品加入购物车”“把适合 MacBook 的那个加入购物车”。这些动作必须调用 `/api/agent/actions`，并写入 Trace 或消息记录。

### 33.3 ProductCard

ProductCard 展示推荐商品的移动端摘要：

- 商品图
- 商品名
- 价格
- 综合评分
- 一句话推荐理由
- 风险标签
- 查看详情按钮

综合评分由后端 `decision_results` 提供，Android 只展示 `display_score` 或后端返回的等价展示字段，不在本地重新计算排序。

### 33.4 ProductDetailSheet / ProductDetailScreen

ProductDetailSheet 使用底部弹窗或详情页 Tab 展示后端返回的可解释决策过程：

- 推荐理由
- Evidence
- Score
- Agent Trace
- Skill Execution
- Harness Validation

### 33.5 Evidence Panel

展示：

- 参数证据
- 评论证据
- 政策证据
- 兼容性证据

每条证据显示：

- evidence_id
- 来源
- 置信度
- 内容摘要

### 33.6 ScoreBreakdown

展示后端 Decision Scoring 的可解释子分数：

- budget_fit
- scenario_fit
- spec_match
- review_confidence
- visual_similarity
- availability_score
- risk_penalty

### 33.7 Agent Trace Panel

显示 Router、Visual、Retrieval、Decision、Response 每一步：

- 输入摘要
- 输出摘要
- 耗时
- 状态

### 33.8 Skill Execution Panel

显示当前任务用了哪些 Skill：

- product_visual_parse
- policy_check
- compatibility_check
- review_risk_mining
- decision_score

每个 Skill 显示：

- success / failed / skipped
- latency_ms
- output_artifact
- validation_result

### 33.9 Harness Validation Panel

展示：

- Schema Valid
- Evidence IDs Valid
- Score Formula Valid
- Policy Evidence Found
- Risk Warning Included
- Replay Passed

### 33.10 Context / Retrieval / Visual / Fallback 展示

V1-Core Android 展示可按时间优先级补充：

- ContextPanel：展示系统理解的设备、场景、偏好、避雷项。
- RetrievalPlanPanel：展示 Router Agent 生成的检索计划。
- VisualEvidenceViewer：展示字段级视觉证据。
- FallbackStatus：展示 Qwen-VL direct parse、OCR fallback、Demo Pack fallback 等状态。

## 34. 主 Demo 场景设计

主 Demo 是现场展示的核心链路，辅助场景只用于补充说明泛化能力。

### 34.1 主 Demo 输入

用户上传一张充电宝商品截图，并提问：

```text
我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？有没有更合适的？
```

### 34.2 系统需要完成

1. 识别截图中的商品名称、价格、容量、功率、接口、卖点。
2. 判断是否适合 iPhone 15。
3. 判断是否适合 MacBook 供电。
4. 检索航空携带规则或政策知识。
5. 检索评论中的风险，例如发热、虚标、太重、充电慢。
6. 判断硬约束是否通过。
7. 综合预算、场景、参数、风险进行评分。
8. 输出当前商品是否推荐购买。
9. 给出 1 到 2 个替代商品。
10. 输出至少一个反事实解释。
11. 展示 Evidence Panel。
12. 展示 Visual Evidence Viewer。
13. 展示 Evidence Graph Path。
14. 展示 Agent Trace。
15. 展示 Skill Execution Panel。
16. 展示 Harness Validation Panel。

### 34.3 辅助演示

- 文本导购
- 商品对比
- 多轮澄清
- 评论风险总结

## 35. 评测方案与 Baseline 对比

评测不只是评最终回答，还要评 Agent 中间过程是否正确，包括上下文理解、检索计划、工具调用、证据引用、评分计算、fallback 和 Harness 验证结果。

### 35.1 三组 Baseline

1. Qwen Direct Answer  
   只把用户问题直接交给 Qwen 回答，不使用检索和证据。

2. Text-only RAG  
   只使用文本商品库和评论检索，不使用图片理解、不使用多路证据、不使用决策评分。

3. OmniCart Agent  
   使用 Qwen-only Model Stack + Context Compiler + Adaptive Retrieval + Multimodal Evidence RAG + Skill Registry + MCP-compatible ToolManager + A2A-lite + Constraint Solver + Decision Scoring + Harness Validation。

### 35.2 指标

| 指标 | 含义 | 评测方式 |
|---|---|---|
| Constraint Satisfaction Rate | 约束满足率 | golden set 自动/人工判定 |
| Evidence Citation Rate | 证据引用率 | 检查 evidence_ids |
| Hallucination Rate | 幻觉率 | 人工标注事实错误 |
| Image-to-Product Recall@10 | 图片找同款或相似商品召回率 | 标注目标 SKU |
| Recommendation Acceptance Rate | 推荐可接受率 | 人工 10 分制评分 |
| Risk Awareness Rate | 风险提醒覆盖率 | 检查风险标签 |
| Tool Call Success Rate | 工具调用成功率 | ToolCallRecord |
| Schema Valid Rate | Schema 合法率 | Harness 自动检查 |
| Harness Pass Rate | Harness 校验通过率 | Harness Report |
| Context Accuracy Rate | 上下文理解准确率 | 检查 constraints / preference card |
| Retrieval Plan Accuracy | 检索计划合理性 | 人工或规则检查 |
| Evidence Sufficiency Pass Rate | 证据充分性通过率 | Evidence Sufficiency Checker |
| Constraint Violation Rate | 硬约束违规率 | Constraint Solver 检查 |
| Tool Governance Pass Rate | 工具治理检查通过率 | manifest / allowlist / schema |
| Fallback Recovery Rate | 多模态 fallback 恢复率 | fallback trace |
| Response Guard Pass Rate | 最终回答守门通过率 | Response Guard |
| Visual Grounding Accuracy | 视觉字段证据准确率 | 人工核对截图字段 |
| Counterfactual Helpfulness | 反事实解释有用性 | 人工评分 |
| Average Latency | 平均延迟 | 日志统计 |
| P95 Latency | P95 延迟 | 日志统计 |

### 35.3 人工评分

每条 golden query 总分 10 分：

| 维度 | 分数 |
|---|---:|
| 约束满足 | 3 |
| 证据正确 | 2 |
| 风险提醒 | 2 |
| 推荐合理 | 2 |
| 表达清晰 | 1 |

### 35.4 Golden Set 规模

| 阶段 | 数量 |
|---|---:|
| V0 | 30 条 |
| V1 | 100 条 |
| V2 | 200 条以上 |

## 36. Demo Pack 与 Mock Mode

Demo Pack / Mock Mode 是比赛稳定性保障。

Mock Mode 不是造假，而是比赛演示中的稳定性兜底；正式功能仍需要真实 API 链路可运行。

### 36.1 Demo Pack 内容

- 固定主 Demo 输入图片
- 预置商品数据
- 预置视觉解析结果
- 预置检索结果
- 预置 evidence_list
- 预置 skill_executions
- 预置 tool_call_records
- 预置 decision_results
- 预置 harness_report
- 预置 final_response
- 预置 trace_steps
- 预置 compiled_context
- 预置 fallback_status

### 36.2 Mock Mode 行为

Mock Mode 开启后：

- Android 客户端仍然展示完整流程
- 后端返回预置中间结果
- Trace Panel 正常展示
- Skill Execution Panel 正常展示
- Harness Validation Panel 正常展示
- Context Panel 正常展示
- Fallback Status 正常展示
- 保证比赛现场稳定演示

### 36.3 Demo Pack 目录

```text
demo/demo_pack/
  scenario_01_powerbank_screenshot/
    input.png
    preference_memory_card.json
    visual_result.json
    retrieval_plan.json
    retrieval_result.json
    evidence_list.json
    skill_executions.json
    tool_call_records.json
    decision_results.json
    compiled_context.json
    harness_report.json
    trace_steps.json
    fallback_status.json
    final_response.json
```

## 37. V0 / V1 / V1-Plus / V2 开发路线

### 37.1 V0-Core：后端最小可运行文本导购闭环

必须完成：

- FastAPI 后端
- Product / Evidence / AgentState / DecisionResult Schema
- Qwen Model Gateway
- 商品 mock 数据
- Qdrant 文本索引
- Text Retriever
- 基础 Recommendation API
- Decision Scoring
- 文本导购闭环

### 37.2 V0-Android：Android 最小可运行客户端闭环

目标：

```text
Android 四 Tab 基础框架
  + 商品展示基础数据
  + 豆仔智能文本推荐
  + 购物车基础功能
  + 个人中心 Demo 用户
```

必须完成：

- Android 项目初始化
- Bottom Navigation 四 Tab：商品展示、豆仔智能、购物车、个人中心
- MainActivity + Compose 主题
- ProductHomeScreen 商品列表和商品详情
- DouzaiChatScreen 文本推荐
- CartScreen 购物车展示、增加、删除商品
- ProfileScreen Demo 用户展示
- ChatInputBar
- Retrofit / OkHttp API 调用
- RecommendRequest / RecommendResponse 数据类
- ProductCard
- 后端商品、购物车、用户基础 API
- `/api/recommend` 返回 mock 推荐
- Demo Mode 本地假数据
- Android 模拟器或真机运行

V0-Android 未跑通前，不允许优先开发完整 Evidence、Trace、Harness、Skill、地址管理、模拟订单等高级能力。

### 37.3 V1-Core：参赛核心闭环版本

目标：

```text
登录 / 注册 + 地址 / 偏好 + 图文输入 + 多模态 RAG + 豆仔加入购物车 + 模拟结算 + 主 Demo
```

V1 增强为参赛核心版，但所有能力都采用轻量实现，不做复杂企业级系统。

V1-Core 不再是单一豆仔智能页，也不只等同于后端 Agent 能力；它同时包含 Android 四 Tab 主体验、登录 / 地址 / 偏好、图片导购、豆仔加购和模拟结算。V1-Core 完成标准是主 Demo 能从商品展示进入豆仔智能，再通过受控 action 加入购物车，最后完成模拟结算并在个人中心展示用户偏好。

后端必须完成：

- 图片上传
- auth / products / cart / addresses / users / agent_actions API
- 用户登录 / 注册
- 地址管理
- 用户偏好管理
- Qwen-VL 图片解析
- Visual Agent
- 5 Agent Workflow
- Context Compiler
- Preference Memory Card
- Skill Registry
- MCP-compatible ToolManager
- A2A-lite AgentMessage / Artifact
- Adaptive Retrieval
- Evidence Sufficiency Checker
- Evidence Graph Lite
- Visual Evidence Grounding
- Constraint Solver
- Counterfactual Recommendation
- Tool Governance
- Declarative workflow.yaml
- Tiered Multimodal Fallback
- Hierarchical Shopping Knowledge Index
- Response Guard
- Multimodal Evidence RAG
- Qwen Reranker
- Decision Scoring
- Decision Harness
- State Checkpoint
- Async Retrieval
- Demo Pack / Mock Mode
- 主 Demo 数据
- baseline 对比脚本
- Cart / Address / Preference Service
- Agent Action Service 调用受控购物车动作
- MockOrder / 模拟结算结果生成

Android 客户端必须完成：

- 图片选择 / 上传
- ImagePreview
- 登录 / 注册
- 地址管理
- 用户偏好管理
- 主 Demo 充电宝截图
- 豆仔通过对话加入购物车
- 购物车模拟结算
- EvidencePanel
- ScoreBreakdown
- AgentTracePanel
- SkillExecutionPanel
- HarnessValidationPanel
- ProductDetailSheet
- Mock Mode 一键演示
- APK 打包

### 37.4 V1-Plus：比赛加分创新版本

V1-Plus 在 V1-Core 稳定后开发，用于提升 Agent 感和可解释性，但不能阻塞四 Tab 基础体验和主 Demo。

建议完成：

- Retrieval Plan Panel。
- Context Panel。
- Preference Memory Card 展示。
- Visual Evidence Grounding。
- Counterfactual Recommendation。
- Evidence Graph Path。
- Skill Execution Panel。
- Tool Governance 展示。
- Fallback Status。
- 更完整 Demo Pack 回放和 baseline 对比。

### 37.5 V2 / V3：增强展示版本

可以完成：

- 标准 MCP Server / Client
- 标准 A2A Protocol
- Computer Use / Browser Use
- iOS Swift + SwiftUI 客户端
- Neo4j GraphRAG
- Qwen-Omni 语音导购
- 用户长期偏好记忆
- 更复杂的 Context Engineering
- 在线反馈学习 / Bandit 排序
- Langfuse / Phoenix 可观测性
- 大规模商品数据接入
- 更完整 Evaluation Dashboard

V2 / V3 是答辩时可作为扩展规划展示，不阻塞比赛交付。

## 38. DEVELOPMENT_TASKS.md 任务拆解

### 38.1 V0-Core 后端任务

- 初始化 FastAPI 后端项目
- 定义 Product / Evidence / AgentState / DecisionResult Schema
- 接入 Qwen Model Gateway
- 构建商品 mock 数据
- 构建 Qdrant 文本向量索引
- 实现 Text Retriever
- 实现基础 Recommendation API
- 跑通文本导购闭环

### 38.2 V0-Android 任务

- 初始化 `android-client/`
- 实现 MainActivity + Compose 主题
- 实现 MainScaffold + BottomNavBar + AppNavGraph
- 实现 ProductHomeScreen / ProductDetailScreen
- 实现 DouzaiChatScreen
- 实现 CartScreen 基础增删
- 实现 ProfileScreen Demo 用户
- 实现 ChatInputBar
- 实现 Retrofit / OkHttp API 调用
- 实现 RecommendRequest / RecommendResponse 数据类
- 实现 User / CartItem / Address / UserPreference 基础数据类
- 实现 ProductCard
- 实现商品、购物车、用户基础 API
- 实现 Demo Mode 本地假数据
- 在 Android 模拟器或真机跑通四 Tab、商品展示、文本推荐、购物车和 Demo 用户

### 38.3 V1-Core 后端任务

- 实现图片上传
- 实现 auth / users / products / cart / addresses / agent_actions API
- 实现 user / product / cart / address / preference / agent_action services
- 接入 Qwen-VL 图片解析
- 实现 Visual Agent
- 实现 5 Agent Workflow
- 实现 Context Compiler
- 实现 Preference Memory Card
- 实现 Skill Registry
- 实现 MCP-compatible ToolManager
- 实现 A2A-lite AgentMessage / Artifact
- 实现 Adaptive Retrieval
- 实现 Evidence Sufficiency Checker
- 实现 Evidence Graph Lite
- 实现 Visual Evidence Grounding
- 实现 Constraint Solver
- 实现 Counterfactual Recommendation
- 实现 Tool Governance
- 实现 Declarative workflow.yaml
- 实现 Tiered Multimodal Fallback
- 实现 Hierarchical Shopping Knowledge Index
- 实现 Response Guard
- 实现 Multimodal Evidence RAG
- 实现 Qwen Reranker
- 实现 Decision Scoring
- 实现 Decision Harness
- 实现 State Checkpoint
- 实现 Async Retrieval
- 实现 Demo Pack / Mock Mode
- 准备主 Demo 数据
- 完成 baseline 对比脚本
- 实现豆仔智能受控购物车 action
- 实现 mock checkout / 模拟订单

### 38.4 V1-Core Android 任务

- 实现 Android Photo Picker 图片选择
- 实现 ImagePreview
- 实现图片上传或 image_url 传递
- 实现登录 / 注册 / Demo 用户
- 实现地址管理和偏好管理
- 实现豆仔对话加入购物车
- 实现购物车多选、全选、模拟结算
- 实现 ProductDetailSheet
- 实现 EvidencePanel
- 实现 ScoreBreakdown
- 实现 AgentTracePanel
- 实现 SkillExecutionPanel
- 实现 HarnessValidationPanel
- 实现 Mock Mode 一键演示
- 完成 APK 打包

### 38.5 V2 / V3 任务

- 标准 MCP Server / Client
- 标准 A2A 协议
- Computer Use / Browser Use
- iOS Swift + SwiftUI 客户端
- Neo4j GraphRAG
- Qwen-Omni 语音导购
- 用户长期偏好记忆
- Langfuse / Phoenix 可观测性
- 在线反馈学习 / Bandit 排序
- 更大规模数据集
- 更完整 Evaluation Dashboard

## 39. 风险与边界

### 39.1 功能边界

- 不自动下单
- 不支付
- 不操作用户账号
- 购物车、模拟结算和模拟订单仅用于比赛版闭环展示，不接入真实支付
- 豆仔智能只能通过受控 Agent Action 操作购物车，不允许直接操作数据库
- Computer Use 只作为 V2 / V3 探索能力，V1 不执行真实网页操作
- Web、WebView、React Native、Expo、Flutter 不作为最终交付端
- MCP 标准服务只作为 V2 扩展，V1 只做 MCP-compatible ToolManager
- 长期记忆只作为 V2 扩展，V1 只做 Preference Memory Card 和轻量 checkpoint

### 39.2 证据边界

- 所有政策判断必须引用政策证据
- 所有风险建议必须标注证据来源
- 对低置信度视觉识别结果要触发澄清
- 对缺少证据的问题不要强行推荐
- Response Agent 不允许生成无证据购买结论

### 39.3 工具边界

- V1 工具默认只读
- 不允许工具执行真实购买、支付、账号修改
- 所有工具输出必须通过 schema validation
- 所有工具调用必须记录 ToolCallRecord

### 39.4 演示边界

- Mock Mode 只用于演示兜底，不替代真实链路
- Demo Pack 必须和真实数据结构一致
- 预置结果也要经过 Harness Validation

## 40. 答辩与简历亮点

### 40.1 答辩亮点

1. 不是聊天式导购，而是可验证的多 Agent 购物决策 Runtime。
2. 不是简单 RAG，而是 Multimodal Evidence RAG + Hierarchical Knowledge Index。
3. 不是固定检索，而是 Adaptive Retrieval + Evidence Sufficiency Checker。
4. 不是工具乱调，而是 Skill Registry + MCP-compatible ToolManager + Tool Governance。
5. 不是 Agent 之间传自然语言，而是 A2A-lite AgentMessage + Artifact。
6. 不是模型拍脑袋推荐，而是 Constraint Solver + Decision Scoring。
7. 不是黑盒图片理解，而是 Visual Evidence Grounding。
8. 不是只给结论，而是 Counterfactual Recommendation。
9. 不是一次性对话，而是 Preference Memory Card + Stateful Decision Tree。
10. 不是现场碰运气，而是 Demo Pack + Mock Mode + Harness Validation。

### 40.2 简历描述

```text
设计并实现 OmniCart Agent，一个面向电商购买前决策的可验证多模态 Agent Runtime。项目基于 Qwen-only Model Stack，构建 Workflow-controlled Multi-Agent 架构，融合 Multimodal Evidence RAG、Context Compiler、Adaptive Retrieval、Skill Registry、MCP-compatible ToolManager、A2A-lite Agent Communication、Tool Governance、Visual Evidence Grounding、Constraint Solver、Explainable Decision Scoring 与 Decision Harness，支持商品截图理解、文本/视觉/结构化多路召回、政策规则检索、兼容性判断、评论风险挖掘、反事实推荐解释、Agent Trace、Evidence Panel 与 Demo Pack 稳定演示。
```

## 41. 总结

OmniCart Agent Competition Edition 的目标不是堆满所有 Agent 技术名词，而是在比赛周期内做出一个能跑、能测、能展示、能解释、能回放、能验证的多模态购物决策 Agent。

项目主线应始终保持清晰：

```text
用户上传文本或商品截图
  -> Qwen 识别意图和视觉信息
  -> Context Compiler 组织购物决策上下文
  -> Skill 和 Tool 组织检索与规则判断
  -> Adaptive Multimodal Evidence RAG 检索商品、评论、政策和规则
  -> Evidence Sufficiency Checker 判断证据是否足够
  -> Constraint Solver 处理硬约束
  -> Decision Agent 计算可解释评分
  -> Harness 验证证据、评分、约束和风险
  -> Response Agent 生成证据绑定推荐
  -> Response Guard 最终守门
  -> Android 原生客户端展示商品、评分、证据、Trace、Skill、Context、Fallback 和 Harness
```

最终交付应让评委清楚看到：

- 系统理解了用户需求
- 系统看懂了商品截图
- 系统找到了相关证据
- 系统组织了 Skill 和 Tool
- 系统做出了硬约束判断
- 系统做出了可解释评分
- 系统验证了关键决策
- 系统给出了有依据的购买建议
- 系统的每一步都能追踪、回放和展示

这就是 OmniCart Agent 作为 Agent 挑战赛参赛项目最应该突出的价值。
