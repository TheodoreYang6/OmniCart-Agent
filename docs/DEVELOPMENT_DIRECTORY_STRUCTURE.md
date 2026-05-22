# OmniCart Agent 开发目录结构与工程施工规范

本文档基于 [OMNICART_AGENT_COMPLETE_BLUEPRINT.md](./OMNICART_AGENT_COMPLETE_BLUEPRINT.md) 生成，用作 OmniCart Agent 从当前未开发底座进入正式开发阶段的目录施工图和工程执行规范。

它描述的是项目最终目标结构，不代表项目初始化时必须一次性创建所有目录和文件。

请牢记三句话：

1. 目录结构是目标结构，不是一次性生成清单。
2. 开发必须遵循“竖向闭环优先”原则。
3. 禁止一次性生成大量无调用方、无输入输出、无测试方式的空壳文件。

任何新文件的创建都必须服务当前里程碑，并满足以下条件：

- 有明确职责。
- 有明确输入输出。
- 有明确调用方。
- 有明确验收标准。
- 必要时有测试文件。
- 不破坏当前已跑通的主链路。

目标不是“把目录填满”，而是让 OmniCart Agent 按 V0-Core -> V0-Android -> V1-Core -> V1-Android -> V1-Plus -> V1-Advanced -> V2/V3 的顺序逐步跑起来。

## 1. 目录设计原则

OmniCart Agent 是参赛版项目，不是企业级全量平台。因此目录结构需要同时满足三个要求：

1. **比赛可展示**：能清楚看到 Agent、RAG、Skill、Tool、Trace、Harness、Demo Pack 等亮点。
2. **工程可落地**：每个模块边界清楚，能按优先级逐步实现。
3. **长期可扩展**：V1 使用轻量实现，V2 / V3 可以平滑接入标准 MCP、标准 A2A、Neo4j、Langfuse / Phoenix、语音导购等增强能力。

目录采用“双层组织”：

- `backend/`：后端 Agent Runtime、RAG、检索、决策、验证、API。
- `android-client/`：V1 参赛主交付端，Android 原生四 Tab 客户端，包括商品展示、豆仔智能、购物车、个人中心，以及 ProductCard、Evidence、Trace、Skill、Harness、Demo Mode。

`frontend/` 不再作为主线目录。历史文档或历史代码中出现的 `frontend/`、Next.js、React、TailwindCSS 统一视为 deprecated，不再新增或维护。Web、WebView、React Native、Expo、Flutter 不得作为最终交付端。

同时保留：

- `data/`：商品、评论、政策、兼容性规则、图片、golden queries。
- `demo/`：主 Demo、Demo Pack、截图、演示脚本。
- `scripts/`：索引构建、数据导入、评测、Demo Pack 生成。
- `eval/`：Baseline、指标、报告。
- `docs/`：蓝图、目录说明、开发任务、API、架构、开发指南。
- `infra/`：Docker Compose 和后续部署配置。

## 2. 防空壳开发规则

先完成一条可运行的竖向闭环，再逐步横向扩展高级模块。

规则：

1. 禁止一次性创建完整空壳目录。
2. 禁止创建没有调用方的文件。
3. 禁止创建只包含 `pass`、`TODO`、`placeholder` 的核心模块。
4. 禁止为了匹配目录结构而提前实现 V2/V3 模块。
5. 每个新增文件必须在当前 milestone 中被调用或被测试。
6. 每个新增模块必须说明它属于 V0-Core、V0-Android、V1-Core、V1-Android、V1-Plus、V1-Advanced、V2 或 V3。
7. 每个新增模块必须能在 README、测试脚本或 API 链路中体现用途。
8. 如果一个模块暂时不会实现，只允许在文档中列为 planned，不允许创建空代码文件。
9. 任何改动不得破坏 V0/V1-Core 主链路。
10. 如果新功能导致主链路不可用，必须优先修复或回滚。
11. Android 客户端也必须遵守防空壳规则，不允许一次性生成完整 `android-client/` 空文件树。
12. V0-Android 未跑通前，不允许开发完整 Evidence、Trace、Harness、Skill 等高级 UI。
13. 新增商品展示、购物车、个人中心后，仍必须按 V0-Android -> V1-Core -> V1-Android -> V1-Plus 分阶段创建，不允许一次性铺满用户、购物车、地址、订单、Agent Action 全部空文件。
14. 豆仔智能仍是核心创新页面，传统电商基础功能必须服务主 Demo 和用户体验，不能喧宾夺主。

开发判断标准：

```text
如果一个文件当前没有调用方、没有测试方式、没有验收标准，就先不要创建它。
```

## 3. V0-Core 最小可运行目录

V0-Core 的目标不是实现完整 Agent Runtime，而是先跑通最小文本导购闭环：

```text
用户文本输入
  -> 后端 API
  -> 商品数据读取
  -> 文本检索
  -> 决策评分
  -> 推荐结果结构化返回
```

V0-Core 最小目录：

```text
backend/
  app/
    main.py
    api/
      health.py
      recommend.py
    core/
      config.py
    schemas/
      product.py
      evidence.py
      decision_result.py
    model_gateway/
      gateway.py
      qwen_chat.py
      qwen_embedding.py
    repositories/
      product_repo.py
      vector_repo.py
    retrieval/
      text_retriever.py
    decision/
      scoring.py

data/
  products.json
  golden_queries.json

scripts/
  build_text_index.py
  smoke_recommend.py

tests/
  unit/
    test_scoring.py
    test_text_retriever.py
  integration/
    test_recommend_api.py
```

V0-Core 没有跑通之前，不允许优先开发：

- A2A-lite
- MCP-compatible ToolManager
- Skill Registry
- Harness
- Evidence Graph
- Visual Grounding
- Preference Memory
- Declarative Workflow
- Long-term memory
- Standard MCP Server
- Standard A2A Protocol

## 4. V0-Android 最小可运行目录

V0-Android 的目标是跑通原生四 Tab 客户端最小购物闭环：

```text
Android 底部四 Tab
  -> 商品展示基础数据
  -> 豆仔智能文本推荐
  -> 购物车基础增删
  -> 个人中心 Demo 用户
```

V0-Android 最小目录：

```text
android-client/
  settings.gradle.kts
  build.gradle.kts
  app/
    build.gradle.kts
    src/main/
      AndroidManifest.xml
      java/com/omnicart/agent/
        MainActivity.kt
        MainScaffold.kt
        core/
          config/AppConfig.kt
          network/ApiClient.kt
          network/OmniCartApi.kt
          network/NetworkResult.kt
          model/RecommendRequest.kt
          model/RecommendResponse.kt
          model/Product.kt
          model/User.kt
          model/CartItem.kt
          model/DecisionResult.kt
          theme/Color.kt
          theme/Theme.kt
          theme/Type.kt
        feature/
          product/ProductHomeScreen.kt
          product/ProductCard.kt
          product/ProductDetailScreen.kt
          douzai/DouzaiChatScreen.kt
          douzai/DouzaiViewModel.kt
          douzai/DouzaiUiState.kt
          douzai/ChatInputBar.kt
          cart/CartScreen.kt
          cart/CartItemRow.kt
          profile/ProfileScreen.kt
          demo/DemoModeSwitch.kt
        navigation/AppNavGraph.kt
        navigation/BottomNavBar.kt
```

## 5. V1 开发优先级分层

### 5.1 V1-Core：后端参赛主链路必须完成

V1-Core 决定项目是否能参赛展示，优先级最高。

必须完成：

- 用户登录 / Demo 用户
- 商品列表 / 商品详情 / 商品搜索 API
- 购物车查询、加入、删除、数量修改 API
- 地址和用户偏好 API
- Agent Action Service 受控购物车动作
- 图片上传
- Qwen-VL 图片解析
- Visual Agent
- 5 Agent Workflow
- Multimodal Evidence RAG
- 评论风险检索
- 政策规则检索
- 兼容性规则检索
- Decision Scoring
- Demo Pack / Mock Mode
- 主 Demo 稳定跑通

V1-Core 主链路：

```text
图片 + 文本 query
  -> 当前商品上下文 / 用户偏好
  -> Visual Agent
  -> Multimodal Evidence RAG
  -> Decision Agent
  -> Response Agent
  -> Agent Action 可受控加入购物车
  -> Android EvidencePanel
  -> Android AgentTracePanel
  -> Demo Pack / Mock Mode
```

### 5.2 V1-Android：参赛客户端核心展示

V1-Android 在 V0-Android 跑通后开发，负责登录/地址/偏好、图文输入、豆仔加入购物车、模拟结算和主 Demo 展示。

必须完成：

- 图片选择 / 上传
- ImagePreview
- 登录 / 注册 / Demo 用户
- 地址管理
- 用户偏好管理
- 豆仔对话加入购物车
- 购物车多选、全选、模拟结算
- 主 Demo 充电宝截图
- EvidencePanel
- ScoreBreakdown
- AgentTracePanel
- SkillExecutionPanel
- HarnessValidationPanel
- ProductDetailSheet
- Mock Mode 一键演示
- APK 打包

### 5.3 V1-Plus：强加分项

V1-Plus 能让项目从普通多模态 RAG Demo 升级为 Agent Runtime 项目，但不能影响 V1-Core 交付。

建议完成：

- Skill Registry
- MCP-compatible ToolManager
- A2A-lite AgentMessage / Artifact
- Context Compiler
- Constraint Solver
- Evidence Sufficiency Checker
- Response Guard
- Android SkillExecutionPanel
- Android HarnessValidationPanel
- Baseline 对比脚本

