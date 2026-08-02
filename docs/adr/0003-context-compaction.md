# ADR 0003：Context 多源采集 + Token 预算 + 分级压缩

- 状态：已采纳
- 日期：2026-07

## 背景

上下文相关逻辑分散：`compiler.py` 手工拼 Response prompt（无 token 预算，长对话可能撑爆）；
`context_compressor.py` 每轮都调 LLM 做单级摘要（短内容也调，浪费延迟）；无多源并行采集抽象。

## 决策

借鉴 amap `libs/context_store` + `context_compaction`：

- 框架层 `framework/context/`：`ContextManager`（多源并行采集 + per-provider 超时 + 整体
  time_budget + token 预算贪心裁剪）+ `ContextProvider` ABC + `TokenEstimator`（tiktoken/字符）+
  `TierSelector`（L0/L1/L2/L3/TRUNCATION，按 `usage_ratio` 分级）。
- 实现层 `providers/context/`：`time` / `followup` / `profile_hint` 三 Provider + `get_context_manager()`。

## 关键取舍（严格非破坏 Response prompt）

- **`context_compressor` 接入分级压缩**：内容极短(L0)时跳过 LLM 直接增量拼接（省延迟/成本），
  其余走原 LLM 摘要。summary 仅供 FollowUpEngine 上下文，非 Response 关键路径，风险低。
- **`compiler` 只加 token 安全网**：用 `TokenEstimator` 估算 prompt，超 3000 token 才按比例截断
  （正常 Top-N 提示远低于此，几乎不触发）。**不重构 compiler 的 prompt 结构**（候选/证据/约束段
  保持原样），避免影响 Response 质量。
- `ContextManager` + 三 Provider 作为「多源并行采集」能力经 `get_context_manager()` 暴露 +
  单测覆盖，为后续更广采用留接口；本期不接管 Response prompt 主体。

## 影响

Response prompt 结构不变；新增 token 安全网 + 摘要分级（延迟优化）。
单测见 `tests/unit/test_context_framework.py`。
