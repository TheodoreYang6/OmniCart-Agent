# OmniCart Agent 开发过程规则与 AI Agent 行为规范

版本：v1.0  
适用项目：OmniCart Agent Competition Edition  
适用对象：Claude Code / Codex / Cursor Agent / 通义灵码 / 其他 AI 编程 Agent  
基准蓝图：`OMNICART_AGENT_COMPLETE_BLUEPRINT.md` v5.0  
更新日期：2026-05-20  

---

## 0. 文档目的

本文档用于约束 OmniCart Agent 项目在开发过程中的 AI 编程 Agent 行为，确保项目始终围绕最终蓝图推进，避免 AI Agent 在开发过程中擅自改动架构、遗忘开发进度、丢失技术总结、绕过测试验证或引入不可控实现。

OmniCart Agent 的目标不是快速拼出一个 Demo，而是构建一个可运行、可展示、可解释、可验证、可回放、可写进简历和答辩材料的多模态购物决策 Agent Runtime。因此，开发过程本身必须被结构化管理。

本文档要求所有 AI 编程 Agent 在执行任何代码修改、文档修改、模块开发、功能总结、测试验证和里程碑推进时，必须遵守以下规则。

---

## 1. 总体开发原则

### 1.1 蓝图优先原则

`OMNICART_AGENT_COMPLETE_BLUEPRINT.md` 是项目最高级别设计文档，默认只读。

除非用户明确说出以下类似指令：

```text
允许修改最终蓝图
更新开发蓝图
修改 OMNICART_AGENT_COMPLETE_BLUEPRINT.md
重构蓝图文档
```

否则 AI Agent 不得修改该文件。

允许读取、引用、对照蓝图，但不得在开发过程中擅自改动蓝图内容。

### 1.2 参赛版边界原则

项目当前目标是 Competition Edition，而不是企业级全功能系统。所有开发必须围绕 V1 参赛核心版本推进。

V1 优先完成：

```text
FastAPI 后端
Android Native Client
Kotlin + Jetpack Compose + Material 3
Android 四 Tab：商品展示 / 豆仔智能 / 购物车 / 个人中心
商品展示、购物车、个人中心基础电商能力
登录 / 注册、用户信息、收货地址、个人偏好管理
豆仔智能通过受控 action 加入购物车
mock checkout / 模拟结算
Qwen-only Model Gateway
5 Agent Workflow
Multimodal Evidence RAG
Skill Registry
MCP-compatible ToolManager
A2A-lite AgentMessage / Artifact
Context Compiler
Adaptive Retrieval
Evidence Sufficiency Checker
Decision Scoring
Constraint Solver
Decision Harness
State Checkpoint
Agent Trace Panel
Evidence Panel
Skill Execution Panel
Harness Validation Panel
Demo Pack / Mock Mode
Baseline 评测
```

比赛要求原生客户端后，所有核心演示能力必须优先在 `android-client/` 中实现。Web、WebView、Next.js、React、TailwindCSS、React Native、Expo、Flutter 禁止作为最终交付端；历史文档或历史代码中出现的 `frontend/` 统一视为 deprecated，不得继续创建或维护为主线目录。iOS Swift + SwiftUI 仅作为未来可选扩展，不进入 V1。

当前产品不是只有豆仔智能页面，而是四 Tab Android 原生客户端：商品展示、豆仔智能、购物车、个人中心。豆仔智能仍是核心 AI Agent 页面，新增传统电商基础功能必须服务主 Demo 和用户体验，不能喧宾夺主，不能把项目改成普通购物 App。

四个页面都是主页面：商品展示、豆仔智能、购物车、个人中心必须共同构成完整购物体验。其中豆仔智能是核心创新页面，商品展示、购物车和个人中心是基础电商能力，负责承接浏览、加购、模拟结算、用户信息、收货地址和个人偏好。

不得未经用户同意将 V2 能力提前作为主线，例如：

```text
标准 MCP Server / Client
标准 A2A 分布式协议
Computer Use / Browser Use
Neo4j 完整 GraphRAG
跨会话长期记忆
Qwen-Omni 语音导购
Langfuse / Phoenix 完整观测平台
在线学习 / Bandit 排序
订单 / 支付 / 账号操作
真实支付接入
Agent 直接操作数据库
绕过后端 service 操作购物车
Web / WebView / 跨平台客户端作为最终交付端
```

