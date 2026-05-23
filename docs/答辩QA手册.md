# OmniCart Agent 答辩 QA 手册

> 适用：字节跳动 Agent 挑战赛答辩 / 技术面试 / 项目汇报
> 更新：2026-05-23（基于 V1 全部完成架构 — 51/51 项，含 Redis 四级缓存体系）

---

## 一句话定位

> OmniCart Agent 是一个面向购买前决策的 Android 原生多模态购物决策 Agent，融合 Qwen 全栈模型、LLM 查询改写 + Qdrant 语义向量 + jieba 关键词 RRF 混合检索、LangGraph 8 节点 Multi-Agent 编排、PostgreSQL 6 表持久化、7 维可解释决策评分、标准 MCP Protocol 8 Tool + JSON-RPC 2.0 + Skill Registry + ToolManager、State Checkpoint、Decision Harness 验证框架、Redis 四级缓存、LLM 全链路可观测性、Qwen-Omni 语音导购、闲聊模式 + 完整用户体系 + Android 四 Tab 原生客户端 + V1-Plus Agent 洞察面板。

---

## 一、系统架构全景

```
Android App (Kotlin/Compose/MVVM) — 四个 Tab + 10 个子页面
    │ Retrofit + OkHttp + Auth Bearer Token 拦截器
    ▼
FastAPI Backend (Python 3.11) — 26 个 API 端点
    │
    ├─ POST /api/recommend/v2 ──→ LangGraph 8 节点 Workflow
    │   Router → Visual(Qwen-VL) → Retrieval(LLM改写+三通道并行) → Reranker
    │       → EvidenceCheck → Decision → Response(Qwen) → Guard → Harness
    │
    ├─ /api/auth/*       ──→ PgUserRepository (PBKDF2 100k + Bearer Token)
    ├─ /api/addresses/*  ──→ PgAddressRepository (省/市/区/详细 + is_default互斥)
    ├─ /api/preferences  ──→ PreferenceMemory + PgPreferenceRepository
    ├─ /api/products     ──→ PgProductRepository (100件商品 JSONB)
    ├─ /api/cart/*       ──→ PgCartRepository (购物车商品快照)
    ├─ /api/checkout     ──→ Mock 结算（不接入真实支付）
    ├─ /api/agent/action ──→ 豆仔加购（受控操作 + ToolCallRecord）
    └─ /api/upload       ──→ 图片上传 + Qwen-VL 解析

基础设施层:
    ├─ **Redis 四级缓存**: Visual(1h) / Search(5min) / LLM Rewrite(30min) / Workflow(5min)
    ├─ **LLM 可观测性**: Gateway 全量追踪 + 本地 JSON 存储 + 聚合统计 API
    ├─ **MCP Server**: 8 Tool + JSON-RPC 2.0 + stdio/SSE 双传输 + Claude Desktop 可接入
    ├─ Skill Registry: 8 Skill（视觉/检索/评论/政策/兼容性/评分/验证/Demo）
    ├─ ToolManager: 8 Tool + Manifest + 权限控制 + V1 只读强制
    ├─ State Checkpoint: JSON 文件 8 节点持久化 (resume/replay/export)
    ├─ Decision Harness: 7 项统一校验框架
    ├─ Evidence Graph Lite: NetworkX 商品-证据-风险图
    ├─ A2A-lite Dispatcher: AgentMessage/Artifact 同进程分发
    ├─ CategoryIndex: 品类→子品类→品牌→商品 4 级分层 + 250+关键词映射
    ├─ Multimodal Fallback: L0 Qwen-VL → L1 Mock → L2 纯文本 3 级降级
    ├─ Counterfactual Recommender: 0 结果时智能反事实建议
    ├─ Visual Grounding: 字段级视觉证据绑定 (evidence_id 可追溯)
    └─ LLM Query Rewrite: Qwen 口语→搜索关键词 + jieba 单字兜底
```

---

## 二、Multi-Agent 编排（创新点必问）

### Q: 8 个节点做什么？

| # | 节点 | 功能 | 关键技术 |
|---|------|------|---------|
| 1 | Router Agent | 意图识别(6种含闲聊) + 约束抽取 + 检索计划 | 规则优先 LLM + 250+关键词 + 16个闲聊检测 + 话题切换 |
| 2 | Visual Agent | Qwen-VL 商品截图解析 | 3 级降级(L0真实→L1 Mock→L2纯文本) + Visual Grounding |
| 3 | Retrieval Agent | 三通道并行检索 | **LLM查询改写**(口语→搜索词) + Qdrant 1024d ANN + jieba RRF k=60 |
| 4 | Reranker | Qwen3-Rerank 语义精排 | 失败保持原序，不阻塞链路 |
| 5 | Evidence Checker | 按意图类型检查证据充足性 | 5 种意图×最少证据类型矩阵 |
| 6 | Decision Agent | 硬约束过滤 + 7维加权评分 + 风险标签 | 预算×2/品类不匹配直接排除 |
| 7 | Response Agent | LLM 回答 + 闲聊/购物双模式 | Context Compiler + 6类闲聊模板兜底 |
| 8 | Response Guard | 5 项守门验证 | evidence_bound/price_accurate/risk_warned/honest/无依据 |

### Q: Agent 间怎么通信？

LangGraph WorkflowState 全局状态 + A2A-lite Dispatcher（AgentMessage/Artifact）。V2 可升级为标准 A2A Protocol。

### Q: 闲聊怎么处理？

Router 检测 16 个闲聊关键词 → intent=chitchat → **跳过全部检索/评分链**，直接 Response Agent 用独立 Prompt 生成友好文字回复。6 类模板兜底（打招呼/自我介绍/能力说明/感谢/告别/其他）。

