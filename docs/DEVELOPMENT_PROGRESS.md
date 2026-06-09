# OmniCart Agent 开发进度

更新时间：2026-06-07
当前阶段：**记忆系统完整版（长期偏好画像）**
当前重点：记忆系统全链路完成 + 待用户手动测试
当前阻塞：无

## 进度总览

| 模块 | 状态 | 完成度 |
|------|------|--------|
| V0-Core | 完成 | 100% |
| V0-Android | 完成 | 100% |
| V1-Core (P0+P1+P2) | 完成 | 31/31 (100%) |
| V1-Android (P1+P2) | 完成 | 10/10 (100%) |
| V1-Plus | 完成 | 10/10 (100%) |
| V1-Android P0 (APK) | 待开始 | 0/1 |
| V2 | 完成 | 7/13 (+5 已分析跳过) |

## V2 完成清单 (7/13)

| # | 任务 | 日期 |
|---|------|------|
| 47 | **Redis 四级缓存** — Visual(1h)/Search(5min)/Rewrite(30min)/Workflow(5min) + 优雅降级 | 2026-05-23 |
| 49 | **LLM 全链路可观测性** — Gateway 全量追踪 4 方法 + Token 统计 + P50/P95 + 聚合 API | 2026-05-23 |
| 43 | **Qwen-Omni 语音导购** — ASR→Agent→TTS + Android 全屏语音 + 长按录音 + 文字清洗 | 2026-05-23 |
| 40 | **标准 MCP Server/Client** — 8 Tool JSON-RPC 2.0 + stdio/SSE 双传输 + Claude Desktop 可接入 | 2026-05-23 |
| 46 | **用户长期偏好记忆 V1** — 跨会话 UserProfile + 行为信号 + PG/JSON（已被 V2 替代） | 2026-05-23 |
| 54 | **记忆系统完整版 V2** — 一张表 user_profiles + UserProfileService + Qwen 解析 + Android 文本输入卡片 + search_hints 优化 + 推荐链路集成 | 2026-06-07 |
| 51 | **Evaluation Dashboard** — Web 可视化面板 + Chart.js + 10 golden queries + 历史趋势 | 2026-05-23 |
| 53 | **全量 Bug 修复 + 代码优化 + 测试覆盖** — 37 文件 / 5 轮迭代 / 36+ Bug 修复 | 2026-05-24 |

## V2 已分析跳过 5 项

| # | 任务 | 说明 |
|---|------|------|
| 41 | 标准 A2A Protocol | 同进程 LangGraph 不需要跨框架通信 |
| 42 | Neo4j GraphRAG | NetworkX 已足够，V3 可升级 |
| 44 | iOS SwiftUI 客户端 | 比赛交付端是 Android |
| 45 | Computer Use / Browser Use | Demo 不可控风险高 |
| 48 | 在线反馈学习 / Bandit | 可选 — 需行为数据积累 |

## V2 待完成 1 项

| # | 任务 | 说明 |
|---|------|------|
| 19 | APK Release 打包 | Release 签名 + assembleRelease |
| 50 | 大规模商品数据（1000+ 件） | 👤 队友负责 |

## V4-RAG 优化 (2026-06-02)

| # | 任务 | 说明 | 文件 |
|---|------|------|------|
| O5.1 | 本地Chunk缓存补充原文 | 降级场景从product.rag_knowledge重建chunk原文，evidence可读 | `semantic_retriever.py` |
| O5.2 | Chunk权重注释 | _WEIGHTS配置加注释说明分配依据 | `semantic_retriever.py` |
| O7.1 | 补充证据搜索语义化 | 从关键词匹配升级为Embedding余弦相似度 | `retrieval_agent.py` |
| O8.1 | Reranker截断优化 | FAQ答案120→300, 评论100→200, 描述200→300 | `graph.py` |
| DOC | RAG全链路技术文档 | 1248行, 10站逐站剖析+8个答辩FAQ+完整数据流轨迹 | `docs/RAG_FULL_CHAIN_WORKFLOW_AND_AUDIT.md` |
| DOC | 评分体系文档修正 | Android模型缺字段标注 + SCORE_VERSION描述修正 | `docs/SCORING_SYSTEM_COMPLETE_REFERENCE.md` |
| DOC | RAG文档修正 | FollowUpEngine/ContextBuilder引用更新, Bug#7路径修正 | `docs/RAG_FULL_CHAIN_WORKFLOW_AND_AUDIT.md` |

**验证**: V1 Stream全链路通过 (5 products, 20 evidence, 5/5 chunks有text, Reranker精排生效)
| 52 | Docker 开发环境搭建 | 📋 待办 |

## 2026-05-24 完成详情 (37 文件，5 轮迭代)

### Bug 修复 (第一轮：15 项)
- `user_id` NameError 崩溃、`vision()` 参数错位、asyncpg DSN 不兼容
- 模块加载网络 I/O → `__getattr__` 惰性解析
- CORS credentials+wildcard 冲突、音频数据污染、提示模板 JSON 语法错误
- 缺失依赖 `jieba`/`mcp`、`USE_REDIS` 默认值不一致
- `_CapabilityProxy.chat` async/sync 不匹配

### 性能优化 (第二轮)
- **httpx 全链路异步化**: 4 个 LLM 网关 → `AsyncClient`（不再阻塞事件循环）
- **共享 AsyncBridge**: 5 处重复 `_run()` → `database.py` 的 `run_async()`
- **jieba 分词缓存**: 每查询仅分词一次（原每商品重复）
- **购物车批量删除**: `batch_remove()` 单条 SQL 替代 N+1
- **全文搜索**: `to_tsquery` → `plainto_tsquery`（特殊字符不崩溃）

### 安全加固
- **上传魔数校验**: `validate_image_magic()` 拒绝伪造图片
- **eval 路径穿越**: run_id 正则校验
- **语音错误脱敏**: 内部异常不返回客户端
- **Android**: 网络安全配置、FileProvider 收窄、OkHttp 日志仅 Debug、`onCleared()`

### 架构改进
- **共享规则模块**: `app/decision/rules.py` 统一品类/预算/场景检测
- **死代码清理**: SkuProperty, _get_cart, NetworkResult, 未使用导入
- **日志完善**: 8 处被吞噬异常添加 debug/warning 日志
- **workflow.yaml**: 标记为文档参考

### 测试覆盖
- 单元测试: 31 → **54** (新增 23 个 rules 测试)
- 集成测试: 8 → **15** (新增 7 个 V2 工作流测试)
- **61/61 全部通过**

## 基础设施

- 后端 API 端点：30+ 个
- 后端测试：**54 单元 + 15 集成 = 69 全部通过**（2026-05-24 更新）
- Android：BUILD SUCCESSFUL（多次编译通过）
- Workflow：8 节点 LangGraph（Reranker 对空查询自动降级）
- Skill Registry：8 skills / ToolManager：8 tools
- MCP Server：8 Tool JSON-RPC 2.0
- 共享规则模块：`app/decision/rules.py`（4 类规则集中管理）
- 数据集：100 件商品
- 代码仓库：GitHub (TheodoreYang6/OmniCart-Agent)

## 文档

- 答辩QA手册.md：20 章 + 附录，覆盖全部技术点
- README.md：面向队友
- CHANGELOG.md：完整变更记录 (含 2026-05-24 五轮迭代)
- TASK_LIST.md：任务跟踪
- DATABASE_DESIGN.md：数据库设计
- KNOWLEDGE_LOG.md：知识节点 (含 V2-Complete 架构知识)
- DECISION_LOG.md：技术决策