### 1.3 可验证优先原则

任何关键节点不能只说“完成”，必须能被验证。

完成标准至少包括：

```text
代码已实现
接口可运行
有测试或验证方式
文档已更新
进度已记录
知识总结已沉淀
如涉及 Agent / RAG / Tool / Harness，必须能在 Trace 或日志中看到执行过程
```

### 1.4 不破坏历史原则

AI Agent 不得删除历史开发文档、总结文档、进度文档、设计文档或旧版本方案。

如果某文件已经过时，只能：

```text
标记为 deprecated
移动到 archive/
在文件顶部注明废弃原因
保留引用关系
```

禁止直接删除。

### 1.5 每个亮点都要沉淀原则

每完成一个关键技术亮点，必须生成详细知识总结，用于后续答辩、简历和技术复盘。

关键亮点包括但不限于：

```text
FastAPI 后端
Android Native Client
Qwen Model Gateway
Router Agent
Visual Agent
Retrieval Agent
Decision Agent
Response Agent
A2A-lite
Skill Registry
MCP-compatible ToolManager
Context Compiler
Adaptive Retrieval
Evidence Graph Lite
Visual Evidence Grounding
Constraint Solver
Decision Scoring
Decision Harness
State Checkpoint
Demo Pack / Mock Mode
Evaluation / Baseline
```

---

## 2. 固定维护文件清单

项目根目录建议维护以下文件：

```text
OMNICART_AGENT_COMPLETE_BLUEPRINT.md     # 最终蓝图，默认只读
DEVELOPMENT_RULES.md                    # 当前文档，开发规则
DEVELOPMENT_PROGRESS.md                 # 开发进度
KNOWLEDGE_LOG.md                        # 技术知识沉淀
CHANGELOG.md                            # 项目变更日志
DECISION_LOG.md                         # 关键技术决策记录
MILESTONE_SUMMARY.md                    # 阶段性里程碑总结
DEMO_SCRIPT.md                          # 比赛演示脚本
EVALUATION_REPORT.md                    # 评测结果报告
BUG_LOG.md                              # 问题与修复记录
RISK_REGISTER.md                        # 风险清单
```

如果文件不存在，AI Agent 在第一次需要写入时应自动创建，但创建前需要说明即将创建的文件名和用途。

---

## 3. 文件不可变规则

### 3.1 绝对默认只读文件

以下文件默认不可修改：

```text
OMNICART_AGENT_COMPLETE_BLUEPRINT.md
```

只有用户明确授权时才允许修改。

### 3.2 受控修改文件

以下文件可以修改，但必须遵循模板：

```text
DEVELOPMENT_PROGRESS.md
KNOWLEDGE_LOG.md
CHANGELOG.md
DECISION_LOG.md
MILESTONE_SUMMARY.md
DEMO_SCRIPT.md
EVALUATION_REPORT.md
BUG_LOG.md
RISK_REGISTER.md
```

### 3.3 源代码修改规则

AI Agent 修改源代码时必须遵循：

```text
不得大范围无理由重构
不得擅自替换主技术栈
不得绕过 Model Gateway 直接调用模型
不得绕过 ToolManager 直接调用工具
不得让 Response Agent 生成无 evidence_ids 的结论
不得让 Decision Agent 使用纯 LLM 主观排序替代评分公式
不得让 Agent 直接操作数据库或绕过 service 修改购物车
不得接入真实支付，付款只能做 mock checkout / 模拟结算
不得一次性铺满用户、购物车、地址、订单、Agent Action 全部空模块
不得把 V2 能力混入 V1 主线
```

---

## 4. 用户触发命令规则

### 4.1 “进行记忆存储”

当用户说：

```text
进行记忆存储
记忆存储
保存当前进度
记录当前开发状态
```

AI Agent 必须执行以下动作：

1. 读取当前项目状态。
2. 更新 `DEVELOPMENT_PROGRESS.md`。
3. 如果本轮完成了关键技术节点，追加更新 `KNOWLEDGE_LOG.md`。
4. 如果发生代码或文档变更，更新 `CHANGELOG.md`。
5. 如果产生关键技术取舍，更新 `DECISION_LOG.md`。
6. 输出本次记忆存储摘要。

