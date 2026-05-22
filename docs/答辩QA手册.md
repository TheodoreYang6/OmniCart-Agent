# OmniCart Agent 答辩 QA 手册

> 适用：字节跳动 Agent 挑战赛答辩 / 技术面试 / 项目汇报
> 更新：2026-05-22（基于 V1 参赛版当前架构）

---

## 一句话定位

> OmniCart Agent 是一个面向购买前决策的 Android 原生多模态购物决策 Agent，融合 Qwen 全栈模型、多路证据 RAG（含 Qdrant 语义向量检索）、LangGraph Multi-Agent 编排、PostgreSQL 持久化与 7 维可解释决策评分。

---

## 一、系统架构（必问）

### Q: 整体架构

```
Android App (Kotlin/Compose/MVVM)
    │ Retrofit + OkHttp
    ▼
FastAPI Backend (Python 3.11)
    │
    ├─ POST /api/recommend/v2 ──→ LangGraph Workflow
    │   Router → Visual(Qwen-VL) → Retrieval → Reranker → Decision → Response(Qwen) → Guard
    │       │                           │
    │       ▼                           ▼
    │   PreferenceMemory          HybridSearch
    │   (PostgreSQL)              ├─ Qdrant (1024d ANN)
    │                             └─ jieba (关键词)
    │
    ├─ /api/products  ──→ PgProductRepository (100件商品)
    ├─ /api/cart      ──→ PgCartRepository (PostgreSQL)
    ├─ /api/checkout  ──→ Mock 结算
    ├─ /api/agent/action → 豆仔加购
    └─ /api/upload    ──→ 图片上传 + Qwen-VL 解析
```

**关键文件：**
- 工作流：`backend/app/workflow/graph.py`
- API 入口：`backend/app/api/recommend.py`
- Android 客户端：`android-client/app/src/main/java/com/omnicart/agent/`

### Q: 为什么用 LangGraph 而不是自己写 if-else 或开放式 ReAct？

购物决策需要 **可控性 + 可追溯 + 安全约束**：
1. 每一步产出可追踪、可审计、可回放（`trace_steps` 记录每个 Agent 的执行结果）
2. 每个推荐结论绑定 `evidence_ids`，杜绝 LLM 幻觉
3. 硬约束（预算超 2 倍/品类不匹配）在 Decision Agent 中规则过滤，LLM 只做回答生成，不做决策判断
4. 开放式 ReAct 可能死循环或跳过约束检查，不适合生产环境

---

## 二、数据库架构（重点）

### Q: 为什么选 PostgreSQL + Qdrant 双库？

| 数据库 | 用途 | 选型理由 |
|--------|------|---------|
| PostgreSQL | 商品、购物车、用户偏好 | JSONB 存嵌套数据、全文搜索 tsvector、ACID 事务、asyncpg 异步驱动 |
| Qdrant | 语义向量检索 | Rust 实现高性能 ANN、COSINE 距离、本地 Windows 二进制部署零依赖 |

### Q: 降级策略

```
DATABASE_URL 为空 + QDRANT_URL 为空 → JSON 文件 + jieba 关键词（V0 模式）
DATABASE_URL 有值 + QDRANT_URL 为空 → PostgreSQL + jieba 关键词
两个都有值                      → 全功能模式
任何一个连接失败                 → 自动降级，不阻塞主链路
```

`.env` 中留空连接串即自动降级，无需改代码。开发和参赛 Demo 可分别配置。

### Q: 三张表设计

#### products（100 件商品）

| 列 | 类型 | 说明 |
|----|------|------|
| `product_id` | VARCHAR(64) PK | `p_beauty_001` |
| `title` / `brand` | TEXT / VARCHAR(128) | 商品名 / 品牌 |
| `category` | VARCHAR(64) INDEX | 美妆护肤/数码电子/服饰运动/食品饮料 |
| `sub_category` | VARCHAR(64) INDEX | 精华/手机/T恤/咖啡 |
| `base_price` | NUMERIC(10,2) INDEX | 基准价 |
| `skus` | JSONB | `[{sku_id, properties, price}]` |
| `rag_knowledge` | JSONB | marketing_description + official_faq + user_reviews |