### Q: Router Agent 为什么规则优先于 LLM？

**实测发现** Qwen 有时将"买食品"误判为"美妆护肤"、"买鞋"遗漏。合并策略 `{**llm_result, **rule_result}` 确保规则覆盖 LLM，品类/预算/意图以规则为准。

---

## 三、LLM 查询改写（新增核心创新）

### Q: 怎么解决口语查询检索不准？

**两阶段增强**：
1. **LLM 改写**：Qwen LLM 把"我想买鞋"→"运动鞋 跑步鞋 休闲鞋 鞋"→ 直接命中所有鞋类子品类，score 从 0 飙升到 50-65
2. **单字拆分兜底**：LLM 不可用时，jieba 分词后多字词拆单字（"买鞋"→["买","鞋"]），单字"鞋"命中子品类 +3.0 分

**效果对比**：
```
修改前：查询"我想买鞋" → 所有产品 score=0 → 返回护肤品（默认顺序）
修改后：查询"我想买鞋" → 9款鞋 score=3.0-65.0 → Top5全是鞋 ✅
```

### Q: 为什么不能只用 jieba？

jieba 把"我想买鞋"切为"买鞋"（一个词），任何产品都不含"买鞋"，score 全 0。手工维护 250+ 关键词永远有边界 case。LLM 理解"我想买鞋"=要买鞋零成本。

---

## 四、数据库架构

### Q: PostgreSQL + Qdrant 双库设计

| 数据库 | 用途 | 技术亮点 |
|--------|------|---------|
| PostgreSQL 18 | 6 张表（products/users/addresses/cart_items/user_preferences/checkpoints） | JSONB 嵌套数据 + asyncpg + Alembic |
| Qdrant 1.18 | 语义向量检索 | Rust 高性能 ANN + 1024d COSINE + 本地部署零依赖 |

### Q: 6 张表设计要点

- **products**：skus + rag_knowledge 用 JSONB（动态属性无需 EAV，100 件规模完美）
- **users**：PBKDF2-SHA256 100k 迭代 + Bearer Token 每次登录刷新
- **addresses**：省/市/区/详细 + is_default 互斥逻辑
- **cart_items**：商品快照反范式（加购时复制 price/title/image，标准做法）
- **user_preferences**：JSONB + UPSERT ON CONFLICT
- **checkpoints**：JSON 文件存储（data/checkpoints/{session}_{node}.json）

### Q: 降级策略

```
DATABASE_URL="" + QDRANT_URL="" → JSON文件 + jieba（V0兼容）
任一有值                       → 对应功能启用
任一连接失败                    → 自动降级，不阻塞
```

`.env` 留空即降级，无需改代码。6 类 Repository 全部 PG+内存双模 + 工厂注入。

### Q: sync-async 桥接

LangGraph invoke() 同步 + SQLAlchemy async → `nest_asyncio` 允嵌套事件循环 → `loop.run_until_complete()` 桥接。

---

## 五、RAG 检索体系

### Q: 三层 RAG 架构

```
第一层：LLM查询改写（口语→搜索关键词）
第二层：三通道并行检索
  ├─ Text: Qdrant 1024d ANN + jieba关键词 RRF(k=60) 融合
  ├─ Review: ≤2★差评 + ≥4★好评 正反证据
  └─ Policy: FAQ航空/兼容/过敏 关键词匹配
第三层：Qwen3-Rerank 语义精排 + Evidence Sufficiency Checker
```

### Q: RRF 为什么不是加权求和？

两个排序列表分数尺度不同（余弦相似度 0~1 vs 关键词命中次数），RRF 只依赖排名位置无需归一化。业界标准（ES 8.x 也在用）。

### Q: 证据怎么绑定？

每个推荐结论绑定 `evidence_ids`（如 `E-MKT-p001`/`R-p001-0`/`POL-p001-1`/`V-p001-specs`），可追溯到具体数据源。Android ProductDetailSheet 证据 Tab 展示类型/内容/置信度。

---

## 六、可解释决策评分

### Q: 7 维公式

```
raw = 0.22×budget_fit + 0.24×scenario_fit + 0.20×spec_match
    + 0.14×review_confidence + 0.10×visual_similarity  
    + 0.10×availability_score - 0.15×risk_penalty

final = clamp(raw, 0, 1)
display = final×10（0-10分）
```

场景匹配权重最高，风险扣分独立不抵消。Android 端 ScoreBreakdown 7 维进度条颜色编码展示，每项可独立解释。

---

## 七、用户体系

### Q: 认证方案

PBKDF2-SHA256 100k 迭代（纯标准库，零外部依赖）+ Bearer Token。Android AuthManager SharedPreferences 持久化 + OkHttp 拦截器自动注入 `Authorization: Bearer <token>`。

### Q: 为什么不用 JWT？

比赛场景无需过期/刷新/黑名单等 JWT 复杂度。Bearer Token 每次登录刷新，足够安全。

### Q: 地址管理的默认地址互斥

数据库 + 仓库层双向保证：新增/修改默认地址时，自动清除同用户其他地址的 `is_default` 标记。

---

## 八、多模态 + 降级

### Q: 图片识别三级降级

```
L0: Qwen-VL 真实推理 → L1: Mock视觉解析 → L2: 纯文本模式
```

每级记录 `fallback_status`（level + attempts + description）。Visual Agent 输出 specs 为列表时自动 join 为字符串（适配 Qwen-VL 返回格式变化）。

### Q: Visual Evidence Grounding

Visual Agent 的每个字段（商品名/品牌/品类/规格×颜色/容量...）绑定独立 `evidence_id`（如 `V-p001-specs-颜色`），实现字段级视觉证据可追溯。

