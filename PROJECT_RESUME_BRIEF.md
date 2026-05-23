# OmniCart Agent · 豆仔购物智能助手 — 项目简历材料

> **用途**：指导 Codex / AI Agent 生成高质量简历项目经历
> **原则**：只写事实，不写简历成品，不虚构不存在的能力
> **更新**：2026-05-23（基于 V2 实际代码状态）

---

## 一、项目总览

### 1. 一句话介绍

OmniCart Agent 是一个面向电商购物前决策场景的 Android 原生多模态智能导购 Agent 系统，融合 Qwen 全栈模型、LangGraph Multi-Agent 编排、多模态 Evidence RAG、可解释决策评分、Skill/Tool 工具治理、语音导购、长期偏好记忆和标准 MCP 协议，跑通从商品浏览到模拟结算的完整购物决策闭环。

### 2. 项目解决的问题

- 电商购物推荐缺乏**可解释性**：用户不知道"为什么推荐这个商品"
- 传统搜索式购物**意图理解弱**：用户口语化需求难以转化为精准商品匹配
- LLM 直接生成推荐**不可控**：幻觉、无依据判断、无法追溯证据
- 图片/截图购物场景**信息提取困难**：用户拍一张商品截图，系统需要理解参数、品牌、规格
- 多个 AI 能力需要**统一编排**：视觉理解、文本检索、评论挖掘、政策查询、评分计算需要被协调调度

### 3. 为什么重要

- Agent 不再是聊天机器人，而是**可控的决策流水线**：每一步可追踪、可验证、可复算
- 所有推荐结论绑定 `evidence_ids`：从商品参数、用户评论、官方FAQ、视觉解析等来源引用证据
- 端到端闭环：从商品浏览 → 图文咨询 → 证据检索 → 决策评分 → 推荐解释 → 加入购物车 → 模拟结算

### 4. 目标用户

- 有明确购物需求但需要专业比选建议的消费者
- 需要手机拍照快速了解商品参数的场景（线下看到商品，拍照问 AI）
- 比赛评委 / 面试官（展示 Agent 工程能力）

### 5. 典型使用场景

1. **文本导购**：用户输入"推荐一款500以内的降噪蓝牙耳机" → 意图解析 → 多路检索 → 评分排序 → 推荐理由 + 证据面板
2. **拍照识图**：用户拍摄商品货架/截图 → Qwen-VL 提取参数 → 自动匹配数据库商品 → 对比推荐
3. **语音导购**：长按麦克风说"推荐一款防晒霜" → ASR转写 → Agent推荐 → TTS语音播报
4. **多轮对话**：用户连续追问"有没有便宜的"、"这个适合敏感肌吗" → 偏好记忆合并约束 → 增量推荐

### 6. 不是普通购物 App 或聊天机器人

- **不是**：商品目录 App、WebView 套壳、单一 LLM 聊天窗口
- **是**：Workflow-controlled Multi-Agent 系统，Agent 编排取代单一 LLM 自由生成，每个推荐步骤有结构化输入输出、可追踪、可验证

### 7. 最终交付形态

- **Android 原生客户端**（Kotlin + Jetpack Compose + Material 3 + MVVM）：四 Tab 完整产品
- **FastAPI 后端 Agent Runtime**（Python 3.11 + LangGraph + PostgreSQL + Qdrant + Redis）
- **APK 可打包安装**，后端可独立部署

### 8. 客户端与后端职责

| Android 客户端 | FastAPI 后端 |
|----------------|-------------|
| 四 Tab 页面展示与导航 | Agent Workflow 编排（8节点LangGraph） |
| 用户输入（文本/图片/语音） | 多模态理解（Qwen-VL视觉解析 + Omni语音） |
| 状态管理（ViewModel + StateFlow） | 多路 Evidence RAG 检索 |
| API 请求（Retrofit + OkHttp + Auth拦截器） | 7维 Decision Scoring |
| 可解释面板展示（Evidence/Score/Trace/Harness/Skill） | Tool Action 受控执行 |
| 图片选择与上传（Photo Picker + Coil） | 数据持久化（PostgreSQL 6表 + 双模降级） |
| Demo Mode 一键演示 | State Checkpoint / Harness 验证 |

### 9. 工程价值

- 展示从**架构设计 → Agent编排 → RAG检索 → 评分决策 → 移动端交付**的完整工程能力
- 不依赖单一 LLM 黑盒，每个环节可独立优化、测试、替换
- 6 类 Repository 全部 PG+内存双实现 + 工厂注入，展示生产级代码组织能力
- 31 个单元测试，8 节点 Workflow 全链路可复现

---

## 二、产品功能说明

### 2.1 商品展示页

- **商品列表**：展示 105 件商品（4 品类：美妆护肤/数码电子/服饰运动/食品饮料），支持品类标签切换筛选
- **商品搜索**：关键词搜索商品标题、品牌、描述
- **商品分类**：顶部品类 Tabs + 子品类过滤
- **商品详情**：点击商品卡片弹出 ProductDetailSheet（6 Tab：推荐理由/证据列表/评分细分/执行链路/技能执行/验证结果）
- **商品图片**：Coil 异步加载，支持实拍商品图（JPG 格式）
- **商品参数**：SKU 多规格展示（颜色/版本等）+ 价格区间
- **评论摘要**：用户评分 + 精选评论内容
- **加入购物车**：商品详情页和卡片均可一键加购，调用 `/api/agent/action`
- **"问豆仔"入口**：将当前商品上下文传递给豆仔智能页，自动带入商品信息发起咨询