不得只在对话中口头总结，必须写入对应文档。

### 4.2 “标记节点完成：<节点名>”

当用户说：

```text
标记节点完成：fastapi_backend
标记节点完成：android_native_client
标记节点完成：a2a_lite
标记节点完成：rag_pipeline
```

AI Agent 必须执行以下动作：

1. 检查该节点是否确实有对应代码、文档或测试结果。
2. 如果没有证据，不得标记为完成，应标记为 `blocked` 或 `needs_verification`。
3. 如果有证据，更新 `DEVELOPMENT_PROGRESS.md`。
4. 生成对应节点的详细知识总结，写入 `KNOWLEDGE_LOG.md`。
5. 更新 `CHANGELOG.md`。
6. 如果该节点是里程碑节点，更新 `MILESTONE_SUMMARY.md`。
7. 输出节点完成摘要。

### 4.3 “生成知识总结：<节点名>”

AI Agent 必须在 `KNOWLEDGE_LOG.md` 中生成一篇完整技术总结，包含：

```text
模块目标
技术背景
实现内容
核心代码路径
数据结构
接口设计
关键流程
设计取舍
替代方案
踩坑记录
测试方式
性能表现
与蓝图的对应关系
答辩讲法
简历写法
后续优化
```

### 4.4 “更新开发蓝图”

这是高风险操作。AI Agent 必须先询问确认：

```text
你确认要修改 OMNICART_AGENT_COMPLETE_BLUEPRINT.md 吗？
该文件是最终蓝图，默认不可修改。
建议先生成 BLUEPRINT_CHANGE_PROPOSAL.md，确认后再修改。
```

未经二次确认，不得修改蓝图。

### 4.5 “运行验证”

当用户说：

```text
运行验证
运行测试
运行 Harness
验证当前节点
```

AI Agent 必须优先执行已有测试和验证脚本。如果测试不存在，应说明缺失并创建合理的最小验证方案。

验证结果必须写入：

```text
EVALUATION_REPORT.md
或当前节点对应的 KNOWLEDGE_LOG.md 条目
```

---

## 5. DEVELOPMENT_PROGRESS.md 维护规范

### 5.1 文件用途

`DEVELOPMENT_PROGRESS.md` 用于记录项目整体开发进度，避免 AI Agent 和开发者遗忘当前状态。

### 5.2 推荐结构

```markdown
# OmniCart Agent 开发进度

更新时间：YYYY-MM-DD HH:mm

## 当前总体状态

当前阶段：V0-Core / V0-Android / V1-Core / V1-Android / V1-Plus / V1-Advanced / V2
当前重点：
当前阻塞：
下一步任务：

## 进度总览

| 模块 | 状态 | 优先级 | 负责人 | 代码路径 | 验证方式 | 更新时间 |
|---|---|---|---|---|---|---|
| FastAPI 后端 | done | P0 | Lucas | backend/app/main.py | pytest | 2026-xx-xx |
| Android Native Client | in_progress | P0 | Lucas | android-client/ | Android 模拟器 / 真机 / APK | 2026-xx-xx |

## V0 任务

- [ ] FastAPI 项目初始化
- [ ] Android 项目初始化
- [ ] Android Bottom Navigation 四 Tab
- [ ] 商品展示页基础列表
- [ ] 购物车基础增删
- [ ] 个人中心 Demo 用户
- [ ] Product / Evidence / AgentState Schema
- [ ] Qwen Model Gateway
- [ ] 文本检索闭环

## V1 任务

- [ ] 登录 / 注册
- [ ] 地址管理
- [ ] 用户偏好管理
- [ ] 图片上传
- [ ] Android Photo Picker / ImagePreview
- [ ] 豆仔通过受控 action 加入购物车
- [ ] 购物车模拟结算
- [ ] Visual Agent
- [ ] Multimodal Evidence RAG
- [ ] Skill Registry
- [ ] A2A-lite
- [ ] MCP-compatible ToolManager
- [ ] Decision Harness
- [ ] Demo Pack

## 当前阻塞问题

| 问题 | 影响 | 解决方案 | 状态 |
|---|---|---|---|

## 下一步计划

1. ...
2. ...
3. ...
```

