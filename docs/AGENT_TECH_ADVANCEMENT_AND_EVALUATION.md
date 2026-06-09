# OmniCart Agent 技术先进性评审与优化路线图

> **文档定位**：项目组会议技术讨论材料，非 README、非简历材料。
> **生成日期**：2026-05-24
> **基于代码版本**：V2-Complete (69 测试全部通过)
> **原则**：以代码为准，文档与代码不一致处以代码为准。

---

## 一、当前实现现状盘点

### 1.1 后端目录结构概览

```
backend/app/
├── main.py                    # FastAPI 应用工厂，15 路由注册，CORS/StaticFiles
├── api/ (15 文件)              # HTTP 协议适配层
│   ├── health.py              # GET /api/health
│   ├── recommend.py           # POST /api/recommend (V0) + /api/recommend/v2 (V2)
│   ├── upload.py              # POST /api/upload (含魔数校验)
│   ├── products.py            # GET /api/products
│   ├── cart.py                # 购物车 CRUD
│   ├── checkout.py            # POST /api/checkout (批量删除)
│   ├── auth.py                # 注册/登录 (PBKDF2-SHA256)
│   ├── address.py             # 收货地址 CRUD
│   ├── preference.py          # 偏好 REST + 长期偏好 API
│   ├── agent_actions.py       # POST /api/agent/action (加购记录)
│   ├── observability.py       # LLM 追踪统计 P50/P95
│   ├── voice.py               # ASR→Agent→TTS 语音导购
│   ├── eval.py                # 评测 API (run/results/golden)
│   └── eval_dashboard.py      # HTML 可视化评测面板 (Chart.js)
├── agents/ (6 文件)           # 5 核心 Agent + BaseAgent 抽象基类
│   ├── base.py                # card + execute(state)→state + trace
│   ├── router_agent.py        # 意图识别+约束抽取+检索计划 (规则+LLM)
│   ├── visual_agent.py        # Qwen-VL 商品截图→VisualResult
│   ├── retrieval_agent.py     # text/review/policy 三通道并行检索
│   ├── decision_agent.py      # 硬约束过滤+7维加权评分
│   └── response_agent.py      # LLM优先+模板兜底
├── core/ (4 文件)             # 全局基础设施
│   ├── config.py              # .env 环境变量 (含 USE_REDIS 修复)
│   ├── database.py            # SQLAlchemy async engine + run_async() 共享桥接
│   ├── cache.py               # Redis get-or-compute + 命中率统计
│   ├── redis_client.py        # Redis 连接单例 (透明降级)
│   └── qdrant_client.py       # Qdrant 连接单例
├── model_gateway/ (8 文件)    # Qwen 全栈模型网关 (全部 AsyncClient)
│   ├── gateway.py             # ModelGateway 单例 (chat/vision/embed/rerank)
│   ├── model_config.yaml      # 7 能力→模型映射
│   ├── qwen_chat.py           # async Qwen-Chat
│   ├── qwen_vision.py         # async Qwen-VL
│   ├── qwen_embedding.py      # async text-embedding-v4 (1024d)
│   ├── qwen_reranker.py       # async qwen3-rerank
│   ├── qwen_omni.py           # Qwen-Omni 语音 (OpenAI SDK)
│   └── mock_model.py          # MockChat/MockEmbedding/mock_vision_parse
├── workflow/ (2 文件)         # LangGraph 编排
│   ├── graph.py               # 8 节点 StateGraph + 条件边 + Checkpoint
│   └── workflow.yaml          # 工作流文档参考 (非运行时解析)
├── schemas/ (10 文件)         # Pydantic 数据契约
│   ├── product.py             # Product/Sku/RagKnowledge/FaqItem/ReviewItem
│   ├── workflow.py            # WorkflowState/Constraints/RetrievalPlan/TraceStep
│   ├── decision_result.py     # DecisionResult/ScoreBreakdown (7维)
│   ├── evidence.py            # Evidence 通用模型
│   ├── visual.py              # VisualResult/VisualEvidence
│   ├── a2a.py                 # AgentCard/AgentMessage/Artifact
│   ├── cart.py                # Cart/CartItem/CheckoutRequest
│   ├── auth.py                # RegisterRequest/LoginRequest/AuthResponse
│   ├── address.py             # AddressCreate/Update/Response
│   └── preference.py          # PreferenceUpdate
├── retrieval/ (1 文件)        # 检索层
│   └── text_retriever.py      # jieba+Qdrant RRF k=60 融合 + Redis 缓存
├── decision/ (3 文件)         # 决策层
│   ├── scoring.py             # 7 维加权评分公式
│   ├── rules.py               # 共享规则: 品类/预算/场景/魔数 (2026-05-24 新增)
│   └── counterfactual.py      # 反事实推荐
├── repositories/ (12 文件)    # 数据访问层 (ABC + 双实现 + 工厂)
│   ├── product_repo.py        # 工厂 + __getattr__ 惰性加载
│   ├── base_product_repo.py   # 商品仓库 ABC
│   ├── json_product_repo.py   # JSON 文件实现
│   ├── pg_product_repo.py     # PG 实现 (共享 run_async + plainto_tsquery)
│   ├── vector_repo.py         # 向量仓库工厂
│   ├── base_vector_repo.py    # 向量仓库 ABC
│   ├── qdrant_vector_repo.py  # Qdrant 实现
│   ├── stub_vector_repo.py    # 无向量库降级
│   ├── pg_cart_repo.py        # 购物车 PG (含 batch_remove)
│   ├── pg_preference_repo.py  # 偏好 PG (共享 run_async)
│   ├── user_repo.py           # 用户 PG (PBKDF2 哈希)
│   └── address_repo.py        # 地址 PG
├── context/ (1 文件)          # 上下文编译
│   └── compiler.py            # 结构化编译决策上下文
├── memory/ (2 文件)           # 偏好记忆
│   ├── preference_memory.py   # 会话级多轮约束合并 + 话题切换
│   └── long_term.py           # V2 长期偏好 (行为信号+时间衰减)
├── mcp/ (3 文件)              # 标准 MCP Server
│   ├── server.py              # MCP Server (stdio + SSE/HTTP)
│   ├── tools.py               # 8 Tool 定义 + Handler
│   └── __main__.py            # python -m 入口
├── observability/ (1 文件)    # 可观测性
│   └── collector.py           # TraceCollector + LLMSpan (13字段)
├── verification/ (2 文件)     # 验证层
│   ├── response_guard.py      # 5 项回答守门规则
│   └── evidence_checker.py    # 按意图类型的证据充足性检查
├── skills/ (1 文件)           # Skill Registry
│   └── registry.py            # 8 内置 Skill 注册+查找
├── tools/ (1 文件)            # ToolManager
│   └── manager.py             # 8 Tool + Manifest + 权限 + 记录
├── vision/ (2 文件)           # 视觉模块
│   ├── multimodal_fallback.py # L0真实→L1Mock→L2纯文本 3级降级
│   └── visual_grounding.py    # 字段级视觉证据绑定
├── harness/ (1 文件)          # Decision Harness
│   └── decision_harness.py    # 7 项统一校验框架
├── graph/ (1 文件)            # 证据图谱
│   └── evidence_graph.py      # NetworkX 商品-证据-风险图
├── indexing/ (1 文件)         # 分层索引
│   └── category_index.py      # 品类→子品类→品牌→商品 4级
├── a2a/ (1 文件)              # A2A-lite
│   └── dispatcher.py          # AgentMessage/Artifact 同进程分发
└── models/ (5 文件)           # SQLAlchemy ORM
    ├── product.py             # ProductModel (JSONB skus + rag_knowledge)
    ├── cart_item.py           # CartItemModel (商品快照)
    ├── user.py                # UserModel (pbkdf2 + token)
    ├── user_preference.py     # UserPreferenceModel (JSONB)
    └── address.py             # AddressModel
```

### 1.2 Android 目录结构概览

