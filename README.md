<p align="center">
  <img src="design/app-icon/omnicart-omi-cart-store-512-v1.png" width="148" alt="欧米 · OmniCart Agent" />
</p>

<h1 align="center">OmniCart Agent</h1>

<p align="center">
  <strong>由欧米驱动的多模态电商购物智能体</strong>
  <br />
  从自然语言需求、商品检索与证据分析，到购物车、地址和订单的完整购物闭环
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white" alt="Python 3.11" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=0B1220" alt="React 19" />
  <img src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white" alt="Vite 8" />
  <img src="https://img.shields.io/badge/PostgreSQL-V011-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Qdrant-Hybrid-DC244C" alt="Qdrant Hybrid" />
  <img src="https://img.shields.io/badge/Redis-DB_1-DC382D?logo=redis&logoColor=white" alt="Redis" />
</p>

<p align="center">
  <a href="#快速开始">快速开始</a> ·
  <a href="#系统架构">系统架构</a> ·
  <a href="#功能与页面">功能与页面</a> ·
  <a href="#api-速查">API</a> ·
  <a href="#测试与质量门禁">测试</a> ·
  <a href="DEVELOPMENT.md">开发指南</a>
</p>

---

## 项目简介

OmniCart Agent 不是只会回答问题的电商客服，而是一个能够理解需求、查找商品、展示证据并执行购物操作的 Agent 系统。

用户可以用文字、图片或语音告诉欧米自己的预算、用途、偏好和顾虑。系统会完成意图理解、查询改写、混合检索、语义精排、证据评分和流式生成，并把商品对比、推荐依据、风险提示和可执行操作一起返回。后续对话可以继续完成加购、修改数量、结算和订单查询。

当前仓库以 **React Web 客户端**为主要开发界面，同时保留 Kotlin + Jetpack Compose Android 客户端。后端由 FastAPI、LangGraph、PostgreSQL、Qdrant 和 Redis 组成，并支持本地 Embedding 与 Reranker 离线推理。

### 当前实现基线

| 模块 | 当前实现 |
| --- | --- |
| Web | React 19、TypeScript、Vite 8、React Query、Zustand、Tailwind CSS |
| Android | Kotlin 2.0、Jetpack Compose、Material 3，`minSdk 26 / targetSdk 35` |
| API | FastAPI 2.0.0 服务，REST + SSE，默认端口 `8006` |
| Agent | LangGraph 工作流、动态编排、工具调用、深度思考模式、上下文压缩 |
| 身份 | Web HttpOnly Cookie、游客签名身份、Android Bearer Token 兼容 |
| 商品数据 | 8 个一级品类，共 1000 件商品，包含规格、FAQ、评价与派生字段 |
| PostgreSQL | Alembic V001–V011，保存商品、用户、会话、偏好、购物车、地址和订单 |
| Qdrant | `product_chunks_v7_hybrid`，1024 维 `dense` + BM25 `bm25` 命名向量 |
| Redis | 项目独占 DB 1，用于搜索、视觉、改写和工作流缓存 |
| 本地模型 | `Qwen3-Embedding-0.6B` + `bge-reranker-v2-m3`，支持 CUDA / MPS / CPU |
| 在线模型 | Qwen Chat / Vision / Omni，文本任务可按模型名路由至 DeepSeek |

> 模型权重、`.env`、虚拟环境和数据库运行数据不会提交到 Git。换电脑后需要按本文重新创建环境并下载模型。

---

## 核心能力

### 从对话到购买的完整闭环

用户可以先说“推荐一款 500 元以内的降噪耳机”，再继续说“比较前两个”“把第二个加入购物车”“数量改成 2”“用默认地址下单”。欧米会保持会话上下文，并把自然语言指令转换为真实业务操作。

### 可解释、可追溯的 RAG

检索结果不会直接交给大模型自由发挥。系统将商品描述、规格、FAQ、评论和视觉结果转换为证据，推荐结论通过 `evidence_ids` 与原始数据绑定。Decision 与 Verification 层继续检查价格、品牌、风险和证据覆盖，减少商品幻觉与无依据推荐。

### Dense + BM25 混合检索

