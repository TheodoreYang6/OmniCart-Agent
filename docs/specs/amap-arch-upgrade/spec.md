# 架构升级方案 · 借鉴 amap monorepo 治理与编排机制

> 依据：《维度A-整体架构与工程治理详解》《维度B-Agent编排引擎详解》+ amap 仓库实码
> （importlinter.ini / .dependency-cruiser.js / agentgraph providers.py / CONSTITUTION.md）
> + OmniCart 现状实查（2026-07，全部证据已核实）。
>
> 原则：**对标机制而非照搬形态**。amap 是 13 服务多团队 monorepo，OmniCart 是单服务单人项目——
> 规模差 2 个数量级，每项建议都先回答"这个机制解决的问题在 OmniCart 存不存在"。

---

## 0. 对标总览

| # | amap 机制 | OmniCart 现状 | 判定 | 行动 |
|---|---|---|---|---|
| 1 | 四层 services/commons/libs/schemas | 包内四层 api+workflow / providers / framework / schemas，**已同构** | 补边界防线 | P0-1 修违例、P0-2 上物理防线 |
| 2 | import-linter + dep-cruiser 双语言物理防线 | 仅 ruff 风格门禁 + check_governance（管装配不管 import 方向） | **缺失，唯一真空档** | P0-2 importlinter 契约 |
| 3 | LangGraph StateGraph + 预编译 + 观测套壳 + mode 三档 | StateGraph 预编译单例已有；观测靠节点内手工 append；mode 是 magic string | 半程 | P1-3 观测 wrapper、P2-1 mode 显式化 |
| 4 | SDD（spec→plan→tasks）+ 宪法（条款+执法标注） | plan 文档存在但在 IDE 缓存里不进 repo；无宪法 | 轻量化引入 | P1-1 宪法精简版、P1-2 specs 归档 |
| 5 | ProviderRegistry walk_packages 自动发现 | @component 挂元数据 + builtin() 显式清单 | **现状更优，不照搬** | P1-4 只补"定义未登记"防呆 |
| 6 | 工具全链路（schema 投影/检索/冲突策略/schema_overrides） | ToolSpec→openai_schemas→双路调度→invoke 已完整；flag 未转正 | 主线是转正 | P2-2 灰度转正、P2-3 schema_overrides |

---

## 1. 架构分层：包内四层已同构，缺的是"把它写成法律"

**现状（✅实查）**：OmniCart 的分层与 amap 四层精确同构——

```
amap monorepo                OmniCart 单服务（backend/app/）
─────────────────           ─────────────────────────────
services/  业务编排     ⇔    api/ workflow/ agents/ services/ decision/
commons/   Provider实现 ⇔    providers/（context/memory/recall/tools/agents/skills，builtin() 装配）
libs/      框架与能力   ⇔    framework/（registry/retrieval/tools/orchestration/memory/context）
schemas/   纯契约      ⇔    schemas/（仅依赖 pydantic，已核实零业务 import）
                             + core/（config/db/cache，横向基建，各层可用）
```

**已发现的违例（✅实查 providers/tools/shopping.py L96-102）**：

```python
from app.workflow.graph import (      # ← 实现层反向 import 编排层
    _node_decision, _node_evidence_check, _node_reranker, _node_retrieval,  # 还是私有函数
)
```

双重问题：providers → workflow 方向反了；且依赖 `_` 私有节点函数（graph 内部重构即断）。

**修法（P0-1）**：graph.py 已有 capability 注册表（`get_capability`）。把「retrieval→reranker→
evidence→decision 子管线」下沉为 framework 层的 `run_capability_pipeline(caps, state)` 帮助函数
（通过 capability 名查表调用，不 import graph 私有函数），shopping.py 与 graph.py 都消费它。
依赖方向变为 providers → framework ✓。

**canonical 分层图（P0-3）**：把上表写进 `docs/ARCHITECTURE.md` 顶部，并附「放哪一层」三问
（对齐 amap Part 1.2）：①是 HTTP 入口/编排决策？→ api/workflow ②实现 framework 协议+绑定数据源？
→ providers ③纯协议/算法零业务依赖？→ framework ④纯数据契约？→ schemas。

---

## 2. 依赖治理：importlinter 物理防线（唯一真空档，收益最高）

amap 的核心洞察：**没有 lint 的分层 = 没有分层**（code review 拦不住一行 `from app.workflow import x`）。
OmniCart 的 check_governance 管"组件装配对不对"，不管"import 方向对不对"——这就是空档。