### 2.2 豆仔智能页（核心 AI Agent 页面）

**文本导购**：
- 用户在 ChatInputBar 输入购物需求 → Retrofit 调用 `/api/recommend/v2`
- 触发 8 节点 LangGraph Workflow：Router → Visual(可选) → Retrieval → Reranker → EvidenceCheck → Decision → Response → Guard
- 返回推荐商品列表 + 推荐理由 + 证据 + 评分 + 链路

**图片上传与解析**：
- Android Photo Picker 选择图片或拍照
- 图片上传 `/api/upload` → 返回 image_url
- Qwen-VL 视觉 Agent 解析商品截图 → 提取产品名/品牌/规格/价格/卖点 → 作为检索增强输入

**语音导购（V2）**：
- 长按麦克风进入全屏语音输入界面（暗屏 + 波纹动画 + "请说出你想买的商品..."）
- 录音上传 `/api/voice/transcribe` → Qwen-Omni ASR 转写文字
- 转写文字立即显示在聊天框 → 像打字一样走 Agent 推荐链路
- Agent 回答可生成 TTS 语音播报

**多轮对话**：
- PreferenceMemory 跨轮合并约束（品类/预算/标签）
- 话题切换自动检测（新品类 ≠ 旧品类 → 清除旧约束）
- 长期偏好记忆（V2）：跨会话学习用户偏好，搜索/加购/结账行为信号加权

**闲聊模式**：
- Router 16 词检测闲聊意图 → 跳过全部检索链 → 独立闲聊 Prompt 生成友好回复
- 6 类模板兜底（打招呼/自我介绍/能力说明/感谢/告别/其他）

**Agent 洞察面板（V1-Plus）**：
- AgentInsightSheet 10 Tab：上下文/检索计划/证据图/降级状态/工具调用/反事实建议/视觉绑定/偏好画像/基准评测/摘要

**购物车 Action**：
- 豆仔推荐商品后，用户说"加入购物车" → Agent 识别意图 → 调用 `/api/agent/action` → 后端加购 + 记录长期偏好
- 聊天消息中 ProductCard 始终带加购按钮

### 2.3 购物车页

- **查看购物车**：商品列表 + 图片 + 标题 + 单价 + 数量
- **数量修改**：加减按钮或直接输入
- **删除商品**：单条删除或清空购物车
- **多选/全选**：Checkbox 选择 + 全选/取消全选
- **价格合计**：选中商品总价实时计算
- **模拟结算**：MockCheckoutSheet → 调用 `/api/checkout` → 生成模拟订单（不接入真实支付）
- **来源标记**：豆仔推荐加入的商品标注"由豆仔推荐加入"
- **与豆仔联动**：豆仔推荐结果可直接加购，购物车实时刷新

### 2.4 个人中心页

- **登录/注册**：用户名+密码注册，PBKDF2-SHA256 100k 迭代密码哈希，Bearer Token 认证
- **Demo 用户**：开发阶段默认使用 demo_user_001
- **用户信息**：头像 + 用户名 + 登录状态
- **地址管理**：省/市/区/详细地址 + 手机号 + 收件人，支持默认地址互斥
- **偏好设置**：品类偏好/预算区间/使用场景/偏好标签（逗号分隔）
- **长期偏好画像**：V2 跨会话学习，`GET /api/preferences/long-term/{user_id}`
- **user_id 串联**：用户 → 地址 → 偏好 → 购物车 → 结算 → 个性化推荐

---

## 三、系统架构说明

### 整体架构

```
Android Client (Kotlin/Compose/MVVM)
    │ Retrofit + OkHttp + Bearer Token
    ▼
FastAPI Backend (Python 3.11)
    │
    ├─ POST /api/recommend/v2 → LangGraph 8节点 Workflow
    ├─ POST /api/voice/chat/v2 → ASR → Agent → TTS
    ├─ REST API (30+ 端点): auth/products/cart/address/preferences/upload/eval/observability
    │
    ├─ Model Gateway (Qwen Chat/Vision/Embedding/Reranker/Omni)
    ├─ Retrieval Layer (Qdrant 1024d ANN + jieba RRF k=60)
    ├─ Decision Layer (7维加权评分)
    ├─ Skill Registry (8 Skill) + ToolManager (8 Tool)
    ├─ MCP Server (标准 JSON-RPC 2.0)
    │
    ├─ PostgreSQL 18 (6表: products/users/addresses/cart_items/user_preferences/checkpoints)
    ├─ Qdrant 1.18 (1024d COSINE 向量检索)
    └─ Redis 7 (四级缓存)
```

### Android 客户端职责

- **页面展示**：Jetpack Compose + Material 3，四 Tab + 10 子路由
- **用户输入**：文本输入、图片选择（Photo Picker + 拍照）、语音录音（长按麦克风）
- **API 请求**：Retrofit 2.11 + OkHttp 4.12 + Gson，Auth 拦截器自动注入 Bearer Token
- **状态管理**：MVVM 架构，ViewModel + StateFlow，UI 状态集中管理
- **结果展示**：ProductCard（评分/推荐理由/风险标签）、ProductDetailSheet（6Tab）、AgentInsightSheet（10Tab）
- **可解释面板**：EvidencePanel / ScoreBreakdown / AgentTracePanel / SkillExecutionPanel / HarnessValidationPanel