Qwen3 Embedding 负责 1024 维语义召回，中文 BM25 稀疏向量补充精确词面信号。Qdrant 使用 `Prefetch + FusionQuery(RRF)` 完成服务端融合，并通过品类、子品类、价格、评分和块类型 payload 索引过滤。混合检索不可用时自动降级为纯 Dense；Qdrant 不可用时仍可降级到本地缓存。

### 本地模型优先

- `Qwen3-Embedding-0.6B`：查询侧使用检索指令前缀，输出 L2 归一化的 1024 维向量。
- `bge-reranker-v2-m3`：默认 Cross Encoder 精排器。
- `Qwen3-Reranker-0.6B`：当设置 `OMNICART_RERANKER=qwen3` 时作为兼容回退。
- 模型按需加载并在服务启动后后台预热，CUDA 与 MPS 使用半精度推理。

### 可信身份与跨端兼容

Web 使用签名 HttpOnly Cookie，不再信任请求参数中的 `user_id`。身份解析顺序为：

1. Bearer Token（Android 与 API 客户端）；
2. 登录 Cookie；
3. 游客 Header / Cookie；
4. 显式开启时才允许旧式 `user_id`。

游客可以浏览商品、聊天和使用购物车；订单、地址、偏好等能力要求登录。登录或注册后，游客购物车按 `product_id + sku_id` 合并到用户购物车。

### 可恢复的前端交互

- SSE 支持 UTF-8 尾块、多行 `data`、异常帧、中止与幂等完成。
- 历史会话切换、退出登录或新建会话后，旧请求不能回写当前页面。
- 商品搜索、分类与分页写入 URL，可刷新、返回和分享。
- 购物车使用逐项 pending、乐观更新、最新意图合并和精确失败回滚。
- 页面级懒加载、统一错误边界、正式 404、键盘操作和低动效模式均已接入。

---

## 系统架构

```mermaid
flowchart TB
    subgraph Clients[客户端]
        Web[React Web<br/>Chat · Shop · Cart · Profile]
        Android[Android Compose<br/>Bearer Token 兼容]
    end

    Web -->|Cookie · REST · SSE| API
    Android -->|Bearer · REST · SSE| API

    subgraph Backend[FastAPI Backend :8006]
        API[API / Actor Resolver]
        Workflow[LangGraph Workflow]
        Tools[Shopping Tools]
        Memory[Memory / Context]
        Verify[Evidence / Verification]
        Gateway[Model Gateway]
        API --> Workflow
        Workflow <--> Tools
        Workflow <--> Memory
        Workflow --> Verify
        Workflow <--> Gateway
    end

    Gateway --> LocalModels[Qwen3 Embedding<br/>BGE Reranker]
    Gateway --> CloudModels[Qwen / DeepSeek<br/>Chat · Vision · Voice]
    API --> PostgreSQL[(PostgreSQL)]
    Workflow --> Qdrant[(Qdrant<br/>Dense + BM25)]
    Workflow --> Redis[(Redis DB 1)]
```

### Agent 主链路

```text
Request
  │
  ├─ Router ──────────────── 意图、约束、模式与检索计划
  ├─ Visual（可并行） ────── 图片理解与商品映射
  ├─ Retrieval ───────────── 语义 / 关键词 / 补充证据召回
  ├─ Reranker ────────────── BGE 语义精排与商品融合
  ├─ Evidence Check ──────── 证据充分性检查
  ├─ Decision ────────────── 多维评分、风险与推荐等级
  ├─ Response ────────────── 流式回答、商品与操作卡片
  └─ Guard ───────────────── 品牌、价格、风险和答案一致性校验
```

对于购物车、地址、订单和库存意图，工作流会调用受身份约束的 Shopping Tools。深度思考请求可以进入多轮 OmniAgent Loop；普通请求继续使用低延迟 Pipeline。

### 代码分层

后端遵循“框架与实现分离”的边界：

| 层 | 目录 | 责任 |
| --- | --- | --- |
| Framework | `backend/app/framework/` | 检索、记忆、上下文、工具、技能和编排协议 |
| Providers | `backend/app/providers/` | 业务召回源、记忆实现、工具实现和外部能力适配 |
| Agents | `backend/app/agents/` | Router、Visual、Retrieval、Decision、Response、Shop Action |
| Workflow | `backend/app/workflow/` | LangGraph 状态、节点与主图编排 |
| Gateway | `backend/app/model_gateway/` | 本地与在线模型路由、超时、重试和降级 |
| Data | `models/`、`repositories/`、`services/` | ORM、仓储与业务服务 |
| API | `backend/app/api/` | 认证、商品、对话、购物闭环、语音、评测与可观测接口 |