### 5.3 状态枚举

```text
todo            未开始
in_progress     开发中
blocked         阻塞
needs_review    待审查
needs_test      待测试
done            已完成
deprecated      已废弃
```

---

## 6. KNOWLEDGE_LOG.md 维护规范

### 6.1 文件用途

`KNOWLEDGE_LOG.md` 是项目最重要的知识沉淀文档，用于记录每个关键模块的技术理解、实现过程、问题解决、答辩素材和简历素材。

该文件不是简单日志，而是最终答辩和简历包装的原始素材库。

### 6.2 每个节点必须包含的内容

每完成一个关键节点，必须追加如下模板：

```markdown
## [节点名称] 技术总结

完成时间：
对应阶段：V0 / V1 / V2
对应蓝图章节：
相关代码路径：
相关文档：
验证状态：

### 1. 模块目标

说明这个模块解决什么问题，为什么项目需要它。

### 2. 技术背景

说明该模块涉及的技术概念，例如 FastAPI、Qwen Model Gateway、A2A-lite、MCP-compatible ToolManager、RAG、Harness 等。

### 3. 实现内容

详细说明实现了哪些文件、接口、类、函数、数据结构和流程。

### 4. 核心流程

用步骤或 Mermaid 图说明执行链路。

### 5. 关键数据结构

列出核心 JSON / Pydantic Schema / TypeScript 类型。

### 6. 关键代码说明

摘录最有代表性的代码片段，并解释为什么这样写。

### 7. 设计取舍

说明为什么选择当前方案，而不是其他方案。

示例：
- 为什么 V1 做 A2A-lite，而不是完整 A2A 协议？
- 为什么 V1 做 MCP-compatible ToolManager，而不是标准 MCP Server？
- 为什么使用 Qwen-only Model Stack？
- 为什么用 Qdrant，而不是直接数据库 LIKE 查询？

### 8. 替代方案对比

列出至少 1-3 个替代方案，并说明优缺点。

### 9. 踩坑记录

记录开发过程中遇到的问题、错误信息、排查过程和解决方法。

### 10. 测试与验证

说明如何验证该模块可用，包括：
- 单元测试
- 集成测试
- Harness 验证
- Mock Mode 验证
- Demo 验证

### 11. 性能与稳定性

记录延迟、吞吐、失败率、fallback、异常处理等情况。

### 12. 与项目亮点的关系

说明该模块如何支撑项目亮点。

### 13. 答辩讲法

用 3-5 句话说明答辩时如何讲这个模块。

### 14. 简历写法

给出 1-2 条可直接写进简历的描述。

### 15. 后续优化

列出后续可增强方向。
```

### 6.3 总结详细程度要求

知识总结必须“超级详细”，不能只写：

```text
完成了 FastAPI 后端。
```

必须写清楚：

```text
为什么做
怎么做
用了哪些技术
代码在哪里
接口是什么
如何验证
遇到什么问题
为什么这样设计
怎么讲给评委听
怎么写进简历
```

---

## 7. CHANGELOG.md 维护规范

### 7.1 文件用途

记录每次重要变更，尤其是代码、接口、目录、数据结构、评测、Demo 和文档变化。

### 7.2 推荐格式

```markdown
# Changelog

## [Unreleased]

### Added
- 新增 FastAPI 推荐接口 `/api/recommend`

### Changed
- 调整 AgentState schema，增加 `skill_executions`

### Fixed
- 修复 Qdrant 检索返回空结果时的异常

### Deprecated
- 标记旧版检索脚本为 deprecated

### Removed
- 禁止直接删除，如确需删除必须说明原因

### Security
- 增加 Tool allowlist 校验
```

### 7.3 更新触发条件

以下情况必须更新 `CHANGELOG.md`：

```text
新增核心模块
修改 API
修改数据结构
修改目录结构
修改工具调用方式
修改 Agent 工作流
新增测试或评测
新增 Demo Pack
修复关键 Bug
引入或废弃依赖
```

---

## 8. DECISION_LOG.md 技术决策记录规范

### 8.1 文件用途

记录关键技术决策，避免后续忘记为什么这样设计。

### 8.2 模板