**落地（P0-2）**：仓库根新建 `importlinter.ini`（对齐 amap 独立配置不侵入 pyproject 的做法）：

```ini
; 依赖方向物理防线 —— 对齐 amap importlinter.ini（design §4.9 L4 物理层）
; 运行：PYTHONPATH=backend python -m importlinter.cli lint --config importlinter.ini
[importlinter]
root_packages =
    app

[importlinter:contract:layers]
name = 分层单向依赖（api/workflow > providers > framework > schemas）
type = layers
layers =
    app.api : app.workflow : app.services : app.decision
    app.agents
    app.providers
    app.framework
    app.schemas
containers =
exhaustive = false

[importlinter:contract:schemas-pure]
name = schemas 纯契约（禁止 import 任何业务层）
type = forbidden
source_modules =
    app.schemas
forbidden_modules =
    app.api
    app.workflow
    app.providers
    app.framework
    app.agents
    app.services

[importlinter:contract:framework-blind]
name = framework 对业务不可见（对齐 amap "libs-invisible-to-services"）
type = forbidden
source_modules =
    app.framework
forbidden_modules =
    app.api
    app.workflow
    app.providers
    app.agents
    app.services
```

**渐进式治理（对齐 amap severity 分档）**：先跑一遍看存量违例；shopping.py 修完后 layers 契约
应该绿；如仍有存量，用 `ignore_imports` 白名单登记（每条附 TODO），CI 先上、白名单只减不增。

**CI 接入**：`.github/workflows/lint.yml` 加一步（uvx 隔离运行，零依赖树污染，照抄 amap）：

```yaml
- name: Import contracts (架构防腐)
  run: PYTHONPATH=backend uvx --from import-linter lint-imports --config importlinter.ini
```

---

## 3. Agent 编排：三个具体差距（图本身不用动）

OmniCart 已是 LangGraph StateGraph + 启动期预编译单例 + 条件边路由 + 动态图带 reflect 上限——
与 amap 同底座同姿势，**不需要重构图**。差距在图周围三件事：

### 3.1 mode 显式化（P2-1）：消灭 magic string

**现状（✅实查）**：两种"快速模式"并存——`config.FAST_MODE` 全局 flag +
`"[FAST_MODE]" in state.context_prompt` magic string（router_agent.py L118、graph._node_reranker
L566）。字符串嵌 prompt 是典型腐化点：不可发现、不可校验、污染 prompt 语义。

**改法（对齐 amap BaseModeAgent 三档派发）**：
1. `WorkflowState` 加 `mode: Literal["lite","standard"] = "standard"` 字段
2. API 层解析请求参数 / FAST_MODE 配置 → 写 state.mode（一次翻译，边界层完成）
3. 全部 `"[FAST_MODE]" in ...` 判断改为 `state.mode == "lite"`；context_prompt 不再嵌标记
4. 预留 `"max"` 档：动态编排图（planner-supervisor-reflect）天然就是 max 档——
   `mode="max"` 可作为 ENABLE_DYNAMIC_ORCHESTRATION 的按请求灰度入口（比全局 flag 更细粒度，
   正好服务遗留的 flag 转正任务）

### 3.2 节点观测统一 wrapper（P1-3）：替代手工 trace_steps

**现状**：每个节点函数内手工 `state.trace_steps.append({...})` + `state.timing[...] = ...`，
样板代码散在 11 个节点里，新节点容易漏。

**改法**：不学 amap 的 monkey-patch（那是为了覆盖多服务+第三方 prebuilt 节点的全局方案，
单服务不需要付"上游私有 API 耦合"的代价），在构图处显式包裹即可：

```python
# workflow/graph.py 构图处
def _traced(name: str, fn):
    async def wrapper(state: WorkflowState) -> WorkflowState:
        t0 = time.perf_counter()
        try:
            out = await fn(state)
            _append_trace(out, name, ok=True, ms=(time.perf_counter()-t0)*1000)
            return out
        except Exception:
            _append_trace(state, name, ok=False, ms=(time.perf_counter()-t0)*1000)
            raise
    return wrapper

g.add_node("retrieval", _traced("retrieval", _node_retrieval))  # 所有 add_node 统一过 _traced
```

节点内既有手工 trace 逐步删除（wrapper 落地后节点只写业务）。amap 的两条纪律要保留：
钩子内部独立 try/except（观测不能杀死业务）+ 防重复包装标记。

### 3.3 state patch 约定（明确不做）

amap 节点"只读 state 返回 dict patch"是多团队协作的可回放性投资；OmniCart 节点直改 state
返回全量，改造涉及全部 11 个节点且单人项目回放收益低。**记录差距，不投入。**

