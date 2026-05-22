# OmniCart Agent 答辩 QA 手册

> 适用：字节跳动 Agent 挑战赛答辩 / 技术面试 / 项目汇报
> 更新：2026-05-22（基于 V1 全部完成架构 — P0+P1+P2+V1-Plus = 50/51 项）

---

## 一句话定位

> OmniCart Agent 是一个面向购买前决策的 Android 原生多模态购物决策 Agent，融合 Qwen 全栈模型、LLM 查询改写 + Qdrant 语义向量 + jieba 关键词 RRF 混合检索、LangGraph 8 节点 Multi-Agent 编排、PostgreSQL 6 表持久化、7 维可解释决策评分、Skill Registry + MCP-compatible ToolManager、State Checkpoint、Decision Harness 验证框架、闲聊模式 + 完整用户体系 + Android 四 Tab 原生客户端 + V1-Plus Agent 洞察面板。

---

## 一、系统架构全景

```
Android App (Kotlin/Compose/MVVM) — 四个 Tab + 10 个子页面
    │ Retrofit + OkHttp + Auth Bearer Token 拦截器
    ▼
FastAPI Backend (Python 3.11) — 26 个 API 端点
    │
    ├─ POST /api/recommend/v2 ──→ LangGraph 8 节点 Workflow
    │   Router → Visual(Qwen-VL) → Retrieval(LLM改写+三通道并行) → Reranker
    │       → EvidenceCheck → Decision → Response(Qwen) → Guard → Harness
    │
    ├─ /api/auth/*       ──→ PgUserRepository (PBKDF2 100k + Bearer Token)
    ├─ /api/addresses/*  ──→ PgAddressRepository (省/市/区/详细 + is_default互斥)
    ├─ /api/preferences  ──→ PreferenceMemory + PgPreferenceRepository
    ├─ /api/products     ──→ PgProductRepository (100件商品 JSONB)
    ├─ /api/cart/*       ──→ PgCartRepository (购物车商品快照)
    ├─ /api/checkout     ──→ Mock 结算（不接入真实支付）
    ├─ /api/agent/action ──→ 豆仔加购（受控操作 + ToolCallRecord）
    └─ /api/upload       ──→ 图片上传 + Qwen-VL 解析

基础设施层:
    ├─ Skill Registry: 8 Skill（视觉/检索/评论/政策/兼容性/评分/验证/Demo）
    ├─ ToolManager: 8 Tool + Manifest + 权限控制 + V1 只读强制
    ├─ State Checkpoint: JSON 文件 8 节点持久化 (resume/replay/export)
    ├─ Decision Harness: 7 项统一校验框架
    ├─ Evidence Graph Lite: NetworkX 商品-证据-风险图
    ├─ A2A-lite Dispatcher: AgentMessage/Artifact 同进程分发
    ├─ CategoryIndex: 品类→子品类→品牌→商品 4 级分层 + 250+关键词映射
    ├─ Multimodal Fallback: L0 Qwen-VL → L1 Mock → L2 纯文本 3 级降级
    ├─ Counterfactual Recommender: 0 结果时智能反事实建议
    ├─ Visual Grounding: 字段级视觉证据绑定 (evidence_id 可追溯)
    └─ LLM Query Rewrite: Qwen 口语→搜索关键词 + jieba 单字兜底
```

---

## 二、Multi-Agent 编排（创新点必问）

### Q: 8 个节点做什么？