```markdown
## ADR-001：采用 Qwen-only Model Stack

日期：
状态：accepted / rejected / superseded

### 背景

### 决策

### 原因

### 替代方案

### 影响

### 后续观察
```

### 8.3 必须记录的决策

```text
选择 Qwen-only Model Stack
选择 LangGraph / 自研 Workflow
选择 FastAPI
选择 Android Native Client
选择 Kotlin + Jetpack Compose + Material 3
选择 Retrofit + OkHttp / Coroutines + StateFlow / Coil / Android Photo Picker
选择 Qdrant
选择 A2A-lite 而不是完整 A2A
选择 MCP-compatible ToolManager 而不是完整 MCP Server
选择 Demo Pack / Mock Mode
选择轻量 Evidence Graph Lite 而不是 Neo4j
```

---

## 9. MILESTONE_SUMMARY.md 维护规范

### 9.1 文件用途

每完成一个阶段，生成阶段总结，用于答辩 PPT、项目复盘和简历材料。

### 9.2 里程碑节点

```text
M0：项目初始化完成
V0：文本导购闭环完成
V0-Android：Android 文本输入和 ProductCard 展示完成
V1-alpha：多模态输入和 Qwen-VL 解析完成
V1-beta：Evidence RAG + Decision Scoring 完成
V1-rc：Android 可视化 + Harness + Demo Pack 完成
V1-final：参赛版完整闭环完成
```

### 9.3 模板

```markdown
## V1-beta 里程碑总结

完成时间：
阶段目标：
完成内容：
核心亮点：
关键代码路径：
Demo 效果：
测试结果：
未解决问题：
答辩素材：
简历素材：
下一阶段计划：
```

---

## 10. Agent 编程行为规范

### 10.1 每次开发前必须做

AI Agent 在开始开发前必须：

1. 阅读 `OMNICART_AGENT_COMPLETE_BLUEPRINT.md`。
2. 阅读 `DEVELOPMENT_RULES.md`。
3. 阅读 `DEVELOPMENT_PROGRESS.md`。
4. 明确当前任务属于 V0-Core / V0-Android / V1-Core / V1-Android / V1-Plus / V1-Advanced / V2。
5. 输出本次任务计划。
6. 确认是否涉及不可变文件。
7. 确认是否需要更新知识总结。
8. 如果是 Android 端开发，必须说明属于 V0-Android 还是 V1-Android，以及会影响哪些 Compose / ViewModel / network / model 文件。

### 10.2 每次开发中必须做

开发过程中必须：

```text
小步修改
保持可运行
优先补测试
记录关键设计决策
遇到不确定不擅自改架构
不引入无必要依赖
不将 V2 能力混入 V1 主线
不使用 Web、WebView、React Native、Expo、Flutter 作为最终交付端
不继续创建 frontend/ 作为主线目录
```

### 10.3 每次开发后必须做

开发结束后必须：

1. 总结修改内容。
2. 说明代码路径。
3. 说明如何运行。
4. 说明如何测试。
5. 如果是 Android 端开发，说明如何在 Android 模拟器或真机运行，以及是否可打包 APK。
6. 更新 `DEVELOPMENT_PROGRESS.md`。
7. 如完成关键节点，更新 `KNOWLEDGE_LOG.md`。
8. 如有变更，更新 `CHANGELOG.md`。
9. 如有关键技术取舍，更新 `DECISION_LOG.md`。
10. 给出下一步建议。

每完成 Android 关键节点，必须更新 `DEVELOPMENT_PROGRESS.md`、`KNOWLEDGE_LOG.md` 和 `CHANGELOG.md`。

### 10.4 四 Tab 客户端开发规则

四个主页面都必须围绕完整购物链路服务：

```text
商品展示 -> 问豆仔 -> 加入购物车 -> 模拟结算 -> 个人中心偏好/地址
```

规则：