---

## 4. 工程治理：宪法精简版 + SDD 轻量化

### 4.1 CONSTITUTION 精简版（P1-1）

amap 宪法 767 行是多团队执法需要；OmniCart 取其两个精髓：**每条带执法标注** + **可 cite 条款号**。
新建 `docs/CONSTITUTION.md`（~60 行，10 条）：

```
§1 依赖铁律 [CI:importlinter]   api/workflow > providers > framework > schemas，永不向上
§2 schemas 纯契约 [CI:importlinter]   零业务 import
§3 组件注册 [CI:check_governance]   新组件必须 @component + 登记 builtin()，重名即 fail
§4 Prompt 集中管理 [CI:check_governance]   prompt 只住 app/prompts/，业务代码零内联模板
§5 canonical 名词表 [manual]   每个语义概念全项目一个名字，见附录 A；边界层转换一次
§6 提交类动作 LLM 不可见 [CI:check_governance]   order.submit/pay/cancel 永不进 function schema
§7 评测驱动变更 [manual]   检索/精排/prompt 变更必须先跑 eval_retrieval / 消融，报告落 data/
§8 集合迁移三查 [manual]   改向量集合名先 grep .env / config.py / 缓存 key 盐
§9 SDD 阈值 [manual]   ≥3 文件或 ≥100 行的改造先落 docs/specs/<feature>.md 再动码
§10 模板套话黑名单 [CI:validate_dataset]   数据集文案禁通用话术，金标准为 p_beauty_001

附录 A · canonical 名词表（首批）
- conversation_id = 可恢复聊天线程（HTTP 参数/DB 外键统一用它）
- session_id     = 单次运行会话（仅 checkpoint/trace 内部用，禁止新增对外暴露）
- product_id / chunk_id / point_id（uuid5(chunk_id)）……
```

§5 有真实前科支撑（✅实查 WorkflowState 里 `session_id` 与 `conversation_id` 并存）：
先审计两者所有使用点，明确语义边界写进名词表；如实际同义则收敛为一个（P1-1 附带任务）。

### 4.2 SDD 轻量化（P1-2）

现状：plan 文档（如 Vectorization_V6_Upgrade_task-030.md）存在 IDE 缓存目录，**不进 repo、
不可追溯**。改法照抄 amap 的目录形态、砍掉工单联动：

```
docs/specs/<feature>/spec.md     # 已有 plan 文档直接归档改名（V6/QU-V2/数据集提质三份存量先入库）
```
触发规则写进宪法 §9；代码注释引用规格路径（amap 的"代码↔规格互引"），如
`# spec: docs/specs/vectorization-v6/spec.md §3`。CODEOWNERS 不做（单人项目无意义）。

---

## 5. 插件机制：显式清单是正确选择，只补一个防呆

**判定：不照搬 walk_packages**。amap 从 entry_points → walk_packages 的演进动机是
bazel 无 dist-info + 13 服务扫描规模；OmniCart 的 builtin() 显式清单在当前规模（5 agents /
16 tools / 12 providers）下**更优**：可 grep、启动确定性、无 import 副作用陷阱。
amap 自己也为副作用控制弃 pkgutil 自写 os.walk——副作用正是自动扫描的原罪。

**唯一值得补的（P1-4）**：显式清单的软肋是"写了 @component 忘登记 builtin()"静默失效。
给 check_governance.py 加一个防呆检查：

```python
def _check_unregistered(errors):
    """扫 providers/ 下所有挂 __component_kind__ 的类，与各 builtin() 清单求差集。"""
    defined = _scan_component_classes("app.providers")   # walk 源码文件做 AST/import 扫描
    registered = _collect_builtin_names()                 # 现有各 builtin() 聚合
    if orphans := defined - registered:
        errors.append(f"[registry] 已定义未登记 builtin(): {sorted(orphans)}")
```

这是把 amap"自动发现"的收益（不漏）嫁接到"显式清单"的骨架（可控）上，CI 兜底。

另一个可选增强：@component 加 `ext_schema`（pydantic 配置类），组件配置项类型化校验
（对齐 amap `@tool_component(ext_schema=...)`）——当前组件基本无配置项，**等有需求再上**。

---

## 6. tool / skill 的 LLM 调用：链路已全，主线是"转正"而不是"新建"

**现状（✅实查，比预期完整）**：
- `ToolSpec`（name/description/parameters/permission/llm_exposed/timeout_ms）→
  `ToolRegistry.openai_schemas(llm_only=True)` 投影 OpenAI function schema
