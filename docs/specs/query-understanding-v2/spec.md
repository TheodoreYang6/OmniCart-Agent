# Query Understanding V2 —— 意图扩展 + 语义拆分 + 多路检索

## Summary
把"用户 query 稍改就进向量库"升级为结构化 Query Understanding：Router 现有那次 LLM 调用的 prompt 对标 amap plan prompt 重写（顺序子任务推理 / 决策表带易误判反例 / 硬约束 / 边界 case / 严格 JSON），一次产出 意图(+4 个购物场景) + 约束 + sub_queries 语义拆分 + 检索改写，零额外延迟；规则解析保持降级兜底（LLM 失败时退化为现状行为，不崩）。拆分结果双链路消费：workflow 侧新增 `multi_query_retrieval` capability（compare_retrieval 的泛化：N 路并行 + 分组合并 + 组 top1 钉顶 + 缺货组诚实声明 + 分组回答），Loop 侧共享同一 QU 缓存注入首条消息。配 40 条 QU 离线评测集与评测脚本。

## 已拍板决策
- QU 与 Router 融合（升级现有 LLM 调用 prompt，零额外延迟），规则兜底必须保住；prompt 借鉴 `/Users/yangqiduo/amap-ai-agent/ai_search/rewrite/prompt/plan_prompt_cache`
- 新意图 4 个：bundle（搭配成套）/ gift（送礼）/ replenish（复购）/ knowledge（购物知识）
- 拆分双链路都接；QU 评测集要建

## 1. QU Prompt 重写 `prompts/agent_prompts.py`
`ROUTER_PROMPT` 升级为三段式顺序子任务（保留现有品类归属提示/追问继承规则）：
- 子任务一 意图判定：主决策表 11 个意图（原 7 + bundle/gift/replenish/knowledge），每行含正例与易误判反例（如 "上次买的洗发水再来一瓶"=replenish 而非 recommend；"降噪和通透什么区别"=knowledge 勿硬推商品；"送女朋友生日礼物"=gift）
- 子任务二 约束抽取：沿用现有字段 + 新增 `gift_profile:{recipient,occasion}`（仅 gift 时输出该 Key，其余省略——amap 式"未选中不输出字段"硬约束）
- 子任务三 拆分与改写：`sub_queries:[{role,query,category,budget_hint}]`（仅当存在 >=2 个真独立商品目标时输出；硬约束"禁止为拆而拆"、每条 query <=12 字检索友好词、保持语义、budget_hint 按总预算合理分配）+ `rewritten_query`（单目标检索词）
- 边界 case 清单（含用户例句"上衣和裤子鞋搭配一套"→3 条 sub_queries；"对比A和B"→不进 sub_queries 走 compare 老链路）
- 输出严格 JSON；`build_router_prompt` 渲染方式不变（replace）

## 2. Schema `schemas/workflow.py`
- 新 `SubQuery(BaseModel)`: role/query/category(None 允许)/budget_hint(None 允许)
- `RetrievalPlan.sub_queries: list[SubQuery] = []`
- `Constraints.gift_profile: dict | None = None`

## 3. RouterAgent `agents/router_agent.py`
- QU 调用抽为模块级 `aunderstand_query(query, context) -> dict`（含现有 cached 逻辑，key 不变 router_intent），Router 与 OmniAgent 共用
- 合并段新增 sub_queries 校验：非 list 丢弃；每条 query 非空、category 不在 VALID_CATEGORIES 则置 None、最多 5 条；仅 1 条视为不拆（清空）；校验失败仅丢 sub_queries 不影响其余字段（降级=现状单查询行为）
- 规则词表新增（降级兜底 + 强检测）：bundle（"搭一套/搭配一套/成套/一整套"）、replenish（"再来一/回购/上次买的.*再"）入 `HIGH_CONFIDENCE_INTENTS`（词强）；gift（"送.*礼物/生日礼/送女朋友/送爸妈"）、knowledge（"什么区别/怎么选/什么是/科普"）仅规则默认不进高置信（词易误判，允许 LLM 纠正）
- gift_profile / sub_queries 写入 state.constraints / state.retrieval_plan

## 4. multi_query_retrieval capability `workflow/graph.py`
新 `@register_capability("multi_query_retrieval")`（compare_retrieval 保留不动）：
- 输入 `state.retrieval_plan.sub_queries`；空则退化调用普通 retrieval（防御）
- N 路 `asyncio.gather` 并行检索（每路带自身 query/category/budget_hint 构造子查询，channels 沿用主 plan）
- 每路商品打 `group_role` 标记；交替合并去重进 `state.retrieved_products`；每组 top1 进 `visual_matched_pids` + `reranker_score=0.95` 钉顶（复用 compare 修复机制，防全局重排挤出）
- 命中统计注入 `state.context_prompt`：`[分组检索] 上衣:5件 裤子:4件 鞋:0件；"鞋"未找到符合条件的商品，回答时须如实说明`
- 黑板发布 `multi_query.groups_retrieved`；timing 记录