1. 商品展示、豆仔智能、购物车、个人中心都是主页面，不能只实现单一豆仔智能页。
2. 商品展示、购物车、个人中心是产品完整性能力，不能弱化豆仔智能作为核心创新页面的地位。
3. 商品展示页只展示数据集中已有商品，不在文档或代码里硬编码具体商品内容。
4. 付款只能做 mock checkout / 模拟结算，不接入真实支付 SDK、真实支付网关或真实下单系统。
5. 购物车只做比赛版购物车和模拟订单，不生成真实订单。
6. 用户信息、收货地址、个人偏好、购物车和模拟订单必须绑定 `user_id`。
7. 豆仔可以通过受控 action 操作购物车，但必须调用后端 service，不能直接写数据库。
8. 每完成商品展示、豆仔智能、购物车、个人中心任一主页面，必须更新 `KNOWLEDGE_LOG.md`。
9. 新增传统电商能力时，必须说明它如何服务主 Demo 或用户体验，不允许传统电商功能喧宾夺主。

---

## 11. 质量门禁规则

### 11.1 节点完成门禁

一个节点只有同时满足以下条件，才能标记为 `done`：

```text
功能已实现
基本测试通过
接口或 UI 可访问
关键日志或 Trace 可查看
文档已更新
CHANGELOG 已更新
知识总结已写入
没有破坏蓝图主线
```

### 11.2 RAG 模块门禁

RAG 相关模块完成必须满足：

```text
支持文本或多模态检索
返回 evidence_ids
支持 reranking 或排序规则
支持 Evidence Sufficiency Checker
支持无结果 fallback
有最小 golden query 验证
```

### 11.3 Agent 模块门禁

Agent 相关模块完成必须满足：

```text
输入输出 schema 明确
状态写入 AgentState
产生 TraceStep
必要时产生 Artifact
失败时有 fallback
不直接绕过 Workflow
```

### 11.4 Tool 模块门禁

Tool 相关模块完成必须满足：

```text
有 Tool Manifest
有 input_schema
有 output_schema
有 allowed_agents
有 permission_level
有 timeout_ms
有 ToolCallRecord
通过 schema validation
```

### 11.5 Harness 模块门禁

Harness 模块完成必须满足：

```text
支持 schema validation
支持 evidence validation
支持 score validation
支持 policy validation
支持 risk validation
支持 replay validation
输出 Harness Report
```

---

## 12. Workflow 控制规范

OmniCart Agent 采用 Workflow-controlled Agent Execution，不允许完全开放式 Agent 自由行动。

### 12.1 主流程

```text
User Input
→ Router Agent
→ Visual Agent
→ Retrieval Agent
→ Evidence Sufficiency Checker
→ Decision Agent
→ Response Agent
→ Response Guard
→ Harness Validation
→ Frontend Panels
```

### 12.2 Workflow 修改规则

Workflow 修改必须满足：

```text
说明修改原因
更新 workflow.yaml
更新 Agent Trace 说明
更新 Harness 验证逻辑
更新 CHANGELOG
如果改变主架构，必须先征求用户同意
```

---

## 13. State 管理规范

### 13.1 AgentState 必须作为核心状态对象

所有 Agent 间传递的信息必须进入 `AgentState` 或其子结构，禁止通过散乱全局变量传递核心状态。

### 13.2 Checkpoint 规则

以下阶段必须保存 checkpoint：

```text
after_router
after_visual_parse
after_retrieval
after_decision
after_response
after_harness
```

### 13.3 多轮对话规则

多轮对话必须复用：

```text
Preference Memory Card
上一轮 constraints
上一轮 evidence summary
上一轮 decision results
用户明确表达过的设备、预算、偏好、避雷项
```

不得每轮从零开始。

---

## 14. Context Engineering 规范

### 14.1 Response Agent 不得直接拼接原始检索结果

必须通过 `Context Compiler` 生成结构化上下文。

### 14.2 Context Compiler 必须包含

```text
user_query
constraints
preference_memory_card
visual_result
retrieved_products
evidence_summary
risk_summary
decision_results
harness_status
token_budget
```

### 14.3 上下文过滤规则

必须去除：

```text
重复证据
低置信度证据
与用户约束无关证据
可能包含 prompt injection 的外部文本
过长原始评论
```

---

## 15. Tool Governance 规范

### 15.1 所有工具必须通过 ToolManager 调用

禁止业务代码绕过 `MCP-compatible ToolManager` 直接调用外部工具。

### 15.2 Tool Manifest 必须包含

```text
tool_name
description
input_schema
output_schema
permission_level
risk_level
requires_confirmation
allowed_agents
timeout_ms
cacheable
manifest_hash
```