- `invoke()` 统一执行：权限校验（order 档需确认）→ 弹性超时 → 追踪 → 黑板落板
- 双路调度：RuleToolRouter 关键词 → `ENABLE_LLM_TOOL_CALLING` LLM function calling → 降级
- 治理已到位：order.submit/pay/cancel 禁入 LLM 白名单（check_governance CI 验证）
- `ENABLE_AGENT_LOOP` 的 ReAct 循环（对应 amap standard 图的 invoke_llm⇄execute_tools）已建成

**差距判定**：
| amap 机制 | 判定 |
|---|---|
| retrieve_tools BM25+RRF top-20 收敛 | **不需要**——16 个工具全量注入 token 占用可忽略，几十个以上才值得 |
| InvokeSubAgentTool 动态 enum | **暂无场景**——无 sub agent |
| schema_overrides（LLM 看的与代码执行的分离） | **值得做（P2-3）**——prompt 工程师调工具描述不动代码 |
| ToolConflictPolicy 默认 ERROR | 已等价（ComponentRegistry 重名需 override=True） |

**P2-2 主线：两个 flag 灰度转正**（按既有《三 flag 统一灰度验证操作规范》执行）：
1. `ENABLE_LLM_TOOL_CALLING=true` 灰度：跑 tool dispatch 对比评测（规则路由 vs LLM 路由的
   命中率/延迟），达标转默认 true，规则路由降级为 fallback
2. `ENABLE_AGENT_LOOP=true` 灰度：先补 amap standard 图的两个安全件——迭代上限守卫
  （check_iteration，防 LLM 死循环烧钱）与 recover 节点（异常恢复不整锅报废），再灰度

**P2-3 schema_overrides 运营位**（~30 行）：

```python
# providers/tools/__init__.py 装配处
overrides = json.loads(Path(TOOL_SCHEMA_OVERRIDES).read_text()) if TOOL_SCHEMA_OVERRIDES else {}
# ToolRegistry.openai_schemas() 输出前按 name 整体覆盖 description/parameters
# 运行时校验仍走 ToolSpec.parameters —— "给模型看的"与"代码执行的"分离
```

**Skill 资产（SKILL.md markdown 形态）**：现有 PromptSkill 是代码内字符串模板，数量少、
无跨 Agent 覆盖需求。markdown 资产 + 渐进披露的收益要到"技能多到需要检索"才显现。**暂缓，
记录形态差距。**

---

## 7. 实施清单

### P0 · 防腐化（半天，先做——违例每多活一天就多一处仿写）
- [ ] **P0-1** 修 shopping.py 反向依赖：子管线下沉 framework `run_capability_pipeline`
- [ ] **P0-2** importlinter.ini 三契约 + lint.yml CI 接入（uvx 隔离运行）
- [ ] **P0-3** ARCHITECTURE.md 顶部补 canonical 分层图 + "放哪一层"三问

### P1 · 治理增强（1 天）
- [ ] **P1-1** docs/CONSTITUTION.md 十条精简版（每条执法标注）+ session_id/conversation_id 审计收敛
- [ ] **P1-2** docs/specs/ 建目录，三份存量 spec（V6/QU-V2/数据集提质）归档入库
- [ ] **P1-3** 节点观测 `_traced` wrapper 统一包裹，删节点内手工 trace 样板
- [ ] **P1-4** check_governance 加"已定义未登记 builtin()"防呆

### P2 · 编排与工具升级（2-3 天）
- [ ] **P2-1** mode 显式化：state.mode 三档（lite/standard/max），消灭 "[FAST_MODE]" magic string；
      max 档接动态编排按请求灰度
- [ ] **P2-2** ENABLE_LLM_TOOL_CALLING / ENABLE_AGENT_LOOP 灰度转正（Loop 先补迭代守卫+recover）
- [ ] **P2-3** 工具 schema_overrides 运营位

### 明确不做（判定过，不是没想到）
| 项 | 理由 |
|---|---|
| walk_packages 自动发现 | 规模不需要；显式清单可 grep、无副作用，amap 自己都在控副作用 |
| monkey-patch add_node | 单服务构图处显式包裹即可，不付"上游私有 API 耦合"代价 |
| CODEOWNERS / Aone 工单联动 | 单人项目无执法对象 |
| 节点 dict-patch 状态约定 | 11 节点全改，可回放收益配不上成本 |
| SKILL.md markdown 资产 | 技能数量未到需要渐进披露/检索的规模，记录差距暂缓 |
| dependency-cruiser | web-client 无自研分层库，无契约可立 |
