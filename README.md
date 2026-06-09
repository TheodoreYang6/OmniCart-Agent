# OmniCart Agent

**基于 RAG 的多模态电商智能导购 AI Agent** — 字节跳动 Agent 挑战赛参赛项目。

将传统"展示型广告"升级为"交互型导购"，实现从内容浏览到购买决策的深度连接。支持文字、图片、语音三种输入模态，通过 5 个协作 Agent 完成意图理解→视觉识别→多维检索→决策评分→证据绑定回答的全链路闭环。

---

## 目录

- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [目录结构](#目录结构)
- [配置说明](#配置说明)
- [快速启动](#快速启动)
- [核心功能](#核心功能)
- [Agent 协同](#agent-协同)
- [RAG 全链路](#rag-全链路)
- [记忆系统](#记忆系统)
- [关键问题与解决方案](#关键问题与解决方案)
- [文档索引](#文档索引)

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Android Native Client                     │
│  Kotlin + Jetpack Compose + Material 3 + MVVM               │
│  四 Tab: 商品展示 │ 豆仔智能 │ 购物车 │ 个人中心              │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP + SSE (Retrofit/OkHttp)
┌──────────────────────────▼──────────────────────────────────┐
│                    FastAPI Backend (:8006)                    │
│                                                              │
│  ┌────────┐  ┌────────┐  ┌──────────┐  ┌────────┐  ┌──────┐ │
│  │ Router │→│ Visual │→│ Retrieval │→│Decision│→│Resp..│ │
│  │ Agent  │  │ Agent  │  │  Agent    │  │ Agent  │  │Agent │ │
│  └────────┘  └────────┘  └──────────┘  └────────┘  └──────┘ │
│                                                              │
│              LangGraph StateGraph (Workflow)                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
┌───▼────┐  ┌─────────────▼──┐  ┌───────────────▼──┐
│ Qdrant │  │  PostgreSQL    │  │     Redis        │
│向量检索 │  │ 商品/购物车/会话│  │  四级缓存/降级    │
└────────┘  └────────────────┘  └──────────────────┘
```

**Workflow 流程：**

```
START → Router → [Visual?] → Retrieval → Reranker → EvidenceCheck → Decision → Response → Guard → END
            ↘ (chitchat) ──────────────────────────────────────────→ Response
                         ↘ (有图片时 Router ∥ Visual 并行)
```

---

## 技术栈

| 层次 | 技术 | 说明 |
|------|------|------|
| **客户端** | Kotlin + Jetpack Compose + Material 3 | Android 原生，MVVM 架构 |
| **网络** | Retrofit + OkHttp + Coroutines | HTTP REST + SSE 流式 |
| **图片** | Coil | 异步图片加载 |
| **后端** | Python 3.11 + FastAPI | 异步 Web 框架 |
| **AI 模型** | 通义千问 (Qwen) | qwen-turbo(意图/生成), qwen-vl-max(视觉), qwen3-rerank(精排), text-embedding-v4(向量化) |
| **工作流** | LangGraph | StateGraph 有向图编排 5 Agent |
| **向量库** | Qdrant | ANN 语义检索 + 本地降级 |
| **数据库** | PostgreSQL (asyncpg + SQLAlchemy) | 商品、购物车、订单、会话、偏好 |
| **缓存** | Redis | 视觉(1h)/搜索(5min)/改写(30min)/工作流(5min) 四级缓存, 优雅降级 |
| **语音** | Qwen-Omni | ASR 语音转文字 + TTS 文字转语音 |
| **分词** | jieba | 中文关键词提取 |

---

## 目录结构

```
OmniCart-Agent/
├── android-client/              # Android 原生客户端
│   └── app/src/main/java/com/omnicart/agent/
│       ├── core/                # 配置/网络/模型/主题
│       ├── feature/             # 各功能模块
│       │   ├── chat/            # 豆仔智能对话 (SSE流式/语音/图片)
│       │   ├── product/         # 商品卡片/详情/图片
│       │   ├── cart/            # 购物车 CRUD
│       │   ├── order/           # 订单列表
│       │   ├── address/         # 收货地址管理
│       │   ├── preference/      # 购物偏好设置
│       │   ├── profile/         # 个人中心
│       │   ├── shop/            # 商品浏览(分类筛选)
│       │   ├── panel/           # Agent 洞察面板
│       │   ├── auth/            # 登录注册
│       │   └── demo/            # 演示场景/快捷菜单
│       └── MainActivity.kt
│
├── backend/                     # FastAPI 后端
│   └── app/
│       ├── agents/              # 5 Agent (Router/Visual/Retrieval/Decision/Response)
│       ├── api/                 # REST API (15 端点)
│       ├── services/            # 业务服务 (会话/偏好/追问/压缩)
│       ├── repositories/        # 数据仓库 (PG + 内存双实现)
│       ├── models/              # SQLAlchemy ORM
│       ├── schemas/             # Pydantic 数据模型
│       ├── retrieval/           # 检索 (语义/分块/LLM评估)
│       ├── verification/        # 回答守门 + 证据检查
│       ├── vision/              # 视觉解析 (Qwen-VL)
│       ├── decision/            # 评分公式 + 共享规则 + 证据指标
│       ├── context/             # 上下文编译器
│       ├── workflow/            # LangGraph 工作流编排
│       ├── model_gateway/       # 模型统一网关 (7能力)
│       ├── core/                # 配置/缓存/数据库/Redis/Qdrant
│       ├── observability/       # LLM 全链路追踪+统计
│       └── main.py              # 应用入口
│
├── ecommerce_agent_dataset/     # 商品数据集 (105件/4品类/42子类)
├── docs/                        # 项目文档
├── data/                        # 评测数据/Golden Queries
├── scripts/                     # 工具脚本 (播种/评测/清理)
├── tests/                       # 测试 (70单元+21集成)
├── requirements.txt             # Python 依赖
└── README.md
```

---

## 配置说明

### 环境变量 (.env)

```bash
OMNICART_PORT=8006
OMNICART_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/omnicart
USE_POSTGRES=true
QWEN_API_KEY=your-dashscope-api-key
USE_REDIS=true
REDIS_URL=redis://localhost:6379
OMNICART_MOCK_MODE=false
OMNICART_FAST_MODE=false
```

### 模型配置 (model_config.yaml)

```yaml
capabilities:
  intent_understanding:  qwen-turbo
  chat_generation:       qwen-turbo
  visual_understanding:  qwen-vl-max
  text_embedding:        text-embedding-v4
  text_reranking:        qwen3-rerank
  context_compression:   qwen-turbo
```

### Android 配置 (AppConfig.kt)

```kotlin
object AppConfig {
    const val BASE_URL = "http://192.168.1.101:8006/"
    const val TIMEOUT_SECONDS = 30L
}
```

---

## 快速启动

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python scripts/seed_postgresql.py
python scripts/seed_qdrant.py
```

### 3. 启动后端

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8006
```

### 4. 构建 Android

```bash
cd android-client
./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

### 5. 验证

```bash
curl http://localhost:8006/api/health
python scripts/smoke_recommend.py
```

---

## 核心功能

| 功能 | 说明 | 状态 |
|------|------|------|
| 文字导购 | 自然语言输入→RAG检索→推荐回复 | ✅ |
| 流式输出 | SSE 逐字打字机效果 | ✅ |
| 拍照识图 | 拍照→Qwen-VL解析→同类商品检索 | ✅ |
| 语音导购 | 长按录音→ASR→推荐→TTS朗读 | ✅ |
| 多轮对话 | 追问/指代/品类继承/上下文管理 | ✅ |
| 商品对比 | 多商品并行检索+维度对比 | ✅ |
| 购物车 | 对话加购/自然语言管理/模拟结算 | ✅ |
| 下单流程 | 地址确认→订单汇总→模拟下单→持久化 | ✅ |
| 偏好记忆 | 条目化偏好+品类感知注入+Android管理 | ✅ |
| 快速模式 | 跳过LLM的模板回答(⚡开关) | ✅ |
| 幻觉检测 | 品牌验证+证据绑定+价格准确+风险覆盖 | ✅ |
| 评测仪表盘 | 10 Golden Query+可视化趋势 | ✅ |

---

## Agent 协同

> 详见 [AGENT_COLLABORATION.md](docs/AGENT_COLLABORATION.md)

5 个 Agent 通过 LangGraph StateGraph 编排：

| Agent | 模型 | 职责 |
|-------|------|------|
| Router | qwen-turbo + 规则 | 意图识别、品类/预算/场景约束提取、检索计划 |
| Visual | qwen-vl-max | 图像解析、品类映射、DB 精确匹配 |
| Retrieval | text-embedding-v4 + qwen3-rerank | 语义检索、精排、证据补充(三通道并行) |
| Decision | 规则公式 | 7维加权评分、避雷过滤、推荐等级判定 |
| Response | qwen-turbo + 模板 | 上下文编译、LLM生成、模板兜底 |

性能优化：Router+Visual(有图)并行、品类预填时跳过Router LLM、快速模式跳过全部LLM。

---

## RAG 全链路

> 详见 [RAG_PIPELINE.md](docs/RAG_PIPELINE.md)

```
Query → Embedding(1024d) → Qdrant ANN → 品类/价格过滤
  → Qwen3-Reranker精排(0.68+0.38*score) → 视觉置顶(0.99)
  → 避雷硬过滤 → 证据补充(3通道并行) → Context Compiler → Response
```

- 向量库: Qdrant, 1024维, 210商品, 余弦相似度
- 证据: review/policy/FAQ 三通道并行检索
- 评测: Hit@K, MRR, Recall, NDCG, 10 Golden Queries
- 缓存: Redis 4级, 优雅降级到本地

---

## 记忆系统

> 详见 [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)

三层记忆架构：

| 层次 | 存储 | 内容 |
|------|------|------|
| 短期 | context_snapshot (PG JSONB) | 约束/上轮对话/pending_question |
| 长期 | user_preference_entries (PG) | 品类+品牌+场景+避雷标签 |
| 会话 | conversations + messages (PG) | 对话历史+消息持久化 |

- FollowUpEngine: 7种追问模式检测
- 品类感知注入: 检测query品类→仅注入匹配条目
- 上下文压缩: qwen-turbo增量摘要
- Android PreferenceScreen: 自然语言输入→解析→保存

---

## 关键问题与解决方案

### LLM 延迟优化

Router(4s+) → 切换qwen-turbo(~1s) + Prompt压缩(1200t→740t) + 品类预填跳过LLM + 快速模式(模板秒回)

### 拍照识图品类偏差

Visual prompt 只列美妆类别 → 对齐数据集全品类(210商品/4品类/42子类) + 不在库内设低confidence

### 品类约束泄漏

上轮"T恤"锁死后续搜索 → 当前query不含子品类关键词时不继承

### 肯定回复链路断裂

"要"→搜索无结果 → pending_question检测+肯定词→query自动替换为问题内容

### 品牌中英文不对齐

"不要Nike"无法匹配"耐克" → BRAND_ALIASES 60+品牌中英双向映射

### 地址 user_id 绑定

Android端缺userId→地址存为空 → 全部API传入AuthManager.effectiveUserId

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [README.md](README.md) | 项目总览 |
| [AGENT_COLLABORATION.md](docs/AGENT_COLLABORATION.md) | 5 Agent 协同设计 |
| [RAG_PIPELINE.md](docs/RAG_PIPELINE.md) | RAG 全链路 |
| [MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md) | 记忆系统 |
| [OMNICART_AGENT_COMPLETE_BLUEPRINT.md](docs/OMNICART_AGENT_COMPLETE_BLUEPRINT.md) | 完整蓝图 |
| [SCORING_SYSTEM_COMPLETE_REFERENCE.md](docs/SCORING_SYSTEM_COMPLETE_REFERENCE.md) | 评分体系 |
| [DATABASE_DESIGN.md](docs/DATABASE_DESIGN.md) | 数据库设计 |
| [答辩QA手册.md](docs/答辩QA手册.md) | 答辩问答 |
| [DEVELOPMENT_RULES.md](docs/DEVELOPMENT_RULES.md) | 开发规范 |
| [CHANGELOG.md](docs/CHANGELOG.md) | 变更日志 |
