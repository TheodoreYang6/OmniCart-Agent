# ADR 0002：Memory 统一到 MemoryBank + 多路召回 + LLM/规则写入整合

- 状态：已采纳
- 日期：2026-07

## 背景

三层记忆（短期 `conversation_service` / 长期 `user_profile_service` 条目 / 会话）各自为政，
无统一接口。长期偏好召回只是「品类关键词命中 → 全量条目拼接」，无排序、无多路；写入是
「每次新建条目、无去重」，导致同品类偏好冗余、`喜欢/避雷`同品牌可能并存冲突。
`used_memories` 结构化通道长期空置。

## 决策

借鉴 amap `libs/memory_bank`：

- 框架层 `framework/memory/`：`MemoryBank`（rewrite → 多 Provider 并行召回 → 汇总）+
  `DefaultRecallEngine`（N 路并发 → Fusion → Rerank → top_n）+ `TagPath/RecencyPath` +
  `RRFFusion/SimpleMergeFusion` + `MMRReranker/NoopReranker`。
- 实现层 `providers/memory/`：`preference` / `short_term` / `conversation_history` 三 Provider
  统一由一个 `MemoryBank` 编排；`PreferenceWriter` 做写入整合。

## 关键取舍

- **偏好召回升级为多路 + RRF**：`TagPath`（query/tags 与条目标签 Dice 重合）+ `RecencyPath`
  （更新时间衰减）→ RRF 融合。`inject_profile_hints` 内部改由 MemoryBank 排序驱动，但
  **对外契约字节级不变**（下游 hints 对品牌/标签做集合去重，排序不影响输出集合）——零风险接入。
- **写入整合用规则而非 LLM**：8 字段小 schema 下，规则化去重/冲突（`find_mergeable` +
  `merge`，新表述胜出）比 LLM 更可靠、可单测、零延迟；接口预留可替换为 LLM。
- **不激活 `used_memories` 品牌加成**：现偏好经 `context_prompt` 已注入并被 `decision` 提取
  `preferred_brands`，若再填 `used_memories` 会**双重计分**，故保持其空置，评分行为不变。

## 影响

`inject_profile_hints` 输出不变；新增：`parse_and_save` 新条目走去重整合（减少冗余）。
纯逻辑单测见 `tests/unit/test_memory_framework.py`。
