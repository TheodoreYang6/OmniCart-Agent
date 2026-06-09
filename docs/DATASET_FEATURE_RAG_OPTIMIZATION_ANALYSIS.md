# OmniCart Agent 数据集、特征工程与 RAG 检索优化分析

生成日期：2026-05-24  
分析范围：`ecommerce_agent_dataset/`、`data/`、`backend/`、`scripts/`、`tests/`、`alembic/`、核心项目文档。  
任务边界：本文件只做分析与优化方案设计，不修改任何业务代码。

## 0. 关键结论摘要

当前 OmniCart Agent 已经具备一条可运行的电商导购数据链路：本地 JSON 商品数据通过 `JsonProductRepository` 读取，PostgreSQL 可通过 `seed_postgresql.py` 导入商品主表，推荐接口可基于 `TextRetriever` 做关键词检索，`DecisionScoring` 计算 7 维推荐分，LangGraph Workflow 串联 Router、Visual、Retrieval、Reranker、EvidenceCheck、Decision、Response、Guard，并通过 Android 端展示商品、Evidence、Score、Trace 等结果。

但从“数据集、RAG、检索 Agent、数据库、特征工程与特征治理”角度看，当前实现仍以商品级 JSON / JSONB 与商品级文本检索为主，尚未形成严格的 chunk 级 RAG 数据资产、稳定的 evidence 数据血缘、独立的 review / FAQ / policy 表、可复用的 feature dictionary、检索分层评测体系和数据版本治理体系。

需要特别注意以下代码级事实：

- 主 LangGraph Workflow 中 `RetrievalAgent._text_channel()` 当前调用的是 `TextRetriever.search()`，不是 `TextRetriever.hybrid_search()`；因此主链路默认仍是 jieba + 关键词检索，Qdrant hybrid search 主要在 `scripts/run_baseline.py` 和直接调用 `hybrid_search()` 时使用。
- `scripts/seed_qdrant.py` 设计为将商品级拼接文本写入 Qdrant，但脚本中 `gateway.embed(...)` 是 async 方法，当前同步 `main()` 中没有 `await`，需要修复后才能稳定批量建索引。
- Qdrant 当前 payload 只有 `product_id` 与拼接 `text`，没有 `source_type`、`evidence_id`、`category`、`brand`、`price`、`risk_tags` 等可过滤 metadata。
- 当前 Evidence 多数由检索阶段即时拼接，`content` 常是 “Text match score” 或 “Evidence for product_id” 级摘要，并不是严格可引用的原文 span / citation_text。
- `DecisionHarness` 类已经存在，但 `backend/app/workflow/graph.py` 当前没有直接调用 `DecisionHarness.validate()`；主 workflow 里的 `harness_report` 主要由 `ResponseGuard.check()` 写入轻量检查结果。
- PostgreSQL 当前主要有 `products`、`cart_items`、`user_preferences`、`users`、`addresses` 五类 ORM 模型；Alembic 初始迁移只包含 `products`、`cart_items`、`user_preferences`，`users` 和 `addresses` 依赖 `create_all()` 自动建表，迁移版本尚未补齐。
- 数据集实际扫描结果为 105 个商品 JSON、100 张图片；README / seed 脚本文案中多处仍写“100 件商品”。`2_Digital_Electronics` 有 30 个 JSON，但只有 25 张图片，`p_digital_026` 到 `p_digital_030` 缺少对应图片文件。

## 1. 数据集总体盘点

### 1.1 数据集目录结构与规模

数据集根目录：`ecommerce_agent_dataset/`

| 文件/目录 | 数据类型 | 数据规模 | 主要字段 | 用途 | 当前代码是否使用 | 对应代码路径 |
|---|---:|---:|---|---|---|---|
| `ecommerce_agent_dataset/1_Beauty_and_Skincare/data/*.json` | 商品 JSON | 25 个商品 | `product_id`、`title`、`brand`、`category`、`sub_category`、`base_price`、`image_path`、`skus`、`rag_knowledge` | 美妆护肤商品、FAQ、评论与营销描述 | 是 | `backend/app/repositories/json_product_repo.py` |
| `ecommerce_agent_dataset/1_Beauty_and_Skincare/images/*.jpg` | 商品图片 | 25 张 | 文件名如 `p_beauty_001_live.jpg` | Android 商品图片展示、视觉 Demo 素材 | 间接使用 | `BaseProductRepository.resolve_image_url()` |
| `ecommerce_agent_dataset/2_Digital_Electronics/data/*.json` | 商品 JSON | 30 个商品 | 同上 | 数码电子商品，含手机、电脑、平板、耳机、移动电源、充电器 | 是 | `JsonProductRepository`、`TextRetriever` |
| `ecommerce_agent_dataset/2_Digital_Electronics/images/*.jpg` | 商品图片 | 25 张 | `p_digital_001_live.jpg` 到 `p_digital_025_live.jpg` | 商品展示 | 部分使用 | `resolve_image_url()`；`p_digital_026` 到 `p_digital_030` 缺图 |
| `ecommerce_agent_dataset/3_Clothing_and_Sports/data/*.json` | 商品 JSON | 25 个商品 | 同上 | 服饰运动商品 | 是 | `JsonProductRepository` |
| `ecommerce_agent_dataset/3_Clothing_and_Sports/images/*.jpg` | 商品图片 | 25 张 | `p_clothes_xxx_live.jpg` | 商品展示 | 是 | `resolve_image_url()` |
| `ecommerce_agent_dataset/4_Food_and_Life/data/*.json` | 商品 JSON | 25 个商品 | 同上 | 食品饮料商品 | 是 | `JsonProductRepository` |
| `ecommerce_agent_dataset/4_Food_and_Life/images/*.jpg` | 商品图片 | 25 张 | `p_food_xxx_live.jpg` | 商品展示 | 是 | `resolve_image_url()` |
| `data/golden_queries.json` | 评测 query JSON | 30 条 | `query_id`、`user_query`、`category`、`constraints` | 充电宝场景评测集雏形 | 代码中未找到完整接入 | `backend/app/api/eval.py` 使用内置 10 条，不读取该文件 |
| `data/products_v0_archive.json` | 历史商品归档 | 60 条 | 历史 V0 商品字段 | 旧版数据备份 | 当前主链路未使用 | 代码中未找到直接读取 |
| `data/checkpoints/*.json` | Workflow checkpoint | 多个运行态文件 | `WorkflowState` 中间态 | 状态恢复、Demo Pack 导出 | 是 | `backend/app/workflow/checkpoint.py` |
| `data/eval_runs/*.json` | 评测结果 | 运行时生成 | pass_rate、latency、details | Eval Dashboard 历史趋势 | 是 | `backend/app/api/eval.py` |
| `data/uploads/*` | 上传图片 | 运行时生成 | 图片文件 | Visual Agent 解析输入 | 是 | `backend/app/api/upload.py`、`backend/app/agents/visual_agent.py` |

### 1.2 商品数据统计

真实扫描结果：

| 品类目录 | 商品 JSON | 图片文件 | SKU 数 | FAQ 数 | 评论数 | 备注 |
|---|---:|---:|---:|---:|---:|---|
| `1_Beauty_and_Skincare` | 25 | 25 | 55 | 106 | 119 | 图片完整 |
| `2_Digital_Electronics` | 30 | 25 | 185 | 123 | 125 | 5 个商品缺图 |
| `3_Clothing_and_Sports` | 25 | 25 | 263 | 109 | 115 | SKU 最多 |
| `4_Food_and_Life` | 25 | 25 | 92 | 116 | 110 | 图片完整 |
| 合计 | 105 | 100 | 595 | 454 | 469 | 商品数与 README/脚本文案“100”不一致 |

### 1.3 商品字段结构

每个商品 JSON 顶层字段完全一致：

