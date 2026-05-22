# OmniCart Agent 功能与用户使用说明文档（比赛交付版）

## 1. 文档定位

本文档是 OmniCart Agent 项目的第四个核心文档，定位为“产品功能说明书 + Android 用户使用说明书 + 比赛 Demo 展示说明书 + 功能验收标准”。

它不替代最终技术蓝图、工程目录规范或开发规则，而是回答以下问题：

- 最终用户可以用 Android App 做什么。
- 用户如何完成一次购物咨询。
- App 最终需要呈现哪些功能。
- 哪些功能是基础能力，哪些功能是比赛创新能力。
- 每个功能在 Android 原生客户端上如何展示。
- 每个功能背后依赖哪些后端能力。
- 比赛现场如何演示。
- 评委为什么会觉得项目有竞争力。
- 最终交付时如何验收。

本文档与其他三个核心文档分工如下：

| 文档 | 职责 |
|---|---|
| `OMNICART_AGENT_COMPLETE_BLUEPRINT.md` | 定义项目愿景、技术架构和创新点。 |
| `DEVELOPMENT_DIRECTORY_STRUCTURE.md` | 定义工程目录、阶段顺序和文件落地优先级。 |
| `DEVELOPMENT_RULES.md` | 约束 Claude Code / Codex 等 AI 编程 Agent 的开发行为。 |
| `PRODUCT_FUNCTIONS_AND_USER_GUIDE.md` | 定义最终用户功能、Android 客户端使用流程、比赛演示方式和验收标准。 |

## 2. 产品一句话定位

中文定位：

OmniCart Agent 是一个具备完整购物链路的 Android 原生多模态电商智能导购客户端。用户可以先浏览商品、查看详情、进入“豆仔智能”咨询，再把推荐商品加入购物车并完成模拟结算；系统结合商品数据、用户评论、政策规则、兼容性约束和多模态证据，给出可解释、可验证、可回放的购买建议。

英文定位：

OmniCart Agent is an Android-native multimodal shopping decision agent that helps users make pre-purchase decisions through visual understanding, evidence-grounded RAG, explainable scoring, and verifiable agent execution.

OmniCart Agent 不是普通购物 App，也不是简单商品问答系统。它在传统商品展示、购物车和个人中心基础上，把“豆仔智能”作为核心 AI Agent 页面，帮助用户判断：

- 这个商品能不能买？
- 这个商品适不适合我？
- 有什么风险？
- 有没有更合适的替代品？
- 为什么推荐这个？
- 推荐依据来自哪里？

## 3. 最终交付形态

最终交付形态统一为：

```text
Android Native Client + FastAPI Agent Runtime Backend
```

Android 客户端技术路线统一为：

```text
Kotlin + Jetpack Compose + Material 3
MVVM + ViewModel + StateFlow + Coroutines
Retrofit / OkHttp
```

Android 客户端负责：

- 底部四 Tab：商品展示、豆仔智能、购物车、个人中心。
- 商品列表、商品搜索、商品详情和商品卡片展示。
- 加入购物车、购物车增删改、多选、全选、价格合计和模拟结算。
- Demo 用户、登录状态、地址和个人偏好展示。
- 文本输入。
- 图片选择 / 上传。
- 调用后端 API。
- 展示商品卡片。
- 展示推荐理由。
- 展示 Evidence / Score / Trace / Harness。
- Demo Mode / Mock Mode 演示。

Android 客户端不负责：

- RAG 检索。
- Agent 编排。
- 多模型调用。
- 决策评分计算。
- Harness 验证。
- 复杂推理逻辑。
- 真实支付。
- 真实下单。

所有复杂智能能力均由 FastAPI 后端 Agent Runtime 完成。Android App 是用户交互与结果解释窗口，不是推理引擎。

## 4. 目标用户与典型场景

目标用户：

- 有明确购买意图、但不确定商品是否适合自己的普通消费者。
- 看到商品截图、短视频商品页、直播间商品卡后，希望快速判断是否值得购买的用户。
- 需要综合考虑预算、设备兼容、评论风险、政策规则和使用场景的用户。
- 希望看到推荐依据，而不是只得到一句“可以买”或“不建议”的用户。

典型场景：

| 场景 | 用户问题 | 系统价值 |
|---|---|---|
| 出差充电宝决策 | 我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？ | 同时判断手机兼容、笔记本功率、航空携带风险和评论风险。 |
| 商品截图导购 | 这个截图里的商品适合我吗？ | 识别截图中的商品参数，再结合用户需求做推荐。 |
| 预算内推荐 | 我预算 300 元，想买适合出差的充电宝。 | 检索候选商品，按预算、场景、参数和风险排序。 |
| 风险咨询 | 这款会不会发热？坐飞机能带吗？ | 检索评论风险和政策规则，给出可验证结论。 |
| 多轮追问 | 如果只给 iPhone 充电呢？如果还要给 MacBook 呢？ | 复用上下文约束，给出反事实解释和替代建议。 |
| 完整购物旅程 | 我先看看商品，再问豆仔，最后加入购物车。 | 商品展示、豆仔智能、购物车和个人中心形成真实购物闭环。 |

## 5. 用户核心价值

OmniCart Agent 对用户的核心价值是“把购买前的犹豫变成可解释的决策”。

具体价值：

1. 降低信息搜集成本：用户不用分别查商品参数、评论、政策和兼容性规则。
2. 降低踩坑风险：系统主动提示发热、虚标、功率不足、政策限制等风险。
3. 让推荐可解释：不仅给商品，还展示推荐理由、证据、评分和 Agent 执行过程。
4. 支持图文输入：用户可以直接上传商品截图，不必手动输入完整商品名和参数。
5. 支持购物车联动：豆仔智能可以通过受控 action 将推荐商品加入购物车。
6. 支持个人偏好：设备、预算、品牌偏好和避雷项可服务后续推荐。
7. 支持比赛稳定演示：Demo Mode / Mock Mode 可保证现场展示完整链路。
8. 支持可验证交付：Evidence、Score、Trace、Harness 让结果可检查、可复盘。

## 6. 功能总览

功能分为三层：

```text
V0-Android：四 Tab 基础可用功能
V1-Core：比赛核心功能
V1-Plus：比赛加分创新功能
```

### V0-Android：四 Tab 基础可用功能

目标：

```text
Android App 四 Tab 基础框架
  + 商品展示基础数据
  + 豆仔智能文本推荐
  + 购物车基础功能
  + 个人中心 Demo 用户
```

必须包含：

1. Android 底部四 Tab。
2. 商品展示页可展示商品列表。
3. 商品详情页。
4. 豆仔智能页可进行文本推荐。
5. `/api/recommend` 返回 mock 推荐。
6. 购物车页可展示、增加、删除商品。
7. 个人中心页可显示 Demo 用户。
8. 后端提供商品、购物车、用户基础 API。
9. Demo Mode 可用。

