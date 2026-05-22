# OmniCart Agent

> Android 原生四 Tab 电商智能导购客户端 | FastAPI Agent Runtime 多模态购物决策后端
>
> **字节跳动 Agent 挑战赛参赛项目** · V1 全部完成 (50/51) · 私有仓库

---

## 1. 项目简介

OmniCart Agent 是一个**具备完整购物链路的 Android 原生智能导购 Agent 产品**。它不同于普通购物 App，也不是单一聊天机器人——它是一个以 AI Agent 为核心的端到端购物决策系统。

**四个主页面：**

| Tab | 功能 | 说明 |
|-----|------|------|
| 商品展示 | 浏览商品、分类筛选、商品详情 | 展示官方数据集商品，支持搜索和品类筛选 |
| **豆仔智能** | **核心 AI Agent 页面** | 多模态导购、商品推荐、证据解释、评分、Trace、Harness 展示、受控加入购物车 |
| 购物车 | 购物车管理、模拟结算 | 增删改查、多选、全选、豆仔推荐标识、mock checkout |
| 个人中心 | 用户信息、地址、偏好 | 登录/注册、收货地址管理、购物偏好设置 |

**本项目不是**：普通 Android 购物 App、WebView 套壳、RAG 聊天 Demo。

**本项目是**：Workflow-controlled Multi-Agent（非开放式 ReAct），所有推荐结论绑定 `evidence_ids`，具备完整的可解释决策链路。

---

## 2. 项目核心能力

### Android 原生客户端
- Kotlin + Jetpack Compose + Material 3 + MVVM
- 底部四 Tab 导航 + 10 个子路由：商品 / **豆仔（含 Agent 洞察 10 Tab）** / 购物车 / 我的（含登录/地址/偏好）
- 图片选择（Photo Picker）+ 图片上传 + 图片预览
- **ProductDetailSheet 6 Tab**（推荐/证据/评分/链路/技能/验证）
- **AgentInsightSheet 10 Tab**（上下文/检索计划/证据图/降级/工具/反事实/视觉绑定/偏好/基准/摘要）
- Demo Mode 一键展示完整 Agent 链路数据

### FastAPI 后端 Agent Runtime
- **8 节点 LangGraph Workflow**：Router → Visual → Retrieval → Reranker → EvidenceCheck → Decision → Response → Guard
- **LLM 查询改写**：Qwen 口语→搜索关键词（"我想买鞋"→"运动鞋 跑步鞋 休闲鞋"），jieba 单字拆分兜底
- **闲聊模式**：16 词检测 → 跳过全部检索链 → 纯文字友好回复 + 6 类模板兜底
- Qwen-only Model Stack（Chat / Vision / Embedding / Reranker）
- PostgreSQL 18（6 张表）+ Qdrant 1.18（1024d COSINE）双数据库架构
- **6 类 Repository** 全部 PG+内存双实现 + 工厂注入 + 透明降级
- **State Checkpoint**：JSON 文件 8 节点持久化（resume/replay/export）
- **Skill Registry**：8 内置 Skill（组合能力，编排原子 Tool）
- **MCP-compatible ToolManager**：8 内置 Tool + Manifest + 权限 + V1 只读强制

### 多模态 Evidence RAG
- **LLM 查询改写 + jieba 单字拆分**：口语精准转化为搜索关键词
- Hybrid Search（Qdrant 1024d ANN + jieba 关键词 RRF k=60 融合 + 透明降级）
- 用户评论挖掘：低分评论风险提取 + 好评证据
- 政策/规则查询：购物政策、航空携带规则等
- 7 维 Decision Scoring + Qwen Reranker 精排
- **Visual Evidence Grounding**：字段级视觉证据绑定
- **Evidence Graph Lite**：NetworkX 商品-证据-风险图关系
- **Counterfactual Recommendation**：0 结果时智能反事实建议
- **Hierarchical Knowledge Index**：品类→子品类→品牌→商品 4 级分层 + 250+ 关键词

