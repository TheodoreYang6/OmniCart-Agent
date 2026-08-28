# OmniCart-Agent 升级方案 · 借鉴 amap-ai-agent 十一维度

> 参考：`amap-ai-agent/学习文档/技术面试提问维度指南.md`（维度 A–K）
> 本文所有「现状」都来自对当前工作区的实测，命令与证据随条目附上。
> 前序方案：[架构升级方案-借鉴amap治理与编排.md](架构升级方案-借鉴amap治理与编排.md)（framework/providers 分层那一轮，已落地）

---

## 0. 先说结论：哪些该借，哪些不该借

amap 是**多服务 Agent 平台**（monorepo + bazel + 20+ libs + 沙箱网关 + Temporal 记忆流水线）；OmniCart 是**单服务电商导购 Agent**。照搬会得到一堆没有承载业务的抽象层。

按「对 OmniCart 当前规模是否真有收益」筛选后：

| 维度 | 结论 | 理由 |
|---|---|---|
| B Agent 编排 | **P0 借** | 已发现两处真实缺陷（构图抄了 4 份、Agent 资源不回收） |
| E 模型网关 | **P0 借** | 只有 CircuitBreaker，缺故障转移；而「Qwen 余额耗尽切 DeepSeek」这事已真实发生过 |
| D 多路召回 | **P0 借** | BM25 参数与门控缺失，直接影响推荐质量 |
| C 上下文 | P1 借 | 有 compaction/token_estimator，缺依赖 DAG |
| F 可观测 | P1 借 | `_traced()` 只有 timing，缺钩子链 |
| K Tool-Use | P1 部分借 | 冲突策略现在就该做；工具检索 RRF **现阶段不划算**（见 §5） |
| A 工程治理 | 基本已有 | CI 已跑 `check_governance.py` + ruff + pytest，只差 importlinter 未进 CI |
| H 评测 | 基本已有 | 已有 recall@k / mrr / ndcg@k / faithfulness / context precision-recall |
| I 基础库 | 低优先 | 单服务无需分布式锁；cache 门面可后补 |
| G 沙箱网关 | **不借** | OmniCart 不执行用户代码，没有「给 Agent 一只手」的需求 |
| J WebSocket | **不借** | SSE 已满足；语音是上传式非流式 |

**明确不做的还有**：Bazel/monorepo 分层、TS 双实现模型网关、Temporal 记忆流水线、MQ 消费分片。这些的触发条件写在 §7。

---

## 1. 维度逐项差异对比（实测）