```
android-client/app/src/main/java/com/omnicart/agent/
├── MainActivity.kt                    # ComponentActivity + edge-to-edge
├── MainScreen.kt                      # Scaffold + BottomNavBar + NavHost (10路由)
├── core/
│   ├── config/AppConfig.kt            # BASE_URL="http://127.0.0.1:8006/", TIMEOUT=30s
│   ├── network/
│   │   ├── ApiClient.kt               # Retrofit+OkHttp (BuildConfig.DEBUG 控制日志)
│   │   └── OmniCartApi.kt             # 30+ API 接口定义 + 全部数据类
│   ├── model/
│   │   ├── Product.kt                 # 28字段 (含Sku/RagKnowledge)
│   │   ├── RecommendRequest.kt        # user_query + image_url + demo_mode
│   │   ├── RecommendResponse.kt       # 8 字段
│   │   └── DecisionResult.kt          # ScoreBreakdown (7维)
│   └── theme/
│       ├── Color.kt                   # 评分色 (绿≥8/橙≥6/红<6) + 风险标签色
│       ├── Theme.kt                   # OmniCartTheme (lightColorScheme)
│       └── Type.kt                    # Typography
├── feature/
│   ├── chat/
│   │   ├── ChatScreen.kt              # 主界面: LazyColumn + ProductCard + DetailSheet
│   │   ├── ChatViewModel.kt           # AndroidViewModel: onSend/uploadImage/toggleDemo
│   │   ├── ChatUiState.kt             # messages/isLoading/products/decisionResults...
│   │   ├── ChatInputBar.kt            # 输入栏: 📷+输入框+🎤/发送+➕
│   │   ├── MessageBubble.kt           # 用户/豆仔消息气泡
│   │   ├── VoiceRecorder.kt           # MediaRecorder 封装 (M4A)
│   │   └── VoiceInputOverlay.kt       # 全屏暗屏 + 波纹动画
│   ├── shop/
│   │   ├── ProductListScreen.kt       # 商品列表: LazyVerticalGrid + 品类筛选
│   │   └── ProductListViewModel.kt    # 分页加载 + 品类过滤
│   ├── product/
│   │   ├── ProductCard.kt             # Card: Coil图片+标题+品牌+价格+评分+推荐理由+风险
│   │   └── ProductDetailSheet.kt      # ModalBottomSheet: 推荐/证据/评分/链路/技能/验证 6Tab
│   ├── cart/
│   │   ├── CartScreen.kt              # 购物车列表 + 合计 + 结算
│   │   └── CartViewModel.kt           # 增删改 + 多选/全选 + 异常报告
│   ├── auth/
│   │   ├── LoginScreen.kt             # 登录/注册表单
│   │   ├── AuthViewModel.kt           # 注册/登录状态管理
│   │   └── AuthManager.kt             # SharedPreferences Token 持久化
│   ├── address/
│   │   ├── AddressScreen.kt           # 地址列表 + SnackbarHost
│   │   └── AddressViewModel.kt        # CRUD + 默认地址互斥
│   ├── preference/
│   │   ├── PreferenceScreen.kt        # 偏好表单
│   │   └── PreferenceViewModel.kt     # API 同步 + 增量合并
│   ├── profile/
│   │   └── ProfileScreen.kt           # 登录/未登录双态 + 地址/偏好入口
│   ├── panel/
│   │   ├── EvidencePanel.kt           # 可折叠证据列表 (按 source_type 分色图标)
│   │   ├── AgentTracePanel.kt         # 可折叠时间轴 (状态色点)
│   │   ├── ScoreBreakdownPanel.kt     # 7 维进度条颜色编码
│   │   ├── HarnessValidationPanel.kt  # 5 项守门规则 ✅/❌
│   │   ├── SkillExecutionPanel.kt     # 技能执行状态列表
│   │   └── AgentInsightSheet.kt       # 10 Tab 全量洞察面板
│   ├── demo/
│   │   ├── DemoModeSwitch.kt          # TopAppBar 内 Demo 开关
│   │   ├── DemoScenarioSelector.kt    # 7 个预设场景
│   │   ├── MockDemoData.kt            # 完整预置 Evidence/Trace/Harness
│   │   └── PlusMenuSheet.kt           # ➕弹出菜单 (快捷场景+图片来源)
│   └── upload/
│       └── ImagePicker.kt             # ImagePreview: 64dp缩略图+删除
└── res/
    ├── xml/
    │   ├── file_paths.xml              # FileProvider → camera/ 子目录
    │   └── network_security_config.xml # 仅 localhost/模拟器 允许明文 (2026-05-24 新增)
    └── values/
        ├── strings.xml                 # 30+ UI 字符串提取 (2026-05-24 新增)
        └── themes.xml                  # Material 3 主题
```

### 1.3 模块实现状态总表

| 模块 | 当前状态 | 代码路径 | 关键类/函数 | 是否可运行 | 备注 |
|------|----------|----------|-------------|-----------|------|
| **Agent Runtime** | 已实现 | `workflow/graph.py` | `build_workflow()` / `run_workflow()` | ✅ | 8节点 LangGraph StateGraph |
| **Router Agent** | 已实现 | `agents/router_agent.py` | `RouterAgent.execute()` / `_rule_based_parse()` | ✅ | 规则优先+LLM增强，使用共享 rules.py |
| **Visual Agent** | 已实现 | `agents/visual_agent.py` | `VisualAgent.parse()` | ✅ | Qwen-VL + Redis缓存 + JSON解析 |
| **Retrieval Agent** | 已实现 | `agents/retrieval_agent.py` | `RetrievalAgent.execute()` | ✅ | 三通道(text/review/policy) + 批量加载优化 |
| **Decision Agent** | 已实现 | `agents/decision_agent.py` | `DecisionAgent.execute()` | ✅ | 硬约束过滤+7维评分+风险标签 |
| **Response Agent** | 已实现 | `agents/response_agent.py` | `ResponseAgent.execute()` | ✅ | LLM优先+模板兜底 |
| **RAG (检索)** | 已实现 | `retrieval/text_retriever.py` | `TextRetriever.search()` / `hybrid_search()` | ✅ | jieba+Qdrant RRF k=60 |
| **RAG (重排)** | 已实现 | `workflow/graph.py:_node_reranker` | `_gateway.rerank()` | ✅ | Qwen Reranker + plainto_tsquery |
| **Context Compiler** | 已实现 | `context/compiler.py` | `ContextCompiler.compile()` | ✅ | 7段结构化上下文 |
| **Decision Scoring** | 已实现 | `decision/scoring.py` | `DecisionScoring.score()` | ✅ | 7维加权 (budget_fit×0.22+...) |
| **Shared Rules** | 已实现 | `decision/rules.py` | `detect_category/budget/scenario/validate_image_magic` | ✅ | 2026-05-24 新增 |
| **Response Guard** | 已实现 | `verification/response_guard.py` | `ResponseGuard.check()` | ✅ | 5项守门规则 |
| **Evidence Checker** | 已实现 | `verification/evidence_checker.py` | `EvidenceSufficiencyChecker.check()` | ✅ | 按意图类型检查 |
| **Harness** | 已实现 | `harness/decision_harness.py` | `DecisionHarness.validate()` | ✅ | 7项校验框架 |
| **Preference Memory** | 已实现 | `memory/preference_memory.py` | `PreferenceMemory.merge_constraints()` | ✅ | 多轮约束合并+话题切换 |
| **Long-Term Memory** | 已实现 | `memory/long_term.py` | `LongTermMemory.record_search/merge_with_session()` | ✅ | 行为信号+时间衰减+PG/JSON |
| **Skill Registry** | 已实现 | `skills/registry.py` | `SkillRegistry` | ✅ | 8内置Skill |
| **ToolManager** | 已实现 | `tools/manager.py` | `ToolManager` | ✅ | 8Tool+Manifest+权限+V1只读 |
| **MCP Server** | 已实现 | `mcp/server.py` | `OmniCart MCPServer` (stdio+SSE) | ✅ | JSON-RPC 2.0, 8 Tool |
| **Eval Dashboard** | 已实现 | `api/eval.py` + `api/eval_dashboard.py` | Chart.js 可视化面板 | ✅ | 10 golden queries |
| **Observability** | 已实现 | `observability/collector.py` | `TraceCollector` + `LLMSpan` | ✅ | P50/P95/Token统计 |
| **Redis Cache** | 已实现 | `core/cache.py` | `cached(key,ttl,factory)` | ✅ | 四级缓存+透明降级 |
| **Voice (ASR+TTS)** | 已实现 | `api/voice.py` | `voice_chat_v2()` | ✅ | ASR→Agent→TTS |
| **Checkpoint** | 已实现 | `workflow/checkpoint.py` | `CheckpointStore.save/load()` | ✅ | JSON文件持久化 |
| **Evidence Graph** | 已实现 | `graph/evidence_graph.py` | NetworkX 商品-证据-风险图 | ✅ | 优雅降级 |
| **Visual Grounding** | 已实现 | `vision/visual_grounding.py` | `VisualGrounding.ground()` | ✅ | 字段级证据绑定 |
| **Counterfactual** | 已实现 | `decision/counterfactual.py` | 反事实推荐 | ✅ | 0结果时建议 |
| **Multimodal Fallback** | 已实现 | `vision/multimodal_fallback.py` | `MultimodalFallback.try_visual_parse()` | ✅ | L0→L1→L2 |
| **Category Index** | 已实现 | `indexing/category_index.py` | 4级分层索引 | ✅ | 品类→子品→品牌→商品 |
| **A2A-lite** | 已实现 | `a2a/dispatcher.py` | `Dispatcher.dispatch()` | ✅ | 同进程AgentMessage |
| **Android Evidence Panel** | 已实现 | `feature/panel/EvidencePanel.kt` | 可折叠+按source_type分色 | ✅ | 文本/评论/政策/视觉 |
| **Android Trace Panel** | 已实现 | `feature/panel/AgentTracePanel.kt` | 可折叠时间轴+状态色点 | ✅ | 8步完整链路 |
| **Android Harness Panel** | 已实现 | `feature/panel/HarnessValidationPanel.kt` | 5项守门✅/❌ | ✅ | |
| **Android Score Panel** | 已实现 | `feature/panel/ScoreBreakdownPanel.kt` | 7维进度条颜色编码 | ✅ | |
| **Android Skill Panel** | 已实现 | `feature/panel/SkillExecutionPanel.kt` | 技能执行状态列表 | ✅ | |
| **PG 双模 Repository** | 已实现 | `repositories/` 全部6类 | ABC+JSON/PG双实现+工厂注入 | ✅ | 透明降级 |
| **Upload 魔数校验** | 已实现 | `api/upload.py` | `validate_image_magic()` | ✅ | 2026-05-24 新增 |
| **workflow.yaml 解析** | 未实现 | `workflow/workflow.yaml` | — | ❌ | 仅作文档参考，graph.py 硬编码 |