### V1-Core：比赛核心功能

目标：

```text
登录 / 地址 / 偏好
  -> 图文输入
  -> 多模态识别
  -> 多路证据检索
  -> 约束判断
  -> 决策评分
  -> 可解释推荐
  -> 豆仔通过对话加入购物车
  -> 模拟结算
  -> Android 客户端展示 Evidence / Score / Trace / Harness
```

必须包含：

1. 登录 / 注册。
2. 收货地址管理。
3. 用户偏好管理。
4. 图片选择 / 上传。
5. 商品截图解析。
6. 多模态 Evidence RAG。
7. 评论风险检索。
8. 政策规则检索。
9. 兼容性判断。
10. Decision Scoring。
11. Evidence Panel。
12. Score Breakdown。
13. Agent Trace Panel。
14. Harness Validation Panel。
15. 豆仔通过对话加入购物车。
16. 模拟结算。
17. 主 Demo 稳定跑通。

### V1-Plus：比赛加分创新功能

建议包含：

1. Retrieval Plan Panel。
2. Context Panel。
3. Preference Memory Card。
4. Visual Evidence Grounding。
5. Counterfactual Recommendation。
6. Evidence Graph Path。
7. Skill Execution Panel。
8. Tool Governance 展示。
9. Fallback Status。
10. 更完整的 Demo Pack 回放。

V1-Plus 是加分项，不是 V0-Android 或 V1-Core 的前置条件。开发时必须先保证基础闭环和主 Demo 稳定，再逐步补充加分能力。

## 7. 基础功能清单

| 功能名称 | 用户操作 | Android 展示 | 后端依赖 | 验收标准 | 所属阶段 |
|---|---|---|---|---|---|
| 底部四 Tab | 用户点击底部导航切换页面。 | Material 3 `NavigationBar` 展示商品展示、豆仔智能、购物车、个人中心。 | AppNavGraph。 | 四个 Tab 可切换，当前页高亮。 | V0-Android |
| 商品展示 | 用户浏览商品。 | `ProductHomeScreen` 展示商品列表、分类标签、搜索栏。 | `GET /api/products`。 | 能展示数据集商品。 | V0-Android |
| 商品详情 | 用户点击商品卡片。 | `ProductDetailScreen` 展示图片、价格、品牌、规格、参数、评论摘要、风险标签。 | `GET /api/products/{product_id}`。 | 商品详情信息完整。 | V0-Android |
| 文本输入 | 用户在底部输入框输入购物问题并点击发送。 | `ChatInputBar` 展示输入内容，消息进入聊天流。 | `/api/recommend` 接收 `user_query`。 | 文本可输入、可发送、可触发请求。 | V0-Android |
| 图片上传 | 用户点击图片按钮，选择商品截图。 | `ImagePreview` 展示已选图片。 | 上传接口或图片 URL 处理能力。 | 图片可选择、可预览、可随请求发送。 | V1-Core |
| 商品推荐 | 用户提交问题后等待结果。 | 聊天流中出现推荐结果和商品列表。 | Text Retriever / Evidence RAG / Decision Scoring。 | 返回至少 1 个可展示商品。 | V0-Android / V1-Core |
| 商品卡片展示 | 用户浏览推荐商品。 | `ProductCard` 展示商品图、名称、品牌、价格、评分、理由、风险标签。 | `products` 与 `decision_results`。 | 商品卡片字段完整、布局适配手机。 | V0-Android |
| 商品详情查看 | 用户点击“查看详情”。 | `ProductDetailSheet` 从底部弹出，展示多个 Tab。 | 推荐理由、证据、评分、Trace、Harness 数据。 | Tab 可切换，内容与商品关联。 | V1-Core |
| 加入购物车 | 用户点击“加入购物车”。 | 商品详情或 ProductCard 显示加入成功。 | `POST /api/cart/items`。 | 购物车新增对应商品。 | V0-Android |
| 豆仔加入购物车 | 用户说“把适合 MacBook 的那个加入购物车”。 | 豆仔消息显示 action 结果，购物车标注“由豆仔推荐加入”。 | `POST /api/agent/actions` + Cart Service。 | action 可追踪，购物车商品来源正确。 | V1-Core |
| 购物车管理 | 用户增减数量、删除、多选、全选。 | `CartScreen` 展示商品行、数量、选中状态、合计。 | Cart API。 | 增删改、多选、全选有效。 | V0-Android / V1-Core |
| 模拟结算 | 用户点击结算。 | `MockCheckoutSheet` 展示地址、商品、合计和模拟付款结果。 | `POST /api/cart/checkout/mock`。 | 生成模拟订单，不接入真实支付。 | V1-Core |
| 个人中心 | 用户进入个人中心。 | `ProfileScreen` 展示 Demo 用户、登录状态、地址、偏好入口。 | User / Address / Preference API。 | Demo 用户可用，地址和偏好可展示。 | V0-Android / V1-Core |
| 推荐理由展示 | 用户查看商品是否值得买。 | 推荐理由 Tab 展示简洁结论。 | Response Agent 输出 `answer` 和推荐理由。 | 每个推荐结论有理由，不空泛。 | V0-Android / V1-Core |
| Demo Mode | 用户开启 Demo Mode 并选择场景。 | 顶部开关和场景选择，自动填充问题或展示预置结果。 | Demo Pack / Mock Mode。 | 无真实模型调用时也能稳定演示。 | V0-Android / V1-Core |
| API 调用 | 用户点击发送。 | Loading、成功、失败状态清晰展示。 | Retrofit / OkHttp 调用 FastAPI。 | 成功解析响应，失败时提示可理解。 | V0-Android |
| Android APK 运行 | 评委安装或开发者运行 App。 | Android 原生 App 可启动和操作。 | 后端可本地或远程访问。 | APK 可安装，核心流程可跑通。 | V0-Android / V1-Core |

## 8. 创新功能清单

