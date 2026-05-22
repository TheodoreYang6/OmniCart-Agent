# Changelog

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