| # | 节点 | 功能 | 关键技术 |
|---|------|------|---------|
| 1 | Router Agent | 意图识别(6种含闲聊) + 约束抽取 + 检索计划 | 规则优先 LLM + 250+关键词 + 16个闲聊检测 + 话题切换 |
| 2 | Visual Agent | Qwen-VL 商品截图解析 | 3 级降级(L0真实→L1 Mock→L2纯文本) + Visual Grounding |
| 3 | Retrieval Agent | 三通道并行检索 | **LLM查询改写**(口语→搜索词) + Qdrant 1024d ANN + jieba RRF k=60 |
| 4 | Reranker | Qwen3-Rerank 语义精排 | 失败保持原序，不阻塞链路 |
| 5 | Evidence Checker | 按意图类型检查证据充足性 | 5 种意图×最少证据类型矩阵 |
| 6 | Decision Agent | 硬约束过滤 + 7维加权评分 + 风险标签 | 预算×2/品类不匹配直接排除 |
| 7 | Response Agent | LLM 回答 + 闲聊/购物双模式 | Context Compiler + 6类闲聊模板兜底 |
| 8 | Response Guard | 5 项守门验证 | evidence_bound/price_accurate/risk_warned/honest/无依据 |

### Q: Agent 间怎么通信？

LangGraph WorkflowState 全局状态 + A2A-lite Dispatcher（AgentMessage/Artifact）。V2 可升级为标准 A2A Protocol。

### Q: 闲聊怎么处理？

Router 检测 16 个闲聊关键词 → intent=chitchat → **跳过全部检索/评分链**，直接 Response Agent 用独立 Prompt 生成友好文字回复。6 类模板兜底（打招呼/自我介绍/能力说明/感谢/告别/其他）。

### Q: Router Agent 为什么规则优先于 LLM？

**实测发现** Qwen 有时将"买食品"误判为"美妆护肤"、"买鞋"遗漏。合并策略 `{**llm_result, **rule_result}` 确保规则覆盖 LLM，品类/预算/意图以规则为准。

---

## 三、LLM 查询改写（新增核心创新）

### Q: 怎么解决口语查询检索不准？

**两阶段增强**：
1. **LLM 改写**：Qwen LLM 把"我想买鞋"→"运动鞋 跑步鞋 休闲鞋 鞋"→ 直接命中所有鞋类子品类，score 从 0 飙升到 50-65
2. **单字拆分兜底**：LLM 不可用时，jieba 分词后多字词拆单字（"买鞋"→["买","鞋"]），单字"鞋"命中子品类 +3.0 分

**效果对比**：
```
修改前：查询"我想买鞋" → 所有产品 score=0 → 返回护肤品（默认顺序）
修改后：查询"我想买鞋" → 9款鞋 score=3.0-65.0 → Top5全是鞋 ✅
```

### Q: 为什么不能只用 jieba？

jieba 把"我想买鞋"切为"买鞋"（一个词），任何产品都不含"买鞋"，score 全 0。手工维护 250+ 关键词永远有边界 case。LLM 理解"我想买鞋"=要买鞋零成本。

---

## 四、数据库架构

### Q: PostgreSQL + Qdrant 双库设计

| 数据库 | 用途 | 技术亮点 |
|--------|------|---------|
| PostgreSQL 18 | 6 张表（products/users/addresses/cart_items/user_preferences/checkpoints） | JSONB 嵌套数据 + asyncpg + Alembic |
| Qdrant 1.18 | 语义向量检索 | Rust 高性能 ANN + 1024d COSINE + 本地部署零依赖 |

### Q: 6 张表设计要点

- **products**：skus + rag_knowledge 用 JSONB（动态属性无需 EAV，100 件规模完美）
- **users**：PBKDF2-SHA256 100k 迭代 + Bearer Token 每次登录刷新
- **addresses**：省/市/区/详细 + is_default 互斥逻辑
- **cart_items**：商品快照反范式（加购时复制 price/title/image，标准做法）
- **user_preferences**：JSONB + UPSERT ON CONFLICT
- **checkpoints**：JSON 文件存储（data/checkpoints/{session}_{node}.json）

### Q: 降级策略

```
DATABASE_URL="" + QDRANT_URL="" → JSON文件 + jieba（V0兼容）
任一有值                       → 对应功能启用
任一连接失败                    → 自动降级，不阻塞
```

`.env` 留空即降级，无需改代码。6 类 Repository 全部 PG+内存双模 + 工厂注入。

### Q: sync-async 桥接

LangGraph invoke() 同步 + SQLAlchemy async → `nest_asyncio` 允嵌套事件循环 → `loop.run_until_complete()` 桥接。

