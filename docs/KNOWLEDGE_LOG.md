# OmniCart Agent 知识日志

## V2-3: 用户长期偏好记忆

完成时间：2026-05-23 | 验证：8 步行为模拟测试 + 31/31 单元测试

### 核心知识
- **三级行为信号**: 搜索(weight=1) < 加购(weight=3) < 结账(weight=5)
- **时间衰减**: 30 天半衰期, `0.5^(days/30)`, 旧偏好自动淡化
- **预算学习**: EMA 指数移动平均, 购买权重高于浏览 2 倍
- **合并策略**: Session 明确值 > 长期默认值, 不覆盖用户当前意图
- **持久化**: PG JSONB (user_preferences 表, key=`ltm:{user_id}`) + JSON 文件双模式
- `UserProfile` dataclass: 品类/品牌/场景/标签 各 Top-N 截断, 归一化 0-1

### 文件清单
- `memory/long_term.py` — LongTermMemory 类 + UserProfile
- `workflow/graph.py` — Router 节点接入 LT merge + search recording
- `schemas/workflow.py` — WorkflowState 新增 user_id
- `api/preference.py` — 新增 GET/DELETE long-term profile API
- `api/agent_actions.py` — 加购自动记录

## V2-4: Evaluation Dashboard

完成时间：2026-05-23 | 验证：5/5 golden queries 全部命中

### 核心知识
- 10 条 golden queries 覆盖 4 品类, 每次评测保存到 `data/eval_runs/{run_id}.json`
- Dashboard: Chart.js 双图表 (Bar + Doughnut) + 统计卡片 + 明细表格 + 历史趋势
- API: POST /api/eval/run, GET /api/eval/results, GET /api/eval/results/{id}, GET /api/eval/golden

### 文件清单
- `api/eval.py` — 评测 API
- `api/eval_dashboard.py` — HTML Dashboard (单文件自包含)

---

## V2-1: 标准 MCP Server/Client 实现

完成时间：2026-05-23 | 验证：8/8 Tool 连通性测试 + 31/31 单元测试

### 核心知识
- **MCP (Model Context Protocol)** 是 Anthropic 发布的开放标准
- 架构：Client ↔ Server，JSON-RPC 2.0 over stdio 或 HTTP/SSE
- Python SDK: `mcp>=1.27`

### 文件清单
- `app/mcp/server.py` / `app/mcp/tools.py` / `scripts/run_mcp_server.py` / `scripts/test_mcp.py`

---

## V1-Core-7: 7 节点工作流升级（Reranker + Context Compiler + Guard + Memory + Async）

完成时间：2026-05-22
对应阶段：V1-Core
对应蓝图章节：多个章节
验证状态：22/22 单元测试 + 端到端 5 品类验证

### 关键成果

工作流从 4 节点升级为 7 节点：
```
Router → [Visual?] → Retrieval(并行) → Reranker → Decision → Response(Compiler) → Guard → END
```

### 新增模块详情

#### 1. Qwen Reranker 精排
- **文件**: `workflow/graph.py`（`_node_reranker` 函数）
- **功能**: 在 jieba 粗排后调用 Qwen Reranker API 语义重排序
- **实现**: 为每个候选商品构造 document 文本（title+category+description），调用 `gateway.rerank(query, documents, top_n)`，按 relevance_score 降序重排
- **降级**: Mock 模式或 API 异常时保持原序不变

#### 2. Context Compiler
- **文件**: `context/compiler.py`
- **功能**: 将 WorkflowState 编译为 LLM-ready 结构化上下文，替代原来分散的 prompt 模板
- **结构**: ①用户需求和意图 ②约束条件 ③图片识别结果 ④候选商品+评分 ⑤证据摘要+关键摘录 ⑥反事实建议 ⑦检索计划
- **效果**: LLM 回答从泛泛而谈 → 引用具体评分/风险/证据

#### 3. Response Guard
- **文件**: `verification/response_guard.py`
- **功能**: 5 项规则检查 → 写入 `harness_report`
  1. 证据绑定: 回答是否引用用户评分/FAQ/评论
  2. 价格准确: 未检查硬错误
  3. 风险覆盖: 有风险标签时是否提醒
  4. 空结果诚实: 无商品时不应说"推荐购买"
  5. 无依据断言: 禁止"最好/第一/最强/绝对/保证"