**为什么 SKU 和知识库用 JSONB 而不是拆分表？**
- SKU 属性是动态的（颜色/容量/尺码），无固定 schema，拆表需要 EAV 模式
- 用户评论和 FAQ 是嵌套数组，拆分需 3+ 关联表，JOIN 开销大
- JSONB 支持索引和 `->>` 运算符查询，100 件商品规模完全够用

#### cart_items

| 列 | 类型 | 设计要点 |
|----|------|---------|
| `cart_item_id` | VARCHAR(64) PK | UUID4 前 8 位 |
| `user_id` | VARCHAR(64) INDEX | 默认 `demo_user_001` |
| `title`/`brand`/`price`/`image_url` | — | **反范式化快照**——加购时复制商品信息 |

**为什么反范式化？** 购物车是快照语义——用户加购后，即使商品涨价或下架，购物车记录不变。这是电商系统的标准做法。

#### user_preferences

| 列 | 类型 | 说明 |
|----|------|------|
| `session_id` | VARCHAR(64) INDEX | 会话 ID |
| `preferences` | JSONB | `{category, budget_max, scenario, ...}` |
| UNIQUE(`session_id`, `user_id`) | — | UPSERT 冲突键 |

### Q: Repository 抽象层怎么设计的

```
BaseProductRepository (ABC)
    ├── JsonProductRepository   (JSON 文件，默认)
    └── PgProductRepository     (PostgreSQL，填串即切)

BaseVectorRepository (ABC)
    ├── StubVectorRepository    (空操作降级)
    └── QdrantVectorRepository  (真实 Qdrant ANN)
```

工厂函数根据 `.env` 自动选择：
```python
def get_product_repo():
    if USE_POSTGRES: return PgProductRepository()
    return JsonProductRepository()
```

### Q: 同步 Agent 怎么调用异步 PostgreSQL？

**矛盾**：LangGraph `invoke()` 是同步的，但 SQLAlchemy async 需要事件循环。

**方案**：`nest_asyncio` 允许嵌套事件循环 → `loop.run_until_complete()` 在运行中的 Uvicorn 循环中同步等待异步查询。

```python
def _run(self, coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # 无循环：直接创建
    
    nest_asyncio.apply(loop)      # 允许嵌套
    return loop.run_until_complete(coro)  # 同步等待
```

### Q: 购物车和偏好也支持 PG/内存双模吗？

是。`PgCartRepository` / `MemCartRepository` 和 `PgPreferenceRepository` / `MemPreferenceRepository`，通过各自 `get_*_repo()` 工厂自动切换。测试环境用 `Mem*` 零依赖，生产环境用 `Pg*` 持久化。

---

## 三、RAG 检索 — 多模态证据 RAG（重点必问）

### Q: 你们的 RAG 整体架构

三层 RAG，从粗到精：

```
第一层：商品知识库
  100件商品 JSON → PostgreSQL products 表
  每件含 rag_knowledge: {营销描述, 官方FAQ, 用户评论(1-5分)}
  
第二层：多通道检索（Retrieval Agent 并行）
  ├─ Text 通道：HybridSearch（Qdrant 向量 + jieba 关键词 RRF 融合）
  ├─ Review 通道：提取 ≤2★ 差评 + ≥4★ 好评作为正反证据
  └─ Policy 通道：FAQ 中匹配航空/兼容/敏感/过敏等关键词条
  
第三层：精排 + 证据绑定
  Qwen3-Rerank 语义重排序
  每条结果绑定 evidence_id: E-MKT-* / R-* / POL-* / V-*
```

### Q: Hybrid Search 怎么融合向量和关键词？

```
用户查询 "蓝牙耳机降噪好的"
    │
    ├──→ Qwen text-embedding-v4 → 1024d 向量 → Qdrant ANN (top_k × 2)
    │
    └──→ jieba 分词 → 品类约束过滤 → 关键词全文匹配 (top_k × 2)
    
    ↓ RRF 融合 (Reciprocal Rank Fusion, k=60)
    
    score = 1/(60 + rank_qdrant) + 1/(60 + rank_text)
    
    ↓ 按融合分降序 → Top-K
```