---

## 九、Skill Registry + ToolManager

### Q: Skill 和 Tool 什么关系？

| 概念 | 粒度 | 示例 |
|------|------|------|
| Skill | 组合能力（编排多个 Tool） | product_retrieve = text_search + vector_search + structured_filter |
| Tool | 原子能力 | product_text_search（jieba关键词检索） |

### Q: 安全机制

- Manifest 强制（input/output schema + permission_level + risk_level）
- Agent 权限检查（`can_agent_use(tool, agent)`）
- V1 只读强制（`permission_level != "read"` 直接拒绝）
- ToolCallRecord 全量记录（call_id/tool/agent/latency/status）

---

## 十、标准 MCP Server/Client（Agent 领域核心考点）

### Q: 什么是 MCP（Model Context Protocol）？

MCP 是 Anthropic 于 2024 年底发布的开放标准协议，定义了 AI 应用与外部工具/数据源之间的统一通信方式。可以类比为 **LLM 世界的 USB-C 接口** — 任何 MCP Server 暴露的工具，任何 MCP Client（Claude Desktop、Cursor、VS Code 等）都能即插即用。

### Q: MCP 的架构模型

```
┌──────────────────────┐
│   MCP Client         │  Claude Desktop / Cursor / VS Code / 自定义App
│   (Host)             │
└──────┬───────────────┘
       │ JSON-RPC 2.0
       │ over stdio / SSE
┌──────▼───────────────┐
│   MCP Server         │  OmniCart Agent
│                      │
│  ┌─── Tool 1: product_text_search
│  ├─── Tool 2: product_detail
│  ├─── Tool 3: review_search
│  ├─── Tool 4: policy_lookup
│  ├─── Tool 5: compatibility_check
│  ├─── Tool 6: structured_filter
│  ├─── Tool 7: decision_score
│  └─── Tool 8: list_categories
└──────────────────────┘
```

**三大核心概念：**

| 概念 | 说明 | OmniCart 实现 |
|------|------|-------------|
| **Tools** | 可被 LLM 调用的函数，有明确的输入 Schema 和输出格式 | 8 个购物工具，每个都有 `inputSchema` JSON Schema 定义 |
| **Resources** | 可被 LLM 读取的数据源（文件、数据库等） | 商品数据集（100+ 件）、评论、政策 FAQ |
| **Prompts** | 预定义的 Prompt 模板 | 购物推荐、风险检查、兼容性检查等场景 Prompt |

### Q: MCP 的通信协议

```
Client                          Server
  │                                │
  │── initialize ────────────────→│  握手：交换能力描述
  │←─ capabilities ──────────────│
  │                                │
  │── tools/list ────────────────→│  列出所有可用工具
  │←─ [Tool, Tool, ...] ─────────│
  │                                │
  │── tools/call ────────────────→│  调用具体工具
  │   {"name":"product_text_search",│
  │    "arguments":{"query":"蓝牙耳机"}}│
  │←─ {"total":3, "products":[...]}│
  │                                │
```

基于 **JSON-RPC 2.0**，所有消息都是结构化的请求/响应。传输层支持两种模式：

| 传输方式 | 适用场景 | OmniCart 支持 |
|----------|---------|-------------|
| **stdio** | Claude Desktop 等本地客户端 | ✅ `python -m app.mcp.server` |
| **HTTP/SSE** | 浏览器端、Web 客户端 | ✅ `python scripts/run_mcp_server.py --http --port 8007` |

### Q: 为什么 MCP 是 Agent 领域重点？

1. **互操作性**：不同团队开发的工具可以通过统一协议被任何 LLM 调用，避免厂商锁定
2. **安全边界**：工具执行在 Server 端完成，Client 只看到声明的 Schema，无法越权
3. **可组合性**：多个 MCP Server 可以叠加，LLM 同时拥有文件系统、数据库、API 等多种工具
4. **标准化**：取代了早期每个 Agent 框架各自定义 Tool Schema 的碎片化局面

### Q: OmniCart 的 MCP 实现架构

```
backend/app/mcp/
├── __init__.py         模块入口
├── server.py           MCP Server 核心（stdio + SSE 双传输）
├── tools.py            8 个 Tool 定义 + handler 实现
└── __main__.py         python -m 入口（Claude Desktop 用）

scripts/
├── run_mcp_server.py   启动脚本（--http 切换传输模式）
└── test_mcp.py         8 Tool 连通性测试
```

### Q: 和之前的 ToolManager 什么关系？

| 维度 | 旧 ToolManager（MCP-compatible） | 新 MCP Server（标准协议） |
|------|------|------|
| 协议 | 自定义 Python API | JSON-RPC 2.0 标准协议 |
| Schema | Pydantic `ToolManifest` | JSON Schema（MCP 标准格式） |
| 传输 | 仅内部调用 | stdio + SSE/HTTP 双模式 |
| 互操作 | 只能 OmniCart 自己用 | Claude Desktop / Cursor / VS Code 均可接入 |
| 工具数量 | 8 个 | 8 个（功能完全一致） |

**两者共存不冲突**：`ToolManager` 是内部实现细节（Agent Workflow 内调用），MCP Server 是对外标准接口（外部 LLM 客户端接入）。

### Q: Tool Schema 示例

```json
{
  "name": "product_text_search",
  "description": "使用 jieba 中文分词 + 关键词匹配检索商品",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string", "description": "搜索关键词"},
      "category": {"type": "string", "description": "品类过滤"},
      "top_k": {"type": "integer", "default": 10},
      "price_max": {"type": "number"},
      "price_min": {"type": "number"}
    },
    "required": ["query"]
  }
}
```