### 后端职责

- **Agent 编排**：LangGraph StateGraph，8 节点 Workflow，状态驱动流转
- **多模态理解**：Qwen-VL 商品截图解析（产品名/品牌/规格/价格/卖点提取）
- **RAG 检索**：LLM 查询改写 + Qdrant 1024d ANN + jieba 关键词 RRF k=60 融合 + Qwen Reranker 精排
- **证据融合**：文本/评论/政策/视觉 四类证据合并、去重、绑定 evidence_ids
- **决策评分**：7 维加权评分（预算/场景/参数/评论/视觉/库存/风险扣分）
- **Tool Action**：受控购物车操作（add_to_cart），ToolCallRecord 全量记录
- **数据持久化**：PostgreSQL 6 表 + JSONB 动态字段 + PG/内存双模降级
- **用户态管理**：注册/登录/地址/偏好/购物车/结算 user_id 串联

### 数据流转链路

```
用户输入 (文本/图片/语音)
  → Router Agent (意图识别 + 约束抽取 + 检索计划)
  → [可选] Visual Agent (Qwen-VL 截图解析)
  → Retrieval Agent (LLM改写 + 文本/评论/政策三通道并行检索)
  → Reranker (Qwen3-Rerank 语义重排序)
  → Evidence Checker (证据充足性验证)
  → Decision Agent (硬约束过滤 + 7维评分)
  → Context Compiler (结构化上下文编译)
  → Response Agent (LLM 回答生成 + 闲聊双模)
  → Response Guard (5项守门验证)
  → Android 展示 (MessageBubble + ProductCard + 可解释面板)
```

---

## 四、Agent Runtime 详细说明

### 4.1 为什么用 LangGraph

- LangGraph 提供**声明式状态图**（StateGraph），适合将复杂购物决策拆分为可管理的顺序步骤
- 每个节点是**纯函数**：输入 WorkflowState → 输出 WorkflowState，状态变更可追踪
- 支持条件边、循环、并行节点，表达力强于线性 Pipeline
- `ainvoke` 支持异步节点（Visual/Retrieval 调用外部 API）
- State Checkpoint 支持断点续跑和链路回放

### 4.2 8 节点工作流

| # | 节点 | 输入 | 处理逻辑 | 输出 |
|---|------|------|---------|------|
| 1 | Router Agent | user_query | 规则优先LLM：意图识别(6种含闲聊) + 约束抽取(品类/预算/场景) + 检索计划生成 | intent, constraints, retrieval_plan |
| 2 | Visual Agent | image_url + user_query | Qwen-VL 解析截图 → 提取产品名/品牌/规格/价格/卖点 → 三级降级(L0真实→L1 Mock→L2纯文本) | visual_result + 增强后的 user_query |
| 3 | Retrieval Agent | retrieval_plan + constraints | LLM查询改写(口语→搜索词) + 三通道并行(text/review/policy) + jieba兜底 | retrieved_products + evidence_list |
| 4 | Reranker | retrieved_products | Qwen3-Rerank 语义精排 → 按relevance_score降序重排 → 失败保持原序 | 重排后的 retrieved_products |
| 5 | Evidence Checker | evidence_list | 按intent类型检查证据充足性(最少证据类型矩阵) | sufficiency_report |
| 6 | Decision Agent | products + evidence + constraints | 硬约束过滤(预算×2/品类不匹配排除) + 7维加权评分 + 风险标签 | decision_results |
| 7 | Response Agent | compiled_context | 闲聊/购物双模式Prompt → LLM生成回答 → 6类模板兜底 | answer |
| 8 | Response Guard | answer + evidence | 5项守门验证(evidence_bound/price_accurate/risk_warned/honest/no_evidence) | guard_warnings |

### 4.3 关键设计决策

- **闲聊边缘**：Router 检测 16 个闲聊关键词 → intent=chitchat → 跳过全部检索链，直接 Response Agent 生成友好文字回复。避免"你好"触发商品检索。
- **规则优先 LLM**：品类/预算/意图以规则解析为准（规则覆盖 LLM），防止 LLM 将"买食品"误判为"美妆护肤"
- **WorkflowState 状态传递**：所有 Agent 共享同一个 Pydantic BaseModel，字段追加式更新，避免消息体膨胀

---

## 五、多模态 Evidence RAG 说明

### 5.1 RAG 输入源

| 输入类型 | 来源 | 作用 |
|----------|------|------|
| 用户文本 query | ChatInputBar | 核心搜索意图 |
| 商品截图 | 用户拍照/上传 | Qwen-VL 提取商品参数 |
| 商品结构化信息 | PostgreSQL/JSON | 标题/品牌/品类/价格/SKU |
| 营销描述 | rag_knowledge | 卖点文案关键词匹配 |
| 官方 FAQ | rag_knowledge | 政策/售后/使用说明 |
| 用户评论 | rag_knowledge | 口碑挖掘（≤2★差评风险 + ≥4★好评证据） |
| 用户偏好 | PreferenceMemory + LongTermMemory | 品类/预算/标签个性化增强 |