## 5. Planner 模板与 Response 分组呈现
- `framework/orchestration/{planner,validator}.py`：`multi_query_retrieval` 加入 PIPELINE_CAPABILITIES；RulePlanner 新模板：
  - bundle：multi_query_retrieval -> reranker -> evidence_check -> decision -> response
  - replenish：tool 步 `order.list`（B2 工具步回填已支持）-> retrieval -> reranker -> evidence_check -> decision -> response
  - knowledge：retrieval(top_k=5) -> response（轻检索重解释，meta.knowledge=true）
  - gift：同 recommend 模板（差异在 response prompt 注入，不新增管线）
- `prompts` response 规则追加两条：context 含 `[分组检索]` 时按组分段回答（每组推荐+理由，给出整套合计价，缺货组如实说明）；constraints.gift_profile 存在时以送礼视角组织（对象/场合/送礼理由）
- 静态图（动态编排 flag off）不接 multi_query：sub_queries 静默忽略，退化单查询 rewritten_query（现状行为，范围可控）

## 6. OmniAgent Loop 消费 `agents/omni_agent.py` + `prompts`
- run_events 组装 messages 前调 `aunderstand_query`（与 workflow 同 cache key，同 query 命中缓存零成本）：结果非 chitchat 时注入首条消息前缀 `[意图理解] intent=bundle；子目标：上衣/裤子/鞋（分别检索后逐组说明）`；QU 异常静默跳过（Loop 自主性兜底）
- `build_omni_agent_prompt` 工作方式补一条：一句话含多个商品目标时分别对每个目标调用 shopping.search，最终逐组说明并给出整套合计

## 7. MOCK 支持 `mock_model.py` + `mock_provider.py`
- MockChat 的 router JSON 分支：query 含"搭一套/搭配"→ 返回 bundle + 3 条 sub_queries；含"上次买的.*再"→ replenish；含"什么区别"→ knowledge；含"送.*礼物"→ gift+gift_profile
- MockProvider.chat_with_tools：消息含多子目标提示时按序返回多个 shopping.search 调用（Loop 拆分场景可演示）

## 8. QU 评测集与脚本
- `data/qu_eval_dataset.json`：40 条标注 `{query, context, expected:{intent, sub_query_roles, category, budget_max}}`，覆盖 11 意图正反例、拆分正例（>=2 目标）、"禁止为拆而拆"负例（信息重叠不拆）、追问继承、口语清洗
- `scripts/eval_qu.py`：逐条调 `aunderstand_query`，输出意图准确率 / 拆分组数 P/R / 品类与预算抽取准确率，结果落 `data/eval_runs/qu-{ts}.json`；MOCK 模式可跑（走 MockChat 脚本验证管线），真实 key 出真基线

## 9. 测试
- `tests/unit/test_qu_understanding.py`（新，~10 例）：4 新意图规则词表；bundle/replenish 高置信不被 LLM 覆盖；sub_queries 合并校验（无效丢弃/单条清空/超 5 截断/坏 category 置 None）；LLM 失败降级规则且 sub_queries 为空；gift_profile 透传
- `tests/unit/test_multi_query_retrieval.py`（新，~5 例，MOCK）：3 路并行分组合并去重；group_role 标记；组 top1 钉顶；缺货组 context_prompt 声明；sub_queries 空退化普通 retrieval
- `tests/unit/test_orchestration.py` 追加：bundle/replenish/knowledge 模板断言（含 replenish 的 tool 步）
- `tests/integration/test_bundle_e2e.py`（新，~3 例，flag on + MOCK）："上衣裤子鞋搭一套"走 multi_query -> 分组 context -> 答案生成；Loop 路径 MOCK 多次 search；qu 评测脚本冒烟（MOCK 跑通出报告）
- 回归：全量 unit + integration + 治理

## 10. 验证与收尾
- py_compile + 全量测试 + 治理全绿；MOCK 起服冒烟（bundle 例句 SSE 全链）
- `scripts/eval_qu.py` MOCK 跑通出报告文件
- 更新 `docs/工作日志.md`（工作块 18）；真实 key 灰度手测清单（bundle/gift/replenish/knowledge + 多轮"鞋换便宜点"）留待用户执行

## Out of scope
- 前端分组商品卡 UI（阶段二统一做）
- 预算组合优化（v1 用 LLM budget_hint 简单分配）
- 独立小模型部署（复用 qwen3.7-flash + 能力位配置，未来可为 intent_understanding 配更小模型实例）
- 多轮增量重查（"鞋换便宜点"只重查一路）——本期 QU prompt 预留 role 结构，实装留下期

## Assumptions
- qwen3.7-flash 对三段式 prompt 的 JSON 输出可靠性足够（合并层校验兜底 + 评测集量化）
- QU 缓存 key 维持 query 粒度（同 query 双链路共享，多轮 context 差异可接受，评测时绕缓存）