# OmniCart Agent 宪法（治理条款精简版）

> 对齐 amap CONSTITUTION.md 的两个精髓：**每条带执法方式标注** + **可被 review 引用的条款号**。
> 与其他文档冲突时以本文件为准。执法标注：`[CI:xxx]` = 流水线以 fail 阻断；`[manual]` = 靠
> review/自查，违反时直接 cite 条款号打回。
>
> spec: docs/架构升级方案-借鉴amap治理与编排.md §4

## §1 依赖铁律 `[CI:importlinter]`
`api/workflow/services/decision → agents → providers → framework → schemas`，永不向上。
framework 对业务不可见；providers 不得 import workflow/api。跨层需求用**装配时注入**
（参照 `planner.set_tool_schema_source`），不许直接 import。判定看
`docs/ARCHITECTURE.md` 分层四问；契约在 `importlinter.ini`。

## §2 schemas 纯契约 `[CI:importlinter]`
`schemas/` 只依赖 pydantic/标准库，零业务 import、零 IO、零逻辑（校验器除外）。

## §3 组件注册 `[CI:check_governance]`
新组件（recall/memory/context/agent/tool/skill）必须 `@component` 装饰 + 登记对应
`builtin()` 清单。重名 fail；写了装饰器不登记 builtin() 会被孤儿检测拦下。
不引入运行时自动扫描（显式清单可 grep、无 import 副作用，是本项目规模下的正确选择）。

## §4 Prompt 集中管理 `[manual]`
Prompt 模板只住 `app/prompts/`，业务代码零内联模板字符串；模板变更走 build_xxx() 函数，
模板常量大写可 import 供测试审计。（既有规范，升格为条款）

## §5 Canonical 名词表 `[manual]`
每个语义概念全项目只许一个名字；对接外部系统的转换只在边界层发生一次。首批名词表见附录 A。
新增「同义新名」即违宪（amap 前科：session_id vs thread_id 漂移排障对不上号）。

## §6 提交类动作 LLM 不可见 `[CI:check_governance]`
`order.submit / order.pay / order.cancel` 永不进 LLM function schema（`llm_exposed`
白名单 + 治理校验双保险）。资金安全动作必须经确认流程，不给模型直接扣扳机。

## §7 评测驱动变更 `[manual]`
检索 / 精排 / chunk schema / prompt 的行为变更，必须先跑对应评测（`eval_retrieval.py`、
消融对比），报告落 `data/rag_eval_runs/`，用数据说话再定稿。
（V6 教训：faq 前缀照搬论文掉分 4.7pt，消融后反超；rerank doc 缺信号负增益 20pt。）

## §8 集合迁移三查 `[manual]`
改向量集合名 / 缓存 key 结构前，先 grep：`.env`、`core/config.py`、缓存 key 盐。
（事故记录：`.env` 残留旧集合名覆盖代码默认，V6 数据写进 v4 名字、回滚手段降级。）

## §9 SDD 阈值 `[manual]`
预计 ≥3 文件或 ≥100 行或改 public API / DB schema 的改造，先落 `docs/specs/<feature>/spec.md`
再动码；代码注释以 `spec: docs/specs/...` 回引。小改（≤2 文件且 <100 行）豁免。

## §10 数据集金标准 `[CI:validate_dataset]`
商品数据变更必须过 `scripts/validate_dataset.py` 20 项规则（营销≥150字、FAQ≥3条、
评分分化、SKU 阶梯价、图片存在、模板套话黑名单），金标准样本 `p_beauty_001.json`。

---

## 附录 A · Canonical 名词表（首批，新增概念时追加）

| 名字 | 语义 | 边界 |
|---|---|---|
| `session_id` | 客户端设备/登录会话（客户端生成，跨多轮对话稳定） | 请求参数、conversation 表检索键（`aget_latest_by_session`） |
| `conversation_id` | 可恢复聊天线程（服务端生成，一次对话串） | 消息落库外键、checkpoint、上下文加载；**与 session_id 语义有别，非冗余**（2026-07 审计：72/209 使用点，各司其职） |
| `user_id` | 用户身份 | 全链唯一用户标识 |
| `product_id` | 商品 | `p_<品类>_<序号>` |
| `chunk_id` | 商品知识块 | `<product_id>\|<chunk_type>\|<序号>`；Qdrant 点 ID = `uuid5(chunk_id)` |
| `intent` | 一级意图 | Router 产出，封闭词表（意图体系扩展规范） |
| `capability` | 可派发编排能力 | `framework/orchestration/capabilities.py` 注册表；`tool:` 前缀表示工具步 |
| `exec_mode` | 执行档位 lite/standard/max | `WorkflowState.mode` / API 参数 `exec_mode`；**与业务场景 `mode`（normal_recommend 等）无关，严禁混用** |
| `trace_steps` | Agent 执行轨迹 | WorkflowState 内，前端 AgentTrace 消费 |

## 附录 B · 待自动化清单（`[manual]` 条款的收紧路径）
- §4 → ruff 自定义规则或 grep CI（检测业务代码内联长模板字符串）
- §5 → 名词表 lint（禁用词清单：thread_id、chat_id 等同义新名）
- §9 → PR 模板勾选项
