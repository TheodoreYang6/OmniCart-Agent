# OmniCart Agent 协同设计文档

## 概述

OmniCart 采用 **Workflow-controlled Multi-Agent** 架构（非开放式 ReAct）。5 个 Agent 通过 LangGraph StateGraph 有向图编排，每个 Agent 职责单一、输入输出明确、失败有降级。相比自由 ReAct 循环，这种设计可控性强、延迟可预测、便于追踪调试。

### 架构优势

- **可控性**: 每个节点有明确的输入/输出 Schema，不会出现 Agent 自由循环无法收敛
- **可观测性**: 每个节点产生 TraceStep，可在 Android AgentInsightSheet 中逐步查看
- **可优化性**: 节点间可以并行（Router∥Visual）、可以跳过（chitchat 直通 Response）、可以缓存
- **鲁棒性**: 每个节点独立降级，单点失败不影响全链路

---

## Agent 总览

| Agent | 模型/方式 | 核心职责 | 关键输出 |
|-------|----------|---------|---------|
| **Router** | qwen-turbo + 规则兜底 | 意图识别、约束提取、检索计划 | intent, category, budget, scenario, spec_keywords, must_tags, exclude_tags |
| **Visual** | qwen-vl-max | 图像解析、品类映射、DB精确匹配 | product_name, brand, category, confidence, visual_matched_pids |
| **Retrieval** | text-embedding-v4 + qwen3-rerank | 语义检索、精排、证据补充 | retrieved_products, evidence_list |
| **Decision** | 7维加权公式 + 规则 | 评分、避雷过滤、推荐等级 | decision_results (score, reason, level, risks) |
| **Response** | qwen-turbo + 模板兜底 | 上下文编译、回答生成 | answer (自然语言) |

三个基础设施节点：**Reranker** (精排)、**EvidenceCheck** (证据充分性)、**Guard** (回答守门)。

---

## Workflow 编排

### 完整流程图

```
                        ┌─────────────────────┐
                        │       START          │
                        └──────────┬──────────┘
                                   │
                        ┌──────────▼──────────┐
                        │    Router Agent      │
                        │  intent + constraints│
                        └──────────┬──────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
     intent=chitchat        has image              normal
              │                    │                    │
              │         ┌──────────▼──────────┐         │
              │         │   Visual Agent       │         │
              │         │  (∥ Router 并行)      │         │
              │         └──────────┬──────────┘         │
              │                    │                    │
              │                    ▼                    ▼
              │         ┌─────────────────────────────────┐
              │         │       Retrieval Agent            │
              │         │  semantic search + constraints   │
              │         └──────────────┬──────────────────┘
              │                        │
              │                        ▼
              │         ┌─────────────────────────────────┐
              │         │          Reranker               │
              │         │    qwen3-rerank 精排            │
              │         │  (快速模式跳过)                   │
              │         └──────────────┬──────────────────┘
              │                        │
              │                        ▼
              │         ┌─────────────────────────────────┐
              │         │     Evidence Sufficiency        │
              │         │     检查证据类型覆盖              │
              │         └──────────────┬──────────────────┘
              │                        │
              │              ┌─────────┴─────────┐
              │              │                   │
              │        has products         no products
              │              │                   │
              │              ▼                   │
              │   ┌──────────────────┐           │
              │   │  Decision Agent   │           │
              │   │ 7维评分+避雷+等级 │           │
              │   └────────┬─────────┘           │
              │            │                     │
              └────────────┼─────────────────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │   Response Agent     │
                │ LLM生成 / 模板兜底    │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │    Response Guard    │
                │ 幻觉/证据/价格/风险   │
                └──────────┬──────────┘
                           │
                           ▼
                ┌─────────────────────┐
                │        END          │
                └─────────────────────┘
```

### 条件路由逻辑

```python
# router → next
if intent == "chitchat":        → Response (跳过检索)
elif image_url exists:          → Visual
else:                           → Retrieval

# evidence_check → next
if retrieved_products:          → Decision
else:                           → Response (直接返回空结果)
```

### 性能优化

| 优化项 | 方式 | 效果 |
|--------|------|------|
| Router∥Visual 并行 | 有图片时 `asyncio.create_task` 同时执行 | 省 1-3s |
| 品类预填跳过 LLM | 追问时 category+sub_category 已确定 | 省 1s |
| 快速模式 | 跳过 Router LLM + Reranker + Response LLM | 省 3-6s |
| Router Redis 缓存 | 相同 query 30min 内直接返回 | 省 1s |
| Reranker 跳过 | 单商品或快速模式时跳过 | 省 0.3s |

---

## Router Agent — 意图识别与约束提取

### 双路径架构