### Q: 怎么验证 MCP 工具可用？

```bash
# 快速测试所有 8 个工具
python scripts/test_mcp.py

# 输出示例：
#   [PASS] product_text_search({"query": "蓝牙耳机", "top_k": 3})
#   [PASS] product_detail({"product_id": "p_digital_007"})
#   [PASS] decision_score({"product_id": "p_digital_026", "budget_max": 200})
#   8/8 tools passed
```

### Q: Claude Desktop 如何接入 OmniCart MCP？

在 Claude Desktop 配置文件中添加：

```json
{
  "mcpServers": {
    "omnicart": {
      "command": "python",
      "args": ["-m", "app.mcp.server"],
      "cwd": "/path/to/OmniCart-Agent/backend"
    }
  }
}
```

配置后，Claude Desktop 启动时自动连接 OmniCart MCP Server，可以直接调用 8 个购物工具查询商品、对比评分、检查兼容性。

### Q: MCP Server 代码核心实现

```python
# backend/app/mcp/server.py — 核心 20 行
from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.types import Tool
from app.mcp.tools import TOOL_DEFINITIONS, handle_tool

server = Server("omnicart-agent")

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [Tool(**td) for td in TOOL_DEFINITIONS]

@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    result = await handle_tool(name, arguments)
    return [TextContent(type="text", text=result)]

# stdio 模式启动
async with stdio_server() as (read, write):
    await server.run(read, write, capabilities)
```

### Q: 答辩可能追问

**Q: 为什么不用 LangChain Tool 而是 MCP？**

LangChain Tool 是 LangChain 生态内部的概念，换到 LlamaIndex/AutoGen 就不能用了。MCP 是**生态无关**的开放标准，任何支持 JSON-RPC 的客户端都能接入。

**Q: 8 个工具够吗？**

比赛阶段 8 个工具覆盖了商品搜索、详情查看、评分分析、政策查询、兼容性检查等核心购物决策链路。标准协议的优势在于：需要新工具时只需加一个 Tool 定义和 handler，不改协议。

**Q: MCP 和 A2A（Agent-to-Agent）的区别？**

| MCP | A2A |
|-----|-----|
| LLM ↔ 工具/数据 | Agent ↔ Agent |
| 暴露能力（Tools） | 委托任务（Tasks） |
| JSON-RPC over stdio/SSE | JSON-RPC over HTTP |
| Claude 主导 | Google 主导 |

两者互补：MCP 管"用什么工具"，A2A 管"多个 Agent 怎么协作"。OmniCart 两套都做了（MCP 标准协议 + A2A-lite）。

---

## 十一、State Checkpoint + Decision Harness + Evidence Graph

### Q: Checkpoint 做什么？

JSON 文件持久化 8 节点状态 → 支持 resume（断点续跑）、replay（链路回放）、export（Demo Pack 导出）。

### Q: Harness 7 项校验

schema_valid / evidence_bound / score_recalculable / policy_cited / risk_warning / sufficiency_check / no_empty_answer

Android HarnessTab 智能展示：布尔值 ✅/❌，列表显示条目数+内容，嵌套字典展开子项。

### Q: Evidence Graph

NetworkX 商品-证据-风险图关系。`get_supporting_evidence(product_id)` / `get_risk_tags(product_id)` / `get_evidence_path(from, to)`。无 NetworkX 时优雅降级。

---

## 十二、Android 客户端全景

### Q: 四 Tab + 子页面

| Tab | 子页面 | 关键能力 |
|-----|--------|---------|
| 商品 | 品类筛选 + 商品列表 + 商品详情弹窗 6 Tab | 推荐/证据/评分/链路/技能/验证 |
| **豆仔** | 多轮对话 + 图片上传 + 加购 + Agent洞察10Tab | LLM改写检索 + 闲聊模式 + 自动滚动 + ⭐Agent洞察 |
| 购物车 | 增删改查 + 全选/多选 + 模拟结算 | 商品快照 + cartRefreshKey + LaunchedEffect |
| 我的 | 登录/注册 + 地址管理 + 偏好设置 | AuthManager + Token拦截器 + 默认地址互斥 |

### Q: 豆仔页面交互

- **文本输入**：LLM 查询改写 → 精准检索 → 7 维评分 → 证据绑定回答 → ProductCard + ProductDetailSheet（点击卡片）
- **图片识别**：Photo Picker → Qwen-VL → 三级降级 → 增强文字查询 → 卡片始终有加购按钮
- **闲聊模式**：自动检测 16 个闲聊词 → 跳过检索 → 纯文字友好回复 → 6 类模板兜底
- **Agent 洞察**：顶栏 ⭐ → AgentInsightSheet → 10 个 Tab（上下文/检索计划/证据图/降级/工具/反事实/视觉绑定/偏好/基准/摘要）
- **Demo 模式**：一键展示完整证据+链路+Harness+评分面板数据
- **自动滚动**：新消息自动滚动到底部
- **键盘**：imePadding() 根 Box 层无缝推升

### Q: ProductDetailSheet 6 Tab

推荐 → 证据列表 → 评分细分 → Agent 链路 → Skill 技能 → Harness 验证 ✅/❌

### Q: AgentInsightSheet 10 Tab（V1-Plus）

上下文 → 检索计划 → 证据图 → 降级状态 → 工具治理 → 反事实推荐 → 视觉绑定 → 偏好记忆 → 基准评测 → 摘要

---

## 十三、Counterfactual + Knowledge Index（进阶）

### Q: 0 结果时怎么办？

`CounterfactualRecommender` 三级建议：
```
结果=0 → 放宽预算 + 放宽品类 + 去除标签 + 重新措辞
结果≤2 → 展示热门 + 标注"不完全匹配"
结果≥3 → 正常展示
```

