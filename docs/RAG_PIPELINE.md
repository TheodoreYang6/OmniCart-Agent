# OmniCart RAG 全链路技术文档

## 概述

OmniCart 的 RAG (Retrieval-Augmented Generation) 管道是系统的核心检索引擎，负责将用户自然语言查询转化为精准的商品推荐。全链路包含 Embedding 向量化 → Qdrant ANN 检索 → 约束过滤 → Reranker 精排 → 证据补充 → 上下文编译 → 生成回答 7 个环节。

### 核心指标

| 指标 | 数值 |
|------|------|
| 商品数量 | 105 件 (4 品类/42 子类) |
| 向量维度 | 1024 (text-embedding-v4) |
| 向量库 | Qdrant (ANN) |
| 检索延迟 | ~400ms (含Embedding) |
| 精排延迟 | ~300ms (qwen3-rerank) |
| 证据通道 | 3 路并行 (review/policy/text) |
| 缓存策略 | Redis 4级 (视觉/搜索/改写/工作流) |
| 降级能力 | Qdrant→本地余弦, Embedding→关键词 |

---

## 全链路架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        RAG Pipeline                             │
│                                                                  │
│  User Query                                                      │
│     │                                                            │
│     ▼                                                            │
│  ┌──────────────────────┐                                        │
│  │  1. Query Rewrite    │  Router提取category/must_tags/        │
│  │     (Router Agent)   │  spec_keywords → 拼接搜索词           │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐                                        │
│  │  2. Embedding        │  text-embedding-v4                    │
│  │     (1024 dims)      │  输入: 搜索词 → 输出: 1024维向量      │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐     ┌─────────────────┐               │
│  │  3. Vector Search    │────→│ Qdrant 降级      │               │
│  │     Qdrant ANN       │     │ 本地余弦相似度    │               │
│  └──────────┬───────────┘     └─────────────────┘               │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐                                        │
│  │  4. Filter & Boost   │  品类/子品类/价格范围过滤              │
│  │                      │  must_tags硬匹配→顶部插入              │
│  │                      │  exclude_tags硬过滤→直接移除           │
│  │                      │  visual_matched→置顶(0.99)             │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐     ┌─────────────────┐               │
│  │  5. Reranker         │────→│ 降级: 保持原序    │               │
│  │     qwen3-rerank     │     │ (快速模式/异常)    │               │
│  │     分数校准          │     └─────────────────┘               │
│  └──────────┬───────────┘                                        │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────────────────────────┐                    │
│  │  6. Evidence Supplement (并行)            │                    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────────┐ │                    │
│  │  │ review  │ │ policy  │ │    text      │ │                    │
│  │  │用户评价  │ │ FAQ/政策 │ │  商品描述     │ │                    │
│  │  │余弦匹配  │ │ 余弦匹配  │ │  语义检索     │ │                    │
│  │  └─────────┘ └─────────┘ └─────────────┘ │                    │
│  └──────────┬───────────────────────────────┘                    │
│             │                                                    │
│             ▼                                                    │
│  ┌──────────────────────┐                                        │
│  │  7. Context Compile  │  编译结构化上下文                      │
│  │     + Response Gen   │  LLM生成 / 模板回答                    │
│  └──────────────────────┘                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. Query Rewrite — 查询改写

Router Agent 提取结构化信息后，Retrieval Agent 根据丰富度判断：

- **Router丰富** (有category/must_tags) → 直接拼接搜索词，不调LLM
- **Router稀疏** (仅简短query) → LLM关键词提取(qwen-turbo)

```python
# 搜索词拼接 (Router丰富的快速路径)
search_query = f"{user_query} {category} {sub_category} {must_tags} {spec_keywords}"
```

**亮点**: Router提取的 `must_tags` 和 `spec_keywords` 直接复用，避免额外的LLM关键词提取调用。单这一项省 ~500ms。

---

## 2. Embedding — 文本向量化

```
搜索词 → text-embedding-v4 → [0.023, -0.015, ..., 0.041] (1024维)
```

| 属性 | 值 |
|------|-----|
| 模型 | text-embedding-v4 |
| 维度 | 1024 |
| 延迟 | ~200ms |
| 缓存 | Redis (TTL=300s) |

Embedding 调用失败时自动降级为关键词子串匹配，保证可用性。

---

## 3. Vector Search — Qdrant 向量检索

### ANN 搜索

```python
QdrantClient.search(
    collection_name="products",
    query_vector=embedding,
    limit=top_k * 3,  # 召回3倍候选，给后续过滤留空间
)
```

### 降级方案

```
Qdrant 连接失败/超时
  → httpx 不走系统代理 (NO_PROXY)
  → 本地余弦相似度计算 (product_embeddings.json)
  → 关键词子串匹配 (jieba分词)
```

### 产品数据粒度

每个产品存储为 Qdrant Point：

```json
{
  "id": "p_beauty_001",
  "vector": [...],
  "payload": {
    "title": "雅诗兰黛特润修护肌活精华露...",
    "brand": "雅诗兰黛",
    "category": "美妆护肤",
    "sub_category": "精华",
    "price": 720.00,
    "rag_knowledge": {
      "marketing_description": "...",
      "faq": [...],
      "reviews": [...]
    }
  }
}
```

---

## 4. Filter & Boost — 多维度候选集调整

检索结果在进入精排前经过多层调整：