```
用户Query
  ├── 规则解析(_rule_based_parse): 0ms
  │   ├── 闲聊词库匹配 → chitchat
  │   ├── 购物操作词库 → shop_action
  │   ├── 对比关键词 → compare
  │   ├── 品类检测(detect_category)
  │   ├── 预算提取(detect_budget)
  │   ├── 场景检测(detect_scenario)
  │   └── 避雷提取(4条正则)
  │
  └── LLM增强(qwen-turbo): ~1s
      ├── 补充 sub_category/must_tags/spec_keywords
      ├── 理解追问语义
      └── 失败时静默降级到规则结果
```

### 约束提取能力

从自然语言中提取结构化约束：

| 约束类型 | 示例输入 | 提取结果 |
|----------|---------|---------|
| 品类 | "推荐蓝牙耳机" | category=数码电子, sub_category=真无线耳机 |
| 预算 | "200以内的跑鞋" | budget_max=200, category=服饰运动 |
| 场景 | "出差用的充电宝" | scenario=business_trip, keywords=["便携","大容量","快充"] |
| 排除 | "不要含酒精的，不要日系品牌" | exclude_tags=["含酒精的","日系品牌"] |
| 品牌偏好 | "喜欢苹果华为" | must_tags=["Apple","华为"] |
| 品质规格 | "降噪好的耳机" | spec_keywords=["降噪","音质","续航"...] |

### 关键设计决策

**规则优先，LLM增强**: 规则解析提供可靠基础(0ms)，LLM补充细节。规则确定的意图类型(chitchat/shop_action/risk_check)不被LLM覆盖，防止LLM误判。

**Prompt 持续优化**: 从1200 tokens压缩到740 tokens，品类列表从4行详细子类压缩为1行；spec_keywords从8-12个减到3-5个；删除3个死字段(need_visual/policy_check/compatibility_check)。

**上下文注入**: 每轮对话后，Router通过`_build_session_context`将上轮品类/预算/场景/商品列表注入LLM prompt，使追问理解准确。

---

## Visual Agent — 多模态商品识别

### 处理流程

```
图片上传 → Qwen-VL-Max 解析 → 结构化 VisualResult
  → confidence ≥ 0.5: 精确匹配(品牌ILIKE+产品名OR) → visual_matched_pids
  → confidence ≥ 0.2: 品类映射→引导搜索，不精确匹配
  → confidence < 0.2: 忽略视觉结果
```

### 全品类 Prompt 设计

Prompt 对齐数据集全部 210 件商品、4 大品类、42 子类，示例覆盖：

- 数码电子: 真无线耳机/智能手机/平板电脑/笔记本电脑/移动电源/充电器
- 美妆护肤: 精华/面霜/防晒/化妆水/眼霜/面膜/粉底液/蜜粉/唇釉/眉笔/洁面/卸妆
- 服饰运动: 跑步鞋/篮球鞋/徒步鞋/短袖T恤/速干T恤/卫衣/运动长裤/背包/帽子
- 食品饮料: 咖啡/牛奶/酸奶/碳酸饮料/功能饮料/茶饮/方便食品/坚果零食

不在支持类别内的商品(鼠标/键盘/家电等)guidance设confidence < 0.3。

### 品类映射

`_map_visual_category` 覆盖 80+ 子类→4大类的映射，用子串模糊匹配保证覆盖率：

```python
"鼠标" → 数码电子, "精华" → 美妆护肤, "跑鞋" → 服饰运动, "咖啡" → 食品饮料
```

### 精确匹配策略

品牌名 ILIKE + 产品名 2-3 字滑窗 OR 匹配，容忍数据库名称与识别结果的差异(如"特润修护精华" vs "特润修护肌活精华露")。

### 检索置顶

匹配到的商品在检索结果中置顶，Reranker分数锁定0.99，确保不被后续精排翻盘。

### 并行优化

有图片时 Router 和 Visual 并行执行(`asyncio.create_task`)，省 1-3s。

---

## Retrieval Agent — 多通道检索与精排

### 三阶段检索

```
Phase 1: 语义检索
  Query → text-embedding-v4(1024d) → Qdrant ANN → top_k*3 候选

Phase 2: 约束过滤
  品类/子品类/价格范围 → 过滤候选集 → top_k

Phase 3: 精排
  Qwen3-Reranker → 分数校准(0.68+0.38*score) → 最终排序
```

### 多通道证据补充

商品检索完成后，三通道并行补充证据：

| 通道 | 内容 | 方式 |
|------|------|------|
| text | 商品描述匹配 | 语义检索 |
| review | 用户评价 | Embedding余弦相似度匹配chunk |
| policy | 政策/FAQ | 同上 |

### 降级策略

```
Qdrant不可用 → 本地余弦相似度
Embedding API失败 → 关键词子串匹配
Reranker失败 → 维持检索原始排序
```

### 检索优化

