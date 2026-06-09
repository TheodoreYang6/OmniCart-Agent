# OmniCart Agent RAG 全链路技术文档

**版本**: V4 | **日期**: 2026-06-02 | **状态**: 生产级，已通过全链路验证

---

## 目录

1. [架构总览与设计哲学](#一架构总览与设计哲学)
2. [全链路详解：10站逐站剖析](#二全链路详解10站逐站剖析)
3. [完整数据流轨迹](#三完整数据流轨迹)
4. [答辩 / 面试常见问题](#四答辩--面试常见问题)
5. [RAG 评价体系：当前实现与未来优化](#五rag-评价体系当前实现与未来优化)

---

## 一、架构总览与设计哲学

### 1.0 一句话概述

> **OmniCart RAG 链路是一条 10 站流水线，将用户的购物口语转化为证据驱动的商品推荐。每一站独立可替换、每一站有降级方案、每一条推荐结论可追溯到具体证据。**

### 1.1 全景架构图

```
用户说："推荐一款200以内适合跑步的蓝牙耳机"
  │
  │  ┌─────────────────────────────────────────────────────┐
  │  │               Workflow 外部                          │
  │  │  [0] FollowUpEngine ─── 追问检测(7模式)              │
  │  │       ↓ context_prompt + updated_constraints         │
  │  └─────────────────────────────────────────────────────┘
  │
  ├── [1] RouterAgent ───────────── 意图识别 + 约束抽取 + 检索计划
  │     ├─ 规则兜底 (100%可靠) + LLM增强 (可选)
  │     └─ 输出: intent, category, budget_max, scenario, channels
  │
  ├── [2] MemoryRetriever ───────── 长期偏好记忆检索
  │     ├─ 品牌/品类/场景偏好 → 搜索词增强 (检索后恢复)
  │     └─ 输出: used_memories, blocked_memories, memory_trace
  │
  ├── [3] LLM Query Rewrite ─────── 口语→搜索关键词
  │     ├─ Qwen LLM 提取关键词 + Redis 缓存 30min
  │     └─ "推荐一款200以内适合跑步的蓝牙耳机" → "蓝牙耳机 跑步 运动 无线"
  │
  ├── [4] Semantic Search ───────── 核心检索 (Chunk级)
  │     ├─ Qwen Embedding (1024维) → Qdrant ANN (1133 chunks)
  │     ├─ 约束过滤 → Chunk聚合 → 产品排名
  │     ├─ 五级降级: Qdrant→本地余弦→产品级Qdrant→产品级本地→子串匹配
  │     └─ 输出: retrieved_products[] (含 matched_chunks + evidence_ids)
  │
  ├── [5] Review/Policy Mining ──── 并行证据提取
  │     ├─ ThreadPool: _review_channel ∥ _policy_channel
  │     ├─ 评论分级: risk(≤2星) / neutral(3星) / positive(≥4星)
  │     └─ 输出: evidence_list[] (E-MKT-*/POL-*/R-*)
  │
  ├── [6] Supplementary Search ──── 反向发现 (结果<3时触发)
  │     ├─ Embedding余弦搜索 faq/rev chunk
  │     └─ 输出: 遗漏商品 + E-SUPP-* 证据
  │
  ├── [7] Qwen Reranker ─────────── 语义精排
  │     ├─ Cross-encoder 重排序 (title+desc+FAQ+评论+evidence)
  │     └─ 写回: reranker_score + relevance_score
  │
  ├── [8] Evidence Check ────────── 证据充足性验证
  │     ├─ 按 intent 检查必需证据类型
  │     └─ 不足时全局降级为 cautious
  │
  ├── [9] Decision Agent ────────── 证据驱动9维评分
  │     ├─ 0.45×relevance + 0.20×budget + 0.12×user_sat + ...
  │     ├─ 5级推荐: strong_recommend → not_recommended
  │     └─ 输出: DecisionResult[] (含 component_scores + evidence_ids)
  │
  └── Response → Guard ──────────── 生成回答 + 安全验证 → 返回客户端
```

### 1.2 三大核心设计原则

#### 原则一：降级无处不在 (Degradation Everywhere)

```
Qdrant ANN (最快最准)
  ↓ Qdrant宕机
本地暴力余弦 (35MB缓存, 1133 chunks, 毫秒级)
  ↓ 约束过滤后无结果
产品级Qdrant (粗粒度)
  ↓ Qdrant仍不可用
产品级本地 (3.5MB缓存, 105 products)
  ↓ 无结果
关键词子串匹配 (不用向量, 纯文本)
  ↓
至少返回空列表 + 兜底话术，绝不白屏/报错
```

**每一站独立降级**：Embedding挂了→走关键词；LLM挂了→走规则；Reranker挂了→保持原排序。不存在单点故障。

#### 原则二：证据可追溯 (Evidence-Backed)

```
所有推荐结论绑定 evidence_id

推荐等级: recommended ─── 因为:
  ├─ support_evidence_ids: ["E-MKT-p_digital_007-0", "R-p_digital_007-0"]
  ├─ 可点击查看: "[营销] Baseus入门TWS，蓝牙5.3，续航5h..."
  └─ 可点击查看: "[用户] 小明(5星): 音质好，续航长，性价比高"

证据ID体系统一:
  E-MKT-{pid}-0      → 营销描述
  POL-{pid}-{i}       → 官方FAQ
  R-{pid}-{i}         → 用户评论
  E-SUPP-{pid}        → 补充发现证据
```

#### 原则三：去 LLM 化，可复算 (LLM-Free Core Scoring)

```
V4 评分公式完全由确定性规则计算:

  raw = 0.45 × relevance          ← Reranker分数 或 检索分数 或 关键词匹配
      + 0.20 × budget_fit         ← 价格在预算内的比例
      + 0.12 × user_sat           ← 评论均分/5
      + 0.10 × value_score        ← 同品类性价比分位
      + 0.08 × spec_quality       ← 技术规格关键词命中
      + 0.05 × scenario_fit       ← 场景关键词命中
      + preference_bonus          ← 长期偏好匹配 (max 0.07)
      - risk_penalty              ← 差评扣分 (max 0.30)
      - avoid_penalty             ← 避雷惩罚 (max 0.10)

LLM 仅用于两处可选增强:
  1. Query Rewrite (口语转关键词, 失败退回原query)
  2. Router 意图识别 (失败用规则兜底)

评分本身不调LLM → 同一输入永远得到同一分数 → 可复算、可审计
```

### 1.3 关键数据

| 指标 | 数值 | 说明 |
|------|------|------|
| 商品总数 | 105 | 覆盖数码/美妆/服饰/食品四大品类 |
| Chunk总数 | 1133 | summary(105) + mkt(105) + faq(454) + rev(469) |
| 向量维度 | 1024 | Qwen text-embedding-v4 |
| Chunk缓存 | 35.2MB | 本地 product_chunk_embeddings.json |
| 检索降级 | 5级 | Qdrant→本地余弦→产品Qdrant→产品本地→子串 |
| 评分维度 | 9维 | 6基础 + risk - penalty + preference_bonus - avoid_penalty |
| 推荐等级 | 5级 | strong_recommend / recommended / cautious / insufficient_evidence / not_recommended |
| 追问模式 | 7种 | 序数引用/上次引用/预算更新/购物车/对比/模糊追问/纯预算 |
| Evidence类型 | 4类 | marketing / official_faq / user_review / supplementary |

---

## 二、全链路详解：10站逐站剖析

### 站点0：FollowUpEngine — 追问上下文继承

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/services/followup_engine.py` |
| **调用入口** | `backend/app/api/agent_stream.py:99-116` |
| **依赖** | ConversationService (PG context_snapshot), PreferenceMemory (session约束) |
| **输入** | conversation_id, session_id, current_query |
| **输出** | is_follow_up, follow_up_type, context_prompt, updated_constraints |

#### 职责一句话

> 在 Workflow 启动前判断用户是否在追问，如果是则从上一轮对话继承品类/预算/场景约束。

#### 为什么要放在 Workflow 外面？

FollowUpEngine 需要读两个数据源：**PG 中的 context_snapshot**（上轮的 product_ids、last_answer）和 **PreferenceMemory**（session 累积约束）。这些是"对话级"数据，不属于 WorkflowState 的一部分。在 workflow 前完成检测，将结果以 `context_prompt`（追加到 query）和 `updated_constraints`（注入 WorkflowState）的形式传给下游。

#### 7种追问模式（按优先级）

| 优先级 | 模式 | 触发条件 | 示例 | 处理方式 |
|--------|------|---------|------|---------|
| 1 | `ordinal_ref` | "第X个怎么样" | "第二个怎么样？" | 精确定位上一轮推荐的第N个商品 |
| 2 | `last_ref` | "刚才那个"/"这个" | "这个能上飞机吗？" | 引用上轮第一个商品 |
| 3 | `budget_update` | "换成X元以内的" | "换成200以内的" | 更新预算上限，继承品类 |
| 4 | `cart_intent` | "加入购物车"/"加购" | "加入购物车" | 标记加购意图 + 定位商品 |
| 5 | `compare` | "和刚才那个比" | "和刚才那个比哪个好？" | 启动对比模式 |
| 6 | `vague_followup` | "便宜一点"/"好一点"(无品类词) | "有没有便宜一点的" | 继承品类+场景，调整预算倾向 |
| 7 | `budget_only` | 价格数字(无品类词) | "100以内" | 设预算 + 继承品类 |

#### 架构演变

旧架构中，追问逻辑分散在两处：
- `ContextBuilder` (`services/context_builder.py`) — 5种精确模式检测（序数/上次/预算/购物车/对比）
- `RouterAgent._enhance_with_session()` — 模糊追问继承品类

P2 重构将两者合并为 `FollowUpEngine`，统一 7 模式检测，单次 `detect()` 调用完成全部工作。

#### 答辩要点

> "追问检测必须放在 Workflow 外面，因为它依赖对话级数据（PG context_snapshot）而非请求级数据。放在 Workflow 内会导致循环依赖——Workflow 需要 constraints 才能检索，但追问检测需要上轮检索结果才能确定继承什么约束。"

---

### 站点1：RouterAgent — 意图识别 + 约束抽取

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/agents/router_agent.py` |
| **调用入口** | `backend/app/workflow/graph.py:_node_router` L42-45 |
| **输入** | user_query, session_id (用于构建会话上下文) |
| **输出** | intent, constraints (category/budget/scenario/must_tags/exclude_tags), retrieval_plan (channels/top_k) |

#### 职责一句话

> 从用户自然语言中提取结构化购物需求：想买什么品类？预算多少？什么场景？有什么硬性要求？

#### 双保险设计：规则底 + LLM顶

```
规则解析 _rule_based_parse(query)        ← 100%可靠，无需网络
  ├─ 闲聊检测: "你好/谢谢/再见" → intent=chitchat → 跳过全部检索
  ├─ 意图: "对比/vs"→compare, "风险/过敏"→risk_check, "替代/换一个"→alternative
  ├─ 品类: detect_category(query) → 数码电子/美妆护肤/服饰运动/食品饮料
  ├─ 预算: detect_budget(query) → 正则提取数字+单位 (200以内/100-300元)
  ├─ 场景: detect_scenario(query) → commute/sport/flight/office...
  └─ 排除: "不要XX"/"不想买XX" → exclude_tags

LLM增强 gateway.chat("intent_understanding", prompt)  ← 可选，失败静默降级
  └─ 预填约束时跳过 (引导流程已完成品类选择)

合并策略: LLM结果 ∩ 规则结果 → 规则优先级更高
```

#### 约束输出如何影响下游

| 约束字段 | 类型 | 影响下游 |
|---------|------|---------|
| `category` | str | Qdrant chunk/product 搜索过滤 → 硬约束过滤 |
| `sub_category` | str | 同上，更细粒度 |
| `budget_max` | float | 检索价格过滤 → 评分 budget_fit 维度 (权重0.20) |
| `budget_min` | float | 检索价格过滤 |
| `scenario` | str | 评分 scenario_fit 维度 (权重0.05)，场景关键词匹配 |
| `must_tags` | list[str] | 硬约束：标题/描述必须包含 |
| `exclude_tags` | list[str] | 硬约束：标题/品牌匹配→排除 (支持品类映射"日系"→品牌列表) |

#### 闲聊快速路径

```
检测到 chitchat → intent="chitchat" → retrieval channels=[] → 跳过检索 → 直接 Response
节省: Embedding API调用 + Qdrant搜索 + Reranker调用
```

#### 答辩要点

> "Router 不是简单的 if-else，而是规则优先 + LLM增强的双层架构。规则保证基础可用性——即使 LLM API 完全不可用，用户说的'蓝牙耳机200以内'仍然能被正确解析为 category=数码电子, budget_max=200。LLM只是锦上添花，处理'想给女朋友买个不太贵的生日礼物'这类口语化表达。"

---

### 站点2：MemoryRetriever — 长期偏好记忆检索

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/workflow/graph.py:_node_router` L78-144 |
| **服务层** | `backend/app/services/memory_retriever.py` |
| **输入** | user_id, session_id, current_query, current_intent, current_constraints |
| **输出** | used_memories[], blocked_memories[], memory_trace |

#### 职责一句话

> 从用户长期行为中检索偏好记忆（品牌、品类、场景、避雷项），注入搜索增强和评分加成。

#### 三条影响路径

```
路径1: Query增强 (检索阶段)
  偏好品牌 "Sony" → 临时追加到搜索词 "蓝牙耳机 跑步 Sony"
  偏好场景 "通勤"  → 追加 "通勤"
  ⚠️ 检索完成后恢复原query (graph.py:186-189)

路径2: Preference Bonus (评分阶段)
  category偏好匹配 → +0.03 × confidence (上限控制在 0.03)
  brand偏好匹配    → +0.02 × confidence
  scenario偏好匹配 → +0.02 × confidence
  总加成上限: 0.07

路径3: Avoid Penalty (评分阶段)
  negative_preference "Sony" → 商品品牌含"Sony" → 扣0.05 × confidence
  总惩罚上限: 0.10
```

#### Query恢复机制 (关键细节)

```python
# graph.py:137-141 — 临时追加搜索词
if memory_hints:
    hint_str = " ".join(memory_hints[:3])
    state.user_query = f"{state.user_query} {hint_str}"
    state.user_query_original = state.user_query[:-(len(hint_str)+1)]

# graph.py:186-189 — 检索完成后恢复
if getattr(state, "user_query_original", None):
    state.user_query = state.user_query_original
```

为什么恢复？因为 Reranker、Response、后续追问都依赖原始 query，不能让"搜索增强词"污染这些环节。

#### 答辩要点

> "Memory不是简单的'记住用户喜欢什么品牌'然后硬过滤。它分三个粒度参与：检索时温和增强搜索词（不改变原始query）、评分时微小加成（最多0.07分）、避雷时直接惩罚。这种设计让记忆提供'偏好信号'而不是'硬约束'——用户说'推荐耳机'时，偏好Sony的商品排名稍高，但不排除其他品牌。"

---

### 站点3：LLM Query Rewrite — 口语→搜索关键词

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/agents/retrieval_agent.py:_llm_extract_keywords` L95-117 |
| **调用入口** | `retrieval_agent.py:_text_channel` L124 |
| **缓存** | Redis, TTL=30min, key=md5("rewrite|{user_query}") |
| **降级** | LLM失败 → 返回原query |

#### 职责一句话

> 将用户的自然语言购物表达转化为搜索引擎友好的关键词串。

#### 为什么需要改写？

```
用户输入:  "推荐一款200以内适合跑步的蓝牙耳机"
             ↓ Qwen LLM
改写输出:  "蓝牙耳机 跑步 运动 无线 200以内"

Embedding 直接编码口语 → 向量空间中 "推荐一款" 这类无用词也会参与余弦计算
Embedding 编码关键词 → 每个词都是高信号，匹配更精准
```

#### Redis 缓存策略

```python
cache_key = make_key("rewrite", user_query)  # → omnicart:rewrite:{md5}
return await cached(cache_key, REDIS_CACHE_TTL_REWRITE, _do_rewrite)  # TTL=30min
```

Trade-off：30分钟意味着同一query只调一次LLM（省钱），但用户改一个字就不会命中缓存。

#### 降级

```python
except Exception as e:
    logger.warning(f"LLM keyword extraction failed: {e}")
    return user_query  # 退回原始口语，后续 Embedding 直接编码
```

#### 答辩要点

> "改写不是必须的——它是一个'质量提升'环节而非'必要条件'。LLM 提取关键词可以让 Embedding 更聚焦于语义核心，但即使改写失败，原始口语也能被 Embedding 模型合理编码。关键是：失败不阻塞后续链路。"

---

### 站点4：Semantic Search — 核心检索（重点站）

| 属性 | 值 |
|------|-----|
| **TextRetriever** | `backend/app/retrieval/text_retriever.py` |
| **SemanticRetriever** | `backend/app/retrieval/semantic_retriever.py` |
| **Embedding** | Qwen text-embedding-v4, 1024维 |
| **向量库** | Qdrant (product_chunks collection, HNSW ANN) |
| **本地缓存** | product_chunk_embeddings.json (35.2MB, 1133 chunks) |
| **输入** | search_query, top_k, category, sub_category, price_max/min |
| **输出** | retrieved_products[] (含 matched_chunks + evidence_ids + rag_knowledge) |

#### 职责一句话

> 将搜索关键词转为1024维向量，在1133个商品chunk中找最相似的，聚合回产品级排名。

#### 4.1 为什么用 Chunk 级搜索？（答辩核心问题）

```
产品级搜索 (旧方案):
  商品: "Baseus Bowie E18 真无线蓝牙耳机，蓝牙5.3，续航5h，Type-C充电..."
  用户搜: "适合跑步"
  → 标题和描述中没出现"跑步" → 余弦相似度低 → 漏掉！❌

Chunk级搜索 (当前方案):
  同一商品被拆成4类chunk:
    - summary: "Baseus Bowie E18 真无线耳机 数码电子..."
    - mkt:     "蓝牙5.3，续航5h，Type-C充电..."
    - faq[0]:  "Q: 适合运动吗？ A: 支持IPX5防水，跑步健身都合适"  ← 精准命中！
    - faq[1]:  "Q: 降噪效果如何？ A: 通话降噪，地铁环境清晰..."
    - rev[0]:  "小明(5星): 音质好，跑步戴着不掉"
  
  → "跑步"匹配到 faq[0] 和 rev[0] → 余弦相似度高 → 成功召回！✅
```

**核心价值**：让细节匹配不被商品整体描述淹没。FAQ和用户评论往往包含最具体的场景关键词。

#### 4.2 完整检索执行流程

```
_search_chunk_impl (semantic_retriever.py:276-360)

Step 1: Embed Query
  embed("蓝牙耳机 跑步 运动 无线") → Qwen text-embedding-v4 → 1024维向量

Step 2: Chunk向量搜索 (检索 top_k×10 = 50 chunks)
  ├─ 优先: Qdrant HNSW ANN (product_chunks collection, 1133 chunks)
  │   └─ client.query_points(collection="product_chunks", query=vec, limit=50, with_payload=True)
  │      → 返回: [{product_id, chunk_id, chunk_type, score, payload: {text, ...}}, ...]
  │
  └─ 降级: 本地 product_chunk_embeddings.json
      └─ 暴力余弦相似度, 1133 chunks遍历, <10ms
         → payload.text 为空时 → _reconstruct_chunk_text() 从 product.rag_knowledge 重建

Step 3: 约束过滤
  category=数码电子, sub_category=真无线耳机, price_max=200
  → 过滤后可能从50 chunks减到20 chunks

Step 4: 约束过滤后空 → 降级产品级搜索
  if not chunk_hits:
      return await self._search_impl(...)  # 产品级Qdrant/本地搜索

Step 5: 按 product_id 分组
  chunk_groups = {"p_digital_026": [chunk1, chunk3, chunk7], "p_digital_007": [chunk2, chunk5], ...}

Step 6: Chunk聚合 → 产品排名
  _aggregate_chunks(chunk_groups, "max_score")
  对每个 product_id, 取其所有chunk的最高分作为产品得分
  → [(p_digital_026, 0.86), (p_digital_007, 0.79), ...]

Step 7: 构建产品结果
  for pid, agg_score in ranked_pids:
      product = repo.get_by_id(pid)
      result = _product_to_result(product, agg_score)
      result["matched_chunks"] = [...]  ← 附上匹配的chunk详情
      result["matched_chunk_count"] = len(matched_chunks)

Step 8: 补齐 (结果不足top_k)
  if len(results) < top_k:
      产品级搜索补齐 → 补齐的产品设 matched_chunks=[] (默认空)
```

#### 4.3 五级降级链

| 级别 | 搜索方式 | 数据量 | 速度 | 场景 |
|------|---------|--------|------|------|
| 1 | Qdrant product_chunks HNSW ANN | 1133 chunks | 最快 | 正常 |
| 2 | 本地 product_chunk_embeddings.json 暴力余弦 | 1133 chunks | ms级 | Qdrant不可用 |
| 3 | Qdrant products 产品级搜索 | 105 products | 快 | Chunk过滤后无结果 |
| 4 | 本地 product_embeddings.json 产品级暴力 | 105 products | ms级 | Qdrant不可用+Chunk无结果 |
| 5 | filter_by + 关键词子串匹配 | 105 products | ms级 | Embedding API不可用 |

```
Qdrant product_chunks (1133 chunks, HNSW ANN, 余弦相似度)
  ↓ Qdrant不可用/collection不存在
本地 product_chunk_embeddings.json (35.2MB, 暴力余弦)
  ↓ 约束过滤后无结果 (Bug 4修复: 不再静默失败)
Qdrant products (105 products, 产品级向量搜索)
  ↓ 失败
本地 product_embeddings.json (3.5MB, 产品级暴力搜索)
  ↓ 无结果
filter_by + 子串匹配 (不用向量, 纯关键词文本匹配)
  ↓
至少返回空列表 + 兜底话术
```

#### 4.4 Chunk 聚合权重

```python
# semantic_retriever.py:460
# Chunk权重: summary(商品核心信息)和faq(精准匹配用户疑问)最高,
# mkt(营销描述,有夸张可能)次之, rev(用户评论,噪音多情感偏差大)最低
_WEIGHTS = {"summary": 1.0, "mkt": 0.9, "faq": 1.0, "rev": 0.8}
```

| Chunk类型 | 数量 | 内容 | 权重 | 为什么 |
|-----------|------|------|------|--------|
| summary | 105 | 商品标题+品牌+品类+描述摘要(200字) | 1.0 | 商品核心信息，权威性最高 |
| faq | 454 | Q: 敏感肌能用吗？ A: ... | 1.0 | 精准匹配用户疑问，与1.0同权 |
| mkt | 105 | 营销描述全文 | 0.9 | 信息丰富但含营销话术，略降权 |
| rev | 469 | 用户评论原文 | 0.8 | 真实反馈但噪音多、情感偏差大 |

**权重演变历史**：旧版 `faq=0.6, rev=0.4` → 发现FAQ/评论无法合理影响产品排名 → Bug修复为 `faq=1.0, rev=0.8`。

#### 4.5 _product_to_result — 证据ID组装

```python
# semantic_retriever.py:483-504
def _product_to_result(product, score):
    evidence_ids = [f"E-MKT-{product.product_id}-0"]     # 营销证据 (每商品1条)
    for i in range(len(product.rag_knowledge.official_faq)):
        evidence_ids.append(f"POL-{product.product_id}-{i}")  # FAQ证据
    for i in range(len(product.rag_knowledge.user_reviews)):
        evidence_ids.append(f"R-{product.product_id}-{i}")    # 评论证据
    return {
        "product_id": ..., "title": ..., "score": score,
        "evidence_ids": evidence_ids,
        "matched_chunks": ...,  # 仅 chunk 搜索路径有
    }
```

#### 4.6 本地降级时的Chunk原文重建 (O5.1优化)

```python
# semantic_retriever.py — _reconstruct_chunk_text()
# 本地 product_chunk_embeddings.json 只存向量+元数据，不存chunk原文
# 当Qdrant不可用时，从已加载的 product.rag_knowledge 重建原文:
#
#   summary → f"{title} {brand} {category} {sub_category} {mkt_desc[:200]}"
#   mkt     → marketing_description[:300]
#   faq     → f"Q: {faq.question} A: {faq.answer}"
#   rev     → f"[{rev.nickname}][{rev.rating}星] {rev.content}"
```

#### 答辩要点

> "Chunk级检索是这个系统区别于传统电商搜索的核心差异化设计。传统搜索用产品标题+描述做向量化——粒度太粗，细节信号被淹没。我们把每个商品拆成平均10.8个chunk，每个chunk是一个独立语义单元——一条FAQ、一条评论、一段营销描述。用户搜'适合敏感肌'，能直接命中某个面霜FAQ中的'本产品经皮肤科测试，适合敏感肌使用'，而不是靠产品标题中模糊的'温和不刺激'。"

> "五级降级不是过度设计。比赛中环境不稳定——API可能超额、Qdrant可能OOM、本地文件可能被误删。每一级降级都有明确的触发条件和fallback，确保在任何情况下都能返回结果。"

---

### 站点5：Review/Policy Mining — 并行证据提取

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/agents/retrieval_agent.py` |
| **_review_channel** | L187-221 |
| **_policy_channel** | L223-250 |
| **_evidence_content_for_id** | L344-388 |
| **并发方式** | ThreadPoolExecutor(max_workers=2) |
| **输入** | state.retrieved_products (商品列表, 含 rag_knowledge) |
| **输出** | evidence_list[] (结构化证据, 含 content + confidence + source_type) |

#### 职责一句话

> 从检索到的商品中提取结构化的评论证据和FAQ证据，双通道并行执行。

#### 5.1 Review Channel — 评论分级

```python
# retrieval_agent.py:187-221
for item in state.retrieved_products:
    for i, review in enumerate(product.rag_knowledge.user_reviews):
        rating = review.rating  # 1-5星
        
        if rating <= 2:
            source_type = "review_risk"
            confidence = 0.8 if rating == 1 else 0.5  # 1星比2星更确信是差评
        elif rating == 3:
            source_type = "review_neutral"
            confidence = 0.4  # 3星中性评价, 信号弱
        else:  # rating >= 4
            source_type = "review_positive"
            confidence = 0.7  # 好评
            
        evidence_id = f"R-{pid}-{i}"
        content = f"[{nickname}][{rating}星] {review_content[:150]}"
```

**confidence 设计逻辑**：
- 1星差评 → 0.8：极低评分，强烈的负面信号
- 2星差评 → 0.5：不太满意但非致命，中等负面信号
- 3星中评 → 0.4：中性信号，权重最低
- 4-5星好评 → 0.7：正面但不如极差评确信（好评可能是刷的）

#### 5.2 Policy Channel — FAQ提取

```python
# retrieval_agent.py:223-250
for item in state.retrieved_products[:3]:  # 只取TOP3
    for i, faq in enumerate(product.rag_knowledge.official_faq):
        evidence_id = f"POL-{pid}-{i}"
        source_type = "policy_faq"
        confidence = 0.9  # 官方FAQ可信度最高
        content = f"Q: {question[:100]} A: {answer[:150]}"
```

**演变 (Bug 6修复)**：旧版按关键词过滤FAQ → 过滤逻辑有bug导致大量FAQ被误删 → 修复为保留全部FAQ。

#### 5.3 Text Channel 避免重复

```python
# retrieval_agent.py:173
for eid in item.get("evidence_ids", []):
    if eid.startswith("R-"):
        continue  # R-* 评论证据由 review_channel 负责
    # text_channel 只处理 E-MKT-* 和 POL-*
```

#### 5.4 Evidence ID 体系统一

```
证据来源           ID格式              示例                    confidence
──────────────────────────────────────────────────────────────────
营销描述           E-MKT-{pid}-0       E-MKT-p_beauty_001-0   由检索分计算
FAQ                POL-{pid}-{i}       POL-p_beauty_001-0     0.9
用户评论(好评)      R-{pid}-{i}         R-p_beauty_001-0       0.7
用户评论(中评)      R-{pid}-{i}         R-p_beauty_001-1       0.4
用户评论(差评)      R-{pid}-{i}         R-p_beauty_001-2       0.5/0.8
补充证据            E-SUPP-{pid}       E-SUPP-p_beauty_023    语义相似度

已废弃:
  E-KW-{pid}        ❌ 旧版关键词合成证据, Bug 3-1 已删除
  R-POS-{pid}-{i}   ❌ 旧版好评专用ID, Bug 2 统一为 R-*
```

#### 答辩要点

> "证据提取不是简单地把所有数据扔给前端。review_channel 根据评分分级并设定不同的置信度——1星差评比2星更确信(0.8 vs 0.5)，官方FAQ比用户评论更可信(0.9 vs 0.7)。这些置信度最终进入评分体系，影响 evidence_confidence 计算和推荐等级判定。"

---

### 站点6：Supplementary Evidence Search — 反向发现

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/agents/retrieval_agent.py:_supplementary_evidence_search` L252-367 |
| **触发条件** | 主 text 检索结果 < 3件 |
| **搜索范围** | 本地 chunk 缓存中 faq/rev 类型 chunk (923 chunks) |
| **搜索方式** | Embedding余弦相似度 > 关键词子串匹配(降级) |

#### 职责一句话

> 当主检索结果不足时，从FAQ和评论chunk中反向搜索，发现title/描述中不含关键词但实际上相关的商品。

#### 为什么需要反向发现？

```
用户搜: "适合飞机上用的充电宝"
  
主检索 (title+描述):
  商品A: "20000mAh大容量移动电源，支持PD快充" → 没有"飞机" → 漏掉 ❌

补充搜索 (FAQ chunk):
  商品A的FAQ: "Q: 能带上飞机吗？ A: 符合航空标准，100Wh以下可登机，无需申报"
  → Embedding 余弦相似度匹配 "飞机"+"充电宝" → 命中！✅
```

#### 搜索方式 (O7.1 语义化优化)

```python
# V2: 优先 Embedding 余弦相似度 (解决中文"飞机"≠"航空"的匹配问题)
try:
    query_vec = gateway.embed([query], "text_embedding")[0]
    for chunk in evidence_chunks:
        sim = cosine_similarity(query_vec, chunk.embedding)
        if sim > 0.35:  # 最低相似度阈值, 过滤噪音
            matched_pids[pid] = max(matched_pids[pid], sim)
except:
    # 降级: 关键词子串匹配 (兼容无Embedding环境)
    for chunk in evidence_chunks:
        score = sum(1 for w in query_words if w in chunk_text)
```

#### 答辩要点

> "补充搜索解决了一个实际痛点：商品标题和营销描述往往不会覆盖所有用户关心的场景关键词。'能带上飞机吗'这类信息藏在FAQ里，'跑步戴着不掉'藏在用户评论里。反向发现利用chunk级别的细粒度信息发现这些隐性匹配。"

---

### 站点7：Qwen Reranker — 语义精排

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/workflow/graph.py:_node_reranker` L194-274 |
| **调用条件** | len(products) > 1 |
| **模型** | qwen3-rerank (Cross-Encoder) |
| **降级** | 异常静默 → 保持原排序 |

#### 职责一句话

> 使用 Cross-Encoder 模型对检索结果进行语义重排序，比 Embedding 的余弦相似度更精准。

#### Embedding vs Reranker（高频面试题）

```
                    Embedding (Bi-Encoder)          Reranker (Cross-Encoder)
                    ─────────────────────           ──────────────────────
架构:               query→编码, doc→编码             query+doc → 联合编码
                    各自独立计算向量                  同时输入，交叉注意力
                    
相似度计算:         余弦(query_vec, doc_vec)         直接输出相关性分数 [0,1]

速度:               极快 (向量已预计算)               较慢 (每次重新编码)
                    1133 chunks < 10ms              10 documents ~ 200ms

精度:               中等 (信息压缩到向量)              高 (原始文本交互)

用在:               粗筛: 1133→TOP30 chunks          精排: TOP10→最终排序
```

**一句话**：Embedding是"先记住所有人的脸，再比对"，Reranker是"把两个人拉到一起当面比较"。

#### 文档构建 (O8.1优化后)

```python
# graph.py:202-238 — 为每个候选商品构建一篇文章
document = (
    f"{title} {category} {sub_category}"           # 商品基本信息
    + f" {description[:300]}"                       # 描述摘要
    + f" {marketing_description[:300]}"             # 营销描述
    + f" {faq[0].question[:150]} {faq[0].answer[:300]}"  # FAQ 1
    + f" {faq[1].question[:150]} {faq[1].answer[:300]}"  # FAQ 2
    + f" 用户评价: {review[0].content[:200]}"        # 评论 1
    + f" 用户评价: {review[1].content[:200]}"        # 评论 2
    + f" {evidence_snippets}"                        # 已提取的证据片段
)
```

**优化历程**：
- 旧版：只传 title+category+description → Bug 9：不含FAQ/评论/证据
- Bug 9修复：加入 rag_knowledge + evidence snippets，但重度截断 (FAQ答案120字)
- O8.1优化：截断阈值提升 (FAQ答案120→300, 评论100→200, 描述200→300)

#### 分数写回

```python
# graph.py:254-256
for idx, p in enumerate(products):
    p["reranker_score"] = index_map.get(idx, 0.0)
    p["relevance_score"] = p["reranker_score"]  # 别名, 供 Decision 使用
```

Reranker分数在 Decision 阶段被优先使用：`compute_rag_relevance()` 优先取 `reranker_score`。

#### 失败降级

```python
except Exception as e:
    logger.debug(f"Reranker unavailable, keeping original order: {e}")
    # 静默保持原排序, 不阻塞后续流程
```

#### 答辩要点

> "Reranker 和 Embedding 解决的是不同阶段的问题。Embedding 负责从1133个chunk中快速粗筛TOP30——这个阶段追求'快且广'。Reranker 对TOP10做交叉编码精排——追求'准'。两者配合，既有向量搜索的速度，又有语义匹配的精度。"

---

### 站点8：Evidence Check — 证据充足性验证

| 属性 | 值 |
|------|-----|
| **代码位置** | `backend/app/verification/evidence_checker.py` |
| **调用入口** | `backend/app/workflow/graph.py:_node_evidence_check` L306-322 |
| **执行时机** | Reranker之后、Decision之前 |

#### 职责一句话

> 检查当前检索到的证据类型是否足以支撑推荐结论，不足时降低整体推荐置信度。

#### 不同 Intent 的证据要求

```python
MIN_EVIDENCE_TYPES = {
    "recommend":            {"text_retrieval", "review_positive"},  # 至少要有商品文本+好评
    "risk_check":           {"review_risk"},                        # 必须有差评数据
    "compare":              {"text_retrieval", "review_positive"},  # 对比需要双方数据
    "compatibility_check":  {"policy_faq"},                         # 兼容性必须有FAQ
    "alternative":          {"text_retrieval"},                     # 替代品最低要求
}
```

#### 不足时的降级机制

```python
# evidence_checker.py:38-43
if missing:
    report["sufficient"] = False
    # → Decision Agent 读取 sufficiency_report["sufficient"]
    # → 为 False 时, 所有商品推荐最高不超过 "cautious" (0.70分)
    # → 防止在证据不足时给出"强烈推荐"的结论
```

#### 答辩要点

> "这个检查是一个安全阀。试想用户搜'这款面霜会过敏吗'——如果检索只返回了营销描述、没有任何用户差评或风险FAQ，我们不能说'强烈推荐'。Evidence Check 发现缺少 review_risk 证据 → 全局降级 → 所有商品的推荐等级上限为 cautious，即使评分很高也不允许 strongly_recommend。"

---

### 站点9：Decision Agent — 证据驱动9维评分

| 属性 | 值 |
|------|-----|
| **编排层** | `backend/app/agents/decision_agent.py` L42-181 |
| **主评分引擎** | `backend/app/decision/scoring.py` |
| **证据指标** | `backend/app/decision/evidence_metrics.py` |
| **评分版本** | evidence_scoring_v1 |
| **LLM参与** | 默认关闭 (ENABLE_DECISION_LLM=false) |

#### 职责一句话

> 对每个候选商品进行9维评分，综合证据置信度输出5级推荐等级。

#### 9.1 Decision Agent 执行流程

```
Step 1: EvidenceScoringHelper.build_profiles(evidence_list, products)
  → 按 product_id 聚合 evidence → ProductEvidenceProfile

Step 2: (可选) LLM Evaluator — 默认禁用

Step 3: 读取 sufficiency_report["sufficient"] → 全局证据充足标志

Step 4: 遍历每个 candidate product:
  ├─ 重建 Product 对象 (from dict)
  ├─ 硬约束检查 → 不通过 → not_recommended
  ├─ compute_rag_relevance(item, profile) → rag_rel (RAG相关度)
  ├─ compute_metrics(pid, profile, ...) → EvidenceMetrics
  └─ score_with_evidence(...) → DecisionResult

Step 5: 按 final_score 降序排序
```

#### 9.2 9维评分公式

```python
# scoring.py:153-163
raw = (
    0.45 × relevance          ← RAG语义相关度 (Reranker > 检索分 > 关键词)
  + 0.20 × budget_fit         ← 价格与预算的匹配度
  + 0.12 × user_sat           ← 用户评论均分/5 (评论数不再加成)
  + 0.10 × value_score        ← 同品类性价比分位 × 品类品质系数
  + 0.08 × spec_quality       ← 技术规格关键词命中
  + 0.05 × scenario_fit       ← 场景关键词命中
  + preference_bonus          ← 长期偏好匹配加成 (max 0.07)
  - risk_penalty              ← 差评风险扣分 (max 0.30)
  - avoid_penalty             ← 避雷项惩罚 (max 0.10)
)

final_score = clamp(raw, 0.0, 1.0)
display_score = round(final_score × 10, 1)  # 0.0 ~ 10.0
```

#### 9.3 各维度详解

| 维度 | 权重 | 方法 | 简介 |
|------|------|------|------|
| **relevance** | 0.45 | `compute_rag_relevance()` | 优先取Reranker分→检索分→关键词兜底。对数映射归一化到[0,1] |
| **budget_fit** | 0.20 | `_calc_budget_fit()` | 无约束默认0.92；未超预算按比例0.88-0.98；超预算0.75-0.40 |
| **user_sat** | 0.12 | `_calc_user_satisfaction()` | 评论均分/5映射。1-2条评论做平滑回归(向0.65均值回归)，评论数不再加成 |
| **value_score** | 0.10 | `_calc_value_score()` | 0.5×品质分+0.5×价格分，乘以品类品质系数。低价品类(充电宝1.3)比高价品类(手机0.9)更容易拿高分 |
| **spec_quality** | 0.08 | `_calc_spec_quality()` | 品类专属技术关键词命中数。耳机检测ANC/LDAC/aptX等，手机检测OIS/120Hz/IP68等 |
| **scenario_fit** | 0.05 | `_calc_scenario_fit()` | 场景关键词匹配。query词1倍权重，场景专属词2倍权重。flight场景检测"航空/安检/登机/100wh" |
| **preference_bonus** | +max0.07 | 记忆匹配 | 品类偏好+0.03×conf, 品牌偏好+0.02×conf, 场景偏好+0.02×conf |
| **risk_penalty** | -max0.30 | 差评扣分 | ≥3条差评扣0.15, ≥1条扣0.05; 均分<3.0追加0.10, <3.5追加0.03 |
| **avoid_penalty** | -max0.10 | 避雷惩罚 | 负面偏好匹配到商品标题/品牌 → 0.05×conf |

#### 9.4 RAG 相关度的取值优先级

```python
# evidence_metrics.py:206-234
优先级1: product["reranker_score"]    ← Qwen Reranker 精排分数 (最优先)
优先级2: product["relevance_score"]    ← 同上（别名）
优先级3: profile.max_rerank_score      ← EvidenceProfile 聚合的最高 rerank 分
优先级4: product["score"]              ← 检索原始分 (Qdrant/本地余弦)
优先级5: product["retrieval_score"]    ← 检索分（别名）
优先级6: profile.avg_retrieval_score   ← EvidenceProfile 的平均检索分
优先级7: 无 → 0.0 (不再下钻到关键词兜底, V4改进)
```

#### 9.5 推荐等级5级判定树

```python
# scoring.py:260-287
if hard_constraint_failed:
    → "not_recommended"

if evidence_confidence < 0.35:
    → "insufficient_evidence"

if global_evidence_sufficient == False:
    → max "cautious" (所有商品降级, 不允许 strongly_recommend/recommended)

if risk_penalty >= 0.25:
    → "cautious"

if final_score >= 0.85 AND ev_conf >= 0.75 AND risk < 0.10:
    → "strong_recommend"

if final_score >= 0.70:
    → "recommended"

if final_score >= 0.55:
    → "cautious"

else:
    → "not_recommended"
```

| 等级 | display_score | 前端颜色 | 条件 |
|------|-------------|---------|------|
| strongly_recommend | 8.5-10 | 绿色 | 评分高+证据足+风险低 |
| recommended | 7.0-8.5 | 蓝色 | 评分较高+证据支撑 |
| cautious | 5.5-7.0 | 黄色 | 有风险或证据不足，分数上限0.70 |
| insufficient_evidence | 0-5.0 | 灰色 | 证据太少，分数上限0.50 |
| not_recommended | 0-4.5 | 红色 | 硬约束失败或评分极低，分数上限0.45 |

#### 9.6 硬约束过滤

```python
# decision_agent.py:197-238
# 不通过则强制 not_recommended:
1. 价格 > budget_max × 2          → 超过预算2倍直接过滤
2. category 精确匹配               → 品类不对直接过滤  
3. must_tags: 标题/描述必须包含    → "必须带降噪" → 标题不含"降噪"→过滤
4. exclude_tags: 标题/品牌不能含  → 支持品类映射 "日系"→[资生堂,SK-II,...]
   └─ 内容级排除: 检查否定语境, "不含酒精" 中的 "酒精" 不算排除
```

#### 9.7 Confidence Cap

```python
# scoring.py:290-297 — 推荐等级限制最终分数上限
not_recommended       → min(final, 0.45)
insufficient_evidence → min(final, 0.50)
cautious              → min(final, 0.70)
recommended / strong  → 无限制
```

#### 答辩要点

> "评分的核心设计是去LLM化。9个维度全部是确定性规则计算，同一输入永远得到同一分数。权重不是拍脑袋定的——relevance占45%因为语义匹配是最重要的信号，budget_fit占20%因为价格是电商第一决策因子，risk_penalty可以扣到0.30因为差评是强烈负面信号。每个维度的计算方法都有明确的业务逻辑可解释。"

> "5级推荐不是简单的高于0.7就是推荐。判定树同时考虑三个因素：final_score（评分本身）、evidence_confidence（证据是否有说服力）、risk_penalty（风险程度）。即使评分高达0.85，如果证据置信度<0.75或有风险≥0.10，也拿不到strongly_recommend。"

---

## 三、完整数据流轨迹

以下追踪一个完整的请求实例：从用户输入到最终推荐结果。

### Step 1: 用户输入
```
用户: "推荐一款200以内的蓝牙耳机，通勤用"
```

### Step 2: FollowUpEngine (Workflow前)
```
首次请求 → is_follow_up=False → 不追加 context_prompt
enriched_query = "推荐一款200以内的蓝牙耳机，通勤用"
```

### Step 3: RouterAgent → 约束提取
```python
intent = "recommend"
constraints = Constraints(
    category="数码电子",
    sub_category="真无线耳机",
    budget_max=200.0,
    scenario="commute",
    must_tags=[],
    exclude_tags=[],
)
retrieval_plan = RetrievalPlan(
    channels=["text", "review", "policy"],
    top_k=5,
    priority="balanced",
)
```

### Step 4: MemoryRetriever
```
首次用户 → 无长期记忆 → used_memories=[], blocked_memories=[]
→ 不追加搜索词
```

### Step 5: LLM Query Rewrite
```
"推荐一款200以内的蓝牙耳机，通勤用"
  ↓ Qwen LLM
"蓝牙耳机 通勤 降噪 200以内"
  ↓ Redis 缓存 (首次 miss, 写入缓存)
```

### Step 6: Semantic Search
```
embed("蓝牙耳机 通勤 降噪 200以内") → 1024维向量

Qdrant HNSW ANN (product_chunks, 1133 chunks) → TOP 30 chunks

约束过滤: category=数码电子, price_max=200
  → 剩余 18 chunks, 覆盖 8 个产品

按 product_id 分组 → max_score 聚合:
  p_digital_026: 0.86 (faq chunk "Q: 降噪效果如何？A: 40dB主动降噪...")
  p_digital_027: 0.72 (mkt chunk "小米Redmi Buds 6...AI通话降噪...")
  p_digital_030: 0.68 (summary chunk)
  p_digital_007: 0.61 (rev chunk "小明(5星): 通勤用很合适...")
  p_digital_018: 0.55 (faq chunk)

→ retrieved_products = [p_digital_026, p_digital_027, p_digital_030, p_digital_007, p_digital_018]
  (每个含 matched_chunks + evidence_ids + rag_knowledge)
```

### Step 7: Review/Policy Mining (并行)
```
_review_channel (Thread-1):
  p_digital_026: rating=5→review_positive(R-026-0), rating=4→review_positive(R-026-1)
  p_digital_027: rating=2→review_risk(R-027-0,conf=0.5), rating=5→review_positive(R-027-1)
  ...

_policy_channel (Thread-2, TOP3):
  p_digital_026: Q:降噪效果？→POL-026-0, Q:适合运动？→POL-026-1
  ...

→ evidence_list = [E-MKT-026-0, ..., R-026-0, R-026-1, ..., POL-026-0, ...]
  共约20条证据
```

### Step 8: Supplementary Search
```
len(products)=5 ≥ 3 → 不触发
```

### Step 9: Qwen Reranker
```
构建5篇document (title+desc+mkt+FAQ+review+evidence snippets)

gateway.rerank(query="蓝牙耳机 通勤 降噪 200以内", documents, top_n=5)
  → relevance_scores: [0.813, 0.672, 0.704, 0.591, 0.523]

写回: p["reranker_score"] = relevance_score
重排: products 按 reranker_score 降序
```

### Step 10: Evidence Check
```
evidence_types = {"text_retrieval", "review_positive", "review_risk", "policy_faq"}
required (recommend): {"text_retrieval", "review_positive"}
missing: set() → sufficient=True  (假设都有)
```

### Step 11: Decision Agent → 评分
```
以 p_digital_026 为例:

compute_rag_relevance: reranker_score=0.813 → normalize(0.813)=0.813
relevance = 0.813

_budget_fit: price=199, budget=200, ratio=99.5% → 0.88
_user_sat: reviews=[5,4,5,4], avg=4.5, 4条评论无回归 → 4.5/5=0.90
_value_score: median=800, price=199 < 400 → price_score=0.95; quality=0.95 → 1.1×(0.5×0.95+0.5×0.95)=1.045→clamp=1.0
_spec_quality: 匹配"主动降噪"/"低延迟"/"长续航"/"快充"=4hits → 0.60+4×0.07=0.88
_scenario_fit: "降噪"/"通勤"/"蓝牙"→3hits, 场景词"通勤"×2=2 → total=5hits → 0.55+5×0.10=1.0→clamp=1.0

risk_penalty: 无差评 → 0.0
preference_bonus: 无偏好记忆 → 0.0
avoid_penalty: 无避雷 → 0.0

raw = 0.45×0.813 + 0.20×0.88 + 0.12×0.90 + 0.10×1.0 + 0.08×0.88 + 0.05×1.0
    = 0.366 + 0.176 + 0.108 + 0.100 + 0.070 + 0.050
    = 0.870

ev_conf = 0.25×0.813 + 0.20×1.0 + 0.20×0.75 + 0.15×0.78 + 0.10×0.75 + 0.10×0.90
        = 0.203 + 0.20 + 0.15 + 0.117 + 0.075 + 0.09
        = 0.835

推荐等级: final≥0.85, ev_conf≥0.75, risk<0.10 → "strong_recommend"
display_score = 0.870 × 10 = 8.7
```

### Step 12: Response → Guard → 返回
```json
{
  "answer": "根据您的需求，为您找到以下商品：\n\n1. [数码电子/真无线耳机] ...",
  "products": [{...}],
  "decision_results": [{
    "product_id": "p_digital_026",
    "final_score": 0.870,
    "display_score": 8.7,
    "recommendation_level": "strong_recommend",
    "evidence_confidence": 0.835,
    "component_scores": {
      "relevance": {"score": 0.813, "weight": 0.45, "method": "reranker_score"},
      "budget_fit": {"score": 0.88, "weight": 0.20, "method": "structured_price_rule"},
      ...
    }
  }]
}
```

---

## 四、答辩 / 面试常见问题

### Q1: 为什么用 Chunk 级搜索而不是产品级？

> **一句话**：产品级粒度太粗，细节信号被整体描述淹没。
>
> 产品级搜索把整个商品的 title+description 编码为一个向量。用户搜"适合跑步的蓝牙耳机"，如果商品的营销描述侧重"音质/降噪/续航"而没提"跑步"，就会漏掉。但同一件商品的 FAQ chunk 中可能包含"Q: 适合运动吗？A: IPX5防水，跑步健身都合适"——这个精准匹配在产品级搜索中会被平均化掉。
>
> Chunk级搜索把105件商品拆成1133个独立语义单元（summary/mkt/faq/rev），每个单元聚焦一个信息点。用户query匹配到FAQ中的"跑步"就能召回商品，不依赖标题中是否有这个词。

### Q2: LLM 挂了怎么办？

> **一句话**：整个系统有完整的非LLM降级路径。
>
> - Router: 规则解析 `_rule_based_parse()` 100%可靠，不依赖LLM
> - Query Rewrite: 失败返回原query，Embedding直接编码口语
> - Decision Scoring: 默认关闭LLM Evaluator，9维评分全部规则计算
>
> LLM在整个链路中只用于"质量提升"——改写让搜索更精准、意图让约束更准确。但每处LLM调用都有 `try-except` + 降级方案，不存在"LLM挂了系统就不能用"的情况。

### Q3: Embedding 和 Reranker 有什么区别？为什么两个都要？

> **一句话**：Embedding是粗筛（快但粗），Reranker是精排（慢但准）。
>
> **架构区别**：Embedding使用Bi-Encoder（双塔），query和document各自独立编码为向量，用余弦距离算相似度。Reranker使用Cross-Encoder（交叉编码），将query和document同时输入模型，通过交叉注意力计算相关性。
>
> **为什么两个都要**：Embedding可以在毫秒级搜索1133个chunk（向量预计算+ANN索引），但没有Cross-Encoder精准。Reranker精度高但每次都要重新编码query+document对，1133次太慢。实际做法是Embedding粗筛TOP30→Reranker精排TOP10。两者配合兼顾速度和精度。

### Q4: 怎么保证推荐不是"AI瞎编的"？

> **一句话**：所有推荐结论绑定 evidence_id，可追溯到具体证据源。
>
> 每条推荐都有 `support_evidence_ids` 字段，指向具体的营销描述(E-MKT-*)、官方FAQ(POL-*)、用户评论(R-*)。前端可以展示："推荐理由：用户小明(5星)评价'音质好续航长'+ 官方FAQ确认'支持IPX5防水适合运动'"。`component_scores` 中每个评分维度也标注了计算方法和使用的证据ID。整个推荐是可解释、可追溯、可审计的。

### Q5: 如果检索完全为空怎么处理？

> **一句话**：五级降级 + 补充证据搜索 + 兜底话术。
>
> 第一道防线：补充证据搜索（站点6）在主结果<3时反向发现遗漏商品。第二道防线：五级降级链确保在任何条件下都能执行搜索（直到最后一关：纯文本子串匹配）。第三道防线：如果最终结果为空，Response Agent 返回兜底话术"抱歉，暂时无法回答您的问题"，不会白屏或报错。

### Q6: 追问是怎么处理的？比如用户说"便宜一点的"

> **一句话**：FollowUpEngine 在 Workflow 前统一检测7种追问模式。
>
> "便宜一点"触发 vague_followup 模式：检测到追问词"便宜"且没有新品类词 → 继承上一轮的 category/scenario，设置预算倾向。继承的约束作为 `updated_constraints` 传入 WorkflowState，影响 Router 的约束抽取和后续检索的过滤条件。整个检测通过 PG context_snapshot（上轮product_ids）和 PreferenceMemory（session累积约束）获取上下文。

### Q7: 为什么评分是9维？权重怎么定的？

> **一句话**：每个维度对应一个用户购物决策的真实考量因素。
>
> - relevance(0.45)：语义匹配度——"这个东西跟我搜的是不是一回事"
> - budget_fit(0.20)：价格——电商第一决策因子
> - user_sat(0.12)：用户口碑——别人说好才是真的好
> - value_score(0.10)：性价比——同品类中买得值不值
> - spec_quality(0.08)：技术规格——硬件配置好不好
> - scenario_fit(0.05)：场景适配——适不适合我的使用场景
> - risk_penalty(减分, max0.30)：差评——踩雷的代价
> - preference_bonus/memory(加分,max0.07)：个人偏好——品牌忠诚等
> - avoid_penalty(减分, max0.10)：避雷——明确不想要的

> 权重反映信息密度和决策重要性：语义匹配是基石占45%，价格是电商第一决策占20%，场景适配是锦上添花占5%。

### Q8: 长期记忆怎么工作？会不会过度个性化？

> **一句话**：记忆提供"偏好信号"而非"硬约束"，通过三条路径温和参与。
>
> 路径1：搜索增强——偏好词追加到搜索词（检索后恢复原query，不污染下游）。路径2：评分加成——微小加分（最大仅0.07）。路径3：避雷惩罚——明确不喜欢的品牌扣分（最大0.10）。三条路径都是"调整权重"而非"硬排除"。用户说"推荐耳机"，偏好Sony的商品排名稍高，但不排除其他品牌。这种设计避免"茧房效应"。

---

## 五、RAG 评价体系：当前实现与未来优化

### 5.1 当前实现状态

**核心指标**：10站链路全部打通，V1 workflow 稳定运行，全链路降级验证通过。

**代码质量**：
- 每个站点有明确的单一职责和清晰的输入/输出
- 异常处理覆盖所有外部依赖（LLM/Embedding/Qdrant/Reranker/Redis）
- 无单点故障：任一外部服务不可用时降级到规则或文本匹配

**证据驱动能力**：
- 所有推荐结论绑定 evidence_id（E-MKT/POL/R/E-SUPP 四种类型统一格式）
- 评分维度记录计算方法和使用的证据ID
- 可追溯到具体FAQ问答或用户评论原文

**可观测性**：
- trace_steps 记录每站执行状态和耗时
- timing 记录各节点耗时(router_ms, retrieval_ms, rerank_ms, decision_ms...)
- Redis 缓存命中率统计

### 5.2 历史优化记录

| 轮次 | 日期 | 发现 | 修复 | 关键改进 |
|:--:|------|:--:|:--:|------|
| 1 | V2 | 6 | 6 | Evidence ID体系统一, 合成ID(E-KW-*)清除 |
| 2 | V2 | 4 | 4 | 追问上下文统一, Router约束继承修复 |
| 3 | V3 | 3 | 1 | TextRetriever E-MKT格式统一 |
| 4 | V3 | 4 | 3 | Chunk聚合权重合理化, Reranker输入增强 |
| 5 | 2026-06-02 | 4 | 4 | 本地chunk原文重建, Reranker截断优化, 补充搜索语义化 |

**第五轮优化详情 (2026-06-02)**：

| # | 位置 | 内容 | 效果 |
|:--:|------|------|------|
| O5.1 | `semantic_retriever.py` | 本地降级时从product.rag_knowledge重建chunk原文 | 降级场景evidence可读 |
| O5.2 | `semantic_retriever.py:460` | chunk权重配置加注释 | 可维护性提升 |
| O8.1 | `graph.py:209-233` | Reranker截断阈值提升(80→150/120→300/100→200) | Reranker语义信息更完整 |
| O7.1 | `retrieval_agent.py:256-325` | 补充证据搜索从关键词→Embedding余弦相似度 | 中文语义匹配更精准 |

### 5.3 未来优化方向

#### 短期 (提升检索质量)

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P0 | hybrid_search 接入主链路 | `text_retriever.py:hybrid_search` 已实现完整的语义+向量+RRF融合，128行代码从未调用，接入后可直接提升检索召回率 |
| P1 | Reranker 传完整原文 | 当前仍有截断（300字符），完全移除截断让Reranker基于完整FAQ/评论做判断 |
| P1 | 补充搜索触发阈值可配 | 当前固定<3触发，应根据品类商品密度动态调整 |

#### 中期 (扩展检索能力)

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P2 | 多模态Chunk | 商品图片也做chunk级索引（外观特征/包装细节/实拍图），支持以图搜图 + 图文联合搜索 |
| P2 | 跨品类对比检索 | 当前仅在一个category内搜索，用户说"跑步鞋和跑步耳机哪个更值得买"需要跨品类 |
| P2 | Chunk去重与质量过滤 | 1133 chunks中存在相似度高的重复FAQ，去重可以提升检索效率 |

#### 长期 (智能化)

| 优先级 | 方向 | 说明 |
|--------|------|------|
| P3 | 动态权重学习 | 当前chunk权重(1.0/0.9/1.0/0.8)和评分权重(0.45/0.20/...)均为人工设定。可通过用户行为反馈（点击/加购/下单）学习最优权重 |
| P3 | Query改写质量评估 | 当前无法评估改写后的关键词是否比原query更好。可以对比改写前后的检索结果质量做A/B |
| P3 | Evidence冲突检测 | 当一条FAQ说"适合敏感肌"但多条评论说"用了过敏"，需要检测evidence冲突并降置信度 |

---

## 附录：关键文件索引

| 文件 | 角色 | 所属站点 |
|------|------|:--:|
| `backend/app/services/followup_engine.py` | 追问检测引擎 (7模式) | 0 |
| `backend/app/services/context_builder.py` | 旧追问检测 (已废弃, 被FollowUpEngine替代) | 0 |
| `backend/app/api/agent_stream.py` | SSE流式入口 + FollowUpEngine调用 | 0 |
| `backend/app/agents/router_agent.py` | 意图识别 + 约束抽取 (规则+LLM双层) | 1 |
| `backend/app/decision/rules.py` | 规则解析 (detect_category/budget/scenario等) | 1 |
| `backend/app/workflow/graph.py` | LangGraph Workflow编排 (10节点) | ALL |
| `backend/app/services/memory_retriever.py` | 长期偏好记忆检索 | 2 |
| `backend/app/services/memory_service.py` | 记忆提取与写入 | 2 |
| `backend/app/agents/retrieval_agent.py` | 多通道检索编排 (text/review/policy/suppl) | 3,5,6 |
| `backend/app/retrieval/text_retriever.py` | 文本检索入口 (含hybrid_search) | 4 |
| `backend/app/retrieval/semantic_retriever.py` | 语义检索核心 (Embedding+Qdrant+Chunk聚合) | 4 |
| `backend/app/model_gateway/gateway.py` | 模型网关 (chat/embed/rerank统一接口) | 4,7 |
| `backend/app/model_gateway/qwen_embedding.py` | Qwen Embedding HTTP客户端 | 4 |
| `backend/app/core/cache.py` | Redis缓存层 (get-or-compute模式) | 3,4 |
| `backend/app/verification/evidence_checker.py` | 证据充足性验证 | 8 |
| `backend/app/agents/decision_agent.py` | 决策编排 (profiles→metrics→scoring) | 9 |
| `backend/app/decision/scoring.py` | 9维评分引擎 | 9 |
| `backend/app/decision/evidence_metrics.py` | 证据指标计算 (6因子confidence) | 9 |
| `backend/app/schemas/product.py` | Product/RagKnowledge/FaqItem/ReviewItem 数据模型 | ALL |
| `backend/app/schemas/workflow.py` | WorkflowState/Constraints/RetrievalPlan 工作流状态 | ALL |
| `backend/app/schemas/decision_result.py` | DecisionResult/ScoreBreakdown 评分输出模型 | 9 |
| `backend/app/verification/response_guard.py` | 回答安全验证 | POST |
| `backend/data/product_chunk_embeddings.json` | 本地Chunk向量缓存 (35.2MB, 1133 chunks) | 4 |
| `backend/data/product_embeddings.json` | 本地产品向量缓存 (3.5MB, 105 products) | 4 |

---

> **文档维护**: 每次RAG链路改动后同步更新本文档。当前维护者：TheodoreYang6 + Claude Code。