| 字段 | 类型 | 当前用途 | 适合关键词检索 | 适合向量检索 | 适合过滤 | 适合评分 | 适合 Evidence | 适合 Android 展示 | 未充分利用点 |
|---|---|---|---|---|---|---|---|---|---|
| `product_id` | string | 主键、检索结果关联 | 否 | 否 | 是 | 是 | 是 | 是 | 缺少数据版本前缀和来源批次 |
| `title` | string | 展示、关键词匹配、Qdrant 拼接文本 | 是 | 是 | 弱 | 是 | 是 | 是 | 未做标题规范化、别名展开 |
| `brand` | string | 展示、过滤、评分间接使用 | 是 | 是 | 是 | 是 | 是 | 是 | 品牌别名未统一，如 `Nike` 与 `耐克` 可合并 |
| `category` | string | 过滤、Router 约束、展示 | 是 | 是 | 是 | 是 | 是 | 是 | 类目体系固定但缺少枚举版本 |
| `sub_category` | string | 过滤、展示、检索加权 | 是 | 是 | 是 | 是 | 是 | 是 | 缺少同义词，如“移动电源/充电宝” |
| `base_price` | float | 预算过滤、展示、评分 | 否 | 否 | 是 | 是 | 弱 | 是 | 缺少币种、促销价、历史价 |
| `image_path` | string | 图片 URL 解析 | 否 | 可做视觉索引入口 | 是 | 弱 | 是 | 是 | 5 个数码商品缺图；缺图片质量状态 |
| `skus` | list | 展示规格、商品详情 | 是 | 可拼接 | 是 | 是 | 是 | 是 | SKU 参数未规范化为统一 feature schema |
| `rag_knowledge.marketing_description` | string | 检索、Qdrant 文本、评分 | 是 | 是 | 否 | 是 | 是 | 是 | 未切分 chunk，引用粒度太粗 |
| `rag_knowledge.official_faq` | list | 检索、policy/FAQ evidence | 是 | 是 | 可按 FAQ 类型 | 是 | 是 | 是 | FAQ 未独立 evidence_id 持久化 |
| `rag_knowledge.user_reviews` | list | 检索、风险挖掘、评分 | 是 | 是 | 可按 rating | 是 | 是 | 是 | 评论缺时间、情绪、aspect、可信度 |

### 1.4 SKU 字段分析

SKU 统一字段为：

```json
{
  "sku_id": "s_p_beauty_001_1",
  "properties": {"容量": "30ml 经典装"},
  "price": 720.0
}
```

扫描到的高频 SKU property 包括：`颜色`、`尺码`、`版本`、`容量`、`存储`、`款型`、`屏幕尺寸`、`适用性别`、`包装`、`口味`、`网络版本`、`芯片型号`、`固态硬盘容量`、`规格` 等。

当前问题：

- SKU properties 是自由文本字典，适配不同类目，但缺少统一单位规范。
- `容量` 在美妆中可能是 `30ml`，在数码中可能是 `20000mAh`，在食品中可能是净含量，当前没有 feature namespace。
- `版本`、`规格`、`产品版本`、`存储配置`、`存储规格` 语义相近但字段名不统一。
- SKU 当前主要展示和价格选择，没有被充分用于检索过滤、Decision Scoring 与 constraint solving。

### 1.5 FAQ、评论、政策规则与 RAG 知识

当前数据集中没有独立的 `faq.json`、`reviews.csv`、`policy_rules.md` 或 `rag_knowledge.md` 文件。FAQ、评论和“政策类知识”都嵌在每个商品的 `rag_knowledge` 字段中：

- `marketing_description`：商品详情、卖点、适用人群、使用注意事项。
- `official_faq`：每条包含 `question`、`answer`。
- `user_reviews`：每条包含 `nickname`、`rating`、`content`。

当前代码将 `official_faq` 同时当作 FAQ 和 policy source 使用。`RetrievalAgent._policy_channel()` 通过关键词从 FAQ 中筛选航空、安检、容量、功率、过敏、保修、退换等内容，生成 `policy_faq` 类型 evidence。

这意味着：

- 项目具备政策检索雏形，但没有独立政策规则库。
- FAQ 与政策边界混在一起，无法稳定计算 `Policy Evidence Recall`。
- 航空规则、兼容性规则、售后规则、过敏风险等应拆成独立 `source_type`。

## 2. 当前数据读取与数据流分析

### 2.1 数据读取入口

商品数据读取入口：

| 功能 | 代码路径 | 关键类/函数 | 输入 | 输出 | 当前问题 |
|---|---|---|---|---|---|
| JSON 商品加载 | `backend/app/repositories/json_product_repo.py` | `JsonProductRepository._load()` | `ecommerce_agent_dataset/*/data/*.json` | `list[Product]`、`dict[product_id, Product]` | 异常被直接吞掉，缺少数据质量报告 |
| 商品 schema 校验 | `backend/app/schemas/product.py` | `Product(**raw)` | 原始 JSON | Pydantic Product | 只做类型校验，缺少业务字段质量校验 |
| 图片 URL 转换 | `backend/app/repositories/base_product_repo.py` | `resolve_image_url()` | `image_path` | `/images/...` URL | 不检查文件是否真实存在 |
| PostgreSQL 导入 | `scripts/seed_postgresql.py` | `main_async()` | JSON Repo | `products` 表 | 文案写 100 件，实际 105 件；只导入商品表 |
| Qdrant 导入 | `scripts/seed_qdrant.py` | `main()` | JSON Repo + embedding | Qdrant points | async embedding 未 await；商品级文本，不是 chunk 级 |

### 2.2 当前实际数据流

代码中已实现的主数据流如下：

```text
ecommerce_agent_dataset 商品 JSON
  -> JsonProductRepository._load()
  -> Product / Sku / RagKnowledge / FaqItem / ReviewItem
  -> TextRetriever.search()
  -> jieba 分词 + 全文字符串匹配
  -> retrieved_products[]
  -> RetrievalAgent 生成 text_retrieval / review_positive / review_risk / policy_faq evidence
  -> Qwen Reranker 对 retrieved_products 重排
  -> EvidenceSufficiencyChecker 检查 evidence 类型
  -> DecisionAgent + DecisionScoring 计算 7 维分数
  -> Context Compiler 结构化上下文
  -> Response Agent 生成推荐回答
  -> Response Guard 写入 harness_report
  -> /api/recommend/v2 返回 Android 展示
```

`/api/recommend` V0 路径更短：

```text
user_query / image_url
  -> VisualAgent 可选解析图片
  -> _parse_constraints()
  -> TextRetriever.search()
  -> DecisionScoring
  -> _build_answer()
  -> RecommendResponse
```

### 2.3 目标数据流与当前差距

用户要求中的理想数据流：

```text
原始数据集
→ 数据加载
→ 字段清洗
→ Schema 映射
→ 商品仓库
→ RAG 知识构建
→ Embedding
→ Qdrant 向量库
→ Retrieval Agent
→ Reranker
→ Evidence
→ Context Compiler
→ Decision Scoring
→ Response
→ Android 展示
```

当前实际完成情况：

| 环节 | 当前状态 | 代码路径 | 说明 |
|---|---|---|---|
| 原始数据集 | 已有 | `ecommerce_agent_dataset/` | 105 商品、100 图片 |
| 数据加载 | 已实现 | `JsonProductRepository._load()` | JSON 加载到内存 |
| 字段清洗 | 部分实现 | `Product(**raw)` | 只有 Pydantic 类型校验，无清洗报告 |
| Schema 映射 | 已实现 | `backend/app/schemas/product.py` | 商品 schema 简洁稳定 |
| 商品仓库 | 已实现 | JSON / PG Repo | PG 可用时切换，默认 JSON |
| RAG 知识构建 | 部分实现 | `TextRetriever._compute_rich_score()`、`RetrievalAgent` | 没有独立 chunk 构建器 |
| Embedding | 部分实现 | `QwenEmbedding`、`gateway.embed()` | 在线 query embedding 可用，批量 seed 脚本需修复 |
| Qdrant 向量库 | 部分实现 | `QdrantVectorRepository` | 商品级 point，不支持 metadata filter |
| Retrieval Agent | 已实现 | `backend/app/agents/retrieval_agent.py` | 主链路关键词检索 + review/policy evidence |
| Reranker | 已实现 | `workflow/graph.py` | Qwen Reranker 对商品候选重排 |
| Evidence | 部分实现 | `schemas/evidence.py`、`RetrievalAgent` | evidence 即时生成，缺 citation_text |
| Context Compiler | 已实现 | `backend/app/context/compiler.py` | ResponseAgent 已调用 |
| Decision Scoring | 已实现 | `backend/app/decision/scoring.py` | 7 维规则评分 |
| Android 展示 | 已实现 | `android-client/.../panel/*` | Evidence/Score/Trace/Harness 面板存在 |

### 2.4 增量更新、重新索引和版本管理

| 能力 | 当前代码状态 | 风险 |
|---|---|---|
| 增量更新商品 JSON | 代码中未找到完整实现 | JSON 修改后需要 repo reload 或重启 |
| PostgreSQL upsert | 已有 | `PgProductRepository.abulk_upsert()` 与 `seed_postgresql.py` 使用 `on_conflict_do_update` |
| Qdrant 增量 upsert | 部分具备 | `QdrantVectorRepository.store_embeddings()` 可 upsert，但 seed 脚本需修复 async |
| embedding 缓存 | 代码中未找到完整实现 | 同一商品重复索引会重复调用 embedding |
| chunk 版本管理 | 代码中未找到完整实现 | evidence_id 与 chunk 内容无法追踪版本 |
| 数据版本字段 | 代码中未找到完整实现 | ProductModel 无 `data_version`、`source_hash` |