| 创新功能 | 用户看到什么 | 背后技术 | 比赛加分点 | 所属阶段 |
|---|---|---|---|---|
| Multimodal Evidence RAG | Evidence Panel 中同时出现商品参数、评论、政策、兼容性证据。 | 多路检索、证据合并、证据 ID 绑定。 | 推荐不是黑盒，结论有依据。 | V1-Core |
| 多 Agent 工作流 | Trace Panel 展示 Router、Visual、Retrieval、Decision、Response 的执行步骤。 | Workflow-controlled Multi-Agent。 | 体现 Agent Runtime，而不是单轮问答。 | V1-Core |
| Evidence Panel | 用户可查看每条证据的来源、类型、摘要和置信度。 | Evidence Schema 与证据检索。 | 可解释、可验证。 | V1-Core |
| Agent Trace | 用户或评委可看到系统如何一步步决策。 | AgentState、TraceStep。 | 可复盘、可审计。 | V1-Core |
| Decision Scoring | Score Breakdown 展示各维度分数和最终得分。 | 约束判断、评分公式、风险惩罚。 | 推荐排序可解释。 | V1-Core |
| Constraint Solver | 商品详情中提示预算、功率、兼容性、政策是否通过。 | 硬约束优先判断。 | 避免推荐不适合的商品。 | V1-Core |
| Harness Validation | Harness Panel 展示 Schema、证据、评分、政策、风险检查结果。 | Decision Harness。 | 结果可自动验证。 | V1-Core |
| Visual Evidence Grounding | 视觉证据显示来自截图中的哪个字段或区域。 | Visual Agent 字段级证据引用。 | 让图片识别可解释。 | V1-Plus |
| Counterfactual Recommendation | 显示“如果只给 iPhone 充电可以考虑；如果给 MacBook 供电建议 65W 以上”。 | 约束变化下的反事实解释。 | 帮助用户理解推荐边界。 | V1-Plus |
| Preference Memory Card | 多轮追问时系统记住预算、设备和出差场景。 | Session-level preference memory。 | 体现多轮购物决策能力。 | V1-Plus |
| Agent 购物车 Action | 用户说“加入购物车”后，豆仔消息显示操作结果。 | `/api/agent/actions`、Cart Service、Trace 记录。 | Agent 与真实购物链路联动。 | V1-Core |
| MCP-compatible Tool Governance | Trace 或 Harness 中展示工具只读、Schema 校验、调用记录。 | ToolManager、ToolCallRecord、权限控制。 | 工具调用可控可信。 | V1-Plus |
| A2A-lite Agent Communication | Trace 中可看到结构化 Agent 消息和产物。 | AgentMessage / Artifact。 | Agent 协作结构化。 | V1-Plus |

## 9. Android 客户端用户使用流程

### 流程一：完整购物旅程

1. 用户打开 Android App。
2. 底部导航显示四个入口：商品展示、豆仔智能、购物车、个人中心。
3. 用户进入商品展示页，浏览充电宝商品。
4. 用户点击某款充电宝进入商品详情页。
5. 用户点击“问豆仔”。
6. App 跳转到豆仔智能页，并带入当前商品上下文。
7. 用户提问：“我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？有没有更合适的？”
8. 豆仔分析商品详情、商品截图、评论、政策和兼容性规则。
9. 豆仔给出是否推荐和替代商品。
10. 用户说：“把适合 MacBook 的那个加入购物车”。
11. 豆仔通过受控 action 将商品加入购物车。
12. 用户切换到购物车页。
13. 购物车展示刚刚加入的商品，并标注“由豆仔推荐加入”。
14. 用户多选商品并进行模拟结算。
15. 用户进入个人中心查看收货地址和个人偏好。

成功体验：

- 传统购物基础能力、智能导购能力和购物车联动都在一个 Android 原生 App 内完成。
- 豆仔智能不是孤立聊天窗口，而是能参与真实购物流程的 Agent 页面。

### 流程二：文本导购

1. 用户打开 OmniCart Agent App。
2. 用户点击底部“豆仔智能”。
3. 用户在底部输入框输入：“我预算 300 元，想买适合 iPhone 15 出差用的充电宝”。
4. 用户点击发送按钮。
5. App 调用 `POST /api/recommend`。
6. 后端返回商品列表、推荐回答和基础评分。
7. App 在聊天流中展示系统回答。
8. App 展示一组 `ProductCard`。
9. 用户点击商品卡片查看详情或加入购物车。

成功体验：

- 用户能在 1 个主页面完成输入、发送、浏览推荐。
- 商品卡片不只是商品列表，而是直接告诉用户“为什么适合”与“有什么风险”。

### 流程三：图片导购

1. 用户点击底部图片按钮。
2. Android Photo Picker 打开系统图片选择器。
3. 用户选择商品截图。
4. App 在聊天流上方显示图片预览。
5. 用户输入：“这个适合我吗？”
6. App 上传图片或携带 `image_url` 发送推荐请求。
7. 后端解析图片，识别商品容量、功率、接口、价格等字段。
8. 后端结合用户问题和商品截图返回推荐。
9. App 展示识别结果、商品推荐和证据。

成功体验：

- 用户不需要手动输入完整商品参数。
- 系统能解释“截图里哪些信息影响了推荐”。

### 流程四：商品详情查看

1. 用户点击 `ProductCard` 上的“查看详情”。
2. App 打开 `ProductDetailSheet`。
3. 用户切换 Tab：
   - 推荐理由。
   - Evidence。
   - Score。
   - Trace。
   - Harness。
4. 用户从结论、证据、评分、过程、验证五个层面理解推荐。

成功体验：

- 普通用户能快速看推荐理由。
- 评委和开发者能展开 Evidence / Trace / Harness 查看系统可信度。

### 流程五：Demo Mode

1. 用户开启顶部 Demo Mode 开关。
2. 用户选择“出差充电宝”场景。
3. 系统自动填充问题和图片。
4. App 展示完整预置推荐结果。
5. Evidence / Score / Trace / Harness 全部可查看。
6. 若真实模型或网络不可用，Mock Mode 仍能展示完整链路。

成功体验：

- 比赛现场不依赖临场运气。
- 评委可以稳定看到系统的完整价值。

## 10. Android 核心页面与交互设计

### 10.1 Bottom Navigation 主框架

Android App 使用 Jetpack Compose Navigation + Material 3 NavigationBar，底部固定四个 Tab：

1. 商品展示。
2. 豆仔智能。
3. 购物车。
4. 个人中心。

交互要求：

- 每个 Tab 使用扁平化 Icon。
- 当前选中页面高亮。
- 保持移动端简洁风格。
- 豆仔智能 Tab 可以轻微强调，但不能破坏整体一致性。

### 10.2 商品展示页 ProductHomeScreen

商品展示页用于展示数据集中已有商品及其详细情况，是用户浏览商品、查看商品详情、进入智能咨询和加入购物车的基础入口。

包含：

- 商品瀑布流 / 列表。
- 商品卡片 ProductCard。
- 分类标签 CategoryChip。
- 搜索栏 SearchBar。
- 商品详情页 ProductDetailScreen。
- “加入购物车”按钮。
- “问豆仔”按钮。

展示内容：

- 商品图片。
- 商品名称。
- 品牌。
- 价格。
- 规格参数。
- 标签。
- 评论摘要。
- 风险标签。