| 维度 | amap 实现 | OmniCart 现状 | 差距 |
|---|---|---|---|
| **A** 治理 | importlinter layers 契约 + 宪法 767 行 + 153 个 spec + CODEOWNERS | `importlinter.ini`（forbidden 契约：framework 对业务不可见）、`docs/CONSTITUTION.md`、`scripts/check_governance.py`（含「提交类动作不得暴露给 LLM」这类业务规则）、CI 跑 governance+ruff+pytest | 小：`lint-imports` 未进 CI |
| **B** 编排 | `AppRuntime` 2152 行三段生命周期；`ProviderRegistry.discover()` walk_packages；standard/max 双图**同构 8 节点**；`ToolManager.retrieve_tools` 三层回退+RRF | `framework/` 2881 行（registry/blackboard/agent_manager/orchestration）；`main.py` 已用 `lifespan`+`on_startup/on_shutdown`；**无 composition root**；`AgentManager.shutdown_all()` 定义但从未被调用；`graph.py` **4 个构图函数、22 次 add_node** | 大 |
| **C** 上下文/记忆 | `ContextManager` 1095 行 + `DependencyGraph` 拓扑分层 + `_assemble_layered` 逐层并行 + 4 种融合策略；MemoryBank 四路召回 | `framework/context/`（manager/compaction/token_estimator/protocols）、`framework/memory/`（bank/fusion/recall/rerank）；**无 depends_on / DAG / 分层执行**，全并行；记忆 3 路 | 中 |
| **D** 召回 | BM25 `k1=1.5 b=0.75` + `SATURATION=6.0` + `MIN_BM25_RAW_SCORE=1.0` 整路丢弃 + `MAX_DF_RATIO=0.8`；Trigger 三档分数；**相关性门控**（trigger 无命中且 embedding top1 低于阈值则丢弃 embedding 整路）；RRF k=60 带权归一化 | BM25 `k1=1.2 b=0.75`，**无 saturation / 无整路丢弃阈值 / 无 DF 剔除**；RRF k=60 但**无权重无归一化**；双超时 `latency_budget_ms`+`time_budget` **已有** | 中 |
| **E** 模型网关 | `BaseProvider` 五方法 + 5 个适配器；Pipeline/StreamingPipeline 洋葱中间件；`FailoverRouter`+`CircuitBreaker`+`HealthChecker`+`RoundRobinRouter`；`StreamPart` 严格生命周期；ConfigCenter 热更新；`_llm_unavailable` 失败快照 | `gateway.py` 能力名路由 + `model_config.yaml` + `providers/`（base/local/mock/qwen）；`resilience.py` **只有 `CircuitOpenError` + `CircuitBreaker`**；无 failover/health/负载均衡；无中间件管线；无失败快照 | 大 |
| **F** 异步/可观测 | `libs/task`（Celery/Temporal 双后端）+ `libs/message_queue`（4 后端）；monkey-patch `add_node` 注入 before/after/on_error 三钩子，每钩子独立 try/except | 无 task 框架、无 MQ（业务上也不需要）；`observability/`（collector/langfuse_exporter/rag_logger/request_context）；`_traced()` 显式套壳，**只有 timing + 异常 trace，无钩子链** | 中 |
| **G** 沙箱 | 独立 `sandbox-gateway` 服务：执行生命周期、会话租约、Redis 分布式锁+Lua 原子释放、CDP 浏览器、MCP 暴露 | 无 | N/A（无需求） |
| **H** 评测 | 三段式 before/eval/after；evaluator 即 agent；Kafka+HTTP 双通道；坏案归因 | `eval/rag_metrics.py`（faithfulness/context precision/recall）+ `scripts/eval_*.py` 5 个 + `data/rag_eval_runs/` | 小 |
| **I** 基础库 | Cache 门面（`service:namespace:key` + fail-open + `get_or_set` 防击穿）；分布式锁自动续约 | `core/cache.py` 是 `cache_result` 装饰器 + `make_key`，**无 fail-open 语义、无 get_or_set 防击穿**；无分布式锁 | 小 |
| **J** 实时通信 | WebSocketServer 四并发泵 + 心跳看门狗 + 4029 背压 | SSE（`api/agent_stream.py`）+ 上传式语音 | N/A |
| **K** Tool-Use | 五种来源（mcp/shenji/local/file/shell）一套 ToolProvider 契约；`ToolConflictPolicy` 默认 ERROR；`schema_overrides_path` 运营位；工具检索漏斗 | `framework/tools/`（dispatcher 双路调度 / registry / providers / ordinal）；`set_schema_overrides` **已有**；**无冲突策略、无 MCP、无工具检索** | 中 |

---

## 2. P0-1｜构图去重：4 份手抄 → 单一节点/边注册表

### 现状证据

```bash
$ grep -nE "^def build_|^def get_workflow" backend/app/workflow/graph.py
957:def build_workflow()                     # legacy 全量
988:def get_workflow()
998:def get_workflow_no_response()           # legacy 去 response/guard（手抄 6 节点）
1027:def build_dynamic_workflow()            # 动态图全量
1063:def build_dynamic_workflow_no_response()# 动态图去 response（再抄一遍）
$ grep -c "add_node" backend/app/workflow/graph.py
22
```