---

## 二、Agent Runtime 架构

### 2.1 一次完整请求的调用链

以下以代码实际执行为准：

```
Android ChatScreen.onSend()
  → ChatViewModel.onSend()
    → [可选] uploadImage(sentImageUri) → POST /api/upload
    → ApiClient.api.recommend(RecommendRequest)
      → POST /api/recommend/v2  (HTTP)

FastAPI recommend_v2()                                  # api/recommend.py:223
  → run_workflow(user_query, image_url, session_id)      # workflow/graph.py:234
    → WorkflowState(...) 初始化                          # schemas/workflow.py
    → [可选] CheckpointStore.load(session_id)            # workflow/checkpoint.py
    → wf.ainvoke(state)                                  # LangGraph StateGraph
      → _node_router(state)                              # async
      │   ├── RouterAgent.execute(state)                 # agents/router_agent.py
      │   │   ├── [LLM] gateway.chat("intent_understanding", prompt)
      │   │   │   → QwenChat.generate(prompt, system)    # async httpx.AsyncClient
      │   │   └── _rule_based_parse(query)               # 规则兜底
      │   │       └── detect_category/budget/scenario()  # decision/rules.py 共享规则
      │   ├── PreferenceMemory.merge_constraints()       # memory/preference_memory.py
      │   ├── [可选] LongTermMemory.merge_with_session() # memory/long_term.py
      │   └── return state                               # state.intent/constraints/retrieval_plan 已填充
      │
      ├── [条件] _node_visual(state)                     # async (仅当 image_url 非空)
      │   └── VisualAgent.parse(image_url, user_query)   # agents/visual_agent.py
      │       └── gateway.vision(image_bytes=..., prompt=...)  # async Qwen-VL
      │           → VisualResult (product_name/brand/price/...) # schemas/visual.py
      │
      ├── _node_retrieval(state)                         # async
      │   └── RetrievalAgent.execute(state)              # agents/retrieval_agent.py
      │       ├── _llm_extract_keywords(user_query)      # LLM查询改写 (Redis缓存)
      │       ├── _text_channel(state)                   # async
      │       │   └── TextRetriever.search(query, top_k, category, ...)
      │       │       ├── jieba.cut(query) → keywords    # 每查询缓存一次
      │       │       ├── ProductRepository.filter_by()  # 品类/价格过滤
      │       │       ├── _compute_rich_score()          # 关键词匹配评分
      │       │       └── [可选] hybrid_search()         # Qdrant ANN + RRF k=60
      │       ├── _review_channel(state)                 # 从已检索结果直接提取
      │       │   └── 遍历 rag_knowledge.user_reviews    # 低分(≤2)风险+高分(≥4)正面
      │       └── _policy_channel(state)                 # 从已检索结果直接提取
      │           └── 遍历 rag_knowledge.official_faq     # 政策关键词匹配
      │
      ├── _node_reranker(state)                          # async
      │   └── gateway.rerank(query, documents, top_n)    # Qwen Reranker 精排
      │       └── [降级] 保持原序 (try/except)
      │
      ├── _node_evidence_check(state)                    # sync
      │   └── EvidenceSufficiencyChecker.check(state)    # verification/evidence_checker.py
      │       └── state.sufficiency_report 已填充
      │
      ├── [条件] _node_decision(state)                   # sync (有结果→decision, 无→response)
      │   └── DecisionAgent.execute(state)               # agents/decision_agent.py
      │       ├── 硬约束过滤: budget_max×2 / 品类不匹配 → 排除
      │       └── DecisionScoring.score(product, query, ...)  # decision/scoring.py
      │           ├── budget_fit      × 0.22
      │           ├── scenario_fit    × 0.24
      │           ├── spec_match      × 0.20
      │           ├── review_confidence × 0.14
      │           ├── visual_similarity × 0.10
      │           ├── availability_score × 0.10
      │           └── risk_penalty    × 0.15 (减法)
      │
      ├── _node_response(state)                          # async
      │   └── ResponseAgent.execute(state)               # agents/response_agent.py
      │       ├── [优先] ContextCompiler.compile(state)  # context/compiler.py
      │       │   └── 7段结构化上下文 (需求/约束/图片/商品/证据/风险/检索计划)
      │       ├── gateway.chat("chat_generation", prompt) # LLM 生成
      │       └── [兜底] 模板回答 (商品名+价格+评分+风险)
      │
      └── _node_guard(state)                             # sync
          └── ResponseGuard.check(state)                 # verification/response_guard.py
              └── state.harness_report 已填充 (5项检查)

    → [可选] CheckpointStore.save(session_id, "guard", state)
    → return WorkflowState (Pydantic model)

  → RecommendResponse(...) 序列化返回                    # api/recommend.py:238
    → HTTP 200 JSON

Android ChatViewModel.onSend() 回调
  → ChatMessage (text + products + evidence + traces + harness)
  → _uiState.update { messages + assistantMessage }
  → ChatScreen 重组渲染
    → LazyColumn: MessageBubble + ProductCard + EvidencePanel + AgentTracePanel + HarnessValidationPanel
```

### 2.2 状态传递机制

```
WorkflowState (Pydantic BaseModel) — 贯穿全部 8 个节点
├── session_id: str                    # 会话标识
├── user_id: str                       # V2: 关联长期偏好
├── user_query: str                    # 原始查询 (Visual Agent 可能增强)
├── image_url: str | None             # 图片 URL
├── intent: str                       # Router 填充 (recommend/risk_check/compare/chitchat/...)
├── constraints: Constraints          # Router 填充 (category/budget/scenario/must_tags/...)
├── retrieval_plan: RetrievalPlan     # Router 填充 (channels/top_k/priority)
├── visual_result: dict | None        # Visual Agent 填充
├── retrieved_products: list[dict]    # Retrieval Agent 填充
├── evidence_list: list[dict]         # Retrieval + Visual Agent 累积
├── decision_results: list[dict]      # Decision Agent 填充
├── sufficiency_report: dict | None   # Evidence Checker 填充
├── answer: str                       # Response Agent 填充
├── trace_steps: list[dict]           # 每个节点追加
├── skill_executions: list            # Skill 执行记录
├── harness_report: dict              # Guard 填充
├── fallback_status: dict             # 降级追踪
```

### 2.3 优化方向

| 方向 | 当前状态 | 目标 |
|------|----------|------|
| 状态 Schema 收敛 | WorkflowState 包含所有中间结果 | 拆分为 AgentState + NodeOutput |
| 错误恢复 | 部分节点 try/except 静默降级 | node-level retry + 错误分类 |
| Async Execution | 大部分节点 async | 全节点 async + 并行化独立节点 |
| Streaming Response | 当前整体返回 | SSE 逐节点推送 trace |
| Observability | LLMSpan 追踪 | 集成 Langfuse/Phoenix |
| Workflow Config 化 | graph.py 硬编码 | 从 workflow.yaml 动态构建 |
| Eval Hooks | 无 | 每个节点注入 eval callback |

---

## 三、Multimodal Evidence RAG 实现机制

### 3.1 RAG 在当前项目中的定位

RAG 是 OmniCart Agent 推荐质量的上限决定者。商品推荐的质量不取决于 LLM 生成能力强弱，而是取决于检索到了哪些证据、这些证据是否准确、是否完整、是否可信。当前 RAG 的输出直接决定了 Decision Scoring 的输入质量和 Response Agent 的回答可信度。

### 3.2 RAG 输入全景

| 输入类型 | 来源 | 代码路径 | 数据结构 |
|----------|------|----------|----------|
| 用户文本 query | Android ChatInputBar | `state.user_query` | `str` |
| 商品截图解析结果 | Visual Agent | `state.visual_result` | `VisualResult (product_name/brand/price/specs/highlights/confidence)` |
| 商品结构化信息 | ProductRepository | `Product (product_id/title/brand/category/sub_category/base_price/skus/rag_knowledge)` | Pydantic BaseModel |
| FAQ/营销描述 | rag_knowledge.official_faq | `product.rag_knowledge.official_faq[]` | `FaqItem(question, answer)` |
| 用户评论 | rag_knowledge.user_reviews | `product.rag_knowledge.user_reviews[]` | `ReviewItem(nickname, rating, content)` |
| 政策规则关键词 | 硬编码关键词列表 | `_policy_channel()` 中的 `policy_keywords` | `list[str]` |
| 兼容性规则 | 代码中尚未独立建模 | — | — |
| 用户偏好 | PreferenceMemory + LongTermMemory | `state.constraints` | `Constraints (category/budget/scenario/must_tags/exclude_tags)` |

### 3.3 数据如何进入索引

**当前实现**：数据以 JSON 文件存储，运行时加载到内存。

```
ecommerce_agent_dataset/
  1_Beauty_and_Skincare/data/*.json  →  JsonProductRepository._load_all()
  2_Digital_Electronics/data/*.json  →  扫描 Path.glob("*.json")
  3_Clothing_and_Sports/data/*.json  →  每文件 → Product(**data)
  4_Food_and_Life/data/*.json        →  self._products: dict[product_id, Product]
```

**关键代码路径**：
- 加载：`repositories/json_product_repo.py:JsonProductRepository._load_all()` — 扫描 4 品类目录
- 向量化：`scripts/seed_qdrant.py` — 调用 `gateway.embed()` → `QdrantVectorRepo.store_embeddings()`
- 向量存储：`repositories/qdrant_vector_repo.py:QdrantVectorRepository.store_embeddings()`