### 10.3 豆仔智能页 DouzaiChatScreen

`DouzaiChatScreen` 是原项目的核心 AI Agent 页面，也是多模态购物决策能力的主要展示入口。

包含：

- 顶部标题 `OmniCart Agent`。
- Demo Mode 开关。
- 聊天消息区。
- 图片预览区。
- 商品推荐卡片区。
- 底部文本输入框。
- 图片选择按钮。
- 发送按钮。

交互要求：

- 输入区固定在屏幕底部。
- 发送请求时显示 loading 状态。
- 请求失败时显示可理解的错误提示。
- Demo Mode 开启时需要有明确状态提示。
- 支持“把第一个推荐商品加入购物车”“把适合 MacBook 的那个加入购物车”等轻量购物动作。
- 购物车动作必须调用 `/api/agent/actions`，并在消息或 Trace 中展示结果。

### 10.4 购物车页 CartScreen

购物车页用于管理用户选择的商品，并支持基础电商购物车功能。

包含：

- 购物车商品列表。
- 商品数量增加。
- 商品数量减少。
- 删除购物车商品。
- 多选商品。
- 全选商品。
- 价格合计。
- 优惠 / 满减占位展示，可选。
- 模拟结算。
- 模拟付款。
- 模拟订单。
- 展示商品是否由豆仔推荐加入。

说明：

- 付款功能在比赛版中为模拟付款 / 模拟结算，不接入真实支付系统。
- 由豆仔加入的商品必须显示 `added_by = douzai_agent` 和 `added_reason`。

### 10.5 个人中心页 ProfileScreen

个人中心用于记录用户信息、登录状态、收货地址、个人偏好和历史行为，是个性化推荐和多轮购物偏好记忆的基础。

包含：

- 用户登录 / 注册 / 退出登录。
- Demo 用户一键登录。
- 用户头像 / 昵称。
- 收货地址管理。
- 新增、编辑、删除、设置默认地址。
- 个人购物偏好管理。
- 设备信息，例如 iPhone 15、MacBook。
- 预算偏好。
- 品牌偏好。
- 避雷项，例如不喜欢太重、发热、虚标容量。
- 历史咨询记录，可选。
- 历史推荐记录，可选。

V1 阶段采用轻量登录系统即可：手机号 / 用户名 + 密码登录、Demo 用户一键登录、JWT 或 session token、本地 DataStore 保存登录状态，后端记录 `user_id`。

### 10.6 ProductCard 商品卡片

展示：

- 商品图。
- 商品名称。
- 品牌。
- 价格。
- 综合评分。
- 一句话推荐理由。
- 风险标签。
- 查看详情按钮。

设计目标：

- 用户在不进入详情页的情况下，也能快速判断商品是否值得继续看。
- 风险标签必须明显，例如“功率不足”“偏重”“发热评论较多”“政策需确认”。

### 10.7 ProductDetailSheet 商品详情底部弹窗

`ProductDetailSheet` 使用底部弹窗或详情页 Tab 展示：

- 推荐理由。
- Evidence。
- Score。
- Agent Trace。
- Skill Execution。
- Harness Validation。

设计目标：

- 默认打开推荐理由，降低普通用户理解成本。
- 高级 Tab 面向评委、开发者和需要查看依据的用户。
- 每个 Tab 的信息都来自后端响应，不在 Android 本地生成推理结论。

### 10.8 Evidence Panel

展示：

- `evidence_id`。
- 证据类型。
- 证据来源。
- 内容摘要。
- 置信度。
- 关联商品。

证据类型示例：

- 商品参数证据。
- 评论风险证据。
- 政策规则证据。
- 兼容性规则证据。
- 视觉识别证据。

### 10.9 Score Breakdown

展示：

- `budget_fit`。
- `scenario_fit`。
- `spec_match`。
- `review_confidence`。
- `visual_similarity`。
- `availability_score`。
- `risk_penalty`。
- `final_score`。
- `display_score`。

说明：

- `final_score` 是后端内部评分。
- `display_score` 是 Android 客户端展示分数。
- Android 不重算分数，只展示后端结果。

### 10.10 Agent Trace Panel

展示：

- Router。
- Visual。
- Retrieval。
- Decision。
- Response。
- 每一步 `action`。
- `input_summary`。
- `output_summary`。
- `latency_ms`。
- `status`。

用户价值：

- 普通用户可跳过。
- 评委可查看系统是否真的经过 Agent 决策链路。
- 开发者可定位问题。

### 10.11 Harness Validation Panel

展示：

- Schema Valid。
- Evidence IDs Valid。
- Score Formula Valid。
- Policy Evidence Found。
- Risk Warning Included。
- Replay Passed。

用户价值：

- 说明系统不仅能生成结果，还会检查结果是否可靠。
- 让比赛项目从“能回答”升级为“能验证”。

### 10.12 Demo Mode / Mock Mode

展示：

- 场景选择。
- 一键填充主 Demo。
- 本地预置数据回放。
- Mock Mode 状态提示。

设计要求：

- Demo Mode 必须让评委明确知道当前使用演示数据。
- Mock Mode 只用于稳定演示，不伪装成真实模型结果。
- Demo Mode 的数据结构必须与真实 API 响应一致。

## 11. 主 Demo 场景：出差充电宝购物决策

主 Demo 从单一豆仔页面扩展为完整用户旅程：

```text
浏览商品 -> 问豆仔 -> 加入购物车 -> 查看购物车 -> 模拟结算 -> 个人中心查看偏好/地址
```

核心问题仍固定为：

```text
我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？有没有更合适的？
```

这个场景适合作为主 Demo，因为它同时覆盖：

- 商品展示。
- 商品详情。
- 问豆仔。
- Agent 与购物车联动。
- 模拟结算。
- 个人中心偏好和地址。
- 商品截图识别。
- 手机兼容性判断。
- MacBook 功率判断。
- 航空携带政策判断。
- 评论风险检索。
- 可解释评分。
- 替代商品推荐。
- 反事实解释。
- Evidence / Score / Trace / Harness 展示。

### 3 分钟演示脚本

