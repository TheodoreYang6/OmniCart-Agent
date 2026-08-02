# DEVELOPMENT.md — 开发者上手指南

> 面向「换一台机器接手这个项目」的场景。按本文从上到下走一遍，即可从空目录到本地跑通全链路。
>
> 相关文档：[MODULES.md](MODULES.md)（模块职责与关键文件） · [DEPLOY.md](DEPLOY.md)（服务器部署） · [SERVER_OPS.md](SERVER_OPS.md)（线上运维） · [本地运行指南.md](本地运行指南.md)（macOS 逐步操作） · [README.md](README.md)（产品与架构全景）

---

## 目录

- [一、五分钟接手（最短路径）](#一五分钟接手最短路径)
- [二、项目结构说明](#二项目结构说明)
- [三、环境配置步骤](#三环境配置步骤)
- [四、开发流程说明](#四开发流程说明)
- [五、部署指南](#五部署指南)
- [六、重要功能模块说明](#六重要功能模块说明)
- [七、踩坑清单](#七踩坑清单)

---

## 一、五分钟接手（最短路径）

不想读完全文，只想先看到界面跑起来，走这条：

```bash
git clone https://github.com/TheodoreYang6/OmniCart-Agent.git
cd OmniCart-Agent

# 1) 后端配置：复制模板，不填密钥也能跑（MOCK 模式）
cp .env.example .env

# 2) 三个中间件用 Docker 起（PostgreSQL + Qdrant + Redis）
docker compose up -d postgres qdrant redis

# 3) 后端（需要 Python >= 3.11）
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd backend && OMNICART_MOCK_MODE=true python -m uvicorn app.main:app \
  --host 127.0.0.1 --port 8006 --loop asyncio
# 另开终端验证：curl http://127.0.0.1:8006/api/health

# 4) 前端
cd web-client && npm install && npm run dev
# 打开 http://localhost:5173
```

`OMNICART_MOCK_MODE=true` 时不调用真实大模型，回复是桩数据，但**全链路结构完整**（路由 → 召回 → 决策 → 回复），足够做前端和框架层开发。要看真实推荐效果，见 [3.4 接入真实模型](#34-接入真实模型)。

> ⚠️ `--loop asyncio` 不是可选项，详见[踩坑清单](#七踩坑清单)第 1 条。

---

## 二、项目结构说明

### 2.1 顶层布局

```
OmniCart-Agent/
├── backend/                    # FastAPI 后端（全部业务与框架代码）
│   ├── app/
│   │   ├── main.py             # 应用入口，装配路由与生命周期
│   │   ├── api/                # HTTP 路由层（薄，只做参数校验与编排调用）
│   │   ├── agents/             # 具体 Agent 实现（路由/召回/决策/回复/购物动作）
│   │   ├── framework/          # ★ 框架核心层：与业务无关的可复用能力
│   │   ├── providers/          # ★ 业务实现层：把业务逻辑注册进框架
│   │   ├── workflow/           # LangGraph 工作流编排（多模态决策主图）
│   │   ├── retrieval/          # 检索实现（稀疏编码、子类目别名）
│   │   ├── decision/           # 评分与规则（scoring.py / rules.py）
│   │   ├── verification/       # 答文一致性守卫（防幻觉）
│   │   ├── memory/             # 记忆相关业务代码
│   │   ├── model_gateway/      # 模型网关：多后端适配 + 配置路由
│   │   ├── context/            # 上下文编译（compiler.py）
│   │   ├── prompts/            # Prompt 集中管理（不散落在代码里）
│   │   ├── observability/      # 追踪、请求上下文、Langfuse 导出
│   │   ├── eval/               # RAG 评测指标实现
│   │   ├── core/               # 配置、数据库、缓存、展示层工具
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic 请求/响应模型
│   │   ├── repositories/       # 数据访问层
│   │   └── services/           # 业务服务层
│   └── tests/unit/             # 后端就近单测
├── web-client/                 # React + Vite + TypeScript + Tailwind 前端
│   ├── src/
│   │   ├── pages/              # 路由级页面（Chat/Shop/Cart/Profile/...）
│   │   ├── components/         # 组件（brand/chat/product/layout/ui）
│   │   ├── store/              # Zustand 状态
│   │   ├── api/                # 接口封装与类型
│   │   ├── hooks/              # 自定义 hook
│   │   └── index.css           # 设计令牌 + 组件样式 + 动效 keyframes
│   ├── public/brand/           # 品牌 3D 素材（omi-perch / omi-hero / omi-poses）
│   └── scripts/                # 素材加工 Python 脚本（抠图、图标生成）
├── android-client/             # Android 客户端（Kotlin + Compose）
├── alembic/                    # 数据库迁移（versions/ 下按序号命名）
├── scripts/                    # 运维与评测脚本（灌数据、评测、治理校验）
├── tests/                      # 仓库级测试：unit / integration / eval / manual
├── data/                       # 运行期数据（BM25 统计、评测结果、追踪）
├── ecommerce_agent_dataset/    # 商品数据集（按中文品类分目录，JSON + 图片）
├── docs/                       # 架构文档、宪章、ADR、specs、工作日志
├── submission/                 # 答辩材料
├── docker-compose.yml          # 四容器编排：postgres / qdrant / redis / backend
├── Makefile                    # 常用命令收敛（install/lint/test/run/governance）
├── requirements.txt            # 后端 Python 依赖
├── pyproject.toml              # 工具配置（ruff / pytest，pythonpath=backend）
├── importlinter.ini            # 分层依赖约束（禁止 framework 反向依赖 providers）
└── run.py                      # 一键启动 + 健康检查
```

### 2.2 最关键的一件事：framework 与 providers 的分层

这是本项目架构的核心约定，改代码前必须理解：

```
framework/   —— 只定义协议与编排，不含任何电商业务概念
                （retrieval 编排、memory 融合、tools 调度、orchestration 规划、
                  registry 组件注册、blackboard 请求级黑板）
     ↑ 依赖方向单向向上，禁止反向
providers/   —— 电商业务实现，通过 registry 注册进 framework
                （商品召回源、偏好记忆、购物车/订单工具、上下文提供者）
```

- `framework/` **不允许** import `providers/`，也不允许出现"商品""购物车"这类业务词。
- 新增能力的正确做法：在 `framework/xxx/protocols.py` 里对齐协议 → 在 `providers/xxx/` 写实现 → 注册到 registry。
- 这条约束由 `importlinter.ini` 和 `make governance` 双重把关，CI 会拦。

模块逐一说明见 [MODULES.md](MODULES.md)。

---

## 三、环境配置步骤

### 3.1 依赖版本

| 组件 | 版本要求 | 说明 |
|---|---|---|
| Python | **>= 3.11** | `pyproject.toml` 硬性要求；3.9 会因语法与依赖直接失败 |
| Node.js | >= 18 | Vite 5 要求 |
| PostgreSQL | 16 | 商品、用户、购物车、订单、会话 |
| Qdrant | latest | 向量库，商品向量检索 |
| Redis | 7 | 多级缓存（视觉/检索/改写/工作流） |
| Docker | 可选但推荐 | 三个中间件用 compose 起最省事 |

> 本机踩过的坑：系统自带 `python3` 可能是 3.9，且 `python` 命令可能不存在。务必显式建 venv，并注意 `Makefile` 默认 `PY ?= python`，需要时用 `make test PY=python3.11` 覆盖。

### 3.2 中间件启动

**方式 A：Docker（推荐，跨平台一致）**

```bash
docker compose up -d postgres qdrant redis
docker compose ps        # 等三个都 healthy
```

**方式 B：本机安装**

- macOS：见 [本地运行指南.md](本地运行指南.md)（Homebrew 托管 PG/Redis + 手动起 Qdrant 二进制）
- Windows：仓库根有 `start-databases.bat`

### 3.3 后端配置

配置走 **pydantic-settings + YAML + .env 三层加载**：

| 层 | 文件 | 作用 |
|---|---|---|
| 代码默认值 | `backend/app/core/config.py` | 兜底 |
| 模型路由 | `backend/app/model_gateway/model_config.yaml` | 哪个能力用哪个模型/后端 |
| 环境覆盖 | 根目录 `.env` | 密钥、连接串、开关（**不入库**） |

```bash
cp .env.example .env
```

`.env` 关键项：

```ini
OMNICART_PORT=8006
OMNICART_MOCK_MODE=false            # true=不调真实模型，桩数据跑通全链路
QWEN_API_KEY=                       # 留空则只能用 MOCK 模式
QWEN_BASE_URL=https://dashscope.aliyuncs.com/api/v1
DATABASE_URL=postgresql+asyncpg://omnicart:omnicart@localhost:5432/omnicart
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
```

> Docker 部署时连接串用服务名而非 localhost，模板见 `.env.docker`。

### 3.4 接入真实模型

模型选择不写死在代码里，改 `backend/app/model_gateway/model_config.yaml` 即可切换后端（DashScope / DeepSeek / 本地）。注意两条项目约定：

- 走 OpenAI 兼容协议的模型（Qwen / DeepSeek）统一用同一套适配器；
- Qwen3 系列必须显式设置 `enable_thinking: false`，否则响应延迟显著变差。

填好 `QWEN_API_KEY` 并把 `OMNICART_MOCK_MODE` 置为 `false` 后重启后端生效。

### 3.5 数据初始化（首次或重建时）

```bash
# 表结构
alembic upgrade head

# 灌商品到 PostgreSQL 与 Qdrant
PYTHONPATH=backend python scripts/seed_postgresql.py
PYTHONPATH=backend python scripts/seed_qdrant.py

# 商品分块索引（混合检索用）
PYTHONPATH=backend python scripts/index_product_chunks.py
```

验证：

```bash
curl http://127.0.0.1:8006/api/health
# postgres / qdrant / redis 应均为 connected
curl "http://127.0.0.1:8006/api/products?page=1&page_size=1"
```

### 3.6 前端配置

```bash
cd web-client
npm install
cp .env.example .env.local     # VITE_API_BASE 留空则用 Vite 代理转发 /api
npm run dev                     # http://localhost:5173
```

`.env.local` **不入库**（`.gitignore` 已排除 `*.env.local`）。

---

## 四、开发流程说明

### 4.1 常用命令（全部收敛在 Makefile）

```bash
make install      # 安装运行依赖 + ruff/pytest 开发工具
make run          # 本地起后端（--reload）
make smoke        # MOCK 模式起后端
make lint         # ruff 门禁：framework / providers / config
make fmt          # ruff 自动格式化与修复
make test         # 单元测试（tests/unit + backend/tests/unit）
make governance   # 组件治理校验（分层与注册约束）
make registry     # 生成 docs/COMPONENT_REGISTRY.md
```

`Makefile` 里 `PY ?= python`、`PORT ?= 8006`，可覆盖：`make run PY=python3.11 PORT=8010`。

前端：

```bash
cd web-client
npm run dev       # 开发
npm run lint      # tsc --noEmit
npm run build     # tsc -b && vite build
npm run preview   # 预览产物
```

### 4.2 提交前门禁

改动后端（尤其 `framework/` 或 `providers/`）：

```bash
make lint && make test && make governance
```

改动前端：

```bash
cd web-client && npm run lint && npm run build
```

三者任一不过不要提交。`make governance` 专门拦分层违规（比如 framework 反向 import providers）。

### 4.3 典型任务怎么做

| 任务 | 落点 |
|---|---|
| 加一个召回源 | `providers/recall/` 写实现 → 注册进 `framework/retrieval/registry.py` |
| 加一个工具（可被 Agent 调用） | `providers/tools/` 写实现 → 注册进 `framework/tools/registry.py` |
| 改评分权重 | `backend/app/decision/scoring.py`（改动会影响推荐等级，需跑评测对比） |
| 改 Prompt | `backend/app/prompts/`，不要写进业务代码 |
| 加数据库字段 | `backend/app/models/` 改 ORM → `alembic revision` 生成迁移 → `alembic upgrade head` |
| 加接口 | `backend/app/api/` 加路由（薄）+ `services/` 放逻辑 + `schemas/` 定契约 |
| 换模型 | 只改 `model_gateway/model_config.yaml` |
| 前端加页面 | `web-client/src/pages/` + 在 `App.tsx` 注册路由 |

### 4.4 评测与回归

改了检索、评分、Prompt 这类影响效果的部分，跑对应评测再看数字，不要凭感觉：

```bash
PYTHONPATH=backend python scripts/eval_retrieval.py      # 召回质量
PYTHONPATH=backend python scripts/eval_qu.py             # 查询理解
PYTHONPATH=backend python scripts/eval_memory.py         # 记忆
PYTHONPATH=backend python scripts/smoke_rag_eval.py      # RAG 指标冒烟
PYTHONPATH=backend python scripts/rag_stats.py           # 结果统计
```

结果落在 `data/rag_eval_runs/`。

### 4.5 工作记录

`docs/工作日志.md` 是按任务倒序记录的开发日志（包含每次改动的动机、踩的坑、验证方式）。接手时从最新几条读起，能快速知道上一轮在做什么、留了什么尾巴。

---

## 五、部署指南

服务器部署与线上运维已有专门文档，不在此重复：

- **[DEPLOY.md](DEPLOY.md)** — 从零部署：服务器初始化、Docker 起四容器、数据初始化、代码更新、备份恢复、Nginx 反代、Android APK 构建与 API 地址修改。
- **[SERVER_OPS.md](SERVER_OPS.md)** — 日常运维：启停重启、日志查看、健康检查、防火墙、备份。

补充说明：

### 5.1 Docker 编排

`docker-compose.yml` 定义四个服务：

| 服务 | 镜像 | 端口 |
|---|---|---|
| postgres | postgres:16-alpine | 5432 |
| qdrant | qdrant/qdrant:latest | 6333 / 6334 |
| redis | redis:7-alpine | 6379 |
| backend | 本地构建 | 8006 |

部署时用 `.env.docker` 作模板（连接串已改为容器服务名），复制为 `.env` 并填入真实密钥。

### 5.2 前端产物部署

```bash
cd web-client
# 生产构建前把后端地址写进环境变量
echo "VITE_API_BASE=http://<后端地址>:8006" > .env.production.local
npm run build          # 产物在 web-client/dist/
```

`dist/` 是纯静态文件，交给 Nginx 或任意静态服务器托管即可。注意 `VITE_API_BASE` 是**构建期**注入的，改地址必须重新构建。

### 5.3 Android 客户端

见 [DEPLOY.md](DEPLOY.md) 第六节（APK 构建、API 地址修改、安装）。

---

## 六、重要功能模块说明

模块职责、关键文件、协作关系与改动注意事项，统一放在 **[MODULES.md](MODULES.md)**。

产品视角的完整介绍（Agent 协同流程、RAG 全链路、评分公式七维分解、三层记忆设计、十个关键问题的解法、API 速查、评测体系）见 **[README.md](README.md)**，那份文档更偏"这个系统是什么、为什么这么设计"。

---

## 七、踩坑清单

按踩到的频率排序，都是真实遇到过的：

1. **后端必须加 `--loop asyncio`**
   `uvicorn` 默认用 uvloop，与项目里的 `nest_asyncio` 不兼容，表现为请求挂死或事件循环报错。启动命令固定写成：
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8006 --loop asyncio
   ```

2. **Python 版本**
   要求 `>= 3.11`。系统自带 `python3` 常常是 3.9，装依赖时 `langgraph`、`torch` 等会失败或行为异常。先建 venv 再装。

3. **`python` 命令可能不存在**
   只有 `python3`。`Makefile` 默认 `PY ?= python`，遇到 `command not found` 时用 `make test PY=python3.11`。

4. **仓库根跑测试要靠 pythonpath 注入**
   `pyproject.toml` 里配了 `pythonpath = ["backend"]`，所以 `from app.xxx import ...` 在仓库根能直接用。手动跑脚本时需要自己带上 `PYTHONPATH=backend`。

5. **前端 `VITE_API_BASE` 是构建期变量**
   开发时留空走 Vite 代理；生产改了地址必须重新 `npm run build`，改 `dist/` 里的文件没用。

6. **改品牌素材要同步改坐标常量**
   `web-client/src/components/brand/OmiPerch.tsx` 里的眼睛坐标、`viewBox` 尺寸、`build_brand_assets.py` 的猫头裁切比例，都是对当前 PNG 像素级实测得来的。换素材后必须重新测量，否则眼神跟随、眨眼、图标裁切都会错位。素材加工流程见 `web-client/scripts/cutout.py` 的模块注释。

7. **`.env` 与 `.env.local` 不入库**
   换机器后这两个文件需要自己从 `.env.example` / `web-client/.env.example` 复制并填写。仓库里只有模板（值都是占位符）。

8. **数据集目录是中文名**
   `ecommerce_agent_dataset/` 下按 `1_美妆护肤` 这类中文品类分目录。脚本里路径不要写死英文名。