### 品类/价格过滤

```python
if constraints.category:   → 保留category匹配的商品
if constraints.sub_category: → 进一步过滤
if constraints.budget_max:   → price ≤ budget_max
```

### must_tags 硬匹配

用户明确提到的品牌/商品名，通过 `search_text()` 关键词检索确保出现在结果中：

```python
for tag in must_tags:
    hits = product_repo.search_text(tag)  → 插入检索结果顶部
    hits.reranker_score = 0.97  # 确保不被精排翻盘
```

### exclude_tags 硬过滤

匹配避雷标签的商品直接从检索结果移除：

```python
retrieved_products = [p for p in products
    if not any(tag in p.title+p.brand for tag in exclude_tags)]
```

### 视觉置顶

Visual Agent 精确匹配到的商品锁定在 0.99 分，确保识图结果不被评分公式压下去。

---

## 5. Reranker — Qwen3-Rerank 精排

### 精排文档构建

每个候选商品拼接为结构化文档：

```python
doc = f"{title} {brand} | 描述: {description} | FAQ: {faq} | 评论: {reviews} | 证据: {evidence}"
```

### 分数校准

```python
calibrated_score = 0.68 + 0.38 * raw_rerank_score
```

将 Reranker 原始分映射到 [0.68, 1.06] 区间，避免极端值。

### 跳过条件

- 仅 1 个候选商品 → 跳过（无意义）
- 快速模式 → 跳过（省 ~300ms）
- API 异常 → 保持检索原始排序

---

## 6. Evidence Supplement — 三通道并行证据

检索完成后，三通道并行补充证据信息：

### Review 通道

```
用户评价 chunks → Embedding(query) → 余弦相似度匹配 → top-k 相关评价
```

- 匹配阈值: cosine > 0.35
- 降级: 关键词子串匹配

### Policy/FAQ 通道

```
FAQ chunks → 同上流程
```

### Text 通道

```
商品描述 → 语义检索 (已在主检索完成)
```

### 并行优势

三通道通过 `ThreadPoolExecutor` 并行执行，总延迟 = max(各通道延迟)，而非 sum。

---

## 7. Context Compile + Response

### Context Compiler

将 WorkflowState 编译为结构化上下文：

```
## 用户需求
query, intent, constraints

## 候选商品
[1] brand title price score
    evidence: review/FAQ snippets

## 风险提示
risk_factors

## 偏好上下文
profile hints
```

### Response 生成

- **LLM 路径**: qwen-turbo 生成自然语言, 6s 超时→模板兜底
- **模板路径**: 快速模式或 LLM 失败时使用模板, 纯商品名+价格

### 幻觉检测 (Response Guard)

5项守门检查确保回答质量：证据绑定、价格准确、风险覆盖、空结果诚实、品牌幻觉检测。

---

## RAG 评测体系

### Golden Query 集

10 条精心设计的评测查询，覆盖 4 品类 × 多种查询类型：

| 类型 | 示例 |
|------|------|
| 模糊推荐 | "推荐一款适合油皮的洗面奶" |
| 条件筛选 | "200元以下的蓝牙耳机有哪些" |
| 场景化搜索 | "下周去三亚度假,帮我搭配一套防晒到穿搭" |
| 反选排除 | "推荐防晒霜，但不要含酒精的，也不要日系品牌" |
| 多模态 | [上传街拍照片]"我想要同款外套" |

### 评测指标

| 指标 | 说明 |
|------|------|
| Hit@5 | Top5是否包含相关商品 |
| Hit@10 | Top10是否包含相关商品 |
| MRR | 第一个相关商品的倒数排名均值 |
| Recall@10 | Top10召回了多少相关商品 |
| NDCG@10 | 归一化折损累计增益 |

### Eval Dashboard

Web 可视化面板 (Chart.js)：通过率/延迟/品类准确率/Recall/MRR/NDCG 卡片 + 查询详情表格 + 历史运行趋势。

---

## 性能优化

### Redis 四级缓存

| 缓存层 | TTL | 缓存内容 |
|--------|-----|---------|
| Visual | 3600s | Qwen-VL 图片解析结果 (含图片hash+prompt hash) |
| Search | 300s | 搜索结果 (含query+category hash) |
| Rewrite | 1800s | Router LLM 输出 |
| Workflow | 300s | 完整 WorkflowState (含query+image hash) |

所有缓存优雅降级——Redis不可用时直接计算。

### 快速模式

`fast_mode=true` 时跳过 Router LLM + Reranker + Response LLM，全链路仅保留 Embedding + Qdrant + Decision + 模板。延迟从 4-8s 降至 ~1s。

### Router∥Visual 并行

有图片时 Router 和 Visual 同时执行，省 1-3s。

### Prompt 压缩

Router prompt 从 1200t → 740t, Response prompt 从 250t → 130t。累计省 ~600 tokens/请求。

---

## 全链路追踪

`observability/rag_logger.py` 记录每轮 RAG 全链路数据：

```json
{
  "session_id": "xxx",
  "query": "推荐蓝牙耳机",
  "embedding": { "latency_ms": 200, "candidates": 15 },
  "rerank": { "latency_ms": 300, "top_score": 0.85 },
  "final": { "products": 5, "evidence": 12 }
}
```

Gateway 审计日志输出每次模型调用的能力名、模型名、耗时、输入输出摘要。