### 3.4 Chunk 构造

**当前实现**：未做显式 chunking。整个商品的 `title + brand + marketing_description + faq[] + reviews[]` 拼接为一个全文索引单元。

```python
# text_retriever.py:217-234 — 全文索引构建
text_parts = [
    product.title,
    product.brand,
    product.category,
    product.sub_category,
]
if product.rag_knowledge:
    rk = product.rag_knowledge
    text_parts.append(rk.marketing_description)
    for faq in rk.official_faq:
        text_parts.append(faq.question)
        text_parts.append(faq.answer)
    for rev in rk.user_reviews:
        text_parts.append(rev.content)
full_text = " ".join(t.lower() for t in text_parts)
```

**当前问题**：
1. FAQ 和 Review 与商品信息混在一起，无法单独召回某条 FAQ 或某条评论
2. 没有 metadata 标注每条文本的来源类型
3. Qdrant 向量的 payload 缺少结构化字段过滤

### 3.5 Embedding 生成

```python
# model_gateway/qwen_embedding.py — async
class QwenEmbedding:
    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = _get_client()  # httpx.AsyncClient (模块级复用)
        resp = await client.post(
            f"{self._base_url}/services/embeddings/text-embedding/text-embedding",
            json={"model": "text-embedding-v4", "input": {"texts": texts},
                  "parameters": {"dimension": 1024}},
        )
        return [e["embedding"] for e in data["output"]["embeddings"]]
```

**关键参数**：模型 `text-embedding-v4`，维度 `1024`，通过 `model_config.yaml` 配置。

### 3.6 Qdrant 向量检索

```python
# repositories/qdrant_vector_repo.py
class QdrantVectorRepository(BaseVectorRepository):
    def search_similar(self, query_vector: list[float], top_k: int = 20) -> list[dict]:
        results = self._client.search(
            collection_name=self._collection,
            query_vector=query_vector,
            limit=top_k,
        )
        return [{"product_id": r.payload.get("product_id", ""), "score": r.score} for r in results]
```

**当前状态**：Qdrant 可用时参与 RRF 融合，不可用时透明降级为纯 jieba 关键词搜索。

### 3.7 jieba 关键词召回

```python
# text_retriever.py:236-265 — 关键词评分
keywords = [w.strip() for w in jieba.cut(query) if w.strip() and w.strip() not in _QUERY_STOP_WORDS]
# 每查询缓存一次 (2026-05-24 优化)

for kw in keywords:
    count = full_text.count(kw_lower)        # 全文命中 × 0.8
    title_count = title_lower.count(kw_lower) # 标题命中 × 2.0
    if kw_lower in product.category:          # 品类精确匹配 × 5.0
        score += 5.0
    # 多字词拆单字：如"买鞋"→["买","鞋"]，单字"鞋"命中子品类 × 3.0
```

### 3.8 RRF 融合排序

```python
# text_retriever.py:161-189 — Reciprocal Rank Fusion
@staticmethod
def _rrf_fusion(results_a: list[dict], results_b: list[dict], k: int = 60) -> list[dict]:
    scored: dict[str, tuple[dict, float]] = {}
    for rank, item in enumerate(results_a):
        scored[pid] = (item, 1.0 / (k + rank + 1))
    for rank, item in enumerate(results_b):
        if pid in scored:
            # 合并 evidence_ids
            scored[pid] = (merged_item, scored[pid][1] + 1.0 / (k + rank + 1))
        else:
            scored[pid] = (item, 1.0 / (k + rank + 1))
```

**参数 k=60**：平滑排名差异，使两个列表的排名贡献更均衡。

### 3.9 Qwen Reranker 精排

```python
# workflow/graph.py:108-152 — _node_reranker
async def _node_reranker(state: WorkflowState) -> WorkflowState:
    documents = [f"{p.get('title','')} {p.get('category','')} {p.get('sub_category','')}" 
                 for p in state.retrieved_products]
    ranked = await _gateway.rerank(query=state.user_query, documents=documents, top_n=len(products))
    # 按 relevance_score 降序重排
    reordered = sorted(enumerate(products), key=lambda x: index_map.get(x[0], 0.0), reverse=True)
```

**降级策略**：Reranker 不可用时 `try/except` 保持原序。

### 3.10 evidence_ids 绑定机制

```python
# text_retriever.py:85-91 — 每条检索结果绑定 evidence_ids
evidence_ids = [f"E-MKT-{product.product_id}"]
for i, faq in enumerate(product.rag_knowledge.official_faq):
    evidence_ids.append(f"POL-{product.product_id}-{i}")
for i, rev in enumerate(product.rag_knowledge.user_reviews):
    evidence_ids.append(f"R-{product.product_id}-{i}")
```

**ID 前缀规范**：
- `E-MKT-{pid}` — 营销描述证据
- `POL-{pid}-{i}` — 政策/FAQ 证据
- `R-{pid}-{i}` — 低分评论风险证据
- `R-POS-{pid}-{i}` — 高分评论正面证据
- `V-{field}` — 视觉字段级证据

### 3.11 Retrieval Agent 调用检索

```python
# agents/retrieval_agent.py:execute()
async def execute(self, state: WorkflowState) -> WorkflowState:
    # Step 1: LLM 查询改写
    search_query = await self._llm_extract_keywords(state.user_query)
    # "我想买个运动鞋跑步穿" → "运动鞋 跑步鞋 透气 缓震"

    # Step 2: 文本通道 (主检索)
    results, evidence = await self._text_channel(state)

    # Step 3: 评论通道 + 政策通道 (并行)
    with ThreadPoolExecutor(max_workers=2) as executor:
        review_future = executor.submit(self._review_channel, state)
        policy_future = executor.submit(self._policy_channel, state)
    # 2026-05-24 优化: 直接从 state.retrieved_products 提取，不再 N+1 查询

    # Step 4: 合并
    state.retrieved_products = results
    state.evidence_list = evidence + review_evidence + policy_evidence
```

### 3.12 检索结果进入 Context Compiler

```python
# context/compiler.py — 7 段结构化上下文
class ContextCompiler:
    def compile(self, state: WorkflowState) -> str:
        sections = []
        sections.append(self._user_intent_section(state))        # ①用户需求和意图
        sections.append(self._constraints_section(state))        # ②约束条件
        sections.append(self._visual_section(state))             # ③图片识别结果
        sections.append(self._candidates_section(state))         # ④候选商品+评分
        sections.append(self._evidence_section(state))           # ⑤证据摘要+关键摘录
        sections.append(self._counterfactual_section(state))     # ⑥反事实建议
        sections.append(self._retrieval_plan_section(state))     # ⑦检索计划
        return "\n\n".join(sections)
```

### 3.13 Android 端 Evidence 展示

```kotlin
// feature/panel/EvidencePanel.kt
@Composable
fun EvidencePanel(evidenceList: List<Map<String, Any?>>, modifier: Modifier) {
    // 可折叠卡片，按 source_type 分色图标
    // text_retrieval → 📄 蓝色
    // review_risk → ⚠️ 红色
    // review_positive → ✅ 绿色
    // policy_faq → 📋 橙色
    // visual → 🖼️ 紫色
}
```

### 3.14 当前 RAG 可能的失败点

| 失败模式 | 原因 | 影响 |
|----------|------|------|
| 品类关键词遗漏 | CATEGORY_RULES 覆盖不全 | 商品召回为 0 或品类错误 |
| jieba 分词不准 | 新词/长尾词无法正确切分 | 关键词匹配失效 |
| 向量库不可用 | Qdrant 未启动 | 退化为纯 jieba，召回精度下降 |
| Reranker API 故障 | Qwen API 400/超时 | try/except 保持原序 |
| 空查询 | user_query="" | Reranker 400 → 降级 (2026-05-24 修复) |
| FAQ/Review 混在全文索引 | 无法独立召回 | 具体 FAQ/Review 证据精度低 |
| 无 chunk 粒度控制 | 整个商品作为一个单元 | 长文本中关键信息被稀释 |

### 3.15 RAG 分层评测体系设计

#### 3.15.1 Golden Evaluation Set 构建

每一条 golden case 应包含：

```json
{
  "query": "500元以内适合跑步穿的蓝牙耳机",
  "correct_evidence_chunks": ["R-POS-p_digital_007-0", "POL-p_digital_007-1"],
  "correct_products": ["p_digital_007"],
  "correct_policies": ["防水等级IPX5"],
  "correct_reviews": ["佩戴舒适不脱落"],
  "ideal_answer": "推荐XXX耳机，防水防汗，佩戴稳固...",
  "failure_labels": ["retrieval_miss", "rerank_error", "context_missing"]
}
```

#### 3.15.2 检索层指标

| 指标 | 定义 | 计算方式 | 当前可测 |
|------|------|----------|----------|
| Recall@K | Top-K 结果中包含正确商品的比例 | `|retrieved ∩ relevant| / |relevant|` | ✅ 需要 golden set |
| Hit@K | Top-K 结果中至少命中 1 个的比例 | `1 if any(retrieved ∩ relevant) else 0` | ✅ |
| MRR | 第一个相关结果的排名倒数均值 | `1/rank_of_first_relevant` | ✅ |
| NDCG@K | 考虑排名位置的相关性 | 标准 DCG/IDCG 公式 | ✅ |
| Context Precision | 检索结果中相关项的比例 | `|relevant_in_topK| / K` | ✅ |
| Duplicate Rate | 重复证据比例 | `1 - |unique_evidence| / |all_evidence|` | ✅ 当前较低 |
| Latency | 检索耗时 | `perf_counter` 差值 | ✅ 已有 trace |