`legacy × dynamic` 乘 `全量 × no_response` 是个 2×2 矩阵，四份都手写了节点注册与边。**加一个节点要改 4 处**，漏改任一处就是「某条链路上新节点不生效」，这种 bug 在运行期极难定位。

对照 amap：standard 与 max 两张图**节点名清单完全相同**（8 节点），差异只在节点实现与提示词策略——拓扑骨架共享，观测/恢复/迭代上限这些基础设施两档共用。

### 改法

在 `graph.py` 内把「节点清单」和「边清单」提成数据，构图函数只做裁剪：

```python
# backend/app/workflow/graph.py

# 节点注册表：名字 → 实现。唯一真源，加节点只改这里。
_NODES: dict[str, Callable] = {
    "router": _node_router,
    "visual": _node_visual,
    "retrieval": _node_retrieval,
    "reranker": _node_reranker,
    "evidence_check": _node_evidence_check,
    "decision": _node_decision,
    "response": _node_response,
    "guard": _node_guard,
}

# 变体定义：哪些节点参与、终点如何改写。
# no_response 变体不是"删边"而是"把指向 response 的边改指 END" ——
# 直接在全量图上追加 decision→END 会让 LangGraph fan-out，response 仍会执行
# （这个坑原代码注释里记过，这里用声明式重写保住该语义）。
_VARIANTS = {
    "full":        {"drop": set(),                    "reroute": {}},
    "no_response": {"drop": {"response", "guard"},    "reroute": {"response": END, "guard": END}},
}

_EDGES = [
    ("router", "conditional", "router_next", {"visual": "visual", "retrieval": "retrieval", "response": "response"}),
    ("visual", "edge", "retrieval", None),
    ("retrieval", "edge", "reranker", None),
    ("reranker", "edge", "evidence_check", None),
    ("evidence_check", "conditional", "has_results", {"decision": "decision", "response": "response"}),
    ("decision", "edge", "response", None),
    ("response", "edge", "guard", None),
    ("guard", "edge", END, None),
]

def _assemble(nodes: dict[str, Callable], edges: list, variant: str) -> StateGraph:
    """按变体裁剪后装配。所有变体共享同一份节点注册与观测套壳。"""
    v = _VARIANTS[variant]
    g = StateGraph(WorkflowState)
    for name, fn in nodes.items():
        if name in v["drop"]:
            continue
        g.add_node(name, _traced(name, fn))
    g.set_entry_point("router")
    for src, kind, key, mapping in edges:
        if src in v["drop"]:
            continue
        if kind == "edge":
            g.add_edge(src, v["reroute"].get(key, key) if isinstance(key, str) else key)
        else:
            m = {k: v["reroute"].get(tgt, tgt) for k, tgt in mapping.items()}
            g.add_conditional_edges(src, get_route(key), m)
    return g
```

四个入口收敛为参数化调用。动态图（`ENABLE_DYNAMIC_ORCHESTRATION`）是另一套四节点，同模式定义：

```python
# 动态图节点（实测当前 build_dynamic_workflow 的节点集）
_DYN_NODES: dict[str, Callable] = {
    "router": _node_router,
    "planner": _node_planner,
    "supervisor": _node_supervisor,
    "reflect": _node_reflect,
}

_DYN_EDGES = [
    ("router", "edge", "planner", None),
    ("planner", "edge", "supervisor", None),
    ("supervisor", "edge", "reflect", None),
    # reflect 自己写 plan["reflect_route"]，_reflect_next 纯函数读它
    ("reflect", "conditional", "reflect_route", {"supervisor": "supervisor", "end": END}),
]

# 动态图的 no_response 变体不需要 drop（它本来就不含 response/guard），
# 但仍走同一个 _assemble，保证观测套壳与裁剪语义一份实现。
```