更完整的边界说明见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 和 [MODULES.md](MODULES.md)。

---

## 功能与页面

### Web 页面

| 路由 | 功能 | 访问要求 |
| --- | --- | --- |
| `/chat` | 欧米对话、图片/语音输入、证据、推理和商品分析 | 游客可用 |
| `/shop` | 商品搜索、分类筛选、分页与 URL 状态恢复 | 游客可用 |
| `/product/:productId` | 商品详情、AI 总结、加购与聚焦分析 | 游客可用 |
| `/cart` | 数量、选择、删除、结算摘要与并发安全更新 | 游客可用 |
| `/profile` | 宽屏个人工作台、订单/地址/偏好摘要 | 游客 / 用户差异展示 |
| `/orders` | 历史订单 | 需要登录 |
| `/address` | 收货地址管理 | 需要登录 |
| `/preferences` | 结构化购物偏好与欧米记忆 | 需要登录 |
| `/login` | 登录、注册、游客购物车合并与返回路径 | 公开 |

`/brand` 只在 Vite 开发环境注册，用于欧米品牌组件预览；生产构建不会暴露该页面。

### 欧米品牌系统

当前欧米形象统一用于 README、Web 导航、欢迎页、登录页、状态反馈和移动端图标。组件支持空闲、倾听、搜索、思考、说话、成功、加购、下单和错误等状态，并在 `prefers-reduced-motion` 下关闭非必要动画。

最终素材位于：

- `design/app-icon/`：移动应用图标源文件；
- `design/brand/omi-perch-transparent-v4.png`：当前趴姿欧米透明源图；
- `web-client/public/brand/`：供浏览器使用的 AVIF、WebP 和 PNG 响应式版本。

---

## 快速开始

以下流程是当前项目的主要开发路径：**Windows + Conda + 本地 PostgreSQL / Qdrant / Memurai**。Docker 文件仍保留在仓库中，但不作为本地开发的默认步骤。

### 1. 准备环境

- Git
- Conda / Miniconda
- Python 3.11
- Node.js 20.19+、22.12+ 或当前 LTS
- PostgreSQL Windows 服务
- Qdrant Windows x64
- Memurai Developer 或兼容 Redis 服务
- NVIDIA GPU 可选；本地模型也可以在 CPU 上运行，但速度会明显降低

### 2. 克隆并安装依赖

```powershell
git clone https://github.com/TheodoreYang6/OmniCart-Agent.git
Set-Location OmniCart-Agent

conda create -n omnicart python=3.11 -y
conda activate omnicart
python -m pip install -r requirements.txt

Copy-Item .env.example .env

Set-Location web-client
npm ci
Set-Location ..
```

如需 RTX 50 系显卡支持，请根据本机驱动从 PyTorch 官方 CUDA 源安装匹配版本，再验证：

```powershell
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

### 3. 准备本地模型

模型不进入 Git 仓库。默认目录结构为：

```text
D:\OmniCart-Agent-runtime\models\
├── Qwen3-Embedding-0.6B\
└── bge-reranker-v2-m3\
```

对应 Hugging Face 仓库：

- `Qwen/Qwen3-Embedding-0.6B`
- `BAAI/bge-reranker-v2-m3`

下载后确认 `.env` 包含：

```dotenv
OMNICART_MOCK_MODE=false
OMNICART_USE_LOCAL_MODELS=true
OMNICART_MODELS_DIR=D:/OmniCart-Agent-runtime/models
OMNICART_RERANKER=bge
EMBEDDING_DIMENSION=1024
```

### 4. 配置本机服务

从模板复制得到的 `.env` 已包含完整键名。必须在本机修改 PostgreSQL 密码和会话密钥：

```dotenv
OMNICART_SESSION_SECRET=请替换为至少32字节的随机值
DATABASE_URL=postgresql+asyncpg://omnicart:本机密码@127.0.0.1:5432/omnicart
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION_NAME=product_chunks_v7_hybrid
OMNICART_CHUNK_COLLECTION=product_chunks_v7_hybrid
REDIS_URL=redis://127.0.0.1:6379/1
```

不要提交 `.env`。仓库只维护不含密钥的 [.env.example](.env.example)。

### 5. 启动本地基础设施

已经完成 PostgreSQL、Qdrant 和 Memurai 安装与配置时，可以双击：

```text
start-databases.bat
```

或在 PowerShell 中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-local-infra.ps1
```