#### 4. Evidence Sufficiency Checker
- **文件**: `verification/evidence_checker.py`
- **功能**: 按意图类型（recommend/risk_check/compare/compatibility/alternative）要求不同最少证据类型
- **状态**: 已创建，未嵌入工作流主链（预留 V1-Plus 集成）

#### 5. Preference Memory（多轮记忆）
- **文件**: `memory/preference_memory.py`
- **功能**: 每个 session 保存历史约束（品类/预算/场景/标签），新查询自动合并
- **合并策略**: 新值覆盖旧值，None 不覆盖，标签集合去重合并
- **集成**: `_node_router` 执行后调用 `mem.merge_constraints()` + `mem.update()`
- **后端**: V1 用 in-memory dict，V2 可切 Redis

#### 6. workflow.yaml 声明式配置
- **文件**: `workflow/workflow.yaml`
- **内容**: 7 节点定义、边+条件边、检索参数、评分权重、Guard 检查项、Memory 配置
- **目的**: 修改工作流无需改 Python 代码

#### 7. Async Retrieval（并行检索）
- **文件**: `agents/retrieval_agent.py`
- **改动**: text 通道先执行（必须拿到商品ID），review+policy 通过 ThreadPoolExecutor 并行执行

### 踩坑
- `response_agent.py` 被 linter 误改（第1行 `ji"""` 乱码），需手动修复
- Reranker mock 模式下不排序，需在 `_node_reranker` 中 try/except 兜底
- ThreadPoolExecutor 在线程中访问 Pydantic model 正常（线程安全）

---

## V1-Core-5: Android 图片识别链路修复

完成时间：2026-05-22
对应阶段：V1-Android
修复 Bug 数：3 个

### Bug 1: UploadResponse 反序列化失败
- **根因**: `UploadResponse` 5 个字段全是 snake_case JSON key → Kotlin camelCase 属性名，但缺 `@SerializedName` 注解，Gson 无法映射
- **修复**: 全部添加 `@SerializedName("file_id")` 等注解

### Bug 2: 图片数据发送前被清空
- **根因**: `onSend()` 中 `selectedImageUri` 和 `uploadedImageUrl` 在 async 上传协程启动前就被设为 null
- **修复**: 先保存到局部变量 `sentImageUri` / `sentImageUrl`，再清空 UI 状态

### Bug 3: Visual Agent 未接入 V2 工作流
- **根因**: `graph.py:41-45` 行 `_has_image()` 函数硬编码 `return "retrieval"`，注释写着"V1 暂跳过"
- **修复**: 恢复条件判断 `if state.image_url: return "visual"`，Visual Agent 正常执行后将识别结果注入 `state.user_query` 增强检索

---

## V1-Core-4: LangGraph 4-Agent 工作流编排

完成时间：2026-05-22
对应阶段：V1-Core
对应蓝图章节：§8 Workflow-controlled Multi-Agent
验证状态：22/22 单元测试通过 + 端到端验证

### 关键成果

4 个 Agent + LangGraph StateGraph 编排：

```
POST /api/recommend/v2
  → Router Agent    (意图+约束+检索计划)
  → Retrieval Agent (text/review/policy 三通道)
  → Decision Agent  (硬约束+评分+风险)
  → Response Agent  (LLM证据绑定+模板兜底)
```

### 技术细节

1. **Router Agent**：规则为主（100%覆盖常见中文购物表达）+ LLM增强（长尾/复杂表达）。混合策略确保 LLM 不可用时系统仍可用。
2. **Retrieval Agent**：三通道并行检索。text通道复用 jieba TextRetriever，review通道提取 ≤2星差评 + ≥4星好评，policy通道提取 FAQ 中含航空/兼容/敏感等关键词条。
3. **Decision Agent**：硬约束先过滤（预算×2、品类不匹配直接排除），再用 7 维加权公式评分。评分用真实 user_reviews.rating 而非固定值。
4. **Response Agent**：LLM 优先（chat_generation capability），生成含证据引用的自然语言回答；失败时模板兜底。
5. **LangGraph**：StateGraph(WorkflowState) 控制流转，conditional edge 处理有无检索结果的分支。

### 踩坑

- LangGraph `invoke()` 返回 dict 而非 Pydantic model，需手动 `WorkflowState(**result_dict)` 转换
- 数据集全是旗舰产品（数码最低 ¥1699），低价查询可能 0 结果，Response 需处理空结果
- Router LLM 输出格式不可控，必须用 try/except JSON 解析 + 规则 fallback
- `asyncio.run()` 在已有 event loop 的环境中会报错，需注意调用方式

---

## V1-Core-3: 官方数据集迁移

