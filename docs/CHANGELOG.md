# Changelog

## [V2] 长期偏好记忆 + Evaluation Dashboard — 2026-05-23 (下午)

### Added
- **用户长期偏好记忆**：跨会话 UserProfile + 三级行为信号(搜索/加购/结账) + 时间衰减(30天半衰期) + EMA预算学习 + PG/JSON双持久化
- **Evaluation Dashboard**：Web 可视化面板 + Chart.js + 10 golden queries + 历史趋势 + 统计卡片
- **数据集扩充**：新增 5 个平价数码产品（99-199元）

### Changed
- WorkflowState 新增 `user_id` 字段，RecommendRequest 新增 `user_id`
- 加购时自动记录长期偏好
- Router 节点接入长期记忆合并
- eval API 新增 4 个端点 + Dashboard HTML 页面

---

## [V2] Redis 缓存 + LLM 可观测性 + Qwen-Omni 语音 + 标准 MCP — 2026-05-23 (上午)

### Added
- **Redis 四级缓存**：Visual(1h) / Search(5min) / LLM Rewrite(30min) / Workflow(5min) 四级，get-or-compute 模式，Redis 不可用自动降级
- **LLM 全链路可观测性**：Gateway 全量接入(chat/vision/embed/rerank)，13 字段追踪，本地 JSON 存储，P50/P95 聚合统计 API
- **Qwen-Omni 语音导购**：ASR 文字转写 → Agent Workflow → TTS 语音回复，Android 全屏语音输入 + 长按录音
- **标准 MCP Server/Client**：8 Tool JSON-RPC 2.0，stdio + SSE/HTTP 双传输，Claude Desktop/Cursor 可接入
- **数据集扩充**：新增 5 个平价数码产品（99-199元），填补 500 元以下空白
- **语音文字清洗**：`_clean_transcription()` 逐句截断 AI 废话后缀
- **产品仓库降级修复**：`_check_pg()` PG 不可用时自动切换 JSON 模式

### Changed
- Gateway 4 方法全部 async 化（chat/vision/embed/rerank）以支持缓存和追踪
- LangGraph Workflow 节点 async 化，`invoke()` → `ainvoke()`
- 语音流程重构：ASR 先行 → 文字即时显示 → 复用 Agent 推荐通道
- 偏好设置 API 修复：`Map<String, Any?>` 加 `@JvmSuppressWildcards`

### Fixed
- 我的订单/收藏无响应 → 订单加提示，收藏删除
- 语音识别中加 loading 转圈指示器

---

## [V1-Core] Phase 5 完成：参赛打磨 — 2026-05-22

### Added
- State Checkpoint（JSON 文件持久化 8 节点，支持 resume/replay/export）
- baseline 对比脚本（10 条 golden queries，品类准确率/延迟/结果数评估）
- Evidence Graph Lite（NetworkX 商品-证据-风险图关系，优雅降级）
- Visual Evidence Grounding（字段级视觉证据绑定，evidence_id 可追溯）
- Counterfactual Recommendation（0 结果时反事实建议：放宽预算/品类/标签）
- Declarative workflow.yaml（更新至 8 节点 + fallback + checkpoint 配置）
- Tiered Multimodal Fallback（L0 Qwen-VL → L1 Mock → L2 纯文本 3 级降级）
- Hierarchical Shopping Knowledge Index（品类→子品类→品牌→商品 4 级分层）
- Decision Harness（7 项统一校验框架，包裹 ResponseGuard + EvidenceChecker）
- A2A-lite Dispatcher（AgentMessage/Artifact 同进程分发 + Agent 注册）
- Demo Pack 导出脚本（4 场景：蓝牙耳机/防晒霜/跑步鞋/咖啡）
- Android MockDemoData（一键 Demo 完整预置数据：Evidence + Trace + Harness 全面板）
- ChatViewModel Demo 模式升级为 MockDemoData（一次点击展示全部面板）
- 答辩QA手册扩展至 17 章（含全部 Phase 2-5 新增内容 + 完整代码索引）
- 4 个面板组件内联到 ChatScreen 豆仔对话流

### Test Results
- 后端：21/21 单元测试通过
- Workflow：8 节点正确注册
- Skill Registry：8 skills / ToolManager：8 tools + 权限 + 记录
- 13 个新 Phase 5 模块全部导入验证通过
- Android：BUILD SUCCESSFUL

---

## [V1-Core] Phase 2-4 完成：用户体系 + 证据链 + Agent 面板 — 2026-05-22