### 豆仔智能导购 Agent
- Router Agent：规则优先 LLM + 6 种意图（含闲聊） + 16 词闲聊检测
- Visual Agent：截图→结构化参数 + 三级降级（L0 真实→L1 Mock→L2 纯文本）
- Retrieval Agent：**LLM 改写** + 三通道并行（text/review/policy）
- Decision Agent：硬约束过滤（预算×2 排除）+ 7 维评分 + 风险标签
- Response Agent：**闲聊/购物双模式 Prompt** + 6 类模板兜底
- Response Guard + Evidence Checker + Decision Harness（7 项校验）
- Preference Memory：多轮约束合并 + 话题切换自动清除 + REST API

### 商品展示
- 100 件官方数据集商品（美妆护肤 / 数码电子 / 服饰运动 / 食品饮料）
- 品类筛选 + 子品类展示 + SKU 价格区间 + 用户评分

### 购物车
- PG/内存双模 + 商品快照（加购时锁定价格）
- 增删改查 + 多选/全选 + 模拟结算（不接入真实支付）

### 个人中心
- 用户注册/登录（PBKDF2-SHA256 100k 迭代 + Bearer Token，每次登录刷新）
- 收货地址 CRUD（省/市/区/详细 + 默认地址互斥）
- 用户偏好 REST API（品类/预算/标签/场景）

### Demo Mode / Mock Mode
- 一键 Demo 完整数据：2 商品 + 4 证据 + 7 条 Trace + 完整 Harness + Agent 洞察全部数据
- 真实 API → Mock 透明切换，离线可展示

---

## 3. 技术栈

### Android 客户端
| 类别 | 技术 |
|------|------|
| 语言 | Kotlin |
| UI | Jetpack Compose + Material 3 |
| 架构 | MVVM (ViewModel + StateFlow) |
| 异步 | Kotlin Coroutines |
| 网络 | Retrofit 2.11 + OkHttp 4.12 + Gson |
| 图片 | Coil 2.6 |
| 图片选择 | Android Photo Picker |
| 导航 | Jetpack Compose Navigation |
| 构建 | Gradle 8.7 + AGP 8.5.0 + Kotlin 2.0.0 |

### 后端
| 类别 | 技术 |
|------|------|
| 语言 | Python 3.11 |
| 框架 | FastAPI + Pydantic v2 |
| Agent | LangGraph StateGraph (8 节点 Workflow) |
| 数据库 | PostgreSQL 18 (6 表) + SQLAlchemy 2.0 (async) |
| 向量库 | Qdrant 1.18 (1024d COSINE) |
| 模型 | Qwen (Chat / Vision / Embedding / Reranker) |
| 分词 | jieba 中文分词 |
| 检索融合 | RRF (Reciprocal Rank Fusion, k=60) |
| 迁移 | Alembic |
| 异步桥接 | nest_asyncio |

### 协作与工程
| 类别 | 技术 |
|------|------|
| 版本控制 | Git + GitHub Private Repository |
| 分支策略 | feature branch workflow |
| 环境管理 | Conda (omnicart 环境) + pip |
| 配置 | .env / .env.example |
| 文档 | 蓝图 / 开发规则 / 进度 / 知识 / 决策 / 变更日志 / 答辩QA手册(17章) / 数据库设计详解 |

---

## 4. 仓库目录结构