### 5.2 检索方式

1. **LLM 查询改写**：Qwen Chat 将口语转为搜索关键词（"我想买双跑步穿的鞋"→"跑步鞋 运动鞋 透气"），jieba 单字拆分兜底
2. **Qdrant 向量检索**：1024d COSINE ANN，Qwen3-Embedding 生成 query embedding
3. **jieba 关键词召回**：中文分词 + 停用词过滤 + 全文关键词命中评分（标题加权×2，品类命中+5，单字拆分+3）
4. **RRF 融合**：Reciprocal Rank Fusion k=60，合并语义向量排名和关键词排名，无需分数归一化
5. **Qwen Reranker 精排**：对融合结果做语义重排序，失败保持原序不阻塞

### 5.3 证据类型

| 证据类型 | 前缀 | 示例 |
|----------|------|------|
| 营销描述 | E-MKT-{pid} | 商品卖点文案 |
| 用户评论 | R-{pid}-{idx} | ≤2★差评风险 / ≥4★好评 |
| 政策 FAQ | POL-{pid}-{idx} | 航空携带规则/退换货政策 |
| 视觉解析 | V-{field} | 从截图提取的字段级证据 |

### 5.4 evidence_ids 机制

- 每条推荐结果绑定 `evidence_ids` 列表，每个 ID 可追溯到具体数据源
- 例如：`["E-MKT-p_digital_026", "R-p_digital_026-0", "POL-p_digital_026-1", "V-product_name"]`
- Android EvidencePanel 展示：evidence_id / 类型 / 来源 / 内容摘要 / 置信度
- 用户可逐条验证"这个推荐理由来自哪条评论/哪个 FAQ"

### 5.5 RAG vs 纯 LLM 推荐

| 维度 | 纯 LLM | OmniCart RAG |
|------|--------|-------------|
| 商品信息 | 训练数据记忆（可能过时） | 实时检索数据库（准确） |
| 推荐理由 | 自由生成（可能幻觉） | 绑定 evidence_ids（可追溯） |
| 风险提示 | 可能遗漏 | 评论挖掘 + 政策查询覆盖 |
| 评分依据 | 主观判断 | 7维公式可复算 |

---

## 六、Decision Scoring 说明

### 6.1 为什么需要评分

单一 LLM 推荐依赖模型主观判断，无法量化、无法复算、无法对比。结构化评分系统将推荐转化为可计算的决策问题。

### 6.2 7 维评分维度

| 维度 | 衡量内容 | 权重 |
|------|---------|------|
| 预算匹配 | 商品价格是否在用户预算范围内 | 22% |
| 场景匹配 | 商品是否适合用户使用场景（出差/运动/办公等） | 24% |
| 参数匹配 | 商品规格与用户需求的吻合程度 | 20% |
| 评论置信度 | 来自用户评论的口碑证据强度 | 14% |
| 视觉相似度 | 上传截图与数据库商品的视觉匹配度（V2） | 10% |
| 可购买性 | 库存/可购买状态 | 10% |
| 风险扣分 | 差评风险/政策违规/兼容性问题（负向扣分） | -15% |

### 6.3 评分输出

- `final_score`: 0-1 归一化综合分
- `display_score`: final_score × 10（0-10 分直观展示）
- `score_breakdown`: 7 个子维度得分
- `recommendation_reason`: 一句话推荐理由
- `risk_factors`: 风险标签列表
- `evidence_ids`: 引用的证据 ID

### 6.4 Android 端展示

ScoreBreakdown 组件：7 维进度条颜色编码（绿=高分，黄=中等，红=低分），每项可独立展开查看计算依据。

---

## 七、Tool Action / Skill Registry / ToolManager 说明

### 7.1 两层能力体系

| 概念 | 粒度 | 职责 |
|------|------|------|
| Skill（技能） | 组合能力 | 编排多个 Tool 完成复杂任务，如 product_retrieve = text_search + vector_search + filter |
| Tool（工具） | 原子能力 | 单一功能函数，如 product_text_search、review_search、decision_score_calculator |

### 7.2 ToolManager
- 8 个内置 Tool：product_text_search / product_vector_search / review_search / policy_lookup / compatibility_rule_query / structured_filter / decision_score_calculator / demo_replay_loader
- 每个 Tool 有 Manifest：input/output schema（JSON Schema）、permission_level、risk_level、cacheable
- 权限检查：Agent 调用时验证 `can_agent_use(tool, agent)`
- ToolCallRecord：call_id / tool_name / agent_name / input/output_summary / latency_ms / status 全量记录

### 7.3 Skill Registry
- 8 个内置 Skill：product_visual_parse / product_retrieve / review_risk_mining / policy_check / compatibility_check / decision_score / evidence_validation / demo_replay
- 每个 Skill 定义 required_tools、validation_rules、输入输出规范

### 7.4 购物车 Action 联动
1. 用户在豆仔对话中说"把推荐的那个加入购物车"
2. Agent 识别意图 → 生成 action="add_to_cart" + product_id
3. 调用 `/api/agent/action` → 后端 Cart Service 写入购物车（商品快照：锁定当时价格/标题/图片）
4. Android 端 ProductCard 始终显示加购按钮，用户也可手动点击
5. V2 长期偏好记忆：加购行为自动记录为偏好信号（权重×3）