脚本会检查并启动：

| 服务 | 地址 | 数据用途 |
| --- | --- | --- |
| PostgreSQL | `127.0.0.1:5432` | 业务数据与用户状态 |
| Qdrant | `127.0.0.1:6333 / 6334` | Dense / BM25 商品块索引 |
| Redis / Memurai | `127.0.0.1:6379/1` | 项目缓存 |

该脚本负责启动已安装的服务，不负责下载安装数据库或模型。

### 6. 首次初始化数据

```powershell
alembic upgrade head

$env:PYTHONPATH = "backend"
python scripts/seed_postgresql.py
python scripts/index_product_chunks.py --recreate
```

`alembic upgrade head` 应到达 V011。种子脚本导入 1000 件商品；分块索引脚本根据 `.env` 创建 V7 混合集合。完整重算 10066 个商品块的本地 Embedding 会花费较长时间，请避免无必要地重复 `--recreate`。

如果已有 V6 Dense 集合，可以使用迁移脚本复用 Dense 向量并补充 BM25：

```powershell
$env:PYTHONPATH = "backend"
python scripts/migrate_v6_to_v7_hybrid.py --dry-run
python scripts/migrate_v6_to_v7_hybrid.py
```

### 7. 启动项目

一键启动前后端并检查三个本地服务：

```powershell
conda activate omnicart
python run.py
```

也可以分别启动：

```powershell
# 终端 1：后端
Set-Location backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8006 --reload

# 终端 2：前端
Set-Location web-client
npm run dev
```

打开：

- Web：<http://127.0.0.1:5173>
- API 文档：<http://127.0.0.1:8006/docs>
- 健康检查：<http://127.0.0.1:8006/api/health>

完整模式下健康检查应包含：

```json
{
  "status": "ok",
  "service": "omnicart-agent",
  "version": "2.0.0",
  "postgres": "connected",
  "qdrant": "connected",
  "redis": "connected"
}
```

### 轻量 MOCK 模式

只开发 UI 或 API 契约时，可以在 `.env` 中关闭本地模型并清空外部连接：

```dotenv
OMNICART_MOCK_MODE=true
OMNICART_USE_LOCAL_MODELS=false
DATABASE_URL=
QDRANT_URL=
REDIS_URL=
```

服务会使用 Mock Model 与本地数据降级路径，但登录、持久化、真实向量搜索和完整订单能力需要对应基础设施。

---

## 配置说明

### 后端关键变量

| 变量 | 建议值 / 作用 |
| --- | --- |
| `OMNICART_HOST` | 后端监听地址，默认 `127.0.0.1` |
| `OMNICART_PORT` | 后端端口，当前为 `8006` |
| `OMNICART_SESSION_SECRET` | Cookie 与游客身份签名密钥，必须自行生成 |
| `OMNICART_CORS_ORIGINS` | 允许携带凭据的明确 Web 来源列表 |
| `OMNICART_ALLOW_LEGACY_USER_ID` | 是否信任旧式 `user_id`，默认 `false` |
| `OMNICART_MOCK_MODE` | 使用 Mock Model，完整模式设为 `false` |
| `OMNICART_USE_LOCAL_MODELS` | 是否启用本地 Embedding / Reranker |
| `OMNICART_MODELS_DIR` | 两个本地模型的父目录 |
| `OMNICART_RERANKER` | `bge` 默认；`qwen3` 使用兼容回退 |
| `DATABASE_URL` | PostgreSQL SQLAlchemy Async URL |
| `QDRANT_URL` | Qdrant HTTP 地址 |
| `OMNICART_CHUNK_COLLECTION` | 当前检索集合名 |
| `OMNICART_ENABLE_HYBRID_RETRIEVAL` | 是否发送 BM25 稀疏查询 |
| `OMNICART_ENABLE_RERANK` | 是否启用语义精排 |
| `REDIS_URL` | Redis 连接地址，当前项目使用 DB 1 |
| `QWEN_API_KEY` | Chat / Vision / Voice 等在线能力密钥，可留空 |
| `DEEPSEEK_API_KEY` | DeepSeek 兼容文本模型密钥，可留空 |