- **Router丰富度判断**: 有category即跳过LLM关键词提取，直接用Router输出拼接搜索词
- **搜索词构建**: category + sub_category + must_tags + spec_keywords 拼接
- **Chunk检索**: 支持商品分块检索+聚合，适合长商品描述

---

## Decision Agent — 7维评分与推荐决策

### 评分公式 (V4)

```
raw_score = 0.45 × relevance        (RAG语义相关度)
          + 0.20 × budget_fit       (价格适配度)
          + 0.12 × user_sat         (用户口碑, 贝叶斯校正)
          + 0.10 × value_score      (性价比, 子品类基准)
          + 0.08 × spec_quality     (规格技术信号)
          + 0.05 × scenario_fit     (场景关键词命中)
          + preference_bonus        (用户偏好加成, ≤0.10)
          - risk_penalty            (差评扣分, ≤0.20)
          - avoid_penalty           (避雷扣分, ≤0.10)
```

### 推荐等级判定

| 等级 | 条件 |
|------|------|
| strong_recommend | score ≥ 0.80 + evidence ≥ 0.50 + risk < 0.10 |
| recommended | score ≥ 0.65 |
| cautious | score ≥ 0.55 或 risk ≥ 0.20 |
| insufficient_evidence | evidence < 0.25 |
| not_recommended | hard_constraint_failed |

### 避雷硬过滤

检索阶段从 `retrieved_products` 中直接移除匹配 `exclude_tags` 的商品(title/brand含避雷标签)。不再使用软降权——语言识别准确后硬过滤更安全。

### 品牌别名展开

60+品牌中英文双向映射(`BRAND_ALIASES`)，用户说"不要Nike"自动展开为`["Nike","耐克"]`，确保中英文品牌名都能被过滤。

---

## Response Agent — 回答生成与兜底

### 双路径策略

```
FAST_MODE=false:
  LLM生成(qwen-turbo, 6s超时) → 校验(长度≥10 + 引用商品)
  → 成功: 返回LLM回答
  → 失败/超时: 模板兜底

FAST_MODE=true (快速模式):
  模板生成 → 直接返回 (不调LLM)
```

### 模板回答

快速模式下纯模板生成，输出格式简洁：

```
帮你挑了几款～

阿迪达斯 adidas Originals 三叶草 男子连帽卫衣
   ¥459

Nike Sportswear Club 男子针织运动长裤
   ¥349
```

视觉识图场景有专门模板：识别到同款→"就是这款～"，无同款→"库内暂无同款，看看这些相近的～"。

### Context Compiler

将 WorkflowState 编译为结构化上下文供 LLM 使用：
- 用户 query + constraints
- 候选商品列表 (name/brand/price/score)
- 证据摘要 (review/FAQ)
- 风险摘要
- 偏好上下文

---

## Response Guard — 5项守门检查

| 检查项 | 逻辑 | 硬失败 |
|--------|------|--------|
| evidence_bound | 回答是否引用商品品牌/标题关键词 | 否 |
| price_accurate | 提到商品时价格是否正确 | 否 |
| risk_warned | 有风险项时回答是否提醒 | 否 |
| honest_on_empty | 无商品时是否诚实告知 | **是** |
| hallucination | 是否提到非检索结果的品牌 | **是** |

幻觉检测支持品牌别名、否定语境豁免、用户提及豁免。硬失败项触发时写入harness_report并日志告警。

---

## 状态管理

### WorkflowState

所有 Agent 间传递的信息通过 WorkflowState (Pydantic BaseModel)：

```python
class WorkflowState(BaseModel):
    user_query: str
    image_url: str | None
    intent: str
    constraints: Constraints
    retrieval_plan: RetrievalPlan
    retrieved_products: list[dict]
    evidence_list: list[dict]
    decision_results: list[dict]
    visual_result: dict | None
    visual_matched_pids: list[str]
    answer: str
    trace_steps: list[dict]
    harness_report: dict
    timing: dict
    context_prompt: str
    session_id: str
    conversation_id: str
```

### TraceStep 追踪

每个节点执行后生成 TraceStep：

```json
{
  "step_id": "T001",
  "agent_name": "Router Agent",
  "action": "intent_and_constraints",
  "input_summary": "蓝牙耳机推荐",
  "output_summary": "intent=recommend, cat=数码电子",
  "latency_ms": 1200,
  "status": "success"
}
```

Android AgentInsightSheet 可逐步骤查看完整追踪链。

---

## 关键设计原则

1. **不开放 ReAct**: Agent 不能自由决策下一步，严格按 Workflow 编排走
2. **证据绑定**: 所有推荐结论必须有 evidence_ids，Response Guard 强制执行
3. **失败降级**: 每个节点独立降级，单点故障不阻塞全链路
4. **工具只读**: V1 所有工具不执行下单/支付/账号操作
5. **用户数据隔离**: 购物车/地址/偏好/订单全部绑定 user_id