### Q: Knowledge Index 做什么？

250+ 关键词→品类映射 + 品类→子品类→品牌→商品 4 级分层。Router 意图识别和检索品类过滤的加速索引。

---

## 十四、Mock Mode / Demo Pack

### Q: 一键 Demo 怎么工作？

- Android Demo Mode 开关 → `MockDemoData` 提供完整预置数据：2 商品 + 2 决策结果 + 4 证据 + 7 条 Trace + 完整 Harness + AgentInsightSheet 全部数据
- 后端 Mock Mode：`.env` 中 `OMNICART_MOCK_MODE=true` → 所有 LLM 调用返回预置结果
- Demo Pack 导出：`scripts/export_demo_pack.py` — 4 场景（蓝牙耳机/防晒霜/跑步鞋/咖啡）

---

## 十五、Redis 四级缓存体系（新增 V2 基础设施）

### Q: 为什么需要缓存？

OmniCart 全链路涉及 3 次 LLM API 调用（Qwen-VL 视觉解析 + Qwen Chat 查询改写 + Qwen Chat 回答生成）+ 向量检索 + RRF 融合 + Rerank 精排，一次请求延迟 3-10 秒。相同图片/查询反复发时，每次重算浪费 API 调用量且影响用户体验。

### Q: 四级缓存架构

```
用户请求
  │
  ├─ L1: Workflow 全链路缓存   TTL 5min   key=MD5(query+image)
  │   └─ 命中 → 直接返回完整推荐结果，跳过全部 8 个 Agent 节点
  │
  ├─ L2: Visual 视觉解析缓存   TTL 1h     key=MD5(图片MD5+query)
  │   └─ 命中 → 跳过 Qwen-VL API 调用（最贵操作，2-5s→0ms）
  │
  ├─ L3: LLM 查询改写缓存      TTL 30min  key=MD5(原始查询)
  │   └─ 命中 → 跳过 Qwen Chat 调用，"推荐蓝牙耳机"→"蓝牙耳机" 确定性映射
  │
  └─ L4: 文本检索缓存          TTL 5min   key=MD5(查询+品类+价格+top_k)
      └─ 命中 → 跳过 jieba+Qdrant+Embedding 全流程，200-1000ms→0ms
```

### Q: 缓存键设计

| 层级 | Key 模式 | TTL | 设计理由 |
|------|----------|-----|---------|
| L1 Workflow | `omnicart:workflow:{md5(query+image)}` | 5min | 完整结果不变，短期有效 |
| L2 Visual | `omnicart:visual:{md5(图片MD5+query前80字)}` | 1h | 商品图不会变，最稳定 |
| L3 Rewrite | `omnicart:rewrite:{md5(原始查询)}` | 30min | 同查询→同关键词 |
| L4 Search | `omnicart:search:{md5(query+品类+价格区间+top_k)}` | 5min | 商品库相对稳定 |

关键设计：Visual 层用**图片内容 MD5**而非 URL，因为同一张图可能走不同路径上传。

### Q: 核心实现 — get-or-compute 模式

```python
# backend/app/core/cache.py — 核心 15 行
async def cached(key: str, ttl: int, factory: Callable) -> Any:
    redis = await get_redis()
    if redis is None:               # Redis 不可用 → 透明跳过
        return await factory()

    raw = await redis.get(key)      # 查缓存
    if raw is not None:
        _stats["hits"] += 1          # 命中
        return json.loads(raw)

    _stats["misses"] += 1
    result = await factory()        # 未命中 → 调真实逻辑
    await redis.setex(key, ttl, json.dumps(result))  # 异步写入
    return result
```

**设计要点**：
- `factory` 是 async callable，只在 cache miss 时调用 — 零预热、零空跑
- Redis 连接失败 → `get_redis()` 返回 `None` → 直接调 factory — 完全不影响业务
- `json.dumps(result, default=str)` 兼容任何 Pydantic/ORM 对象序列化

### Q: Visual Agent 缓存接入（最贵操作优化）

```python
# backend/app/agents/visual_agent.py — parse() 改为 async
async def parse(self, image_url: str, user_query: str = "") -> VisualResult:
    image_bytes = filepath.read_bytes()
    img_hash = hashlib.md5(image_bytes).hexdigest()[:12]  # 图片指纹
    cache_key = make_key("visual", img_hash, user_query[:80])

    async def _do_parse():
        # 原始 Qwen-VL API 调用逻辑（不变）
        raw = self._gateway.vision(...)
        return self._parse_json(raw)

    return await cached(cache_key, REDIS_CACHE_TTL_VISUAL, _do_parse)
```

`parse()` 从同步改为 async，调用方（graph.py / recommend.py）统一用 `await`。LangGraph 从 `invoke()` 改为 `ainvoke()` 以支持异步节点，可与同步节点混合编排。

### Q: 优雅降级策略

```
.env 中 REDIS_URL 留空
  → USE_REDIS = False
  → get_redis() 直接返回 None
  → 所有 cached() 调用直接执行 factory
  → 业务逻辑不受任何影响
  → 日志：Redis disabled — no performance boost

Redis 中途宕机
  → redis.get() / redis.setex() 抛异常
  → except 捕获 → 返回 factory() 结果
  → 写入失败 → 日志记录，下次请求仍 miss
  → 不抛异常到上层

Redis 恢复
  → 下次请求自动重连
  → 冷启动 → 逐步填充缓存
```

**零破坏原则**：缓存层对业务完全透明，Redis 不存在或不稳定的情况下，系统行为与未加缓存时完全一致。

### Q: 命中率监控