**为什么用 RRF 而不是加权求和？**
- 两个排序列表的分数尺度不同（0~1 的余弦相似度 vs 整数关键词命中次数）
- RRF 只依赖排名位置，无需归一化
- 业界标准做法（Elasticsearch 8.x 也在用）

### Q: Qdrant 怎么配置的？

```
Collection: products
维度: 1024（匹配 text-embedding-v4 输出）
距离度量: COSINE
索引数据: 100 件商品
嵌入文本: "product_id | title brand category sub_category marketing_description"
构建脚本: scripts/seed_qdrant.py
```

Qdrant 不可用时 `hybrid_search()` 透明降级为纯 jieba 关键词，用户无感知。

### Q: 证据怎么绑定到推荐结果？

每条证据有唯一 ID，可追溯到原始数据：

```
E-MKT-p_digital_007      → 营销描述证据
R-p_digital_007-0        → 第 0 条用户评论
POL-p_digital_007-1      → 第 1 条 FAQ 政策证据
V-screenshot             → 视觉识别证据
```

Android 端在 ProductDetailSheet 的证据 Tab 中展示每条证据的类型、来源内容、置信度。

**代码位置：** `backend/app/retrieval/text_retriever.py` — `_product_to_result()`
**Android 端：** `ProductDetailSheet.kt` — EvidenceTab

---

## 四、Multi-Agent 编排（创新点必问）

### Q: 5 个 Agent 分别做什么？

```
Router Agent     → 意图识别(5种) + 约束抽取 + 检索计划生成
                  规则为主(90%+) + LLM增强(Qwen intent_understanding)
                  
Visual Agent     → Qwen-VL 商品截图解析
                  {product_name, brand, category, price, specs, confidence}
                  
Retrieval Agent  → 三通道并行检索(text + review + policy)
                  text通道: HybridSearch(Qdrant+ jieba RRF)
                  
Decision Agent   → 硬约束过滤 + 7维加权评分 + 风险标签 + 证据绑定
                  预算超2倍/品类不匹配 → 直接排除
                  
Response Agent   → Context Compiler 编译上下文 → Qwen LLM 生成回答
                  LLM失败 → 模板兜底

Response Guard   → 5项守门：证据绑定/价格准确/风险提醒/诚实/无依据断言
```

**每个 Agent 都是一个独立模块，有明确的输入(WorkflowState)→输出(WorkflowState)合约。**

### Q: Agent 之间怎么通信？

通过 LangGraph 的 `WorkflowState` 全局状态传递。Agent 读取 state 中的字段（如 `user_query`、`constraints`、`retrieved_products`），处理后写回新的 state 字段。A2A-lite 的 AgentCard/AgentMessage/Artifact 数据模型已定义，V2 可升级为标准 A2A 协议。

### Q: Router Agent 的意图识别怎么做？

**规则为主 + LLM 增强**混合策略：
- 规则层 `_rule_based_parse()`：覆盖 90%+ 中文购物表达——品类关键词（250+ 词覆盖 4 大品类）、预算正则（"500以内"/"¥300"）、场景词、意图词
- LLM 层：Qwen `intent_understanding`（温度 0.3）处理长尾表达
- 合并策略：**规则优先于 LLM**（防止 LLM 幻觉覆盖品类检测）
- LLM 不可用时 100% 规则兜底，系统不中断

**为什么规则优先？** 实测发现 Qwen 有时会将"买食品"误判为"美妆护肤"。规则优先保证核心品类/预算/意图不受 LLM 干扰。

---

## 五、可解释决策评分（创新点必问）

### Q: 评分公式

7 维加权，每项独立可解释，Android 端以进度条可视化：