### 5.4 V1-Advanced：有时间再做

这些功能有很强前沿感，但不是主 Demo 跑通的前置条件。时间不足时可以先用静态 Demo Pack 或半动态方式展示。

可选完成：

- Evidence Graph Lite
- Visual Evidence Grounding
- Preference Memory Card
- Counterfactual Recommendation
- Declarative workflow.yaml
- Tiered Multimodal Fallback 完整链路
- Hierarchical Shopping Knowledge Index
- Retrieval Plan Panel
- Evidence Graph Path
- Fallback Status Badge

### 5.5 V2 / V3：扩展规划

只在 V1-Core 和关键 V1-Plus 稳定后考虑：

- 标准 MCP Server / Client
- 标准 A2A Protocol
- Computer Use / Browser Use
- Neo4j GraphRAG
- Qwen-Omni 语音导购
- 用户长期偏好记忆
- Langfuse / Phoenix 可观测性
- 在线反馈学习 / Bandit 排序
- 大规模商品数据接入

## 6. API Contract：后端与 Android 客户端接口契约

在 Android 客户端和后端并行开发前，必须先固定 API 契约，避免 Compose UI 状态和后端返回结构不一致。

所有 API 返回结构必须稳定，Android 客户端不得依赖临时字段，也不得在本地承担复杂推理、RAG、Agent、Decision Scoring 或 Harness 逻辑。

### 6.1 `GET /api/health`

用途：检查后端服务是否正常。

响应示例：

```json
{
  "status": "ok",
  "service": "omnicart-agent",
  "version": "0.1.0"
}
```

### 6.2 `POST /api/recommend`

用途：主推荐接口，支持文本导购和后续图文导购。

请求示例：

```json
{
  "user_query": "我预算 300 元，想买适合 iPhone 15 出差用的充电宝",
  "image_url": null,
  "demo_mode": false
}
```

响应示例：

```json
{
  "session_id": "S001",
  "answer": "推荐结果文本",
  "products": [],
  "evidence_list": [],
  "decision_results": [],
  "trace_steps": [],
  "skill_executions": [],
  "harness_report": {},
  "fallback_status": {}
}
```

V0 可以先返回：

- `session_id`
- `answer`
- `products`
- `evidence_list`
- `decision_results`

V1 再补齐：

- `trace_steps`
- `skill_executions`
- `harness_report`
- `fallback_status`

### 6.3 `POST /api/upload`

用途：上传商品截图或商品图片。

请求：

```text
multipart/form-data image file
```

响应示例：

```json
{
  "file_id": "file_001",
  "image_url": "/uploads/file_001.png"
}
```

### 6.4 `GET /api/demo/scenario/{scenario_id}`

用途：读取预置 Demo Pack 场景。

响应示例：

```json
{
  "scenario_id": "powerbank_flight_demo",
  "user_query": "我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？有没有更合适的？",
  "image_url": "/demo/demo_pack/scenario_01_powerbank_screenshot/input.png",
  "mock_response": {}
}
```

### 6.5 `GET /api/trace/{session_id}`

用途：获取某次会话的 Agent Trace。

响应示例：

```json
{
  "session_id": "S001",
  "trace_steps": []
}
```

