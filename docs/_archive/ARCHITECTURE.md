# OmniCart Agent 架构（V3 框架化升级）

> 本次升级借鉴 amap-ai-agent 的框架级设计模式，将后端从「能跑的参赛单体」升级为
> 「分层清晰、可插拔、可扩展的工程化单体」。**渐进式改造**：单体 FastAPI + Android +
> SSE 主链路不变，Mock 模式与三级降级不变。

## ◎ Canonical 分层图（存放判定的唯一口径，物理防线：importlinter.ini 三契约 + CI）

```
amap monorepo             OmniCart 单服务（backend/app/）          依赖方向
─────────────            ───────────────────────────────     （只允许向下）
services/  业务编排   ⇔   api/  workflow/  services/  decision/        │
commons/   Provider实现 ⇔   providers/（builtin() 显式装配）           │
libs/      框架与能力  ⇔   framework/（协议/注册表/编排器，零业务）    │
schemas/   纯契约     ⇔   schemas/（仅 pydantic，零业务 import）      ▼
（core/ 为横向基建：config/db/cache，各层可用，不入契约）
```

**「放哪一层」四问**（对齐 amap Part 1.2 判定标准，新增代码前先过一遍）：
1. 是 HTTP 入口 / 编排决策（谁先谁后、用哪些组件）？→ `api/` / `workflow/`
2. 实现 framework 协议 + 绑定业务数据源（商品库/记忆库/LLM）？→ `providers/`（登记 builtin()）
3. 纯协议 / 通用算法、零业务数据源依赖？→ `framework/`
4. 纯数据契约（请求/响应/状态对象）？→ `schemas/`

违例会被 CI 的 `lint-imports` 以 fail 形式拦住（没有 lint 的分层 = 没有分层）；
治理条款见 `docs/CONSTITUTION.md`。

## 一、设计主线：框架-实现分离 + Provider/Registry

对齐 amap 的 `libs/*`（框架层）+ `commons/*_providers`（实现层）双层结构，在 `backend/app/`
内落地：

```
backend/app/
├── framework/            # 框架层：Protocol/ABC + 编排，不含业务实现
│   ├── registry.py       # ComponentRegistry + @component 声明式装配
│   ├── agent_manager.py  # AgentManager（Agent 注册表 + 生命周期）
│   ├── retrieval/        # RAG 框架（借鉴 libs/knowledge_base）
│   ├── memory/           # 记忆框架（借鉴 libs/memory_bank）
│   └── context/          # 上下文框架（借鉴 libs/context_store + context_compaction）
├── providers/            # 实现层：具体 Provider / RecallSource，经 builtin() 显式装配
│   ├── recall/  memory/  context/  agents/
└── model_gateway/
    ├── providers/        # ModelProvider（Qwen / Mock 多态）
    └── resilience.py     # retry / timeout / circuit_breaker
```

依赖方向单向：`providers → framework`，framework 绝不反向依赖 providers。新增/替换组件
只改 `builtin()` 清单，不动框架与编排。

**为何不照搬 amap 的 walk_packages 自动扫描**：那是为 Bazel/monorepo 多命名空间服务的重实现；
OmniCart 是单体，采用更简单可控的**显式 `builtin()` 清单**装配（对齐 amap 的
`SourceRegistry.default(provider_builtin=...)` / `MemoryBank.default(builtin_providers=...)`）。

## 二、RAG 模块（framework/retrieval + providers/recall）

**6 阶段管线**（`RetrievalOrchestrator`，移植自 amap `knowledge_base/orchestrator.py`）：

```
① Query Rewrite  → ② Activation Filter → ③ Parallel Fetch(双超时) →
④ Result Processing(required 上抛 / optional 降级) → ⑤ Fusion → ⑥ 兜底/增强
```

- **双超时**：per-source `latency_budget_ms` + 整体 `time_budget`。
- **三阶段召回源**（`RecallSource` ABC，`SourceRegistry` 装配）：
  - `recall`：`SemanticRecallSource`（Embedding + Qdrant ANN + 本地余弦降级 + chunk 检索）。
  - `fallback`：`SupplementaryRecallSource`（主召回 < 3 时触发，分块反向召回）。
  - `enrich`：`ReviewRecallSource` / `PolicyRecallSource`（读 `seed_products` 挖掘证据）。
- **可插拔**：`QueryRewriter`（LLM 关键词改写，rich/slow 双路径）、`RetrievalFusion`
  （`SequentialFusion` 默认 / `RRFFusion` 可选）。