---

## 五、RAG 检索体系

### Q: 三层 RAG 架构

```
第一层：LLM查询改写（口语→搜索关键词）
第二层：三通道并行检索
  ├─ Text: Qdrant 1024d ANN + jieba关键词 RRF(k=60) 融合
  ├─ Review: ≤2★差评 + ≥4★好评 正反证据
  └─ Policy: FAQ航空/兼容/过敏 关键词匹配
第三层：Qwen3-Rerank 语义精排 + Evidence Sufficiency Checker
```

### Q: RRF 为什么不是加权求和？

两个排序列表分数尺度不同（余弦相似度 0~1 vs 关键词命中次数），RRF 只依赖排名位置无需归一化。业界标准（ES 8.x 也在用）。

### Q: 证据怎么绑定？

每个推荐结论绑定 `evidence_ids`（如 `E-MKT-p001`/`R-p001-0`/`POL-p001-1`/`V-p001-specs`），可追溯到具体数据源。Android ProductDetailSheet 证据 Tab 展示类型/内容/置信度。

---

## 六、可解释决策评分

### Q: 7 维公式

```
raw = 0.22×budget_fit + 0.24×scenario_fit + 0.20×spec_match
    + 0.14×review_confidence + 0.10×visual_similarity  
    + 0.10×availability_score - 0.15×risk_penalty

final = clamp(raw, 0, 1)
display = final×10（0-10分）
```

场景匹配权重最高，风险扣分独立不抵消。Android 端 ScoreBreakdown 7 维进度条颜色编码展示，每项可独立解释。

---

## 七、用户体系

### Q: 认证方案

PBKDF2-SHA256 100k 迭代（纯标准库，零外部依赖）+ Bearer Token。Android AuthManager SharedPreferences 持久化 + OkHttp 拦截器自动注入 `Authorization: Bearer <token>`。

### Q: 为什么不用 JWT？

比赛场景无需过期/刷新/黑名单等 JWT 复杂度。Bearer Token 每次登录刷新，足够安全。

### Q: 地址管理的默认地址互斥

数据库 + 仓库层双向保证：新增/修改默认地址时，自动清除同用户其他地址的 `is_default` 标记。

---

## 八、多模态 + 降级

### Q: 图片识别三级降级

```
L0: Qwen-VL 真实推理 → L1: Mock视觉解析 → L2: 纯文本模式
```

每级记录 `fallback_status`（level + attempts + description）。Visual Agent 输出 specs 为列表时自动 join 为字符串（适配 Qwen-VL 返回格式变化）。

### Q: Visual Evidence Grounding

Visual Agent 的每个字段（商品名/品牌/品类/规格×颜色/容量...）绑定独立 `evidence_id`（如 `V-p001-specs-颜色`），实现字段级视觉证据可追溯。

---

## 九、Skill Registry + ToolManager

### Q: Skill 和 Tool 什么关系？

| 概念 | 粒度 | 示例 |
|------|------|------|
| Skill | 组合能力（编排多个 Tool） | product_retrieve = text_search + vector_search + structured_filter |
| Tool | 原子能力 | product_text_search（jieba关键词检索） |

### Q: 安全机制

- Manifest 强制（input/output schema + permission_level + risk_level）
- Agent 权限检查（`can_agent_use(tool, agent)`）
- V1 只读强制（`permission_level != "read"` 直接拒绝）
- ToolCallRecord 全量记录（call_id/tool/agent/latency/status）

---

## 十、State Checkpoint + Decision Harness + Evidence Graph

### Q: Checkpoint 做什么？

JSON 文件持久化 8 节点状态 → 支持 resume（断点续跑）、replay（链路回放）、export（Demo Pack 导出）。

### Q: Harness 7 项校验

schema_valid / evidence_bound / score_recalculable / policy_cited / risk_warning / sufficiency_check / no_empty_answer

Android HarnessTab 智能展示：布尔值 ✅/❌，列表显示条目数+内容，嵌套字典展开子项。