### 7.5 标准 MCP Protocol (V2)
- 8 个 Tool 同时注册为 MCP 标准工具（JSON-RPC 2.0 over stdio/SSE）
- Claude Desktop / Cursor / VS Code 等标准 MCP 客户端可直接接入
- 与内部 ToolManager 共存：ToolManager 供 Agent Workflow 内部调用，MCP Server 供外部 LLM 客户端调用
- `mcp` Python SDK 1.27 实现，`@server.list_tools()` + `@server.call_tool()` 注册

---

## 八、Android 原生客户端说明

### 8.1 技术栈

| 技术 | 用途 |
|------|------|
| Kotlin | 开发语言 |
| Jetpack Compose | 声明式 UI |
| Material 3 | 设计系统 |
| MVVM | 架构模式 |
| StateFlow | 响应式状态管理 |
| Retrofit 2.11 + OkHttp 4.12 | HTTP 网络请求 |
| Gson | JSON 序列化 |
| Coil 2.6 | 图片异步加载 |
| Android Photo Picker | 图片选择 |
| Jetpack Compose Navigation | 页面路由 |
| MediaRecorder / MediaPlayer | 语音录制/播放（V2） |

### 8.2 模块划分

| 模块 | 核心文件 | 职责 |
|------|---------|------|
| **Product** | ProductListScreen, ProductCard, ProductDetailSheet | 商品列表/卡片/详情弹窗(6Tab) |
| **Douzai (Chat)** | ChatScreen, ChatViewModel, ChatInputBar, VoiceInputOverlay, VoiceRecorder | 多模态对话/语音/Agent 交互 |
| **Cart** | CartScreen, CartViewModel, MockCheckoutSheet | 购物车管理/结算 |
| **Profile** | ProfileScreen, LoginScreen, AddressScreen, PreferenceScreen | 用户/地址/偏好 |
| **Panel** | AgentInsightSheet | V1-Plus 10 Tab Agent 洞察 |
| **Network** | ApiClient, OmniCartApi | Retrofit 配置/API 接口定义 |
| **Model** | Product, RecommendRequest/Response, DecisionResult, EvidenceItem, TraceStepItem 等 | 数据类 |
| **Auth** | AuthViewModel, AuthManager | 登录状态/Token 管理 |
| **Demo** | MockDemoData, PlusMenuSheet | 一键演示 |

### 8.3 架构特点

- **MVVM + StateFlow**：UI 组件观察 ViewModel 的 StateFlow，状态变更自动触发重组
- **Auth 拦截器**：OkHttp Interceptor 自动注入 Bearer Token，无需手动传参
- **键盘适配**：`imePadding()` + 自动滚动到最新消息
- **图片预览**：已选图片预览 + 删除按钮
- **Demo Mode**：一键切换 Mock 模式，不依赖后端即可展示完整 Agent 链路

---

## 九、后端 API 与数据模型

### 9.1 API 端点（30+ 个）

| 模块 | 端点 | 方法 |
|------|------|------|
| Health | `/api/health` | GET |
| Auth | `/api/auth/register, /login, /profile` | POST, POST, GET |
| Products | `/api/products, /api/products/{id}` | GET |
| Recommend | `/api/recommend/v2` | POST |
| Upload | `/api/upload` | POST (multipart) |
| Cart | `/api/cart, /items, /items/{id}, /select-all, /clear` | GET/POST/PUT/DELETE |
| Checkout | `/api/checkout` | POST |
| Addresses | `/api/addresses, /{id}` | GET/POST/PUT/DELETE |
| Preferences | `/api/preferences, /long-term/{user_id}` | GET/PUT/DELETE |
| Agent Action | `/api/agent/action` | POST |
| Voice | `/api/voice/transcribe, /voice/chat/v2` | POST |
| Eval | `/eval, /api/eval/run, /api/eval/results` | GET/POST |
| Observability | `/api/observability/traces, /stats` | GET |
| MCP | `/health, /sse, /messages` | GET/POST (SSE) |

### 9.2 核心数据模型

| 模型 | 关键字段 | 存储 |
|------|---------|------|
| Product | product_id, title, brand, category, sub_category, base_price, skus(JSONB), rag_knowledge(JSONB), image_path | PG/JSON |
| User | user_id, username, password_hash(pbkdf2), token, email, phone | PG/内存 |
| UserPreference | user_id, session_id, preferences(JSONB) | PG/内存 |
| Address | address_id, user_id, name, phone, province/city/district, detail, is_default | PG/内存 |
| CartItem | cart_item_id, user_id, product_id, sku_id, title, price, image_url, quantity, selected, added_by | PG/内存 |
| MockOrder | order_id, user_id, items, total_price, address_id, status | PG/内存 |
| Evidence | evidence_id, source_type, source_id, product_id, content, modality, confidence | 内存(检索生成) |
| DecisionResult | product_id, final_score, display_score, score_breakdown(7维), recommendation_reason, risk_factors, evidence_ids | 内存(评分生成) |
| TraceStep | step_id, agent_name, action, input_summary, output_summary, latency_ms, status | 内存(Workflow生成) |