## 3. 商品 Schema 与字段质量分析

### 3.1 Product / Sku / RagKnowledge / FaqItem / ReviewItem

代码路径：`backend/app/schemas/product.py`

```python
class Sku(BaseModel):
    sku_id: str
    properties: dict[str, str]
    price: float

class FaqItem(BaseModel):
    question: str
    answer: str

class ReviewItem(BaseModel):
    nickname: str
    rating: int
    content: str

class RagKnowledge(BaseModel):
    marketing_description: str
    official_faq: list[FaqItem]
    user_reviews: list[ReviewItem]

class Product(BaseModel):
    product_id: str
    title: str
    brand: str
    category: str
    sub_category: str
    base_price: float
    image_path: str
    skus: list[Sku]
    rag_knowledge: RagKnowledge | None
```

Schema 优点：

- 足够简单，适合 V0/V1 主链路快速稳定运行。
- 商品、FAQ、评论、SKU 都能被统一加载为 Pydantic 对象。
- `rag_knowledge` 把非结构化知识集中在商品下，便于商品级检索和展示。

Schema 局限：

- FAQ、评论、政策规则没有独立 ID 字段，当前 evidence_id 依赖运行时的数组下标。
- 评论缺少 `created_at`、`aspect_tags`、`sentiment`、`verified_purchase`、`helpful_count`。
- SKU 参数没有单位、数值、枚举、标准字段名。
- 缺少库存、销量、上架状态、售后规则、适航/合规字段。
- 缺少数据治理字段：`source`、`source_version`、`created_at`、`updated_at`、`quality_score`。

### 3.2 字段质量问题清单

| 问题类型 | 具体表现 | 影响模块 | 严重程度 | 优化建议 |
|---|---|---|---|---|
| 商品数口径不一致 | 数据集 105 JSON，README/seed 文案写 100 | 文档、演示、评测 | 中 | 统一 README、seed 输出和数据盘点脚本 |
| 图片缺失 | 数码目录 30 JSON 但 25 图片，`p_digital_026`-`030` 缺图 | Android 展示、视觉检索 | 高 | 增加 image existence check，缺图商品标记 `image_available=false` |
| SKU 字段名不统一 | `规格`、`产品规格`、`版本`、`产品版本` 等混用 | 过滤、评分、检索 | 中 | 建立 SKU property alias map |
| 单位未结构化 | `30ml`、`20000mAh`、`65W` 等在字符串中 | constraint solving、RAG | 高 | 抽取 `numeric_value`、`unit`、`normalized_unit` |
| FAQ 无 ID | 通过数组下标生成 `POL-{pid}-{i}` | evidence 稳定性 | 高 | 导入时生成稳定 `faq_id = hash(product_id + question)` |
| 评论无 ID | 通过数组下标生成 `R-{pid}-{i}` | evidence 稳定性、评测 | 高 | 生成稳定 `review_id`，保留原始 index |
| 评论缺时间 | 无法判断评论时效性 | 风险评分、排序 | 中 | 补充模拟或真实 `created_at` |
| 评论缺 aspect | 只能按 rating 做粗风险 | 风险检索、可解释推荐 | 高 | 抽取 `aspect_tags`：发热、重量、兼容、包装等 |
| 政策规则无独立表 | policy 从 FAQ 关键词筛出 | policy recall、合规判断 | 高 | 建立 `policy_rules` 数据和 evidence chunk |
| 品牌别名未治理 | `Nike` / `耐克`、`Apple 苹果` / `苹果` | 搜索召回、过滤 | 中 | 建立 brand alias dictionary |
| 类目同义词缺失 | `移动电源` 与 `充电宝` 未结构化统一 | Router、检索 | 高 | 建立 category/sub_category synonym map |
| 价格缺上下文 | 只有 base_price 和 SKU price | 促销、预算解释 | 低 | 增加 `currency`、`price_type`、`promotion_price` |
| ProductModel 缺版本 | PG 表无数据版本字段 | 数据回滚、索引一致性 | 中 | 增加 `data_version`、`source_hash` |

## 4. RAG 知识构建与 Chunk 策略分析

### 4.1 当前哪些数据进入 RAG

当前没有独立的 `RagChunk` 或 `EvidenceChunk` 构建模块。进入检索的内容分两类：

1. 关键词检索文本池：`TextRetriever._compute_rich_score()` 将 `title`、`brand`、`category`、`sub_category`、`marketing_description`、FAQ question/answer、review content 拼接成 `full_text` 做匹配。
2. Qdrant 商品级向量文本：`scripts/seed_qdrant.py` 将 `product_id | title brand category sub_category marketing_description` 写入向量库，不包含 FAQ 与评论正文。

| 数据 | 是否进入关键词检索 | 是否进入 Qdrant | 是否形成独立 chunk | 是否有 metadata | 说明 |
|---|---|---|---|---|---|
| 商品标题 | 是 | 是 | 否 | 商品级 | title 权重更高 |
| 品牌 | 是 | 是 | 否 | 商品级 | 可用于 alias 优化 |
| 类目/子类目 | 是 | 是 | 否 | 商品级 | 可用于过滤 |
| base_price | 过滤使用 | 否 | 否 | 商品级 | 未进向量 |
| SKU 参数 | 返回展示 | 否 | 否 | 商品级 | 检索利用不足 |
| 商品详情 | 是 | 是 | 否 | 商品级 | Qdrant 主要文本来源 |
| FAQ | 是 | 否 | 否 | 运行时 evidence | policy_channel 从结果中筛选 |
| 评论 | 是 | 否 | 否 | 运行时 evidence | review_channel 从结果中筛选 |
| 政策规则 | 嵌在 FAQ 中 | 否 | 否 | 无独立 metadata | 缺独立 policy 数据 |
| 视觉解析结果 | 追加到 query | 否 | 视觉 evidence | 字段级 | `VisualAgent` 生成 `VisualEvidence` |
| 用户偏好 | 影响 constraints | 否 | 否 | session/user 级 | 未进入 RAG index |

### 4.2 当前 evidence 生成方式

代码路径：

- `backend/app/retrieval/text_retriever.py`
- `backend/app/agents/retrieval_agent.py`
- `backend/app/api/recommend.py`
- `backend/app/decision/scoring.py`

当前 evidence_id 规则：

| evidence_id | 来源 | 当前内容 | 问题 |
|---|---|---|---|
| `E-MKT-{product_id}` | 商品详情/营销描述 | 在 TextRetriever 中加入 evidence_ids | 没有真实 content span |
| `POL-{product_id}-{i}` | FAQ / policy | FAQ 下标 | 下标随数据顺序变化，不稳定 |
| `R-{product_id}-{i}` | 评论 | 评论下标 | 无 review_id，无法版本追踪 |
| `R-POS-{product_id}-{i}` | 好评 evidence | review_channel 运行时生成 | 与 `R-{pid}-{i}` 体系重复 |
| `V-{field_name}` | 图片解析字段 | VisualAgent 生成 | 缺 image_id / bbox |
| `E-KW-{product_id}` | 关键词匹配 | DecisionScoring 生成 | 与检索 evidence 不完全一致 |

### 4.3 当前 chunk 策略问题

当前“RAG 知识构建”更接近商品级全文检索，而不是严格 chunk 级 RAG：

- 没有统一 `chunk_id`、`evidence_id`、`source_type`、`citation_text`。
- FAQ、评论、政策没有单独入向量库。
- `TextRetriever` 返回的 evidence content 主要是匹配分数，不是用户可校验原文。
- `Context Compiler` 只摘录部分 `review_risk` / `policy_faq` evidence，对普通 text evidence 的原文支持不足。
- Android Evidence Panel 可以展示 evidence 字段，但证据内容质量依赖后端是否给出真实 citation。

### 4.4 推荐 chunk schema

建议新增离线构建产物，而不是在检索时临时拼接：

