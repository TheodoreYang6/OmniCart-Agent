# MODULES.md — 重要功能模块说明

> 每个模块写清三件事：**它负责什么**、**关键文件在哪**、**改它要注意什么**。
> 说明取自各模块的代码内注释与实际文件结构，不是推测。
>
> 上手流程见 [DEVELOPMENT.md](DEVELOPMENT.md)，产品与架构全景见 [README.md](README.md)。

---

## 目录

- [0. 分层总则](#0-分层总则)
- [1. framework/ 框架核心层](#1-framework-框架核心层)
- [2. providers/ 业务实现层](#2-providers-业务实现层)
- [3. agents/ 与 workflow/ Agent 与编排](#3-agents-与-workflow-agent-与编排)
- [4. model_gateway/ 模型网关](#4-model_gateway-模型网关)
- [5. retrieval/ 与 decision/ 检索与决策](#5-retrieval-与-decision-检索与决策)
- [6. verification/ 答文一致性守卫](#6-verification-答文一致性守卫)
- [7. context/ 与 prompts/ 上下文与提示词](#7-context-与-prompts-上下文与提示词)
- [8. core/ 基础设施](#8-core-基础设施)
- [9. 数据层：models / schemas / repositories / services](#9-数据层models--schemas--repositories--services)
- [10. observability/ 与 eval/ 可观测与评测](#10-observability-与-eval-可观测与评测)
- [11. web-client/ 前端](#11-web-client-前端)
- [12. android-client/ 安卓客户端](#12-android-client-安卓客户端)
- [13. scripts/ 与 alembic/ 脚本与迁移](#13-scripts-与-alembic-脚本与迁移)

---

## 0. 分层总则

```
api/          HTTP 边界，薄。只做参数校验与调用编排
   ↓
workflow/     LangGraph 主图，串联 5 个 Agent 的状态流转
   ↓
agents/       单个 Agent 的职责实现
   ↓
framework/    ★ 与业务无关的可复用能力（协议 + 编排 + 注册表）
   ↑          依赖方向单向，framework 不得 import providers
providers/    ★ 电商业务实现，通过 registry 注册进 framework
   ↓
services/ repositories/ models/    数据与业务服务
   ↓
core/         配置、数据库、缓存等基础设施
```

**这条分层由工具强制**：`importlinter.ini` 声明约束，`make governance`（`scripts/check_governance.py`）在提交前校验。`framework/` 里出现"商品""购物车"这类业务词就是设计错了。

---

## 1. framework/ 框架核心层

设计思路借鉴 amap-ai-agent 的 `libs/*`，但针对 OmniCart 单体架构做了简化（例如剔除运行时全包扫描，改为显式清单装配）。

### 1.1 registry.py — 组件注册表

- **职责**：轻量组件注册表 + 声明式 `@<kind>_component` 装饰器，统一装配入口。
- **关键取舍**：不做 `pkgutil.walk_packages` 运行时全包扫描（那是为 bazel/monorepo 多命名空间设计的重实现），改用**显式 `builtin()` 清单**，更简单可控。
- **改动注意**：新增组件必须进 `builtin()` 清单，否则运行时拿不到。

### 1.2 blackboard.py — 请求级 A2A 黑板

- **职责**：Artifact 存储 + asyncio 事件等待 + 订阅回调，实现 Agent 间共享上下文（Blackboard 架构 / orchestrator-workers 共享上下文模式）。
- **接口语义**：生产者 `publish` 主题化产物（topic == artifact_type）；消费者 `get` 非阻塞，`wait_for` 超时降级返回 `None`，**不阻塞主链**。
- **契约**：`schemas/a2a.py` 定义 Artifact。
- **改动注意**：黑板是**请求级**的，不要往里塞跨请求状态。

### 1.3 agent_manager.py — Agent 生命周期

- **职责**：在通用 `ComponentRegistry` 之上做 Agent 语义封装，按名注册/获取 + 批量 `init_all` / `shutdown_all`（Agent 实现了可选的 `init`/`shutdown` 协程才调用）。
- **存在意义**：替换 `workflow/graph.py` 里原先硬编码的模块级单例，改为"注册表装配 + 按名获取"。

### 1.4 retrieval/ — 检索框架层

6 阶段管线（`orchestrator.py`）：

| 阶段 | 做什么 |
|---|---|
| ① Query Rewrite | 可插拔 `QueryRewriter`，失败回退原 query |
| ② Activation Filter | 按 `should_activate` 筛选要激活的召回源 |
| ③ Parallel Fetch | 多源并行 + 双超时（每源 `latency_budget_ms` + 整体 `time_budget`） |
| ④ Fusion | `fusion.py` 融合多源结果 |
| ⑤ Rerank | `rerank.py` 重排 |
| ⑥ 结果整形 | `types.py` 统一契约 |

其他文件：`registry.py`（召回源注册）、`source.py`（源协议）、`errors.py`。

- **改动注意**：新召回源实现 `source.py` 的协议后注册进 `registry.py`，**不要**直接在 orchestrator 里加分支。超时预算是保障可用性的关键，不要为了"多召一点"随意放大。

### 1.5 memory/ — 记忆框架层

- `bank.py`：`MemoryBank` 统一入口。流程是「可选 rewrite → 多 Provider 并行召回（受整体 `time_budget` 约束）→ 汇总」，`default(builtin_providers=...)` 显式清单装配。
- `fusion.py` / `rerank.py`：多路记忆的融合与重排。
- `recall.py` / `paths.py` / `protocols.py`：召回逻辑、路径、协议。

### 1.6 tools/ — 工具框架与调度

`dispatcher.py` 是**双路调度**：

1. `RuleToolRouter`：关键词 → `(tool_name, args)`，0 LLM 延迟、MOCK 安全；
2. LLM 函数调用：OpenAI tools 协议，LLM 从**白名单**工具中选择并填参。`ENABLE_LLM_TOOL_CALLING` 关闭 / MOCK 模式 / 异常时降级到规则路由。

两路都未命中返回 `error="no_match"`，由调用方交回旧逻辑。

其他：`registry.py`（工具注册）、`providers.py`、`ordinal.py`（序数指代，如"第二个"）、`protocols.py`。

- **改动注意**：新增工具务必同时进白名单，否则 LLM 选不到；规则路由的关键词表要考虑误命中。

### 1.7 orchestration/ — 编排规划器（Plan-and-Execute）

`planner.py` 三层结构：

- `RulePlanner`：意图模板，0 延迟，覆盖 90%+ 单意图流量；
- `LLMPlanner`：复杂/多步 query 由 LLM 在**封闭能力词表**内编排计划；
- `PlanValidator`（`validator.py`）：硬校验 + 双层缓存（进程内 + Redis）。

其他：`plan.py`（计划结构）、`capabilities.py`（能力词表）。

- **改动注意**：能力词表是封闭的，LLM 只能在词表内编排；加能力要同步更新词表与 validator。

### 1.8 context/ — 上下文框架层

`manager.py`：多源并行采集（per-provider 超时 + 整体 `time_budget`）→ 格式化 + token 估算 → 按 `priority` 排序 → **token 预算贪心裁剪**（超预算丢弃低优先级切片）。

其他：`compaction.py`（压缩）、`token_estimator.py`、`protocols.py`。

- **改动注意**：新增上下文源要给合理的 `priority`，否则可能在裁剪时挤掉更重要的信息。

### 1.9 skills/ — 技能协议

目前仅 `protocols.py`，是预留的扩展点。

---

## 2. providers/ 业务实现层

把电商业务接进 framework 的地方。

| 目录 | 内容 | 说明 |
|---|---|---|
| `recall/` | `semantic_source.py` `keyword_source.py` `supplementary_source.py` `enrich_sources.py` `keyword_rewriter.py` `rerank_fusion.py` `evidence.py` | 语义/关键词/补充召回源、查询改写、融合重排、证据构造 |
| `memory/` | `preference_provider.py` `session_providers.py` `used_memories.py` | 偏好记忆、会话记忆、已用记忆去重 |
| `tools/` | `cart.py` `order.py` `shopping.py` `conversation.py` `preference.py` `mocks.py` | 购物车、订单、购物检索、会话、偏好工具；mocks 供 MOCK 模式使用 |
| `context/` | `context_providers.py` | 业务上下文提供者 |
| `agents/` `skills/` | 仅 `__init__.py` | 预留 |

- **改动注意**：这一层可以自由引用业务概念，但**不要把编排逻辑写进来**——编排属于 framework。

---

## 3. agents/ 与 workflow/ Agent 与编排

`workflow/graph.py` 是 LangGraph `StateGraph` 主图，5-Agent 购物决策编排：

```
START → Router → [Visual?] → Retrieval → [Reranker?] → Decision → Response → END
```

每个 Agent 是一个 node，状态在图里流转。

`agents/` 下的实现：

| 文件 | 职责 |
|---|---|
| `router_agent.py` | 意图路由，决定走哪条链路 |
| `retrieval_agent.py` | 召回商品 |
| `decision_agent.py` | 评分与决策 |
| `response_agent.py` | 生成回复 |
| `shop_action_agent.py` | 购物动作（加购/下单等） |
| `omni_agent.py` | 统一 Agent 入口 |

- **改动注意**：改图结构会影响所有链路，务必跑 `scripts/eval_agent_loop.py` 和单测。新增 Agent 走 `framework/agent_manager.py` 注册，不要加模块级单例。

---

## 4. model_gateway/ 模型网关

**能力名驱动**的模型访问层——业务代码只调用能力名，不写死模型名：

```python
gateway.get_model("visual_understanding")
gateway.chat("chat_generation", prompt="...")
```

| 文件 | 职责 |
|---|---|
| `gateway.py` | 网关入口，能力名 → 模型路由 |
| `model_config.yaml` | **唯一配置源**：哪个能力用哪个模型/后端 |
| `qwen_chat.py` / `qwen_embedding.py` | DashScope / OpenAI 兼容协议适配 |
| `providers/` | 各后端 provider 实现 |
| `local_backend.py` | 本地模型后端 |
| `resilience.py` | 重试、降级、熔断 |
| `mock_model.py` | MOCK 模式桩实现 |

- **改动注意**：换模型只改 `model_config.yaml`，不要动业务代码。Qwen3 系列必须设 `enable_thinking: false`（否则延迟明显变差）；Qwen 与 DeepSeek 统一走 OpenAI 兼容协议同一套适配器。

---

## 5. retrieval/ 与 decision/ 检索与决策

- `retrieval/sparse_encoder.py`：稀疏向量编码（BM25 类），统计数据在 `data/bm25_stats.json`。
- `retrieval/subcategory_alias.py`：子类目别名映射，缓解"自然语言 → 精准品类"的语义鸿沟。
- `decision/scoring.py`：评分公式与 7 维分解（`component_scores`），产出推荐等级与证据可信度。
- `decision/rules.py`：硬规则。

- **改动注意**：`scoring.py` 的权重直接决定推荐结果，改完必须跑 `scripts/eval_retrieval.py` 对比前后指标，不能只看单个 case。

---

## 6. verification/ 答文一致性守卫

防幻觉层：校验回复中的商品信息与检索到的证据是否一致，不一致则拦截或降级。

- **改动注意**：这是"答文一致性三道锁"之一，属于质量红线，改动前先确认清楚约束语义。

---

## 7. context/ 与 prompts/ 上下文与提示词

- `context/compiler.py`：上下文编译，把多源上下文拼装成模型输入。
- `prompts/`：**Prompt 集中管理**。项目约定 Prompt 不散落在业务代码里，全部收敛到这里。QU（Query Understanding）类 Prompt 遵循三段式重写规范。

- **改动注意**：改 Prompt 属于影响效果的改动，跑 `scripts/eval_qu.py` 看数字。

---

## 8. core/ 基础设施

| 文件 | 职责 |
|---|---|
| `config.py` | pydantic-settings 配置，三层加载（代码默认值 → YAML → `.env`） |
| `database.py` | 异步数据库引擎与会话 |
| `cache.py` | Redis 多级缓存（视觉/检索/改写/工作流，TTL 分别可配） |
| `display.py` | 展示层工具 |

- **改动注意**：加配置项要同时更新 `.env.example` 和 `.env.docker`，否则换机器的人不知道有这个开关。

---

## 9. 数据层：models / schemas / repositories / services

- `models/`：SQLAlchemy ORM，对应 PostgreSQL 表（商品、用户、购物车、订单、会话、偏好、地址）。
- `schemas/`：Pydantic 请求/响应契约，含 `product_chunk.py`（商品分块）、`a2a.py`（Agent 间产物契约）。
- `repositories/`：数据访问层，含 `order_repo.py` 等。
- `services/`：业务服务层，被 `api/` 调用。

- **改动注意**：改 ORM 必须配套 `alembic revision` 生成迁移；仓库层有同步/异步 API 混用的历史包袱，调用前确认签名。

---

## 10. observability/ 与 eval/ 可观测与评测

- `observability/request_context.py`：请求级上下文（trace 串联）。
- `observability/langfuse_exporter.py`：追踪导出到 Langfuse。
- `eval/rag_metrics.py`：RAG 评测指标实现（Faithfulness / Context Precision / Context Recall）。
- 追踪数据落在 `data/rag_traces.jsonl`，评测结果在 `data/rag_eval_runs/`。

---

## 11. web-client/ 前端

React 18 + Vite 5 + TypeScript + Tailwind + Zustand。

| 目录 | 内容 |
|---|---|
| `src/pages/` | 路由级页面：Chat / Shop / ProductDetail / Cart / Orders / Profile / Address / Preference / Login / BrandPreview |
| `src/components/brand/` | 品牌形象组件：`Omi.tsx`（SVG 吉祥物，9 种表情 + 相位动效）、`OmiPerch.tsx`（3D 主视觉 + SVG 可动部件混合） |
| `src/components/chat/` | 消息气泡、会话历史、Agent 洞察、思考轨迹 |
| `src/components/product/` | 商品卡、Spotlight |
| `src/store/` | Zustand 状态（auth / cart / toast） |
| `src/api/` | 接口封装与 TypeScript 类型 |
| `src/index.css` | 设计令牌 + 玻璃拟态组件样式 + 动效 keyframes |
| `public/brand/` | 3D 素材：`omi-perch.png`（640x568）、`omi-hero.png`、`omi-poses.png` |
| `scripts/` | 素材加工：`cutout.py`（绿幕抠图）、`build_brand_assets.py`（主视觉缩放 + 图标生成） |

**改动注意（踩过坑）**：

- `OmiPerch.tsx` 里的眼睛坐标、`viewBox` 尺寸都是对 `omi-perch.png` **像素级实测**得来的，与素材一一对应。换素材必须重新测量，否则眼神跟随/眨眼/星星眼全部错位。
- `build_brand_assets.py` 的猫头裁切比例同样是实测常量，随 `cutout.py` 的裁切框变化。
- 素材自带一条盘在身前的尾巴，**不要再叠 SVG 尾巴**（会变成两条）。
- `prefers-reduced-motion` 下所有动效必须降为静态，这是既有护栏，新增动效要跟上。
- 主题切换走 `document.documentElement` 的 `data-theme` 属性（`light`/`dark`），**不是** `class="dark"`。

---

## 12. android-client/ 安卓客户端

Kotlin + Jetpack Compose + Retrofit。功能与 Web 端对齐：登录、聊天、商品列表/详情、购物车、偏好、个人中心。

入口 `MainScreen.kt`，按 feature 分包（`feature/auth`、`feature/chat`、`feature/cart`、`feature/product`、`feature/shop`、`feature/profile`、`feature/preference`、`feature/demo`）。

APK 构建与 API 地址修改见 [DEPLOY.md](DEPLOY.md) 第六节。

---

## 13. scripts/ 与 alembic/ 脚本与迁移

**数据初始化**：`seed_postgresql.py` `seed_qdrant.py` `index_products.py` `index_product_chunks.py` `reindex_all.py` `clean_db.py`

**数据集加工**：`generate_1000_products.py` `enrich_dataset.py` `validate_dataset.py` `dataset_kb*.py` `apply_subcategory_images.py` `clean_brand_category.py`

**评测**：`eval_retrieval.py` `eval_qu.py` `eval_memory.py` `eval_agent_loop.py` `eval_subcategory_purity.py` `smoke_rag_eval.py` `rag_stats.py` `run_baseline.py`

**工程治理**：`check_governance.py`（分层与注册约束校验，`make governance`）、`gen_component_registry.py`（生成组件注册表文档，`make registry`）

**冒烟**：`smoke_recommend.py` `smoke_test_v2.py`

`alembic/versions/` 下迁移按序号命名（如 `011_add_product_derived_columns.py`），新增迁移用 `alembic revision -m "描述"` 生成后手工核对。

- **改动注意**：脚本大多需要 `PYTHONPATH=backend` 才能 import `app.*`。