#### 3.15.3 重排层指标

| 指标 | 当前可测 | 说明 |
|------|----------|------|
| Rerank Recall@K | ✅ | Reranker 后 Top-K 是否包含正确答案 |
| MRR | ✅ | 重排后第一个相关结果排名 |
| NDCG | ✅ | 重排后排序质量 |
| Pairwise Ranking Accuracy | ⚠️ 需要标注 | 任意两个商品对排序正确率 |
| Top-1 Accuracy | ✅ | 排名第一是否为正解 |

#### 3.15.4 生成层指标

| 指标 | 定义 | 评测方式 |
|------|------|----------|
| Faithfulness | 回答是否可追溯到证据 | LLM-as-judge / 人工 |
| Answer Relevance | 回答是否直接回应问题 | LLM-as-judge |
| Context Utilization | 回答使用了多少上下文 | 证据引用率 |
| Citation Accuracy | 引用是否正确指向证据 | 正则匹配 evidence_id |
| Hallucination Rate | 无依据陈述比例 | 人工标注 |
| Risk Coverage | 风险是否被提及 | Harness 自动检查 |

#### 3.15.5 端到端指标

| 指标 | 计算方式 |
|------|----------|
| 推荐成功率 | 推荐列表非空 + Top-1 评分 ≥ 5.0 |
| 证据绑定完整率 | `evidence_ids` 非空的结果占比 |
| 用户问题解决率 | 人工评分 ≥ 3/5 的比例 |
| 错误归因统计 | 按 failure_labels 分类统计 |

### 3.16 RAG 短期可落地优化

| 优化项 | 难度 | 预期收益 | 实现方式 |
|--------|------|----------|----------|
| chunk 粒度优化 | 低 | 中 | FAQ/Review 独立索引，单条为一个 chunk |
| metadata schema | 低 | 高 | 每个 chunk 标注 source_type/product_id/category |
| RRF 参数调优 | 低 | 中 | k 值网格搜索 (40/50/60/70) |
| query rewrite 增强 | 中 | 高 | 多查询改写 + 合并结果 |
| evidence sufficiency check | 中 | 中 | 已实现但未在 workflow 中阻断 |
| negative sampling | 中 | 中 | 构造负例评测集 |
| policy evidence boost | 低 | 中 | 政策类查询提升 policy 通道权重 |
| visual evidence boost | 低 | 中 | 有图片时提升 visual 通道权重 |
| preference-aware retrieval | 中 | 高 | constraints 注入检索过滤条件 |
| golden query set | 中 | 高 | 50-100 条覆盖全部 4 品类 |

---

## 四、Context Engineering / Context Compiler

### 4.1 职责定义

Context Compiler 的职责不是"把检索结果塞给 LLM"，而是将多源异构信息编译为 LLM 可直接消费的结构化决策上下文。

### 4.2 输入全景

```
ContextCompiler.compile(state: WorkflowState) → str
输入:
├── state.user_query          # "500元以内蓝牙耳机推荐"
├── state.intent              # "recommend"
├── state.constraints         # Constraints(category="数码电子", budget_max=500.0, scenario=None)
├── state.visual_result       # VisualResult (仅当有图片)
├── state.retrieved_products  # [{"product_id":..., "title":..., "score":..., "rag_knowledge":...}, ...]
├── state.decision_results    # [{"final_score":..., "score_breakdown":{...}, "risk_factors":[...]}, ...]
├── state.evidence_list       # [{"evidence_id":..., "source_type":..., "content":...}, ...]
├── state.retrieval_plan      # RetrievalPlan(channels, top_k, priority)
├── state.sufficiency_report  # EvidenceChecker 输出
└── state.harness_report      # Guard 输出
```

### 4.3 输出格式

```text
## 用户需求与意图
用户查询: 500元以内蓝牙耳机推荐
意图类型: recommend
...

## 约束条件
品类: 数码电子 | 预算上限: ¥500.00 | ...

## 图片识别结果 (如有)
[Visual Agent 解析结果]

## 候选商品与评分
1. XXX耳机 | 综合分: 7.8/10 | 预算匹配: 0.85 | ...
2. YYY耳机 | 综合分: 6.2/10 | ...

## 证据摘要
[E-MKT-xxx] 营销描述: ...
[POL-xxx-0] Q: ... A: ...
[R-xxx-1] [用户][2星] ...

## 风险与注意事项
⚠ 预算超限 ⚠ 低分评论 ...

## 检索计划
渠道: text, review | Top-K: 10 | ...
```

### 4.4 当前实现状态

**代码路径**: `context/compiler.py:ContextCompiler.compile()`

**已实现**：
- 7 段结构化上下文
- 每个 section 有独立格式化函数
- 支持空结果的反事实建议段

**未实现**：
- Token budget controller（无上限控制，可能超出模型上下文窗口）
- 证据优先级排序（当前按原始顺序，未按置信度/相关性排序）
- 证据冲突检测（不处理同一商品的多条矛盾评论）
- 过期/低可信证据过滤（不根据时间/置信度过滤）
- Context compression（无上下文压缩策略）
- Schema-based structured context（输出为纯文本，非结构化 JSON）

### 4.5 Context Engineering 评测指标

| 指标 | 定义 | 当前可测 |
|------|------|----------|
| context completeness | 是否包含全部 7 段 | ✅ |
| evidence coverage | 证据是否全部被引用 | ⚠️ 需 golden |
| constraint coverage | 约束是否全部体现 | ✅ |
| redundancy rate | 重复信息占比 | ⚠️ 需标注 |
| context conflict rate | 矛盾证据占比 | ⚠️ 需标注 |
| token efficiency | 每单位 token 的信息量 | ⚠️ 需 token counting |
| answer faithfulness | 回答是否忠实于上下文 | ⚠️ LLM-as-judge |
| context ablation test | 移除某段后回答质量变化 | ⚠️ 需实验 |

### 4.6 优化方向

| 方向 | 说明 | 难度 |
|------|------|------|
| Schema-based Context | JSON Schema 替代纯文本 | 低 |
| Context Ranking | 按置信度/相关性排序证据 | 低 |
| Evidence Grouping | 按 source_type 分组 | 低 |
| Risk-First Context | 风险信息前置 | 低 |
| Preference-Aware Context | 根据用户偏好调整 | 中 |
| Token Budget Controller | 优先级裁剪超出 token 预算的证据 | 中 |
| Citation-Aware Prompt | 强制要求引用 evidence_id | 中 |
| Conflict Resolver | 标注矛盾证据并请求 LLM 判断 | 高 |
| Context Compression | LLM-based 摘要压缩 | 高 |

---

## 五、Constraint Solver + Decision Scoring

### 5.1 硬约束 vs 软偏好

| 类型 | 定义 | 示例 | 不满足时处理 |
|------|------|------|-------------|
| 硬约束 | 必须满足的条件 | 品类不匹配、预算超 2 倍 | 直接排除 |
| 软偏好 | 希望满足但不强制 | 颜色偏好、品牌偏好 | 降低评分但不排除 |

### 5.2 硬约束判断逻辑

```python
# agents/decision_agent.py — 硬约束过滤
if constraints.category and product.category != constraints.category:
    continue  # 品类不匹配 → 跳过
if constraints.budget_max and product.base_price > constraints.budget_max * 2:
    continue  # 价格超预算 2 倍 → 跳过
```

**当前实现**：
- 品类约束：精确匹配 `product.category == constraints.category`
- 预算约束：`base_price > budget_max * 2` 才排除（留 2 倍弹性）
- 接口兼容：代码中尚未独立建模
- 航空规则：通过政策关键词在 `_policy_channel` 中检索，不进入约束求解
- 风险标签：DecisionScoring 中 `risk_penalty` 维度自动计算

### 5.3 7 维 Decision Scoring 详解

```python
# decision/scoring.py — 完整公式
final_score = (
    budget_fit        * 0.22   # 预算匹配度
    + scenario_fit    * 0.24   # 使用场景匹配
    + spec_match      * 0.20   # 商品参数适配
    + review_confidence * 0.14 # 评论置信度
    + visual_similarity * 0.10 # 视觉相似度
    + availability_score * 0.10 # 可购买性
    - risk_penalty    * 0.15   # 风险惩罚(减法)
)
```

| 维度 | 输入字段 | 计算逻辑 | 代码位置 | 失败模式 |
|------|----------|----------|----------|----------|
| budget_fit | `product.base_price`, `budget_max` | `1.0 - min(abs(price-budget)/budget, 1.0)` | `scoring.py:_budget_fit()` | budget_max 为 None 时默认 1.0 |
| scenario_fit | `product.sub_category`, `scenario` | 场景关键词匹配 sub_category | `scoring.py:_scenario_fit()` | scenario 为 None 时默认 0.5 |
| spec_match | `product.rag_knowledge`, `keyword_score` | 关键词命中率归一化 | `scoring.py:_spec_match()` | 关键词为 0 时默认 0.3 |
| review_confidence | `user_reviews[].rating` | `avg_rating / 5.0` + 评论数量加权 | `scoring.py:_review_confidence()` | 无评论时默认 0.5 |
| visual_similarity | `visual_result.confidence` | 直接使用 | `scoring.py:_visual_similarity()` | 无图片时默认 0.0 |
| availability_score | 库存状态 | 当前所有商品默认 1.0 | `scoring.py:_availability_score()` | 无真实库存数据 |
| risk_penalty | 低分评论比例 | `(count_low_rating / total_reviews)` | `scoring.py:_risk_penalty()` | 无评论时默认 0.0 |