```json
{
  "evidence_id": "ev_review_p_digital_003_9f2a",
  "chunk_id": "chunk_v1_review_p_digital_003_9f2a",
  "product_id": "p_digital_003",
  "source_type": "review",
  "source_id": "review_p_digital_003_9f2a",
  "title": "用户评论：发热与重量反馈",
  "content": "用户反馈长时间快充会发热，重量偏重，不适合轻量通勤。",
  "citation_text": "原始评论中的可引用句子",
  "modality": "text",
  "metadata": {
    "category": "数码电子",
    "sub_category": "移动电源",
    "brand": "Anker",
    "price": 199.0,
    "rating": 2,
    "aspect_tags": ["heat", "weight"],
    "scenario_tags": ["commute", "business_trip"],
    "risk_tags": ["overheat", "heavy"],
    "policy_tags": [],
    "created_at": "2026-05-24",
    "data_version": "dataset_v1",
    "quality_score": 0.86
  }
}
```

### 4.5 各类 chunk 优化方案

| chunk 类型 | 构建方式 | metadata | 用途 | 优先级 |
|---|---|---|---|---|
| 商品参数 chunk | 从 title、SKU properties、marketing_description 抽取结构化参数 | category、brand、price、specs、unit | 参数匹配、过滤、评分 | P0 |
| 评论 chunk | 每条 review 独立 chunk，抽取 sentiment/aspect/risk | rating、aspect_tags、risk_tags | 风险召回、Review Evidence Recall | P0 |
| FAQ chunk | 每个 Q/A 独立 chunk | faq_type、question_hash | FAQ 检索、解释引用 | P0 |
| 政策规则 chunk | 从 FAQ 拆出或新增独立 policy 数据 | policy_type、scope、effective_date | 航空/售后/过敏规则 | P0 |
| 视觉证据 chunk | VisualAgent 输出字段生成 chunk | image_id、field、confidence、bbox | 图片导购、视觉可解释 | P1 |
| 用户偏好 chunk | 长期偏好 profile 摘要 | user_id、affinity、freshness | 个性化 retrieval | P2 |
| 复合 evidence chunk | 合并商品参数 + FAQ + review | evidence_group_id | Context 压缩 | P2 |

## 5. Embedding 与向量检索分析

### 5.1 当前 embedding 实现

| 功能 | 代码路径 | 函数 | 输入 | 输出 | 当前问题 |
|---|---|---|---|---|---|
| Embedding API | `backend/app/model_gateway/qwen_embedding.py` | `QwenEmbedding.embed()` | `list[str]` | `list[list[float]]` | 直接调用 DashScope embedding endpoint |
| Gateway 封装 | `backend/app/model_gateway/gateway.py` | `ModelGateway.embed()` | texts + capability | vectors | 支持 mock、trace、能力名映射 |
| 模型配置 | `backend/app/model_gateway/model_config.yaml` | `text_embedding` | `text-embedding-v4` | 1024 维 | 配置清晰 |
| Qdrant collection | `backend/app/core/qdrant_client.py` | `init_qdrant()` | collection name | `products` collection | 只有单 collection |
| 批量索引 | `scripts/seed_qdrant.py` | `main()` | 商品级文本 | Qdrant points | async 调用未 await |
| 在线向量检索 | `backend/app/retrieval/text_retriever.py` | `hybrid_search()` | query embedding | vector hits | 主 Workflow 未使用 |

Embedding 模型配置：

- `text_embedding`：`text-embedding-v4`
- 维度：`1024`
- Qdrant 距离：`COSINE`
- collection：默认 `products`

### 5.2 Qdrant 当前实现

代码路径：`backend/app/repositories/qdrant_vector_repo.py`

当前 `store_embeddings()` payload：

```json
{
  "product_id": "p_xxx",
  "text": "title brand category sub_category marketing_description"
}
```

当前 `search_similar()`：

- 调用 `client.search(collection_name, query_vector, limit=top_k)`。
- 返回 `product_id`、`score`、`payload`。
- 不传入 `query_filter`。
- 不支持按 `category`、`brand`、`source_type`、`price`、`product_id` 过滤。

### 5.3 向量检索当前问题

| 问题 | 影响 | 优化方案 |
|---|---|---|
| 主 Workflow 未调用 `hybrid_search()` | Qdrant 不参与主推荐路径 | 在 `RetrievalAgent._text_channel()` 中按配置切换 `hybrid_search()` |
| Qdrant seed 脚本 async 未 await | 批量索引可能无法实际生成 embedding | 改为 `asyncio.run(main_async())` |
| 商品级向量粒度过粗 | FAQ/评论/policy 召回不精准 | chunk 级 collection 或 payload source_type |
| payload metadata 太少 | 无法做 filter 和 evidence 展示 | 增加 category、brand、price、source_type、evidence_id |
| 无 embedding cache | 重建索引成本高 | 建立 `data/embedding_cache/*.jsonl` 或 PG table |
| 无 index version | 新旧向量混杂 | collection 命名加版本，如 `products_v20260524` |
| 无 query rewrite 多路召回 | 口语 query 召回不稳 | Router 生成多 query，分别召回再融合 |

### 5.4 推荐向量库设计

短期可以先保持单 collection，但 payload 必须升级：

```json
{
  "product_id": "p_digital_003",
  "evidence_id": "ev_faq_p_digital_003_001",
  "source_type": "faq",
  "category": "数码电子",
  "sub_category": "移动电源",
  "brand": "Anker",
  "price": 199.0,
  "risk_tags": ["flight_limit"],
  "scenario_tags": ["business_trip", "flight"],
  "data_version": "dataset_v1",
  "text": "FAQ 问题 + 答案"
}
```

中期建议拆 collection：

- `product_specs_v1`
- `product_reviews_v1`
- `product_faq_v1`
- `policy_rules_v1`
- `visual_evidence_v1`

这样可以按 intent 控制召回源，例如：

- `compatibility_check`：优先 `product_specs_v1` + `policy_rules_v1`
- `risk_check`：优先 `product_reviews_v1` + `policy_rules_v1`
- `recommend`：`product_specs_v1` + `product_reviews_v1` + `product_faq_v1`

## 6. 关键词检索、PostgreSQL 全文检索与 Hybrid Search

### 6.1 JSON 关键词检索

`JsonProductRepository.search_text()` 是基础版字符串匹配：

- 将 `title`、`brand`、`category`、`sub_category`、marketing、FAQ、review 拼接。
- 对 query 空格切词逐个匹配。
- 对 query bigram 加分。
- 返回 `Product` 列表。

`TextRetriever.search()` 是主链路使用的增强版：

- 使用 jieba 对 query 分词。
- 去除 `_QUERY_STOP_WORDS`。
- 先按 category、sub_category、price 过滤候选。
- `_compute_rich_score()` 对 title、category、sub_category 额外加权。
- 返回结构化 dict，包括 `evidence_ids`、`rag_knowledge`、`image_urls`。

### 6.2 PostgreSQL 全文检索

代码路径：`backend/app/repositories/pg_product_repo.py`

`_asearch_text()` 使用：

```sql
to_tsvector('simple', title || brand || marketing_description)
@@ plainto_tsquery('simple', :q)
```

当前问题：

- PostgreSQL `simple` config 对中文分词效果有限。
- 查询只覆盖 title、brand、marketing_description，没有覆盖 FAQ 和 reviews。
- 没有 `ts_rank` 排序。
- 没有 GIN index migration。
- 没有 `pg_trgm` 模糊匹配。
- fallback 是 `ILIKE '%query%'`，中文长 query 命中不稳定。

### 6.3 Hybrid Search 当前实现

代码路径：`backend/app/retrieval/text_retriever.py`

`hybrid_search()` 流程：

```text
text_results = search(query, top_k * 2)
if Qdrant unavailable:
    return text_results
query_embedding = await gateway.embed([query])
vector_results = vector_repo.search_similar(query_embedding, top_k * 2)
vector_hits = product_id -> Product -> result dict
merged = _rrf_fusion(text_results, vector_hits, k=60)
return merged[:top_k]
```

RRF 当前公式：

```text
rrf_score += 1 / (k + rank + 1), k = 60
```

当前问题：

- RRF score 与原始 `item["score"]` 混合方式不够清晰，存在“显示 score”和“融合排序 score”语义混用。
- vector hit 只回 product_id，无法回 evidence chunk。
- `hybrid_search()` 未在主 Workflow 中调用。
- metadata filter 缺失导致 category/price 过滤只作用于 text branch，不作用于 vector branch。

### 6.4 关键词检索优化方案