### 9.3 user_id 串联

user_id 绑定：用户信息 → 地址 → 偏好 → 购物车 → 结算 → 个性化推荐（长期偏好记忆）

---

## 十、Evidence / Score / Trace / Harness 可解释体系

### 10.1 Evidence Panel（证据面板）

- 展示每条推荐的证据列表：证据ID / 类型(E-MKT/R/POL/V) / 来源 / 内容摘要 / 置信度
- 用户可逐条验证推荐理由的数据来源
- Android: EvidenceItem 组件，可折叠展开

### 10.2 Score Panel（评分面板）

- 7 维评分细分展示：每维得分 + 权重 + 进度条颜色编码
- 最终评分 = 加权和 − 风险扣分，0-10 分
- Android: ScoreBreakdown 组件，7 条 LinearProgressIndicator

### 10.3 Trace Panel（链路面板）

- 展示 Agent 执行全链路：Router → Visual → Retrieval → Reranker → EvidenceCheck → Decision → Response → Guard
- 每步显示：agent_name / action / input_summary / output_summary / latency_ms / status
- Android: TraceStepItem 组件，8 步链路可视化

### 10.4 Harness Panel（验证面板）

- 7 项统一校验框架：schema_valid / evidence_bound / score_recalculable / policy_cited / risk_warning / sufficiency_pass / no_empty_answer
- 每项 ✅/❌ 结果 + 详情说明
- Android: HarnessCheckItem 组件，智能展示布尔值/列表/嵌套

### 10.5 与普通聊天式推荐的区别

| 普通聊天推荐 | OmniCart 可解释体系 |
|-------------|-------------------|
| "推荐这款耳机，音质很好" | "推荐QCY MeloBuds，评分5.0/10，证据来自: 学生党小明5★评论、官方FAQ续航说明、Anker品牌对比" |
| 无评分依据 | 7维分项可视化 + 公式可复算 |
| 无法追溯 | evidence_ids 追溯到每条评论/FAQ |
| 无法验证 | Harness 7项自动校验 |

---

## 十一、完整用户使用流程（典型业务闭环）

1. 用户打开 Android App → 看到四 Tab（商品/豆仔/购物车/我的）
2. 商品页浏览充电宝 → 品类筛选"数码电子" → 看到 Anker 20000mAh 充电宝
3. 点击进入商品详情 → 查看参数/评论/FAQ
4. 点击"问豆仔"→ 跳转豆仔智能页，商品上下文自动带入
5. 用户语音输入："我经常出差坐飞机，iPhone 15 和 MacBook，这个充电宝能买吗？有没有更适合的？"
6. ASR 转写文字立刻显示在聊天框 → 开始分析
7. Agent Workflow 执行：Router 检测意图+约束 → 无图片跳过 Visual → Retrieval 三通道并行 → Reranker 精排 → EvidenceCheck → Decision 7维评分 → Response 生成回答
8. 豆仔回复：推荐 Anker 充电宝（推荐分 7.2/10），引用证据：FAQ"可带上飞机"、用户评价"出差神器"
9. 聊天框展示 ProductCard + 播放语音回复（可选）
10. 用户点击"加入购物车"→ Agent Action 写入购物车
11. 切换到购物车 Tab → 看到商品 + "由豆仔推荐加入"标记
12. 全选 → 模拟结算 → 选择地址 → 完成 Mock Order
13. 个人中心查看偏好画像 → 系统已自动学习"常搜数码电子、预算150元左右"

---

## 十二、技术难点与解决方案

### 1. 多模态输入与商品信息融合

- **难点**：用户可能同时提供文字+图片+语音，三种模态的信息需要统一提取、去重、融合
- **方案**：Qwen-VL 解析图片 → 提取结构化参数增强文字 query；Qwen-Omni 语音转文字后复用文字 Agent 链路；所有模态最终汇聚为统一的 user_query + visual_result + constraints

### 2. RAG 证据检索与推荐结果绑定

- **难点**：如何确保每个推荐都有可追溯的证据，而非 LLM 自由发挥
- **方案**：evidence_ids 机制 — 每条推荐绑定从数据库检索到的具体证据 ID（评论/FAQ/视觉解析），Android 端逐条展示。Response Guard 验证 evidence_bound 守门。

### 3. Agent Workflow 状态流转

- **难点**：8 个 Agent 协作时如何保证状态一致性、可追踪、可复现
- **方案**：LangGraph StateGraph + 单一 WorkflowState Pydantic 模型，每个节点是纯函数追加式更新。State Checkpoint JSON 持久化支持断点续跑。

### 4. 推荐结果可解释

- **难点**：用户需要理解"为什么推荐这个"，而非盲目接受
- **方案**：7 维 Decision Scoring + ScoreBreakdown 可视化 + Evidence Panel 证据溯源 + Harness 自动验证。所有推荐分可公式复算。

### 5. Tool Action 与业务系统联动

- **难点**：Agent 如何安全、可控地操作购物车等业务系统
- **方案**：ToolManager 管理工具调用，Manifest 定义权限，V1 只读 + 白名单 add_to_cart。Agent 不直接操作数据库，通过 agent_action_service 调用 Cart Service。

### 6. Android 端复杂状态展示