| 时间 | 用户操作 | 系统动作 | Android 界面展示 | 答辩讲解点 |
|---|---|---|---|---|
| 0:00-0:15 | 打开 App。 | 初始化 MainScaffold 和 BottomNavBar。 | 底部显示四个入口：商品展示、豆仔智能、购物车、个人中心。 | “这是完整 Android 原生智能购物客户端，不是只有聊天窗口的 Demo。” |
| 0:15-0:35 | 进入商品展示页，浏览充电宝商品。 | 调用商品列表 API 或读取 Demo 商品数据。 | ProductHomeScreen 展示商品列表、分类标签和搜索栏。 | “传统购物能力提供真实入口，用户可以先像普通购物 App 一样浏览商品。” |
| 0:35-0:55 | 点击某款充电宝查看详情。 | 读取商品详情、规格、评论摘要和风险标签。 | ProductDetailScreen 展示图片、价格、品牌、规格、评论摘要、风险标签，以及“加入购物车”“问豆仔”按钮。 | “商品详情来自数据集，后续智能咨询会带入当前商品上下文。” |
| 0:55-1:10 | 点击“问豆仔”。 | 跳转豆仔智能页，携带当前商品上下文。 | DouzaiChatScreen 自动带入当前商品卡片。 | “豆仔智能不是孤立页面，它能从商品详情承接用户问题。” |
| 1:10-1:30 | 输入主问题并发送。 | 调用 `/api/recommend` 或 Demo Pack。 | 聊天流显示用户问题和 loading。 | “Android 只负责采集输入和展示，复杂推理由后端 Agent Runtime 完成。” |
| 1:30-1:55 | 等待分析结果。 | 后端识别商品容量、功率、接口、价格，检索评论风险、航空政策、兼容性规则。 | 豆仔回答、推荐商品 ProductCard、Evidence 数量和 Trace 状态更新。 | “系统不仅识别商品，还把评论、政策、兼容性作为证据参与判断。” |
| 1:55-2:15 | 查看推荐结果。 | 后端完成约束判断、评分和替代商品推荐。 | 当前商品是否推荐、1-2 个替代商品、风险标签和反事实解释。 | “系统会判断 iPhone 15 是否适用、MacBook 是否适用、坐飞机是否有风险。” |
| 2:15-2:35 | 切换 Evidence / Score / Trace / Harness。 | 读取后端结构化结果。 | 展示证据、评分拆解、Agent 执行链路和 Harness 验证。 | “结果可以通过 Evidence、Score、Trace、Harness 四层验证。” |
| 2:35-2:50 | 输入：“把适合 MacBook 的那个加入购物车”。 | 豆仔生成 `add_to_cart` 受控 action，调用 `/api/agent/actions`。 | 聊天消息显示“已加入购物车”，Trace 记录 action。 | “Agent 能执行轻量购物动作，但只能操作购物车，不能真实支付。” |
| 2:50-3:05 | 切换到购物车页。 | 读取购物车。 | CartScreen 展示刚加入的商品，并标注“由豆仔推荐加入”。 | “智能推荐和购物车闭环打通，用户可以继续管理商品。” |
| 3:05-3:20 | 多选商品并点击模拟结算。 | 调用 mock checkout。 | 展示合计价格、默认地址、模拟付款成功和模拟订单。 | “比赛版只做模拟结算，不接入真实支付。” |
| 3:20-3:30 | 进入个人中心。 | 读取 Demo 用户、地址和偏好。 | ProfileScreen 展示设备、预算、品牌偏好、避雷项和默认地址。 | “用户偏好可服务下一轮豆仔推荐，形成可持续购物体验。” |

主 Demo 最终回答应包含：

```text
综合判断后，当前商品适合 iPhone 15 日常充电，但不适合作为 MacBook 主力供电方案。
如果只给 iPhone 15 充电，当前商品可以考虑；如果要给 MacBook 供电，建议选择 65W 以上型号。
坐飞机携带需要关注容量和航空政策限制，系统已引用相关政策证据。
```

主 Demo 必须展示的结果：

1. 底部四 Tab。
2. 商品展示页和商品详情。
3. “问豆仔”带入当前商品上下文。
4. 当前商品是否推荐。
5. 推荐或不推荐的理由。
6. 1-2 个替代商品。
7. ProductCard。
8. Evidence。
9. Score。
10. Trace。
11. Harness。
12. 反事实解释。
13. 豆仔通过受控 action 加入购物车。
14. CartScreen 标注“由豆仔推荐加入”。
15. 模拟结算。
16. 个人中心地址和偏好。

## 12. 辅助 Demo 场景

辅助 Demo 不应喧宾夺主，只用于证明系统可迁移到其他购物决策场景。

| 场景 | 用户输入 | 展示重点 |
|---|---|---|
| 预算内充电宝推荐 | 我预算 300 元，想买适合 iPhone 15 的充电宝。 | 文本导购、ProductCard、基础评分。 |
| 飞机携带风险咨询 | 这个充电宝坐飞机能带吗？ | 政策证据、风险提示、Harness 检查。 |
| 手机配件兼容性 | 这个充电器适合 iPhone 15 吗？ | 兼容性规则、Evidence、Score。 |
| 多轮追问 | 如果我还想给 MacBook 充电呢？ | Preference Memory Card、反事实解释。 |
| 图片识别失败兜底 | 上传模糊商品截图。 | Fallback Status、提示用户补充信息、Mock Mode。 |

## 13. 功能模块详细说明

### 13.1 商品展示

商品展示页像传统购物软件一样提供基础浏览能力，但商品数据来自项目数据集，不在文档中硬编码具体商品内容。

用户看到：

- 商品列表 / 瀑布流。
- 分类标签。
- 搜索栏。
- 商品卡片。
- 商品详情页。
- 加入购物车按钮。
- 问豆仔按钮。

后端依赖：

- `GET /api/products`。
- `GET /api/products/{product_id}`。
- `GET /api/products/search`。
- Product Repository。

### 13.2 豆仔智能

豆仔智能是原项目核心 AI Agent 页面。

用户可以：

- 文本购物咨询。
- 图片上传 / 商品截图识别。
- 商品对比。
- 评论风险总结。
- 兼容性判断。
- 政策规则检索。
- 查看 Evidence / Score / Trace / Harness。
- 通过对话把商品加入购物车。

后端依赖：

- `/api/recommend`。
- `/api/agent/actions`。
- Agent Runtime。
- Multimodal Evidence RAG。
- Decision Scoring。
- Decision Harness。

### 13.3 购物车

购物车页管理用户选择的商品。

用户可以：

- 查看购物车商品。
- 增加或减少数量。
- 删除商品。
- 多选和全选。
- 查看价格合计。
- 进行模拟结算。
- 查看商品是否由豆仔推荐加入。

后端依赖：

- Cart API。
- Cart Service。
- Mock Checkout。

### 13.4 个人中心

个人中心管理用户、地址和偏好。

用户可以：

- 登录 / 注册 / 退出登录。
- Demo 用户一键登录。
- 查看头像和昵称。
- 管理收货地址。
- 管理设备、预算、品牌偏好和避雷项。
- 查看历史咨询或推荐记录，可选。

后端依赖：

- User API。
- Address API。
- Preference API。
- `user_id` 数据绑定。

### 13.5 文本购物咨询

用户输入自然语言购物需求，系统返回结构化推荐结果。