| 优化项 | 做法 | 影响指标 | 优先级 |
|---|---|---|---|
| 电商领域词典 | 添加 jieba userdict：充电宝、移动电源、MacBook、磁吸、氮化镓、航空 | Recall@K | P0 |
| 品牌别名表 | `Apple 苹果`、`苹果`、`iPhone`、`Nike`、`耐克` 归一 | Hit@K、过滤准确率 | P0 |
| 参数同义词 | `功率/瓦数/W`、`容量/mAh/毫安时`、`重量/克/g` | Constraint Coverage | P0 |
| 单位归一化 | 正则抽取 `65W`、`20000mAh`、`100Wh` | Policy Recall、Decision Accuracy | P0 |
| PostgreSQL GIN | 为 `to_tsvector` 表达式或 generated column 加 GIN index | Latency | P1 |
| pg_trgm | title、brand、sub_category 模糊匹配 | typo 容错 | P1 |
| BM25 | 引入 rank_bm25 或 PG ts_rank | Ranking Accuracy | P1 |
| RRF 调参 | 分 source 设置权重，如 vector 0.6、keyword 0.4 | NDCG | P1 |
| query rewrite | Router 输出 canonical search terms | Recall@K | P1 |
| hard negative | 充电宝 vs 充电器，耳机 vs 音箱 | Rerank Accuracy | P2 |

## 7. Retrieval Agent 工作流程分析

### 7.1 Retrieval Agent 输入输出

代码路径：`backend/app/agents/retrieval_agent.py`

输入来自 `WorkflowState`：

- `user_query`
- `retrieval_plan.channels`
- `retrieval_plan.top_k`
- `constraints.category`
- `constraints.sub_category`
- `constraints.budget_max`
- `constraints.budget_min`
- `visual_result` 间接影响：`workflow/graph.py` 中 `_node_visual()` 会把视觉识别出的商品名、品牌、类目、规格追加到 `state.user_query`。
- `user_id` 偏好间接影响：`_node_router()` 中 `PreferenceMemory` 和 `LongTermMemory` 会合并 constraints。

输出写入：

- `state.retrieved_products`
- `state.evidence_list`
- `state.trace_steps`

### 7.2 完整调用链

```text
User Query
  -> RouterAgent.execute()
      -> 规则解析 + Qwen intent_understanding
      -> Constraints
      -> RetrievalPlan(channels, top_k, category)
  -> Workflow._node_visual()
      -> 如果有 image_url，VisualAgent.parse()
      -> 视觉字段追加到 user_query
  -> RetrievalAgent.execute()
      -> _text_channel()
          -> _llm_extract_keywords()
          -> TextRetriever.search()
          -> 生成 text_retrieval evidence
      -> _review_channel()
          -> 从 retrieved_products.rag_knowledge.user_reviews 抽取好评/差评 evidence
      -> _policy_channel()
          -> 从 retrieved_products.rag_knowledge.official_faq 按关键词抽取 policy_faq evidence
      -> 去重 products
      -> 写入 WorkflowState
  -> Workflow._node_reranker()
      -> Qwen Reranker 对 products 重排
  -> EvidenceSufficiencyChecker
  -> DecisionAgent
```

### 7.3 当前 Retrieval Agent 的优点

- Router 生成 `RetrievalPlan`，不是固定写死所有检索渠道。
- text 通道先召回商品，再从候选商品中挖 review/policy evidence，减少无关数据遍历。
- review / policy 二级通道通过 `ThreadPoolExecutor` 并行执行。
- 所有候选商品都携带 `evidence_ids`，便于 Decision 绑定。
- LLM query rewrite 结果会写入 trace。

### 7.4 当前 Retrieval Agent 的问题

| 问题 | 代码表现 | 影响 | 优化方向 |
|---|---|---|---|
| 主链路未用 hybrid search | `_text_channel()` 调用 `search()` | Qdrant 不参与主流程 | 配置化切换 `search/hybrid_search` |
| 没有 RetrievalPlan 细粒度 query | plan 只有 channels/category/top_k | 无法多路 query | 增加 `queries[]`、`filters`、`must_evidence_types` |
| review/policy 依赖已召回商品 | 如果商品未召回，正确评论/政策也不会进入 | 召回天花板低 | candidate recall 与 evidence recall 分离 |
| policy 从 FAQ 关键词筛选 | 无独立 policy repo | 合规问题易漏召 | policy-first retrieval |
| evidence content 偏摘要 | `Text match score` | 可解释性不足 | citation_text 原文引用 |
| ToolManager 未接入 RetrievalAgent | 直接调用 TextRetriever | 工具治理展示不足 | RetrievalAgent 通过 ToolManager 调用工具 |
| failure taxonomy 不完整 | catch Exception 写 error trace | 难定位问题 | 定义 no_candidate、no_policy、vector_down 等失败类型 |

## 8. 后端数据库与数据建模分析

### 8.1 当前 ORM 模型

| 表/模型 | 代码路径 | 主要字段 | 当前用途 | 问题 |
|---|---|---|---|---|
| `products` | `backend/app/models/product.py` | `product_id`、`title`、`brand`、`category`、`sub_category`、`base_price`、`image_path`、`skus JSONB`、`rag_knowledge JSONB` | 商品结构化存储 | FAQ/review/policy 全塞 JSONB，不利于独立检索和统计 |
| `cart_items` | `backend/app/models/cart_item.py` | `cart_item_id`、`user_id`、`product_id`、`sku_id`、`title`、`brand`、`price`、`image_url`、`quantity`、`selected` | 购物车 | 无外键、无 added_by/added_reason |
| `user_preferences` | `backend/app/models/user_preference.py` | `session_id`、`user_id`、`preferences JSONB` | 会话偏好/长期记忆存储 | 与长期 profile 共用 JSON，缺 feature schema |
| `users` | `backend/app/models/user.py` | `user_id`、`username`、`password_hash`、`email`、`phone`、`token` | 登录注册 | Alembic 未包含 |
| `addresses` | `backend/app/models/address.py` | `address_id`、`user_id`、`name`、`phone`、省市区详情、`is_default` | 地址管理 | Alembic 未包含 |

### 8.2 Alembic 迁移状态

`alembic/versions/001_initial.py` 只创建：

- `products`
- `cart_items`
- `user_preferences`

但 ORM 中还有：

- `users`
- `addresses`

应用启动时 `backend/app/core/database.py:init_db()` 会 `Base.metadata.create_all`，因此运行时可能能建表，但迁移体系不完整。建议补齐 Alembic migration，避免生产/演示环境的表结构不可控。

### 8.3 商品相关数据建模问题

当前 `products.rag_knowledge JSONB` 适合快速启动，但不适合检索系统长期治理：

- FAQ、review 无独立主键，无法做 evidence-level recall。
- 无 review 表，无法按 rating、risk_tag、sentiment、时间查询。
- 无 policy 表，无法按政策类型和生效日期查询。
- 无 evidence 表，无法持久化 evidence_id、citation_text、chunk_hash。
- 无 feature 表，无法复用抽取后的结构化特征。

### 8.4 推荐数据库扩展

短期新增逻辑表：

| 表 | 关键字段 | 用途 |
|---|---|---|
| `product_reviews` | `review_id`、`product_id`、`rating`、`content`、`sentiment`、`aspect_tags`、`risk_tags` | 评论检索、风险评分 |
| `product_faqs` | `faq_id`、`product_id`、`question`、`answer`、`faq_type` | FAQ 检索与 citation |
| `policy_rules` | `policy_id`、`policy_type`、`scope`、`condition_json`、`content`、`effective_at` | 航空/售后/合规规则 |
| `evidence_chunks` | `evidence_id`、`product_id`、`source_type`、`content`、`citation_text`、`metadata`、`version` | RAG 基础资产 |
| `retrieval_traces` | `trace_id`、`query_id`、`channel`、`top_k`、`hit_ids`、`latency_ms` | 检索评测与归因 |
| `feature_values` | `entity_type`、`entity_id`、`feature_name`、`feature_value`、`version` | 轻量 feature store |

数据库索引建议：

- `products(category, sub_category, brand, base_price)`
- `products USING GIN (rag_knowledge)`
- `product_reviews(product_id, rating)`
- `product_reviews USING GIN (aspect_tags)`
- `product_faqs(product_id, faq_type)`
- `policy_rules(policy_type, scope)`
- `evidence_chunks(product_id, source_type, data_version)`
- `pg_trgm`：`products.title`、`products.brand`
- `tsvector` generated column：中文效果有限，但可作为 fallback。

## 9. 特征工程现状分析

### 9.1 特征使用总表