```bash
# 实时查看缓存统计
curl http://localhost:8006/api/cache/stats
# → {"redis": true, "stats": {"hits": 142, "misses": 38, "hit_rate": 0.789}}
```

`/api/cache/stats` 端点内置在 health 模块中，返回 Redis 连接状态 + 命中/未命中计数 + 命中率，无需额外监控面板。

### Q: 连接管理

- **连接池**：`redis.asyncio.from_url(url, max_connections=20)`，复用连接不频繁握手
- **超时**：`socket_connect_timeout=2, socket_timeout=2`，2 秒连不上视为不可用
- **生命周期**：FastAPI startup → `init_redis()`，shutdown → `close_redis()`，跟随应用启停
- **序列化**：`decode_responses=True` + JSON，人类可读，方便 `redis-cli` 直接调试

### Q: TTL 为什么这样定？

| 层级 | TTL | 决策依据 |
|------|-----|---------|
| Visual | 3600s (1h) | 商品图片是静态资源，更改频率极低 |
| Search | 300s (5min) | 商品库不会频繁变更，但 5 分钟容忍新增/调价 |
| Rewrite | 1800s (30min) | 同查询→同关键词是确定性映射，半小时内完全可复用 |
| Workflow | 300s (5min) | 包含多种子结果，TTL 不宜过长以保证新鲜度 |

所有 TTL 可通过 `.env` 环境变量单独配置，无需改代码。

### Q: 为什么不用内存缓存（functools.lru_cache）？

| 维度 | Redis | LRU 内存缓存 |
|------|-------|-------------|
| 跨请求共享 | ✅ 所有 worker/进程共享 | ❌ 进程隔离，命中率低 |
| 持久化 | ✅ 重启不丢失 | ❌ 重启清空 |
| 内存管理 | Redis 独立内存，不抢应用 | 和应用抢内存 |
| 分布式 | 天然支持多实例 | 不支持 |
| 监控 | redis-cli / MONITOR 命令 | 无 |

参赛项目用 Redis 也体现工程素养，比 `lru_cache` 更专业。

### Q: async 改造的范围

原系统中 `visual_agent.parse()`、`retrieval_agent.execute()`、`text_retriever.search()` 等核心方法均为同步。为接入 async Redis 缓存，做了最小化 async 改造：

| 方法 | 原 | 改后 | 影响范围 |
|------|----|------|---------|
| `VisualAgent.parse()` | sync | async | graph.py 节点 + recommend.py |
| `RetrievalAgent._llm_extract_keywords()` | sync | async | retrieval_agent 内部 |
| `RetrievalAgent.execute()` | sync | async | graph.py 节点 |
| `TextRetriever.search()` | sync | async | retrieval_agent + recommend.py |
| `TextRetriever.hybrid_search()` | sync | async | retrieval_agent + baseline 脚本 |
| `run_workflow()` | async→`invoke` | async→`ainvoke` | recommend.py v2 端点 |

LangGraph 支持 sync/async 节点混合编排 — Router、Decision、Response 等节点保持同步不变。31 个单元测试全部适配 `@pytest.mark.asyncio`，0 失败。

---

## 十六、全链路数据流（最新版）

```
1. 用户输入"推荐一款500以内的降噪蓝牙耳机"或拍照上传
2. [Redis L1] Workflow 缓存检查 → 命中直接返回
3. Router Agent → 闲聊检测(16词) or 购物意图(6种)，约束抽取
4. PreferenceMemory → 合并/清除历史偏好（话题切换自动清除）
5. [可选] Visual Agent → [Redis L2] 图片缓存检查 → Qwen-VL → 三级降级
6. Retrieval Agent → [Redis L3] LLM改写缓存检查 → 关键词提取
   ├─ Text: [Redis L4] 检索缓存检查 → Qdrant 1024d ANN + jieba RRF k=60
   ├─ Review: ≤2★差评 + ≥4★好评 → 证据
   └─ Policy: FAQ关键词匹配 → 证据
7. Reranker → Qwen3-Rerank 语义精排（失败保持原序）
8. Evidence Checker → 按intent检查证据充足性 → sufficiency_report
9. Decision Agent → 硬约束过滤 + 7维评分 + 风险标签 + evidence绑定
10. Context Compiler → 编译结构化上下文（含Counterfactual反事实建议）
11. Response Agent → 闲聊独立Prompt or 购物LLM回答生成 + 模板兜底
12. Response Guard → 5项守门验证 → guard_warnings
13. Decision Harness → 7项统一校验 → harness_report
14. State Checkpoint → JSON文件持久化guard节点
15. Android展示: MessageBubble + ProductCard(始终有加购按钮) + ProductDetailSheet(6Tab) + AgentInsightSheet(10Tab)
```

---

## 十七、LLM 全链路可观测性（新增 V2 基础设施）

### Q: 这个功能做什么？

Gateway 是全部 LLM 调用的唯一瓶颈（chat / vision / embed / rerank），在每个调用入口自动记录完整追踪数据，无需业务代码改动。

### Q: 记录什么数据？

每条 LLM 调用记录 13 个字段：

| 字段 | 来源 | 示例 |
|------|------|------|
| span_id / trace_id | 自动生成 | `a1b2c3d4e5f6` |
| name | 调用类型 | `qwen.chat` / `qwen.vision` / `qwen.embed` / `qwen.rerank` |
| capability | 能力名 | `intent_understanding` / `visual_understanding` |
| model | 模型名 | `qwen-plus` / `qwen-vl-plus` |
| system_prompt / user_prompt | 完整的 prompt（截断 4000 字符） |
| response | 完整响应（截断 4000 字符） |
| tokens_input / tokens_output | 从 API usage 提取，不可用时字符数/3.5 估算 |
| latency_ms | `time.perf_counter()` 精确计时 |
| status | `success` / `error` / `mock` / `fallback` |
| mock_mode | 是否为 Mock 数据 |
| timestamp | ISO 8601 时间戳 |