```python
_compiled: dict[str, Any] = {}

def get_workflow(*, dynamic: bool = False, with_response: bool = True):
    key = f"{'dynamic' if dynamic else 'legacy'}:{'full' if with_response else 'no_response'}"
    if key not in _compiled:
        nodes, edges = (_DYN_NODES, _DYN_EDGES) if dynamic else (_NODES, _EDGES)
        _compiled[key] = _assemble(nodes, edges, "full" if with_response else "no_response").compile()
    return _compiled[key]
```

保留旧函数名做薄转发，避免动调用方：

```python
def get_workflow_no_response():
    return get_workflow(with_response=False)
```

### 收益 / 风险 / 验证

- **收益**：加节点从改 4 处降到改 1 处；4 个变体共享 `_traced()` 观测套壳（现在也共享，但靠人工抄对）；`_VARIANTS` 把「no_response 必须 reroute 而不是加边」这条踩过的坑变成代码约束而非注释。
- **风险**：**中**。这是行为保持型重构，但 LangGraph 的边语义对 fan-out 敏感，改错会导致 response 节点重复执行或不执行。
- **验证**（改前先建基线）：
  ```bash
  # 1. 四个变体的编译产物节点集必须与重构前逐一相等
  PYTHONPATH=backend python - <<'PY'
  from app.workflow.graph import get_workflow, get_workflow_no_response
  for name, g in [("legacy-full", get_workflow()), ("legacy-nores", get_workflow_no_response())]:
      print(name, sorted(g.get_graph().nodes))
  PY
  # 2. 端到端：MOCK 模式跑冒烟，确认 response 恰好执行一次
  PYTHONPATH=backend OMNICART_MOCK_MODE=true python scripts/smoke_recommend.py
  # 3. 治理与单测
  PYTHONPATH=backend python scripts/check_governance.py && pytest tests/unit backend/tests/unit -q
  ```

---

## 3. P0-2｜生命周期收口：Agent 资源现在不回收

### 现状证据

```bash
$ grep -rn "shutdown_all()" backend/app --include="*.py" | grep -v "def shutdown_all"
（无输出 —— framework/agent_manager.py:52 定义了，但没有任何调用方）

$ sed -n '30,42p' backend/app/workflow/graph.py
_agents = AgentManager.default(builtin=lambda: agents_builtin(_product_repo))  # 模块级，import 期执行
_router = _agents.get("router")
...
```

`main.py` 已经有对称的 `lifespan` + `on_startup/on_shutdown`（远端那批提交改好的），`on_shutdown` 也按 amap 的「容错聚合」写法逐个 try/except 关 PG/Qdrant/Redis。**缺的是业务编排层**：Agent 与模型网关持有的资源（HTTP client、本地模型权重、reranker）没有任何回收路径。

另一个问题是 `_agents` 在**模块级 import 期**构造。amap 的 `AppRuntime` 注释写明这么做的代价：装配顺序不可控、测试无法替换、失败时机在 import 期难定位。

### 改法

**第一步（低风险，先做）**：把 `shutdown_all` 接进 `on_shutdown`，顺序对齐 amap ——**先关业务编排层，再关基础设施**，理由是「避免业务 shutdown 时依赖的 gateway/repo 已被回收」：

```python
# backend/app/main.py，on_shutdown() 开头（在关 PG/Qdrant/Redis 之前）
    # 先关业务编排层：Agent 可能在 shutdown 里回写状态、需要 gateway/repo 还活着。
    # 对齐 amap AppRuntime.shutdown() 的顺序理由。
    try:
        from app.workflow.graph import get_agent_manager
        await get_agent_manager().shutdown_all()
        logger.info("agents shut down")
    except Exception:
        logger.exception("agent shutdown failed")  # 容错聚合：单点失败不阻塞其余收尾
```

`graph.py` 暴露访问器而不是直接导出模块级变量：

```python
def get_agent_manager() -> AgentManager:
    return _agents
```