完整模板见 [.env.example](.env.example)，强类型定义见 [backend/app/core/config.py](backend/app/core/config.py)。

### 前端变量

复制 `web-client/.env.example` 为 `web-client/.env.local`：

```dotenv
VITE_API_BASE=
```

本地开发留空即可，Vite 会把 `/api` 与 `/images` 代理到 `http://127.0.0.1:8006`。生产构建时再设置真实可访问的后端地址。

---

## API 速查

FastAPI 自动文档位于 `/docs`。当前应用注册了 17 个 API 路由模块和 60 余个 HTTP 端点，主要入口如下：

| 能力 | 方法与路径 | 说明 |
| --- | --- | --- |
| 健康检查 | `GET /api/health` | PostgreSQL、Qdrant、Redis 实际连接状态 |
| 游客身份 | `POST /api/auth/guest` | 建立签名游客 Cookie 与令牌 |
| 登录 / 注册 | `POST /api/auth/login`、`POST /api/auth/register` | 建立登录 Cookie并合并游客购物车 |
| 退出 | `POST /api/auth/logout` | 撤销登录令牌并重新建立游客身份 |
| 商品列表 | `GET /api/products` | 搜索、分类与分页 |
| 商品详情 | `GET /api/products/{product_id}` | 商品、规格、FAQ 与评价 |
| 商品总结 | `POST /api/products/{product_id}/ai-summary` | 流式 AI 商品分析 |
| 同步推荐 | `POST /api/recommend`、`POST /api/recommend/v2` | 结构化推荐结果 |
| 流式 Agent | `POST /api/recommend/stream` | SSE 对话、分析与购物动作 |
| 图片上传 | `POST /api/upload` | 多模态图片输入 |
| 购物车 | `/api/cart`、`/api/cart/items` | 查询、加购、改量、删除和选择 |
| 结算 / 订单 | `POST /api/checkout`、`GET /api/orders` | 登录用户购物闭环 |
| 地址 | `/api/addresses` | 登录用户地址 CRUD |
| 偏好 | `/api/preferences`、`/api/preferences/entries` | 偏好解析、条目与画像管理 |
| 会话 | `/api/conversations` | 历史会话、消息与删除 |
| 语音 | `/api/voice/transcribe`、`/api/voice/tts` | ASR 与 TTS |
| 评测 | `/api/eval/*`、`/eval` | Agent / RAG 评测与仪表盘 |
| 可观测 | `/api/observability/*` | Trace 与统计信息 |

前端所有真实请求路径由 `tests/unit/test_frontend_api_contract.py` 与后端路由契约共同校验。

---

## 数据与检索

### 商品块结构

每件商品会被拆分为标题描述、规格、FAQ、评论等不同块。每个块携带统一 payload：

- 商品、块与类型标识；
- 标题、品牌、一级与二级品类；
- 价格、平均评分、评论数量和负面评论数量；
- FAQ 问题、评论评分与展示昵称；
- 可供回答引用的原始文本。

V7 集合为每个块同时保存：

- `dense`：Qwen3 Embedding 生成的 1024 维归一化向量；
- `bm25`：基于项目语料统计生成的中文稀疏向量。

### 降级策略

| 故障 | 行为 |
| --- | --- |
| BM25 或旧集合不兼容 | 自动改用纯 Dense 搜索 |
| Qdrant 不可用 | 使用本地商品块缓存 |
| Redis 不可用 | 跳过缓存，直接执行原始能力 |
| PostgreSQL 未配置 | 部分公开能力使用 JSON / 本地数据模式 |
| 在线模型超时 | 重试、熔断或模板回答，取决于能力类型 |
| 本地模型缺失 | 状态检查返回缺失信息，不伪装为已就绪 |

---

## 目录结构