### Q: 存储与查询

- **存储**：`data/traces/traces-{date}.json`，按日期分文件，单文件 500 条自动轮转
- **写入**：异步缓冲（10条或30秒刷新），不阻塞 LLM 调用
- **列表查询**：`GET /api/observability/traces?limit=50&name=qwen.chat&status=error`
- **单条查询**：`GET /api/observability/traces/{span_id}`
- **聚合统计**：`GET /api/observability/stats?hours=24` → 总调用次数、token 消耗、P50/P95 延迟、错误率、按 capability/model 分组
- **清除**：`DELETE /api/observability/traces?before=2026-05-23T00:00:00`

### Q: 追踪失败会影响业务吗？

不会。`Gateway._trace()` 中所有异常静默捕获，追踪记录失败不会抛出到上层。这是在 Gateway 方法最后的 `finally` 逻辑中以 `try/except` 保护的。

### Q: 怎么接入的？

四个 Gateway 方法改为 async，在每个方法内统一调用 `await self._trace(...)`：

```python
async def chat(self, capability, prompt, system=""):
    t0 = time.perf_counter()
    try:
        response = real_chat_logic(...)
        await self._trace(name, capability, model, system, prompt, response,
                          t0, status="success")
        return response
    except Exception as e:
        await self._trace(name, capability, model, system, prompt, "", t0,
                          status="error", error=str(e))
        raise
```

业务代码零改动 — Router / Retrieval / Response Agent 原本就调 `gateway.chat()`，现在自动被追踪。

### Q: 追踪数据示例

```json
{
  "span_id": "a1b2c3d4e5f6",
  "trace_id": "f6e5d4c3b2a1",
  "name": "qwen.chat",
  "capability": "intent_understanding",
  "model": "qwen-plus",
  "system_prompt": "你是一个购物决策路由Agent...",
  "user_prompt": "推荐一款500以内的蓝牙耳机",
  "response": "{\"intent\": \"recommend\", \"category\": \"数码电子\"...}",
  "tokens_input": 245,
  "tokens_output": 128,
  "latency_ms": 342,
  "status": "success",
  "mock_mode": false,
  "timestamp": "2026-05-23T14:30:00"
}
```

### Q: 统计示例

```json
{
  "window_hours": 24,
  "total_calls": 156,
  "errors": 3,
  "error_rate": 0.0192,
  "mock_calls": 0,
  "tokens_input": 45890,
  "tokens_output": 12450,
  "tokens_total": 58340,
  "latency_avg_ms": 312,
  "latency_p50_ms": 280,
  "latency_p95_ms": 850,
  "by_capability": {"chat_generation": 98, "intent_understanding": 42, "visual_understanding": 16},
  "by_model": {"qwen-plus": 140, "qwen-vl-plus": 16}
}
```

---

## 十八、关键 Bug 及修复（答辩时可展示工程能力）

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| 1 | "买鞋"搜不到鞋 | jieba"买鞋"一词0匹配 | LLM查询改写 + 单字拆分兜底 |
| 2 | 拍照识图 500 错误 | Qwen-VL specs 返回 list，schema 要求 str | visual_agent join 列表转字符串 |
| 3 | 拍照商品无加购按钮 | 按钮在 decisionResult?.let 块内 | 移到外部始终渲染 |
| 4 | 面板点击闪退 | LazyColumn 嵌套 | 内层改为 Column + for 循环 |
| 5 | 键盘上升有空白 | imePadding 位置不当 | 移到根 Box 层 |
| 6 | 注册 422 | password min_length=4 | 改为 1 |
| 7 | Harness 全部 ❌ | 列表/字典值被 Boolean 判断误判 | 按类型分渲染 |
| 8 | sync-async 桥接 | LangGraph 同步 + SQLAlchemy async | nest_asyncio 嵌套事件循环 |
| 9 | 话题切换品类残留 | merge_constraints 操作副本 | 同时清除原始 session 数据 |
| 10 | 购物车切换不刷新 | restoreState=true 冲突 | cartRefreshKey + LaunchedEffect |

---

## 十九、常见追问

### Q: 怎么保证推荐不是胡说？

四层保障：evidence_ids 绑定 → 硬约束过滤(LLM不参与) → Response Guard 5项守门 → Decision Harness 7项校验。

### Q: 和普通导购的区别

| 普通 | OmniCart |
|------|---------|
| 黑盒 | 7维可解释 + evidence溯源 + 风险标签 |
| 单一文本 | 多模态RAG(文本+图片+评论+政策+向量) |
| 单次问答 | 8节点 Multi-Agent + trace_steps + checkpoint |
| 无法验证 | Guard + Harness + 闲聊检测 |
| 无记忆 | 多轮偏好 + 话题切换 + REST API |

### Q: 系统局限性

1. 100 件商品规模（但有 Counterfactual 兜底 + 4 级分层索引）
2. Qwen-VL 中文匹配有落差（Visual Grounding 缓解 + LLM 改写增强）
3. session 级记忆（V2 跨会话长期偏好）
4. 嵌入 API 依赖云端（降级为 jieba + 单字拆分，基本可用）

---

## 二十、技术亮点总结（答辩收尾）