```
raw = 0.22 × budget_fit       (预算匹配：价格/预算比)
    + 0.24 × scenario_fit      (场景匹配：最高权重)
    + 0.20 × spec_match        (规格匹配：关键词命中标题/品类)
    + 0.14 × review_confidence  (评论置信度：真实 user_reviews 评分)
    + 0.10 × visual_similarity  (视觉相似度：Qwen-VL 识别结果匹配)
    + 0.10 × availability_score (可用性：当前固定 1.0)
    - 0.15 × risk_penalty       (风险扣分：低分评论比例 + 高价惩罚)

final = clamp(raw, 0, 1)
display = final × 10  → 0-10 分展示
```

**权重设计理由**：场景匹配最高（用户需求 > 预算），风险扣分独立（不与其他维度抵消，差评多就扣分）。

### Q: 评论置信度怎么算

用数据集真实 `user_reviews[].rating`（1-5 分）：

```python
avg_rating = sum(ratings) / len(ratings)
normalized = avg_rating / 5.0           # 归一化到 0-1
count_bonus = min(0.15, len(reviews) × 0.03)  # 评分数多更可信
review_confidence = min(1.0, normalized + count_bonus)
```

---

## 六、多轮对话记忆

### Q: 怎么记住用户之前说的偏好？

`PreferenceMemory` — 会话级多轮记忆，内存 + PostgreSQL 双存储：

```
第 1 轮: "推荐蓝牙耳机" → Router 检测 category=数码电子 → 存储
第 2 轮: "500以内的"    → Router 检测 budget_max=500   → 合并存储
第 3 轮: "推荐咖啡"     → Router 检测 category=食品饮料 → 话题切换 → 清除旧约束
第 4 轮: "那降噪好的呢" → 保留 budget+category，追加 must_tag=降噪
```

**话题切换检测**：新旧 category 不同 → `forget()` 清空全部旧约束，从头开始。新 query 未检测到品类但旧约束存在 → 清除旧品类，避免"想买鞋但还是搜数码"的问题。

Android 端通过持久 `session_id` 关联同一会话。点击「新对话」按钮重置 session。

---

## 七、多模态识别（创新点必问）

### Q: 图片识别流程

```
用户拍照/选图 (Android Photo Picker)
  → ContentResolver 读字节 → OkHttp MultipartBody
  → POST /api/upload → 保存 data/uploads/
  → POST /api/recommend/v2 { user_query, image_url }
  → LangGraph: Visual Agent → Qwen-VL API
  → 提取 JSON {product_name, brand, category, price, specs, confidence}
  → 识别结果注入搜索查询 → 增强检索精准度
```

### Q: 识别不准怎么降级

三级降级：
1. Qwen-VL 正常识别（confidence > 0.5）→ 增强查询
2. 识别低置信度 → 保留原始查询词，不注入识别结果
3. 完全失败 → Response Agent 提示用户补充文字描述

**fallback_level 字段追踪每次识别的降级状态。**

---

## 八、LLM 管理（必问）

### Q: 用了哪些 Qwen 模型？怎么管理的？

通过 **Model Gateway** 统一调用，业务代码只写能力名不写模型名：

| 能力 | 模型 | 参数 | 用途 |
|------|------|------|------|
| `chat_generation` | qwen-plus | temp=0.7, 2048t | 回答生成 |
| `intent_understanding` | qwen-plus | temp=0.3, 1024t | Router 意图识别 |
| `visual_understanding` | qwen-vl-plus | temp=0.3, 2048t | 商品截图解析 |
| `text_embedding` | text-embedding-v4 | 1024dim | Qdrant 向量检索 |
| `text_reranking` | qwen3-rerank | — | 语义精排 |

配置集中在 `model_config.yaml`，换模型只需改 YAML，业务代码不动。

### Q: Mock Mode 是什么？

`.env` 中 `OMNICART_MOCK_MODE=true` → 所有 LLM 调用返回预置假数据：
- MockChat → 固定文本
- MockEmbedding → MD5 哈希伪向量（128dim）
- MockReranker → 保持原始顺序

用途：离线开发、现场 Demo 网络不可用时一键切换，保证演示不中断。

---

## 九、Android 客户端（必问）