```
OmniCart-Agent/
├── backend/                        # FastAPI 后端 Agent Runtime
│   ├── app/
│   │   ├── main.py                 # 应用入口，路由注册，启动事件
│   │   ├── api/                    # HTTP API 层（协议适配，不写业务逻辑）
│   │   │   ├── health.py           # GET /api/health
│   │   │   ├── recommend.py        # POST /api/recommend/v2
│   │   │   ├── products.py         # GET /api/products, GET /api/products/{id}
│   │   │   ├── cart.py             # CRUD /api/cart
│   │   │   ├── checkout.py         # POST /api/checkout
│   │   │   ├── auth.py             # POST /api/auth/register, /login, GET /profile
│   │   │   ├── address.py          # CRUD /api/addresses
│   │   │   ├── preference.py       # GET/PUT/DELETE /api/preferences
│   │   │   ├── agent_actions.py    # POST /api/agent/action
│   │   │   └── upload.py           # POST /api/upload
│   │   ├── agents/                 # 5 个核心 Agent
│   │   │   ├── base.py             # Agent 抽象基类
│   │   │   ├── router_agent.py     # 意图识别 + 约束抽取 + 检索计划
│   │   │   ├── visual_agent.py     # 截图 → 结构化视觉结果
│   │   │   ├── retrieval_agent.py  # text/review/policy 三通道证据检索
│   │   │   ├── decision_agent.py   # 硬约束过滤 + 7 维加权评分
│   │   │   └── response_agent.py   # LLM 证据引用回答
│   │   ├── core/                   # 全局基础设施
│   │   │   ├── config.py           # 环境变量读取 + 配置导出
│   │   │   ├── database.py         # Async SQLAlchemy engine + session factory
│   │   │   └── qdrant_client.py    # Qdrant client singleton
│   │   ├── models/                 # SQLAlchemy ORM 模型
│   │   │   ├── product.py          # 商品表（JSONB skus + rag_knowledge）
│   │   │   ├── cart_item.py        # 购物车表（商品快照反范式）
│   │   │   ├── user.py             # 用户表（pbkdf2 密码哈希 + token）
│   │   │   ├── user_preference.py  # 用户偏好表（JSONB）
│   │   │   └── address.py          # 收货地址表
│   │   ├── repositories/           # 数据访问层（ABC + 工厂 + 双实现）
│   │   │   ├── base_product_repo.py  # 商品仓库 ABC
│   │   │   ├── json_product_repo.py  # JSON 文件实现
│   │   │   ├── pg_product_repo.py    # PostgreSQL 实现（sync-async 桥接）
│   │   │   ├── product_repo.py       # 工厂 re-export
│   │   │   ├── base_vector_repo.py   # 向量仓库 ABC
│   │   │   ├── qdrant_vector_repo.py # Qdrant 实现
│   │   │   ├── stub_vector_repo.py   # 无向量库降级实现
│   │   │   ├── vector_repo.py        # 工厂 re-export
│   │   │   ├── pg_cart_repo.py       # 购物车（PG + 内存双模）
│   │   │   ├── pg_preference_repo.py # 偏好（PG + 内存双模）
│   │   │   ├── user_repo.py          # 用户（PG + 内存双模）
│   │   │   └── address_repo.py       # 地址（PG + 内存双模）
│   │   ├── schemas/                # Pydantic 数据契约
│   │   │   ├── product.py          # Product / Sku / RagKnowledge
│   │   │   ├── workflow.py         # WorkflowState / Constraints / RetrievalPlan / TraceStep
│   │   │   ├── a2a.py              # AgentCard / AgentMessage / Artifact
│   │   │   ├── cart.py             # CartItem / Cart / CheckoutRequest/Response
│   │   │   ├── auth.py             # RegisterRequest / LoginRequest / AuthResponse
│   │   │   ├── address.py          # AddressCreate/Update/Response
│   │   │   ├── preference.py       # PreferenceUpdate/Response
│   │   │   ├── decision_result.py  # DecisionResult / ScoreBreakdown
│   │   │   ├── evidence.py         # Evidence / EvidenceType
│   │   │   └── visual.py           # VisualResult / VisualEvidence
│   │   ├── retrieval/              # 检索层
│   │   │   └── text_retriever.py   # jieba 关键词 + Qdrant 向量 RRF 融合
│   │   ├── decision/               # 决策层
│   │   │   └── scoring.py          # 7 维 Decision Scoring 公式
│   │   ├── model_gateway/          # Qwen 模型网关
│   │   │   ├── gateway.py          # 统一调用入口
│   │   │   ├── qwen_chat.py        # Chat 能力
│   │   │   ├── qwen_vision.py      # Vision 能力
│   │   │   ├── qwen_embedding.py   # Embedding 能力
│   │   │   ├── qwen_reranker.py    # Reranker 能力
│   │   │   └── mock_model.py       # Mock 降级
│   │   ├── workflow/               # LangGraph 工作流
│   │   │   └── graph.py            # StateGraph 编排：Router→Visual→Retrieval→Reranker→Decision→Response→Guard
│   │   ├── context/                # 上下文编译器
│   │   │   └── compiler.py         # 结构化编译决策上下文
│   │   ├── memory/                 # 偏好记忆
│   │   │   └── preference_memory.py # 多轮对话约束合并 + 话题切换检测
│   │   └── verification/           # 验证层
│   │       ├── evidence_checker.py # 证据充足性检查
│   │       └── response_guard.py   # 5 项回答守门规则
│   └── requirements.txt            # Python 依赖
│
├── android-client/                 # Android 原生客户端（主交付端）
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── app/
│       ├── build.gradle.kts
│       └── src/main/java/com/omnicart/agent/
│           ├── MainActivity.kt
│           ├── MainScreen.kt       # 全局 Scaffold + 底部导航 + NavHost
│           ├── core/
│           │   ├── config/AppConfig.kt
│           │   ├── network/ApiClient.kt    # Retrofit + OkHttp + Auth 拦截器
│           │   ├── network/OmniCartApi.kt  # 全部 API 接口定义 + 数据类
│           │   ├── model/                  # RecommendRequest/Response, Product, DecisionResult
│           │   └── theme/                  # Color / Type / Theme (Material 3)
│           └── feature/
│               ├── chat/           # 豆仔智能（ChatScreen + ChatViewModel + ChatUiState）
│               ├── shop/           # 商品展示（ProductListScreen + ProductCard）
│               ├── cart/           # 购物车（CartScreen + CartViewModel）
│               ├── profile/        # 个人中心（ProfileScreen）
│               ├── auth/           # 登录/注册（LoginScreen + AuthViewModel + AuthManager）
│               └── address/        # 地址管理（AddressScreen + AddressViewModel）
│
├── data/                           # 本地商品数据（JSON）+ golden_queries
├── ecommerce_agent_dataset/        # 官方数据集（100 件商品，4 品类，含实拍 JPG）
├── docs/                           # 项目文档
│   ├── OMNICART_AGENT_COMPLETE_BLUEPRINT.md   # 最终蓝图（默认只读）
│   ├── DEVELOPMENT_DIRECTORY_STRUCTURE.md     # 目标目录结构 + 施工规范
│   ├── DEVELOPMENT_RULES.md                   # AI Agent 开发行为规则
│   ├── DEVELOPMENT_PROGRESS.md                # 开发进度记录
│   ├── PRODUCT_FUNCTIONS_AND_USER_GUIDE.md    # 产品功能与用户指南
│   ├── CHANGELOG.md                           # 变更日志
│   ├── KNOWLEDGE_LOG.md                       # 技术知识沉淀
│   ├── DECISION_LOG.md                        # 关键技术决策
│   └── 答辩QA手册.md                          # 答辩 QA 手册（13 章）
│
├── scripts/                        # 自动化脚本
│   ├── smoke_recommend.py          # 推荐链路快速验证
│   ├── seed_postgresql.py          # JSON → PostgreSQL 数据迁移
│   └── seed_qdrant.py              # Product Embedding → Qdrant 索引
│
├── alembic/                        # 数据库迁移（Alembic）
├── tests/                          # 测试
├── frontend/                       # ⚠️ 已废弃（Next.js），仅历史参考
│
├── run.py                          # 一键启动后端
├── requirements.txt                # Python 依赖
├── .env.example                    # 环境变量模板
├── .gitignore
├── CLAUDE.md                       # Claude Code 项目指令
└── README.md                       # 本文件
```