**第二步（可选，规模上来再做）**：把模块级单例收进一个 `AppRuntime` 雏形。**不要照抄 amap 的 2152 行**——OmniCart 只需要「一个装配入口 + 固定顺序 + 对称收尾」：

```python
# backend/app/core/runtime.py（新建，约 80 行即可）
@dataclass
class AppRuntime:
    product_repo: Any = None
    gateway: Any = None
    agents: AgentManager | None = None

    async def bootstrap(self) -> None:
        """固定顺序装配。顺序有依赖含义，调整需在 CR 里写明理由。"""
        self.product_repo = get_product_repo()
        self.gateway = get_model_gateway()
        self.agents = AgentManager.default(builtin=lambda: agents_builtin(self.product_repo))
        await self.agents.init_all()

    async def shutdown(self) -> None:
        """与 bootstrap 逆序，每步容错。"""
        for step, fn in [("agents", self._close_agents), ("gateway", self._close_gateway)]:
            try:
                await fn()
            except Exception:
                logger.exception("shutdown step failed: %s", step)
```

### 收益 / 风险 / 验证

- **收益**：进程退出不再泄漏 Agent/网关资源（本地 reranker 权重占内存，反复重启开发时尤其明显）；装配顺序从 import 副作用变成显式可读；测试可注入替身。
- **风险**：第一步**低**（只加一段容错调用）；第二步**中**（要动 `graph.py` 的模块级引用，`_router`/`_retrieval` 等 5 个模块级变量都要改为运行时获取）。
- **验证**：
  ```bash
  # 起停一轮，确认 shutdown 日志出现且无异常栈
  PYTHONPATH=backend python -c "
  import asyncio, app.main as m
  asyncio.run(m.on_startup()); asyncio.run(m.on_shutdown())
  " 2>&1 | grep -E "agents shut down|failed"
  ```

---

## 4. P0-3｜模型网关弹性：从「只有熔断」到「熔断 + 故障转移 + 失败快照」

### 现状证据

```bash
$ grep -nE "^class |^def " backend/app/model_gateway/resilience.py
19:class CircuitOpenError(RuntimeError)
52:class CircuitBreaker
```

只有熔断器。amap 那套是四件套协作：`FailoverRouter`（按配置顺序过滤健康 provider）→ `RoundRobinRouter`（候选集内负载均衡）→ `CircuitBreaker`（记失败开断路）→ `HealthChecker`（维护健康状态）。

这不是理论问题：项目记忆里明确记着「Qwen 余额耗尽 → 文本 LLM 已切 DeepSeek」。当时是**人工改配置**切的。熔断器只能让请求快速失败，不能自动切到备用 provider。

### 改法

在 `model_config.yaml` 的能力项上加 `routes` 列表（按优先级），`gateway.py` 取模型时走 failover：

```yaml
# backend/app/model_gateway/model_config.yaml
capabilities:
  chat_generation:
    routes:                      # 按顺序尝试，跳过不健康的
      - model: deepseek-chat
      - model: qwen-plus
      - model: mock             # 兜底：MOCK 保证链路不断
```

```python
# backend/app/model_gateway/resilience.py 追加
class FailoverRouter:
    """按配置顺序返回第一个健康的候选。全不健康时抛 AllProvidersUnavailableError，
    由调用方决定降级（而不是让业务拿到裸异常猜发生了什么）。"""

    def __init__(self, breakers: dict[str, CircuitBreaker]) -> None:
        self._breakers = breakers

    def pick(self, routes: list[str]) -> str:
        for name in routes:
            br = self._breakers.get(name)
            if br is None or br.allow():
                return name
        raise AllProvidersUnavailableError(routes)


class AllProvidersUnavailableError(RuntimeError):
    def __init__(self, routes: list[str]) -> None:
        super().__init__(f"所有候选模型均不可用: {routes}")
        self.routes = routes


class ModelUnavailableError(RuntimeError):
    """进了失败快照的模型：直接抛，不重试。

    与 ``CircuitOpenError`` 必须区分：后者是“运行期连续失败被熔断，过一阵可能
    自恢”；前者是“bootstrap 期就没 build 起来，不改配置永远不会好”。上层的降级
    策略不同：前者应该直接跳下一个候选，后者可以等重试窗口。
    """
```

