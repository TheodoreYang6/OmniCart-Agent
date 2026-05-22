# AGENTS.md

本文件为 Codex (Codex.ai/code) 在此仓库中工作提供指引。

## 项目：OmniCart Agent (参赛版)

基于 Qwen 全栈模型的多模态购物决策 Agent，面向字节跳动 Agent 挑战赛。融合视觉理解、证据 RAG、Skill 工具化、A2A-lite 协作与可解释决策评分。

**目标：** V1 参赛可交付版。
**技术栈：** FastAPI + Next.js + Qwen Model Stack + Qdrant + PostgreSQL + Redis + LangGraph。
**架构：** Workflow-controlled Multi-Agent（非开放式 ReAct）。5 个核心 Agent：Router / Visual / Retrieval / Decision / Response。所有推荐结论必须绑定 `evidence_ids`。

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
V0-Core → V1-Core → V1-Plus → V1-Advanced → V2/V3
```

**当前阶段：V0-Core** — 最小可运行文本导购闭环（已完成）。

**V0-Core 允许范围：** FastAPI 后端、Next.js 前端、Product/Evidence/DecisionResult Schema、Qwen Model Gateway（含 Mock 模式）、mock 商品数据、Text Retriever、Decision Scoring、`/api/recommend`、ChatInput + ProductCard 组件。

**V0-Core 完成前禁止：** Agents（`agents/`）、A2A-lite（`a2a/`）、Skill Registry（`skills/`）、MCP-compatible ToolManager（`tools/`、`mcp_compatible/`）、Context Compiler（`context/`）、Preference Memory（`memory/`）、Harness（`harness/`）、Evidence Graph（`graph/`）、Visual Grounding（`vision/`）、Verification（`verification/`）、Security（`security/`）、Workflow YAML（`workflows/`）、Agent Runtime（`runtime/`）、分层索引（`indexing/`）。

## 开发守则

- 禁止创建无明确职责、无输入输出、无调用方、无验收标准的文件。
- 禁止一次性创建空壳目录或占位文件（`pass`、`TODO`、`raise NotImplementedError`）。
- 每次改动不得破坏当前阶段主链路。
- V0 主链路：`文本输入 → /api/recommend → Text Retriever → Decision Scoring → ProductCard`。

## 每次开发前

说明：属于哪个 milestone、要修改哪些文件、预期完成什么能力。

## 每次开发后

说明：修改了哪些文件、如何运行、如何测试、是否影响主链路。

## 用户触发命令

| 用户说 | 执行动作 |
|---|---|
| "进行记忆存储" | 更新 `DEVELOPMENT_PROGRESS.md`、`KNOWLEDGE_LOG.md`、`CHANGELOG.md` |
| "标记节点完成: X" | 验证确实完成，更新进度 + 知识日志 + 变更日志 |
| "运行验证" | 运行已有测试/脚本；若无则创建最小 smoke test |

## 命名规范

- Python：`snake_case`，React 组件：`PascalCase`，JSON 数据：`snake_case`。
- ID 前缀：`P`=Product、`E`=Evidence、`R`=Review Evidence、`POL`=Policy Evidence、`V`=Visual Evidence、`T`=Trace Step、`A`=Artifact、`SKE`=Skill Execution、`TC`=Tool Call、`HR`=Harness Run。

## V0 API 契约

```
GET  /api/health     → { status, service, version }
POST /api/recommend  → { session_id, answer, products[], evidence_list[], decision_results[],
                         trace_steps[], skill_executions[], harness_report{}, fallback_status{} }
```

## 常用命令

```bash
# 一键安装全部依赖
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pip install -r requirements.txt --proxy="" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 启动后端（双击 run.py 或命令行）
"D:\app_work\anaconda\envs\omnicart\python.exe" run.py

# 运行全部测试（无需 PYTHONPATH，.pth 文件已自动配置）
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pytest tests/ -v

# 运行单个测试文件
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pytest tests/unit/test_scoring.py -v

# Smoke test（需后端运行中）
"D:\app_work\anaconda\envs\omnicart\python.exe" scripts/smoke_recommend.py

# 前端构建
cd frontend && npm run build

# 前端开发模式
cd frontend && npm run dev
```

## 安全红线

- 禁止硬编码 API Key，使用 `.env` / `config.py`。
- V1 所有工具默认只读（不执行下单、支付、账号操作）。
- 禁止删除文件；只能标记 deprecated 或移至 `archive/`。
- 禁止伪造测试结果或将未完成节点标记为 done。