> **注意**：上述目录是**当前实际结构**（非目标结构）。遵循"竖向闭环优先"原则，文件按里程碑逐步创建，**禁止一次性创建空壳目录**。

---

## 5. GitHub 私有仓库协作流程

### 5.1 克隆仓库

```bash
git clone git@github.com:TheodoreYang6/OmniCart-Agent.git
cd OmniCart-Agent
```

### 5.2 配置开发环境

#### 后端环境（Python 3.11.15 + Conda）

```bash
# 创建 conda 环境
conda create -n omnicart python=3.11 -y
conda activate omnicart

# 安装依赖（使用清华镜像）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 环境变量配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入 QWEN_API_KEY（从团队获取）
# QWEN_API_KEY=sk-xxxx
# OMNICART_MOCK_MODE=true  ← 无 API 时可开启 Mock 模式
```

**`.env` 文件已加入 `.gitignore`，不要提交到仓库。**

#### 数据库（可选，V1 需要）

```bash
# 安装 PostgreSQL 18 + Qdrant 1.18
# 启动数据库后，初始化数据
python scripts/seed_postgresql.py
python scripts/seed_qdrant.py
```

> 不配置数据库时系统自动降级为 JSON 文件 + jieba 关键词模式。

#### Android 环境

1. 安装 Android Studio Hedgehog (2023.1.1) 或更高版本
2. 用 Android Studio 打开 `android-client/` 目录
3. 等待 Gradle Sync 完成
4. 创建模拟器（API 35）或连接真机（开启 USB 调试）
5. 在 `AppConfig.kt` 中配置后端地址：
   - 模拟器：`http://10.0.2.2:8006/`（默认，映射宿主机 localhost）
   - 真机：`http://<电脑局域网IP>:8006/`