| # | 亮点 | 一句话 |
|---|------|--------|
| 1 | LLM 查询改写 | Qwen 口语→搜索关键词 + jieba 单字兜底，精准命中 |
| 2 | 闲聊模式 | 16 词检测 → 跳过检索 → 6 类模板，纯文字友好交互 |
| 3 | 双库降级 | PG+Qdrant 填串即用，留空回退 JSON+jieba，零破坏 |
| 4 | RRF 混合检索 | 语义向量 + 关键词双重召回，任一通道失败自动降级 |
| 5 | 6 类仓库工厂 | ABC + PG/内存双模 + 工厂注入，测试/开发/生产即时切换 |
| 6 | 可解释决策 | 7 维评分 + evidence_ids 溯源 + 风险标签 + 进度条可视化 |
| 7 | 规则优先 LLM | 品类/预算/意图以规则为准，防幻觉 |
| 8 | Skill+Tool 双层 | 8 Skill(组合) + 8 Tool(原子) + Manifest + V1 只读 |
| 9 | Harness 7 项校验 | schema/证据/评分/政策/风险/充足性/非空 自动验证 |
| 10 | Checkpoint 持久化 | 8 节点 JSON 文件，支持 resume/replay/export |
| 11 | 三级多模态降级 | L0 Qwen-VL → L1 Mock → L2 纯文本 |
| 12 | Counterfactual | 0 结果时智能建议放宽约束 |
| 13 | Android 面板体系 | 6Tab(商品) + 10Tab(Agent洞察) + Demo 一键展示 |
| 14 | 用户体系完整 | 注册/登录/地址/偏好 + Token + 默认地址互斥 |
| 15 | sync-async 桥接 | nest_asyncio 让同步 Agent 调异步 PG/Qdrant |
| 16 | 闲聊+购物双模 | 日常对话不推商品，购物意图精准推荐 |
| 17 | Visual Grounding | 字段级视觉证据绑定，像素到数据可追溯 |
| 18 | **Redis 四级缓存** | Visual/Search/Rewrite/Workflow 四级加速，首次后秒开，Redis 不可用自动降级 |
| 19 | **LLM 可观测性** | Gateway 全量追踪 + token 统计 + P50/P95 延迟 + 错误率，零业务侵入 |
| 20 | **标准 MCP Protocol** | 8 Tool JSON-RPC 2.0 + stdio/SSE 双传输 + Claude Desktop/Cursor 可接入 |

---

## 附录：核心代码索引

### 工作流
| 文件 | 职责 |
|------|------|
| `workflow/graph.py` | 8 节点 LangGraph + chitchat 边缘 |
| `workflow/checkpoint.py` | State Checkpoint JSON 持久化 |
| `workflow/workflow.yaml` | 声明式配置 |

### Agent
| 文件 | 职责 |
|------|------|
| `agents/router_agent.py` | 意图识别(6种) + 约束 + 闲聊检测(16词) |
| `agents/visual_agent.py` | Qwen-VL 解析 + specs list→str |
| `agents/retrieval_agent.py` | LLM 查询改写 + 三通道并行 |
| `agents/decision_agent.py` | 硬约束 + 7 维评分 |
| `agents/response_agent.py` | 闲聊 Prompt + 购物 Prompt + 6 类模板 |

### 检索
| 文件 | 职责 |
|------|------|
| `retrieval/text_retriever.py` | HybridSearch(Qdrant+jieba RRF) + 单字拆分 |

### 基础设施
| 文件 | 职责 |
|------|------|
| `core/redis_client.py` | Redis 连接池管理 + 健康检查 + 生命周期 |
| `core/cache.py` | 四级缓存核心: get-or-compute + 命中率统计 + 批量失效 |
| `observability/collector.py` | LLM 全链路追踪: TraceCollector + LLMSpan + 本地 JSON 存储 |
| `api/observability.py` | 可观测性 API: 追踪查询 + 聚合统计 + 数据清除 |
| `mcp/server.py` | 标准 MCP Server: stdio + SSE/HTTP 双传输, JSON-RPC 2.0 |
| `mcp/tools.py` | 8 个 MCP Tool: 定义(JSON Schema) + Handler + 连通性测试 |
| `scripts/run_mcp_server.py` | MCP Server 启动脚本: --http 切换 SSE 模式 |
| `scripts/test_mcp.py` | 8 个 MCP Tool 全量连通性测试 |
| `skills/registry.py` | Skill Registry 8 Skill |
| `tools/manager.py` | ToolManager 8 Tool + 权限 + V1 只读 |
| `graph/evidence_graph.py` | NetworkX 证据图 |
| `vision/visual_grounding.py` | 字段级视觉证据绑定 |
| `vision/multimodal_fallback.py` | 三级降级 |
| `decision/counterfactual.py` | 反事实建议 |
| `indexing/category_index.py` | 4 级分层品类索引 |
| `harness/decision_harness.py` | 7 项校验框架 |
| `a2a/dispatcher.py` | AgentMessage/Artifact 分发 |
| `memory/preference_memory.py` | 多轮记忆 + 话题切换 |

### Android
| 文件 | 职责 |
|------|------|
| `MainScreen.kt` | 四 Tab + NavHost(10 路由) |
| `feature/chat/ChatScreen.kt` | 豆仔对话 + 面板 + 键盘 + 自动滚动 |
| `feature/product/ProductCard.kt` | 卡片 + 评分 + 加购(始终显示) |
| `feature/product/ProductDetailSheet.kt` | 6 Tab 详情弹窗 |
| `feature/panel/AgentInsightSheet.kt` | V1-Plus 10 Tab Agent 洞察 |
| `feature/auth/*` | 登录/注册 + AuthManager |
| `feature/address/*` | 地址管理 CRUD |
| `feature/preference/*` | 偏好设置 |
| `feature/demo/MockDemoData.kt` | 一键 Demo 预置数据 |
| `core/network/OmniCartApi.kt` | 26+ API 端点 + 数据类 |
