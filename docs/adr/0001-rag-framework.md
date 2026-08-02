# ADR 0001：RAG 框架化（RecallSource + 6 阶段编排器）

- 状态：已采纳
- 日期：2026-07

## 背景

原实现里，RAG 的三通道（text/review/policy）+ 补充召回 + query 改写全部内联在
`retrieval_agent.py`（~450 行），rerank/避雷/视觉置顶散落在 `graph.py`。无统一检索接口、
无多源注册、query 改写不可插拔，扩展一个召回源需改动 Agent 主体。

## 决策

借鉴 amap `libs/knowledge_base`，做**框架-实现分离**：

- 框架层 `framework/retrieval/`：`RecallSource` ABC + `RetrievalQuery/Result/Bundle` +
  `RetrievalOrchestrator`（6 阶段：改写→激活→并行+双超时→处理→融合→兜底/增强）+
  `SourceRegistry`（`builtin()` 清单装配）+ `RRFFusion/SequentialFusion` + `QueryRewriter`。
- 实现层 `providers/recall/`：`Semantic`(recall) / `Supplementary`(fallback) /
  `Review`+`Policy`(enrich) 四个 `RecallSource` + `LLMKeywordRewriter`。
- `RetrievalAgent` 瘦身为「构建 query → 调 orchestrator → 写回 state」。

## 关键取舍

- **双超时**：per-source `latency_budget_ms` + 整体 `time_budget`，`required` 失败上抛、
  `optional` 失败降级。生产 `time_budget=8000ms`（高于真实最坏延迟，不误伤）。
- **SemanticRecallSource `is_required=False`**：忠实现有行为——检索失败内部降级到空结果，
  再由 Response 模板兜底，**从不因检索失败中断 SSE**。
- **默认 `SequentialFusion`（不重排）**：保持与旧实现商品顺序一致；`RRFFusion` 作为可选策略。
  LLM Reranker 仍留在 graph 节点，本次不动，保证主链路排序字节级一致。
- 修正了 `SupplementaryRecallSource` 的 chunk 缓存路径笔误（`backend/backend/data` → `backend/data`）。

## 影响

产出的 `retrieved_products` / `evidence_list` 结构不变，Decision/Guard/Android 无感。
新增召回源只改 `providers/recall/builtin()`。协议级单测见 `tests/unit/test_retrieval_framework.py`。