- **难点**：Agent 返回的数据结构复杂（产品列表+评分+证据+链路+验证），需要合理组织 UI
- **方案**：ProductDetailSheet 6 Tab + AgentInsightSheet 10 Tab + StateFlow 状态管理。每个面板独立渲染，互不阻塞。

### 7. 数据串联

- **难点**：用户/地址/偏好/购物车/结算/推荐 6 类数据通过 user_id 串联
- **方案**：PostgreSQL 6 表 + Repository 抽象层 + 工厂注入 + PG/内存双模降级。Auth Token → user_id → 全链路透传。

---

## 十三、项目亮点总结

### 产品完整性
1. 四 Tab 完整电商 App，非聊天窗口 Demo
2. 商品浏览 → 图文咨询 → 加购 → 结算，端到端闭环
3. 用户注册/登录/地址/偏好，完整的用户体系
4. Android 原生交付，APK 可安装

### Agent 编排能力
1. LangGraph 8 节点 Workflow，非单一 LLM 自由生成
2. 闲聊/购物双模式，智能分流
3. 规则优先 LLM，防止幻觉
4. State Checkpoint 持久化 + 链路回放

### RAG 检索能力
1. LLM 查询改写 + Qdrant 向量 + jieba 关键词 RRF 三重融合
2. 文本/评论/政策/视觉四类证据并行检索
3. evidence_ids 全链路可追溯
4. Qwen Reranker 语义精排

### 可解释推荐能力
1. 7 维 Decision Scoring + 公式可复算
2. Evidence/Source/Trace/Harness 四层可解释面板
3. Android 端进度条颜色编码可视化

### Android 原生工程
1. Kotlin + Jetpack Compose + Material 3 + MVVM
2. 四 Tab + 10 子路由 + 状态管理
3. 图片选择/上传 + 语音录音/播放
4. Demo Mode 一键演示

### 后端服务化
1. FastAPI 30+ 端点 + Pydantic v2 数据契约
2. Repository 抽象层 + PG/内存双模 + 透明降级
3. 31 单元测试 + 评测 Dashboard

### 工具调用治理
1. Skill Registry (8 Skill) + ToolManager (8 Tool) 双层能力体系
2. Manifest 权限控制 + ToolCallRecord 全量记录
3. 标准 MCP Protocol 外部接入
4. Preference Memory 多轮 + LongTermMemory 跨会话

### 端到端闭环
1. 语音/文字/图片三种输入 → Agent 决策 → 商品推荐 → 加购 → 结算
2. 完整用户态数据：注册/登录/地址/偏好/购物车/订单

---

## 十四、简历关键词

### AI Agent
- **LangGraph Workflow** — 8 节点 StateGraph 编排 Agent 决策链路
- **Multi-Agent** — Router/Visual/Retrieval/Reranker/EvidenceCheck/Decision/Response/Guard
- **State Checkpoint** — JSON 持久化，支持断点续跑和链路回放
- **Tool Action** — Agent 受控调用购物车 API
- **Skill Registry** — 8 个组合技能注册管理
- **ToolManager** — 8 个原子工具 + Manifest Schema + 权限控制
- **MCP Protocol** — 标准 JSON-RPC 2.0，Claude Desktop 可接入

### RAG
- **多模态 Evidence RAG** — 文本/评论/政策/视觉四类证据融合
- **Hybrid Search** — Qdrant 1024d ANN + jieba 关键词 RRF k=60 融合
- **Qwen Reranker** — 语义精排
- **LLM Query Rewrite** — 口语→搜索关键词改写
- **evidence_ids** — 推荐结论到数据源的全链路可追溯

### 后端
- **FastAPI** — Python 后端框架，30+ REST API
- **PostgreSQL 18** — 6 表关系型存储 + JSONB 动态字段
- **Qdrant 1.18** — 1024d COSINE 向量检索引擎
- **Redis 7** — 四级缓存（Visual/Search/Rewrite/Workflow）
- **SQLAlchemy 2.0 async** — 异步 ORM + Alembic 迁移
- **Repository Pattern** — PG/内存双模 + 工厂注入 + 透明降级
- **Pydantic v2** — 数据校验与 API 契约

### Android
- **Kotlin + Jetpack Compose + Material 3** — 原生 UI
- **MVVM + StateFlow** — 响应式架构
- **Retrofit 2.11 + OkHttp 4.12** — 网络层
- **Coil 2.6** — 异步图片加载
- **Compose Navigation** — 页面路由
- **MediaRecorder/MediaPlayer** — 语音功能

### 可解释性
- **Decision Scoring** — 7 维加权评分公式
- **ScoreBreakdown** — 分项可视化
- **Evidence Panel** — 证据来源追溯
- **Trace Panel** — 执行链路可视化
- **Harness** — 推荐结果自动验证

### 工程化
- **31 单元测试** — pytest + pytest-asyncio
- **Evaluation Dashboard** — Chart.js 可视化评测面板
- **LLM Observability** — Gateway 全量追踪 + Token/P50/P95 统计
- **Long-Term Memory** — 跨会话用户偏好学习 + 时间衰减
- **Qwen-Omni Voice** — 语音导购（ASR + TTS）

---

## 十五、简历写作建议

### 项目标题

