# OmniCart Agent 完整蓝图

版本：v6.0 | 日期：2026-06-09 | 状态：参赛交付版

OmniCart Agent 是基于 RAG 的多模态电商智能导购 AI Agent，参加字节跳动 Agent 挑战赛。系统以 5 个协作 Agent 为核心，通过 LangGraph 工作流编排，实现从意图理解到证据绑定推荐的全链路闭环。Android 原生客户端提供商品展示、豆仔智能、购物车、个人中心四个主页面。

---

## 目录

1. [项目定位](#1-项目定位)
2. [系统架构](#2-系统架构)
3. [Agent 协同设计](#3-agent-协同设计)
4. [RAG 全链路](#4-rag-全链路)
5. [记忆系统](#5-记忆系统)
6. [评分体系](#6-评分体系)
7. [Android 客户端](#7-android-客户端)
8. [API 设计](#8-api-设计)
9. [数据库设计](#9-数据库设计)
10. [性能优化](#10-性能优化)
11. [安全与验证](#11-安全与验证)
12. [评测体系](#12-评测体系)
13. [部署与配置](#13-部署与配置)

---

## 1. 项目定位

OmniCart Agent 不是普通的电商客服机器人，而是面向"购买前决策"的智能导购系统。它帮助用户完成：商品识别 → 需求理解 → 多维检索 → 商品对比 → 风险总结 → 可解释推荐。

核心问题：

```
这个商品适不适合我？为什么适合？有哪些风险？
有没有更好的替代品？这些判断依据来自哪些证据？
```

### 四页面架构

| 页面 | 定位 | 核心能力 |
|------|------|---------|
| 商品展示 | 商品浏览 | 分类筛选、商品详情、加入购物车、问豆仔 |
| 豆仔智能 | AI 核心 | 文字/图片/语音导购、RAG 检索、决策评分、受控加购 |
| 购物车 | 交易管理 | 增删改查、数量管理、模拟结算 |
| 个人中心 | 用户管理 | 登录注册、收货地址、购物偏好、订单查询 |

豆仔智能通过受控 action 操作购物车（调用后端 service，不直接写数据库）。付款仅做 mock checkout，不接入真实支付。

---

## 2. 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                  Android Client (Kotlin)                  │
│  MVVM + Compose + Material3 + Retrofit + SSE             │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP + SSE
┌────────────────────────▼─────────────────────────────────┐
│                  FastAPI Backend (:8006)                   │
│                                                           │
│  ┌──────────────────────────────────────────────────┐    │
│  │              LangGraph Workflow                    │    │
│  │                                                    │    │
│  │  Router → [Visual] → Retrieval → Reranker         │    │
│  │     → EvidenceCheck → Decision → Response → Guard  │    │
│  └──────────────────────────────────────────────────┘    │
│                                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │  Model   │ │ Services │ │  Repos   │ │   API    │   │
│  │ Gateway  │ │(会话/偏好)│ │(PG/内存) │ │(REST/SSE)│   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└────────────────────────┬─────────────────────────────────┘
                         │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
┌───▼────┐  ┌───────────▼──┐  ┌─────────────▼──┐
│ Qdrant │  │  PostgreSQL  │  │     Redis       │
│ ANN检索│  │  OLTP + JSONB│  │  4级缓存/降级   │
└────────┘  └──────────────┘  └─────────────────┘
```

### 技术栈

| 层 | 技术 | 版本/说明 |
|----|------|---------|
| 客户端 | Kotlin + Jetpack Compose + Material 3 | Android 原生, MVVM |
| 网络 | Retrofit + OkHttp + Coroutines | REST + SSE 流式 |
| 后端 | Python 3.11 + FastAPI | 异步 Web 框架 |
| 工作流 | LangGraph | StateGraph 编排 |
| AI | 通义千问 | qwen-turbo/VL-max/reranker/embedding-v4 |
| 向量库 | Qdrant | ANN, 1024维, 本地降级 |
| 数据库 | PostgreSQL | asyncpg + SQLAlchemy 2.0 |
| 缓存 | Redis | 视觉/搜索/改写/工作流 4级 |

---

## 3. Agent 协同设计

### Agent 总览

| Agent | 模型 | 职责 | 关键输出 |
|-------|------|------|---------|
| Router | qwen-turbo + 规则 | 意图识别、约束提取、检索计划 | intent/category/budget/scenario |
| Visual | qwen-vl-max | 图像解析、品类映射、DB匹配 | product_name/brand/visual_matched_pids |
| Retrieval | embedding-v4 + reranker | 语义检索、精排、证据补充 | retrieved_products/evidence_list |
| Decision | 规则公式 | 7维评分、避雷过滤、推荐等级 | decision_results |
| Response | qwen-turbo + 模板 | 上下文编译、LLM生成、模板兜底 | answer |

### Workflow 流程

```
START → Router → [Visual?] → Retrieval → Reranker
  → EvidenceCheck → Decision → Response → Guard → END

条件分支:
- intent=chitchat → 跳过检索,直通 Response
- 有图片 → Router ∥ Visual 并行
- 无商品 → EvidenceCheck → Response (跳过 Decision)
- 快速模式 → 跳过 Router LLM + Reranker + Response LLM
```

### 关键设计

- **非开放式 ReAct**: 严格按 Workflow 编排，Agent 不自由决策下一步
- **失败降级**: 每个节点独立降级（LLM失败→规则兜底, Embedding失败→关键词）
- **证据绑定**: 所有推荐必须绑定 evidence_ids
- **并行优化**: Router∥Visual, 三通道证据并行, FollowUp∥Profile

---

## 4. RAG 全链路

### 流水线

```
Query → Embedding(1024d) → Qdrant ANN(top_k*3)
  → 品类/价格过滤
  → must_tags 硬匹配(顶部插入)
  → exclude_tags 硬过滤(直接移除)
  → visual_matched 置顶(0.99)
  → Qwen3-Reranker 精排(0.68+0.38*score)
  → 证据补充(3通道并行: review/policy/text)
  → Context Compiler → Response
```

### 数据规模

- 105 件商品, 4 品类(数码电子/美妆护肤/服饰运动/食品饮料), 42 子类
- Qdrant 1024 维向量, 余弦相似度
- 每件商品含: 标题/品牌/价格/描述/FAQ/用户评价/SKU

### 降级策略

```
Qdrant 不可用 → 本地余弦相似度
Embedding API 失败 → jieba 关键词子串匹配
Reranker 异常 → 保持检索原始排序
Redis 不可用 → 直接计算(无缓存)
```

### 评测

10 条 Golden Queries + Hit@K/MRR/Recall/NDCG + Eval Dashboard (Chart.js)

---

## 5. 记忆系统

三层架构：

| 层 | 存储 | 用途 |
|----|------|------|
| 短期 | context_snapshot (PG JSONB) | 约束继承、指代消解、pending_question |
| 长期 | user_preference_entries (PG) | 条目化偏好、品类感知注入 |
| 会话 | conversations + messages (PG) | 对话历史、消息持久化、会话恢复 |

核心组件：

- **ConversationService**: context_snapshot 读写 + 内存缓存(5min TTL)
- **FollowUpEngine**: 7 种追问模式检测(序数指代/品牌引用/预算更新/购物车意图等)
- **UserProfileService**: 条目化偏好 + Qwen 解析 + 品类感知注入(search_hints/context_prompt 分离)
- **ContextCompressor**: qwen-turbo 增量摘要, 异步后台执行

---

## 6. 评分体系

### 评分公式 (V4)

```
raw = 0.45 × relevance         (RAG语义相关度)
    + 0.20 × budget_fit        (价格适配度)
    + 0.12 × user_sat          (用户口碑,贝叶斯校正)
    + 0.10 × value_score       (性价比,子品类基准)
    + 0.08 × spec_quality      (规格技术信号)
    + 0.05 × scenario_fit      (场景关键词命中)
    + preference_bonus         (偏好加成, ≤0.10)
    - risk_penalty             (差评扣分, ≤0.20)
    - avoid_penalty            (避雷扣分, ≤0.10)
```

### 推荐等级

| 等级 | 条件 |
|------|------|
| strong_recommend | ≥0.80 + evidence≥0.50 + risk<0.10 |
| recommended | ≥0.65 |
| cautious | ≥0.55 或 risk≥0.20 |
| insufficient_evidence | evidence<0.25 |
| not_recommended | 硬约束失败 |

### 避雷机制

- **检索层硬过滤**: exclude_tags 匹配的商品直接从 retrieved_products 移除
- **品牌别名展开**: 60+品牌中英双向映射, "不要Nike"自动展开["Nike","耐克"]
- **语言识别**: 4条严格正则 + 噪音词过滤 + "除了X还有什么"不误判

---

## 7. Android 客户端

### 架构

```
MVVM: ViewModel + StateFlow
网络: Retrofit + OkHttp + Coroutines
图片: Coil (SubcomposeAsyncImage)
SSE: AgentStreamClient (OkHttp + callbackFlow)
```

### 四 Tab

| Tab | 路由 | 核心组件 |
|-----|------|---------|
| 商品展示 | shop | ProductListScreen + ProductCard + ProductDetailScreen |
| 豆仔智能 | chat | ChatScreen + MessageBubble + ProductCard + VoiceInput |
| 购物车 | cart | CartScreen + CartViewModel |
| 个人中心 | profile | ProfileScreen → 订单/地址/偏好/关于 |

### 豆仔智能核心功能

- SSE 流式打字机效果
- 商品卡片嵌入对话流 (可点击进入详情/问豆仔/加购)
- 拍照识图 (PhotoPicker + 上传 + Visual Agent)
- 语音导购 (长按录音 → ASR → 推荐 → TTS 朗读)
- 快速模式开关 (⚡ Switch, 跳过 LLM 模板秒回)
- 购物操作 (对话加购/购物车管理/下单确认)
- Agent 洞察面板 (11 Tab: 上下文/检索计划/证据/评分/追踪等)
- 会话历史 (ConversationListSheet, 加载/切换/删除)

### 其他功能

- 商品浏览: 分类筛选 + 详情页 + 问豆仔跳转
- 购物车: 增删改查 + 数量管理 + 全选 + 模拟结算
- 收货地址: 列表/新增/编辑/删除/设默认 + 下单时选择模式
- 购物偏好: 自然语言输入 → Qwen 解析 → 预览 → 条目管理
- 订单: 订单列表 + 商品明细 + 状态展示
- 登录注册: 用户名/密码 + Token 持久化

---

## 8. API 设计

### REST 端点 (30+)

| 类别 | 端点 | 方法 |
|------|------|------|
| 健康 | `/api/health` | GET |
| 推荐 | `/api/recommend`, `/api/recommend/v2` | POST |
| 流式 | `/api/recommend/stream` | POST (SSE) |
| 引导 | `/api/recommend/guide` | POST |
| 商品 | `/api/products`, `/api/products/{id}` | GET |
| 购物车 | `/api/cart`, `/api/cart/items`, `/api/cart/select-all` | GET/POST/PUT/DELETE |
| 结算 | `/api/checkout` | POST |
| 订单 | `/api/orders` | GET |
| 地址 | `/api/addresses` | GET/POST/PUT/DELETE |
| 偏好 | `/api/preferences/entries`, `/api/preferences/parse` | GET/POST/PUT/DELETE |
| 会话 | `/api/conversations`, `/api/conversations/{id}/messages` | GET/DELETE |
| 上传 | `/api/upload` | POST (multipart) |
| 语音 | `/api/voice/transcribe`, `/api/voice/tts` | POST |
| 认证 | `/api/auth/login`, `/api/auth/register`, `/api/auth/profile` | POST/GET |
| 评测 | `/api/eval/run`, `/api/eval/results` | POST/GET |
| 可观测 | `/api/observability/traces`, `/api/observability/stats` | GET/DELETE |

### SSE 协议

```
event: token    → {"text": "我"}          # 逐字流式
event: token    → {"text": "为"}          # ...
event: result   → {完整 RecommendResponse}  # 结构化结果
event: done     → {"finish_reason": "stop"} # 结束
```

---

## 9. 数据库设计

### 核心表

| 表 | 引擎 | 用途 |
|----|------|------|
| products | Qdrant + PG | 商品元信息 |
| cart_items | PG | 购物车 |
| orders | PG | 订单 (模拟) |
| addresses | PG | 收货地址 |
| users | PG/内存 | 用户认证 |
| conversations | PG | 会话 (含 context_snapshot JSONB) |
| conversation_messages | PG | 消息 |
| user_preference_entries | PG | 偏好条目 |
| context_snapshots | PG | 会话上下文 (已合并到 conversations) |

### Repository 模式

所有数据访问通过 Repository 抽象层，支持 PG 和内存双实现 (`USE_POSTGRES` 切换)。

---

## 10. 性能优化

| 优化 | 方式 | 效果 |
|------|------|------|
| 模型切换 | qwen-plus → qwen-turbo | 4s → 1s |
| Prompt 压缩 | Router 1200t→740t, Response 250t→130t | 省 600t/请求 |
| 快速模式 | 跳过 Router LLM + Reranker + Response LLM | 4-8s → ~1s |
| Router∥Visual | 有图片时 asyncio.create_task 并行 | 省 1-3s |
| 品类预填跳过 | 追问时 category+sub_category 已确定, 跳过 Router LLM | 省 1s |
| 证据并行 | review/policy/text 3通道 ThreadPoolExecutor | 总延迟=max而非sum |
| Redis 缓存 | 视觉(1h)/搜索(5min)/改写(30min)/工作流(5min) | 命中时省 0.5-2s |
| 关键词免 LLM | Router 有 category 时跳过 LLM 关键词提取 | 省 0.5s |
| 上下文压缩 | qwen-turbo 异步增量摘要 | 不阻塞响应 |

---

## 11. 安全与验证

### Response Guard — 5 项检查

| 检查 | 逻辑 | 硬失败 |
|------|------|--------|
| evidence_bound | 品牌/标题关键词命中 | 否 |
| price_accurate | 品牌+滑窗匹配 → 价格验证 | 否 |
| risk_warned | 风险关键词提取 → 回答包含 | 否 |
| honest_on_empty | 无商品时无误导词 | **是** |
| hallucination | 品牌不在检索结果 + 不在用户提及 + 非否定语境 | **是** |

### 上传安全

- 图片魔数校验 (JPEG/PNG/GIF/WebP 文件头)
- Content-Type 白名单
- 10MB 大小限制
- 唯一文件名生成

### 数据隔离

- 购物车/地址/偏好/订单全部绑定 user_id
- Android API 调用统一传入 AuthManager.effectiveUserId
- 后端空 user_id 兜底 DEMO_USER_ID

---

## 12. 评测体系

### Golden Queries

10 条评测查询覆盖 4 品类 × 多种查询类型 (模糊推荐/条件筛选/场景化/反选排除/多模态)

### 指标

Hit@K, MRR, Recall@K, Precision@K, NDCG@10

### 基础设施

- `observability/rag_logger.py`: 全链路数据记录
- `data/eval_queries.json`: Golden Query 定义
- `scripts/rag_stats.py`: 统计脚本 (Hit@K/MRR/Recall)
- `api/eval_dashboard.py`: Web 可视化面板 (Chart.js)

---

## 13. 部署与配置

### 依赖

```
Python 3.11+ | PostgreSQL 14+ | Qdrant | Redis (可选)
```

### 环境变量

```bash
OMNICART_PORT=8006
OMNICART_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/omnicart
USE_POSTGRES=true
QWEN_API_KEY=your-key
USE_REDIS=true
REDIS_URL=redis://localhost:6379
OMNICART_MOCK_MODE=false
OMNICART_FAST_MODE=false
```

### 模型配置

```yaml
capabilities:
  intent_understanding:  qwen-turbo
  chat_generation:       qwen-turbo
  visual_understanding:  qwen-vl-max
  text_embedding:        text-embedding-v4
  text_reranking:        qwen3-rerank
  context_compression:   qwen-turbo
```

### 快速启动

```bash
pip install -r requirements.txt
python scripts/seed_postgresql.py
python scripts/seed_qdrant.py
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8006
```

### 相关文档

| 文档 | 说明 |
|------|------|
| `AGENT_COLLABORATION.md` | Agent 协同详细设计 |
| `RAG_PIPELINE.md` | RAG 全链路技术文档 |
| `MEMORY_SYSTEM.md` | 记忆系统设计 |
| `SCORING_SYSTEM_COMPLETE_REFERENCE.md` | 评分体系参考 |
| `DATABASE_DESIGN.md` | 数据库设计 |
| `答辩QA手册.md` | 答辩问答准备 |