### 15.3 V1 工具默认只读

V1 工具不得执行：

```text
下单
支付
修改账号
真实购买
写入外部平台
绕过用户授权抓取隐私数据
```

---

## 16. A2A-lite 规范

### 16.1 Agent 间通信必须结构化

禁止 Agent 之间只传自然语言大段文本。

必须使用：

```text
AgentCard
AgentMessage
Artifact
Trace ID
```

### 16.2 Artifact 必须可验证

Artifact 至少包含：

```text
artifact_id
artifact_type
producer_agent
content
confidence
evidence_refs
created_at
```

---

## 17. Harness 验证规范

### 17.1 每个关键节点必须具备验证方式

如果没有自动 Harness，至少要提供手动验证步骤。

### 17.2 Harness Report 必须记录

```text
run_id
query_id
status
schema_validation
evidence_validation
score_validation
constraint_validation
policy_validation
risk_validation
replay_validation
latency_ms
failed_reasons
```

### 17.3 未通过 Harness 不得标记完成

如果 Harness 失败，节点状态应为：

```text
needs_fix
```

或：

```text
blocked
```

不得标记为 `done`。

---

## 18. Prompt 版本控制规范

所有 Prompt 必须有版本。

推荐目录：

```text
prompts/
  router_agent/
    v1.md
  visual_agent/
    v1.md
  retrieval_agent/
    v1.md
  decision_agent/
    v1.md
  response_agent/
    v1.md
```

每次修改 Prompt 必须记录：

```text
修改原因
修改前问题
修改后效果
测试 query
是否影响 Harness
```

---

## 19. Demo Pack / Mock Mode 规范

### 19.1 Demo Pack 必须包含

```text
固定主 Demo 图片
预置商品数据
预置视觉解析结果
预置检索结果
预置 evidence_list
预置 skill_executions
预置 tool_call_records
预置 decision_results
预置 harness_report
预置 final_response
预置 trace_steps
```

### 19.2 Mock Mode 规则

Mock Mode 只能作为比赛稳定性兜底，不得替代真实链路开发。

当 Mock Mode 开启时，Android 客户端必须显示：

```text
当前为 Mock Mode
```

避免误导。

---

## 20. 安全红线

AI Agent 不得执行以下操作：

```text
删除最终蓝图
擅自修改最终蓝图
删除历史开发记录
硬编码 API Key
提交密钥到仓库
执行真实支付或下单
接入真实支付 SDK 或真实支付网关
Agent 直接写入购物车/订单数据库
绕过 user_id 绑定写用户、地址、偏好数据
抓取用户隐私数据
绕过 Tool Governance
绕过 Response Guard
编造测试结果
伪造 Harness 通过
把未完成节点标记为完成
```

---

## 21. 开发过程推荐触发词

用户可以使用以下触发词管理开发过程：

```text
进行记忆存储
标记节点完成：<节点名>
生成知识总结：<节点名>
更新开发进度
查看当前进度
生成里程碑总结：<里程碑名>
运行验证：<模块名>
运行 Harness
生成答辩素材：<模块名>
生成简历描述：<模块名>
记录技术决策：<决策名>
记录踩坑：<问题名>
开启 Mock Mode
关闭 Mock Mode
生成 Demo 脚本
更新 CHANGELOG
```

---

## 22. 推荐节点命名规范

```text
project_init
fastapi_backend
android_native_client
bottom_navigation
product_home
douzai_intelligence
cart
profile_center
mock_checkout
agent_action_service
v0_android
v1_android
qwen_model_gateway
schema_design
router_agent
visual_agent
retrieval_agent
decision_agent
response_agent
context_compiler
preference_memory_card
adaptive_retrieval
evidence_sufficiency_checker
evidence_graph_lite
visual_evidence_grounding
constraint_solver
decision_scoring
skill_registry
mcp_compatible_toolmanager
a2a_lite
decision_harness
state_checkpoint
response_guard
demo_pack
mock_mode
evaluation_baseline
android_panels
main_demo
```

---

## 23. 每次回答的最低要求

当 AI Agent 执行开发任务后，回复用户至少包含：