| 特征类别 | 当前字段 | 当前是否使用 | 使用位置 | 问题 | 优化方案 |
|---|---|---|---|---|---|
| 商品基础特征 | category、brand、price、title | 是 | Router、Repo filter、TextRetriever、DecisionScoring、Android | 缺 alias 和版本 | 类目/品牌字典治理 |
| SKU 特征 | skus.properties、sku.price | 部分 | API 返回、Android 展示 | 未进入检索评分 | 抽取标准化 spec feature |
| 商品描述文本 | marketing_description | 是 | 关键词检索、Qdrant seed、Context | 粒度粗 | 切 product_spec chunk |
| FAQ 文本 | question、answer | 是 | 关键词检索、policy_channel | 无独立 ID | 切 FAQ chunk，生成 faq_type |
| 评论文本 | nickname、rating、content | 是 | 关键词检索、review_channel、review_confidence | 无 aspect/sentiment/time | 评论 NLP 标注 |
| 视觉特征 | product_name、brand、category、specs、price、confidence | 是 | VisualAgent、query append、visual_similarity | 无 bbox、无入库 | 视觉 evidence 入库 |
| 用户偏好 | session constraints、long-term profile | 是 | PreferenceMemory、LongTermMemory | 未进入检索排序 | preference-aware retrieval |
| 检索特征 | keyword score、vector score、rerank score | 部分 | TextRetriever、Qdrant、Reranker | 分数语义未统一 | 标准化 retrieval feature |
| 决策特征 | 7 维 score breakdown | 是 | DecisionScoring、Android Score Panel | 部分维度粗略 | 引入真实 spec/policy/review feature |

### 9.2 7 维 Decision Scoring 当前实现

代码路径：`backend/app/decision/scoring.py`

当前公式：

```text
raw_score =
  0.22 * budget_fit
+ 0.24 * scenario_fit
+ 0.20 * spec_match
+ 0.14 * review_confidence
+ 0.10 * visual_similarity
+ 0.10 * availability_score
- 0.15 * risk_penalty
```

当前维度说明：

- `budget_fit`：基于 `base_price` 与预算上限。
- `scenario_fit`：query 词在 title / marketing_description 中命中。
- `spec_match`：query 词在 title/category/sub_category/marketing 中命中。
- `review_confidence`：评论平均分 + 数量 bonus。
- `visual_similarity`：视觉解析 product_name / brand 与商品匹配。
- `availability_score`：默认 1.0，因为数据集没有库存。
- `risk_penalty`：低评分评论数量和高价格惩罚。

需要优化的点：

- `scenario_fit` 和 `spec_match` 都依赖字符串命中，缺少结构化特征。
- `availability_score` 没有真实库存字段。
- `risk_penalty` 未使用评论 aspect 和具体风险词。
- 航空政策、兼容性、功率、容量等硬约束还没有独立评分维度。

### 9.3 可提取的关键电商特征

| 类别 | 推荐特征 | 来源 | 用途 |
|---|---|---|---|
| 商品参数 | capacity_mAh、power_watt、weight_g、ports、protocols、screen_size、storage_gb | title、SKU、marketing、FAQ | 过滤、spec_match、policy check |
| 航空规则 | wh_value、is_flight_allowed、needs_airline_approval | policy_rules、FAQ | policy-first retrieval、risk warning |
| 兼容性 | compatible_devices、charging_protocols、required_power | FAQ、marketing、SKU | MacBook/iPhone 场景判断 |
| 评论风险 | heat_risk、heavy_risk、quality_risk、fake_capacity_risk | reviews | risk_penalty、Evidence |
| 用户偏好 | preferred_brands、budget_range、scenario、avoid_tags | PreferenceMemory、LongTermMemory | personalization |
| 检索排序 | keyword_score、vector_score、rrf_score、rerank_score | retrieval pipeline | ranking eval |
| 可解释性 | evidence_coverage、policy_cited、score_breakdown | evidence + decision | Harness |

## 10. 特征治理方案

### 10.1 Feature Schema 规范

建议定义统一特征结构：

```json
{
  "feature_name": "power_watt",
  "entity_type": "product|sku|review|user|query|evidence",
  "entity_id": "p_digital_003",
  "feature_type": "numeric|categorical|text|list|boolean",
  "value": 65,
  "unit": "W",
  "source": "sku.properties|faq|review|visual|manual",
  "confidence": 0.92,
  "version": "feature_v1",
  "created_at": "2026-05-24"
}
```

### 10.2 Feature Dictionary 示例

| feature_name | feature_type | source | owner | used_by | freshness | quality_check | description |
|---|---|---|---|---|---|---|---|
| `category` | categorical | product JSON | product_repo | retrieval/filter/display | dataset version | enum check | 一级品类 |
| `sub_category` | categorical | product JSON | product_repo | retrieval/filter/router | dataset version | enum + synonym check | 二级品类 |
| `brand_norm` | categorical | brand alias dict | feature_pipeline | retrieval/filter/rerank | alias version | alias coverage | 规范化品牌 |
| `price` | numeric | `base_price` / SKU | product_repo | budget_fit/display | daily | >0 check | 商品基础价 |
| `capacity_mAh` | numeric | title/SKU/FAQ extraction | feature_pipeline | policy/scoring | dataset version | unit check | 电池容量 |
| `power_watt` | numeric | title/SKU/FAQ extraction | feature_pipeline | compatibility/scoring | dataset version | unit check | 最大输出功率 |
| `review_sentiment` | categorical | review NLP | review_pipeline | risk/rerank | dataset version | label enum | 评论情绪 |
| `risk_tags` | list | review/policy extraction | risk_pipeline | Decision/Harness | dataset version | tag enum | 风险标签 |
| `policy_type` | categorical | policy rules | policy_pipeline | policy retrieval | policy version | enum check | 航空/售后/过敏等 |
| `query_intent` | categorical | RouterAgent | runtime | retrieval plan | per request | enum check | 用户意图 |
| `rrf_score` | numeric | retriever | retrieval | ranking eval | per request | range check | 融合召回分 |
| `rerank_score` | numeric | QwenReranker | reranker | ranking/trace | per request | range check | 精排相关性分 |

### 10.3 Feature Governance 机制

| 治理项 | 建议规则 | 落地方式 |
|---|---|---|
| Feature Schema | 所有特征必须有 name/type/source/confidence/version | `schemas/feature.py` |
| Feature Dictionary | 每个特征登记 owner 和 used_by | `docs/FEATURE_DICTIONARY.md` 或 JSON |
| Feature Version | 特征抽取逻辑升级时 version 增加 | `feature_v1`、`feature_v2` |
| Feature Lineage | 保存 source field、extractor、chunk_id | `feature_values.metadata` |
| Feature Quality | 缺失率、枚举合法率、单位合法率 | `scripts/check_feature_quality.py` |
| Feature Freshness | 区分静态商品特征和动态用户行为 | static/daily/realtime |
| Offline/Online | 商品特征离线，query/user/retrieval 特征在线 | feature store 分层 |
| 缺失处理 | numeric 用 null + missing flag，不随意填 0 | `capacity_missing=true` |
| 单位归一化 | mAh、Wh、W、g、ml 统一 parser | regex + unit map |
| 冲突处理 | 多来源冲突记录 confidence 和 priority | `source_priority` |
| 审计日志 | 每次重建索引记录 data_version、feature_version | `data/index_runs/*.json` |

### 10.4 特征如何被各模块使用

- Retrieval：使用 category、sub_category、brand_norm、price、scenario_tags、risk_tags 做过滤和召回增强。
- Reranker：输入 title + structured specs + top evidence summary，而不是只输入 title/category/description。
- Context Compiler：优先选择高质量、低冗余、覆盖约束的 evidence chunks。
- Decision Scoring：使用结构化 power/capacity/weight/policy/review risk 替代纯字符串匹配。
- Harness：校验必须 evidence 类型是否覆盖，如 flight query 必须包含 policy evidence。
- Android：展示 feature-derived tags，如“支持 65W”“可上飞机需确认”“低分评论提到发热”。

## 11. 数据质量问题与治理规则