`RetrievalAgent.execute` 只负责构建 `RetrievalQuery` → 调 orchestrator → 写回 state。
产出的 `retrieved_products` / `evidence_list` 结构不变，下游 Decision/Guard/Android 无感。

## 三、Memory 模块（framework/memory + providers/memory）

**三层记忆统一到一个 `MemoryBank`**（借鉴 amap `libs/memory_bank`）：

- `MemoryBank.default(builtin_providers=...)`：rewrite → 多 Provider 并行召回（time_budget）→ 汇总。
- Provider：`preference`（长期偏好）/ `short_term`（context_snapshot）/ `conversation_history`。
- `PreferenceMemoryProvider` 用 `DefaultRecallEngine` 做多路召回：
  `TagPath`（标签 Dice 重合）+ `RecencyPath`（时间衰减）→ `RRFFusion` → `MMRReranker`（可选）。
- **LLM/规则驱动写入整合**（`PreferenceWriter`）：写入前读现有同品类条目 → 去重 + 冲突处理
  （同品牌新表述为避雷则从 must 移除，新表述胜出），替换旧的「每次新建、无去重」。

偏好注入（`inject_profile_hints`）内部改由 MemoryBank 多路召回排序驱动，**对外契约字节级不变**
（下游 hints 对品牌/标签做集合去重）。

## 四、Context 模块（framework/context + providers/context）

- `ContextManager`（借鉴 `libs/context_store`）：多源并行采集（per-provider 超时 + 整体
  time_budget）→ 格式化 + token 估算 → 按 priority 排序 → **token 预算贪心裁剪**。
- Provider：`time` / `followup` / `profile_hint`。
- **分级压缩 `TierSelector`**（借鉴 `context_compaction`）：按 `usage_ratio` 分 L0/L1/L2/L3/TRUNCATION。
  已接入 `context_compressor`——内容极短(L0)时跳过 LLM 直接增量拼接（省延迟），其余走 LLM 摘要。
- `TokenEstimator`：tiktoken 可用则精确，否则 CJK 逐字字符估算。`compiler` 用它做 prompt token 安全网。

## 五、多 Agent 编排与模型网关

- **AgentManager**：`graph.py` 的 5 个硬编码单例改为「注册表装配 + 按名获取」；节点逻辑/边不变。
  提供 `init_all` / `shutdown_all` 生命周期钩子。
- **ModelProvider**：`gateway` 每方法内联的 `if MOCK_MODE` 收敛为 `QwenModelProvider` /
  `MockModelProvider` 多态；gateway 只保留能力路由 + trace/audit。
- **弹性**：`resilience.py` 提供 retry / timeout / CircuitBreaker；QwenProvider 默认保持
  与现网关一致（不额外超时/重试），仅叠加熔断在持续故障时快速失败。

## 六、可观测性

- **全链路 trace_id**：`observability/request_context.py` 用 contextvar 在请求入口
  （`run_workflow`）设置共享 trace_id，`gateway._trace` 读取，使一次请求内的所有 LLM span
  串成一条链路（对齐 amap 的 Langfuse trace 思路，纯标准库实现）。

## 七、工程化

- **配置治理**：`core/config.py` 升级为 `pydantic-settings` 的 `Settings`（分组 + 校验 + 派生开关），
  底部 re-export 全部历史扁平常量，存量 import 零改动。
- **CI**（`.github/workflows/`）：`lint`（ruff 门禁新代码 + 存量非阻塞报告）/ `backend-unit`
  （Mock 模式无外部依赖）/ `smoke`（起服务 + health + recommend）。
- **治理脚本**：`scripts/check_governance.py` 校验各 `builtin()` 名称唯一 + 契约完整。
- **测试金字塔**：`tests/unit` 覆盖框架层纯逻辑（RRF/MMR/orchestrator 双超时降级/TierSelector/
  熔断/偏好整合）。

## 八、与 amap 的对应关系

| OmniCart（本次） | amap-ai-agent | 借鉴点 |
|---|---|---|
| `framework/retrieval` | `libs/knowledge_base` | RecallSource + 6 阶段编排 + 双超时 |
| `framework/memory` | `libs/memory_bank` | MemoryBank + RecallEngine + RRF/MMR |
| `framework/context` | `libs/context_store` + `context_compaction` | 多源采集 + token 预算 + 分级压缩 |
| `framework/registry` | `libs/agent_graph/app/providers` | Provider/Registry（轻量清单版） |
| `model_gateway/providers` + `resilience` | 多模型网关 SDK | Provider 多态 + retry/timeout/熔断 |
| `.github/workflows` | `.aoneci/*.yml` | unit/smoke/lint 分层门禁 |

详见 `docs/adr/`。