```text
OmniCart-Agent/
├── backend/
│   ├── app/
│   │   ├── agents/             # 业务 Agent
│   │   ├── api/                # FastAPI 路由
│   │   ├── core/               # 配置、身份与基础设施连接
│   │   ├── framework/          # RAG / Memory / Context / Tools 框架
│   │   ├── model_gateway/      # 本地与在线模型网关
│   │   ├── providers/          # 框架协议的业务实现
│   │   ├── repositories/       # PostgreSQL / Qdrant 仓储
│   │   ├── verification/       # 证据与答案一致性守卫
│   │   └── workflow/           # LangGraph 主工作流
│   └── tests/
├── web-client/                 # React 19 Web 客户端
│   ├── e2e/                    # Playwright 测试
│   ├── public/brand/           # 欧米 Web 素材
│   └── src/                    # 页面、组件、API 与 Store
├── android-client/             # Kotlin / Jetpack Compose 客户端
├── alembic/versions/           # V001–V011 数据库迁移
├── ecommerce_agent_dataset/    # 1000 件商品数据与图片
├── design/                     # 欧米最终图标与品牌源素材
├── scripts/                    # 初始化、索引、迁移、评测与运维脚本
├── tests/                      # 后端单元、集成与契约测试
├── docs/                       # 架构、ADR、规范与工作记录
├── .env.example                # 安全配置模板
├── run.py                      # 前后端一键启动入口
└── start-databases.bat         # Windows 本地基础设施启动入口
```

---

## 测试与质量门禁

### 后端

```powershell
conda activate omnicart
python -m pytest

# 只运行快速单元测试
python -m pytest tests/unit backend/tests/unit -q

# 覆盖率
python -m pytest --cov=backend/app --cov-report=term-missing
```

### 前端

```powershell
Set-Location web-client
npm run typecheck
npm run lint
npm run test
npm run test:coverage
npm run build
npm run test:e2e
```

前端覆盖率阈值在 `vite.config.ts` 中统一设置为语句、分支、函数和行均不低于 80%。Playwright 覆盖桌面与移动视口，并使用 axe 检查关键页面的严重可访问性问题。

### 架构与评测

```powershell
# Framework / Provider 依赖边界
python scripts/check_governance.py

# RAG 检索评测
python scripts/eval_retrieval.py

# 数据集质量
python scripts/validate_dataset.py
```

提交前至少应通过后端测试、前端 TypeScript、ESLint、Vitest 和生产构建。涉及检索、身份或购物车时，还应运行对应契约测试与 E2E。

---

## 换一台电脑继续开发

Git 仓库负责同步可复现的代码与必要资产，不同步机器状态。迁移时请按以下清单恢复：

1. 克隆仓库并创建 Python 3.11 Conda 环境；
2. 使用 `requirements.txt` 与 `web-client/package-lock.json` 安装依赖；
3. 复制 `.env.example` 为 `.env`，重新填写密钥、密码和模型路径；
4. 安装或恢复 PostgreSQL、Qdrant、Memurai；
5. 下载两个本地模型到 `OMNICART_MODELS_DIR`；
6. 执行 Alembic、商品种子和向量索引脚本；
7. 运行 `python run.py` 并检查 `/api/health`。

以下内容不会上传，不能通过 `git clone` 恢复：

- `.env` 与任何真实密钥；
- Conda / `.venv`、`node_modules` 与构建缓存；
- Hugging Face 模型权重；
- PostgreSQL、Qdrant、Redis 的本地运行数据；
- 上传文件、日志、Trace、评测临时结果和浏览器登录态；
- 个人文档与设计过程中的废弃中间图。

---

## 文档索引

| 文档 | 用途 |
| --- | --- |
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发流程、环境、门禁与常见任务 |
| [MODULES.md](MODULES.md) | 重要模块职责、入口和修改边界 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | V3 分层架构与 Provider / Registry 设计 |
| [docs/CONSTITUTION.md](docs/CONSTITUTION.md) | 项目工程约束与长期原则 |
| [docs/adr/](docs/adr/) | RAG、Memory 和上下文压缩决策记录 |
| [docs/specs/](docs/specs/) | 检索、查询理解、数据集与编排规范 |
| [DEPLOY.md](DEPLOY.md) | 可选的服务器与 Docker 部署资料 |
| [SERVER_OPS.md](SERVER_OPS.md) | 历史服务器运维资料 |

---

<p align="center">
  <img src="web-client/public/brand/omi-cart-avatar-256-v2.webp" width="72" alt="欧米头像" />
  <br />
  <strong>OmniCart Agent · 让欧米把“找商品”变成一场可以继续追问、可以验证、也可以直接行动的对话。</strong>
</p>
