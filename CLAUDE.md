# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作提供指引。重点：每次回答和工作前，先叫我主人

## 项目：OmniCart Agent (参赛版)

基于 Qwen 全栈模型的多模态购物决策 Agent，面向字节跳动 Agent 挑战赛。融合视觉理解、证据 RAG、可解释决策评分、三层记忆与流式对话。

**目标：** V2 参赛可交付版（Docker 容器化 + 阿里云部署 + Android Release APK）。
**技术栈：** FastAPI + Android Native Client (Kotlin + Jetpack Compose + Material 3) + Qwen Model Stack + Qdrant + PostgreSQL + Redis + LangGraph。
**架构：** Workflow-controlled Multi-Agent（非开放式 ReAct）。5 个核心 Agent：Router / Visual / Retrieval / Decision / Response。所有推荐结论必须绑定 `evidence_ids`。
**部署：** Docker Compose 四服务编排，阿里云轻量服务器 8.137.187.54:8006。

## 客户端形态

**主交付端：Android Native Client**
- 语言：Kotlin
- UI：Jetpack Compose + Material 3
- 架构：MVVM (ViewModel + StateFlow)
- 网络：Retrofit + OkHttp + Coroutines + SSE 流式
- 图片：Coil
- 图片选择：Android Photo Picker
- 语音：ASR 录音 → 转文字 → SSE 推荐 → TTS 朗读

**禁止使用：** WebView、React Native、Expo、Flutter 等作为最终交付端。
**已移除：** frontend/ (Next.js) — 已从仓库删除。

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

- `OMNICART_AGENT_COMPLETE_BLUEPRINT.md` — **最终蓝图，默认只读。** 除非用户明确说"修改最终蓝图"，否则不得修改。
- `AGENT_COLLABORATION.md` — 5 Agent 协同设计与 LangGraph 编排。
- `RAG_PIPELINE.md` — RAG 检索全链路（Embedding → Qdrant → Reranker → 证据补充）。
- `MEMORY_SYSTEM.md` — 三层记忆架构（短期/长期/会话）。
- `SCORING_SYSTEM_COMPLETE_REFERENCE.md` — 7 维加权评分公式与证据指标。
- `DATABASE_DESIGN.md` — PostgreSQL 表结构与 ORM 模型。
- `DEVELOPMENT_RULES.md` — AI 编程 Agent 行为规范：开发前后该做什么、文档维护触发条件、质量门禁。
- `DEVELOPMENT_PROGRESS.md` — 开发进度记录。
- `KNOWLEDGE_LOG.md` — 关键技术节点知识总结。
- `CHANGELOG.md` — 变更日志。
- `答辩QA手册.md` — 答辩问答准备。

## 当前阶段：V2 生产就绪

V0~V2 全部里程碑已完成，当前处于文档优化与运维完善阶段。

**已完成的能力：**

| 模块 | 内容 |
|------|------|
| 后端 API | 17 个路由模块：health / recommend(v0+v2+guide+stream) / products / cart / checkout / auth / address / preference / conversation / upload / voice / agent_actions / observability / eval / eval_dashboard / user_profile |
| 5 Agent | Router（意图+约束）、Visual（Qwen-VL 拍照识图+品类映射+DB精确匹配）、Retrieval（三通道并行：text语义+review评论+policy/FAQ+证据补充）、Decision（7维证据加权评分+LLM可选评估）、Response（LLM流式生成+模板兜底+幻觉校验） |
| LangGraph | StateGraph 编排：Router → Visual(并行) → Retrieval → Reranker → EvidenceCheck → Decision → Response → Guard → END |
| 检索链路 | Embedding(1024d) → Qdrant ANN → 品类/价格过滤 → Qwen3-Reranker 精排 → 视觉置顶(0.99) → 避雷硬过滤 → 分块证据补充 |
| 记忆系统 | 短期(context_snapshot JSONB) + 长期(user_preference_entries 条目化+品类感知注入) + 会话(conversations+messages PG持久化) |
| 对话引擎 | FollowUpEngine 7 种追问检测 + ContextCompressor 增量摘要 + 对话标题自动生成 + pending_question 问答链 |
| 购物闭环 | 对话加购(SKU规格选择) + 购物车CRUD + 自然语言管理 + 模拟下单 + 订单持久化 |
| 语音 | ASR 录音转文字(静音检测+AI回复清洗) + TTS 文字转语音(MediaPlayer播放) |
| Android | 四Tab(商品/豆仔/购物车/我的) + SSE流式打字机 + 拍照识图 + 语音输入 + 历史对话 + 偏好管理 + 登录注册 + 地址管理 + 快速模式 + Demo演示 |
| 评测 | 10 Golden Queries + Recall@K/MRR/NDCG@K + Chart.js 可视化仪表盘 + LLM 全链路追踪 |
| 部署 | Docker Compose 四服务(postgres+qdrant+redis+backend) + 阿里云轻量服务器 + Release APK(签名混淆2.4MB) + 运维手册 |

**当前主链路：**
```
Android SSE输入 → /api/recommend/stream → FollowUpEngine检测 → Router(LLM+规则) → Visual(有图并行)
→ Retrieval(语义+分块+证据补充) → Reranker精排 → Decision(7维证据评分) → Response(流式LLM+模板兜底)
→ Guard校验 → SSE token逐字返回 → conversation持久化 + 上下文压缩
```

## 开发守则