```text
完成了什么
修改了哪些文件
如何运行
如何测试
是否更新进度文档
是否更新知识文档
是否更新 CHANGELOG
下一步建议
```

如果没有更新某个文档，必须说明原因。

---

## 24. 最终交付前检查清单

参赛版最终交付前必须检查：

```text
[ ] V1 主 Demo 可完整运行
[ ] 真实链路可运行
[ ] Mock Mode 可运行
[ ] Android App 可在模拟器或真机运行
[ ] Android APK 可打包
[ ] 底部四 Tab 可用：商品展示、豆仔智能、购物车、个人中心
[ ] 商品展示页可浏览商品和进入详情
[ ] 商品详情可跳转豆仔智能咨询当前商品
[ ] 购物车可增删改、多选、全选和模拟结算
[ ] 个人中心可展示 Demo 用户、地址和偏好
[ ] 豆仔智能可通过受控 action 加入购物车
[ ] Android ProductCard 可展示
[ ] Android EvidencePanel 可展示
[ ] Android AgentTracePanel 可展示
[ ] Android SkillExecutionPanel 可展示
[ ] Android HarnessValidationPanel 可展示
[ ] Decision Score 可解释
[ ] 所有推荐有 evidence_ids
[ ] 主 Demo 有 Demo Script
[ ] Baseline 对比完成
[ ] README 完整
[ ] DEVELOPMENT_PROGRESS 更新
[ ] KNOWLEDGE_LOG 完整
[ ] CHANGELOG 完整
[ ] MILESTONE_SUMMARY 完整
[ ] 简历描述准备完成
[ ] 答辩讲稿准备完成
```

---

## 25. 给 Claude Code / Codex 的系统级执行指令

以下内容可直接放入 `CLAUDE.md`、`AGENTS.md` 或 Codex 项目指令中：

```text
你是 OmniCart Agent 项目的 AI 编程助手。你必须严格遵守 DEVELOPMENT_RULES.md。

核心规则：

1. OMNICART_AGENT_COMPLETE_BLUEPRINT.md 是最终蓝图，默认只读，除非用户明确授权，否则不得修改。
2. 每次开发前必须读取最终蓝图、开发规则和开发进度。
3. 不得擅自改变项目主线：Android Native Client 四 Tab、豆仔智能核心 Agent 页面、Qwen-only Model Stack、5 Agent Workflow、Multimodal Evidence RAG、Skill Registry、MCP-compatible ToolManager、A2A-lite、Decision Harness、State Checkpoint。
4. V1 是参赛版，必须保持工程可落地，不得把 V2 能力强行塞进 V1。
5. 禁止使用 Web、WebView、React Native、Expo、Flutter 作为最终交付端，禁止继续创建 frontend/ 作为主线目录。
6. Android 端开发必须说明属于 V0-Android 还是 V1-Android，完成后必须说明模拟器或真机运行方式。
7. 付款只能做 mock checkout，Agent 只能通过受控 action 操作购物车，所有用户、地址、偏好数据必须绑定 user_id。
8. 当用户说“进行记忆存储”时，必须更新 DEVELOPMENT_PROGRESS.md；如果完成关键节点，还必须更新 KNOWLEDGE_LOG.md 和 CHANGELOG.md。
9. 每完成一个关键技术节点，必须写入超级详细知识总结，用于答辩和简历沉淀。
10. 未通过测试或 Harness 验证，不得将节点标记为 done。
11. 不得删除历史文件，只能标记 deprecated 或归档。
12. 所有工具调用必须通过 ToolManager，所有 Agent 通信必须使用结构化 schema。
13. 所有推荐结论必须绑定 evidence_ids，不允许无证据生成。
14. 每次完成开发任务后，必须说明修改文件、运行方式、测试方式、文档更新情况和下一步建议。
```

---

## 26. 总结

本规则文档的核心目标是让 OmniCart Agent 的开发过程本身具备可控性、连续性和可沉淀性。

AI Agent 不能只是写代码，还必须帮助项目维护：

```text
开发进度
技术知识
设计决策
变更日志
测试验证
答辩素材
简历素材
```

最终项目不仅要做出一个能跑的多模态购物决策 Agent，还要形成一套完整的工程化开发记录，使项目能够在比赛答辩、简历展示和后续迭代中持续发挥价值。
