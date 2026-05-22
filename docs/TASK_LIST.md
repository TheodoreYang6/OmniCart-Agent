# OmniCart Agent 任务清单

> 更新：2026-05-22 | 当前阶段：V1-Core（约 75% 完成）

---

## V0-Core（已完成 ✅）

- [x] FastAPI 后端骨架
- [x] Product / Evidence / DecisionResult / Visual Schema
- [x] Qwen Model Gateway（Mock + 真实双模式，7 能力）
- [x] 商品数据（100 件 4 品类官方数据集）
- [x] Text Retriever（jieba 分词 + rag_knowledge 全文检索）
- [x] Decision Scoring（7 维加权公式）
- [x] /api/recommend + /api/upload 接口
- [x] 单元测试 22 个 + 集成测试 8 个

## V0-Android（已完成 ✅）

- [x] Gradle 项目骨架 + 依赖配置
- [x] MainActivity + Compose Theme（Color/Type/Theme）
- [x] Bottom Navigation 四 Tab（商品/豆仔/购物车/我的）
- [x] Network Layer（Retrofit/OkHttp/ApiClient）
- [x] Data Models（Product/Sku/RecommendRequest/Response/DecisionResult）
- [x] ChatScreen + ChatInputBar + MessageBubble
- [x] ProductCard + ProductDetailSheet（6 Tab）
- [x] ProductListScreen + 品类筛选 Tabs
- [x] CartScreen + CartViewModel
- [x] ProfileScreen
- [x] ImagePicker + ImagePreview（拍照/相册）
- [x] PlusMenuSheet + DemoScenarioSelector
- [x] Demo Mode 假数据
- [x] 模拟器/真机运行

## V1-Core 后端（进行中）

### P0 — 阻塞完赛（0 项，全部完成 ✅）

- [x] PostgreSQL + Qdrant 双数据库架构
- [x] Repository 抽象层（ABC + 工厂 + 双实现）
- [x] Hybrid Search（Qdrant 向量 + jieba 关键词 RRF 融合）
- [x] 5 Agent LangGraph Workflow
- [x] /api/recommend/v2 端点
- [x] /api/products + /api/products/{id}
- [x] /api/cart CRUD + /api/checkout + /api/agent/action
- [x] Preference Memory（多轮记忆 + 话题切换）
- [x] Context Compiler
- [x] Response Guard（5 项守门）
- [x] Qwen Reranker 精排
- [x] Async Retrieval（三通道并行）
- [x] 31 单元测试全部通过

### P1 — V1 质量线（剩余 8 项）

| # | 任务 | 蓝图要求 | 当前状态 |
|---|------|---------|---------|
| 1 | **用户登录/注册 API** | auth API | 未开始。硬编码 `demo_user_001` |
| 2 | **收货地址 CRUD API** | addresses API | 未开始。ProfileScreen 静态假文字 |
| 3 | **用户偏好 REST API** | preference API | `PreferenceMemory` 已有 PG 持久化，但无 REST 端点 |
| 4 | **Evidence Sufficiency Checker 接入 Workflow** | 证据充足性检查 | `evidence_checker.py` 已实现但从未被调用 |
| 5 | **Skill Registry** | 技能注册中心 | 未开始。Skill Tab 展示静态假列表 |
| 6 | **MCP-compatible ToolManager** | 工具统一管理 | 未开始。Agent 直接调 repo，无工具抽象层 |
| 7 | **State Checkpoint** | 工作流状态持久化 | 未开始。`PreferenceMemory` 仅存约束不存完整 state |
| 8 | **baseline 对比脚本** | 评估对比 | 未开始 |

### P2 — 参赛打磨（剩余 10 项）

| # | 任务 | 蓝图要求 | 当前状态 |
|---|------|---------|---------|
| 9 | Evidence Graph Lite | 商品-参数-评论图关系 | 未开始。NetworkX 已安装 |
| 10 | Visual Evidence Grounding | 字段级视觉证据引用 | Visual Agent 有字段提取但未做 grounding 绑定 |
| 11 | Counterfactual Recommendation | 0 结果时反事实建议 | Context Compiler 有 stub，未正式实现 |
| 12 | Constraint Solver | 约束求解 | 未开始 |
| 13 | Declarative workflow.yaml | YAML 声明式配置 | `workflow/` 目录只有 `graph.py`，无 YAML |
| 14 | Tiered Multimodal Fallback | 多模态降级链路 | 仅有 Mock/Real 切换，无分层降级 |
| 15 | Hierarchical Shopping Knowledge Index | 分层知识索引 | 检索为扁平结构，无层级 |
| 16 | Decision Harness | 决策验证框架 | `ResponseGuard` 部分覆盖，无完整 Harness |
| 17 | A2A-lite 集成到 Agent 通信 | AgentMessage/Artifact | Schema 已定义但 Agent 间仍用 WorkflowState dict |
| 18 | Demo Pack 一键演示数据 | 预设 Demo 场景 | Android Demo Mode 有 3 个假商品，无完整 Pack |