### 6.6 用户 API

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/users/me
PUT  /api/users/me/preferences
```

V1 可使用手机号 / 用户名 + 密码登录、Demo 用户一键登录、JWT 或 session token。本地 Android 使用 DataStore 保存登录状态，后端数据必须绑定 `user_id`。

### 6.7 商品 API

```text
GET /api/products
GET /api/products/{product_id}
GET /api/products/search
```

用于商品展示页读取数据集中已有商品信息、商品详情、分类筛选和搜索结果。文档不硬编码具体商品内容，商品数据以 `data/` 或后端 repository 为准。

### 6.8 购物车 API

```text
GET    /api/cart
POST   /api/cart/items
PUT    /api/cart/items/{cart_item_id}
DELETE /api/cart/items/{cart_item_id}
PUT    /api/cart/items/select
POST   /api/cart/checkout/mock
```

购物车支持增删改、多选、全选、价格合计和模拟结算。比赛版只做 mock checkout / 模拟付款 / 模拟订单，不接入真实支付。

### 6.9 地址 API

```text
GET    /api/addresses
POST   /api/addresses
PUT    /api/addresses/{address_id}
DELETE /api/addresses/{address_id}
PUT    /api/addresses/{address_id}/default
```

地址数据必须绑定 `user_id`，支持新增、编辑、删除和设置默认地址。

### 6.10 豆仔智能 Action API

```text
POST /api/agent/actions
```

示例：

```json
{
  "action_type": "add_to_cart",
  "product_id": "P001",
  "quantity": 1,
  "reason": "豆仔根据用户需求推荐并加入购物车"
}
```

`/api/agent/actions` 只允许受控购物车动作，例如 `add_to_cart`、`remove_from_cart`、`update_cart_quantity`。Agent 不直接操作数据库，必须通过 `agent_action_service.py` 调用后端 Cart Service，并在 Trace 或聊天消息中展示动作结果。

### 6.11 新增数据模型

V1 阶段可以使用 SQLite / PostgreSQL / JSON mock 数据，不强制上复杂数据库。

| 模型 | 核心字段 |
|---|---|
| User | `user_id`, `username`, `phone`, `password_hash`, `avatar_url`, `created_at` |
| UserPreference | `user_id`, `devices`, `budget_range`, `preferred_categories`, `preferred_brands`, `avoid_tags`, `scenarios` |
| Address | `address_id`, `user_id`, `receiver_name`, `phone`, `province`, `city`, `district`, `detail`, `is_default` |
| Product | 沿用现有 Product Schema。 |
| CartItem | `cart_item_id`, `user_id`, `product_id`, `quantity`, `selected`, `added_by`, `added_reason`, `created_at` |
| MockOrder | `order_id`, `user_id`, `items`, `total_price`, `address_id`, `status`, `created_at` |

### 6.12 四 Tab 与基础电商文件落地对应

以下清单用于把 `PRODUCT_FUNCTIONS_AND_USER_GUIDE.md` 中的四 Tab 产品设计同步到工程目录。它是落地优先级索引，不代表一次性创建空文件。

Android 端关键文件：

| 文件 | 阶段 | 对应能力 |
|---|---|---|
| `MainScaffold.kt` | V0-Android | 承载全局 Scaffold、底部导航和主页面容器。 |
| `BottomNavBar.kt` | V0-Android | 四 Tab 底部导航：商品展示、豆仔智能、购物车、个人中心。 |
| `ProductHomeScreen.kt` | V0-Android | 商品展示主页，商品列表、搜索、分类入口。 |
| `ProductDetailScreen.kt` | V0-Android / V1-Android | 商品详情、加入购物车、问豆仔。 |
| `DouzaiChatScreen.kt` | V0-Android / V1-Android | 豆仔智能核心 AI Agent 页面。 |
| `CartScreen.kt` | V0-Android / V1-Android | 购物车基础管理、多选、全选、合计。 |
| `MockCheckoutSheet.kt` | V1-Android | 模拟结算，不接入真实支付。 |
| `ProfileScreen.kt` | V0-Android / V1-Android | Demo 用户、登录状态、地址和偏好入口。 |

后端 API 文件：

| 文件 | 阶段 | 对应接口 |
|---|---|---|
| `api/auth.py` | V1-Core | 注册、登录、登出、Demo 用户登录。 |
| `api/products.py` | V0-Android | 商品列表、详情、搜索、分类筛选。 |
| `api/cart.py` | V0-Android / V1-Core | 购物车增删改查、多选、全选、模拟结算。 |
| `api/addresses.py` | V1-Core | 收货地址管理。 |
| `api/users.py` | V0-Android / V1-Core | 当前用户信息和用户偏好入口。 |
| `api/agent_actions.py` | V1-Core | 豆仔智能受控购物车 action。 |

Schemas 文件：

```text
schemas/user.py
schemas/cart.py
schemas/address.py
schemas/preference.py
schemas/order.py
```

Services 文件：

```text
services/user_service.py
services/product_service.py
services/cart_service.py
services/address_service.py
services/preference_service.py
services/agent_action_service.py
```

Repositories 文件：

```text
repositories/user_repo.py
repositories/cart_repo.py
repositories/address_repo.py
```

这些文件必须按里程碑逐步创建：V0-Android 优先商品、购物车基础、Demo 用户；V1-Core 再补登录/注册、地址、偏好、豆仔受控加购和模拟结算。API 层不得直接操作数据库，必须通过 service 和 repository 分层完成。

## 7. 模块验收标准

### 7.1 FastAPI 后端完成标准

- 能启动服务。
- `/api/health` 返回正常。
- `/api/recommend` 可接收文本 query。
- 能返回结构化 JSON。
- 异常时返回明确错误信息。
- 有基础 integration test。

### 7.2 Text Retriever 完成标准

- 输入 query 和 filters。
- 能返回 Top-K 商品。
- 每个结果包含 product_id、score、evidence_ids。
- 支持无向量数据库时使用 demo fallback。
- 有 smoke test。

### 7.3 Product Repository 完成标准

- 能读取 `products.json`。
- 能按 product_id 查询商品。
- 能按 category / brand / price 做基础过滤。
- 返回结构符合 Product Schema。

### 7.4 Decision Scoring 完成标准

- 输入 candidate_products、constraints、evidence_list。
- 输出 final_score、display_score、score_breakdown。
- 所有子分数范围为 0 到 1。
- risk_penalty 方向正确。
- final_score 可复算。
- 有 unit test。

### 7.5 Visual Agent 完成标准

- 输入 image_url 和 user_query。
- 输出 product_name、capacity、power、ports、price、confidence。
- 失败时进入 fallback。
- 结果写入 trace_steps。
- Demo Pack 可复现。
- 至少通过 5 张测试截图。

### 7.6 Android EvidencePanel 完成标准

- 能展示 evidence_id。
- 能展示证据类型。
- 能展示证据来源。
- 能展示置信度。
- 能与推荐商品关联。

### 7.7 Android AgentTracePanel 完成标准

- 能展示 Router、Visual、Retrieval、Decision、Response 每一步。
- 每一步包含 action、input_summary、output_summary、latency_ms、status。
- Demo Mode 下也能展示完整 Trace。

### 7.8 Demo Pack 完成标准

- 包含固定主 Demo 输入图片。
- 包含 visual_result。
- 包含 retrieval_plan。
- 包含 evidence_list。
- 包含 decision_results。
- 包含 trace_steps。
- 包含 final_response。
- Mock Mode 可一键复现完整演示。

### 7.9 Harness Validation 完成标准

- 能校验 schema。
- 能校验证据 ID 是否存在。
- 能校验评分是否可复算。
- 能校验政策类问题是否包含政策证据。
- 能校验风险问题是否包含风险提醒。
- 输出 harness_report。

## 8. 推荐完整目录树

以下目录树是最终目标结构，不是一次性生成清单。

```text
OmniCart Agent/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── __init__.py
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── products.py
│   │   │   ├── cart.py
│   │   │   ├── addresses.py
│   │   │   ├── agent_actions.py
│   │   │   ├── chat.py
│   │   │   ├── recommend.py
│   │   │   ├── upload.py
│   │   │   ├── demo.py
│   │   │   ├── evaluation.py
│   │   │   ├── trace.py
│   │   │   └── health.py
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── errors.py
│   │   │   ├── dependencies.py
│   │   │   └── feature_flags.py
│   │   │
│   │   ├── runtime/
│   │   │   ├── __init__.py
│   │   │   ├── agent_runtime.py
│   │   │   ├── workflow_engine.py
│   │   │   ├── state_manager.py
│   │   │   └── checkpoint_store.py
│   │   │
│   │   ├── agents/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── router_agent.py
│   │   │   ├── visual_agent.py
│   │   │   ├── retrieval_agent.py
│   │   │   ├── decision_agent.py
│   │   │   └── response_agent.py
│   │   │
│   │   ├── a2a/
│   │   │   ├── __init__.py
│   │   │   ├── agent_card.py
│   │   │   ├── message.py
│   │   │   ├── artifact.py
│   │   │   └── dispatcher.py
│   │   │
│   │   ├── context/
│   │   │   ├── __init__.py
│   │   │   ├── context_compiler.py
│   │   │   ├── prompt_builder.py
│   │   │   ├── token_budget_controller.py
│   │   │   └── context_schema.py
│   │   │
│   │   ├── memory/
│   │   │   ├── __init__.py
│   │   │   ├── preference_card.py
│   │   │   └── session_memory.py
│   │   │
│   │   ├── skills/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   ├── product_visual_parse.py
│   │   │   ├── product_retrieve.py
│   │   │   ├── review_risk_mining.py
│   │   │   ├── policy_check.py
│   │   │   ├── compatibility_check.py
│   │   │   └── decision_score.py
│   │   │
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── manager.py
│   │   │   ├── manifest.py
│   │   │   ├── product_text_search.py
│   │   │   ├── product_image_search.py
│   │   │   ├── review_search.py
│   │   │   ├── policy_lookup.py
│   │   │   ├── compatibility_rule_query.py
│   │   │   ├── structured_filter.py
│   │   │   ├── decision_score_calculator.py
│   │   │   ├── evidence_validator.py
│   │   │   └── demo_replay_loader.py
│   │   │
│   │   ├── mcp_compatible/
│   │   │   ├── __init__.py
│   │   │   ├── server_adapter.py
│   │   │   ├── tool_schema.py
│   │   │   └── resource_schema.py
│   │   │
│   │   ├── retrieval/
│   │   │   ├── __init__.py
│   │   │   ├── text_retriever.py
│   │   │   ├── visual_retriever.py
│   │   │   ├── structured_retriever.py
│   │   │   ├── review_retriever.py
│   │   │   ├── policy_retriever.py
│   │   │   ├── compatibility_retriever.py
│   │   │   ├── evidence_merger.py
│   │   │   ├── reranker.py
│   │   │   ├── retrieval_policy.py
│   │   │   └── adaptive_router.py
│   │   │
│   │   ├── verification/
│   │   │   ├── __init__.py
│   │   │   ├── evidence_sufficiency.py
│   │   │   ├── retrieval_reflection.py
│   │   │   └── response_guard.py
│   │   │
│   │   ├── graph/
│   │   │   ├── __init__.py
│   │   │   ├── evidence_graph.py
│   │   │   ├── graph_builder.py
│   │   │   └── path_explainer.py
│   │   │
│   │   ├── vision/
│   │   │   ├── __init__.py
│   │   │   ├── visual_grounding.py
│   │   │   ├── visual_evidence.py
│   │   │   └── multimodal_fallback.py
│   │   │
│   │   ├── decision/
│   │   │   ├── __init__.py
│   │   │   ├── scoring.py
│   │   │   ├── risk_analyzer.py
│   │   │   ├── compatibility_checker.py
│   │   │   ├── constraint_solver.py
│   │   │   ├── hard_filter.py
│   │   │   └── soft_ranker.py
│   │   │
│   │   ├── security/
│   │   │   ├── __init__.py
│   │   │   ├── tool_governance.py
│   │   │   ├── manifest_checker.py
│   │   │   └── prompt_injection_filter.py
│   │   │
│   │   ├── workflows/
│   │   │   ├── powerbank_purchase_advice.yaml
│   │   │   ├── text_shopping_advice.yaml
│   │   │   └── product_comparison.yaml
│   │   │
│   │   ├── indexing/
│   │   │   ├── __init__.py
│   │   │   ├── build_category_index.py
│   │   │   ├── build_product_index.py
│   │   │   ├── build_review_index.py
│   │   │   ├── build_policy_index.py
│   │   │   └── build_compatibility_index.py
│   │   │
│   │   ├── harness/
│   │   │   ├── __init__.py
│   │   │   ├── runner.py
│   │   │   ├── validators.py
│   │   │   ├── replay.py
│   │   │   ├── golden_loader.py
│   │   │   └── report.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── agent_state.py
│   │   │   ├── product.py
│   │   │   ├── user.py
│   │   │   ├── cart.py
│   │   │   ├── address.py
│   │   │   ├── preference.py
│   │   │   ├── order.py
│   │   │   ├── evidence.py
│   │   │   ├── decision_result.py
│   │   │   ├── trace_step.py
│   │   │   ├── skill.py
│   │   │   ├── tool.py
│   │   │   ├── a2a_message.py
│   │   │   ├── artifact.py
│   │   │   ├── checkpoint.py
│   │   │   ├── context.py
│   │   │   ├── preference.py
│   │   │   ├── retrieval.py
│   │   │   ├── visual.py
│   │   │   └── harness.py
│   │   │
│   │   ├── model_gateway/
│   │   │   ├── __init__.py
│   │   │   ├── gateway.py
│   │   │   ├── qwen_chat.py
│   │   │   ├── qwen_vision.py
│   │   │   ├── qwen_embedding.py
│   │   │   ├── qwen_reranker.py
│   │   │   └── mock_model.py
│   │   │
│   │   ├── repositories/
│   │   │   ├── __init__.py
│   │   │   ├── user_repo.py
│   │   │   ├── product_repo.py
│   │   │   ├── cart_repo.py
│   │   │   ├── address_repo.py
│   │   │   ├── review_repo.py
│   │   │   ├── policy_repo.py
│   │   │   ├── compatibility_repo.py
│   │   │   ├── vector_repo.py
│   │   │   ├── graph_repo.py
│   │   │   ├── session_repo.py
│   │   │   └── demo_pack_repo.py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── user_service.py
│   │   │   ├── product_service.py
│   │   │   ├── cart_service.py
│   │   │   ├── address_service.py
│   │   │   ├── preference_service.py
│   │   │   └── agent_action_service.py
│   │   │
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── text.py
│   │       ├── json.py
│   │       ├── scoring.py
│   │       ├── image.py
│   │       ├── time.py
│   │       └── ids.py
│   │
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
│
├── android-client/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── app/
│       ├── build.gradle.kts
│       └── src/main/
│           ├── AndroidManifest.xml
│           └── java/com/omnicart/agent/
│               ├── MainActivity.kt
│               ├── MainScaffold.kt
│               ├── core/
│               │   ├── config/AppConfig.kt
│               │   ├── network/ApiClient.kt
│               │   ├── network/OmniCartApi.kt
│               │   ├── network/NetworkResult.kt
│               │   ├── model/RecommendRequest.kt
│               │   ├── model/RecommendResponse.kt
│               │   ├── model/Product.kt
│               │   ├── model/User.kt
│               │   ├── model/UserPreference.kt
│               │   ├── model/CartItem.kt
│               │   ├── model/Address.kt
│               │   ├── model/MockOrder.kt
│               │   ├── model/Evidence.kt
│               │   ├── model/DecisionResult.kt
│               │   ├── model/TraceStep.kt
│               │   ├── model/SkillExecution.kt
│               │   ├── model/HarnessReport.kt
│               │   ├── model/FallbackStatus.kt
│               │   ├── theme/Color.kt
│               │   ├── theme/Theme.kt
│               │   └── theme/Type.kt
│               ├── feature/
│               │   ├── product/ProductHomeScreen.kt
│               │   ├── product/ProductList.kt
│               │   ├── product/ProductCard.kt
│               │   ├── product/ProductDetailScreen.kt
│               │   ├── product/CategoryChip.kt
│               │   ├── product/SearchBar.kt
│               │   ├── douzai/DouzaiChatScreen.kt
│               │   ├── douzai/DouzaiViewModel.kt
│               │   ├── douzai/DouzaiUiState.kt
│               │   ├── douzai/ChatInputBar.kt
│               │   ├── douzai/MessageBubble.kt
│               │   ├── upload/ImagePickerButton.kt
│               │   ├── upload/ImagePreview.kt
│               │   ├── product/ScoreBreakdown.kt
│               │   ├── product/RiskTag.kt
│               │   ├── cart/CartScreen.kt
│               │   ├── cart/CartItemRow.kt
│               │   ├── cart/CartSummaryBar.kt
│               │   ├── cart/MockCheckoutSheet.kt
│               │   ├── profile/ProfileScreen.kt
│               │   ├── profile/LoginScreen.kt
│               │   ├── profile/AddressListScreen.kt
│               │   ├── profile/PreferenceScreen.kt
│               │   ├── evidence/EvidencePanel.kt
│               │   ├── evidence/EvidenceItem.kt
│               │   ├── evidence/VisualEvidenceViewer.kt
│               │   ├── trace/AgentTracePanel.kt
│               │   ├── trace/TraceStepItem.kt
│               │   ├── skill/SkillExecutionPanel.kt
│               │   ├── skill/SkillExecutionItem.kt
│               │   ├── harness/HarnessValidationPanel.kt
│               │   ├── harness/HarnessCheckItem.kt
│               │   ├── context/ContextPanel.kt
│               │   ├── context/RetrievalPlanPanel.kt
│               │   ├── demo/DemoModeSwitch.kt
│               │   └── demo/DemoScenarioSelector.kt
│               ├── navigation/AppNavGraph.kt
│               ├── navigation/BottomNavBar.kt
│               └── util/UiText.kt
│
├── data/
│   ├── products.json
│   ├── reviews.json
│   ├── policies.json
│   ├── compatibility_rules.json
│   ├── category_guides.json
│   ├── golden_queries.json
│   └── demo/
│       └── powerbank_flight/
│           ├── input.png
│           ├── visual_result.json
│           ├── retrieval_plan.json
│           ├── evidence_list.json
│           ├── decision_results.json
│           ├── harness_report.json
│           └── final_response.json
│
├── demo/
├── scripts/
├── eval/
├── docs/
├── infra/
├── pyproject.toml
├── requirements.txt
├── README.md
└── .env.example
```

## 9. 顶层目录解析

| 路径 | 阶段 | 职责 |
|---|---|---|
| `backend/` | V0 起 | 后端核心，包括 FastAPI、Agent Runtime、RAG、Skill、Tool、Harness，以及用户、商品、购物车、地址、偏好等基础电商服务。 |
| `android-client/` | V0-Android 起 | Android 原生四 Tab 客户端，V1 参赛主交付端，展示商品展示、豆仔智能、购物车、个人中心、证据、Trace、Skill、Harness、Context。 |
| `frontend/` | deprecated | 历史 Web 前端目录，不再作为主线创建或维护。 |
| `data/` | V0 起 | 本地数据集，包含商品、评论、FAQ、兼容性规则、图片、golden queries。 |
| `demo/` | V1-Core | 主 Demo 场景、Demo Pack、Mock Mode 所需预置结果。 |
| `scripts/` | V0 起 | 索引构建、数据导入、评测、Demo Pack 导出、smoke test。 |
| `eval/` | V1-Plus | Baseline、指标、评测报告。 |
| `docs/` | V0 起 | 蓝图、目录说明、开发规则、进度、知识、决策、API、测试说明。 |
| `infra/` | V0 起 | Docker Compose、容器镜像、Qdrant 本地配置。 |

## 10. Backend 目录详细解析

### 10.1 `backend/app/main.py`

阶段：V0-Core

FastAPI 应用入口。

职责：

- 创建 FastAPI app。
- 注册 API router。
- 注册启动和关闭事件。
- 初始化核心依赖，例如配置、日志、Model Gateway。

建议保持极简，不写业务逻辑。

### 10.2 `backend/app/api/`

阶段：V0-Core 起

HTTP API 层。只做协议适配，不直接写 Agent 或 RAG 业务逻辑。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `health.py` | V0-Core | 健康检查接口。 |
| `auth.py` | V0-Android / V1-Core | 注册、登录、登出、Demo 用户。 |
| `users.py` | V0-Android / V1-Core | 当前用户信息和用户偏好接口。 |
| `products.py` | V0-Android | 商品列表、详情、搜索、分类筛选。 |
| `cart.py` | V0-Android / V1-Core | 购物车查询、添加、数量修改、删除、选择、模拟结算。 |
| `addresses.py` | V1-Core | 收货地址查询、新增、编辑、删除、默认地址。 |
| `agent_actions.py` | V1-Core | 豆仔智能受控购物车 action，例如 add_to_cart。 |
| `recommend.py` | V0-Core | 核心推荐接口，触发文本导购或完整 Workflow。 |
| `upload.py` | V1-Core | 图片 / 截图上传接口。 |
| `demo.py` | V1-Core | Demo Pack / Mock Mode 接口。 |
| `trace.py` | V1-Core | 查询 Agent Trace。 |
| `evaluation.py` | V1-Plus | 触发 golden query 评测和 Harness。 |
| `chat.py` | V1-Advanced | 多轮对话入口，封装 session_id、Preference Memory Card、Checkpoint。 |

### 10.3 `backend/app/core/`

阶段：V0-Core 起

全局基础设施。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `config.py` | V0-Core | 环境变量、模型配置、Qdrant/PostgreSQL/Redis 连接配置、Demo Mode 开关。 |
| `logging.py` | V0-Core | 日志格式、trace_id 注入、控制台/文件日志。 |
| `errors.py` | V0-Core | 统一异常类型，例如 ModelError、ToolError、HarnessValidationError。 |
| `dependencies.py` | V0-Core | FastAPI dependency 注入。 |
| `feature_flags.py` | V1-Plus | 控制 enable_mock_mode、enable_visual_grounding 等特性开关。 |

### 10.4 `backend/app/runtime/`

阶段：V1-Plus

Agent Runtime 核心。V1-Core 可以先用简单 Workflow 函数，V1-Plus 再抽象成 runtime。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `agent_runtime.py` | V1-Plus | Runtime 门面。接收请求，创建 AgentState，调用 WorkflowEngine。 |
| `workflow_engine.py` | V1-Core / Plus | 执行 route -> visual -> retrieval -> decision -> response。 |
| `state_manager.py` | V1-Plus | 读写 AgentState，合并 Preference Memory Card，维护 trace_steps。 |
| `checkpoint_store.py` | V1-Advanced | 保存 after_visual_parse、after_retrieval、after_decision、after_response。 |

### 10.5 `backend/app/agents/`

阶段：V1-Core

5 个核心 Agent。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `base.py` | V1-Core | 定义 Agent 输入输出、trace、artifact 标准接口。 |
| `router_agent.py` | V1-Core | 识别意图、抽取约束、生成 retrieval_plan。 |
| `visual_agent.py` | V1-Core | 解析截图/商品图，生成 visual_result。 |
| `retrieval_agent.py` | V1-Core | 执行 Multimodal Evidence RAG，获取证据。 |
| `decision_agent.py` | V1-Core | 执行 Decision Scoring。 |
| `response_agent.py` | V1-Core | 生成最终回答。 |

注意：

- 不增加第 6 个主 Agent。
- Response Guard、Evidence Sufficiency、Verifier 作为 `verification/` 或 `harness/` 模块，不升级为主 Agent。

### 10.6 `backend/app/a2a/`

阶段：V1-Plus

A2A-lite 结构化通信层。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `agent_card.py` | V1-Plus | 定义 AgentCard。 |
| `message.py` | V1-Plus | 定义 AgentMessage。 |
| `artifact.py` | V1-Plus | 定义 Artifact。 |
| `dispatcher.py` | V1-Plus | 同进程内分发 AgentMessage。 |

V1 是同后端内的轻量结构化通信，不实现完整分布式 A2A 协议。

### 10.7 `backend/app/context/`

阶段：V1-Plus

Context Engineering 模块。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `context_compiler.py` | V1-Plus | 汇总 query、constraints、visual_result、evidence_list、decision_results、risk_factors、harness 状态。 |
| `prompt_builder.py` | V1-Plus | 将 CompiledContext 转成 Response Agent prompt。 |
| `token_budget_controller.py` | V1-Advanced | 按优先级裁剪证据。 |
| `context_schema.py` | V1-Plus | 定义 CompiledContext。 |

### 10.8 `backend/app/memory/`

阶段：V1-Advanced

会话级购物偏好记忆。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `preference_card.py` | V1-Advanced | 定义 PreferenceMemoryCard。 |
| `session_memory.py` | V1-Advanced | 在当前 session 内读写 Preference Memory Card。 |

V1 只做 session-level memory，不做跨会话长期记忆。

### 10.9 `backend/app/skills/`

阶段：V1-Plus

Skill Registry 与任务能力封装层。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `base.py` | V1-Plus | 定义 Skill 输入、输出、required_tools、validation_rules。 |
| `registry.py` | V1-Plus | 注册和查找 Skill。 |
| `product_visual_parse.py` | V1-Plus | 解析商品截图，抽取字段和视觉证据。 |
| `product_retrieve.py` | V1-Plus | 编排文本/视觉/结构化召回。 |
| `review_risk_mining.py` | V1-Core / Plus | 从评论中抽取风险证据。 |
| `policy_check.py` | V1-Core / Plus | 查询政策、航空规则、售后规则。 |
| `compatibility_check.py` | V1-Core / Plus | 判断设备、接口、功率、场景兼容性。 |
| `decision_score.py` | V1-Plus | 调用约束求解和评分公式。 |

Skill 是组合能力，Tool 是原子能力。

### 10.10 `backend/app/tools/`

阶段：V1-Plus

MCP-compatible Tool Layer。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `manager.py` | V1-Plus | 统一加载 manifest、执行工具、记录 ToolCallRecord。 |
| `manifest.py` | V1-Plus | 定义工具描述、schema、权限、timeout、cacheable、manifest_hash。 |
| `product_text_search.py` | V0-Core / V1-Plus | 检索商品文本索引。 |
| `product_image_search.py` | V1-Core / Plus | 检索图片或视觉描述索引。 |
| `review_search.py` | V1-Core / Plus | 检索评论证据。 |
| `policy_lookup.py` | V1-Core / Plus | 检索政策、FAQ、航空规则。 |
| `compatibility_rule_query.py` | V1-Core / Plus | 查询兼容性规则。 |
| `structured_filter.py` | V1-Core / Plus | 按价格、品类、库存、接口、功率过滤。 |
| `decision_score_calculator.py` | V1-Plus | 计算 final_score 和 display_score。 |
| `evidence_validator.py` | V1-Plus | 校验证据 ID、证据类型和引用关系。 |
| `demo_replay_loader.py` | V1-Core | 从 Demo Pack 加载预置中间结果。 |

所有 Tool 输出必须是结构化 JSON。

### 10.11 `backend/app/retrieval/`

阶段：V0/V1

Adaptive Multimodal Evidence Retrieval。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `text_retriever.py` | V0-Core | 检索商品标题、参数、评论、FAQ、政策文本。 |
| `visual_retriever.py` | V1-Core | 检索商品图片、截图视觉证据或视觉文本 fallback。 |
| `structured_retriever.py` | V1-Core | 读取价格、库存、接口、功率、规则。 |
| `review_retriever.py` | V1-Core | 按 aspect 检索评论风险。 |
| `policy_retriever.py` | V1-Core | 检索平台政策、航空携带、售后规则。 |
| `compatibility_retriever.py` | V1-Core | 检索 iPhone / MacBook / USB-C / PD 等兼容性规则。 |
| `evidence_merger.py` | V1-Core | 合并文本、视觉、结构化证据。 |
| `reranker.py` | V1-Core | 调用 Qwen reranking 或 fallback 规则分。 |
| `retrieval_policy.py` | V1-Advanced | 定义不同任务的检索策略。 |
| `adaptive_router.py` | V1-Advanced | 根据 intent / constraints / visual_result 生成 Retrieval Plan。 |

### 10.12 `backend/app/decision/`

阶段：V0/V1

硬约束和软评分。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `scoring.py` | V0-Core | 实现 Decision Scoring 公式。 |
| `risk_analyzer.py` | V1-Core | 从评论、政策、结构化规则聚合 risk_penalty。 |
| `compatibility_checker.py` | V1-Core | 判断设备、接口、功率兼容性。 |
| `constraint_solver.py` | V1-Plus | 统一执行硬约束判断。 |
| `hard_filter.py` | V1-Plus | 对硬约束失败商品做过滤或降权。 |
| `soft_ranker.py` | V1-Plus | 对硬约束通过商品做加权排序。 |

### 10.13 其他后端目录归属

| 目录 | 阶段 | 说明 |
|---|---|---|
| `mcp_compatible/` | V2 planned | V1 只保留文档规划，不提前创建空代码，除非 ToolManager 已跑通。 |
| `verification/` | V1-Plus | Evidence Sufficiency、Response Guard。 |
| `graph/` | V1-Advanced | Evidence Graph Lite。 |
| `vision/` | V1-Core / Advanced | visual parsing 属 Core，visual grounding 属 Advanced。 |
| `security/` | V1-Plus | Tool Governance。 |
| `workflows/` | V1-Advanced | workflow.yaml，可先只放主 Demo YAML。 |
| `indexing/` | V0/V1 | 各类索引构建脚本。 |
| `harness/` | V1-Plus | Decision Harness。 |
| `schemas/` | V0 起 | 所有跨模块数据契约。 |
| `model_gateway/` | V0 起 | Qwen-only Model Gateway。 |
| `repositories/` | V0 起 | 商品、评论、政策、向量库、Demo Pack、用户、购物车、地址访问。 |
| `services/` | V0-Android / V1-Core | 用户、商品、购物车、地址、偏好和 Agent Action 业务服务，API 层不得直接操作数据库。 |
| `utils/` | V0 起 | 通用工具函数。 |

新增基础电商服务文件职责：

| 文件 | 阶段 | 职责 |
|---|---|---|
| `user_service.py` | V0-Android / V1-Core | Demo 用户、注册登录、当前用户、token 处理。 |
| `product_service.py` | V0-Android | 商品列表、详情、搜索、分类筛选。 |
| `cart_service.py` | V0-Android / V1-Core | 购物车增删改查、多选、全选、价格合计、模拟结算。 |
| `address_service.py` | V1-Core | 地址新增、编辑、删除、默认地址。 |
| `preference_service.py` | V1-Core | 用户偏好读取和更新，与 Preference Memory Card 对齐。 |
| `agent_action_service.py` | V1-Core | 将豆仔智能结构化 action 转为受控 Cart Service 调用，并记录 Trace。 |

## 11. Android Client 目录详细解析

### 11.1 `android-client/app/src/main/java/com/omnicart/agent/core/`

Android 客户端核心基础层。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `config/AppConfig.kt` | V0-Android | 后端 baseUrl、Demo Mode 默认值、客户端配置。 |
| `network/ApiClient.kt` | V0-Android | Retrofit + OkHttp 初始化。 |
| `network/OmniCartApi.kt` | V0-Android | 定义 `/api/recommend`、商品、购物车、用户等 API。 |
| `network/NetworkResult.kt` | V0-Android | 统一 success/error/loading 状态。 |
| `model/RecommendRequest.kt` | V0-Android | 推荐请求数据类。 |
| `model/RecommendResponse.kt` | V0-Android | 推荐响应数据类。 |
| `model/Product.kt` | V0-Android | 商品卡片展示所需字段。 |
| `model/User.kt` | V0-Android | Demo 用户和登录用户信息。 |
| `model/CartItem.kt` | V0-Android | 购物车商品行。 |
| `model/Address.kt` | V1-Android | 收货地址。 |
| `model/UserPreference.kt` | V1-Android | 设备、预算、品牌、避雷项等偏好。 |
| `model/MockOrder.kt` | V1-Android | 模拟结算生成的订单。 |
| `model/Evidence.kt` | V1-Android | 证据展示字段。 |
| `model/DecisionResult.kt` | V0-Android | 推荐评分字段。 |
| `model/TraceStep.kt` | V1-Android | Agent Trace 字段。 |
| `model/SkillExecution.kt` | V1-Android | Skill 执行结果字段。 |
| `model/HarnessReport.kt` | V1-Android | Harness 校验结果字段。 |
| `model/FallbackStatus.kt` | V1-Android | fallback 状态字段。 |
| `theme/Color.kt` / `Theme.kt` / `Type.kt` | V0-Android | Compose + Material 3 主题。 |

### 11.2 `android-client/app/src/main/java/com/omnicart/agent/feature/`

比赛展示核心。Android UI 必须按 V0-Android -> V1-Android 逐步创建，不得为了匹配目标结构一次性生成空文件。

| 文件 | 阶段 | 职责 |
|---|---|---|
| `product/ProductHomeScreen.kt` | V0-Android | 商品展示页，商品列表、搜索、分类筛选。 |
| `product/ProductList.kt` | V0-Android | 商品瀑布流 / 列表。 |
| `product/ProductCard.kt` | V0-Android | 商品图、标题、品牌、价格、评分、推荐理由、风险。 |
| `product/ProductDetailScreen.kt` | V0-Android / V1-Android | 商品详情、参数、评论摘要、加入购物车、问豆仔。 |
| `product/CategoryChip.kt` | V0-Android | 商品分类标签。 |
| `product/SearchBar.kt` | V0-Android | 商品搜索输入。 |
| `douzai/DouzaiChatScreen.kt` | V0-Android / V1-Android | 豆仔智能页，文本导购、图片导购、推荐结果和 action 消息。 |
| `douzai/DouzaiViewModel.kt` | V0-Android / V1-Android | 豆仔智能 MVVM 状态管理。 |
| `douzai/DouzaiUiState.kt` | V0-Android / V1-Android | messages、products、demoMode、agentActions 等 UI 状态。 |
| `douzai/ChatInputBar.kt` | V0-Android | 文本输入、图片选择入口、发送按钮。 |
| `douzai/MessageBubble.kt` | V1-Android | 用户、豆仔回答、购物车 action 结果消息。 |
| `upload/ImagePickerButton.kt` | V1-Android | Android Photo Picker 入口。 |
| `upload/ImagePreview.kt` | V1-Android | 已选图片预览。 |
| `product/ScoreBreakdown.kt` | V1-Android | 展示评分细分。 |
| `product/RiskTag.kt` | V0-Android | 风险标签。 |
| `cart/CartScreen.kt` | V0-Android / V1-Android | 购物车页，查看商品、数量、选择和合计。 |
| `cart/CartItemRow.kt` | V0-Android | 单个购物车商品。 |
| `cart/CartSummaryBar.kt` | V1-Android | 全选、合计、模拟结算入口。 |
| `cart/MockCheckoutSheet.kt` | V1-Android | 模拟结算 / 模拟付款，不接入真实支付。 |
| `profile/ProfileScreen.kt` | V0-Android / V1-Android | 个人中心，Demo 用户、登录状态、偏好入口。 |
| `profile/LoginScreen.kt` | V1-Android | 登录 / 注册 / Demo 用户登录。 |
| `profile/AddressListScreen.kt` | V1-Android | 地址列表、新增、编辑、删除、默认地址。 |
| `profile/PreferenceScreen.kt` | V1-Android | 设备、预算、品牌、避雷项等偏好管理。 |
| `evidence/EvidencePanel.kt` | V1-Android | 展示文本、评论、政策、兼容性证据。 |
| `evidence/EvidenceItem.kt` | V1-Android | 单条证据。 |
| `evidence/VisualEvidenceViewer.kt` | V1-Android | 字段级视觉证据。 |
| `trace/AgentTracePanel.kt` | V1-Android | Agent 步骤展示。 |
| `trace/TraceStepItem.kt` | V1-Android | 单个 Trace Step。 |
| `skill/SkillExecutionPanel.kt` | V1-Android | Skill 执行结果列表。 |
| `skill/SkillExecutionItem.kt` | V1-Android | 单个 Skill 执行结果。 |
| `harness/HarnessValidationPanel.kt` | V1-Android | Harness 校验结果。 |
| `harness/HarnessCheckItem.kt` | V1-Android | 单个 Harness 检查项。 |
| `context/ContextPanel.kt` | V1-Advanced | 系统理解的设备、场景、偏好、避雷项。 |
| `context/RetrievalPlanPanel.kt` | V1-Advanced | 检索计划和 adaptive_top_k。 |
| `demo/DemoModeSwitch.kt` | V0-Android | Demo Pack / Mock Mode 开关。 |
| `demo/DemoScenarioSelector.kt` | V1-Android | 主 Demo 场景选择。 |

### 11.3 `android-client/app/src/main/java/com/omnicart/agent/navigation/`

| 文件 | 阶段 | 职责 |
|---|---|---|
| `AppNavGraph.kt` | V0-Android | Jetpack Compose Navigation 路由，连接四个底部 Tab 和详情页。 |
| `BottomNavBar.kt` | V0-Android | Material 3 NavigationBar，四个入口：商品展示、豆仔智能、购物车、个人中心。 |
| `../MainScaffold.kt` | V0-Android | 全局 Scaffold，承载底部导航、页面切换和基础状态。 |

### 11.4 `frontend/`

`frontend/` 已废弃，不再维护 Next.js / React / TailwindCSS 主线。若仓库历史中存在该目录，只能保留为 deprecated 或移至 `archive/`，不得继续作为最终交付端开发。

## 12. Data Plan 入口

项目数据质量决定 Demo 可信度。目录结构中必须预留数据规划文件。

推荐 data 目录：

```text
data/
  products.json
  reviews.json
  policies.json
  compatibility_rules.json
  golden_queries.json
  demo/
    powerbank_flight/
      input.png
      visual_result.json
      retrieval_plan.json
      evidence_list.json
      decision_results.json
      harness_report.json
      final_response.json