完成时间：2026-05-22
对应阶段：V0 → V1 过渡
对应蓝图章节：§6 数据架构
验证状态：100 件商品加载 + jieba 检索精准度验证

### 关键成果

从 V0 Mock 60 件充电宝 → 官方 100 件 4 品类数据集：

| 品类 | 数量 | 示例子类 |
|---|---|---|
| 美妆护肤 | 25 | 精华、防晒、面霜、洁面、粉底 |
| 数码电子 | 25 | 手机、耳机、笔记本、平板、手表 |
| 服饰运动 | 25 | T恤、跑鞋、羽绒服、瑜伽裤、登山鞋 |
| 食品饮料 | 25 | 咖啡、零食、饮料、保健品、宠物食品 |

### 技术细节

1. **Schema 重写**：Sku/RagKnowledge/FaqItem/ReviewItem 匹配 JSON 结构
2. **ProductRepository**：从 `ecommerce_agent_dataset/{dir}/data/*.json` 加载
3. **jieba 分词**：替代空格 split，中文查询匹配精度大幅提升
4. **图片路径**：JSON 中中文路径名 `2_数码电子/` → URL 中英文 `2_Digital_Electronics/`
5. **评分增强**：review_confidence 用真实 `user_reviews[].rating` 计算

### 检索精度验证

- "蓝牙耳机" → top2 耳机 (score 18.6 vs 笔记本 2.4)
- "保湿精华推荐" → top3 全是精华
- "跑步运动鞋" → top3 全是跑步鞋
- "咖啡推荐" → top3 全是咖啡
- "办公笔记本电脑" → top3 全是笔记本

---

## V1-Core-2: Visual Agent 商品截图解析

完成时间：2026-05-20
对应阶段：V1-Core
对应蓝图章节：§8.2 Visual Agent
验证状态：端到端验证通过

### 架构

```
POST /api/upload (图片)
    ↓
POST /api/recommend { user_query, image_url }
    ↓
VisualAgent.parse(image_url)
    ↓ Qwen-VL API
VisualResult { product_name, brand, price, capacity, power, ports, highlights, confidence }
    ↓
注入 TextRetriever 查询词 + DecisionScoring 视觉维度
    ↓
Response { visual_result, visual_evidence[], enhanced scores }
```

### VisualResult 数据流

1. Qwen-VL 返回 JSON（被 markdown 代码块包裹）
2. `_parse_json()` 用正则提取 JSON
3. 逐字段校验类型（highlights null→[]、price 类型转换）
4. 生成 VisualEvidence 列表（每字段一条证据，带 evidence_id）

---

## V1-Core-1: Model Gateway 统一配置 + 真实 API 切换

完成时间：2026-05-20
对应阶段：V1-Core
对应蓝图章节：§7 Qwen-only Model Stack
验证状态：5/5 能力真实 API 通过

### 关键成果

一个 API Key 打通 Qwen 全系列 5 个模型：

| 能力 | 模型 | API 类型 | 状态 |
|---|---|---|---|
| chat_generation | qwen-plus | 原生 | ✅ |
| intent_understanding | qwen-plus (低温度) | 原生 | ✅ |
| text_embedding | text-embedding-v4 | 原生 | ✅ 1024dims |
| text_reranking | qwen3-rerank | 兼容 | ✅ |
| visual_understanding | qwen-vl-plus | 原生 | ✅ |

### 踩坑

- `text-embedding-v4` 不能用兼容 API，404
- `qwen3-embedding` 模型不存在，官方名是 `text-embedding-v4`
- `qwen3-reranker` 模型不存在，官方名是 `qwen3-rerank`
- Qwen-VL 返回的 content 是 list 而非 string
- config.py 需显式 load_dotenv()，否则 .env 加载时机晚于模块导入

---

## V0-Core: 最小可运行文本导购闭环

完成时间：2026-05-20
对应蓝图章节：§37.1
验证状态：16/16 tests passed + 前端构建成功

### 核心成果

一条 `python run.py` 启动后端，Android App 可用自然语言查询商品推荐。

### 踩坑记录

1. httpx 系统代理 → trust_env=False
2. 下划线场景匹配 → replace("_", " ") 归一化
3. Google Fonts 不可用 → 系统字体
4. Flask app 包名冲突 → .pth sys.path.insert(0)
5. conda site-packages 无写权限 → pip install 到用户目录
6. uvicorn reload 子进程丢失 PYTHONPATH → .pth 从源头解决