- 禁止创建无明确职责、无输入输出、无调用方、无验收标准的文件。
- 禁止一次性创建空壳目录或占位文件（`pass`、`TODO`、`raise NotImplementedError`）。
- 每次改动不得破坏主链路（SSE 流式推荐 + Android 对话）。
- 新增功能必须考虑 Mock 模式兼容（`OMNICART_MOCK_MODE=true` 时仍可运行）。
- 文档与代码同步：架构/API/配置变更必须同步更新对应的 docs/ 文档。

## 每次开发前

说明：要修改哪些文件、预期完成什么能力、是否影响主链路。

## 每次开发后

说明：修改了哪些文件、如何运行、如何测试、是否影响主链路。
Android 端额外说明：模拟器或真机运行方式、是否可打包 APK。

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

## API 契约

### 核心端点
```
GET  /api/health                    → { status, service, version, redis }
POST /api/recommend                 → V0 同步推荐（兼容旧客户端）
POST /api/recommend/v2              → V2 LangGraph 工作流推荐
POST /api/recommend/stream          → SSE 流式推荐（主力端点，支持文字/图片/语音/聚焦分析/购物操作）
POST /api/recommend/guide           → 约束引导式推荐（品类→预算→推荐多轮引导）
```

### 商品 & 图片
```
GET  /api/products                  → 商品列表（品类/关键词/价格筛选+分页）
GET  /api/products/{id}             → 商品详情（含SKU/FAQ/评论/评价摘要）
GET  /api/products/{id}/image       → 商品图片文件
POST /api/upload                    → 图片上传（魔术字校验+10MB限制）
```

### 购物车 & 结算
```
GET    /api/cart                    → 查看购物车
POST   /api/cart/items              → 加购（SKU校验+价格）
PUT    /api/cart/items/{id}         → 修改数量/选中状态
DELETE /api/cart/items/{id}         → 移除商品
POST   /api/cart/select-all         → 全选/取消全选
DELETE /api/cart/clear              → 清空购物车
POST   /api/checkout                → 模拟结算
GET    /api/orders                  → 订单列表
```

### 用户 & 地址
```
POST   /api/auth/register           → 注册
POST   /api/auth/login              → 登录
GET    /api/auth/profile            → 个人信息
GET    /api/addresses               → 地址列表
POST   /api/addresses               → 新增地址
PUT    /api/addresses/{id}          → 修改地址
DELETE /api/addresses/{id}          → 删除地址
```

### 会话 & 偏好
```
GET    /api/conversations           → 历史对话列表
GET    /api/conversations/{id}      → 对话详情
GET    /api/conversations/{id}/messages → 对话消息（含商品引用）
DELETE /api/conversations/{id}      → 删除对话
GET    /api/preferences             → 当前会话偏好
PUT    /api/preferences             → 更新会话偏好
GET    /api/preferences/entries     → 长期偏好条目列表
PUT    /api/preferences/entries     → 新增偏好条目
POST   /api/preferences/parse       → 预览解析（不存库）
DELETE /api/preferences/entries/{id} → 删除偏好条目
```

### 语音 & Agent & 评测
```
POST   /api/voice/transcribe        → ASR 语音转文字
POST   /api/voice/tts               → TTS 文字转语音
POST   /api/agent/action            → Agent 受控操作（加购等）
GET    /api/observability/traces    → LLM 调用追踪
GET    /api/observability/stats     → 聚合统计
POST   /api/eval/run                → 运行 Golden Query 评测
GET    /api/eval/results            → 历史评测结果
GET    /eval                        → Chart.js 可视化仪表盘
```

后端端口：`8006`（见 `.env` 中 `OMNICART_PORT`）。

## 常用命令

```bash
# 一键安装全部依赖
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pip install -r requirements.txt --proxy="" -i https://pypi.tuna.tsinghua.edu.cn/simple

# 本地启动后端
cd backend && "D:\app_work\anaconda\envs\omnicart\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8006

# 服务器启动（Docker Compose）
cd ~/OmniCart-Agent && docker compose up -d

# 服务器更新代码
git pull && docker compose up -d --build backend

# 运行全部测试
"D:\app_work\anaconda\envs\omnicart\python.exe" -m pytest tests/ -v

# Smoke test（需后端运行中）
"D:\app_work\anaconda\envs\omnicart\python.exe" scripts/smoke_recommend.py

# Android Debug APK
cd android-client && ./gradlew assembleDebug

# Android Release APK（签名混淆）
cd android-client && ./gradlew assembleRelease

# APK 安装到手机
adb install android-client/app/build/outputs/apk/release/app-release.apk
```

## 服务器运维

| 项目 | 值 |
|------|-----|
| 公网 IP | 8.137.187.54 |
| 端口 | 8006 |
| 配置 | 阿里云轻量 2C4G 50G SSD |
| 项目路径 | ~/OmniCart-Agent |
| 健康检查 | `curl http://8.137.187.54:8006/api/health` |
| APK 下载 | `http://8.137.187.54:8006/api/uploads/douzai.apk` |

详见 `SERVER_OPS.md` 和 `DEPLOY.md`。

## 安全红线

- 禁止硬编码 API Key，使用 `.env` / `config.py`。
- 所有工具默认只读（不执行真实支付）。
- 禁止删除文件；只能标记 deprecated 或移至 `archive/`。
- 禁止伪造测试结果或将未完成节点标记为 done。