> `CircuitBreaker` 已经有 `allow()` / `record_success()` / `record_failure()`
> （实测 `backend/app/model_gateway/resilience.py:52` 起），`FailoverRouter` 直接
> 复用它，**不需要改现有熔断器**。

再补 amap 的**失败快照**语义（`_llm_unavailable`）：bootstrap 期构建失败的模型进集合，后续获取**直接抛不重试**，只在配置热更新时清空。理由是「失败也要有确定性」——每次重试会把 build 失败的代价摊到每个请求上。

```python
# backend/app/model_gateway/gateway.py
self._unavailable: set[str] = set()

def get_model(self, capability: str):
    name = self._router.pick(self._routes(capability))
    if name in self._unavailable:
        raise ModelUnavailableError(f"{name} 构建失败已记入失败快照，配置变更后才重试")
    ...
```

### 收益 / 风险 / 验证

- **收益**：单一 provider 余额耗尽/限流/故障时自动切备用，不用人工改配置重启；错误分类（`AllProvidersUnavailableError` vs `CircuitOpenError` vs `ModelUnavailableError`）让上层能做差异化降级。
- **风险**：**中**。故障转移会掩盖单 provider 故障，必须配可观测——每次 failover 要出结构化日志与指标，否则「悄悄降级到 mock」比报错更危险。
- **验证**：
  ```bash
  # 1. 单测：把首选 provider 的断路器打开，断言 pick 返回次选
  pytest backend/tests/unit -k failover -v
  # 2. 故障注入：把 DEEPSEEK_API_KEY 改成无效值，确认自动切 qwen 且日志有 failover 记录
  # 3. 全不可用时确认抛 AllProvidersUnavailableError 而非裸 500
  ```

---

## 5. P0-4｜召回质量：BM25 参数与相关性门控对齐

### 现状证据

```bash
$ grep -rhoE "k1 *= *[0-9.]+|b *= *[0-9.]+" backend/app/retrieval/sparse_encoder.py
k1=1.2  b=0.75          # amap 用 k1=1.5
（无 saturation / 无 MIN_BM25_RAW_SCORE / 无 MAX_DF_RATIO）

$ grep -n "k: int = 60" backend/app/framework/retrieval/fusion.py
64:    def __init__(self, *, k: int = 60)   # RRF k 已对齐，但无权重无归一化
```

缺的三样，每样对应一类线上问题：

| 缺失 | amap 值 | 解决什么 |
|---|---|---|
| BM25 饱和归一化 | `raw/(raw+6.0)` | 防极端高分吃掉融合权重 |
| 整路丢弃阈值 | `MIN_BM25_RAW_SCORE=1.0`，top1 低于此值**整路丢弃** | 词面完全不相关时别拿噪声去污染 RRF |
| 高频词剔除 | `MAX_DF_RATIO=0.8` | "手机""好用"这类词在电商语料里 DF 极高，不剔除会让所有商品都得分 |
| 相关性门控 | trigger 无命中 **且** embedding top1 低于阈值 → 丢弃 embedding 整路 | 语义召回的假阳性（这是电商最容易被吐槽的「推的什么玩意」） |

### 改法

```python
# backend/app/retrieval/sparse_encoder.py
BM25_K1 = 1.5          # 对齐 amap；1.2 偏保守，长 query 下 TF 增益不足
BM25_B = 0.75
BM25_SATURATION = 6.0  # 归一化 raw/(raw+6.0)，把分数压到 (0,1) 且抑制长尾极值
MIN_BM25_RAW_SCORE = 1.0
MAX_DF_RATIO = 0.8

def normalize(raw: float) -> float:
    return raw / (raw + BM25_SATURATION)
```