### Q: Evidence Graph

NetworkX 商品-证据-风险图关系。`get_supporting_evidence(product_id)` / `get_risk_tags(product_id)` / `get_evidence_path(from, to)`。无 NetworkX 时优雅降级。

---

## 十一、Android 客户端全景

### Q: 四 Tab + 子页面

| Tab | 子页面 | 关键能力 |
|-----|--------|---------|
| 商品 | 品类筛选 + 商品列表 + 商品详情弹窗 6 Tab | 推荐/证据/评分/链路/技能/验证 |
| **豆仔** | 多轮对话 + 图片上传 + 加购 + Agent洞察10Tab | LLM改写检索 + 闲聊模式 + 自动滚动 + ⭐Agent洞察 |
| 购物车 | 增删改查 + 全选/多选 + 模拟结算 | 商品快照 + cartRefreshKey + LaunchedEffect |
| 我的 | 登录/注册 + 地址管理 + 偏好设置 | AuthManager + Token拦截器 + 默认地址互斥 |

### Q: 豆仔页面交互

- **文本输入**：LLM 查询改写 → 精准检索 → 7 维评分 → 证据绑定回答 → ProductCard + ProductDetailSheet（点击卡片）
- **图片识别**：Photo Picker → Qwen-VL → 三级降级 → 增强文字查询 → 卡片始终有加购按钮
- **闲聊模式**：自动检测 16 个闲聊词 → 跳过检索 → 纯文字友好回复 → 6 类模板兜底
- **Agent 洞察**：顶栏 ⭐ → AgentInsightSheet → 10 个 Tab（上下文/检索计划/证据图/降级/工具/反事实/视觉绑定/偏好/基准/摘要）
- **Demo 模式**：一键展示完整证据+链路+Harness+评分面板数据
- **自动滚动**：新消息自动滚动到底部
- **键盘**：imePadding() 根 Box 层无缝推升

### Q: ProductDetailSheet 6 Tab

推荐 → 证据列表 → 评分细分 → Agent 链路 → Skill 技能 → Harness 验证 ✅/❌

### Q: AgentInsightSheet 10 Tab（V1-Plus）

上下文 → 检索计划 → 证据图 → 降级状态 → 工具治理 → 反事实推荐 → 视觉绑定 → 偏好记忆 → 基准评测 → 摘要

---

## 十二、Counterfactual + Knowledge Index（进阶）

### Q: 0 结果时怎么办？

`CounterfactualRecommender` 三级建议：
```
结果=0 → 放宽预算 + 放宽品类 + 去除标签 + 重新措辞
结果≤2 → 展示热门 + 标注"不完全匹配"
结果≥3 → 正常展示
```

### Q: Knowledge Index 做什么？

250+ 关键词→品类映射 + 品类→子品类→品牌→商品 4 级分层。Router 意图识别和检索品类过滤的加速索引。

---

## 十三、Mock Mode / Demo Pack

### Q: 一键 Demo 怎么工作？

- Android Demo Mode 开关 → `MockDemoData` 提供完整预置数据：2 商品 + 2 决策结果 + 4 证据 + 7 条 Trace + 完整 Harness + AgentInsightSheet 全部数据
- 后端 Mock Mode：`.env` 中 `OMNICART_MOCK_MODE=true` → 所有 LLM 调用返回预置结果
- Demo Pack 导出：`scripts/export_demo_pack.py` — 4 场景（蓝牙耳机/防晒霜/跑步鞋/咖啡）

---

## 十四、全链路数据流（最新版）