### 5.3 启动开发环境

#### 启动后端

```bash
# 方式一：一键启动
python run.py

# 方式二：直接 uvicorn
cd backend && uvicorn app.main:app --host 127.0.0.1 --port 8006
```

验证：
```bash
curl http://127.0.0.1:8006/api/health
# → {"status":"ok","service":"omnicart-agent","version":"0.1.0"}
```

#### 启动 Android 客户端

```bash
cd android-client

# 编译 Debug APK
./gradlew assembleDebug

# 安装到模拟器/真机
adb install app/build/outputs/apk/debug/app-debug.apk

# 或直接在 Android Studio 中点击 Run 'app'
```

#### ADB 反向代理（真机 USB 连接时）

```bash
# 将手机 8006 端口转发到电脑 8006 端口
adb reverse tcp:8006 tcp:8006
```

### 5.4 Git 分支协作规范

```
main         ← 稳定版本，只接受经过测试的 PR
  └─ dev     ← 日常开发主线
       ├─ feature/auth        ← 用户登录/注册
       ├─ feature/address     ← 地址管理
       ├─ feature/cart-fix    ← 购物车修复
       └─ feature/...
```

**工作流程：**

```bash
# 1. 从 dev 创建功能分支
git checkout dev
git pull origin dev
git checkout -b feature/xxx

# 2. 开发 + 测试 + 提交
git add <files>
git commit -m "feat: xxx"

# 3. 推送到远程
git push origin feature/xxx

# 4. 在 GitHub 上创建 PR → dev
# 5. Code Review 通过后合并
```

**Commit Message 格式：**
```
feat: 新增用户登录/注册 API
fix: 修复 PreferenceMemory 话题切换时 category 未清除
refactor: 重构 CartViewModel 为真实 API
docs: 更新答辩QA手册
```

### 5.5 不可提交的文件

以下文件**严禁提交**到仓库：

| 文件 | 原因 |
|------|------|
| `.env` | 包含 API 密钥 |
| `local.properties` | Android SDK 本地路径 |
| `*.apk / *.aab` | 二进制产物 |
| `.gradle/` / `build/` | 构建产物 |
| `__pycache__/` | Python 缓存 |
| `.idea/` | IDE 个人配置 |
| `data/uploads/` | 运行时上传文件 |
| `.claude/` | Claude Code 内部数据 |

### 5.6 开发后必须做的事