### Added
- 用户登录/注册 API（PBKDF2-SHA256 + Bearer Token + PG/内存双模）
- 收货地址 CRUD API（省/市/区/详细 + is_default 互斥 + PG/内存双模）
- 用户偏好 REST API（GET/PUT/DELETE，基于 PreferenceMemory）
- Evidence Checker 接入 Workflow（新增 evidence_check 节点，Reranker→Decision 之间）
- Skill Registry（8 内置 Skill：视觉解析/商品检索/评论挖掘/政策检查/兼容性/评分/证据充足性/Demo回放）
- MCP-compatible ToolManager（8 内置 Tool + 权限控制 + ToolCallRecord + V1 只读）
- Android 登录/注册页面（LoginScreen + AuthViewModel + AuthManager SharedPreferences）
- Android 地址管理页面（AddressScreen + 新增/编辑对话框 + 删除/默认标识）
- Android 偏好设置页面（PreferenceScreen + API 对接）
- Android EvidencePanel 独立组件（可折叠，按 source_type 分色图标）
- Android AgentTracePanel 独立组件（可折叠时间轴，状态色点）
- Android HarnessValidationPanel 独立组件（5 项守门规则 ✅/❌）
- Android SkillExecutionPanel 独立组件（技能执行状态列表）
- Android ScoreBreakdown 独立组件（7 维进度条颜色编码）
- 4 个面板组件集成到 ChatScreen 豆仔对话流
- 完整 README.md（10 章，面向队友的协作指南）
- .gitignore（保护 .env API 密钥等敏感文件）
- 新增 9 个后端单元测试（auth + address）
- WorkflowState 新增 sufficiency_report 字段

### Changed
- ChatScreen 豆仔对话下方自动展示 Evidence/Trace/Harness/Score 面板
- ProfileScreen 登录/未登录双态 + 地址/偏好可点击跳转
- MainScreen NavHost 新增 login / address / preference 路由
- OkHttp 添加 Authorization Bearer Token 拦截器
- ApiClient 新增 10+ API 接口（auth/address/preference）
- workflow/graph.py 新增 evidence_check 节点（7→8 节点）
- RecommendationResponse 新增 sufficiency_report 传递

### Fixed
- Auth API 错误返回 500 → HTTPException (409/401)
- Preference PUT 后 GET 读到旧数据（mem._sessions 缓存未同步）
- Address create 缺少 is_default 字段默认值
- ScoreBreakdown 字段名与实际模型不匹配
- Panel 组件编译错误（clickable/Box/iconForSource）

### Test Results
- 后端：21/21 单元测试通过
- Workflow：8 节点正确注册
- Skill Registry：8 skills / ToolManager：8 tools 可用
- Android：BUILD SUCCESSFUL

---

## [V1-Core] 双数据库架构定型 + Android 四 Tab 闭环 — 2026-05-22

### Added
- PostgreSQL 18 + Qdrant 1.18 双数据库（三张表 + 向量索引）
- Repository 抽象层（ABC + JSON/PG 双实现 + 工厂注入）
- Hybrid Search（Qdrant ANN + jieba RRF 融合 + 透明降级）
- 购物车 PG/内存双模 + 偏好 PG/内存双模
- Alembic 迁移 + seed_postgresql.py + seed_qdrant.py
- `docs/答辩QA手册.md`（13 章）+ `docs/TASK_LIST.md`（51 项）

### Changed
- Android ChatUiState → ChatMessage 对话历史模型
- ChatScreen 多轮消息不覆盖 + 新对话按钮
- CartViewModel 从 Demo 假数据 → 真实后端 API
- OmniCartApi 补全 cart/checkout/agent_action 8 个接口
- ProductCard 新增加入购物车按钮
- Router Agent 规则优先 LLM + 话题切换检测
- CartScreen/ChatScreen 去掉双层 Scaffold 修复 UI 空白

### Fixed
- agent_actions.py 未定义变量 item → cart_item
- 品类关键词缺失（"食品""鞋""吃的"等）
- PreferenceMemory merge 旧品类未真正清除
- PgProductRepository._run() nest_asyncio 桥接

## [V1-Core] 7节点工作流升级 + Android 图片链路修复 — 2026-05-22 (自主开发)

### Added
- **Qwen Reranker 精排节点**: 对 jieba 粗排结果语义重排序，Mock 模式自动降级
- **Context Compiler** (`context/compiler.py`): 结构化编译决策上下文，替代分散 prompt
- **Response Guard** (`verification/response_guard.py`): 5 项回答守门规则 → harness_report
- **Evidence Sufficiency Checker** (`verification/evidence_checker.py`): 按意图类型检查证据充足性
- **Preference Memory** (`memory/preference_memory.py`): 多轮会话约束合并记忆
- **workflow.yaml**: 声明式 7 节点工作流配置
- **Async Retrieval**: review+policy 通道 ThreadPoolExecutor 并行检索