```python
# backend/app/framework/retrieval/orchestrator.py，融合前加门控
SEM_MIN_TOP1 = 0.35   # 语义路 top1 低于此值且词面路已被丢弃 → 两路都不相关
                      # 初值靠基线评测校定（见下方验证），不要拍脑袋定

def _gate(results: dict[str, RetrievalResult]) -> dict[str, RetrievalResult]:
    """相关性门控必须在 RRF 之前：先融合后过滤会让 top_k 名额被噪声路占掉。"""
    kw = results.get("keyword")
    if kw and kw.items and kw.items[0].raw_score < MIN_BM25_RAW_SCORE:
        results.pop("keyword")           # 词面整路丢弃
    sem = results.get("semantic")
    if "keyword" not in results and sem and sem.items and sem.items[0].score < SEM_MIN_TOP1:
        results.pop("semantic")          # 两路都不相关 → 宁可空结果也不给噪声
    return results
```

### 收益 / 风险 / 验证

- **收益**：直接作用于推荐相关性，是这批里唯一能改善用户可感知质量的项。
- **风险**：**高**。改检索参数一定会动指标，可能一升一降。**绝对不能凭感觉改**。
- **验证（强制先建基线）**：
  ```bash
  # 改之前：跑三份基线并归档
  PYTHONPATH=backend python scripts/eval_retrieval.py   # recall@k / mrr / ndcg@k
  PYTHONPATH=backend python scripts/smoke_rag_eval.py   # faithfulness / context precision-recall
  PYTHONPATH=backend python scripts/eval_subcategory_purity.py
  # 结果落 data/rag_eval_runs/，改后逐项对比
  PYTHONPATH=backend python scripts/rag_stats.py
  ```
  **验收线**：ndcg@10 与 context precision 均不下降，且子类目纯度不下降。任一项掉了就回退该参数单独复测——四个参数要**逐个改逐个测**，不要一起上。

---

## 6. P1 项（收益明确但不紧急）

### P1-1｜上下文依赖 DAG（维度 C）

现状：`framework/context/manager.py` 全并行采集，Provider 之间无法传递结果。amap 的 `DependencyGraph` 让 Provider 声明 `depends_on`，拓扑分层后逐层并行，每层成功的 slices 注入下层 `upstream_slices`，全局 deadline 跨层共享。

- **收益**：支持「先取用户画像 → 再据画像取个性化商品上下文」这类链式依赖，目前只能塞进同一个 Provider 里硬编码。
- **风险**：中。分层执行的总延迟是各层最慢之和（全并行是全局最慢），要给每层留预算。
- **触发条件**：出现第 2 组有依赖关系的 Provider 时再做。现在 17 个 Provider 都独立，做了没有承载。

### P1-2｜可观测钩子链（维度 F）

现状 `_traced()` 只做 timing 兜底 + 异常 trace。补成 before/after/on_error 三钩子的中间件链，**每个钩子独立 try/except**（amap 的第一原则：观测不能杀死业务）。保持现在的显式套壳，**不要**改成 monkey-patch `add_node`——原代码注释已论证过这个取舍（那是多服务+第三方节点全覆盖的方案，代价是耦合 LangGraph 私有 API），OmniCart 单服务不需要付这个代价。

### P1-3｜ToolConflictPolicy（维度 K，零成本）

`framework/tools/registry.py` 现在同名工具后注册者静默覆盖。加三档策略、默认 `ERROR`：

```python
class ToolConflictPolicy(str, Enum):
    ERROR = "error"        # 默认：启动期直接拒绝，绝不把歧义带进运行期
    LAST_WINS = "last_wins"
    FIRST_WINS = "first_wins"
```

同名工具几乎总是接入失误，静默取一个会让 LLM 调到「不知道哪一个」，这种 bug 运行期极难排查。配合已有的 `check_governance.py`（它已经在查工具重名了）形成双保险。