### 5.4 Android ScoreBreakdown 展示

```kotlin
// feature/panel/ScoreBreakdownPanel.kt
@Composable
fun ScoreBreakdownPanel(breakdown: Map<String, Any?>) {
    // 7 维 LinearProgressIndicator 颜色编码
    // ≥ 0.8 → 绿色  |  0.5-0.8 → 橙色  |  < 0.5 → 红色
    // 每维度显示: 名称 | 进度条 | 数值 | 权重
}
```

### 5.5 评测方法

| 指标 | 计算方式 | 当前可测 |
|------|----------|----------|
| Ranking Accuracy | Top-1 是否为正解 | ✅ 需 golden set |
| Constraint Violation Rate | 硬约束失败商品出现在推荐中的比例 | ✅ |
| Risk Miss Rate | 有风险但未标注的比例 | ✅ 可通过 review 交叉验证 |
| Score Calibration | final_score 与人工评分的相关性 | ⚠️ 需人工标注 |
| Score Explanation Completeness | ScoreBreakdown 7 维是否全部有值 | ✅ |
| Ablation Study | 移除某维度后排序变化 | ⚠️ 需实验 |
| Human Preference Agreement | 人工偏好与评分排序一致率 | ⚠️ 需人工标注 |
| Counterfactual Test | 修改约束后推荐是否合理变化 | ⚠️ 需测试集 |

### 5.6 短期可优化任务

| 优化 | 难度 | 说明 |
|------|------|------|
| 权重配置化 | 低 | 将 7 维权重从硬编码移到 model_config.yaml |
| Constraint Reason 输出 | 低 | 被排除商品附带排除原因 |
| 风险惩罚细化 | 中 | 区分安全风险/质量风险/兼容性风险 |
| 政策规则优先级 | 中 | policy 通道命中的商品给 spec_match 加分 |
| 反事实推荐测试集 | 中 | 构造约束变化前后对比 case |


---

## 六、Decision Harness 验证机制

### 6.1 Harness 定位

Harness 是 Agent 结果验证与展示模块，不是简单测试脚本。它用于检查和展示推荐结果是否满足关键约束，增强推荐链路的可验证性。

### 6.2 输入与输出

```
输入: WorkflowState (完整的工作流执行结果)
输出: harness_report (dict) — 写入 state.harness_report
```

### 6.3 Harness Report 结构 (代码: harness/decision_harness.py)

```python
{
    "harness_id": "HR-xxx",
    "checks": [
        {"name": "response_schema", "passed": True, "detail": ""},
        {"name": "evidence_binding", "passed": True, "detail": "3 evidence items bound"},
        {"name": "score_completeness", "passed": True, "detail": "7/7 dimensions scored"},
        {"name": "constraint_satisfaction", "passed": True, "detail": ""},
        {"name": "risk_warning", "passed": False, "detail": "Risk factor not mentioned in answer"},
        {"name": "trace_completeness", "passed": True, "detail": "7 trace steps recorded"},
        {"name": "tool_action_validity", "passed": True, "detail": ""},
    ],
    "overall_pass": False,
}
```

### 6.4 验证内容清单

| 验证项 | 检查逻辑 | 关键函数 |
|--------|----------|----------|
| Response Schema | answer 非空, products 为 list | decision_harness.py |
| evidence_ids 绑定 | 每条结果含非空 evidence_ids | decision_harness.py |
| Evidence 可追溯 | evidence_id 格式符合前缀规范 | decision_harness.py |
| ScoreBreakdown 完整 | 7 维全部有值 | decision_harness.py |
| Constraint 满足 | 推荐商品不违反硬约束 | decision_harness.py |
| Policy 引用 | 政策类查询含政策证据 | decision_harness.py |
| Risk Warning | 风险标签商品在回答中提醒 | decision_harness.py |
| Tool Action 合法 | 工具调用合法 | decision_harness.py |
| Trace 完整 | 记录了完整步骤序列 | decision_harness.py |

### 6.5 Harness 在 Workflow 中的位置

```
Router -> Visual -> Retrieval -> Reranker -> EvidenceCheck -> Decision -> Response -> Guard(harness_report) -> END
```

Guard 调用 ResponseGuard.check() 执行 5 项守门，Harness 通过 decision_harness.py 提供 7 项更全面的校验框架。

### 6.6 关键代码路径

- **Guard 检查**: `verification/response_guard.py:ResponseGuard.check(state)` — 5项守门, 写入 harness_report
- **Harness 验证**: `harness/decision_harness.py:DecisionHarness.validate(state)` — 7项校验框架
- **Evidence Check**: `verification/evidence_checker.py:EvidenceSufficiencyChecker.check(state)` — 按意图类型检查
- **Android 展示**: `feature/panel/HarnessValidationPanel.kt` — 可折叠卡片, 每项绿色✅/红色❌

### 6.7 Harness 失败处理

当前: 失败信息写入 harness_report, 不阻断响应返回。Harness 定位为"事后审计"而非"事前阻断"。

### 6.8 Harness 量化评测

| 指标 | 定义 | 当前可测 |
|------|------|----------|
| Schema Pass Rate | response_schema 检查通过率 | 是 |
| Evidence Binding Pass Rate | evidence_ids 非空比例 | 是 |
| Citation Validity Rate | evidence_id 格式正确率 | 是 |
| Score Completeness Rate | 7维全部有值比例 | 是 |
| Constraint Pass Rate | 硬约束未违反比例 | 是 |
| Risk Warning Coverage | 有风险标签时回答提及风险比例 | 是 |
| Trace Completeness | 8步全记录比例 | 是 |
| Replay Consistency | 重放结果一致性 | 需实现 |

### 6.9 优化方向

| 方向 | 说明 | 难度 |
|------|------|------|
| Rule-based Harness | 当前已实现, 可扩展更多规则 | 低 |
| LLM-as-Judge Harness | 引入LLM判断回答语义质量 | 中 |
| Policy-Aware Harness | 政策查询强制要求政策证据 | 低 |
| Counterfactual Harness | 修改约束后检查推荐是否合理变化 | 中 |
| Replay-based Regression | 保存golden case WorkflowState, 重放对比 | 中 |
| Harness Dashboard | 可视化通过率趋势 | 低 |
| Failure Reason Clustering | 归类失败原因指导优化 | 中 |


---

## 七、Core Agents Workflow 逐个分析

### 7.1 Router Agent

- **职责**: 意图识别、约束抽取、检索计划生成
- **输入**: state.user_query (str)
- **输出**: state.intent, state.constraints, state.retrieval_plan
- **关键代码**: `agents/router_agent.py:RouterAgent.execute()`
- **关键函数**: `_rule_based_parse(query)` 使用共享 `decision/rules.py` 的 `detect_category/budget/scenario()`
- **流程**: LLM优先调用 intent_understanding -> JSON解析 -> 失败则规则兜底(100%覆盖常见中文购物表达)
- **意图分类**: recommend / risk_check / compare / compatibility_check / alternative / chitchat
- **闲聊检测**: 16词检测 -> intent="chitchat" -> 跳过全部检索链
- **失败模式**: LLM输出格式不可控, JSON解析失败 -> 规则fallback
- **优化方向**: 意图分类规则->LLM微调; 约束抽取关键词->NER
- **评测指标**: Intent Accuracy / Constraint Extraction Accuracy / Chitchat Detection Rate

### 7.2 Visual Agent

- **职责**: Qwen-VL 解析商品截图 -> 结构化 VisualResult
- **输入**: image_url (str), user_query (str)
- **输出**: VisualResult (product_name/brand/price/specs/highlights/confidence/evidence_list)
- **关键代码**: `agents/visual_agent.py:VisualAgent.parse()`
- **关键函数**: `parse()` -> Redis缓存 -> gateway.vision() -> `_parse_json(raw)` -> 逐字段校验类型
- **流程**: 本地路径读取bytes -> md5缓存键 -> Qwen-VL多模态API -> JSON提取(支持markdown代码块包裹) -> VisualEvidence生成
- **失败模式**: API不可用/返回非JSON -> fallback_level递增
- **优化方向**: Prompt优化(精准字段提取); 多图支持; 商品库匹配
- **评测指标**: Product Name Accuracy / Brand Accuracy / Price MAE / Confidence Calibration

### 7.3 Retrieval Agent

- **职责**: 多通道证据检索执行
- **输入**: state.user_query, state.constraints, state.retrieval_plan
- **输出**: state.retrieved_products, state.evidence_list
- **关键代码**: `agents/retrieval_agent.py:RetrievalAgent.execute()`
- **关键函数**:
  - `_llm_extract_keywords()` - LLM查询改写("买鞋"->"运动鞋 跑步鞋")
  - `_text_channel()` - jieba+Qdrant RRF融合主检索
  - `_review_channel()` - 从已检索结果直接提取低分/高分评论(2026-05-24优化: 批量加载, 不再N+1)
  - `_policy_channel()` - 从已检索结果直接提取FAQ政策匹配