```

最低数据要求：

### V0

- 30-50 个商品。
- 30 条 golden queries。
- 基础商品参数。

### V1

- 100-300 个商品。
- 500-1000 条评论。
- 30-50 条政策/FAQ。
- 30-100 条兼容性规则。
- 100 条 golden queries。
- 1 个高质量主 Demo Pack。

### V2

- 500+ SKU。
- 3000+ 评论。
- 多类目商品。
- 更完整政策和兼容性知识。

## 13. Tests 目录结构

推荐测试目录：

```text
tests/
  unit/
    test_scoring.py
    test_constraint_solver.py
    test_text_retriever.py
    test_context_compiler.py
    test_tool_manifest.py
    test_evidence_sufficiency.py

  integration/
    test_recommend_api.py
    test_demo_pack.py
    test_agent_workflow.py
    test_visual_agent.py
    test_harness_validation.py

  fixtures/
    sample_products.json
    sample_evidence.json
    sample_agent_state.json
    sample_decision_results.json
    sample_trace_steps.json
```

测试要求：

- V0 至少通过 `test_scoring`、`test_text_retriever`、`test_recommend_api`。
- V1-Core 至少通过 `test_visual_agent`、`test_agent_workflow`、`test_demo_pack`。
- V1-Plus 至少通过 `test_harness_validation`、`test_tool_manifest`。
- 每个关键模块必须有最低限度测试或 smoke test。

## 14. Docs 文档维护体系

推荐 docs 目录：

```text
docs/
  OMNICART_AGENT_COMPLETE_BLUEPRINT.md
  DEVELOPMENT_DIRECTORY_STRUCTURE.md
  DEVELOPMENT_RULES.md
  DEVELOPMENT_PROGRESS.md
  KNOWLEDGE_LOG.md
  DECISION_LOG.md
  CHANGELOG.md
  IMPLEMENTATION_PRIORITY.md
  ACCEPTANCE_CRITERIA.md
  DEMO_SCRIPT.md
  DATA_PLAN.md
  API_CONTRACT.md
  TESTING_GUIDE.md