```
1. 用户输入"推荐一款500以内的降噪蓝牙耳机"或拍照上传
2. Router Agent → 闲聊检测(16词) or 购物意图(6种)，约束抽取
3. PreferenceMemory → 合并/清除历史偏好（话题切换自动清除）
4. [可选] Visual Agent → Qwen-VL → 三级降级 → Visual Grounding字段绑定
5. Retrieval Agent → LLM提取关键词"蓝牙耳机 降噪 500元 无线"
   ├─ Text: Qdrant 1024d ANN + jieba RRF k=60 → 候选商品
   ├─ Review: ≤2★差评 + ≥4★好评 → 证据
   └─ Policy: FAQ关键词匹配 → 证据
6. Reranker → Qwen3-Rerank 语义精排（失败保持原序）
7. Evidence Checker → 按intent检查证据充足性 → sufficiency_report
8. Decision Agent → 硬约束过滤 + 7维评分 + 风险标签 + evidence绑定
9. Context Compiler → 编译结构化上下文（含Counterfactual反事实建议）
10. Response Agent → 闲聊独立Prompt or 购物LLM回答生成 + 模板兜底
11. Response Guard → 5项守门验证 → guard_warnings
12. Decision Harness → 7项统一校验 → harness_report
13. State Checkpoint → JSON文件持久化guard节点
14. Android展示: MessageBubble + ProductCard(始终有加购按钮) + ProductDetailSheet(6Tab) + AgentInsightSheet(10Tab)
```

---

## 十五、关键 Bug 及修复（答辩时可展示工程能力）

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | "买鞋"搜不到鞋 | jieba"买鞋"一词0匹配 | LLM查询改写 + 单字拆分兜底 |
| 2 | 拍照识图 500 错误 | Qwen-VL specs 返回 list，schema 要求 str | visual_agent join 列表转字符串 |
| 3 | 拍照商品无加购按钮 | 按钮在 decisionResult?.let 块内 | 移到外部始终渲染 |
| 4 | 面板点击闪退 | LazyColumn 嵌套 | 内层改为 Column + for 循环 |
| 5 | 键盘上升有空白 | imePadding 位置不当 | 移到根 Box 层 |
| 6 | 注册 422 | password min_length=4 | 改为 1 |
| 7 | Harness 全部 ❌ | 列表/字典值被 Boolean 判断误判 | 按类型分渲染 |
| 8 | sync-async 桥接 | LangGraph 同步 + SQLAlchemy async | nest_asyncio 嵌套事件循环 |
| 9 | 话题切换品类残留 | merge_constraints 操作副本 | 同时清除原始 session 数据 |
| 10 | 购物车切换不刷新 | restoreState=true 冲突 | cartRefreshKey + LaunchedEffect |

---

## 十六、常见追问

### Q: 怎么保证推荐不是胡说？

四层保障：evidence_ids 绑定 → 硬约束过滤(LLM不参与) → Response Guard 5项守门 → Decision Harness 7项校验。

### Q: 和普通导购的区别

| 普通 | OmniCart |
|------|---------|
| 黑盒 | 7维可解释 + evidence溯源 + 风险标签 |
| 单一文本 | 多模态RAG(文本+图片+评论+政策+向量) |
| 单次问答 | 8节点 Multi-Agent + trace_steps + checkpoint |
| 无法验证 | Guard + Harness + 闲聊检测 |
| 无记忆 | 多轮偏好 + 话题切换 + REST API |

### Q: 系统局限性

1. 100 件商品规模（但有 Counterfactual 兜底 + 4 级分层索引）
2. Qwen-VL 中文匹配有落差（Visual Grounding 缓解 + LLM 改写增强）
3. session 级记忆（V2 跨会话长期偏好）
4. 嵌入 API 依赖云端（降级为 jieba + 单字拆分，基本可用）

---

## 十七、技术亮点总结（答辩收尾）