- **流程**: LLM改写 -> 文本通道主检索 -> 评论+政策通道并行(ThreadPoolExecutor) -> 合并evidence
- **失败模式**: LLM改写失败->退回原query; Qdrant不可用->纯jieba; 评论/政策无结果->空列表
- **优化方向**: Multi-query retrieval; 自适应top_k; 通道权重动态调整
- **评测指标**: Recall@K / MRR / Evidence Coverage / Channel Contribution Rate

### 7.4 Reranker 模块 (非独立Agent, Workflow节点)

- **职责**: 对jieba粗排结果语义重排序
- **输入**: state.retrieved_products (list[dict]), state.user_query (str)
- **输出**: state.retrieved_products (重排后)
- **关键代码**: `workflow/graph.py:_node_reranker()` (line 108-152)
- **关键函数**: `_gateway.rerank(query, documents, top_n)` -> Qwen Reranker API
- **降级**: try/except保持原序 (2026-05-24修复logger变量名bug)
- **优化方向**: Reranker prompt/model优化; 交叉编码器替代; 多阶段重排
- **评测指标**: Rerank NDCG Lift / MRR Improvement / Top-1 Swap Rate

### 7.5 EvidenceCheck Agent

- **职责**: 按意图类型检查证据充足性
- **输入**: state (完整WorkflowState)
- **输出**: state.sufficiency_report
- **关键代码**: `verification/evidence_checker.py:EvidenceSufficiencyChecker.check()`
- **实现**: 按意图(recommend/risk_check/compare/compatibility/alternative)要求不同最少证据类型
- **优化方向**: 证据不足时触发补充检索; 证据置信度阈值
- **评测指标**: Sufficiency Pass Rate / Missing Evidence Type Distribution

### 7.6 Decision Agent

- **职责**: 硬约束过滤 + 7维加权评分 + 风险标签
- **输入**: state.retrieved_products, state.constraints, state.visual_result
- **输出**: state.decision_results
- **关键代码**: `agents/decision_agent.py:DecisionAgent.execute()`
- **关键函数**: `_hard_filter(products, constraints)` -> `scorer.score(product, query, ...)`
- **流程**: 品类不匹配/预算超2倍->排除 -> 逐一7维评分 -> final_score降序 -> risk_factors标签
- **失败模式**: 全部被硬约束过滤->返回空列表->触发counterfactual
- **优化方向**: 权重配置化; 约束原因输出; 风险惩罚细化
- **评测指标**: Constraint Violation Rate / Ranking Accuracy / Risk Miss Rate

### 7.7 Response Agent

- **职责**: 生成最终自然语言回答
- **输入**: state (完整WorkflowState)
- **输出**: state.answer
- **关键代码**: `agents/response_agent.py:ResponseAgent.execute()`
- **关键函数**: `ContextCompiler.compile(state)` -> `gateway.chat("chat_generation", prompt)`
- **流程**: LLM优先(含证据引用) -> 模板兜底(商品名+价格+评分+风险)
- **闲聊模式**: 简短友好回复, 6类模板兜底
- **失败模式**: LLM API不可用/超时/token超限/空结果
- **优化方向**: Citation-aware prompt; 流式输出; 多轮对话
- **评测指标**: Faithfulness / Relevance / Citation Accuracy / Hallucination Rate

### 7.8 Guard Agent

- **职责**: 回答守门验证 (5项规则)
- **输入**: state (完整WorkflowState)
- **输出**: state.harness_report
- **关键代码**: `verification/response_guard.py:ResponseGuard.check()`
- **5项规则**: (1)证据绑定 (2)价格准确 (3)风险覆盖 (4)空结果诚实 (5)无依据断言禁止
- **优化方向**: 规则扩展; LLM-as-judge补充; 与Harness整合
- **评测指标**: Guard Pass Rate / 各项规则独立通过率


---

## 八、Preference Memory System 详细分析

### 8.1 三层记忆架构

| 层级 | 作用域 | 存储后端 | 代码路径 |
|------|--------|----------|----------|
| L1 短期 | 单次Workflow执行 | WorkflowState (内存Pydantic) | schemas/workflow.py |
| L2 会话 | 同一session_id多轮 | 内存dict + PG JSONB | memory/preference_memory.py |
| L3 长期 | 跨会话user_id | PG JSONB + JSON文件 | memory/long_term.py |

### 8.2 短期记忆 (WorkflowState)

每次请求的WorkflowState = 临时记忆: constraints, retrieved_products, evidence, decision_results, trace_steps, harness_report

### 8.3 会话记忆 (PreferenceMemory)

```python
# memory/preference_memory.py
class PreferenceMemory:
    _sessions: dict[str, dict]  # session_id -> {category, budget_max, scenario, must_tags, ...}

    def update(self, session_id, constraints: Constraints):
        # 新值覆盖旧值, None不覆盖, 标签集合去重合并
        # PG持久化 (USE_POSTGRES=True时)

    def merge_constraints(self, session_id, new_constraints) -> Constraints:
        # 话题切换: 新旧category不同 -> 丢弃旧约束
        # 新query无category -> 清除旧category
```

**REST API**: GET/PUT/DELETE /api/preferences?session_id=

### 8.4 长期偏好记忆 (LongTermMemory)

```python
# memory/long_term.py
class LongTermMemory:
    # 行为信号: search(weight=1) < add_to_cart(weight=3) < checkout(weight=5)
    # 时间衰减: 0.5^(days/30)
    # 预算学习: EMA指数移动平均 (购买权重2倍于浏览)

    async def record_search(user_id, query, category, sub_category, tags)
    async def record_add_to_cart(user_id, product_id, category, brand, price)
    async def record_checkout(user_id, product_ids, categories, brands, total_price)

    def merge_with_session(user_id, session_constraints) -> dict:
        # Session明确值 > 长期默认值 (不覆盖用户当前意图)
```

**数据模型**: `UserProfile` dataclass — preferred_categories/brands/budget_min_max/scenarios/tags (归一化0-1) + Top-N截断

### 8.5 记忆如何进入推荐链路

```
Router执行后:
  PreferenceMemory.merge_constraints() -> 会话级约束
  LongTermMemory.merge_with_session() -> 长期默认补充

Retrieval执行时:
  constraints.{category/budget/scenario} -> 注入TextRetriever.search()过滤

Decision执行时:
  constraints.{must_tags/exclude_tags} -> 影响评分和风险标签
```

### 8.6 记忆系统评测

| 指标 | 定义 |
|------|------|
| Preference Extraction Accuracy | 从行为信号正确提取偏好的准确率 |
| Profile Update Accuracy | 加购/结账后profile正确更新率 |
| Cross-Session Consistency | 同用户多会话推荐一致性 |
| Personalization Lift | 有记忆vs无记忆的推荐质量提升 |
| Stale Memory Rate | 过期偏好仍影响推荐的比例 |
| Wrong Memory Pollution Rate | 错误记忆污染推荐的比例 |

### 8.7 优化方向

| 方向 | 说明 |
|------|------|
| Memory Confidence | 每个偏好附带置信度分数 |
| Time Decay Tuning | 基于实际数据调优半衰期 |
| Preference Conflict Resolution | 多信号冲突仲裁策略 |
| Implicit Behavior Mining | 从浏览/停留/对比中挖掘 |
| User-Controllable Memory | 允许用户查看/删除/修正偏好 |


---

## 九、SkillRegistry 能力层

### 9.1 Skill vs Tool

| 维度 | Skill | Tool |
|------|-------|------|
| 粒度 | 组合能力 | 原子能力 |
| 示例 | "商品视觉解析" | "调用Qwen-VL API" |
| 编排 | 可调用多个Tool | 单一操作 |
| 验证 | Skill级别validation_rules | Tool级别schema校验 |

### 9.2 当前8个Skill

| Skill | 功能 | 依赖Tool |
|------|------|----------|
| visual_parse | 商品截图解析 | gateway.vision(直接调用) |
| product_retrieve | 商品文本检索 | text_search |
| review_mining | 评论风险挖掘 | review_search |
| policy_check | 政策/FAQ查询 | policy_lookup |
| compatibility_check | 兼容性判断 | compatibility_query |
| decision_scoring | 决策评分 | score_calculator |
| evidence_sufficiency | 证据充足性检查 | evidence_validator |
| demo_replay | Demo数据回放 | demo_loader |

**代码路径**: `skills/registry.py:SkillRegistry` — register/get_skill/list_skills

**执行记录**: SkillExecution(skill_name, status, latency_ms, output_summary)

### 9.3 Skill 评测指标

- Skill Selection Accuracy: Router选择的Skill是否合适
- Skill Execution Success Rate: 执行成功率
- Tool Call Success Rate: Skill内Tool调用成功率
- Invalid Skill Call Rate: 不应被调用但被调用的比例
- Latency: 执行耗时
- Trace Completeness: SkillExecution记录完整率

### 9.4 优化方向

- skill schema标准化; skill confidence; skill fallback链; tool risk-aware selection; skill chain planning; skill unit tests


---

## 十、MCP-compatible ToolManager

### 10.1 架构

```
MCP Client (Claude Desktop / Cursor)
  <-> JSON-RPC 2.0 over stdio / SSE
  <-> OmniCart MCP Server (mcp/server.py)
    <-> ToolManager (tools/manager.py)
      <-> 8 Tool Handlers (mcp/tools.py)
        <-> Agent Runtime / RAG / Decision / Repository
```