### Fixed
- `UploadResponse` 缺 `@SerializedName` → Gson 反序列化失败 → 图片上传永远失败
- `onSend()` 图片数据在异步上传前被清空
- Visual Agent 未接入 V2 工作流（`_has_image` 硬编码跳过）

### Workflow
```
Router → [Visual?] → Retrieval(并行) → Reranker → Decision → Response(Compiler) → Guard → END
```

### Test Results
- 22/22 单元测试通过
- 5 品类端到端验证通过

---

## [V1-Core] 4-Agent LangGraph 工作流 + 官方数据集迁移 — 2026-05-22

### Added
- **官方数据集接入** (100 件商品，4 品类)
  - 品类：美妆护肤 25 + 数码电子 25 + 服饰运动 25 + 食品饮料 25
  - 每件商品含 rag_knowledge（marketing_description + official_faq + user_reviews）
  - 1-14 个 SKU 变体 + 实拍 JPG 图片
  - 图片服务：FastAPI mount `/images/` → `ecommerce_agent_dataset/`
- **产品 Schema 重写** (`app/schemas/product.py`)
  - Product / Sku / RagKnowledge / FaqItem / ReviewItem 匹配数据集结构
- **ProductRepository 重写** (`app/repositories/product_repo.py`)
  - 从 4 个品类子目录递归加载 JSON
  - 图片路径中文→英文映射
  - 新增 search_text() 全品类文本搜索
- **TextRetriever 增强** (`app/retrieval/text_retriever.py`)
  - jieba 中文分词 + 停用词过滤
  - 搜索范围扩展至 rag_knowledge（marketing_description + faq + reviews）
  - 品类/子类精确匹配 5x 加权
- **DecisionScoring 增强** (`app/decision/scoring.py`)
  - review_confidence 使用真实 user_reviews.rating 计算
  - risk_penalty 基于低分评论比例
- **Agent 基础架构** (6 文件)
  - `schemas/workflow.py` — WorkflowState / Constraints / RetrievalPlan / TraceStep
  - `schemas/a2a.py` — AgentCard / AgentMessage / Artifact (A2A-lite)
  - `agents/base.py` — BaseAgent 抽象基类 (card + execute + trace)
  - `agents/router_agent.py` — 意图识别 + 约束抽取 + 检索计划（规则+LLM混合）
  - `agents/retrieval_agent.py` — text/review/policy 三通道证据检索
  - `agents/decision_agent.py` — 硬约束过滤 + 7维加权评分 + 风险标签
  - `agents/response_agent.py` — LLM证据引用回答 + 模板兜底
- **LangGraph Workflow** (`workflow/graph.py`)
  - StateGraph 编排：Router → Retrieval → Decision → Response
  - /api/recommend/v2 Agent 工作流端点
- **Android 模型适配**
  - Product.kt：Sku/RagKnowledge/FaqItem/ReviewItem 数据类
  - ProductCard.kt：sub_category + SKU价格区间 + 用户评分展示
  - 图片URL自动拼接 BASE_URL
- **run.py 简化** — 去掉已废弃的前端，纯后端一键启动

### Changed
- Product 模型：tags/specs/scenarios/stockStatus → skus/ragKnowledge/subCategory
- API 品类识別：英文枚举 → 中文四品类（美妆护肤/数码电子/服饰运动/食品饮料）
- Demo Mode 假数据：3 款充电宝 → 3 款蓝牙耳机（含 RAG 知识）
- ProductCard UI：规格行 → 子品类 + SKU数 + 用户均分

### Test Results
- 单元测试：22/22 passed（12 V0 + 10 V1 Agent）
- 检索精度验证：5 个品类查询全部返回正确品类

### Design Decisions
- Router Agent 采用规则为主+LLM增强混合策略（LLM不可用时降级）
- 硬约束优先于软评分（预算×2/品类不匹配直接排除）
- A2A消息模型已定义但当前用 WorkflowState 直接传参（简化V1实现）
- V0/V2 双端点并存（旧 API 保留不影响已有功能）

---

## [V0-Android] Android Native Client 初始化 — 2026-05-20