1. 运行测试：`python -m pytest tests/ -v`
2. 运行编译：`./gradlew assembleDebug`
3. 更新 `docs/DEVELOPMENT_PROGRESS.md`（进度记录）
4. 更新 `docs/CHANGELOG.md`（变更日志）
5. 如有关键技术取舍，更新 `docs/DECISION_LOG.md`

---

## 6. API 端点总览（26 个）

### 健康检查
```
GET /api/health
```

### 商品
```
GET  /api/products                   # 商品列表（支持 category/page/page_size）
GET  /api/products/{product_id}       # 商品详情
```

### 推荐（核心）
```
POST /api/recommend/v2                # Agent Workflow 推荐（文本 + 图片）
```

### 图片上传
```
POST /api/upload                      # multipart/form-data 图片上传
```

### 用户认证
```
POST /api/auth/register               # 注册
POST /api/auth/login                  # 登录
GET  /api/auth/profile                # 获取个人信息（需 Bearer Token）
```

### 地址管理
```
GET    /api/addresses                 # 地址列表
POST   /api/addresses                 # 新增地址
PUT    /api/addresses/{address_id}    # 编辑地址
DELETE /api/addresses/{address_id}    # 删除地址
```

### 偏好设置
```
GET    /api/preferences?session_id=   # 获取偏好
PUT    /api/preferences?session_id=   # 更新偏好（增量合并）
DELETE /api/preferences?session_id=   # 重置偏好
```

### 购物车
```
GET    /api/cart                      # 获取购物车
POST   /api/cart/items                # 加入购物车
PUT    /api/cart/items/{cart_item_id} # 修改数量/选择状态
DELETE /api/cart/items/{cart_item_id} # 移除商品
POST   /api/cart/select-all           # 全选/取消全选
DELETE /api/cart/clear                # 清空购物车
```

### 结算
```
POST /api/checkout                    # 模拟结算（mock checkout，不接入真实支付）
```

### Agent 受控操作
```
POST /api/agent/action                # 豆仔受控操作（add_to_cart 等）
```

---

## 7. 测试

### 运行后端测试

```bash
cd backend
python -m pytest tests/ -v
```

### 运行 Smoke Test（需后端运行中）

```bash
python scripts/smoke_recommend.py
```

### 测试要求

- V1-Core 必须通过 Agent Workflow 完整链路测试
- 每个关键模块必须有单元测试或 smoke test
- Demo Mode 下完整链路可复现

---

## 8. 安全红线

- **禁止**硬编码 API Key — 使用 `.env` 文件
- **禁止**提交 `.env` 到仓库
- **禁止**接入真实支付 SDK 或真实支付网关
- **禁止**Agent 直接操作数据库（必须通过 Repository 层）
- V1 工具**默认只读**（不执行下单、支付、账号操作）
- **禁止**绕过 ToolManager 直接调用外部工具
- **禁止**伪造测试结果

---

## 9. 团队角色

| 角色 | 职责 |
|------|------|
| 后端开发 | FastAPI / Agent Workflow / RAG / Agent / Decision Scoring |
| Android 开发 | Compose UI / ViewModel / API 对接 / Demo Mode |
| 数据工程 | 商品数据集 / Golden Queries / 评测脚本 |
| 文档 & 答辩 | 蓝图维护 / 答辩 QA / Demo 脚本 |

---

## 10. 快速开始（新成员 5 分钟上手）

```bash
# 1. 克隆仓库
git clone git@github.com:TheodoreYang6/OmniCart-Agent.git
cd OmniCart-Agent

# 2. 安装 Python 依赖
conda create -n omnicart python=3.11 -y && conda activate omnicart
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 OMNICART_MOCK_MODE=true，OMNICART_PORT=8006

# 4. 启动后端
python run.py

# 5. 验证
curl http://127.0.0.1:8006/api/health
# → {"status":"ok", ...}

# 6. Android 客户端（可选）
# 用 Android Studio 打开 android-client/，Gradle Sync 后 Run
```

---

**OmniCart Agent** — 不只是导购，是可解释的 Agent 购物决策系统。