| 问题 | 检测方法 | 修复方法 | 影响模块 | 优先级 |
|---|---|---|---|---|
| 缺失字段 | Pydantic + required field scan | 输出缺失报告，阻断导入 | 全链路 | P0 |
| 重复商品 | `product_id`、title hash、brand+title 相似度 | 合并或标记 duplicate | 检索、展示 | P1 |
| 商品 ID 不一致 | JSON 文件名与 `product_id` 对比 | 自动报告并修正 | evidence_id | P0 |
| 品类不统一 | category enum check | 映射到标准类目 | Router、filter | P0 |
| 品牌别名 | alias dictionary coverage | 生成 `brand_norm` | 搜索、过滤 | P0 |
| 价格格式 | 检查 numeric、>0、SKU price 范围 | 标准化 currency/price | budget_fit | P0 |
| 容量单位 | regex 抽取 ml/mAh/GB 等 | 拆 numeric + unit | spec/policy | P0 |
| 功率单位 | regex 抽取 W | 拆 numeric + unit | MacBook/快充 | P0 |
| 重量单位 | regex 抽取 g/kg | 统一为 g | 轻便/出差 | P1 |
| 评论噪声 | 长度、重复率、敏感词 | 清洗、去重 | review risk | P1 |
| 评论与商品错配 | review 中品牌/品类实体检查 | 标记低置信度 | Evidence | P1 |
| FAQ 重复 | question hash / semantic duplicate | 去重并合并 | FAQ Recall | P1 |
| 政策规则过期 | `effective_at` / `expires_at` | 更新 policy version | policy check | P0 |
| 图片 URL 不可用 | 文件存在性检查 | 缺图占位或补图 | Android/Visual | P0 |
| 视觉字段缺失 | VisualResult confidence + field coverage | fallback query，不入库低置信字段 | Visual RAG | P1 |
| evidence_id 不稳定 | 基于数组下标检测 | hash-based stable ID | Harness/eval | P0 |
| metadata 不完整 | chunk metadata required check | 默认值 + missing flag | filter/eval | P0 |

## 12. RAG 与检索评测体系设计

### 12.1 为什么必须分层评测

召回是天花板。如果正确 product 或 evidence 没有进入 Top-K，后续 Reranker、LLM、Decision Scoring 再强也无法稳定答对。因此评测必须按以下顺序拆开：

```text
检索召回
  -> 重排质量
  -> 证据正确性
  -> Context 质量
  -> 生成忠实度
  -> 决策正确性
  -> 端到端任务成功
```

不能只看最终回答是否“看起来合理”。

### 12.2 Golden Evaluation Set 设计

建议将 `data/golden_queries.json` 升级为如下结构：

```json
{
  "query_id": "q_001",
  "query": "我用 MacBook 出差，想买能上飞机的充电宝",
  "user_profile": {
    "devices": ["MacBook", "iPhone 15"],
    "budget_max": 300,
    "scenario": ["business_trip", "flight"]
  },
  "image_case": null,
  "gold_product_ids": ["p_digital_xxx"],
  "gold_evidence_ids": ["ev_policy_flight_xxx", "ev_spec_power_xxx"],
  "gold_policy_ids": ["policy_flight_powerbank_100wh"],
  "gold_review_ids": ["review_xxx"],
  "expected_constraints": ["capacity_wh <= 100", "power_watt >= 45"],
  "expected_risks": ["flight_limit", "insufficient_power"],
  "ideal_answer_points": [
    "说明是否能带上飞机",
    "说明是否能给 MacBook 充电",
    "引用政策或 FAQ 证据",
    "给出风险提醒"
  ],
  "failure_tags": ["policy_missing", "wrong_capacity", "no_macbook_power"]
}
```

### 12.3 分层指标

#### 检索层

| 指标 | 定义 | 计算方式 | 需要数据 | 失败归因 | 优化方向 |
|---|---|---|---|---|---|
| Recall@K | gold evidence/product 是否被召回 | `hit_gold / total_gold` | gold ids、retrieved ids | query rewrite、index、metadata filter | chunk、词典、多路召回 |
| Hit@K | Top-K 是否至少命中一个 gold | `1/0` | gold ids | 召回失败 | 扩大 top_k、query expansion |
| MRR | 第一个正确结果排名倒数 | `1/rank` | 排名列表 | 排序差 | rerank、RRF 调参 |
| NDCG@K | 多相关性排序质量 | DCG/IDCG | relevance label | 排名不优 | reranker、feature score |
| Context Precision | Top-K 中有用 evidence 比例 | useful / K | evidence label | 噪声过多 | filter、dedup |
| Duplicate Rate | 重复或近重复 evidence 比例 | dup / K | content hash | chunk 重复 | 去重 |
| Latency | 检索耗时 | ms | trace | 性能瓶颈 | cache、索引 |

#### 重排层

| 指标 | 定义 | 计算方式 | 需要数据 | 优化方向 |
|---|---|---|---|---|
| Rerank Recall@K | rerank 后 Top-K 是否保留 gold | hit_gold_after / total_gold | rerank list | 保留召回池、top_n 调参 |
| MRR/NDCG | 精排排名质量 | 同上 | relevance label | 输入文档格式优化 |
| Pairwise Ranking Accuracy | gold 是否排在 negative 前 | correct_pairs / all_pairs | pair labels | hard negative |
| Top-1 Accuracy | 第一名是否 gold | 1/0 | gold product | reranker + decision |

#### 证据层

| 指标 | 定义 | 计算方式 | 优化方向 |
|---|---|---|---|
| Evidence Coverage | 是否覆盖 spec/review/policy/visual | covered_types / required_types | policy-first、review-first |
| Evidence Correctness | evidence 是否支持结论 | 人工或规则标注 | citation_text、chunk quality |
| Citation Accuracy | 引用文本与原文一致 | exact/semantic match | span 保留 |
| Evidence Diversity | 来源类型多样性 | unique source_type | RRF diversity |
| Policy Evidence Recall | 政策类 gold 命中率 | hit policy / gold policy | 独立 policy collection |
| Review Evidence Recall | 评论类 gold 命中率 | hit review / gold review | review chunk index |

#### Context 层

| 指标 | 定义 | 计算方式 | 优化方向 |
|---|---|---|---|
| Context Completeness | 是否包含回答必需信息 | required points coverage | context selector |
| Context Redundancy | 重复 token 比例 | duplicate text / total | dedup |
| Context Conflict Rate | 上下文互相矛盾比例 | conflict pairs | source priority |
| Token Efficiency | 每 1k token 支持多少有效证据 | useful evidence / token | compression |
| Constraint Coverage | 预算/设备/场景/政策是否都覆盖 | covered constraints / expected | constraint-aware context |

#### 生成层

| 指标 | 定义 | 计算方式 | 优化方向 |
|---|---|---|---|
| Faithfulness | 回答是否忠实于 evidence | LLM judge + rule check | stronger citation |
| Answer Relevance | 是否回答用户问题 | judge/manual | prompt/context |
| Context Utilization | 是否使用关键 evidence | cited key evidence / gold | citation instruction |
| Hallucination Rate | 无依据断言比例 | unsupported claims / claims | guard |
| Risk Coverage | 风险点是否提到 | hit expected risks | risk evidence |

#### 决策层

| 指标 | 定义 | 计算方式 | 优化方向 |
|---|---|---|---|
| Constraint Violation Rate | 推荐违反硬约束比例 | violations / recommendations | hard filter |
| Ranking Accuracy | 推荐排序与 gold/human 一致 | NDCG / pairwise | scoring weights |
| Human Preference Agreement | 与人工选择一致度 | agreement rate | preference features |
| Score Calibration | 分数与正确率相关性 | calibration curve | score weight tuning |
| Risk Miss Rate | 应提示风险但未提示 | missed risks / expected risks | risk mining |

#### 端到端层

| 指标 | 定义 | 采集方式 | 优化方向 |
|---|---|---|---|
| Task Success Rate | 用户任务是否完成 | golden case + manual review | 全链路 |
| Recommendation Acceptance | 推荐是否被加购 | action logs | personalization |
| Manual Review Score | 人工评分 | 1-5 scale | answer quality |
| Error Attribution | 失败归因分布 | trace + labels | 优先修最高频问题 |

## 13. 数据集优化方案