### Q: 技术栈

```
Kotlin + Jetpack Compose + Material 3
MVVM (ViewModel + StateFlow)
Retrofit + OkHttp + Gson (网络)
Coil (图片加载)
Coroutines (异步)
Navigation Compose (四 Tab 路由)
```

### Q: 四 Tab 架构

| Tab | 功能 | 后端 API |
|-----|------|---------|
| 商品 | 品类筛选 + 商品列表 + 详情弹窗 | `GET /api/products` |
| 豆仔 | 多轮对话推荐 + 图片上传 + 加入购物车 | `POST /api/recommend/v2` + `POST /api/agent/action` |
| 购物车 | 增减/全选/删除/结算 | `GET/POST/PUT/DELETE /api/cart` + `POST /api/checkout` |
| 我的 | 个人信息 + 偏好 + 地址（静态占位） | 待实现 |

### Q: 手机怎么连后端？

ADB 反向隧道：`adb reverse tcp:8006 tcp:8006`
手机访问 `127.0.0.1:8006` → 自动转发到电脑 `localhost:8006`

`AppConfig.kt` → `BASE_URL = "http://127.0.0.1:8006/"`
双击 `connect.bat` 一键建立隧道。

### Q: 加入购物车后购物车 Tab 怎么刷新？

MainScreen 点击购物车 Tab 时累加 `cartRefreshKey` → 传给 CartScreen → `LaunchedEffect(refreshKey)` 检测到变化 → 调用 `loadCart()` 重新拉取 `/api/cart`。

---

## 十、Context Compiler（进阶问）

### Q: LLM 的 prompt 怎么组织的？

不是把原始数据直接丢给 LLM。先用 Context Compiler 编译成结构化上下文：

```
用户需求 + 约束条件
    ↓
图片识别结果（如有）
    ↓
候选商品（含评分/风险/推荐理由）
    ↓
证据摘要（按类型统计 + 关键证据摘录）
    ↓
反事实建议（0 结果时提示放宽条件）
    ↓
→ 编译为 LLM Prompt
```

**代码位置：** `backend/app/context/compiler.py`

---

## 十一、数据流全景（完整请求链路）

```
1. 用户输入 "推荐一款500以内的降噪蓝牙耳机"
2. Router Agent → intent=recommend, category=数码电子, budget=500
3. PreferenceMemory → 合并历史偏好（如有话题切换则清除）
4. [可选] Visual Agent → Qwen-VL 解析图片
5. Retrieval Agent → 三通道并行:
   ├─ text: Qdrant ANN + jieba 关键词 → RRF 融合
   ├─ review: 提取差评证据 + 好评证据
   └─ policy: FAQ 匹配关键规则
6. Reranker → Qwen3-Rerank 语义精排
7. Decision Agent → 硬约束过滤 + 7维评分 + 证据绑定 + 风险标签
8. Context Compiler → 编译结构化上下文
9. Response Agent → Qwen LLM 生成自然语言回答（含证据引用）
10. Response Guard → 5项验证 → harness_report
11. Android 展示: MessageBubble + ProductCard + ProductDetailSheet(6 Tab)
```

**文本链路约 3-5 秒，含图片约 5-8 秒（含 Qwen-VL API 调用）。**

---

## 十二、常见追问

### Q: 怎么保证推荐不是胡说？

三层保障：
1. **证据绑定**：每个结论绑定 `evidence_ids`，来源可追溯到具体商品/评论/FAQ
2. **硬约束过滤**：预算超 2 倍/品类不匹配直接排除，LLM 不参与约束判断
3. **Response Guard**：5 项规则（证据/价格/风险/诚实/无依据）拦截无依据断言

### Q: 和普通电商导购的区别

| 普通导购 | OmniCart Agent |
|---------|---------------|
| 黑盒推荐 | 7 维可解释评分 + 证据溯源 |
| 单一文本匹配 | 多模态 RAG（文本+图片+评论+政策+FAQ 向量） |
| 单次问答 | Multi-Agent 决策链路，每步可追踪 `trace_steps` |
| 无法验证 | Response Guard 自动验证 + `harness_report` |
| 无记忆 | 多轮偏好记忆 + 话题切换检测 |