| # | 亮点 | 一句话 |
|---|------|--------|
| 1 | LLM 查询改写 | Qwen 口语→搜索关键词 + jieba 单字兜底，精准命中 |
| 2 | 闲聊模式 | 16 词检测 → 跳过检索 → 6 类模板，纯文字友好交互 |
| 3 | 双库降级 | PG+Qdrant 填串即用，留空回退 JSON+jieba，零破坏 |
| 4 | RRF 混合检索 | 语义向量 + 关键词双重召回，任一通道失败自动降级 |
| 5 | 6 类仓库工厂 | ABC + PG/内存双模 + 工厂注入，测试/开发/生产即时切换 |
| 6 | 可解释决策 | 7 维评分 + evidence_ids 溯源 + 风险标签 + 进度条可视化 |
| 7 | 规则优先 LLM | 品类/预算/意图以规则为准，防幻觉 |
| 8 | Skill+Tool 双层 | 8 Skill(组合) + 8 Tool(原子) + Manifest + V1 只读 |
| 9 | Harness 7 项校验 | schema/证据/评分/政策/风险/充足性/非空 自动验证 |
| 10 | Checkpoint 持久化 | 8 节点 JSON 文件，支持 resume/replay/export |
| 11 | 三级多模态降级 | L0 Qwen-VL → L1 Mock → L2 纯文本 |
| 12 | Counterfactual | 0 结果时智能建议放宽约束 |
| 13 | Android 面板体系 | 6Tab(商品) + 10Tab(Agent洞察) + Demo 一键展示 |
| 14 | 用户体系完整 | 注册/登录/地址/偏好 + Token + 默认地址互斥 |
| 15 | sync-async 桥接 | nest_asyncio 让同步 Agent 调异步 PG/Qdrant |
| 16 | 闲聊+购物双模 | 日常对话不推商品，购物意图精准推荐 |
| 17 | Visual Grounding | 字段级视觉证据绑定，像素到数据可追溯 |

---

## 附录：核心代码索引

### 工作流
| 文件 | 职责 |
|------|------|
| `workflow/graph.py` | 8 节点 LangGraph + chitchat 边缘 |
| `workflow/checkpoint.py` | State Checkpoint JSON 持久化 |
| `workflow/workflow.yaml` | 声明式配置 |

### Agent
| 文件 | 职责 |
|------|------|
| `agents/router_agent.py` | 意图识别(6种) + 约束 + 闲聊检测(16词) |
| `agents/visual_agent.py` | Qwen-VL 解析 + specs list→str |
| `agents/retrieval_agent.py` | LLM 查询改写 + 三通道并行 |
| `agents/decision_agent.py` | 硬约束 + 7 维评分 |
| `agents/response_agent.py` | 闲聊 Prompt + 购物 Prompt + 6 类模板 |

### 检索
| 文件 | 职责 |
|------|------|
| `retrieval/text_retriever.py` | HybridSearch(Qdrant+jieba RRF) + 单字拆分 |

### 基础设施
| 文件 | 职责 |
|------|------|
| `skills/registry.py` | Skill Registry 8 Skill |
| `tools/manager.py` | ToolManager 8 Tool + 权限 + V1 只读 |
| `graph/evidence_graph.py` | NetworkX 证据图 |
| `vision/visual_grounding.py` | 字段级视觉证据绑定 |
| `vision/multimodal_fallback.py` | 三级降级 |
| `decision/counterfactual.py` | 反事实建议 |
| `indexing/category_index.py` | 4 级分层品类索引 |
| `harness/decision_harness.py` | 7 项校验框架 |
| `a2a/dispatcher.py` | AgentMessage/Artifact 分发 |
| `memory/preference_memory.py` | 多轮记忆 + 话题切换 |

### Android
| 文件 | 职责 |
|------|------|
| `MainScreen.kt` | 四 Tab + NavHost(10 路由) |
| `feature/chat/ChatScreen.kt` | 豆仔对话 + 面板 + 键盘 + 自动滚动 |
| `feature/product/ProductCard.kt` | 卡片 + 评分 + 加购(始终显示) |
| `feature/product/ProductDetailSheet.kt` | 6 Tab 详情弹窗 |
| `feature/panel/AgentInsightSheet.kt` | V1-Plus 10 Tab Agent 洞察 |
| `feature/auth/*` | 登录/注册 + AuthManager |
| `feature/address/*` | 地址管理 CRUD |
| `feature/preference/*` | 偏好设置 |
| `feature/demo/MockDemoData.kt` | 一键 Demo 预置数据 |
| `core/network/OmniCartApi.kt` | 26+ API 端点 + 数据类 |
