# OmniCart Agent 开发进度

更新时间：2026-05-23
当前阶段：**V2 扩展 (6/13)**
当前重点：Docker 环境搭建 + APK 打包收尾
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
| V2 | 进行中 | 6/13 |

## V2 已完成 6 项

| # | 任务 | 日期 |
|---|------|------|
| 47 | **Redis 四级缓存** — Visual(1h)/Search(5min)/Rewrite(30min)/Workflow(5min) + 优雅降级 | 2026-05-23 |
| 49 | **LLM 全链路可观测性** — Gateway 全量追踪 4 方法 + Token 统计 + P50/P95 + 聚合 API | 2026-05-23 |
| 43 | **Qwen-Omni 语音导购** — ASR→Agent→TTS + Android 全屏语音 + 长按录音 + 文字清洗 | 2026-05-23 |
| 40 | **标准 MCP Server/Client** — 8 Tool JSON-RPC 2.0 + stdio/SSE 双传输 + Claude Desktop 可接入 | 2026-05-23 |
| 46 | **用户长期偏好记忆** — 跨会话 UserProfile + 行为信号(搜索/加购/结账) + 时间衰减 + PG/JSON | 2026-05-23 |
| 51 | **Evaluation Dashboard** — Web 可视化面板 + Chart.js + 10 golden queries + 历史趋势 | 2026-05-23 |

## V2 待完成 7 项

| # | 任务 | 说明 |
|---|------|------|
| 19 | APK Release 打包 | Release 签名 + assembleRelease |
| 41 | 标准 A2A Protocol | 经分析跳过 — 同进程 LangGraph 不需要跨框架通信 |
| 42 | Neo4j GraphRAG | 经分析跳过 — NetworkX 已足够，V3 可升级 |
| 44 | iOS SwiftUI 客户端 | 经分析跳过 — 比赛交付端是 Android |
| 45 | Computer Use / Browser Use | 经分析跳过 — Demo 不可控风险高 |
| 48 | 在线反馈学习 / Bandit | 可选 — 需行为数据积累 |
| 50 | 大规模商品数据（1000+ 件） | 👤 队友负责 |
| 52 | Docker 开发环境搭建 | 📋 待办 |

## 基础设施

- 后端 API 端点：30+ 个
- 后端测试：31/31 通过
- Android：BUILD SUCCESSFUL（多次编译通过）
- Workflow：8 节点 LangGraph
- Skill Registry：8 skills / ToolManager：8 tools
- MCP Server：8 Tool JSON-RPC 2.0
- 数据集：100 件商品（含 2026-05-23 新增 5 件平价数码）
- 代码仓库：GitHub (TheodoreYang6/OmniCart-Agent)

## 文档

- 答辩QA手册.md：20 章 + 附录，覆盖全部技术点
- README.md：面向队友
- CHANGELOG.md：完整变更记录
- TASK_LIST.md：任务跟踪
- DATABASE_DESIGN.md：数据库设计
- KNOWLEDGE_LOG.md：知识节点
- DECISION_LOG.md：技术决策