推荐格式：`OmniCart Agent — 多模态智能导购 Agent 系统 (Android + FastAPI + LangGraph)`

### 项目简介怎么写

突出三句话：(1) 解决什么问题 (2) 用了什么核心技术 (3) 产出了什么结果

### 必须保留的 Bullet

- LangGraph 8 节点 Multi-Agent Workflow 替代单一 LLM
- 多模态 Evidence RAG + evidence_ids 全链路追溯
- 7 维 Decision Scoring 可解释推荐
- Android 原生完整产品交付（非 WebView 壳）
- 语音/文字/图片三种输入模态

### 不适合写进简历的

- V1 只读边界、比赛兜底机制、Mock 模式、开发约束
- 模块内部文件清单
- "预留扩展"、"未来规划"
- 技术栈平铺堆砌

### 适合面试展开的

- LangGraph vs 纯 LLM 的区别和取舍
- RRF 融合为什么比加权求和好
- 规则优先 LLM 的工程经验
- 多模态输入的降级策略
- 证据绑定和可解释性的工程实现

### AI Agent 岗位版本

强调：LangGraph 编排、Multi-Agent 状态管理、Tool/Skill 治理、MCP 协议、Agent 可观测性

### Android/全栈岗位版本

强调：MVVM + StateFlow、Retrofit 网络层、30+ API 对接、语音/图片/文本多模态输入、可解释面板

---

## 十六、Codex 项目事实摘要

OmniCart Agent 是一个面向电商购物决策场景的多模态智能导购 Agent 系统，由 Android 原生客户端（Kotlin + Jetpack Compose + Material 3 + MVVM）和 FastAPI 后端 Agent Runtime（Python 3.11 + LangGraph + PostgreSQL + Qdrant + Redis）组成。

核心技术架构：使用 LangGraph StateGraph 构建 8 节点 Multi-Agent Workflow（Router → Visual → Retrieval → Reranker → EvidenceCheck → Decision → Response → Guard），每个节点为纯函数，输入输出通过 WorkflowState Pydantic 模型传递，替代单一 LLM 自由生成，实现可追踪、可验证的决策流水线。

多模态 Evidence RAG 系统融合四类证据（商品参数、用户评论、政策FAQ、视觉解析），采用 LLM 查询改写 + Qdrant 1024d 向量 ANN + jieba 中文分词 RRF k=60 融合 + Qwen Reranker 语义精排的混合检索链路。所有推荐结论绑定 evidence_ids，可追溯到具体数据源。

7 维 Decision Scoring（预算匹配/场景匹配/参数适配/评论置信度/视觉相似度/可购买性/风险扣分）生成 0-10 分可解释评分，Android 端 ScoreBreakdown 进度条颜色编码可视化。

Android 客户端为完整的四 Tab 原生应用（商品/豆仔智能/购物车/个人中心），支持文本输入、图片选择上传、长按语音录音、商品浏览/搜索/详情、购物车管理/模拟结算、用户注册/登录/地址/偏好管理。豆仔智能页为核心 AI Agent 交互入口，支持多轮对话、闲聊分流、Agent 洞察面板（10 Tab）、受控加购 Action。V2 新增全屏语音输入界面和语音消息标识。

后端 30+ REST API 端点，PostgreSQL 18 管理 6 张业务表（JSONB 动态字段 + async SQLAlchemy 2.0），Qdrant 1.18 提供语义向量检索，Redis 7 提供四级缓存（Visual/Search/Rewrite/Workflow）。Repository 抽象层实现 PG/内存双模 + 工厂注入 + 透明降级。

Tool 体系双层设计：Skill Registry 管理 8 个组合技能，ToolManager 管理 8 个原子工具（含 Manifest JSON Schema + 权限控制 + ToolCallRecord），同时实现标准 MCP Protocol（JSON-RPC 2.0 over stdio/SSE）。V2 新增用户长期偏好记忆（跨会话行为信号学习 + 时间衰减）、LLM 全链路可观测性（Gateway 全量追踪 + Token/P50/P95 统计）、Qwen-Omni 语音导购（ASR → Agent → TTS）、Evaluation Dashboard（Chart.js 可视化评测面板）。

工程实践：31 个单元测试（pytest + pytest-asyncio），start-databases.bat 一键启动基础设施，run.py 一键启动后端，评测 Dashboard 可视化 10 条 golden queries 的通过率/延迟/品类准确率。

---

## 十七、需要确认的功能

以下功能基于代码和文档分析，但可能存在实现差异：

1. **Visual Grounding 字段级绑定**：`vision/visual_grounding.py` 已实现但调用频率低，实际 Demo 中视觉证据主要来自 Visual Agent 的 `evidence_list`
2. **Counterfactual Recommendation**：`decision/counterfactual.py` 已实现，0 结果时建议放宽预算，但真实触发场景有限
3. **Neo4j GraphRAG**：NetworkX 轻量图已实现，Neo4j 标注为 V3 扩展
4. **在线反馈学习 / Bandit 排序**：未实现，标注为可选
5. **iOS SwiftUI 客户端**：未实现，标注为跳过

> **代码与文档一致性**：答辩QA手册的架构描述与当前代码一致。README.md 的 API 端点列表覆盖当前所有已实现接口。TASK_LIST.md 的任务状态与实际代码完成度一致。