用户看到：

- 用户消息气泡。
- 系统回答。
- 商品推荐卡片。
- 基础评分和推荐理由。

后端依赖：

- 文本检索。
- 商品数据读取。
- Decision Scoring。
- Response Agent。

### 13.6 图片选择 / 上传

用户通过 Android Photo Picker 选择商品截图。

用户看到：

- 图片预览。
- 识别中状态。
- 识别结果摘要。
- 后续推荐结果。

后端依赖：

- 图片上传或图片 URL 处理。
- Visual Agent。
- visual_result 结构化输出。

### 13.7 商品推荐卡片

商品推荐卡片是用户最先看到的决策结果。

用户看到：

- 商品图、名称、品牌、价格。
- 综合评分。
- 一句话推荐理由。
- 风险标签。
- 查看详情按钮。

后端依赖：

- `products`。
- `decision_results`。
- `answer`。
- `evidence_ids`。

### 13.8 推荐理由

推荐理由面向普通用户，必须简洁、直接、可行动。

推荐理由应回答：

- 为什么推荐。
- 为什么不推荐。
- 适合什么场景。
- 有什么风险。
- 是否有替代选择。

后端依赖：

- Response Agent。
- Context Compiler。
- Evidence。
- DecisionResult。

### 13.9 Evidence Panel

Evidence Panel 面向希望查看依据的用户和评委。

每条证据应包含：

- 证据 ID。
- 类型。
- 来源。
- 摘要。
- 置信度。
- 关联商品。

后端依赖：

- Evidence RAG。
- Evidence Merger。
- Evidence ID 绑定。

### 13.10 Score Breakdown

Score Breakdown 展示推荐分数如何形成。

用户看到：

- 各维度分数。
- 风险惩罚。
- 最终分数。
- 展示分数。

后端依赖：

- Decision Scoring。
- Constraint Solver。
- Risk Analyzer。

### 13.11 Agent Trace Panel

Trace Panel 展示系统执行过程。

用户看到：

- 每个 Agent 的动作。
- 输入输出摘要。
- 执行耗时。
- 成功、失败或跳过状态。

后端依赖：

- Agent Runtime。
- AgentState。
- TraceStep。

### 13.12 Harness Validation Panel

Harness Panel 展示系统是否自检通过。

用户看到：

- Schema 是否有效。
- Evidence IDs 是否有效。
- Score Formula 是否有效。
- Policy Evidence 是否存在。
- Risk Warning 是否包含。
- Replay 是否通过。

后端依赖：

- Decision Harness。
- Demo Pack 回放。
- 验证规则。

## 14. 后端能力与 Android 展示映射

| 后端能力 | Android 展示位置 | 用户感知 |
|---|---|---|
| FastAPI `/api/recommend` | ChatScreen loading / result | 发送问题后得到推荐。 |
| Visual Agent | 图片识别摘要、Visual Evidence | 系统看懂商品截图。 |
| Text / Product Retriever | ProductCard | 系统找到候选商品。 |
| Review Risk Retriever | Evidence Panel、风险标签 | 系统发现评论风险。 |
| Policy Retriever | Evidence Panel、Harness Panel | 系统引用政策依据。 |
| Compatibility Retriever | Score Breakdown、推荐理由 | 系统判断设备是否适配。 |
| Constraint Solver | ProductCard 风险标签、Score Tab | 系统识别硬约束是否通过。 |
| Decision Scoring | Score Breakdown | 推荐排序有分数依据。 |
| Response Agent | 系统回答、推荐理由 Tab | 生成面向用户的解释。 |
| Agent Trace | Trace Panel | 展示执行过程。 |
| Decision Harness | Harness Validation Panel | 展示验证结果。 |
| Demo Pack / Mock Mode | Demo Mode 场景回放 | 保证比赛稳定演示。 |

## 15. Demo Mode / Mock Mode 说明

Demo Mode 是比赛展示功能，不是伪造真实能力。

Demo Mode 的作用：

- 固定主 Demo 输入。
- 回放预置图片、问题和后端结构化结果。
- 在模型接口、网络或本地环境不稳定时保证演示完整。
- 让评委稳定看到 Evidence / Score / Trace / Harness。

Mock Mode 的要求：

- 必须在 Android 客户端显示当前为 Mock Mode。
- Mock 数据结构必须与真实 `/api/recommend` 响应一致。
- Mock Mode 只作为兜底，不替代真实链路开发。
- 演示时可以先展示 Mock Mode，再说明真实 API 使用同一套展示结构。

主 Demo Pack 至少包含：

```text
powerbank_flight_demo/
  input.png
  user_query.txt
  visual_result.json
  evidence_list.json
  decision_results.json
  trace_steps.json
  skill_executions.json
  harness_report.json
  fallback_status.json
  final_response.json
```

## 16. Evidence / Score / Trace / Harness 可验证体验

OmniCart Agent 的比赛竞争力，来自“推荐结果可验证”。

### Evidence：依据可追溯

用户可以看到推荐结论引用了哪些证据：

- 商品参数来自哪里。
- 评论风险来自哪里。
- 政策规则来自哪里。
- 兼容性判断来自哪里。

### Score：排序可解释

用户可以看到推荐分数如何形成：

- 是否符合预算。
- 是否符合使用场景。
- 参数是否匹配。
- 评论可信度如何。
- 视觉相似度如何。
- 库存或可购买性如何。
- 风险如何扣分。

### Trace：过程可复盘

用户和评委可以看到系统执行链路：

```text
Router -> Visual -> Retrieval -> Decision -> Response
```

### Harness：结果可验证

系统不仅输出答案，还检查答案：

- Schema 是否正确。
- Evidence IDs 是否存在。
- 评分是否可复算。
- 政策类问题是否引用政策证据。
- 风险类问题是否包含风险提醒。
- Demo Pack 是否可回放。

## 17. API 契约与客户端展示字段

### 17.1 推荐主接口

Android 客户端的智能导购主接口是：

```text
POST /api/recommend
```

请求示例：

```json
{
  "user_query": "我用 iPhone 15 和 MacBook，经常出差坐飞机，这个充电宝能买吗？",
  "image_url": "/uploads/demo_powerbank.png",
  "demo_mode": false
}
```

响应示例：

```json
{
  "session_id": "S001",
  "answer": "综合判断后，当前商品适合 iPhone 15 日常充电，但不适合作为 MacBook 主力供电方案。",
  "products": [],
  "evidence_list": [],
  "decision_results": [],
  "trace_steps": [],
  "skill_executions": [],
  "harness_report": {},
  "fallback_status": {}
}
```

Android 客户端字段使用方式：