### 10.2 当前8个Tool

| Tool | 功能 | 权限 | 风险 |
|------|------|------|------|
| text_search | 商品文本搜索 | read | low |
| image_search | 视觉检索 | read | low |
| review_search | 评论检索 | read | low |
| policy_lookup | 政策查询 | read | low |
| compatibility_query | 兼容性查询 | read | low |
| score_calculator | 评分计算 | read | low |
| evidence_validator | 证据校验 | read | low |
| demo_loader | Demo数据加载 | read | low |

**V1安全策略**: 全部Tool只读, 不执行下单/支付/账号操作。

### 10.3 MCP Server双传输

```python
# mcp/server.py
# stdio模式: python -m app.mcp.server (Claude Desktop集成)
async def run_stdio():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(...)

# SSE/HTTP模式: uvicorn app.mcp.server:create_starlette_app --port 8007
def create_starlette_app():
    sse = SseServerTransport("/messages")
    # GET /sse -> SSE连接
    # POST /messages -> JSON-RPC请求
```

### 10.4 MCP兼容性

- 协议: JSON-RPC 2.0
- 传输: stdio (Claude Desktop) + SSE/HTTP (浏览器)
- Tool定义: 符合MCP Tool Schema (name/description/inputSchema)
- 8/8 Tool连通性测试通过

### 10.5 Tool评测指标

| 指标 | 定义 |
|------|------|
| Tool Call Success Rate | 调用成功比例 |
| Invalid Tool Call Rate | 参数schema不匹配比例 |
| Permission Violation Rate | 越权调用比例(V1应为0) |
| Schema Validation Pass Rate | I/O schema校验通过率 |
| Average Tool Latency | 平均耗时 |
| MCP Protocol Compatibility | 标准MCP客户端兼容性 |

### 10.6 优化方向

- manifest schema对齐标准MCP; tool permission policy; tool sandbox; tool timeout/retry; tool audit log; mcp compatibility tests; external tool integration


---

## 十一、总评测体系设计

### 11.1 分层评测架构

```
Layer 1: 数据集  -> golden queries/evidence/products/policies/visual/memory/tool
Layer 2: 检索    -> Recall@K, MRR, NDCG, HitRate, ContextPrecision, DuplicateRate, Latency
Layer 3: 重排    -> MRR, NDCG, Top1Accuracy, RerankLift
Layer 4: Context -> completeness, redundancy, conflict, token efficiency
Layer 5: Scoring -> constraint violation, ranking accuracy, risk miss, calibration
Layer 6: Generation -> faithfulness, relevance, citation, hallucination
Layer 7: Harness -> schema pass, evidence pass, score completeness, risk coverage, trace
Layer 8: Tool    -> action success, tool call success, invalid call, latency
Layer 9: End2End -> task success, recommendation acceptance, human agreement, manual review
```

### 11.2 指标体系详解

**检索层**:
- Recall@K = |retrieved AND relevant| / |relevant|
- MRR = mean(1 / rank_of_first_relevant)
- NDCG@K = DCG@K / IDCG@K
- Context Precision@K = |relevant_in_topK| / K

**重排层**:
- Rerank NDCG Lift = NDCG_after - NDCG_before
- Top-1 Swap Rate = 重排前后Top-1变化比例

**Scoring层**:
- Constraint Violation Rate = 违反硬约束的商品数/总推荐数
- Ranking Accuracy = Top-1是否为正解的比例
- Risk Miss Rate = 有风险标签但回答未提及的比例

**Generation层**:
- Faithfulness = 可追溯陈述数/总陈述数
- Citation Accuracy = 正确引用evidence_id的比例
- Hallucination Rate = 无依据陈述比例

**Harness层**:
- Schema Pass Rate = schema检查通过数/总检查数
- Evidence Pass Rate = evidence_ids非空的推荐数/总推荐数
- Risk Coverage = 有风险提醒/应有风险提醒

### 11.3 数据采集

| 数据 | 采集方式 |
|------|----------|
| golden queries | eval.py GOLDEN_QUERIES (已构建10条) |
| retrieval结果 | TraceCollector记录每节点中间态 |
| reranker结果 | _node_reranker trace记录 |
| decision结果 | state.decision_results序列化 |
| harness结果 | state.harness_report序列化 |
| LLM调用 | TraceCollector: token/latency/status |
| 人工评分 | 需构建评分界面 |

### 11.4 失败归因流程

```
推荐失败 -> 检查harness_report
  -> evidence_binding=False -> RAG检索失败 -> 检查retrieval trace
    -> jieba关键词为空 -> query rewrite失败
    -> Qdrant不可用 -> 基础设施
    -> RRF融合后无结果 -> 数据覆盖不足
  -> constraint_violation=True -> Decision硬约束问题
  -> risk_warning=False -> Response未生成风险提示
  -> trace_completeness=False -> 工作流中途崩溃
```


---

## 十二、下一阶段优化路线图

### P0: 必须先做 (比赛展示底线)

| # | 任务 | 说明 | 工作量 |
|---|------|------|--------|
| P0-1 | Golden Query Set构建 | 50-100条覆盖4品类+正确商品/证据标注 | 3-5天 |
| P0-2 | RAG Recall@K/MRR/NDCG基线 | 基于golden set跑当前RAG评测 | 1天 |
| P0-3 | Harness Pass Rate基线 | 对所有golden queries运行Harness | 0.5天 |
| P0-4 | 主链路Trace完整性检查 | 确保8节点全部记录 | 0.5天 |
| P0-5 | 代码现状盘点文档 | 本文档 | 已完成 |

### P1: 短期优化 (2周内可落地, 高ROI)

| # | 任务 | 难度 | 收益 |
|---|------|------|------|
| P1-1 | Chunk/Metadata优化 | 低 | 高: FAQ/Review独立索引, 标注source_type |
| P1-2 | RRF参数网格搜索 | 低 | 中: k值40/50/60/70调优 |
| P1-3 | Reranker Prompt优化 | 低 | 中 |
| P1-4 | Context Compiler Schema化 | 低 | 高: JSON Schema替代纯文本 |
| P1-5 | Scoring权重配置化 | 低 | 中: 从model_config.yaml读取 |
| P1-6 | Harness Failure Taxonomy | 低 | 中: 归类失败模式 |
| P1-7 | Query Rewrite增强 | 中 | 高: 多查询改写+结果合并 |
| P1-8 | 自动化评跑+报告 | 中 | 高: golden query一键评测 |

### P2: 中期优化 (1月内)

| # | 任务 |
|---|------|
| P2-1 | Memory-Aware Retrieval: constraints注入检索过滤 |
| P2-2 | Preference-Aware Scoring: 用户偏好影响评分权重 |
| P2-3 | Tool Governance Tests: 越权/异常参数测试 |
| P2-4 | MCP Compatibility Tests: Claude Desktop/Cursor兼容性 |
| P2-5 | Eval Dashboard增强: 更多指标+趋势图 |
| P2-6 | Counterfactual Evaluation: 约束变化前后对比 |

### P3: 长期优化 (比赛后)

| # | 任务 |
|---|------|
| P3-1 | GraphRAG: Neo4j替代NetworkX |
| P3-2 | Online Feedback Learning: Bandit排序 |
| P3-3 | Personalized Recommendation Benchmark |
| P3-4 | Large-Scale Product Dataset: 1000+件 |
| P3-5 | Streaming Response: SSE逐节点推送 |


---

## 十三、会议讨论问题

1. **RAG瓶颈定位**: 当前最大问题是召回不足, 重排错误, 还是上下文组织? 建议先跑golden query基线数据再判断。

2. **Golden Queries场景覆盖**: 至少应覆盖: 普通推荐、预算约束、风险咨询、品类对比、替代推荐、兼容性、空查询降级、图片导购、闲聊过滤。

3. **硬约束弹性**: 预算2倍弹性是否合理? 品类不匹配直接排除是否会误杀跨品类推荐?

4. **Harness演进**: 先完善规则校验(成本低)还是直接引入LLM-as-judge(语义覆盖但成本高)?

5. **Memory影响范围**: 长期偏好应影响检索(过滤候选)还是只影响评分(调整权重)? 如果影响检索, 错误记忆会直接导致好商品不可见。

6. **Tool权限**: V1全只读策略是否足够? 比赛展示是否需要"加购"动作(需write权限)?

7. **评委体验**: 哪些优化直接提升评委体验? 建议: Golden Query一键评测展示、Harness通过率可视化、Trace完整链路动画。

8. **简历价值**: 哪些能写进简历? RAG分层评测体系、Harness验证框架、MCP标准兼容、Context Engineering、Memory三层架构。

9. **技术债**: 5处AsyncBridge已统一、品类规则已集中、死代码已清理。剩余: workflow.yaml未解析、Evidence Graph未嵌入主链。

10. **下一步**: 确定P0/P1优先级排序, 分配负责人和截止日期。


---

> **文档结束** — 基于 OmniCart Agent V2-Complete (2026-05-24) 真实代码生成。
> 所有代码路径、函数名、数据结构均与当前仓库一致。如有差异以代码为准。
> 文件统计: 13章, 覆盖53个模块/类/函数的代码级分析。
> 生成工具: Claude Code + 手动验证
