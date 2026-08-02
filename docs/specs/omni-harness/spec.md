# Spec · 深度思考模式（OmniAgent Harness 以开关形态落地）

> 决策修订（2026-07-29，用户定稿）：不做主链倒置，harness 以「深度思考」开关落地。
> 默认链路 = pipeline（3.8s 稳定不动）；`deep_think=true` = OmniAgent ReAct Loop 全权
> （LLM 自主决策调用检索/购物车/对比等工具）。延迟预期由用户开关自设（对齐 R1/o1 交互范式）；
> 未来数据证明 Loop 更优时翻默认值即完成主链倒置（复用三 flag 灰度转正路径）。
>
> 前序调研结论保留：amap standard 主链即图化 ReAct（invoke_llm⇄execute_tools + 守卫节点），
> 工具为"聪明工具"（search_place_pro 背后是完整搜索服务）——本 spec 的 Loop 形态与其同构。

## 1. 目标架构

```
SSE 入口 /api/recommend/stream
├─ _FAST_COMMANDS 5 条字面全匹配 → 直通工具（两条链共用，类 slash command）
├─ product_focused_analysis → 独立分支（不受 deep_think 影响）
├─ deep_think=true → OmniAgent ReAct Loop（LLM 全权，跳过购物关键词门控）
│    ├─ ENABLE_AGENT_LOOP 从"路径开关"改为"能力开关"：默认 true（有 deep_think 请求才生效）
│    ├─ while 8 轮预算: chat_with_tools → 执行 → role=tool 回填
│    ├─ 收口轮：预算剩最后 1 轮时注入"请基于已收集信息直接给出最终回答"提示
│    │   （对齐 amap check_completion 显式收口，避免预算耗尽走降级统稿）
│    ├─ 终稿权：收口用 chat_stream 逐 token 直推 SSE（真流式，对齐 amap invoke_llm 内推流）
│    │   ResponseGuard 事后校验保留；商品卡走 state→result 帧旁路不变
│    └─ 降级：LLM 异常 → pipeline（现有 fallback 保留）
└─ 默认 → 现有 pipeline 主链（门控/工具链/动态编排全部不动）
```

## 2. 改造清单

- **D1 触发重构**（agent_stream.py）：`deep_think=true` 请求跳过购物关键词门控直入 Loop；
  ENABLE_AGENT_LOOP 默认值翻 true（语义降级为能力开关：仅 deep_think 请求走 Loop）
- **D2 收口轮 + 终稿真流式**（omni_agent.py + agent_stream.py）：
  倒数第 1 轮注入收口提示；conclude 改为 `chat_stream` 逐 token yield（type=token 事件），
  SSE 层直转发；不再调 ResponseAgent 统稿（异常/空产出时降级统稿保留）
- **D3 原子检索参数**（providers/tools/shopping.py）：shopping.search 增加
  `min_rating`（接通 rating_min 服务端过滤遗留）与 `focus`（reviews/faq 聚焦）可选参数
- **D4 前端 deep_think 开关**（web-client）：聊天输入区"深度思考"toggle →
  StreamRequest.deep_think（字段已存在）；开启时 status 事件外显"思考-行动"过程
  （onStatus 已接线）；Android 字段已有，UI 不在本期
- **D5 评测**（scripts/eval_agent_loop.py）：deep_think vs pipeline 对比
  （推荐/追问/购物操作/多步组合四类），报告落 data/eval_runs/——作为观察基线非转正门槛

## 3. 验收

- deep_think=false：全量回归零变化（324+ 测试绿）
- deep_think=true："预算2000的降噪耳机和保温杯" → LLM 多轮调 shopping.search；
  "把第二个加入购物车" → LLM 自主选 cart.add（无关键词门控）；商品卡正常
- 收口轮为真流式 token；治理/importlinter/lint 门禁绿