### Added
- **Android 原生客户端项目** (`android-client/`)
  - Kotlin + Jetpack Compose + Material 3 + MVVM 架构
  - Gradle 8.7 + AGP 8.5.0 + Kotlin 2.0.0
  - Retrofit 2.11 + OkHttp 4.12 + Gson + Coil 2.6
  - Lifecycle ViewModel Compose + Coroutines 1.8
- **Gradle 项目骨架** (7 文件)
  - settings.gradle.kts / build.gradle.kts / gradle.properties / gradle-wrapper.properties
  - app/build.gradle.kts (Compose + Retrofit + Coil + Coroutines 依赖)
  - proguard-rules.pro / .gitignore
- **Core 基础层** (10 文件)
  - `config/AppConfig.kt` — 后端 baseUrl (10.0.2.2:8006 模拟器映射)
  - `theme/Color.kt + Type.kt + Theme.kt` — Material 3 主题 (评分颜色/风险标签色)
  - `network/ApiClient.kt` — Retrofit + OkHttp 单例 (含日志拦截器)
  - `network/OmniCartApi.kt` — /api/health + /api/recommend 接口
  - `network/NetworkResult.kt` — Success/Error/Loading 封装
  - `model/RecommendRequest.kt + RecommendResponse.kt` — 请求/响应数据类
  - `model/Product.kt` — 商品+规格数据类 (@SerializedName 映射)
  - `model/DecisionResult.kt` — 评分+细分+风险因素 (@SerializedName 映射)
- **Feature UI 层** (6 文件)
  - `ChatScreen.kt` — Scaffold + TopAppBar + LazyColumn 主页面
  - `ChatViewModel.kt` — MVVM StateFlow (真实API调用 + Demo本地假数据双模式)
  - `ChatUiState.kt` — loading/error/products/answer/demoMode 状态
  - `ChatInputBar.kt` — OutlinedTextField + 发送按钮
  - `ProductCard.kt` — Coil图片 + 标题+品牌+价格+评分(颜色编码)+风险标签
  - `DemoModeSwitch.kt` — TopAppBar 内 Demo Mode 开关
- **AndroidManifest.xml** — INTERNET权限 + cleartext (本地调试)
- **Demo Mode 本地假数据** — 3 款充电宝 + 完整 DecisionResult 模拟

### Changed
- **TextRetriever** 返回字典增加 `image_urls` 字段 (修复 Android ProductCard 图片展示)
- **CLAUDE.md** 全面更新：
  - 技术栈从 FastAPI + Next.js → FastAPI + Android Native Client
  - 开发里程碑加入 V0-Android / V1-Android
  - 移除所有前端 (frontend/) 相关命令
  - 新增 Android 构建/ADB 命令
  - V0 主链路改为 Android 文本输入 → ProductCard

### Deprecated
- **frontend/** 目录标记为废弃 (新增 `frontend/DEPRECATED.md`)
- **run.py** 一键启动中的前端部分已不可用（仅后端可用）
- 所有 Web/Next.js/React/TailwindCSS 相关描述视为 deprecated

### Design Decisions
- 使用 `10.0.2.2:8006` 作为模拟器到宿主机的映射地址
- 使用 `@SerializedName` 将后端 snake_case JSON 映射为 Kotlin camelCase
- ProductCard 评分颜色：>=8.0 绿色 / >=6.0 橙色 / <6.0 红色
- Demo Mode 本地假数据包含 3 款充电宝，可离线展示完整 UI

---

## [V1-Core] Model Gateway + Visual Agent — 2026-05-20

### Added
- 模型配置统一 (model_config.yaml) — 7 个能力→模型映射
- Qwen-VL / Reranker / Embedding (1024dims) / Chat 增强
- Visual Agent (截图→结构化 VisualResult + VisualEvidence)
- VisualResult + VisualEvidence Schema
- 推荐链路增强 (视觉字段注入检索 + 视觉证据)
- 评分引擎 visual_similarity / spec_match 增强
- 前端视觉结果面板 + 图片上传按钮

### Test Results
- 单元测试：12/12 passed · 集成测试：8/8 passed

---

## [V0-Core] Initial Setup — 2026-05-20

### Added
- FastAPI 后端 + Next.js 前端骨架 (前端已废弃)
- Product / Evidence / DecisionResult Schema
- Qwen Model Gateway + Mock Mode
- 35 个充电宝 Mock 数据 + 30 条 Golden Queries
- Text Retriever (关键词匹配) + Decision Scoring (7维公式)
- /api/recommend + /api/health + /api/upload
- ChatInput + ProductCard + ScoreBreakdown 组件
- 16 个测试 (12 unit + 4 integration)