### Q: 系统局限性

1. 数据集仅 100 件旗舰产品，低价/长尾查询可能 0 结果（已用反事实建议提示放宽条件）
2. Qwen-VL 返回英文名与中文数据集标题可能有匹配落差
3. 多轮记忆基于 session 级，跨会话需 V2 用户系统
4. 嵌入 API 依赖 Qwen 云端（DashScope），网络不可用时语义检索降级为关键词

### Q: V2 计划做什么？

1. Redis 缓存（视觉解析/Demo Pack 缓存）
2. 用户系统（登录注册 + 跨会话记忆）
3. 多模态分层索引（图片向量 + 文本向量双 Qdrant Collection）
4. Evidence Graph Lite（NetworkX 构建商品-参数-评论图关系）
5. A2A 标准协议升级
6. iOS SwiftUI 客户端

---

## 十三、技术亮点总结（答辩开场或收尾用）

| # | 亮点 | 一句话 |
|---|------|--------|
| 1 | 双数据库自动降级 | PG+Qdrant 填串即用，留空自动回退 JSON+jieba，零破坏 |
| 2 | RRF 混合检索 | 语义向量 + 关键词双重召回融合，任一通道失败自动降级 |
| 3 | 仓库抽象工厂 | ABC + 工厂注入，测试/开发/生产三套配置随时切换 |
| 4 | 可解释决策 | 7 维评分 + evidence_ids 溯源 + 风险标签，彻底告别黑盒 |
| 5 | 规则优先 LLM | Router 品类/预算/意图以规则为准，LLM 只做补充，防幻觉 |
| 6 | 同步-异步桥接 | nest_asyncio 让同步 Agent 调用异步数据库，无需全链路重构 |
| 7 | MCP-compatible | Agent 不直接操作 DB，所有动作通过受控 API，可审计可追溯 |

---

## 附录：核心代码快速索引

| 你想找什么 | 去这里 |
|-----------|--------|
| 工作流编排 | `backend/app/workflow/graph.py` |
| Hybrid 混合检索 | `backend/app/retrieval/text_retriever.py:hybrid_search()` |
| 7 维评分公式 | `backend/app/decision/scoring.py` |
| Router 规则引擎 | `backend/app/agents/router_agent.py:_rule_based_parse()` |
| Visual 图片解析 | `backend/app/agents/visual_agent.py` |
| 回复生成 + 模板兜底 | `backend/app/agents/response_agent.py` |
| Response Guard 5 项守门 | `backend/app/verification/response_guard.py` |
| Context Compiler | `backend/app/context/compiler.py` |
| Preference 多轮记忆 | `backend/app/memory/preference_memory.py` |
| Model Gateway | `backend/app/model_gateway/gateway.py` |
| PG 仓库（sync-async 桥接） | `backend/app/repositories/pg_product_repo.py` |
| Qdrant 向量仓库 | `backend/app/repositories/qdrant_vector_repo.py` |
| 仓库抽象基类 + 工厂 | `backend/app/repositories/base_product_repo.py` + `product_repo.py` |
| 三张表 ORM 模型 | `backend/app/models/product.py` / `cart_item.py` / `user_preference.py` |
| Alembic 迁移 | `alembic/versions/001_initial.py` |
| 种子脚本 | `scripts/seed_postgresql.py` / `scripts/seed_qdrant.py` |
| Android 四 Tab 主框架 | `MainScreen.kt` |
| Android 对话 + 加购 | `ChatScreen.kt` + `ChatViewModel.kt` |
| Android 购物车 | `CartScreen.kt` + `CartViewModel.kt` |
| Android 商品详情 6 Tab | `ProductDetailSheet.kt` |
| Android 网络层 | `OmniCartApi.kt` + `ApiClient.kt` |
| .env 配置 | 项目根目录 `.env` |
| 100 件商品数据 | `ecommerce_agent_dataset/` |