```

文件职责：

| 文件 | 职责 |
|---|---|
| `OMNICART_AGENT_COMPLETE_BLUEPRINT.md` | 最终蓝图，默认只读。 |
| `DEVELOPMENT_DIRECTORY_STRUCTURE.md` | 工程目录施工图。 |
| `DEVELOPMENT_RULES.md` | AI 编程 Agent 行为规则。 |
| `DEVELOPMENT_PROGRESS.md` | 开发进度记录。 |
| `KNOWLEDGE_LOG.md` | 关键技术节点知识总结。 |
| `DECISION_LOG.md` | 重要技术决策和取舍。 |
| `CHANGELOG.md` | 变更记录。 |
| `IMPLEMENTATION_PRIORITY.md` | 实现优先级。 |
| `ACCEPTANCE_CRITERIA.md` | 模块验收标准。 |
| `DEMO_SCRIPT.md` | 比赛演示脚本。 |
| `DATA_PLAN.md` | 商品、评论、政策、兼容性数据计划。 |
| `API_CONTRACT.md` | 接口契约。 |
| `TESTING_GUIDE.md` | 测试说明。 |

维护规则：

- 每完成一个 milestone，必须更新 `DEVELOPMENT_PROGRESS.md`、`KNOWLEDGE_LOG.md` 和 `CHANGELOG.md`。
- 每做一个重要技术取舍，必须更新 `DECISION_LOG.md`。
- 每完成一个可演示功能，必须更新 `DEMO_SCRIPT.md` 或对应演示说明。

## 15. Scripts 目录详细解析

| 文件 | 阶段 | 职责 |
|---|---|---|
| `build_text_index.py` | V0-Core | 构建商品文本向量索引。 |
| `build_image_index.py` | V1-Core | 构建图片或视觉描述索引。 |
| `seed_postgres.py` | V0/V1 | 将 JSON 数据导入 PostgreSQL。 |
| `seed_qdrant.py` | V0/V1 | 将 embedding 写入 Qdrant。 |
| `run_eval.py` | V1-Plus | 运行 baseline 和 OmniCart 评测。 |
| `run_demo_mode.py` | V1-Core | 启动 Demo Pack 模式。 |
| `export_demo_pack.py` | V1-Core | 从真实运行结果导出 Demo Pack。 |
| `smoke_recommend.py` | V0-Core | 快速验证推荐链路是否可运行。 |

## 16. Eval 目录详细解析

### 16.1 `eval/baselines/`

| 文件 | 职责 |
|---|---|
| `qwen_direct_answer.py` | 纯 Qwen 直接回答 baseline。 |
| `text_only_rag.py` | 普通文本 RAG baseline。 |
| `omnicart_agent.py` | OmniCart 完整链路评测入口。 |

### 16.2 `eval/metrics/`

| 文件 | 指标 |
|---|---|
| `constraint.py` | Constraint Satisfaction Rate、Constraint Violation Rate。 |
| `evidence.py` | Evidence Citation Rate、Evidence Sufficiency Pass Rate。 |
| `hallucination.py` | Hallucination Rate。 |
| `latency.py` | Average Latency、P95 Latency。 |
| `visual_grounding.py` | Visual Grounding Accuracy。 |
| `harness.py` | Harness Pass Rate、Schema Valid Rate、Tool Governance Pass Rate。 |

## 17. 推荐开发执行顺序

每一步完成后必须可以运行，不允许连续多个步骤都处于半成品状态。

### Step 1：项目初始化

- 初始化 backend FastAPI。
- 初始化 `android-client/` Android 原生项目。
- 配置基础 lint / format。
- 创建 `data/products.json`。
- 创建 `/api/health`。

### Step 2：V0 文本导购闭环

- Product Schema。
- Product Repository。
- 商品列表 / 商品详情 API。
- 购物车基础 API。
- Demo 用户 API。
- Text Retriever。
- Decision Scoring。
- `/api/recommend`。
- Android 四 Tab + Bottom Navigation。
- Android 商品展示页。
- Android 豆仔智能文本输入。
- Android 购物车页。
- Android 个人中心 Demo 用户。
- Android ProductCard。
- `smoke_recommend.py`。

### Step 3：V1 图片导购主链路

- 登录 / 注册。
- 地址管理。
- 用户偏好管理。
- 图片上传。
- Qwen-VL 图片解析。
- Visual Agent。
- visual_result schema。
- Demo Pack 主图片。
- 豆仔智能 Agent Action 加入购物车。
- 购物车模拟结算。
- Android 图片选择、上传和 ImagePreview。

### Step 4：Multimodal Evidence RAG

- Review Retriever。
- Policy Retriever。
- Compatibility Retriever。
- Evidence Merger。
- Android EvidencePanel。

### Step 5：Agent Workflow

- Router Agent。
- Retrieval Agent。
- Decision Agent。
- Response Agent。
- AgentState。
- TraceStep。
- Android AgentTracePanel。

### Step 6：参赛增强能力

- Skill Registry。
- MCP-compatible ToolManager。
- A2A-lite。
- Context Compiler。
- Constraint Solver。
- Harness Validation。
- Android SkillExecutionPanel。
- Mock Mode。

### Step 7：评测与答辩材料

- Baseline 脚本。
- golden_queries。
- `DEMO_SCRIPT.md`。
- `KNOWLEDGE_LOG.md`。
- 答辩素材总结。

## 18. V0 / V1 / V2 文件落地顺序

### 18.1 V0-Core 最小可运行文本导购

优先落地：

```text
backend/app/main.py
backend/app/api/recommend.py
backend/app/api/health.py
backend/app/api/products.py
backend/app/api/cart.py
backend/app/api/users.py
backend/app/core/config.py
backend/app/schemas/product.py
backend/app/schemas/user.py
backend/app/schemas/cart.py
backend/app/schemas/evidence.py
backend/app/schemas/decision_result.py
backend/app/model_gateway/gateway.py
backend/app/model_gateway/qwen_embedding.py
backend/app/model_gateway/qwen_chat.py
backend/app/retrieval/text_retriever.py
backend/app/repositories/product_repo.py
backend/app/repositories/cart_repo.py
backend/app/repositories/user_repo.py
backend/app/repositories/vector_repo.py
backend/app/services/product_service.py
backend/app/services/cart_service.py
backend/app/services/user_service.py
backend/app/decision/scoring.py
data/products.json
data/golden_queries.json
scripts/build_text_index.py
scripts/smoke_recommend.py
tests/unit/test_scoring.py
tests/unit/test_text_retriever.py
tests/integration/test_recommend_api.py
```

V0 验收：

- 文本输入能返回推荐商品。
- 推荐结果带 evidence_ids。
- 商品展示页 API 能返回商品列表和详情。
- 购物车 API 能添加、查询和删除商品。
- Demo 用户可用。

### 18.2 V0-Android 最小可运行客户端

V0-Core API 跑通后落地：

```text
android-client/settings.gradle.kts
android-client/build.gradle.kts
android-client/app/build.gradle.kts
android-client/app/src/main/AndroidManifest.xml
android-client/app/src/main/java/com/omnicart/agent/MainActivity.kt
android-client/app/src/main/java/com/omnicart/agent/MainScaffold.kt
android-client/app/src/main/java/com/omnicart/agent/core/config/AppConfig.kt
android-client/app/src/main/java/com/omnicart/agent/core/network/ApiClient.kt
android-client/app/src/main/java/com/omnicart/agent/core/network/OmniCartApi.kt
android-client/app/src/main/java/com/omnicart/agent/core/network/NetworkResult.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/RecommendRequest.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/RecommendResponse.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/Product.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/User.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/CartItem.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/DecisionResult.kt
android-client/app/src/main/java/com/omnicart/agent/core/theme/Color.kt
android-client/app/src/main/java/com/omnicart/agent/core/theme/Theme.kt
android-client/app/src/main/java/com/omnicart/agent/core/theme/Type.kt
android-client/app/src/main/java/com/omnicart/agent/feature/product/ProductHomeScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/product/ProductList.kt
android-client/app/src/main/java/com/omnicart/agent/feature/product/ProductCard.kt
android-client/app/src/main/java/com/omnicart/agent/feature/product/ProductDetailScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/douzai/DouzaiChatScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/douzai/DouzaiViewModel.kt
android-client/app/src/main/java/com/omnicart/agent/feature/douzai/DouzaiUiState.kt
android-client/app/src/main/java/com/omnicart/agent/feature/douzai/ChatInputBar.kt
android-client/app/src/main/java/com/omnicart/agent/feature/cart/CartScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/cart/CartItemRow.kt
android-client/app/src/main/java/com/omnicart/agent/feature/profile/ProfileScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/demo/DemoModeSwitch.kt
android-client/app/src/main/java/com/omnicart/agent/navigation/AppNavGraph.kt
android-client/app/src/main/java/com/omnicart/agent/navigation/BottomNavBar.kt
```

V0-Android 验收：

- Android App 可在模拟器或真机启动。
- 底部四 Tab 可切换：商品展示、豆仔智能、购物车、个人中心。
- 商品展示页能展示商品列表和商品详情。
- 文本输入能调用 `/api/recommend`。
- 购物车页能展示、增加、删除商品。
- 个人中心能显示 Demo 用户。
- 商品卡片能显示商品图、商品名、价格、综合评分、一句话推荐理由和风险标签。
- Demo Mode 本地假数据可展示。

### 18.3 V1-Core 后端参赛主链路

继续落地：

```text
backend/app/api/upload.py
backend/app/api/auth.py
backend/app/api/addresses.py
backend/app/api/agent_actions.py
backend/app/api/demo.py
backend/app/api/trace.py
backend/app/schemas/address.py
backend/app/schemas/preference.py
backend/app/schemas/order.py
backend/app/services/address_service.py
backend/app/services/preference_service.py
backend/app/services/agent_action_service.py
backend/app/repositories/address_repo.py
backend/app/agents/
backend/app/retrieval/visual_retriever.py
backend/app/retrieval/review_retriever.py
backend/app/retrieval/policy_retriever.py
backend/app/retrieval/compatibility_retriever.py
backend/app/retrieval/evidence_merger.py
backend/app/retrieval/reranker.py
backend/app/vision/multimodal_fallback.py
backend/app/decision/risk_analyzer.py
backend/app/decision/compatibility_checker.py
demo/demo_pack/
tests/integration/test_visual_agent.py
tests/integration/test_agent_workflow.py
tests/integration/test_demo_pack.py
```

V1-Core 验收：

- 主 Demo 场景稳定跑通。
- 登录 / 注册、地址管理、用户偏好、豆仔受控加入购物车和模拟结算可用。
- Android EvidencePanel 和 AgentTracePanel 能展示。
- Demo Pack / Mock Mode 可用。

### 18.4 V1-Android 参赛客户端主链路

V0-Android 跑通后继续落地：

```text
android-client/app/src/main/java/com/omnicart/agent/core/model/Evidence.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/TraceStep.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/SkillExecution.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/HarnessReport.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/FallbackStatus.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/Address.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/UserPreference.kt
android-client/app/src/main/java/com/omnicart/agent/core/model/MockOrder.kt
android-client/app/src/main/java/com/omnicart/agent/feature/douzai/MessageBubble.kt
android-client/app/src/main/java/com/omnicart/agent/feature/upload/ImagePickerButton.kt
android-client/app/src/main/java/com/omnicart/agent/feature/upload/ImagePreview.kt
android-client/app/src/main/java/com/omnicart/agent/feature/product/ScoreBreakdown.kt
android-client/app/src/main/java/com/omnicart/agent/feature/product/RiskTag.kt
android-client/app/src/main/java/com/omnicart/agent/feature/cart/CartSummaryBar.kt
android-client/app/src/main/java/com/omnicart/agent/feature/cart/MockCheckoutSheet.kt
android-client/app/src/main/java/com/omnicart/agent/feature/profile/LoginScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/profile/AddressListScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/profile/PreferenceScreen.kt
android-client/app/src/main/java/com/omnicart/agent/feature/evidence/EvidencePanel.kt
android-client/app/src/main/java/com/omnicart/agent/feature/evidence/EvidenceItem.kt
android-client/app/src/main/java/com/omnicart/agent/feature/evidence/VisualEvidenceViewer.kt
android-client/app/src/main/java/com/omnicart/agent/feature/trace/AgentTracePanel.kt
android-client/app/src/main/java/com/omnicart/agent/feature/trace/TraceStepItem.kt
android-client/app/src/main/java/com/omnicart/agent/feature/skill/SkillExecutionPanel.kt
android-client/app/src/main/java/com/omnicart/agent/feature/skill/SkillExecutionItem.kt
android-client/app/src/main/java/com/omnicart/agent/feature/harness/HarnessValidationPanel.kt
android-client/app/src/main/java/com/omnicart/agent/feature/harness/HarnessCheckItem.kt
android-client/app/src/main/java/com/omnicart/agent/feature/demo/DemoScenarioSelector.kt
android-client/app/src/main/java/com/omnicart/agent/navigation/AppNavGraph.kt
android-client/app/src/main/java/com/omnicart/agent/util/UiText.kt
```

V1-Android 验收：

- 图片选择 / 上传可用。
- 商品详情或豆仔详情区域能展示推荐理由、Evidence、Score、Agent Trace、Skill Execution、Harness Validation。
- 豆仔智能能通过受控 action 将商品加入购物车。
- 购物车能展示“由豆仔推荐加入”，并支持模拟结算。
- 个人中心能管理地址和偏好。
- Mock Mode 一键演示可用。
- APK 可打包。

### 18.5 V1-Plus 强加分项

有 V1-Core 后再落地：

```text
backend/app/runtime/
backend/app/a2a/
backend/app/context/
backend/app/skills/
backend/app/tools/
backend/app/verification/
backend/app/harness/
backend/app/security/
eval/
```

### 18.6 V1-Advanced 前沿展示项

时间充足再落地：

```text
backend/app/memory/
backend/app/graph/
backend/app/vision/visual_grounding.py
backend/app/vision/visual_evidence.py
backend/app/workflows/
backend/app/indexing/
android-client/app/src/main/java/com/omnicart/agent/feature/context/ContextPanel.kt
android-client/app/src/main/java/com/omnicart/agent/feature/context/RetrievalPlanPanel.kt
```

### 18.7 V2 / V3 增强版

后续扩展：

```text
标准 MCP Server / Client
标准 A2A Protocol
Computer Use / Browser Use
iOS Swift + SwiftUI
Neo4j GraphRAG
Qwen-Omni voice interaction
User long-term memory
Langfuse / Phoenix observability
Online feedback learning
```

这些不阻塞 V1 比赛交付。

## 19. 主链路保护规则

任何新增功能都不得破坏以下主链路。

### 19.1 V0 主链路

```text
文本 query
  -> /api/recommend
  -> Text Retriever
  -> Decision Scoring
  -> Android 豆仔智能推荐
  -> Android 商品展示 / ProductCard
  -> Android 购物车可加入商品