| 字段 | Android 展示 |
|---|---|
| `session_id` | 会话状态和 Trace 查询关联。 |
| `answer` | 系统回答气泡、推荐理由摘要。 |
| `products` | ProductCard 列表。 |
| `evidence_list` | Evidence Panel。 |
| `decision_results` | Score Breakdown、风险标签、综合评分。 |
| `trace_steps` | Agent Trace Panel。 |
| `skill_executions` | Skill Execution Panel。 |
| `harness_report` | Harness Validation Panel。 |
| `fallback_status` | Demo / fallback 状态提示。 |

### 17.2 基础电商 API 契约

以下 API 服务 Android 四 Tab 基础能力。所有用户态数据都必须通过 `user_id` 绑定，Android 客户端只调用 API，不直接访问数据库。

#### Auth API

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
```

用途：

- 注册账号。
- 登录账号或 Demo 用户。
- 退出登录。
- 返回当前会话 token 和 `user_id`，供用户信息、地址、偏好、购物车和 Agent Action 使用。

请求字段示例：

```json
{
  "username": "demo_user",
  "phone": "13800000000",
  "password": "demo_password"
}
```

响应字段示例：

```json
{
  "user": {},
  "access_token": "demo-token",
  "token_type": "bearer"
}
```

#### Users API

```text
GET /api/users/me
PUT /api/users/me
GET /api/users/me/preferences
PUT /api/users/me/preferences
```

用途：

- 读取和更新当前用户信息。
- 读取和更新用户偏好。
- 个人中心展示 Demo 用户、设备、预算、品牌偏好、避雷项和使用场景。

#### Products API

```text
GET /api/products
GET /api/products/{product_id}
GET /api/products/search
```

用途：

- 商品展示页读取商品列表。
- 商品详情页读取商品详情。
- 支持关键词、分类、品牌、价格区间等基础筛选。
- 商品数据以后端 repository / `data/` 数据集为准，不在 Android 端硬编码。

#### Cart API

```text
GET    /api/cart
POST   /api/cart/items
PUT    /api/cart/items/{cart_item_id}
DELETE /api/cart/items/{cart_item_id}
PUT    /api/cart/items/select
POST   /api/cart/checkout/mock
```

用途：

- 查询购物车。
- 加入商品。
- 修改数量。
- 删除商品。
- 多选、全选、取消选择。
- 生成模拟订单并展示模拟结算结果。

`POST /api/cart/checkout/mock` 只能做 mock checkout / 模拟付款 / 模拟订单，不接入真实支付 SDK、真实支付网关或真实下单系统。

#### Addresses API

```text
GET    /api/addresses
POST   /api/addresses
PUT    /api/addresses/{address_id}
DELETE /api/addresses/{address_id}
PUT    /api/addresses/{address_id}/default
```

用途：

- 查询当前用户地址列表。
- 新增、编辑、删除地址。
- 设置默认收货地址。
- 购物车模拟结算时读取默认地址。

#### Agent Actions API

```text
POST /api/agent/actions
```

用途：

- 豆仔智能通过结构化受控 action 操作购物车。
- 允许 `add_to_cart`、`remove_from_cart`、`update_cart_quantity` 等轻量购物车动作。
- Agent 不直接操作数据库，必须通过 `agent_action_service.py` 调用 Cart Service。
- action 结果必须写入聊天消息或 Trace，便于比赛展示和审计。

请求示例：

```json
{
  "session_id": "S001",
  "action_type": "add_to_cart",
  "product_id": "P001",
  "quantity": 1,
  "reason": "豆仔根据用户 MacBook 供电需求推荐加入购物车"
}
```

响应示例：

```json
{
  "action_id": "ACT001",
  "status": "success",
  "cart_item_id": "CART001",
  "message": "已加入购物车",
  "trace_step_id": "T010"
}
```

### 17.3 基础数据模型

V0-Android 可以先使用 JSON mock 数据或内存数据；V1-Core 再接入 SQLite / PostgreSQL。无论实现方式如何，用户信息、地址、偏好、购物车和模拟订单都必须绑定 `user_id`。

| 模型 | 核心字段 | Android 展示位置 |
|---|---|---|
| `User` | `user_id`, `username`, `phone`, `avatar_url`, `created_at` | ProfileScreen、登录状态。 |
| `UserPreference` | `user_id`, `devices`, `budget_range`, `preferred_categories`, `preferred_brands`, `avoid_tags`, `scenarios` | ProfileScreen、PreferenceScreen、豆仔上下文。 |
| `Address` | `address_id`, `user_id`, `receiver_name`, `phone`, `province`, `city`, `district`, `detail`, `is_default` | AddressListScreen、MockCheckoutSheet。 |
| `CartItem` | `cart_item_id`, `user_id`, `product_id`, `quantity`, `selected`, `added_by`, `added_reason`, `created_at` | CartScreen、CartItemRow。 |
| `MockOrder` | `order_id`, `user_id`, `items`, `total_price`, `address_id`, `status`, `created_at` | MockCheckoutSheet、模拟结算结果。 |

Android 客户端只根据这些字段渲染 UI，不参与复杂推理，不重算评分，不生成证据，不伪造 Trace 或 Harness。

## 18. 功能验收标准

### V0-Android 验收

- Android App 可安装运行。
- 底部四 Tab 可切换：商品展示、豆仔智能、购物车、个人中心。
- 商品展示页可展示数据集商品和商品详情。
- 用户可输入文本。
- App 可调用 `/api/recommend`。
- 后端返回 mock 推荐。
- 购物车可展示、增加、删除商品。
- 个人中心可展示 Demo 用户。
- App 可展示 ProductCard。
- ProductCard 至少展示商品名、价格、评分、推荐理由和风险标签。
- Demo Mode 可用。
- 不依赖任何非 Android 原生客户端交付形态。

### V1-Core 验收

- 用户可登录 / 注册。
- 用户可管理收货地址。
- 用户可管理设备、预算、品牌偏好和避雷项。
- 用户可选择或上传图片。
- App 可展示图片预览。
- 后端可解析图片或使用 Demo Pack 返回 `visual_result`。
- App 可展示推荐结果。
- 豆仔智能可通过受控 action 将推荐商品加入购物车。
- 购物车可执行模拟结算并生成模拟订单。
- Evidence Panel 可展示证据。
- Score Panel 可展示评分。
- Trace Panel 可展示 Agent 过程。
- Harness Panel 可展示验证结果。
- 主 Demo 可稳定演示。
- Mock Mode 可一键兜底。

### V1-Plus 验收

- Context Panel 可展示用户约束。
- Retrieval Plan Panel 可展示检索计划。
- Visual Evidence Grounding 可展示图片证据来源。
- Counterfactual Recommendation 可展示“如果……那么……”解释。
- Preference Memory Card 可支持多轮追问。
- Tool Governance 可在 Trace 或 Harness 中体现。

## 19. 比赛评测指标

| 指标 | 说明 | 评测方式 |
|---|---|---|
| 主链路完成率 | 文本或图文输入后是否能返回推荐。 | 使用固定 Demo Query 测试。 |
| Android 可用性 | App 是否可安装、可启动、可操作。 | 真机或模拟器验证。 |
| Evidence Citation Rate | 推荐结论是否绑定证据。 | 检查 `evidence_ids` 和 Evidence Panel。 |
| Constraint Satisfaction Rate | 推荐是否满足预算、设备、政策等硬约束。 | Golden Query 人工或脚本检查。 |
| Risk Awareness Rate | 是否提示评论风险和政策风险。 | 检查回答和风险标签。 |
| Score Explainability | 分数是否能拆解展示。 | 检查 Score Breakdown。 |
| Trace Completeness | Agent 过程是否完整。 | 检查 Trace Panel。 |
| Harness Pass Rate | 验证项是否通过。 | 检查 Harness Report。 |
| Demo Stability | 主 Demo 是否稳定跑完。 | 连续多次演示。 |
| Fallback Recovery | 异常时是否能进入兜底流程。 | 模拟视觉失败或网络不稳定。 |

## 20. 比赛展示话术

1. OmniCart Agent 不是一个简单的商品问答机器人，而是一个面向购买前决策的多模态购物决策 Agent。
2. 用户可以在 Android 原生 App 中输入购物需求，也可以直接上传商品截图，系统会结合图像理解和结构化证据给出购买建议。
3. 用户上传商品截图后，系统不仅识别商品，还会结合评论、政策、兼容性规则和商品信息进行综合判断。
4. 我们把一次购物咨询拆解为可追踪的 Agent 决策链路，最终结果可以通过 Evidence、Score、Trace 和 Harness 四个层面验证。
5. 对用户来说，它回答的不只是“买哪一个”，而是“为什么这个适合我、有什么风险、有没有更好的替代品”。
6. Android 客户端只负责输入采集和结果展示，复杂推理、RAG 检索、Agent 编排、评分和验证都由 FastAPI 后端 Agent Runtime 完成。
7. Demo Mode 让比赛现场可以稳定展示完整链路，同时真实 API 与 Demo Pack 使用同一套响应结构。
8. 项目的核心竞争力是把多模态 RAG、可解释评分和可验证 Agent 执行落到一个真实可用的移动端购物决策体验中。

## 21. 最小交付清单

| 交付物 | 最小要求 |
|---|---|
| Android App / APK | 可安装、可启动、可完成 V0-Android 文本导购闭环。 |
| FastAPI 后端 | 提供 `/api/health` 和 `/api/recommend`。 |
| ProductCard | 可展示商品图、商品名、价格、评分、推荐理由、风险标签。 |
| ProductDetailSheet | 可展示推荐理由、Evidence、Score、Trace、Harness。 |
| Demo Mode | 可选择“出差充电宝”场景并稳定回放。 |
| Demo Pack | 包含主 Demo 图片、问题、证据、评分、Trace、Harness、最终回答。 |
| Mock Mode | 网络或模型不可用时仍可展示完整结果。 |
| Smoke Test | 可验证 `/api/recommend` 返回结构符合 Android 展示需要。 |
| 说明文档 | 包含用户流程、Demo 方式、验收标准和比赛话术。 |

## 22. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 图片解析失败 | 无法从截图中提取商品参数。 | 使用 Demo Pack、OCR fallback 或提示用户补充商品名称。 |
| 后端响应慢 | Android 端等待时间过长。 | 显示 loading，设置超时，Demo Mode 兜底。 |
| API 字段变更 | Android UI 渲染失败。 | 固定 `/api/recommend` 契约，使用数据类和错误状态兜底。 |
| 证据不足 | 推荐结论可信度下降。 | Harness 标记证据不足，回答中降低结论强度。 |
| 主 Demo 数据不稳定 | 比赛现场演示风险高。 | 使用固定 Demo Pack，提前多次彩排。 |
| 功能范围过大 | 影响基础交付。 | 严格按 V0-Android、V1-Core、V1-Plus 分层推进。 |
| Android UI 信息过载 | 普通用户看不懂。 | 默认展示推荐理由，高级信息放入 Bottom Sheet Tab。 |

## 23. 开发优先级建议

### 第 1 周：V0-Android 闭环

目标：

- Android App 可启动。
- ChatScreen 可输入文本。
- App 可调用 `/api/recommend`。
- ProductCard 可展示。
- Demo Mode 本地假数据可用。

不做：

- 完整 Evidence。
- 完整 Trace。
- 完整 Harness。
- 复杂图片逻辑。

### 第 2 周：V1-Core 主 Demo

目标：

- 图片选择 / 上传。
- 主 Demo 充电宝截图。
- ProductDetailSheet。
- Evidence Panel。
- Score Breakdown。
- Agent Trace Panel。
- Harness Validation Panel。
- Mock Mode 一键演示。

重点：

- 主 Demo 稳定跑通。
- Evidence、Score、Trace、Harness 至少有完整可展示数据。

### 第 3 周：V1-Plus 加分项

目标：

- Retrieval Plan Panel。
- Context Panel。
- Visual Evidence Grounding。
- Counterfactual Recommendation。
- Skill Execution Panel。
- Tool Governance 展示。
- 更完整 Demo Pack 回放。

原则：

- 只在 V1-Core 稳定后开发。
- 加分项不影响主链路。
- 任何高级能力失败时，主 Demo 仍可运行。

## 24. 总结

OmniCart Agent 的产品目标，是把一次“我到底该不该买”的购物咨询，转化为一个可解释、可验证、可回放的 Android 原生移动端决策体验。

用户在 App 中输入文本或上传商品截图后，系统由 FastAPI 后端 Agent Runtime 完成视觉理解、证据检索、约束判断、评分和验证。Android 客户端负责以移动端友好的方式展示结果：ProductCard 给出快速结论，ProductDetailSheet 展示推荐理由、Evidence、Score、Trace 和 Harness。

比赛交付时，项目最重要的不是堆满所有高级功能，而是稳定展示一条完整主链路：

```text
Android 图文输入
  -> 后端 Agent Runtime 决策
  -> Android ProductCard 展示
  -> Evidence / Score / Trace / Harness 可验证解释
  -> Demo Mode 稳定回放
```

只要 V0-Android 基础闭环、V1-Core 主 Demo 和可验证体验稳定完成，OmniCart Agent 就能向评委清楚证明：它不是普通聊天机器人，而是一个真正面向购买前决策的多模态购物决策 Agent。
