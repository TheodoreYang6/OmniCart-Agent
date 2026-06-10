# 豆仔——OmniCart Agent

> 基于 RAG 的多模态电商智能导购 AI Agent · 字节跳动 Agent 挑战赛参赛作品

---

## 目录

- [一、团队信息](#一团队信息)
- [二、项目名称](#二项目名称)
- [三、代码仓库地址](#三代码仓库地址)
- [四、项目亮点与创新点](#四项目亮点与创新点)
- [五、设计文档](#五设计文档)
  - [5.1 系统架构](#51-系统架构)
  - [5.2 技术栈](#52-技术栈)
  - [5.3 依赖环境](#53-依赖环境)
  - [5.4 目录结构](#54-目录结构)
  - [5.5 配置说明](#55-配置说明)
  - [5.6 关键问题与解决方案](#56-关键问题与解决方案)
- [六、说明文档（部署与体验）](#六说明文档部署与体验)
- [七、演示视频](#七演示视频)
- [八、其他补充信息](#八其他补充信息)

---

## 一、团队信息

### 队名

（由队长在提交表单中填写）

### 团队成员

| 姓名 | 角色 | 职责 |
|------|------|------|
| **杨启铎** | 全栈架构 | 项目整体架构设计、FastAPI 后端开发、5-Agent 协同系统（Router / Visual / Retrieval / Decision / Response）、LangGraph 工作流编排、RAG 全链路检索（Embedding + Qdrant + Reranker + 证据补充）、7 维证据评分引擎、三层记忆系统（短期 / 长期 / 会话）、FollowUpEngine 追问检测、SSE 流式对话、购物闭环（自然语言加购 / 下单）、语音导购（ASR + TTS）、Docker 容器化部署、阿里云服务器运维、全部技术文档撰写 |
| **胡金成** | 后端 / 数据 | RAG 评测体系搭建（10 条 Golden Query 设计、Recall@K / MRR / NDCG@K 指标计算、Chart.js 可视化仪表盘）、PostgreSQL + Qdrant + Redis 数据库架构设计与维护、数据播种与索引脚本 |
| **章恒睿** | Android 客户端 | Android 原生客户端全部开发：Jetpack Compose 四 Tab 架构（商品 / 豆仔 / 购物车 / 我的）、SSE 流式对话界面、拍照识图、语音输入、购物车管理、偏好设置、Agent 洞察面板（追踪 / 证据 / 评分 / 安全）、Demo 演示模式、APK 签名混淆打包 |

### 分工说明

杨启铎负责项目整体架构设计与全栈开发，核心工作包括 LangGraph 5-Agent 协同编排、RAG 全链路检索管道、评分引擎与记忆系统的设计与实现，以及 Docker 部署与服务器运维。

胡金成负责 RAG 评测体系与数据库架构，设计了 10 条覆盖 4 大品类的 Golden Query 评测集，实现了 Recall@K、MRR、NDCG@K 等检索指标自动计算和 Chart.js 可视化仪表盘，同时负责 PostgreSQL 7 张业务表、Qdrant 双集合向量索引和 Redis 四级缓存的架构设计与数据维护。

章恒睿独立完成 Android 原生客户端全部开发工作，基于 Jetpack Compose + Material 3 实现了四 Tab 主架构，核心功能包括 SSE 流式打字机对话、拍照识图、语音导购、对话式购物操作、偏好管理和 Agent 洞察面板，并完成了 Release APK 的签名混淆打包。

---

## 二、项目名称

**OmniCart Agent** — 基于 RAG 的多模态电商智能导购 AI Agent

OmniCart Agent 将传统电商的"展示型广告"升级为"交互型导购"，打通从内容浏览到购买决策的完整闭环。用户通过文字、拍照、语音任一方式表达购物需求，系统内部 5 个协作 Agent 在 LangGraph 编排下完成意图理解 → 视觉识别 → 多维检索 → 证据评分 → 流式回复的全链路推理，最终在 Android 原生客户端上以打字机效果呈现推荐结果。所有推荐结论均绑定 `evidence_ids`，做到可解释、可追溯、可验证。

---

## 三、代码仓库地址

**GitHub：** https://github.com/TheodoreYang6/OmniCart-Agent

**服务运行中：** http://8.137.187.54:8006/api/health

**APK 下载：** http://8.137.187.54:8006/api/uploads/douzai.apk

---

## 四、项目亮点与创新点

### 1. 从"问答"到"交易"的完整 Agent 闭环

大多数 AI 导购只能做 Q&A——用户问、AI 推荐一段文字、用户自己去 App 里搜商品、比价格、加购物车、下单。AI 和交易是割裂的。OmniCart 实现了自然语言驱动的完整购物闭环：

- **推荐→加购→下单一气呵成**：用户说"推荐蓝牙耳机500以内"→ 5 Agent 协同检索评分 → 流式推荐结果 → 用户说"第二个加购"→ 自动解析中文序数指代、匹配 SKU 规格、完成加购 → 用户说"下单"→ 读取默认地址、生成订单汇总确认卡片 → 用户说"确认"→ 订单持久化 PostgreSQL。全程自然语言，不离开对话界面，从选品到下单一条消息链完成。
- **「问豆仔」深度分析**：用户点击任一商品可触发 `product_focused_analysis` 模式——Agent 围绕该商品做**用户口碑分析**（均分/好评率/差评风险）、**FAQ 覆盖解读**、**SKU 规格建议**、**适用人群推荐**，同时检索同类商品生成**多维度对比表**（价格/推荐分/用户口碑/规格品质等维度横向比较）。分析完成后检测购买意向信号，主动询问"要不要帮你直接下单？"
- **7 种购物操作自然语言驱动**：加购、删第 N 个、数量改成 N、清空购物车、下单、修改地址、确认下单——全部在 SSE 流式端点内通过关键词分流 + 正则解析完成，不进 Agent Workflow，省延迟、确定性高。

### 2. 证据绑定的可解释推荐——每个推荐都可追溯到原文

LLM 推荐最大的隐患是"幻觉"——编造不存在的品牌、虚构价格、说不清推荐理由。OmniCart 从架构层面解决这个问题：

- **5 类证据绑定**：所有推荐结论绑定 `evidence_ids`——营销描述证据（E-MKT）、官方 FAQ/政策证据（POL）、用户评论证据（R，分正向/中性/风险三级）、视觉识别证据（V，拍照识图结果）、补充发现证据（E-SUPP，分块语义匹配反向发现）。
- **7 维分解分**：每件商品产出 `component_scores`，每个维度标注**分数 + 权重 + 计算方法 + 支撑证据 ID 列表**。relevance（0.45，Reranker 精排分数校准）→ budget_fit（0.20，预算内梯度评分）→ user_sat（0.12，Bayesian 平滑评论均分）→ value_score（0.10，39 子品类独立基准价）→ spec_quality（0.08，LLM 规格关键词匹配）→ scenario_fit（0.05，12 场景动态关键词）→ risk_penalty（差评扣分）。每个分数都可复算、可追溯。
- **四道幻觉防线**：① 强制引用候选商品（LLM 回答必须包含至少一个候选品牌/标题，否则回退模板）→ ② 65 品牌白名单校验 → ③ 价格准确性检查（回答中的价格必须与候选商品一致）→ ④ 6s 超时自动模板兜底。`harness_report` 汇总全部检查结果，前端可视化展示。

### 3. 闲聊与导购智能区分 + 三层记忆个性化

传统方案要么只会推荐（用户说"你好"也硬推商品，体验生硬），要么只会闲聊（聊完无法自然过渡到购物）。OmniCart 在同一对话中实现了两者的无缝切换，并通过三层记忆实现个性化：

- **30+ 闲聊场景智能识别**：Router 内置词库快速识别打招呼、问身份、情感表达、测试消息等 30+ 种闲聊场景。命中闲聊时走专用 `_handle_chitchat` 链路——**先回应情绪再顺势引导购物**（用户说"饿了"→"辛苦啦！要不要一起挑点香喷喷的零食？"、用户说"无聊"→"无聊的时候最适合逛好东西啦！"、用户说"想你"→"我也想你呀～"）。不强行推销，像朋友聊天一样自然过渡。用户随时可以接着说"推荐跑鞋"，Router 自动切回导购模式。
- **三层记忆越聊越懂你**：短期记忆（`context_snapshot` JSONB，品类/预算/场景跨轮累积继承，话题切换自动清空）、长期记忆（`user_preference_entries` 条目化管理，支持自然语言输入→LLM 自动解析→品类感知注入——搜手机时只注入数码偏好，不污染美妆搜索）、会话记忆（对话历史完整持久化，跨设备恢复，LLM 自动生成标题，增量压缩摘要）。
- **7 种追问模式全覆盖**：FollowUpEngine 按优先级检测——序数指代（"第二个怎么样"）→ 品牌引用（"Sony那个"）→ 上次引用（"刚才那个能上飞机吗"）→ 预算更新（"换成200以内的"）→ 购物车意图 → 对比意图 → 模糊追问（"便宜一点"，自动继承当前品类约束）。配合问答链机制（豆仔提问→用户简短回答"好"→Router 自动从 pending_question 推断搜索意图并替换 query），让多轮对话自然连贯。

---

## 五、设计文档

### 5.1 系统架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                       🖥  Android Native Client                        │
│  Kotlin + Jetpack Compose + Material 3  ·  MVVM + StateFlow           │
│                                                                        │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│   │  📦 商品  │   │  🫘 豆仔  │   │  🛒 购物车 │   │  👤 我的  │          │
│   │ 商品浏览  │   │ SSE 对话  │   │ 购物管理  │   │ 个人中心  │          │
│   └──────────┘   └──────────┘   └──────────┘   └──────────┘          │
│                         │                                              │
│   输入模态：💬 文字  ·  📷 拍照识图  ·  🎤 语音导购                     │
│   对话能力：追问/指代/对比/加购/下单/偏好记忆                           │
└─────────────────────────────┬────────────────────────────────────────┘
                              │  HTTP REST + SSE Stream (Retrofit/OkHttp)
┌─────────────────────────────▼────────────────────────────────────────┐
│                     ⚙  FastAPI Backend (:8006)                         │
│                                                                        │
│  ┌─────────────────── Workflow (LangGraph StateGraph) ──────────────┐ │
│  │                                                                    │ │
│  │  START ──→ Router ──→ Visual (∥并行) ──→ Retrieval ──→ Reranker  │ │
│  │              │                                    │                │ │
│  │              │ (chitchat)                         │                │ │
│  │              ▼                                    ▼                │ │
│  │           Response         EvidenceCheck ←── Reranker              │ │
│  │              ▲                  │                                  │ │
│  │              │                  ▼                                  │ │
│  │              └──────────── Decision ──→ Response ──→ Guard ──→ END │ │
│  │                     (无结果时跳过 Decision)                         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ FollowUpEngine│  │CtxCompressor │  │ Memory Layer │                 │
│  │ 7种追问检测   │  │ 对话增量摘要  │  │ 三层记忆     │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
│                                                                        │
│  17 个 API 路由模块  ·  5 Agent 协作  ·  7 大模型能力                   │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
      ┌───────────────────────┼───────────────────────┐
      │                       │                       │
┌─────▼─────┐  ┌──────────────▼──┐  ┌───────────────▼──┐
│ PostgreSQL │  │     Qdrant      │  │      Redis        │
│   16       │  │   向量检索引擎    │  │     7             │
│ 商品/用户   │  │  1024d ANN      │  │  四级缓存          │
│ 会话/购物车 │  │  余弦相似度      │  │  优雅降级          │
│ 订单/偏好   │  │  本地降级兜底    │  │                    │
└───────────┘  └─────────────────┘  └────────────────────┘

              ┌─────────────────────────────────┐
              │       Qwen Model Stack           │
              │  qwen-turbo    · 意图/生成       │
              │  qwen-vl-max   · 视觉理解        │
              │  qwen3-rerank  · 语义精排        │
              │  text-embedding-v4 · 向量化(1024d)│
              │  qwen-omni-turbo · 语音(ASR+TTS) │
              └─────────────────────────────────┘
```

**Workflow 节点流转：**

| 步骤 | 节点 | 职责 | 性能优化 |
|------|------|------|----------|
| 1 | **Router** | 意图识别 + 品类/预算/场景约束提取 + 检索计划 | 品类预填跳过 LLM；规则+LLM 合并 |
| 2 | **Visual** | 拍照识图、品类映射、DB 精确匹配 | 与 Router 并行执行 |
| 3 | **Retrieval** | 语义检索 + 分块证据补充（三通道） | LLM 关键词改写缓存 30min |
| 4 | **Reranker** | Qwen3-Rerank 语义精排 | 视觉匹配商品置顶 0.99 |
| 5 | **EvidenceCheck** | 证据充足性校验 | 不满足则标记 insufficiency |
| 6 | **Decision** | 7 维证据加权评分 + 避雷过滤 | LLM 评估可选（默认关闭） |
| 7 | **Response** | LLM 流式生成 + 幻觉校验 | 6s 超时模板兜底 |
| 8 | **Guard** | 品牌验证 + 价格准确 + 风险覆盖 | 四道防线 |

**Agent 协同设计：**

5 个 Agent 通过 LangGraph StateGraph 编排为有向无环图，共享 `WorkflowState` 状态对象。与 ReAct 模式不同，StateGraph 的每条边是显式的，流程固定、状态强类型、每个节点可独立调试。

| Agent | 模型 | 核心职责 | 输入 | 输出 |
|-------|------|----------|------|------|
| **Router** | qwen-turbo + 规则 | 意图识别、品类/预算/场景约束提取、检索计划生成 | user_query | intent + Constraints + RetrievalPlan |
| **Visual** | qwen-vl-max | 拍照识图、品类映射(80+映射表)、DB 精确匹配 | image_url + user_query | VisualResult + visual_matched_pids |
| **Retrieval** | text-embedding-v4 | 三通道并行检索(text/review/policy) + 分块证据补充 + LLM 关键词改写 | plan + constraints | products[] + evidence[] |
| **Decision** | 规则公式 + LLM(可选) | 7 维证据加权评分 + 硬约束过滤 + 避雷检测 | products + evidence | decision_results[] |
| **Response** | qwen-turbo + 模板 | LLM 流式生成 + 6s 超时兜底 + 幻觉校验 + 对比/闲聊模式 | decision_results + context | answer (SSE stream) |

**关键设计决策：**

- **StateGraph 而非 ReAct**：严格按有向图编排，Agent 不自由决策下一步，调用链完全可预测、可调试
- **并行优化**：Router∥Visual 有图并行、FollowUp∥Profile 并行加载、三通道证据 ThreadPoolExecutor 并行
- **预填跳过**：约束引导推荐中 category+sub_category 已确定时，Router 跳过 LLM 节省 ~1s
- **trace_steps 全程记录**：每个节点写入输入/输出/耗时/状态，前端 AgentTracePanel 可视化

### 5.2 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| **客户端** | Kotlin + Jetpack Compose + Material 3 | Android 原生，MVVM 架构 |
| **网络** | Retrofit + OkHttp + Coroutines | HTTP REST + SSE 流式 |
| **图片** | Coil | 异步图片加载 |
| **后端** | Python 3.11 + FastAPI | 异步 Web 框架 |
| **AI 模型** | 通义千问 (Qwen) | qwen-turbo(意图/生成)、qwen-vl-max(视觉)、qwen3-rerank(精排)、text-embedding-v4(向量化)、qwen-omni-turbo(语音) |
| **工作流** | LangGraph 0.2 | StateGraph 有向图编排 8 节点 |
| **向量库** | Qdrant | ANN 语义检索 + 本地降级，1024d COSINE |
| **数据库** | PostgreSQL 16 | asyncpg + SQLAlchemy 2.0 + Alembic，7 张业务表 |
| **缓存** | Redis 7 | 视觉(1h)/搜索(5min)/改写(30min)/工作流(5min) 四级缓存，透明降级 |
| **语音** | Qwen-Omni | ASR 语音转文字 + TTS 文字转语音 |
| **部署** | Docker 24+ + Compose v2 | 四服务编排（backend + PG + Qdrant + Redis） |
| **分词** | jieba | 中文关键词提取（降级兜底） |

### 5.3 依赖环境

| 层次 | 依赖 | 版本要求 | 说明 |
|------|------|----------|------|
| **运行时** | Python | 3.11+ | 后端运行环境 |
| | Docker + Compose | 24+ / v2 | 容器化部署（推荐） |
| | JDK | 17+ | Android APK 构建 |
| **数据库** | PostgreSQL | 16 | 商品/用户/会话/订单持久化（可降级为 JSON 文件） |
| | Qdrant | latest | 向量检索引擎（可降级为本地 Embedding 缓存） |
| | Redis | 7 | 四级缓存（可降级禁用） |
| **AI 模型** | Qwen API Key | — | 阿里云 DashScope，Mock 模式可免 Key 运行 |
| **Python 包** | 见 requirements.txt | 18 个 | FastAPI / LangGraph / SQLAlchemy / Qdrant / Redis / OpenAI SDK |

> **降级策略：** 三项基础设施（PostgreSQL / Qdrant / Redis）均支持优雅降级。不配置时自动切换为 JSON 文件模式 + 本地缓存 + 无缓存模式，Mock 模式无需任何外部依赖即可运行全部功能。

### 5.4 目录结构

```
OmniCart-Agent/
│
├── android-client/                          # Android 原生客户端 (Kotlin)
│   └── app/src/main/java/com/omnicart/agent/
│       ├── core/                            # 配置/网络/模型/主题
│       │   ├── config/AppConfig.kt          # API 地址 + 超时配置
│       │   ├── model/                       # 数据类 (Product/RecommendResponse/DecisionResult)
│       │   ├── network/                     # Retrofit API (30+ 端点) + SSE 客户端
│       │   └── theme/                       # Material 3 主题
│       └── feature/
│           ├── chat/                        # 🫘 豆仔智能对话 (SSE流式/语音/图片/购物操作)
│           ├── product/                     # 商品卡片/详情/图片
│           ├── cart/                        # 🛒 购物车管理
│           ├── order/                       # 📋 订单列表
│           ├── address/                     # 📍 收货地址 CRUD
│           ├── auth/                        # 🔐 登录注册 + Token 管理
│           ├── preference/                  # ⚙ 购物偏好 (自然语言→解析→条目)
│           ├── profile/                     # 👤 个人中心
│           ├── shop/                        # 📦 商品浏览 (分类筛选)
│           ├── panel/                       # 🔍 Agent 洞察面板 (追踪/证据/评分/安全)
│           ├── demo/                        # 🎮 演示模式 + Mock 数据
│           └── upload/                      # 📷 Photo Picker
│
├── backend/                                 # FastAPI 后端 (Python 3.11)
│   ├── Dockerfile                           # 容器构建
│   ├── entrypoint.sh                        # 容器入口 (迁移+启动)
│   └── app/
│       ├── main.py                          # 应用入口 (路由注册+CORS+启动)
│       ├── agents/                          # 5 Agent 实现 (Router/Visual/Retrieval/Decision/Response)
│       ├── api/                             # 17 个路由模块 (health/recommend/stream/products/cart/checkout/auth/address/conversation/preference/upload/voice/agent_actions/observability/eval)
│       ├── workflow/                        # LangGraph 编排 (StateGraph 构建+编译+缓存+执行)
│       ├── model_gateway/                   # Qwen 模型统一网关 (chat/vision/embedding/reranker/omni/mock)
│       ├── services/                        # 业务服务层 (conversation/profile/followup/compressor/guide)
│       ├── retrieval/                       # 检索模块 (语义检索/分块检索/LLM评估)
│       ├── decision/                        # 评分模块 (6维公式/证据指标/共享规则)
│       ├── verification/                    # 安全验证 (回答守门/证据检查)
│       ├── repositories/                    # 数据仓库 (PG + 内存双实现，12个)
│       ├── models/                          # SQLAlchemy ORM (7 张表)
│       ├── schemas/                         # Pydantic 数据模型 (11个)
│       ├── core/                            # 基础设施 (config/database/cache/qdrant/redis)
│       ├── context/                         # 上下文编译 (决策结果→LLM Prompt)
│       ├── observability/                   # 可观测性 (LLM Span/RAG日志)
│       └── eval/                            # 评测指标 (Recall@K/MRR/NDCG@K)
│
├── ecommerce_agent_dataset/                 # 商品数据集 (105件 / 4品类 / 39子类)
├── scripts/                                 # 工具脚本 (15个: 播种/索引/冒烟/评测)
├── data/                                    # 数据目录 (评测/上传/缓存)
├── alembic/                                 # 数据库迁移
├── docker-compose.yml                       # Docker 四服务编排
├── requirements.txt                         # Python 依赖 (18个包)
└── README.md                                # 项目总览
```

**代码统计：** 87 个 Python 文件 · 50 个 Kotlin 文件 · 13 个测试文件 · 15 个脚本

### 5.5 配置说明

所有配置通过 `.env` 环境变量管理，无硬编码。

**核心配置项：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OMNICART_PORT` | `8006` | 后端服务端口 |
| `OMNICART_MOCK_MODE` | `true` | `true` = 无需 API Key，使用内置 Mock 数据 |
| `OMNICART_FAST_MODE` | `false` | `true` = 跳过 LLM，模板秒回 |
| `QWEN_API_KEY` | — | 阿里云 DashScope API Key（Mock 模式下可不填） |
| `DATABASE_URL` | — | PostgreSQL 连接串。留空自动降级 JSON 文件 |
| `QDRANT_URL` | — | Qdrant 服务地址。留空自动降级本地缓存 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串。留空则禁用缓存 |
| `EMBEDDING_DIMENSION` | `1024` | 向量维度（text-embedding-v4） |
| `OMNICART_DEFAULT_TOP_K` | `10` | 检索返回商品数 |
| `OMNICART_ENABLE_EVIDENCE_SCORING` | `true` | 证据驱动评分开关 |
| `OMNICART_ENABLE_DECISION_LLM` | `false` | LLM 证据评估开关（实验功能） |

**本地开发最小配置（`.env`）：**
```bash
OMNICART_PORT=8006
OMNICART_MOCK_MODE=true                      # 无需 API Key
DATABASE_URL=postgresql+asyncpg://omnicart:omnicart@localhost:5432/omnicart
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
```

**Docker 部署最小配置（`cp .env.docker .env` 后修改）：**
```bash
QWEN_API_KEY=sk-your-real-key-here           # 必填
OMNICART_MOCK_MODE=false
DATABASE_URL=postgresql+asyncpg://omnicart:omnicart@postgres:5432/omnicart
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379/0
```

> Docker 容器内 PostgreSQL/Qdrant/Redis 通过服务名互通（`postgres`/`qdrant`/`redis`），本地裸机开发改为 `localhost`。

### 5.6 关键问题与解决方案

以下是构建多模态购物导购 Agent 过程中遇到的 10 个核心设计问题，以及基于实际代码的解决方案。

**1. 多 Agent 如何有序协作不混乱？**

5 个 Agent 各有独立职责，若采用开放式 ReAct 循环会导致调用链不可控、调试困难、token 消耗大。解决方案：采用 LangGraph StateGraph 有向图编排，流程固定、状态显式。Router 和 Visual 有图片时并行执行（`asyncio.create_task`），品类预填时跳过 Router LLM，闲聊意图跳过检索和评分。

**2. 自然语言到精准商品的语义鸿沟？**

用户说"推荐蓝牙耳机500以内"，系统需理解品类、子品类、预算、场景。解决方案：5 步检索链路——LLM 关键词改写 → Embedding 1024d → Qdrant ANN → 品类/价格过滤 → Qwen3-Reranker 精排（校准公式 0.68+0.38×score）。子品类无结果自动放宽，检索不足 3 件触发分块证据补充。

**3. 评分如何可解释而非黑盒？**

传统推荐输出一个分数，用户不知道为什么。解决方案：6 维加权公式（relevance 0.45 / budget_fit 0.20 / user_sat 0.12 / value_score 0.10 / spec_quality 0.08 / scenario_fit 0.05），每维独立计算+绑定证据 ID。RAG 驱动而非 LLM 驱动，Bayesian 平滑（C=3，prior=0.80）避免冷启动偏差，39 子品类独立基准价。

**4. 多轮对话如何记住上下文？**

用户说"第二个便宜的有吗"，系统需知道"第二个"指谁、"便宜"在哪品类下。解决方案：三层记忆——短期（context_snapshot JSONB，TLS 2h）、长期（user_preference_entries 条目化，品类感知注入）、会话（conversations+messages 持久化）。FollowUpEngine 7 种追问模式 + 问答链（pending_question→肯定词→自动替换 query）。

**5. 如何防止 AI 幻觉？**

LLM 可能编造品牌、价格、商品名。解决方案：四层防线——强制引用候选商品（否则回退模板）→ 65 品牌白名单校验 → 价格准确性检查 → 6s 超时模板兜底。

**6. 数据库架构如何支撑 Agent 全链路？**

Agent 需同时管理商品、会话、向量检索、高频缓存。解决方案：三库分立——PostgreSQL 7 表（商品/用户/会话/消息/购物车/订单/偏好）、Qdrant 双集合（products 产品级 + product_chunks 分块级，1024d COSINE）、Redis 四级缓存（视觉 1h/搜索 5min/改写 30min/工作流 5min，透明降级）。

**7. 模糊意图如何匹配精准商品？**

"送女朋友礼物"——没品类、没预算、没品牌。解决方案：四维约束提取（规则+LLM 合并）+ 子品类自动放宽 + 60+ 品牌中英别名 + 约束引导推荐（品类→子品类→预算多轮）。

**8. 文字+图片双模态如何有效融合？**

拍照 + "有便宜的吗"，视觉和文本约束来自两个 Agent。解决方案：Router∥Visual 并行执行 → 视觉品类映射（80+）→ 高置信度（≥0.5）DB 精确匹配置顶 0.99 → 视觉信息注入 search_query。

**9. 外部依赖不可靠时如何保障可用？**

API 超时、DB 断开、Qdrant 挂。解决方案：三级降级——PG→JSON、Qdrant→本地缓存→关键词匹配、Redis→穿透 factory、LLM→6s 超时模板兜底 / Mock 全离线。每项独立 try/except，单项故障不扩散。

**10. 对话如何直接转化为下单？**

传统 AI 客服只能聊天，需切换到购物车页面手动操作。解决方案：SSE 流式端点内购物操作分流——关键词检测 → 中文序数指代解析 → SKU 规格选择 → 订单确认卡片 → PG 持久化。FollowUpEngine 加购意图自动检测，不进 Agent Workflow 省延迟。

---

## 六、说明文档（部署与体验）

### 方式一：直接安装 APK（最快，30 秒）

APK 已配置连接云服务器 `8.137.187.54:8006`，安装即用。

**下载安装：** `http://8.137.187.54:8006/api/uploads/douzai.apk`

**体验路径：**
1. 打开 App → 底部切到「🫘 豆仔」Tab
2. 输入 "推荐一款蓝牙耳机，500以内" → 观看 SSE 打字机效果
3. 点击商品卡片 → 查看详情（SKU / FAQ / 评论 / 评分拆解）
4. 点击「问豆仔」→ 深度分析该商品 + 同类对比
5. 说 "第二个加入购物车" → 对话式加购（含 SKU 规格选择）
6. 说 "下单" → 模拟下单流程
7. 切到「📦 商品」Tab → 浏览 105 件商品，按分类筛选
8. 切到「🛒 购物车」Tab → 查看/管理已加购商品
9. 切到「👤 我的」Tab → 登录注册 / 偏好设置 / 地址管理

**更多体验：** 拍照识图 / 语音导购（长按🎤） / 快速模式（⚡开关） / 约束引导推荐（➕） / Agent 洞察面板（🧠）

### 方式二：Docker 一行起跑（2 分钟）

```bash
git clone https://github.com/TheodoreYang6/OmniCart-Agent.git && cd OmniCart-Agent
cp .env.docker .env
docker compose up -d
docker compose exec backend python scripts/seed_postgresql.py      # 首次
docker compose exec backend python scripts/index_products.py       # 首次
curl http://localhost:8006/api/health
# → {"status":"ok","service":"omnicart-agent","version":"2.0.0"}
```

### 方式三：本地 Python 开发（3 分钟）

```bash
pip install -r requirements.txt
OMNICART_MOCK_MODE=true uvicorn backend.app.main:app --port 8006
curl http://localhost:8006/api/health
```

### 核心 API 速测

| 端点 | 说明 |
|------|------|
| `GET /api/health` | 健康检查 |
| `POST /api/recommend/v2` | V2 LangGraph 5-Agent 工作流推荐 |
| `POST /api/recommend/stream` | SSE 流式推荐（主力端点） |
| `GET /api/products?category=数码电子` | 商品列表（分页+筛选） |
| `GET /api/products/{id}` | 商品详情（SKU/FAQ/评论） |
| `POST /api/eval/run?method=default` | Golden Query 评测 |
| `GET /eval` | Chart.js 可视化仪表盘 |

### 服务地址

| 项目 | 地址 |
|------|------|
| 云服务器 API | `http://8.137.187.54:8006/api/health` |
| APK 下载 | `http://8.137.187.54:8006/api/uploads/douzai.apk` |
| 本地部署 | `http://localhost:8006` |

---

## 七、演示视频

（录制 5-10 分钟带讲解视频，上传后填写链接）

---

## 八、其他补充信息

### 评测体系

10 条 Golden Query 覆盖 4 大品类 × 多种查询类型（模糊推荐/条件筛选/场景化/肤质匹配/特殊约束）。支持 Recall@5 / Recall@10 / MRR / NDCG@10 / Category Accuracy / P95 Latency 自动评测。Chart.js 交互式可视化仪表盘可查看历史趋势和逐 Query 详情。

### 部署状态

Docker Compose 四服务编排（PostgreSQL 16 + Qdrant + Redis 7 + FastAPI），阿里云轻量服务器 2C4G 50G SSD 生产运行中（8.137.187.54:8006）。

### Release APK

已签名混淆打包（ProGuard），2.4MB，可直接安装体验。网络安全配置已添加服务器 IP。

### 接口文档

30+ REST 端点 + SSE 流式协议，覆盖推荐/商品/购物车/结算/用户/地址/会话/偏好/语音/评测/可观测全部模块。

### 测试

13 个测试文件：单元测试（Agent/评分/规则/检索/偏好）+ 集成测试（推荐/SSE/上传/Workflow）。

### 数据库

PostgreSQL 7 张业务表（products / users / conversations / conversation_messages / cart_items / orders / user_preference_entries）。Qdrant 双集合向量索引（products 产品级 105 条 + product_chunks 分块级 ~800 条）。Redis 四级缓存（视觉 1h / 搜索 5min / 改写 30min / 工作流 5min），支持透明降级。