### P1-4｜importlinter 进 CI（维度 A）

CI 已跑 `check_governance.py` + ruff + pytest，但 `importlinter.ini` 的契约没进 CI：

```yaml
# .github/workflows/lint.yml 追加
      - run: pip install import-linter
      - run: lint-imports --config importlinter.ini
```

---

## 7. 明确不做的项与触发条件

| 项 | 不做的理由 | 什么时候该做 |
|---|---|---|
| 沙箱网关（G） | OmniCart 不执行用户代码 | 要做「Agent 写代码/操作浏览器帮用户比价」时 |
| WebSocket 四并发泵（J） | SSE 已满足；语音是上传式 | 要做实时语音对话（打断/竞速取消）时 |
| 工具检索 + 工具 RRF（K） | 工具太少，检索漏斗的收益不足以抵消复杂度 | 工具数 > 30，或接入 MCP 远端工具后 |
| Temporal / MQ（F） | 无跨请求长时流水线 | 要做离线用户画像流水线（记忆反思、冲突融合）时 |
| 分布式锁（I） | 单实例部署 | 多实例部署且有共享写路径时 |
| Bazel / monorepo（A） | 单服务 | 拆出第二个 Python 服务时 |
| 模型网关 TS 双实现（E） | 无 Node BFF | 前端需要直连模型时 |
| walk_packages 插件发现（B） | 已用显式 `builtin()` 清单，单体下更可控 | 需要第三方团队旁挂插件包时 |

---

## 8. 分阶段实施与验证

### 阶段一（P0，建议一次一项、各自独立提交）

| 顺序 | 项 | 预估 | 门禁 |
|---|---|---|---|
| 1 | P0-2 第一步：`shutdown_all` 接进 `on_shutdown` | 0.5h | 起停一轮无异常栈 |
| 2 | P0-1 构图去重 | 3–4h | 四变体节点集与重构前逐一相等 + 冒烟 + 单测 |
| 3 | P0-3 模型网关 failover + 失败快照 | 4–6h | failover 单测 + 故障注入（改坏 key 看是否自动切） |
| 4 | P0-4 召回参数（**四个参数逐个改逐个测**） | 每个 1–2h + 评测 | ndcg@10 / context precision / 子类目纯度均不下降 |

顺序理由：先补收尾（最低风险、立即受益）→ 再做行为保持型重构（此时有对称收尾兜底，反复起停调试代价低）→ 再动弹性（依赖前两项的稳定基座）→ 最后动检索（唯一会影响指标的，单独隔离便于回退）。

### 阶段二（P1）

P1-3（零成本）与 P1-4（两行 CI）随手做；P1-2 视排障痛点决定；P1-1 等到出现第二组依赖型 Provider。

### 每项通用验收

```bash
# 后端
PYTHONPATH=backend python scripts/check_governance.py
lint-imports --config importlinter.ini
ruff check backend/app
pytest tests/unit backend/tests/unit -q
# 端到端
~/miniforge3/envs/omnicart/bin/python run.py     # /api/health 三中间件须 connected
# 前端（若改动涉及接口契约）
cd web-client && npm run typecheck && npm run lint && npm test && npm run build
```

### 回退预案

每项独立提交，出问题 `git revert <sha>` 即可。P0-4 额外要求：改前的评测结果必须归档在 `data/rag_eval_runs/`，回退时用它复核指标是否恢复。

---

## 9. 一句话总结

这批升级里**只有 P0-4 会改变用户可感知的效果**（推荐相关性），P0-1/2/3 都是工程健壮性——修掉「加节点要改 4 处」「Agent 资源不回收」「单 provider 故障要人工切」这三个已经存在的真实问题。amap 那些更重的能力（沙箱、Temporal、WebSocket、monorepo 治理）对 OmniCart 当前形态是负债而非资产，§7 给了各自的触发条件，等业务真的走到那里再借。