```

### 19.2 V1 主链路

```text
图片 + 文本 query
  -> 商品详情上下文 / 用户偏好
  -> Visual Agent
  -> Multimodal Evidence RAG
  -> Decision Agent
  -> Response Agent
  -> 受控 Agent Action 可加入购物车
  -> Evidence Panel
  -> Agent Trace Panel
  -> CartScreen 展示“由豆仔推荐加入”
  -> Demo Pack / Mock Mode
```

如果新增功能导致主链路失败：

1. 立即停止开发新功能。
2. 优先修复主链路。
3. 无法修复时回滚最近改动。
4. 在 `CHANGELOG.md` 和 `DEVELOPMENT_PROGRESS.md` 中记录原因。

## 20. 命名规范

### 20.1 ID 前缀

| 类型 | 前缀 |
|---|---|
| Product | `P` |
| User | `U` |
| Cart Item | `CART` |
| Address | `ADDR` |
| Mock Order | `O` |
| Evidence | `E` |
| Review Evidence | `R` |
| Policy Evidence | `POL` |
| Visual Evidence | `V` |
| Trace Step | `T` |
| Artifact | `A` |
| Skill Execution | `SKE` |
| Tool Call | `TC` |
| Harness Run | `HR` |

### 20.2 文件命名

- Python 文件使用 snake_case。
- Kotlin 类、ViewModel、Compose Composable 使用 PascalCase。
- Kotlin 包名和目录使用小写路径，例如 `feature/chat`、`core/network`。
- JSON 数据文件使用 snake_case。
- Workflow YAML 使用场景名，例如 `powerbank_purchase_advice.yaml`。

### 20.3 Schema 命名

- `AgentState`
- `Product`
- `Evidence`
- `DecisionResult`
- `TraceStep`
- `SkillExecution`
- `ToolCallRecord`
- `AgentMessage`
- `Artifact`
- `Checkpoint`
- `CompiledContext`
- `PreferenceMemoryCard`

## 21. 当前仓库迁移建议

当前仓库已经存在：

```text
app/
pipelines/
models/
train/
eval/
demo/
docs/
data/mock/
scripts/
tests/
```

建议迁移策略：

1. 不立刻删除当前 `app/`。
2. 新建 `backend/app/`，按本文档逐步迁移核心代码。
3. 当前 `app/schemas/commerce.py` 可以拆到 `backend/app/schemas/`。
4. 当前 `app/services/` 的逻辑可以拆到 `agents/`、`retrieval/`、`decision/`、`context/`。
5. 当前 `data/mock/` 可以逐步升级为 `data/products.json`、`data/reviews.json`、`data/policies.json`。
6. 当前 `eval/` 保留，但补充 baselines 和 metrics。
7. 当前 `docs/` 保留，新增维护型文档。

这样能避免一次性大重构导致项目不可运行。

## 22. AI 编程 Agent 执行规则

适用于 Claude Code / Codex / 其他 AI 编程 Agent。

1. 不允许擅自修改 `OMNICART_AGENT_COMPLETE_BLUEPRINT.md`。
2. 不允许一次性创建全量目录树。
3. 不允许创建无调用方空文件。
4. 不允许跳过 V0-Core 直接开发高级模块。
5. 不允许删除历史文件，只能标记 deprecated。
6. 每次修改前必须说明本次属于哪个 milestone；Android 开发必须明确属于 V0-Android 还是 V1-Android。
7. 每次修改后必须说明：
   - 修改了哪些文件；
   - 完成了什么能力；
   - 如何运行；
   - Android 端如何在模拟器或真机运行；
   - 如何测试；
   - 是否影响主链路。
8. 用户说“进行记忆存储”时，必须更新 `DEVELOPMENT_PROGRESS.md`。
9. 每完成关键节点，必须更新 `KNOWLEDGE_LOG.md`。
10. 每做关键技术取舍，必须更新 `DECISION_LOG.md`。
11. 每次重要改动必须更新 `CHANGELOG.md`。
12. 如果不确定是否应该创建新模块，优先询问用户或只更新文档，不直接写代码。
13. 禁止继续创建 `frontend/` 作为主线目录；历史 `frontend/` 一律按 deprecated 处理。
14. Agent Action、购物车、用户、地址、偏好相关文件必须有调用方和验收方式，不允许只为“完整电商”提前堆空模块。

## 23. 最终交付检查清单

V1 参赛前检查：

- [ ] FastAPI 后端可启动。
- [ ] Android App 可在模拟器或真机启动。
- [ ] Android APK 可打包。
- [ ] 底部四 Tab 可正常切换：商品展示、豆仔智能、购物车、个人中心。
- [ ] 商品展示页可展示数据集商品、搜索筛选、进入商品详情。
- [ ] 商品详情页可加入购物车、跳转豆仔智能并带入当前商品上下文。
- [ ] 购物车页可增删改数量、多选、全选和模拟结算。
- [ ] 个人中心可展示 Demo 用户、地址和偏好入口。
- [ ] 用户、商品、购物车、地址、偏好 API 可用。
- [ ] `/api/health` 正常。
- [ ] `/api/recommend` 文本链路正常。
- [ ] `/api/agent/actions` 可通过受控 action 将商品加入购物车。
- [ ] 主 Demo 图片可上传。
- [ ] Qwen-VL 解析链路可运行或 Demo Pack 可回放。
- [ ] Text / Policy / Review / Compatibility 检索可运行。
- [ ] Evidence IDs 全部可追溯。
- [ ] Decision Scoring 可复算。
- [ ] Android ProductCard 展示正常。
- [ ] Android EvidencePanel 有证据。
- [ ] Android AgentTracePanel 有完整步骤。
- [ ] Android 商品详情或豆仔详情区域能展示 Evidence / Score / Trace / Skill / Harness。
- [ ] CartScreen 能展示“由豆仔推荐加入”。
- [ ] Demo Pack / Mock Mode 可一键触发。
- [ ] Baseline 对比报告可生成。

V1-Plus 检查：

- [ ] Android SkillExecutionPanel 有 Skill 记录。
- [ ] Android HarnessValidationPanel 有校验结果。
- [ ] Tool Manifest 有 schema 和权限字段。
- [ ] Response Guard 能拦截无证据回答。
- [ ] Context Compiler 输出可展示。

V1-Advanced 检查：

- [ ] Android ContextPanel 展示用户约束。
- [ ] Android RetrievalPlanPanel 展示检索计划。
- [ ] Android VisualEvidenceViewer 展示视觉证据。
- [ ] Android fallback 状态展示 fallback level。

## 24. 总结

本文档是 OmniCart Agent 的工程目录施工规范。

它不是要求一次性创建所有目录，而是要求按优先级完成可运行闭环：

```text
V0-Core：先跑通后端文本导购。
V0-Android：再跑通 Android 四 Tab、商品展示、豆仔文本推荐、购物车基础功能和 Demo 用户。
V1-Core：跑通图片/截图购物决策主 Demo 后端链路，并补登录、地址、偏好、Agent Action 和模拟结算。
V1-Android：补图文输入、Evidence、Trace、Harness、豆仔加入购物车、Mock Mode 和 APK。
V1-Plus：补 Agent Runtime、Skill、Tool、Harness 等强加分项。
V1-Advanced：补 Context、Graph、Grounding、Fallback 等前沿展示项。
V2/V3：再扩展标准 MCP、标准 A2A、iOS、Neo4j、语音、长期记忆、观测平台。
```

开发时的最高原则：

```text
不要堆空目录。
不要堆空文件。
不要破坏主链路。
先把一条竖向闭环跑通，再横向扩展高级模块。
```

只要严格按这个施工规范推进，OmniCart Agent 就能从当前蓝图变成一个能跑、能测、能展示、能解释、能回放、能验证的参赛项目。
