# OmniCart Agent 评分体系完整参考文档

**版本**: V4 | **日期**: 2026-06-09 | **状态**: 生产级

---

## 目录

1. [概述](#1-概述)
2. [评分架构全景图](#2-评分架构全景图)
3. [评分公式](#3-评分公式)
4. [维度1: Relevance 语义相关度 (权重0.45)](#4-维度1-relevance-语义相关度)
5. [维度2: Budget Fit 预算匹配 (权重0.20)](#5-维度2-budget-fit-预算匹配)
6. [维度3: User Sat 用户满意度 (权重0.12)](#6-维度3-user-sat-用户满意度)
7. [维度4: Value Score 性价比 (权重0.10)](#7-维度4-value-score-性价比)
8. [维度5: Spec Quality 规格品质 (权重0.08)](#8-维度5-spec-quality-规格品质)
9. [维度6: Scenario Fit 场景适配 (权重0.05)](#9-维度6-scenario-fit-场景适配)
10. [Risk Penalty 风险扣分](#10-risk-penalty-风险扣分)
11. [Recommendation Level 推荐等级](#11-recommendation-level-推荐等级)
12. [硬约束过滤](#12-硬约束过滤)
13. [DecisionResult 输出结构](#13-decisionresult-输出结构)
14. [完整数据流轨迹](#14-完整数据流轨迹)
15. [关键文件索引](#15-关键文件索引)

---

## 1. 概述

OmniCart 评分系统是一个**规则驱动、证据绑定**的多维商品评分引擎，不依赖 LLM 参与评分决策。

核心设计原则:
- **证据驱动**: relevance 来自 RAG 检索/重排分数，user_sat 来自真实评论数据
- **可复算**: 所有评分参数均可从检索结果和商品数据确定性计算
- **约束优先**: 品类/预算/场景硬约束 > 评分公式 > 偏好加成
- **避雷硬过滤**: 用户明确不要的品牌/属性在检索阶段直接移除，不在评分阶段降权

### 关键配置

| 环境变量 | 当前值 | 作用 |
|----------|--------|------|
| `OMNICART_ENABLE_EVIDENCE_SCORING` | `false` | 证据评分开关 (关闭=纯规则评分) |
| `OMNICART_ENABLE_DECISION_LLM` | `false` | LLM 评估器开关 (关闭) |
| `OMNICART_MOCK_MODE` | `false` | Mock模式 (关闭=使用真实Qwen) |
| `SCORE_VERSION` | `evidence_scoring_v1` | 评分版本标识 |

---

## 2. 评分架构全景图

```
┌──────────────────────────────────────────────────────────────┐
│                    V7 SCORING PIPELINE                        │
│                                                               │
│  SemanticRetriever.search_chunked                             │
│    → Qdrant 余弦相似度 (chunk级, 0.5-0.9)                    │
│    → max_score 聚合 → 产品级 score                            │
│                                                               │
│  DecisionAgent.execute()                                      │
│    Step 1: 从 retrieved_products 重建 Product 对象             │
│    Step 2: 硬约束检查 (_passes_hard_constraints)               │
│    Step 3: score_with_evidence() → DecisionResult             │
│                                                               │
│  SCORING FORMULA (6 维 + 风险扣分)                            │
│    raw = 0.45×relevance + 0.20×budget_fit                    │
│        + 0.12×user_sat + 0.10×value_score                    │
│        + 0.08×spec_q + 0.05×scenario_fit                     │
│        - risk_penalty                                         │
│                                                               │
│  recommendation_level (5 levels)                              │
│    → confidence_cap → final_score → display_score (×10)       │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. 评分公式

### 完整公式

```
raw =
    0.45 × relevance          ← 语义相关度 (Embedding cos-sim 校准)
  + 0.20 × budget_fit         ← 价格与预算的匹配度
  + 0.12 × user_sat           ← 用户评论评分
  + 0.10 × value_score        ← 同品类性价比
  + 0.08 × spec_quality       ← 规格品质 (LLM关键词 + richness兜底)
  + 0.05 × scenario_fit       ← 场景适配
  - risk_penalty              ← 差评风险扣分 (max 0.20)
```

### 已移除的维度 (V7 Memory Lite)

| 维度 | 原因 |
|------|------|
| `preference_bonus` (max 0.07) | MemoryRetriever + user_memories 已删除, `used_memories` 始终为空 |
| `avoid_penalty` (max 0.10) | 同上 |
| `hard_constraint: must_tags` | 改为软约束, Router LLM prompt 限定只放显式要求 |

### 范围约束

```
raw          ∈ [-∞, +∞]  → clamp → [0.0, 1.0]
final_score  ∈ [0.0, 1.0]   (经 confidence_cap 压制后)
display_score ∈ [0.0, 10.0] (final_score × 10, 保留1位小数)
```

---

## 4. 维度1: Relevance 语义相关度

**权重**: 0.45 | **方法**: `_calc_keyword_match()` | **来源**: `scoring.py:322-354`

### 取值流程

```
force_rag_relevance > 0?  → 使用 (ENABLE_EVIDENCE_SCORING=true 时)
  ↓ 否 (当前默认)
llm_relevance > 0?        → 使用 (LLM Evaluator, 默认禁用)
  ↓ 否
_calc_keyword_match()     → 关键词/语义匹配 (当前主路径)
```

### `_calc_keyword_match` 分数检测

```python
if keyword_score <= 0:
    kw_norm = 0.62                    # 无分数 → 基线
elif keyword_score < 1.0:
    kw_norm = 0.68 + 0.38 × score    # 余弦相似度 (0~1) → 校准到商业区间
else:
    kw_norm = 0.62 + 0.28 × log10(score)  # 旧关键词命中数 (>1) → 对数映射
```

### 余弦相似度校准曲线

校准公式 `0.68 + 0.38 × cos_sim` 将压缩的余弦区间拉宽到商业可读范围:

| cos_sim | 校准后 | 含义 |
|---------|--------|------|
| 0.45 | 0.85 | 一般匹配 |
| 0.55 | 0.89 | 较好匹配 |
| 0.70 | 0.95 | 优秀匹配 |
| 0.85 | 1.00 | 完美匹配 |

### 子品类匹配加成

```python
# CJK bigram 匹配: query的每个二字词在 sub_category 中出现→ +0.10
# 最大加成: 0.20
sub_bonus = min(0.20, 0.10 × 匹配的二词词数)
```

### 最终相关度

```python
relevance = min(1.0, kw_norm + sub_bonus)
```

### 数据来源链

```
用户 query → Qwen Embedding → Qdrant ANN (chunk级搜索)
  → chunk.score = cosine_similarity (0.5-0.9)
  → max_score 聚合 → product.score (0.5-0.9)
  → _calc_keyword_match(keyword_score=product.score)
  → 检测 0~1 范围 → 校准曲线映射 → relevance ∈ [0.85, 1.0]
```

---

## 5. 维度2: Budget Fit 预算匹配

**权重**: 0.20 | **方法**: `_calc_budget_fit()` | **来源**: `scoring.py:360-380`

### 计算逻辑

| 条件 | 分值 |
|------|------|
| 无预算约束 | 0.98 |
| 价格 ≤ 预算, ratio < 30% | 0.98 |
| 价格 ≤ 预算, ratio < 60% | 0.93 |
| 价格 ≤ 预算, ratio ≥ 60% | 0.92 |
| 超预算 < 20% | 0.80 |
| 超预算 < 50% | 0.60 |
| 超预算 ≥ 50% | max(0, 0.45 - overage) |

### 数据来源

```
Router Agent → state.constraints.budget_max
商品数据: product.base_price
```

---

## 6. 维度3: User Sat 用户满意度

**权重**: 0.12 | **方法**: `_calc_user_satisfaction()` | **来源**: `scoring.py:386-422`

### 计算逻辑

```python
if no reviews:
    return 0.80                         # 无评论不惩罚

reviews = product.rag_knowledge.user_reviews
score = avg(ratings) / 5.0

# Bayesian连续平滑: C=3条虚拟评论, prior=0.80
score = (score × n + 0.80 × 3) / (n + 3)

# 评论量奖励
if n ≥ 20:  score += 0.08
elif n ≥ 5: score += 0.05
elif n ≥ 2: score += 0.03

# 好评文本关键词加分
positive_keywords = ["推荐","好用","满意","回购","值得","不错","好评","喜欢","性价比","赞","棒"]
if count(评论含正面词) ≥ 3: score += 0.03

return clamp(score, 0, 1)
```

---

## 7. 维度4: Value Score 性价比

**权重**: 0.10 | **方法**: `_calc_value_score()` | **来源**: `scoring.py:428-456`

### 计算逻辑

```python
value = quality_multiplier × (0.5 × quality_score + 0.5 × price_score)
```

**quality_score**: 有评论→ `0.55 + 0.45 × (avg_rating/5.0)`; 无评论→ `0.65`

**price_score** (相对于同品类中位价):

| 价格 vs 中位价 | 分值 |
|---------------|------|
| ≤ 中位价 × 0.5 | 0.95 |
| ≤ 中位价 × 0.8 | 0.88 |
| ≤ 中位价 | 0.82 |
| ≤ 中位价 × 1.5 | 0.72 |
| > 中位价 × 1.5 | 0.58 |

### 品类基准表 (CATEGORY_BENCHMARKS)

| 子品类 | 中位价 | 品质系数 |
|--------|--------|---------|
| 真无线耳机 | 800 | 1.1 |
| 智能手机 | 4000 | 0.9 |
| 移动电源 | 150 | 1.3 |
| 跑步鞋 | 600 | 1.2 |
| 精华 | 400 | 1.0 |
| 零食/膨化 | 30 | 1.4 |
| 碳酸饮料 | 30 | 1.5 |
| ... | ... | ... |

完整29项见 `scoring.py:39-68`。

---

## 8. 维度5: Spec Quality 规格品质

**权重**: 0.08 | **方法**: `_calc_spec_quality()` + `_calc_spec_richness()` | **来源**: `scoring.py:526-584`

### 路径1: LLM spec_keywords (Router LLM 始终为此品类生成)

```python
if spec_keywords:                  # 非空时走此路径
    score = 0.82
    for kw in spec_keywords:
        if kw in full_text:
            if kw in query: score += 0.12   # 用户提到的 ×1.5
            else:           score += 0.08
    return min(1.0, score)
```

### 路径2: 兜底 — 描述文本规格丰富度

统计 4 类信号:
- **数字+单位**: 30ml, 100W, 5G, 5000mAh, 120hz...
- **技术句式标记**: 支持, 搭载, 采用, 配备, 内置, 含...
- **百分比/倍数**: 98%, 3倍, 100-200
- **规格缩写**: ANC, LDAC, IP68, SPF50, OLED...

```python
total = num_unit + tech_markers + pct_range + tech_abbr
if   total ≥ 10: return 0.96
elif total ≥ 6:  return 0.90
elif total ≥ 3:  return 0.84
elif total ≥ 1:  return 0.78
else:            return 0.74
```

---

## 9. 维度6: Scenario Fit 场景适配

**权重**: 0.05 | **方法**: `_calc_scenario_fit()` | **来源**: `scoring.py:462-520`

### 计算逻辑

```python
scenario_fit = min(1.0, base + hits × 0.10)
# base: 有场景=0.65, 无场景=0.72 (不惩罚)
```

**hits** = query CJK bigram/trigram 在商品文本中的匹配数 + 场景关键词匹配 (×2 权重)。

### 场景关键词库

| 场景 | 关键词 |
|------|--------|
| flight | 航空, 飞机, 安检, 登机, ml, 100wh, 随身, 托运 |
| commute | 轻便, 便携, 无线, 降噪, 小巧, 通勤 |
| outdoor | 防水, 耐用, 耐磨, 防滑, 透气, 户外, 登山, 轻量 |
| sport | 防水, 防汗, 运动, 无线, 轻量, 透气 |
| travel | 便携, 快充, 大容量, 航空, 轻, 旅行 |
| office | 静音, 舒适, 专业, 商务, 办公 |
... (完整12项见 scoring.py:497-510)

### 特殊处理

短查询 (≤3字): 额外做单字匹配，避免"水""耳机"等命中0个。

---

## 10. Risk Penalty 风险扣分

**减分项 (max 0.20)** | **方法**: `_calc_risk_penalty_with_evidence()` | **来源**: `scoring.py:595-623`

### 计算逻辑

```python
penalty = 0.0

if reviews exist:
    very_low = count(rating ≤ 2)     # 1-2星差评

    if very_low ≥ 3:   penalty += 0.08
    elif very_low ≥ 1: penalty += 0.02

    if len(reviews) ≥ 3:
        avg = mean(ratings)
        if avg < 3.0:   penalty += 0.05
        elif avg < 3.5: penalty += 0.02

return min(0.20, penalty)
```

### 示例

| 评论数据 | penalty |
|---------|---------|
| 5条评论, 2条1-2星, avg=3.8 | 0.02 |
| 3条评论, 3条1星, avg=1.0 | 0.13 |
| 0条评论 | 0.0 |

---

## 11. Recommendation Level 推荐等级

**方法**: `_determine_recommendation_level()` + `_apply_confidence_cap()` | **来源**: `scoring.py:262-291`

### 5 级判定树 (V7 简化版 — ENABLE_EVIDENCE_SCORING=false 时 ev_conf=0.50)

```
hard_constraint_failed?
  ├─ YES → not_recommended → cap 0.45 → display ≤ 4.5

evidence_confidence < 0.25?
  ├─ YES → insufficient_evidence → cap 0.50 → display ≤ 5.0

risk_penalty ≥ 0.20?
  ├─ YES → cautious → cap 0.80 → display ≤ 8.0

final_score ≥ 0.80 AND ev_conf ≥ 0.50 AND risk < 0.10?
  ├─ YES → strong_recommend → 无上限

final_score ≥ 0.65?
  ├─ YES → recommended → 无上限

final_score ≥ 0.55?
  ├─ YES → cautious → cap 0.80

else → not_recommended → cap 0.45 → display ≤ 4.5
```

### 等级含义

| 等级 | display_score | 含义 |
|------|-------------|------|
| strong_recommend | 8.0-10.0 | 高分 + 低风险 |
| recommended | 6.5-10.0 | 可放心推荐 |
| cautious | 5.5-8.0 | 有限顾虑 |
| insufficient_evidence | 0-5.0 | 证据太少 |
| not_recommended | 0-4.5 | 硬约束失败或极低分 |

---

## 12. 硬约束过滤

**方法**: `_passes_hard_constraints()` | **来源**: `decision_agent.py:199-236`

### 规则

```python
# 1. 预算硬上限 (超过2倍预算直接过滤)
if budget_max and price > budget_max × 2: return False

# 2. 品类精确匹配 (如果指定了)
if category and product.category != category: return False

# 3. 排除标签: 品牌品类映射 + 标题/品牌/内容三级检查
for tag in exclude_tags:
    brands_to_check = BRAND_CATEGORY_MAP.get(tag, [tag])
    if any(b in title or b in brand for b in brands_to_check): return False
    if tag in description and not preceded_by_negation(description, tag): return False

return True  # 通过
```

### V7 变更

| 旧规则 | V7 变更 |
|--------|--------|
| `must_tags` 全部匹配 | **移除**: 改为 Router prompt 限定只放显式要求 |
| LLM category 无校验 | **新增**: 品类安全校验 — 非法值回退规则结果或 None |

### 品类安全校验 (router_agent.py)

```python
VALID_CATEGORIES = {"数码电子", "美妆护肤", "服饰运动", "食品饮料"}
if llm_cat and llm_cat not in VALID_CATEGORIES:
    merged["category"] = rule_result.get("category")  # 回退
```

### 硬约束失败后果

```python
if hc_failed:
    decision.final_score = min(final_score, 0.45)
    decision.display_score = round(0.45 × 10, 1)  # 4.5
    decision.recommendation_level = "not_recommended"
    decision.hard_constraint_status = "failed"
```

---

## 13. DecisionResult 输出结构

### 完整字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `product_id` | str | 唯一标识 |
| `final_score` | float | 最终评分 [0, 1] |
| `display_score` | float | 展示评分 [0, 10] |
| `score_breakdown` | ScoreBreakdown | 7 维基础分 |
| `component_scores` | dict[9] | 9 组件含 method/evidence_ids/weight |
| `recommendation_level` | str | strong_recommend ~ not_recommended |
| `recommendation_reason` | str | 推荐理由文本 |
| `evidence_confidence` | float | 证据置信度 (当前默认 0.50) |
| `risk_factors` | list[str] | 风险提示 |
| `hard_constraint_status` | str | "pass" / "failed" |
| `score_version` | str | "evidence_scoring_v1" |

### component_scores 结构

```json
{
  "relevance":       {"score": 0.954, "weight": 0.45, "method": "...", "evidence_ids": [...]},
  "budget_fit":      {"score": 0.980, "weight": 0.20, "method": "structured_price_rule"},
  "user_sat":        {"score": 0.800, "weight": 0.12, "method": "review_rating_avg_v4"},
  "value_score":     {"score": 0.820, "weight": 0.10, "method": "subcategory_price_benchmark"},
  "spec_quality":    {"score": 0.900, "weight": 0.08, "method": "spec_signal_match"},
  "scenario_fit":    {"score": 0.720, "weight": 0.05, "method": "scenario_keyword_match"},
  "risk_penalty":    {"score": 0.000, "weight": null,  "method": "negative_review_and_low_rating"},
  "preference_bonus":{"score": 0.000, "weight": null,  "method": "memory_category_brand_scenario_match"},
  "avoid_penalty":   {"score": 0.000, "weight": null,  "method": "memory_negative_preference"}
}
```

> **注意**: `preference_bonus` 和 `avoid_penalty` 在 Memory Lite 中始终为 0（MemoryRetriever 已删除）。
> 保留字段是为了前端兼容，后续前端可隐藏这两个始终为 0 的组件。

---

## 14. 完整数据流轨迹

以下追踪 "推荐一些零食" 的完整评分实例:

### Step 1: 用户输入
```
用户: "推荐一些零食"
```

### Step 2: Router → 约束提取
```python
constraints = Constraints(
    category="食品饮料", sub_category="零食/膨化",
    budget_max=None, scenario=None,
    spec_keywords=["酥脆","口感","口味","包装","新鲜","分量","配料","好吃"],
)
intent = "recommend"
```

### Step 3: Retrieval → 语义检索
```python
# Qwen Embedding + Qdrant chunked search
retrieved_products = [
    {
        "product_id": "p_food_003",
        "title": "乐事原味薯片 大包装",
        "brand": "乐事",
        "category": "食品饮料",
        "sub_category": "零食/膨化",
        "price": 15.9,
        "score": 0.78,                     # cos_sim 余弦相似度
        "rag_knowledge": {
            "marketing_description": "经典原味薯片，精选马铃薯...",
            "user_reviews": [
                {"rating": 5, "content": "好吃不贵，每次都回购"},
                {"rating": 4, "content": "味道好分量足"},
            ],
            "official_faq": [...],
        },
    },
    # ... more products
]
```

### Step 4: Decision Agent → 评分

```python
# 硬约束检查
hc_failed = _passes_hard_constraints(product, constraints)
# category="食品饮料" == product.category → 通过
# → hc_failed = False

# 语义相关度 (ENABLE_EVIDENCE_SCORING=false → force_rag_relevance=0 → 走关键词匹配)
keyword_score = item.get("score", 0.0)  # 0.78 (cos-sim)
# _calc_keyword_match: 0.78 < 1.0 → kw_norm = 0.68 + 0.38×0.78 = 0.976
# sub_bonus: "零食" bigram in "零食/膨化" → +0.10
relevance = min(1.0, 0.976 + 0.10) = 1.0

# 各维度计算
budget_fit = 0.98       # 无预算约束
user_sat   = 0.88       # 2 reviews avg=4.5, Bayesian: (0.9×2+0.80×3)/5=0.84 + 0.03(评论量) + 0.03(好评)未触发
                        # 实际: score=(4.5/5)=0.9, n=2, C=3: (0.9×2+0.80×3)/5=0.84, n≥2 → +0.03, =0.87
value_sc   = 0.87       # quality=0.55+0.45×0.9=0.955, price_score=0.95(≤15), qm=1.4
                        # → 1.4×(0.5×0.955+0.5×0.95)=1.334→1.0 上限
                        # 实际: price=15.9, median=30, ≤0.5×30=15 → ratio=0.53, ≤0.8×30 → price_score=0.88
                        # → 1.4×(0.5×0.955+0.5×0.88)=1.4×0.9175=1.285→1.0
spec_q     = 0.90       # LLM spec_keywords: ["酥脆","口感","口味"...] → 0.82 + 1×0.08 = 0.90
scenario_fit = 0.72     # 无场景 → base=0.72, 无hits → 0.72
risk_penalty = 0.0      # 无差评

raw = 0.45×1.0 + 0.20×0.98 + 0.12×0.87 + 0.10×1.0 + 0.08×0.90 + 0.05×0.72 - 0.0
    = 0.450 + 0.196 + 0.104 + 0.100 + 0.072 + 0.036
    = 0.958

final_score = max(0.0, min(1.0, 0.958)) = 0.958
ev_conf = 0.50  (ENABLE_EVIDENCE_SCORING=false → 默认)
recommendation_level = "strong_recommend"  (0.958≥0.80 AND 0.50≥0.50 AND 0<0.10)
display_score = round(0.958 × 10, 1) = 9.6
```

### Step 5: 最终输出
```python
DecisionResult(
    product_id="p_food_003",
    final_score=0.958,
    display_score=9.6,
    recommendation_level="strong_recommend",
    evidence_confidence=0.50,
    component_scores={
        "relevance": {"score": 1.0, "weight": 0.45, ...},
        "budget_fit": {"score": 0.98, "weight": 0.20, ...},
        "user_sat": {"score": 0.87, "weight": 0.12, ...},
        "value_score": {"score": 1.0, "weight": 0.10, ...},
        "spec_quality": {"score": 0.90, "weight": 0.08, ...},
        "scenario_fit": {"score": 0.72, "weight": 0.05, ...},
        "risk_penalty": {"score": 0.0, "weight": null, ...},
        "preference_bonus": {"score": 0.0, "weight": null, ...},
        "avoid_penalty": {"score": 0.0, "weight": null, ...},
    },
)
```

---

## 15. 关键文件索引

| 文件 | 角色 |
|------|------|
| `backend/app/decision/scoring.py` | 主评分引擎: 公式、6维度、风险、推荐等级 |
| `backend/app/agents/decision_agent.py` | 编排层: 硬约束 → 评分 → 排序 |
| `backend/app/agents/router_agent.py` | 约束提取 + 品类安全校验 + LLM prompt |
| `backend/app/retrieval/semantic_retriever.py` | 语义检索: Qdrant chunk搜索 + 聚合 |
| `backend/app/decision/rules.py` | 规则库: detect_category/budget/scenario |
| `backend/app/decision/evidence_metrics.py` | 证据指标 (当前 ENABLE_EVIDENCE_SCORING=false 时不调用) |
| `backend/app/schemas/decision_result.py` | DecisionResult / ScoreBreakdown Pydantic 模型 |
| `android-client/.../DecisionResult.kt` | Android DecisionResult + ScoreBreakdown 模型 |
| `android-client/.../ScoreBreakdownPanel.kt` | Android 评分面板展示 |

### 附录: 配置项速查

| 环境变量 | 当前值 | 影响 |
|----------|--------|------|
| `OMNICART_ENABLE_EVIDENCE_SCORING` | `false` | false=跳过evidence profiles, 走纯规则评分 |
| `OMNICART_ENABLE_DECISION_LLM` | `false` | false=不使用LLM评估器 |
| `OMNICART_MOCK_MODE` | `false` | false=使用真实Qwen API |
| `OMNICART_FAST_MODE` | `false` | false=LLM生成推荐语, true=模板 |