| 优化项 | 为什么做 | 怎么做 | 改哪些数据 | 影响代码模块 | 预期提升 | 优先级 |
|---|---|---|---|---|---|---|
| 商品字段补全 | 缺库存、销量、版本影响评分 | 增加 availability、sales_count、data_version | product JSON/PG | Product schema、ProductModel | Decision Accuracy | P0 |
| 商品参数结构化 | 字符串难做硬约束 | regex + LLM extraction 生成 specs | title/SKU/FAQ | feature pipeline、scoring | Constraint Coverage | P0 |
| 品牌/类目标准化 | 同义词影响召回 | alias dictionary | brand/category | Router、Retriever | Recall@K | P0 |
| 单位归一化 | 功率/容量/重量是核心决策特征 | parse unit to numeric | SKU/title/FAQ | scoring、policy | Policy Recall | P0 |
| 评论清洗 | 评论是风险来源 | 去重、长度过滤、aspect 抽取 | user_reviews | review_channel | Evidence Correctness | P1 |
| 评论风险标签 | 支持风险解释 | 抽取 heat/heavy/quality/fake 等 | user_reviews | DecisionScoring | Risk Coverage | P0 |
| FAQ 去重 | 减少重复上下文 | question hash + semantic dedup | official_faq | chunk builder | Token Efficiency | P1 |
| 政策规则结构化 | 飞机/售后等必须可验证 | 建 `policy_rules.json` | FAQ/manual policy | policy retrieval | Policy Evidence Recall | P0 |
| 航空规则建模 | 充电宝 Demo 核心 | Wh、mAh、V、approval rules | policy_rules/specs | scoring/harness | Constraint Violation Rate | P0 |
| 设备兼容规则 | MacBook/iPhone 场景关键 | device_power_requirements | policy/spec | compatibility | Task Success | P1 |
| 商品场景标签 | 出差/通勤/户外排序 | scenario_tags extraction | product chunks | retrieval/scoring | NDCG | P1 |
| 用户偏好标签 | 个性化推荐 | LongTermMemory profile features | user profile | retrieval/scoring | Acceptance | P2 |
| evidence chunk 生成 | RAG 基础资产 | 每 FAQ/review/spec 一 chunk | derived chunks | vector repo/context | Evidence Coverage | P0 |
| metadata 增强 | 支持过滤和评测 | payload 加 source_type/category/brand | Qdrant payload | qdrant repo | Context Precision | P0 |
| 视觉解析入库 | 支持 visual-aware retrieval | VisualResult -> visual evidence chunk | uploads/visual | vision/retrieval | Visual Recall | P2 |
| golden eval set | 衡量优化效果 | 标注 gold product/evidence/policy | data/golden_queries | eval API | 可验证性 | P0 |
| hard negative | 提升 reranker | 构造相似但错误商品 | eval set | reranker eval | Pairwise Accuracy | P1 |
| 数据版本管理 | 支持回滚和复现 | data_version/source_hash | all derived data | seed/index scripts | Reproducibility | P0 |

## 14. 结合代码的短期优化路线图

| 优先级 | 任务 | 涉及数据 | 涉及代码 | 预期指标提升 | 工作量 | 风险 |
|---|---|---|---|---|---|---|
| P0 | 数据集字段盘点脚本 | product JSON/images | `scripts/check_dataset_quality.py` | 数据质量可见 | 小 | 低 |
| P0 | evidence_id 稳定化 | FAQ/review/spec | chunk builder、RetrievalAgent | Citation Accuracy | 中 | 中 |
| P0 | metadata schema 统一 | chunks/Qdrant payload | `schemas/evidence.py`、vector repo | Context Precision | 中 | 中 |
| P0 | Golden Eval Set 升级 | `data/golden_queries.json` | `api/eval.py` | 可验证优化 | 中 | 低 |
| P0 | Recall@K/MRR/NDCG 脚本 | gold labels | `scripts/eval_retrieval.py` | 检索天花板可测 | 中 | 低 |
| P0 | RAG 检索链路 Trace | retrieval outputs | RetrievalAgent、TraceStep | Error Attribution | 小 | 低 |
| P1 | chunk 粒度优化 | FAQ/review/spec | chunk builder、seed_qdrant | Recall@K | 中 | 中 |
| P1 | 商品参数结构化 | title/SKU/FAQ | feature extractor、scoring | Constraint Coverage | 中 | 中 |
| P1 | 评论风险标签 | reviews | review pipeline | Risk Coverage | 中 | 中 |
| P1 | 政策规则结构化 | FAQ/manual policy | policy repo | Policy Recall | 中 | 中 |
| P1 | hybrid search 接入主 Workflow | Qdrant vectors | RetrievalAgent._text_channel | Recall/NDCG | 小 | 中 |
| P1 | RRF 权重调优 | eval traces | TextRetriever._rrf_fusion | NDCG | 小 | 低 |
| P1 | reranker 输入优化 | product + evidence summary | workflow._node_reranker | MRR/NDCG | 小 | 低 |
| P2 | 特征字典 | feature metadata | docs/schema/scripts | 治理能力 | 中 | 低 |
| P2 | 特征质量检测 | derived features | scripts/check_feature_quality.py | Feature Reliability | 中 | 低 |
| P2 | preference-aware retrieval | user profile | LongTermMemory、RetrievalPlan | Acceptance | 中 | 中 |
| P2 | visual-aware retrieval | VisualResult | VisualAgent、RetrievalAgent | Visual Recall | 中 | 中 |
| P2 | policy-first retrieval | policy_rules | RetrievalAgent、policy repo | Policy Recall | 中 | 中 |
| P2 | evidence diversity | chunks | rerank/context selector | Diversity | 中 | 低 |
| P2 | feature store 雏形 | feature_values | PG schema/repo | 复用性 | 中 | 中 |
| P3 | GraphRAG | product-evidence-risk graph | `graph/evidence_graph.py` 扩展 | Explainability | 大 | 中 |
| P3 | 用户行为反馈闭环 | action logs | cart/checkout/memory | Personalization | 大 | 高 |
| P3 | 个性化排序模型 | training logs | offline training | Ranking Accuracy | 大 | 高 |
| P3 | 自动化数据质量监控 | all datasets | CI scripts | 稳定性 | 中 | 低 |
| P3 | 大规模商品扩展 | 1000+ 商品 | ingestion/index/db | Scalability | 大 | 中 |

## 15. 当前最值得优先优化的 10 个问题

1. 主 Workflow 未接入 `hybrid_search()`，Qdrant 不在主要推荐路径中发挥作用。
2. `seed_qdrant.py` 中 async embedding 调用未 await，批量向量索引脚本需要修复。
3. evidence_id 基于数组下标，FAQ/Review 顺序变化会导致证据 ID 不稳定。
4. Qdrant payload metadata 太少，无法支持 category/source_type/policy filter。
5. FAQ、评论、政策没有独立 chunk，RAG 粒度过粗。
6. `data/golden_queries.json` 未接入 Eval API，评测口径分散。
7. `products.rag_knowledge` 全塞 JSONB，后续 review/policy/evidence 统计困难。
8. 数据集商品数与图片数、文档口径不一致，缺少自动质量检查。
9. Decision Scoring 依赖字符串命中，缺少结构化参数特征。
10. `DecisionHarness` 未接入主 workflow，Harness 能力和展示口径需要统一。

## 16. 可以直接开会讨论的 10 个问题

1. V1 主链路是否应默认启用 hybrid search，还是按环境变量启用？
2. evidence chunk 是否先落 JSONL，再同步 PG/Qdrant，还是直接入库？
3. FAQ 和 policy 是否拆表，还是先在 JSONB 中加 `faq_type/policy_type`？
4. 充电宝航空规则是否作为第一个结构化 policy demo？
5. Golden Eval Set 先做 30 条高质量标注，还是扩展到 100 条？
6. Reranker 输入应使用商品摘要，还是商品 + Top evidence 拼接？
7. Android Evidence Panel 是否必须展示 citation_text 原文？
8. Decision Score 的 7 个维度是否加入 policy_match / compatibility_match？
9. 用户偏好是只影响排序，还是也影响召回 query 和 filter？
10. 数据版本管理采用文件级 hash、chunk 级 hash，还是 PG migration + index version 双轨？

## 17. 后续开始编码时建议的小任务

1. 新增只读数据质量扫描脚本，输出商品数、图片缺失、FAQ/Review 数、字段缺失。
2. 修复 `scripts/seed_qdrant.py` async embedding 调用，确保能真实写入 Qdrant。
3. 新增 `EvidenceChunk` schema 和 JSONL 构建脚本，先覆盖 FAQ、Review、Marketing 三类。
4. 将 Qdrant payload 扩展为 chunk metadata，并支持 `source_type/category/product_id` filter。
5. 将 `RetrievalAgent._text_channel()` 配置化切换到 `hybrid_search()`。
6. 升级 `data/golden_queries.json`，补充 gold product/evidence/policy IDs。
7. 新增 `scripts/eval_retrieval.py`，计算 Recall@K、MRR、NDCG。
8. 在 Retrieval trace 中记录 query rewrite、channel、top_k、hit product/evidence IDs、latency。
9. 拆出 policy rules JSON，优先实现航空规则和 MacBook 供电规则。
10. 将 `DecisionHarness.validate()` 接入 `workflow/graph.py` 的 guard 前或 guard 后，统一 Harness 报告。

## 18. 修改文件清单

本任务不允许修改代码，因此本次只新增分析文档：

- `docs/DATASET_FEATURE_RAG_OPTIMIZATION_ANALYSIS.md`

