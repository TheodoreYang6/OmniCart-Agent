# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作提供指引。

## 项目：OmniCart Agent (参赛版)

基于 Qwen 全栈模型的多模态购物决策 Agent，面向字节跳动 Agent 挑战赛。融合视觉理解、证据 RAG、Skill 工具化、A2A-lite 协作与可解释决策评分。

**目标：** V1 参赛可交付版。
**技术栈：** FastAPI + Android Native Client (Kotlin + Jetpack Compose + Material 3) + Qwen Model Stack + Qdrant + PostgreSQL + Redis + LangGraph。
**架构：** Workflow-controlled Multi-Agent（非开放式 ReAct）。5 个核心 Agent：Router / Visual / Retrieval / Decision / Response。所有推荐结论必须绑定 `evidence_ids`。

## 客户端形态

**主交付端：Android Native Client**
- 语言：Kotlin
- UI：Jetpack Compose + Material 3
- 架构：MVVM (ViewModel + StateFlow)
- 网络：Retrofit + OkHttp + Coroutines
- 图片：Coil
- 图片选择：Android Photo Picker

**已废弃：** frontend/ (Next.js / React / TailwindCSS) — 仅保留供历史参考，不再维护。
**禁止使用：** WebView、React Native、Expo、Flutter 等作为最终交付端。

## Python 环境

```
Python 路径: D:\app_work\anaconda\envs\omnicart\python.exe
版本:       Python 3.11.15
pip 镜像:   https://pypi.tuna.tsinghua.edu.cn/simple
pip 代理:   需要 --proxy="" 绕过系统代理
```

所有 Python 命令必须使用此环境：
```bash
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pip install <包名> --proxy="" -i https://pypi.tuna.tsinghua.edu.cn/simple
```

## 核心文档（docs/ 目录）

- `OMNICART_AGENT_COMPLETE_BLUEPRINT.md` — **最终蓝图，默认只读。** 除非用户明确说"修改最终蓝图"或"更新开发蓝图"，否则不得修改。
- `DEVELOPMENT_DIRECTORY_STRUCTURE.md` — 目标目录结构和各阶段文件落地顺序。
- `DEVELOPMENT_RULES.md` — AI 编程 Agent 行为规范：开发前后该做什么、文档维护触发条件、质量门禁。
- `DEVELOPMENT_PROGRESS.md` — 开发进度记录。
- `KNOWLEDGE_LOG.md` — 关键技术节点知识总结。
- `CHANGELOG.md` — 变更日志。
- `DECISION_LOG.md` — 关键技术决策记录。

## 开发里程碑（严格优先级）

```
V0-Core → V0-Android → V1-Core → V1-Android → V1-Plus → V1-Advanced → V2/V3
```

**当前阶段：V0-Android** — Android 原生客户端最小文本导购闭环。

**V0-Core (已完成)：** FastAPI 后端、Product/Evidence/DecisionResult Schema、Qwen Model Gateway（含 Mock 模式）、mock 商品数据、Text Retriever、Decision Scoring、`/api/recommend`。

**V0-Android (进行中)：** Android 项目骨架、MainActivity + Compose 主题、ChatScreen、ChatInputBar、Retrofit/OkHttp API 调用、RecommendRequest/RecommendResponse 数据类、ProductCard、Demo Mode 本地假数据。

**V0 阶段禁止：** Agents（`agents/`）、A2A-lite（`a2a/`）、Skill Registry（`skills/`）、MCP-compatible ToolManager（`tools/`、`mcp_compatible/`）、Context Compiler（`context/`）、Preference Memory（`memory/`）、Harness（`harness/`）、Evidence Graph（`graph/`）、Visual Grounding（`vision/`）、Verification（`verification/`）、Security（`security/`）、Workflow YAML（`workflows/`）、Agent Runtime（`runtime/`）、分层索引（`indexing/`）。

**V0-Android 完成前禁止：** EvidencePanel、AgentTracePanel、SkillExecutionPanel、HarnessValidationPanel、ProductDetailSheet、ScoreBreakdown、ImagePicker、ImagePreview — 这些是 V1-Android 范围。

## 开发守则

- 禁止创建无明确职责、无输入输出、无调用方、无验收标准的文件。
- 禁止一次性创建空壳目录或占位文件（`pass`、`TODO`、`raise NotImplementedError`）。
- 每次改动不得破坏当前阶段主链路。
- V0 主链路：`Android 文本输入 → Retrofit 调用 /api/recommend → Text Retriever → Decision Scoring → Android ProductCard`。
- frontend/ 目录已废弃，禁止继续创建或维护为主线。

## 每次开发前

说明：属于哪个 milestone、要修改哪些文件、预期完成什么能力。

## 每次开发后

说明：修改了哪些文件、如何运行、如何测试、是否影响主链路。
Android 端开发额外说明：模拟器或真机运行方式、是否可打包 APK。

## 用户触发命令

| 用户说 | 执行动作 |
|---|---|
| "进行记忆存储" | 更新 `DEVELOPMENT_PROGRESS.md`、`KNOWLEDGE_LOG.md`、`CHANGELOG.md` |
| "标记节点完成: X" | 验证确实完成，更新进度 + 知识日志 + 变更日志 |
| "运行验证" | 运行已有测试/脚本；若无则创建最小 smoke test |

## 命名规范

- Python：`snake_case`，Kotlin 类：`PascalCase`，JSON 数据：`snake_case`。
- Kotlin 包名和目录使用小写路径，例如 `feature/chat`、`core/network`。
- ID 前缀：`P`=Product、`E`=Evidence、`R`=Review Evidence、`POL`=Policy Evidence、`V`=Visual Evidence、`T`=Trace Step、`A`=Artifact、`SKE`=Skill Execution、`TC`=Tool Call、`HR`=Harness Run。

## V0 API 契约

```
GET  /api/health     → { status, service, version }
POST /api/recommend  → { session_id, answer, products[], evidence_list[], decision_results[],
                         trace_steps[], visual_result, skill_executions[], harness_report{}, fallback_status{} }
```

后端端口：`8006`（见 `.env` 中 `OMNICART_PORT`）。

## 常用命令

```bash
# 一键安装全部依赖
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pip install -r requirements.txt --proxy="" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 启动后端（仅后端，不启动已废弃的前端）
cd backend && "D:\app_work\anaconda\envs\omnicart\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8006

# 运行全部测试（无需 PYTHONPATH，.pth 文件已自动配置）
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pytest tests/ -v

# 运行单个测试文件
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pytest tests/unit/test_scoring.py -v

# Smoke test（需后端运行中）
"D:\app_work\anaconda\envs\omnicart\python.exe" scripts/smoke_recommend.py

# Android 客户端构建 (需 Android Studio 或 ./gradlew)
cd android-client && ./gradlew assembleDebug

# Android APK 安装到模拟器
adb install android-client/app/build/outputs/apk/debug/app-debug.apk
```

## 安全红线

- 禁止硬编码 API Key，使用 `.env` / `config.py`。
- V1 所有工具默认只读（不执行下单、支付、账号操作）。
- 禁止删除文件；只能标记 deprecated 或移至 `archive/`。
- 禁止伪造测试结果或将未完成节点标记为 done。