---

## V1-Core Android（进行中）

### P0 — 阻塞完赛（1 项）

| # | 任务 | 当前状态 |
|---|------|---------|
| 19 | **APK Release 打包** | Debug APK 可用，Release 未配置签名 |

### P1 — V1 质量线（剩余 6 项）

| # | 任务 | 蓝图要求 | 当前状态 |
|---|------|---------|---------|
| 20 | 登录/注册页面 | auth UI | 未开始 |
| 21 | 地址管理页面 | address UI | 未开始。ProfileScreen 静态占位 |
| 22 | 偏好设置页面 | preference UI | 未开始。ProfileScreen 静态占位 |
| 23 | EvidencePanel 独立组件 | 证据面板 | ProductDetailSheet 内嵌简易版，无独立组件 |
| 24 | AgentTracePanel 独立组件 | 链路面板 | ProductDetailSheet 内嵌简易版 |
| 25 | HarnessValidationPanel 独立组件 | 验证面板 | ProductDetailSheet 内嵌，图标全是 Close（应为 ✅/❌） |

### P2 — 参赛打磨（剩余 4 项）

| # | 任务 | 蓝图要求 | 当前状态 |
|---|------|---------|---------|
| 26 | SkillExecutionPanel | 技能执行面板 | 展示静态假列表 |
| 27 | ScoreBreakdown 独立组件 | 7 维评分可视化 | ProductDetailSheet 内嵌 `LinearProgressIndicator`，基本可用 |
| 28 | Mock Mode 一键演示 | 预设演示流程 | Demo Mode 仅 3 个假耳机，无完整演示 |
| 29 | 主 Demo 充电宝截图数据 | 预设测试数据 | 未准备 |

---

## V1-Plus（加分项，0/10 完成）

| # | 任务 |
|---|------|
| 30 | Retrieval Plan Panel（检索计划可视化） |
| 31 | Context Panel（上下文面板） |
| 32 | Preference Memory Card 展示 |
| 33 | Visual Evidence Grounding 可视化 |
| 34 | Counterfactual Recommendation 展示 |
| 35 | Evidence Graph Path 可视化 |
| 36 | Tool Governance 展示 |
| 37 | Fallback Status 面板 |
| 38 | 更完整 Demo Pack 回放 |
| 39 | baseline 对比结果展示 |

---

## V2/V3（扩展规划，0/12 完成）

| # | 任务 | 说明 |
|---|------|------|
| 40 | 标准 MCP Server/Client | 当前只做了 MCP-compatible |
| 41 | 标准 A2A Protocol | 当前只做了 A2A-lite Schema |
| 42 | Neo4j GraphRAG | 替代 NetworkX 轻量图 |
| 43 | Qwen-Omni 语音导购 | 多模态语音交互 |
| 44 | iOS SwiftUI 客户端 | 第二交付端 |
| 45 | Computer Use / Browser Use | 真实网页操作 |
| 46 | 用户长期偏好记忆 | 跨会话持久化 |
| 47 | Redis 缓存层 | 视觉解析/Demo Pack 缓存 |
| 48 | 在线反馈学习 / Bandit 排序 | 用户行为学习 |
| 49 | Langfuse / Phoenix 可观测性 | LLM 调用追踪 |
| 50 | 大规模商品数据（1000+ 件） | 扩展数据集 |
| 51 | Evaluation Dashboard | 完整评估面板 |

---

## 优先级总览

```
P0 (阻塞完赛)   : #19 APK 打包                   → 1 项, ~1h
P1 (V1 质量线)  : #1-8 后端 + #20-25 Android      → 14 项, ~3-5 天
P2 (参赛打磨)   : #9-18 后端 + #26-29 Android      → 14 项, ~3-5 天
V1-Plus (加分)  : #30-39                          → 10 项, ~1 周
V2/V3 (扩展)    : #40-51                          → 12 项, 比赛后
```

**建议执行顺序**：
```
#19 (APK) → #1 (Auth) → #2 (Address) → #3 (Preference API)
→ #20-22 (Android Auth/Address/Preference UI) → #4-8 (后端 P1)
→ #23-29 (Android P2) → #9-18 (后端 P2) → V1-Plus → V2
```
