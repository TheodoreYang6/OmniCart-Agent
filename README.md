<p align="center">
  <img src="小O.png" width="120" alt="小O Logo" />
</p>

<h1 align="center">OmniCart Agent</h1>

<p align="center">
  <strong>基于 RAG 的多模态电商智能导购 AI Agent</strong>
  <br/>
  字节跳动 Agent 挑战赛参赛作品
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python" alt="Python" />
  <img src="https://img.shields.io/badge/Kotlin-1.9-7F52FF?logo=kotlin" alt="Kotlin" />
  <img src="https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi" alt="FastAPI" />
  <img src="https://img.shields.io/badge/LangGraph-0.2-FF6F00" alt="LangGraph" />
  <img src="https://img.shields.io/badge/Qwen-通义千问-FF6A00" alt="Qwen" />
  <img src="https://img.shields.io/badge/Docker-26-2496ED?logo=docker" alt="Docker" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Redis-7-DC382D?logo=redis" alt="Redis" />
  <img src="https://img.shields.io/badge/Qdrant-latest-243B55" alt="Qdrant" />
</p>

<p align="center">
  <strong>🚀 服务运行中：<a href="http://8.137.187.54:8006/api/health">http://8.137.187.54:8006/api/health</a></strong>
  &nbsp;|&nbsp;
  <strong>📱 APK 下载：<a href="http://8.137.187.54:8006/api/uploads/douzai.apk">小O.apk</a></strong>
</p>

---

## 换一台机器接手？看这里

本 README 是**产品与架构视角**的全景介绍（这个系统是什么、为什么这么设计）。
如果你的目标是**在新机器上把它跑起来并继续开发**，请直接读开发者文档：

| 文档 | 用途 |
|------|------|
| **[DEVELOPMENT.md](DEVELOPMENT.md)** | 开发者上手指南：五分钟最短路径、项目结构、环境配置、开发流程与门禁、踩坑清单 |
| **[MODULES.md](MODULES.md)** | 重要功能模块说明：每个模块负责什么、关键文件在哪、改它要注意什么 |
| **[DEPLOY.md](DEPLOY.md)** | 服务器部署：Docker 四容器、数据初始化、备份恢复、Nginx、APK 构建 |
| **[SERVER_OPS.md](SERVER_OPS.md)** | 线上运维：启停、日志、健康检查、防火墙 |

最短路径（不填密钥也能跑通全链路）：

```bash
git clone https://github.com/TheodoreYang6/OmniCart-Agent.git
cd OmniCart-Agent && cp .env.example .env
docker compose up -d postgres qdrant redis
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
cd backend && OMNICART_MOCK_MODE=true python -m uvicorn app.main:app --port 8006 --loop asyncio
# 另开终端：cd web-client && npm install && npm run dev
```

> ⚠️ `--loop asyncio` 必加（uvloop 与 nest_asyncio 冲突），`.env` / `.env.local` 不入库需自行从 `.env.example` 复制。

---

## 目录

- [项目简介](#项目简介)
- [系统架构](#系统架构)
- [核心亮点](#核心亮点)
- [功能矩阵](#功能矩阵)
- [目录结构](#目录结构)
- [环境与配置](#环境与配置)
- [快速开始](#快速开始)
- [Agent 协同](#agent-协同)
- [RAG 全链路](#rag-全链路)
- [评分体系](#评分体系)
- [记忆系统](#记忆系统)
- [关键问题与解决方案](#关键问题与解决方案)
- [API 速查](#api-速查)
- [评测体系](#评测体系)
- [部署运维](#部署运维)
- [文档索引](#文档索引)

---

## 项目简介

**OmniCart Agent** 将传统电商的"展示型广告"升级为"**交互型导购**"，打通从内容浏览到购买决策的完整闭环。

用户通过**文字、拍照、语音**任一方式表达购物需求，系统内部 **5 个协作 Agent** 在 LangGraph 编排下完成意图理解 → 视觉识别 → 多维检索 → 证据评分 → 流式回复的全链路推理，最终在 **Android 原生客户端**上以打字机效果呈现推荐结果。所有推荐结论均绑定 `evidence_ids`，做到**可解释、可追溯、可验证**。

### 为什么不是又一个"AI 客服"

> **传统搜索：** 输入关键词 → 翻列表 → 比价格 → 看评论 → 自己决策。
> **传统 AI 客服：** 套模板回复 → 推热门商品 → 说不出推荐理由 → 无法操作购物车。
> **OmniCart Agent：** 一句话（或一张图）→ 5 Agent 流水线协作 → 可解释的推荐 + 证据溯源 → 自然语言加购下单。**边说边做，不只是聊天**。

---

## 系统架构

> **V3 框架化升级**：后端已按「框架-实现分离 + Provider/Registry」重构（RAG / Memory / Context 三大框架 + AgentManager + ModelProvider/弹性 + 全链路 trace_id + CI/治理）。详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与 [docs/adr/](docs/adr/)。

```
┌──────────────────────────────────────────────────────────────────────┐
│                       🖥  Android Native Client                        │
│  Kotlin + Jetpack Compose + Material 3  ·  MVVM + StateFlow           │
│                                                                        │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│   │  📦 商品  │   │  🫘 小O  │   │  🛒 购物车 │   │  👤 我的  │          │
│   │ 商品浏览  │   │ SSE 对话  │   │ 购物管理  │   │ 个人中心  │          │
│   └──────────┘   └──────────┘   └──────────┘   └──────────┘          │
│                         │                                              │
│   输入模态：💬 文字  ·  📷 拍照识图  ·  🎤 语音导购                     │
│   对话能力：追问/指代/对比/加购/下单/偏好记忆                           │
└─────────────────────────────┬────────────────────────────────────────┘
                              │  HTTP REST + SSE Stream (Retrofit/OkHttp)
┌─────────────────────────────▼────────────────────────────────────────┐
│                     ⚙  FastAPI Backend (:8006)                         │
│                                                                        │
│  ┌─────────────────── Workflow (LangGraph StateGraph) ──────────────┐ │
│  │                                                                    │ │
│  │  START ──→ Router ──→ Visual (∥并行) ──→ Retrieval ──→ Reranker  │ │
│  │              │                                    │                │ │
│  │              │ (chitchat)                         │                │ │
│  │              ▼                                    ▼                │ │
│  │           Response         EvidenceCheck ←── Reranker              │ │
│  │              ▲                  │                                  │ │
│  │              │                  ▼                                  │ │
│  │              └──────────── Decision ──→ Response ──→ Guard ──→ END │ │
│  │                     (无结果时跳过 Decision)                         │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                 │
│  │ FollowUpEngine│  │CtxCompressor │  │ Memory Layer │                 │
│  │ 7种追问检测   │  │ 对话增量摘要  │  │ 三层记忆     │                 │
│  └──────────────┘  └──────────────┘  └──────────────┘                 │
│                                                                        │
│  17 个 API 路由模块  ·  5 Agent 协作  ·  7 大模型能力                   │
└─────────────────────────────┬────────────────────────────────────────┘
                              │
      ┌───────────────────────┼───────────────────────┐
      │                       │                       │
┌─────▼─────┐  ┌──────────────▼──┐  ┌───────────────▼──┐
│ PostgreSQL │  │     Qdrant      │  │      Redis        │
│   16       │  │   向量检索引擎    │  │     7             │
│ 商品/用户   │  │  1024d ANN      │  │  四级缓存          │
│ 会话/购物车 │  │  余弦相似度      │  │  优雅降级          │
│ 订单/偏好   │  │  本地降级兜底    │  │                    │
└───────────┘  └─────────────────┘  └────────────────────┘

              ┌─────────────────────────────────┐
              │       Qwen Model Stack           │
              │  qwen-turbo    · 意图/生成       │
              │  qwen-vl-max   · 视觉理解        │
              │  qwen3-rerank  · 语义精排        │
              │  text-embedding-v4 · 向量化(1024d)│
              │  qwen-omni-turbo · 语音(ASR+TTS) │
              └─────────────────────────────────┘
```

**Workflow 节点流转：**

| 步骤 | 节点 | 职责 | 性能优化 |
|------|------|------|----------|
| 1 | **Router** | 意图识别 + 品类/预算/场景约束提取 + 检索计划 | 品类预填跳过 LLM；规则+LLM 合并 |
| 2 | **Visual** | 拍照识图、品类映射、DB 精确匹配 | 与 Router 并行执行 |
| 3 | **Retrieval** | 语义检索 + 分块证据补充（三通道） | LLM 关键词改写缓存 30min |
| 4 | **Reranker** | Qwen3-Rerank 语义精排 | 视觉匹配商品置顶 0.99 |
| 5 | **EvidenceCheck** | 证据充足性校验 | 不满足则标记 insufficiency |
| 6 | **Decision** | 7 维证据加权评分 + 避雷过滤 | LLM 评估可选（默认关闭） |
| 7 | **Response** | LLM 流式生成 + 幻觉校验 | 6s 超时模板兜底 |
| 8 | **Guard** | 品牌验证 + 价格准确 + 风险覆盖 | 四道防线 |

---

## 核心亮点

### 完整闭环：从需求到下单，一句话搞定

用户只需说出"推荐一款降噪耳机，预算500以内"→ Agent 自动完成品类识别、商品检索、多维评分、流式推荐。用户接着说"第二个加入购物车"→ 自动解析序号指代，匹配 SKU 规格，完成加购。再说"下单"→ 读取地址、生成订单、持久化。**全链路自然语言驱动，无需手动操作**。

### 证据绑定：每个推荐都可解释、可溯源

AI 导购最致命的问题是"幻觉"——推荐了不存在的商品，或说不出推荐理由。OmniCart 从架构层面解决：**所有推荐结论必须绑定 `evidence_ids`**，前端可逐条追溯到来源数据。

5 类证据覆盖推荐全链路：
- **E-MKT**：商品营销描述（"官方宣称什么"）
- **POL**：官方 FAQ / 政策证据（"厂商怎么说的"）
- **R**：用户评论证据——正向/中性/风险三级（"真实用户怎么评价的"）
- **V**：视觉识别证据——拍照识图结果（"你拍的这是什么"）
- **E-SUPP**：补充发现证据——分块语义匹配（"FAQ里还提到这个"）

Decision Agent 每件商品产出完整可解释结构：`component_scores`（7 维分解分 + 各自权重）→ `recommendation_reason`（推荐理由文案）→ `risk_factors`（风险提示）→ `support_evidence_ids`（支撑证据 ID 列表，可追溯到原文）。**评委 / 用户可以逐条验证每个推荐背后的依据**。

### 三层记忆：越聊越懂你

| 层次 | 存储 | TTL | 内容 |
|------|------|-----|------|
| **短期** | context_snapshot (PG JSONB) | 2h | 当前品类/预算/场景约束、上轮商品引用、pending_question |
| **长期** | user_preference_entries (PG) | 持久 | 品类+品牌+场景+避雷标签，条目化管理，品类感知注入 |
| **会话** | conversations + messages (PG) | 持久 | 对话历史+消息持久化，支持跨设备恢复、增量压缩摘要 |

FollowUpEngine 覆盖 **7 种追问模式**：序数指代（"第二个怎么样"）、品牌引用（"Sony那个"）、上次引用（"刚才那个"）、预算更新、购物车意图、对比意图、模糊追问（"便宜一点"）。Router 的 `_build_session_context` 注入 pending_question 实现问答链：小O问了问题 → 用户简短回答"好"→ 自动推断搜索意图。

### 生产就绪：Docker 一键部署 + 云服务器 + Release APK

```
docker compose up -d          # 一行命令启动四服务
curl 8.137.187.54:8006/api/health  # 公网可访问
```

- 四服务编排：backend + PostgreSQL 16 + Qdrant + Redis 7
- 阿里云轻量服务器 2C4G 运行中
- Android Release APK 签名混淆，2.4MB，可扫码安装
- 环境变量驱动配置，Mock 模式无需 API Key 也能跑

---

## 功能矩阵

### 输入 & 交互

| 功能 | 说明 | 状态 |
|------|------|:--:|
| 文字导购 | 自然语言输入 → RAG 检索 → 流式推荐 | ✅ |
| 拍照识图 | 拍照 → Qwen-VL 解析 → 品类映射 → 同类检索 | ✅ |
| 语音导购 | 长按录音 → ASR 转文字 → SSE 推荐 → TTS 朗读 | ✅ |
| SSE 流式 | 逐字打字机效果，支持中途取消 | ✅ |
| 快速模式 | 跳过 LLM 模板秒回，客户端 ⚡ 开关 | ✅ |
| Demo 演示 | 8 个预设场景一键演示，Mock 本地数据 | ✅ |

### 推荐引擎

| 功能 | 说明 | 状态 |
|------|------|:--:|
| V0 同步推荐 | `POST /api/recommend` 文本检索 + 评分 | ✅ |
| V2 工作流推荐 | `POST /api/recommend/v2` LangGraph 5-Agent | ✅ |
| SSE 流式推荐 | `POST /api/recommend/stream` 主力端点 | ✅ |
| 约束引导推荐 | `POST /api/recommend/guide` 品类→预算多轮 | ✅ |
| 商品聚焦分析 | 问小O → product_focused_analysis → 深度+对比 | ✅ |
| Reranker 精排 | Qwen3-Rerank 语义重排序 + 视觉置顶 | ✅ |
| 6 维加权评分 | relevance + budget_fit + user_sat + value_score + spec_quality + scenario_fit + risk扣分 + 偏好加成 | ✅ |
| 幻觉检测 | 品牌验证 + 价格准确 + 证据绑定 + 风险覆盖 | ✅ |

### 购物闭环

| 功能 | 说明 | 状态 |
|------|------|:--:|
| 对话加购 | "加入购物车"→ SKU 规格选择 → 确认 | ✅ |
| 购物车管理 | 查看/删第N个/数量改成N/清空（自然语言） | ✅ |
| 模拟下单 | 地址确认 → 订单汇总 → 订单持久化 | ✅ |
| 订单查询 | 历史订单列表 | ✅ |
| 地址管理 | CRUD + 默认地址 | ✅ |
| 用户认证 | 注册/登录/Token + 个人信息 | ✅ |

### 记忆 & 对话

| 功能 | 说明 | 状态 |
|------|------|:--:|
| 多轮追问 | 7 种追问模式自动检测 + 约束继承 | ✅ |
| 问答链 | 小O提问 → 用户简短回复 → 自动推断意图 | ✅ |
| 历史对话 | 对话列表 + 消息恢复 + 删除 | ✅ |
| 对话标题 | LLM 自动生成 + 首条截断降级 | ✅ |
| 上下文压缩 | Qwen-turbo 增量摘要 + context_snapshot 持久化 | ✅ |
| 偏好条目 | 自然语言输入 → LLM 解析 → 条目化管理 | ✅ |
| 品类注入 | 检测 query 品类 → 仅注入匹配条目 → 避免污染 | ✅ |
| 避雷过滤 | 偏好 avoid_tags → 硬过滤 + 降权重双重保障 | ✅ |

### 工程 & 质量

| 功能 | 说明 | 状态 |
|------|------|:--:|
| Docker 部署 | docker-compose.yml 四服务编排 | ✅ |
| 云服务器 | 阿里云 8.137.187.54:8006 | ✅ |
| Release APK | 签名 + 混淆 + ProGuard，2.4MB | ✅ |
| LLM 可观测 | 全链路 span 追踪 + 聚合统计 + 延迟分布 | ✅ |
| 评测体系 | 10 Golden Query + Recall@K/MRR/NDCG@K | ✅ |
| 可视化仪表盘 | Chart.js 交互式评测面板 | ✅ |
| Redis 缓存 | 视觉/搜索/改写/工作流四级缓存 + 降级 | ✅ |
| Mock 模式 | 无需 API Key 即可运行，Mock 数据完整 | ✅ |

---

## 目录结构

```
OmniCart-Agent/
│
├── android-client/                          # Android 原生客户端 (Kotlin)
│   ├── app/
│   │   ├── build.gradle.kts                 # 构建配置 (签名/混淆/ProGuard)
│   │   └── src/main/
│   │       ├── AndroidManifest.xml           # 应用清单 (权限/Activity)
│   │       ├── res/
│   │       │   ├── values/                   # 字符串/主题资源
│   │       │   └── xml/
│   │       │       ├── network_security_config.xml  # HTTP 明文配置
│   │       │       └── file_paths.xml               # FileProvider 路径
│   │       └── java/com/omnicart/agent/
│   │           ├── MainActivity.kt           # 应用入口 (Coil + Compose)
│   │           ├── MainScreen.kt             # 主屏幕编排
│   │           ├── core/
│   │           │   ├── config/AppConfig.kt   # API 地址 + 超时配置
│   │           │   ├── model/                # 数据类 (Product/RecommendResponse/DecisionResult)
│   │           │   ├── network/              # Retrofit API 接口 (30+ 端点)
│   │           │   │   ├── OmniCartApi.kt    # REST API 定义
│   │           │   │   ├── ApiClient.kt      # OkHttp + Auth 拦截器
│   │           │   │   └── AgentStreamClient.kt  # SSE 流式客户端
│   │           │   └── theme/                # Material 3 主题 (Color/Type/Theme)
│   │           └── feature/
│   │               ├── chat/                 # 🫘 小O智能对话
│   │               │   ├── ChatScreen.kt     # 对话界面 (LazyColumn + 流式动画)
│   │               │   ├── ChatInputBar.kt   # 输入栏 (文字+图片+语音+⚡)
│   │               │   ├── ChatViewModel.kt  # 对话状态管理 (SSE/语音/Demo)
│   │               │   ├── ChatUiState.kt    # UI 状态定义
│   │               │   ├── MessageBubble.kt  # 消息气泡 (Markdown+商品卡片)
│   │               │   ├── ConversationListSheet.kt  # 历史对话列表
│   │               │   ├── VoiceInputOverlay.kt      # 语音录音浮层
│   │               │   └── VoiceRecorder.kt          # 录音器封装
│   │               ├── product/              # 商品展示
│   │               │   ├── ProductCard.kt    # 商品卡片
│   │               │   ├── ProductDetailSheet.kt  # 商品详情 BottomSheet
│   │               │   ├── ProductDetailScreen.kt  # 独立详情页
│   │               │   └── ProductImage.kt   # Coil 异步图片加载
│   │               ├── cart/                 # 🛒 购物车
│   │               │   ├── CartScreen.kt     # 购物车界面
│   │               │   └── CartViewModel.kt  # 购物车状态
│   │               ├── order/                # 📋 订单
│   │               │   ├── OrderScreen.kt    # 订单列表
│   │               │   └── OrderViewModel.kt # 订单状态
│   │               ├── address/              # 📍 收货地址
│   │               │   ├── AddressScreen.kt  # 地址表单
│   │               │   └── AddressViewModel.kt
│   │               ├── auth/                 # 🔐 登录注册
│   │               │   ├── LoginScreen.kt    # 登录界面
│   │               │   ├── AuthViewModel.kt  # 认证状态
│   │               │   └── AuthManager.kt    # Token 管理
│   │               ├── preference/           # ⚙ 购物偏好
│   │               │   ├── PreferenceScreen.kt   # 偏好设置
│   │               │   └── PreferenceViewModel.kt
│   │               ├── profile/              # 👤 个人中心
│   │               │   └── ProfileScreen.kt
│   │               ├── shop/                 # 📦 商品浏览
│   │               │   ├── ProductListScreen.kt    # 商品列表 (分类筛选)
│   │               │   └── ProductListViewModel.kt
│   │               ├── panel/                # 🔍 Agent 洞察面板
│   │               │   ├── AgentInsightSheet.kt       # 洞察面板入口
│   │               │   ├── AgentTracePanel.kt         # Agent 执行轨迹
│   │               │   ├── EvidencePanel.kt           # 证据追溯面板
│   │               │   ├── ScoreBreakdownPanel.kt     # 评分拆解面板
│   │               │   ├── SkillExecutionPanel.kt     # Skill 执行面板
│   │               │   └── HarnessValidationPanel.kt  # 安全验证面板
│   │               ├── demo/                 # 🎮 演示模式
│   │               │   ├── DemoModeSwitch.kt # 演示模式开关
│   │               │   ├── DemoScenarioSelector.kt  # 场景选择器
│   │               │   ├── MockDemoData.kt   # Mock 数据生成
│   │               │   └── PlusMenuSheet.kt  # 快捷菜单
│   │               └── upload/               # 📷 图片选择
│   │                   └── ImagePicker.kt    # Photo Picker 封装
│   ├── build.gradle.kts                     # 根构建文件
│   └── settings.gradle.kts                  # 项目设置
│
├── backend/                                  # FastAPI 后端 (Python 3.11)
│   ├── Dockerfile                            # 容器构建 (python:3.11-slim)
│   ├── entrypoint.sh                         # 容器入口 (迁移+启动)
│   ├── app/
│   │   ├── main.py                           # 应用入口 (路由注册+CORS+启动)
│   │   ├── agents/                           # 5 Agent 实现
│   │   │   ├── base.py                       # Agent 基类 (trace+card)
│   │   │   ├── router_agent.py               # Router: 意图+约束+计划 (LLM+规则)
│   │   │   ├── visual_agent.py               # Visual: 拍照识图+品类映射+DB匹配
│   │   │   ├── retrieval_agent.py            # Retrieval: 三通道并行检索+分块补充
│   │   │   ├── decision_agent.py             # Decision: 7维证据评分+硬约束过滤
│   │   │   └── response_agent.py             # Response: 流式生成+模板兜底+幻觉校验
│   │   ├── api/                              # 17 个路由模块
│   │   │   ├── health.py                     # GET /api/health + /api/cache/stats
│   │   │   ├── recommend.py                  # V0推荐 + V2工作流 + 约束引导
│   │   │   ├── agent_stream.py               # SSE 流式推荐 (主力端点 + 购物操作)
│   │   │   ├── products.py                   # 商品列表/详情/图片服务
│   │   │   ├── cart.py                       # 购物车 CRUD + 全选
│   │   │   ├── checkout.py                   # 模拟结算 + 订单列表
│   │   │   ├── auth.py                       # 注册/登录/Token
│   │   │   ├── address.py                    # 收货地址 CRUD
│   │   │   ├── conversation.py               # 对话历史管理
│   │   │   ├── preference.py                 # 会话偏好 (短期约束)
│   │   │   ├── user_profile.py               # 长期偏好条目 (解析/保存/管理)
│   │   │   ├── upload.py                     # 图片上传 (魔术字校验)
│   │   │   ├── voice.py                      # ASR 转写 + TTS 语音合成
│   │   │   ├── agent_actions.py              # Agent 受控操作 (加购)
│   │   │   ├── observability.py              # LLM 全链路追踪查询
│   │   │   ├── eval.py                       # Golden Query 评测运行
│   │   │   └── eval_dashboard.py             # Chart.js 可视化仪表盘
│   │   ├── workflow/                         # LangGraph 编排
│   │   │   ├── graph.py                      # StateGraph 构建+编译+缓存+执行
│   │   │   └── checkpoint.py                 # 工作流检查点持久化
│   │   ├── model_gateway/                    # Qwen 模型统一网关
│   │   │   ├── gateway.py                    # 能力→模型路由 + 缓存+限流
│   │   │   ├── qwen_chat.py                  # Chat (意图/生成)
│   │   │   ├── qwen_vision.py                # Vision (拍照识图)
│   │   │   ├── qwen_embedding.py             # Embedding (1024d 向量化)
│   │   │   ├── qwen_reranker.py              # Reranker (语义精排)
│   │   │   ├── qwen_omni.py                  # Omni (ASR + TTS)
│   │   │   └── mock_model.py                 # Mock 模式 (无 API Key 可用)
│   │   ├── services/                         # 业务服务层
│   │   │   ├── conversation_service.py       # 短期上下文 (constraints/追问/产品引用)
│   │   │   ├── user_profile_service.py       # 长期偏好 (LLM解析+品类注入+条目管理)
│   │   │   ├── followup_engine.py            # 7 种追问模式统一检测
│   │   │   ├── context_compressor.py         # 对话历史增量压缩
│   │   │   ├── context_builder.py            # V1 上下文构建器
│   │   │   └── constraint_guide.py           # 约束引导式推荐引擎
│   │   ├── retrieval/                        # 检索模块
│   │   │   ├── text_retriever.py             # 文本语义检索 + 分块检索
│   │   │   ├── semantic_retriever.py         # 语义检索封装
│   │   │   └── llm_evaluator.py              # LLM 证据评估器
│   │   ├── decision/                         # 评分模块
│   │   │   ├── scoring.py                    # 7 维加权评分公式
│   │   │   ├── evidence_metrics.py           # 证据指标计算
│   │   │   └── rules.py                      # 共享规则 (品类/预算/场景/品牌别名)
│   │   ├── verification/                     # 安全验证
│   │   │   ├── response_guard.py             # 回答守门 (品牌/价格/风险/证据 4道防线)
│   │   │   └── evidence_checker.py           # 证据充足性检查
│   │   ├── repositories/                     # 数据仓库 (PG + 内存双实现)
│   │   │   ├── product_repo.py               # 商品仓库入口
│   │   │   ├── pg_product_repo.py            # PG 商品实现
│   │   │   ├── json_product_repo.py          # JSON 商品实现
│   │   │   ├── pg_cart_repo.py               # PG 购物车
│   │   │   ├── user_repo.py                  # 用户仓库
│   │   │   ├── address_repo.py               # 地址仓库
│   │   │   ├── conversation_repo.py          # 对话仓库
│   │   │   ├── user_preference_repo.py       # 偏好条目仓库
│   │   │   ├── base_product_repo.py          # 商品仓库抽象
│   │   │   ├── base_vector_repo.py           # 向量仓库抽象
│   │   │   ├── qdrant_vector_repo.py         # Qdrant 向量实现
│   │   │   ├── stub_vector_repo.py           # 本地降级向量实现
│   │   │   └── vector_repo.py                # 向量仓库入口
│   │   ├── models/                           # SQLAlchemy ORM (7 表)
│   │   │   ├── product.py                    # products 表
│   │   │   ├── user.py                       # users 表
│   │   │   ├── conversation.py               # conversations + conversation_messages
│   │   │   ├── cart_item.py                  # cart_items 表
│   │   │   ├── order.py                      # orders 表
│   │   │   ├── address.py                    # addresses 表
│   │   │   └── user_preference_entry.py      # user_preference_entries 表
│   │   ├── schemas/                          # Pydantic 数据模型
│   │   │   ├── product.py                    # Product / Sku / RagKnowledge
│   │   │   ├── workflow.py                   # WorkflowState / Constraints / RetrievalPlan
│   │   │   ├── decision_result.py            # DecisionResult (7维分数字段)
│   │   │   ├── evidence_metrics.py           # EvidenceMetrics / EvidenceProfile
│   │   │   ├── a2a.py                        # Agent Card (A2A 协议)
│   │   │   ├── cart.py                       # Cart / CartItem
│   │   │   ├── auth.py                       # Auth Request/Response
│   │   │   ├── address.py                    # Address CRUD
│   │   │   ├── conversation.py               # Conversation / Message
│   │   │   ├── preference.py                 # Preference Update
│   │   │   └── visual.py                     # VisualResult
│   │   ├── core/                             # 基础设施
│   │   │   ├── config.py                     # 环境变量配置 (26个配置项)
│   │   │   ├── database.py                   # PostgreSQL async 连接
│   │   │   ├── cache.py                      # Redis 缓存封装 (四级 TTL)
│   │   │   ├── qdrant_client.py              # Qdrant 向量库客户端
│   │   │   └── redis_client.py               # Redis 客户端 + 健康检查
│   │   ├── context/                          # 上下文编译
│   │   │   └── compiler.py                   # Context Compiler (决策结果→LLM Prompt)
│   │   ├── observability/                    # 可观测性
│   │   │   ├── collector.py                  # LLM Span 收集器
│   │   │   └── rag_logger.py                 # RAG 全链路日志
│   │   └── eval/                             # 评测指标
│   │       └── metrics.py                    # Recall@K / MRR / NDCG@K
│   └── tests/                                # 后端测试 (13个)
│       ├── unit/                             # 单元测试 (agents/rules/scoring/retriever/profile)
│       ├── integration/                      # 集成测试 (recommend/sse/upload/workflow)
│       ├── eval/                             # 评测数据
│       └── manual/                           # 手动测试
│
├── ecommerce_agent_dataset/                  # 商品数据集 (105件 / 4品类 / 39子类)
│   ├── 1_美妆护肤/images/                    # 美妆护肤商品图片
│   ├── 2_数码电子/images/                    # 数码电子商品图片
│   ├── 3_服饰运动/images/                    # 服饰运动商品图片
│   └── 4_食品饮料/images/                    # 食品饮料商品图片
│
├── data/                                     # 数据目录
│   ├── mock_products.json                    # Mock 商品数据 (PG 降级用)
│   ├── golden_queries.json                   # 评测 Golden Query (10条)
│   ├── eval_queries.json                     # 评测查询集
│   ├── eval_runs/                            # 历史评测结果
│   └── uploads/                              # 用户上传图片/语音/APK
│
├── scripts/                                  # 工具脚本 (15个)
│   ├── seed_postgresql.py                    # PostgreSQL 建表+播种
│   ├── seed_qdrant.py                        # Qdrant 向量索引建立
│   ├── index_products.py                     # 商品 Embedding 索引
│   ├── index_product_chunks.py               # 分块 Embedding 索引
│   ├── smoke_recommend.py                    # 推荐接口冒烟测试
│   ├── smoke_test_v2.py                      # V2 工作流冒烟测试
│   ├── run_baseline.py                       # 评测基线运行
│   ├── rag_stats.py                          # RAG 检索统计
│   ├── dump_audit.py                         # 审计日志导出
│   ├── clean_db.py                           # 数据库清理
│   └── ...
│
├── docs/                                     # 项目文档 (11份)
│   ├── OMNICART_AGENT_COMPLETE_BLUEPRINT.md  # 完整蓝图 (最终设计)
│   ├── AGENT_COLLABORATION.md                # 5 Agent 协同设计
│   ├── RAG_PIPELINE.md                       # RAG 全链路详解
│   ├── MEMORY_SYSTEM.md                      # 三层记忆系统
│   ├── SCORING_SYSTEM_COMPLETE_REFERENCE.md  # 评分体系完整参考
│   ├── DATABASE_DESIGN.md                    # 数据库设计
│   ├── CHANGELOG.md                          # 变更日志
│   ├── KNOWLEDGE_LOG.md                      # 知识总结
│   ├── DEVELOPMENT_PROGRESS.md               # 开发进度
│   ├── DEVELOPMENT_RULES.md                  # 开发规范
│   └── 答辩QA手册.md                         # 答辩问答准备
│
├── alembic/                                  # 数据库迁移
│   ├── env.py                                # Alembic 环境配置
│   └── versions/                             # 迁移脚本
├── alembic.ini                               # Alembic 配置
│
├── docker-compose.yml                        # Docker 四服务编排
├── requirements.txt                          # Python 依赖 (18个包)
├── .env                                      # 环境变量 (本地)
├── .env.docker                               # 环境变量 (Docker 模板)
├── CLAUDE.md                                 # Claude Code 项目指令
├── DEPLOY.md                                 # 部署指南
├── SERVER_OPS.md                             # 服务器运维手册
├── douzai.png                                # 小O Logo
├── 小O.apk                                  # Release APK 安装包
└── README.md                                 # 本文件
```

**代码统计：** 87 个 Python 文件 · 50 个 Kotlin 文件 · 13 个测试文件 · 15 个脚本 · 11 份文档

---

## 环境与配置

### 依赖环境

| 层次 | 依赖 | 版本要求 | 说明 |
|------|------|----------|------|
| **运行时** | Python | 3.11+ | 后端运行环境 |
| | Docker + Compose | 24+ / v2 | 容器化部署（推荐） |
| | JDK | 17+ | Android APK 构建 |
| **数据库** | PostgreSQL | 16 | 商品/用户/会话/订单持久化（可降级为 JSON 文件） |
| | Qdrant | latest | 向量检索引擎（可降级为本地 Embedding 缓存） |
| | Redis | 7 | 四级缓存（可降级禁用） |
| **AI 模型** | Qwen API Key | — | 阿里云 DashScope，Mock 模式可免 Key 运行 |
| **Python 包** | 见 requirements.txt | 18 个 | FastAPI / LangGraph / SQLAlchemy / Qdrant / Redis / OpenAI SDK |

> **降级策略：** 三项基础设施（PostgreSQL / Qdrant / Redis）均支持优雅降级。不配置时自动切换为 JSON 文件模式 + 本地缓存 + 无缓存模式，Mock 模式无需任何外部依赖即可运行全部功能。

### 配置说明

所有配置通过 `.env` 环境变量管理，无硬编码。项目提供 4 个环境模板：

| 文件 | 用途 |
|------|------|
| `.env.example` | V0 最小配置模板（参考用，变量已过期，建议看 `.env.local`） |
| `.env.local` | 本地完整开发环境（连接本地 PostgreSQL/Qdrant/Redis） |
| `.env.docker` | Docker 部署模板（服务名代替 localhost，`cp .env.docker .env` 后使用） |
| `.env` | 实际生效配置（`.gitignore` 排除，不提交） |

**核心配置项：**

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OMNICART_PORT` | `8006` | 后端服务端口 |
| `OMNICART_MOCK_MODE` | `true` | `true` = 无需 API Key，使用内置 Mock 数据；`false` = 调用真实 Qwen API |
| `OMNICART_FAST_MODE` | `false` | `true` = 跳过 LLM，模板秒回 |
| `QWEN_API_KEY` | — | 阿里云 DashScope API Key（Mock 模式下可不填） |
| `QWEN_BASE_URL` | `https://dashscope.aliyuncs.com/api/v1` | Qwen API 地址 |
| `DATABASE_URL` | — | PostgreSQL 连接串（`postgresql+asyncpg://...`）。留空自动降级 JSON 文件 |
| `QDRANT_URL` | — | Qdrant 服务地址（`http://host:6333`）。留空自动降级本地缓存 |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis 连接串。留空则禁用缓存 |
| `EMBEDDING_DIMENSION` | `1024` | 向量维度（text-embedding-v4） |
| `OMNICART_DEFAULT_TOP_K` | `10` | 检索返回商品数 |
| `OMNICART_ENABLE_DECISION_LLM` | `false` | LLM 证据评估开关（实验功能，默认关闭） |
| `OMNICART_ENABLE_EVIDENCE_SCORING` | `true` | 证据驱动评分开关 |
| `OMNICART_USE_CHUNKED_INDEX` | `false` | 分块索引开关 |
| `REDIS_CACHE_TTL_VISUAL` | `3600` | 视觉识别缓存时间（秒） |
| `REDIS_CACHE_TTL_SEARCH` | `300` | 搜索结果缓存时间（秒） |
| `REDIS_CACHE_TTL_REWRITE` | `1800` | LLM 关键词改写缓存时间（秒） |
| `REDIS_CACHE_TTL_WORKFLOW` | `300` | 工作流结果缓存时间（秒） |

**本地开发最小配置（`.env`）：**
```bash
OMNICART_PORT=8006
OMNICART_MOCK_MODE=true                      # 无需 API Key
DATABASE_URL=postgresql+asyncpg://omnicart:omnicart@localhost:5432/omnicart
QDRANT_URL=http://localhost:6333
REDIS_URL=redis://localhost:6379/0
```

**Docker 部署最小配置（`cp .env.docker .env` 后修改）：**
```bash
QWEN_API_KEY=sk-your-real-key-here           # 必填！
OMNICART_MOCK_MODE=false
DATABASE_URL=postgresql+asyncpg://omnicart:omnicart@postgres:5432/omnicart  # host=服务名
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379/0
```

> **注意：** Docker 容器内 PostgreSQL / Qdrant / Redis 通过服务名互通（`postgres` / `qdrant` / `redis`），本地裸机开发改为 `localhost`。

---

## 快速开始

### 方式一：Docker 一行起跑（推荐）

```bash
# 1. 克隆仓库
git clone <repo-url> && cd OmniCart-Agent

# 2. 配置 API Key
cp .env.docker .env
# 编辑 .env → 填入 QWEN_API_KEY=你的密钥
# 若无密钥，保持 OMNICART_MOCK_MODE=true 也能跑

# 3. 一行启动
docker compose up -d

# 4. 初始化数据（仅首次）
docker compose exec backend python scripts/seed_postgresql.py
docker compose exec backend python scripts/index_products.py

# 5. 验证
curl http://localhost:8006/api/health
# → {"status":"ok","service":"omnicart-agent","version":"2.0.0","redis":"connected"}
```

### 方式二：本地 Python 开发

```bash
# 安装依赖
pip install -r requirements.txt

# 启动后端
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8006

# 验证
curl http://localhost:8006/api/health
```

### 方式三：直接安装 APK

下载并安装 APK（已配置连接服务器 8.137.187.54:8006）：

```
http://8.137.187.54:8006/api/uploads/douzai.apk
```

或本地构建：

```bash
cd android-client
./gradlew assembleRelease
adb install app/build/outputs/apk/release/app-release.apk
```

---

## Agent 协同

> 详见 [docs/AGENT_COLLABORATION.md](docs/AGENT_COLLABORATION.md)

5 个 Agent 通过 LangGraph StateGraph 编排为有向无环图，共享 `WorkflowState` 状态对象：

| Agent | 模型 | 核心职责 | 输入 | 输出 |
|-------|------|----------|------|------|
| **Router** | qwen-turbo + 规则 | 意图识别、品类/预算/场景约束提取、检索计划生成 | user_query | intent + Constraints + RetrievalPlan |
| **Visual** | qwen-vl-max | 拍照识图、品类映射(80+映射表)、DB 精确匹配 | image_url + user_query | VisualResult + visual_matched_pids |
| **Retrieval** | text-embedding-v4 | 三通道并行检索(text/review/policy) + 分块证据补充 + LLM 关键词改写 | plan + constraints | products[] + evidence[] |
| **Decision** | 规则公式 + LLM(可选) | 7 维证据加权评分 + 硬约束过滤 + 避雷检测 | products + evidence | decision_results[] |
| **Response** | qwen-turbo + 模板 | LLM 流式生成 + 6s 超时兜底 + 幻觉校验 + 对比/闲聊模式 | decision_results + context | answer (SSE stream) |

**性能优化：**
- Router 和 Visual 有图片时**并行执行**，节省 ~2s 延迟
- 品类 + 子品类预填时 Router **跳过 LLM**，只用规则解析
- 快速模式 (`OMNICART_FAST_MODE=true`) 跳过全部 LLM，模板秒回
- LLM 关键词改写结果 **Redis 缓存 30 分钟**
- Workflow 结果 **Redis 缓存 5 分钟**（相同 query+image 直接返回）

---

## RAG 全链路

> 详见 [docs/RAG_PIPELINE.md](docs/RAG_PIPELINE.md)

```
用户输入: "推荐一款蓝牙耳机，500以内"
    │
    ▼
┌─ FollowUpEngine ──────────────────────────────────────────────┐
│  检测追问模式 → 无追问 (首轮) → 构建 context_prompt → 透传     │
└──────────────────────────┬───────────────────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │  Router (LLM + 规则)                         │
    │  intent=recommend, category=数码电子         │
    │  sub_category=真无线耳机, budget_max=500     │
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │  Retrieval: LLM 关键词改写                   │
    │  "推荐蓝牙耳机 数码电子 真无线耳机"           │
    │        │                                     │
    │        ▼                                     │
    │  text-embedding-v4 → 1024d 向量              │
    │        │                                     │
    │        ▼                                     │
    │  Qdrant ANN 余弦相似度 → Top-K               │
    │        │                                     │
    │        ▼                                     │
    │  品类/价格过滤 (数码电子 + ≤500)             │
    │        │                                     │
    │        ▼                                     │
    │  Qwen3-Reranker 语义精排 (0.68+0.38*score)   │
    │        │                                     │
    │        ▼                                     │
    │  分块证据补充 (faq/rev chunk 语义搜索)        │
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │  EvidenceCheck: 证据充足性校验               │
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │  Decision: 7 维证据加权评分                  │
    │  0.45×relevance + 0.20×budget_fit           │
    │  + 0.12×user_sat + 0.10×value_score         │
    │  + 0.08×spec_quality + 0.05×scenario_fit    │
    │  + preference_bonus - risk_penalty           │
    │  - avoid_penalty                             │
    │        │                                     │
    │        ▼                                     │
    │  recommend_level: strong_recommend/recommended│
    │  /cautious/insufficient_evidence              │
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │  Response: LLM 流式生成 + 6s 超时模板兜底    │
    │  "嘿嘿～小O来安利..."  (SSE token 逐字输出) │
    └──────────────────────┬──────────────────────┘
                           │
    ┌──────────────────────▼──────────────────────┐
    │  Guard: 品牌验证 + 价格准确 + 风险覆盖       │
    │  → 持久化 conversation + 上下文压缩          │
    └─────────────────────────────────────────────┘
```

**评测指标（10 Golden Queries）：** Recall@10 · MRR · NDCG@10 · Category Accuracy · P95 Latency

---

## 评分体系

> 详见 [docs/SCORING_SYSTEM_COMPLETE_REFERENCE.md](docs/SCORING_SYSTEM_COMPLETE_REFERENCE.md)

OmniCart 的评分系统采用 **RAG 证据驱动** 设计：检索召回的证据直接参与评分，不依赖 LLM 主观判断。每件商品产出可解释的 7 维分解分 + 权重 + 推荐等级 + 风险提示。

### 评分公式

```
raw_score = 0.45 × relevance          # RAG 语义相关度 (reranker_score / embedding 余弦相似度)
          + 0.20 × budget_fit         # 价格合适度 (预算内满分 / 超出梯度扣分)
          + 0.12 × user_sat           # 用户口碑 (评论均分 Bayesian 平滑 + 好评文本关键词加成)
          + 0.10 × value_score        # 性价比 (品质分/价格分 × 子品类系数)
          + 0.08 × spec_quality       # 规格品质 (LLM spec_keywords 匹配 / 描述文本规格密度)
          + 0.05 × scenario_fit       # 场景适配 (场景关键词匹配 / 文本 bigram 命中)
          + preference_bonus          # 偏好加成 (品牌/品类/场景匹配记忆, 上限 +0.10)
          - risk_penalty              # 风险扣分 (差评数/综合低分, 上限 -0.20)
          - avoid_penalty             # 避雷惩罚 (命中避雷标签, 上限 -0.10)

final_score = clamp(raw_score, 0.0, 1.0)
display_score = round(final_score × 10, 1)   →  0.0 ~ 10.0
```

### 7 维分解（component_scores）

每件商品返回 `component_scores` 字典，每个维度标注分数、权重、计算方法和支撑证据 ID：

| 维度 | 权重 | 计算方法 | 说明 |
|------|:----:|------|------|
| **relevance** | 0.45 | Reranker 分数校准 (0.68+0.38×score) + 子品类 bigram 命中加成 | 语义相关度，权重最高 |
| **budget_fit** | 0.20 | 价格在预算内 → 0.92~0.98；超出 → 梯度扣分至 0.45 | 无预算约束时默认 0.98 |
| **user_sat** | 0.12 | 评论均分/5.0 → Bayesian 平滑(C=3, prior=0.80) + 好评关键词 + 评论数量微奖励 | 无评论不惩罚(0.80) |
| **value_score** | 0.10 | 品质分×0.5 + 价格分×0.5 → 子品类 quality_multiplier 校准 | 39 个子品类独立基准价 |
| **spec_quality** | 0.08 | LLM spec_keywords 命中计数 (+0.08~0.12/词) / 规格信号密度自动评分 | 零字典兜底，品类无关 |
| **scenario_fit** | 0.05 | 场景关键词命中 + 文本 bigram 匹配 | 12 场景 × 动态关键词库 |
| **risk_penalty** | — | 差评数≥3 → -0.08；综合评分<3.0 → -0.05 | 绑定风险证据 ID |

### 推荐等级（recommendation_level）

| 等级 | 条件 | 含义 |
|------|------|------|
| **strong_recommend** | final_score ≥ 0.80 且 evidence_confidence ≥ 0.50 且 risk_penalty < 0.10 | 强烈推荐，证据充足 |
| **recommended** | final_score ≥ 0.65 | 值得推荐 |
| **cautious** | final_score ≥ 0.55 或 risk_penalty ≥ 0.20 | 谨慎考虑，有风险提示 |
| **insufficient_evidence** | evidence_confidence < 0.25 | 证据不足，仅供参考 |
| **not_recommended** | 硬约束失败 或 final_score < 0.55 | 不推荐 |

### 证据可信度（evidence_confidence）

独立于评分公式，衡量**证据质量本身**的可信度。由 6 个子指标加权合成：

```
evidence_confidence = 0.25 × evidence_relevance    # 检索/精排信号强度
                    + 0.20 × source_coverage       # 证据类型覆盖度 (是否覆盖 required groups)
                    + 0.20 × aspect_coverage       # 用户关注的方面是否有证据支撑
                    + 0.15 × source_quality        # 证据来源权威度 (FAQ > 评论 > 营销)
                    + 0.10 × source_reliability    # 来源可靠性
                    + 0.10 × evidence_consistency  # 证据一致性 (正负评论共存 → 降权)
```

### 设计原则

- **RAG 驱动**：relevance 来自 Reranker 精排分数，不依赖 LLM。LLM 评估可选（默认关闭），仅作为补充
- **证据绑定**：每个维度产出 `evidence_ids`，可追溯到具体评论/FAQ/营销描述
- **商业校准**：Reranker 分数经固定校准曲线（0.68+0.38×score），确保商业可读的分数区间
- **子品类感知**：39 个子品类独立基准价和品质系数，避免"口红和手机用同一套标准"
- **避雷双重保障**：检索层硬过滤（`exclude_tags`）+ 评分层降权（`avoid_penalty`），防止偏好系统中的避雷品牌漏网
- **Bayesian 平滑**：用户口碑评分采用 C=3 虚拟评论 + prior=0.80，避免"1条5星好评=满分"的冷启动问题

---

## 记忆系统

> 详见 [docs/MEMORY_SYSTEM.md](docs/MEMORY_SYSTEM.md)

```
┌─────────────────────────────────────────────────────┐
│                  三层记忆架构                         │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │  短期记忆 (context_snapshot JSONB, TTL 2h)   │     │
│  │  · 品类/预算/场景约束累积                     │     │
│  │  · 上轮商品引用 (序数/品牌指代)              │     │
│  │  · pending_question (问答链)                 │     │
│  │  · 话题切换自动清空旧约束                    │     │
│  └────────────────────┬────────────────────────┘     │
│                       │                               │
│  ┌────────────────────▼────────────────────────┐     │
│  │  长期记忆 (user_preference_entries, 持久)    │     │
│  │  · 条目化管理 (每品类独立条目)               │     │
│  │  · LLM 解析 → 品类+品牌+场景+预算+避雷      │     │
│  │  · 品类感知注入 (query检测→仅注入匹配条目)   │     │
│  │  · 启用/禁用开关 + 独立删除                  │     │
│  └────────────────────┬────────────────────────┘     │
│                       │                               │
│  ┌────────────────────▼────────────────────────┐     │
│  │  会话记忆 (conversations + messages, 持久)   │     │
│  │  · 对话历史完整持久化                        │     │
│  │  · 商品引用 + 证据引用关联                   │     │
│  │  · LLM 自动标题生成 (8字以内)               │     │
│  │  · 上下文增量压缩 (conversation_summary)     │     │
│  │  · 跨设备恢复 (conversation_id)              │     │
│  └─────────────────────────────────────────────┘     │
│                                                       │
│  ┌─────────────────────────────────────────────┐     │
│  │  FollowUpEngine (统一追问检测)               │     │
│  │  ① 序数指代: "第二个怎么样"                  │     │
│  │  ② 品牌引用: "Sony那个"                      │     │
│  │  ③ 上次引用: "刚才那个能上飞机吗"            │     │
│  │  ④ 预算更新: "换成200以内的"                 │     │
│  │  ⑤ 购物车意图: "加入购物车"                  │     │
│  │  ⑥ 对比意图: "和刚才那个比"                  │     │
│  │  ⑦ 模糊追问: "便宜一点" (继承品类)           │     │
│  └─────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

---

## 关键问题与解决方案

> 以下是构建多模态购物导购 Agent 过程中遇到的 10 个核心设计问题，以及基于实际代码的解决方案。

### 1. 多 Agent 如何有序协作不混乱？

**挑战：** 5 个 Agent 各有独立职责（意图、视觉、检索、评分、回复），若采用开放式 ReAct 循环，Agent 之间自由调用会导致调用链不可控、调试困难、token 消耗大。

**方案：** 采用 **LangGraph StateGraph 有向图编排**，非开放式 ReAct。流程固定为 `Router → Visual(并行) → Retrieval → Reranker → EvidenceCheck → Decision → Response → Guard → END`。统一 `WorkflowState` 在节点间传递，每个节点只读取和写入自己负责的字段，不会互相覆盖。

关键优化：
- `graph.py` `_node_router` — Router 和 Visual **并行执行**（有图片时 `asyncio.create_task`），节省约 2s
- `router_agent.py` `execute` — 品类+子品类预填时**跳过 Router LLM**，仅用规则解析
- `graph.py` `_node_reranker` — 视觉精确匹配商品**直接置顶 0.99**，不被 Reranker 覆盖
- 闲聊意图（`intent == "chitchat"`）**跳过检索和评分**，直接到 Response

**效果：** Agent 协作路径完全可预测、可调试。`trace_steps` 记录每个节点的输入/输出/耗时/状态，前端 AgentTracePanel 可视化展示。

### 2. 自然语言到精准商品的语义鸿沟？

**挑战：** 用户说"推荐一款蓝牙耳机500以内"，系统需要：理解这是推荐意图、抽取品类（数码电子）、子品类（真无线耳机）、预算上限（500元）、场景（通勤）——然后从 105 件商品中找出最匹配的 Top 5。

**方案：** 5 步检索链路，逐级缩小语义差距：

1. **LLM 关键词改写** — `retrieval_agent.py` `_llm_extract_keywords`："推荐一款蓝牙耳机500以内" → "蓝牙耳机 真无线耳机 降噪 500元"，结果 **Redis 缓存 30 分钟**
2. **Embedding 向量化** — `qwen_embedding.py`：text-embedding-v4 → 1024d 向量
3. **Qdrant ANN 搜索** — `qdrant_vector_repo.py`：余弦相似度 Top-K，支持 `product_chunks` 分块检索（`text_retriever.py` `search_chunked`）
4. **品类/价格过滤** — `text_retriever.py`：`category/sub_category/price_max/price_min` 硬过滤
5. **Qwen3-Reranker 精排** — `graph.py` `_node_reranker`：校准公式 `0.68 + 0.38 × score`，视觉匹配商品置顶 0.99

子品类无结果时自动放宽（`retrieval_agent.py` `_text_channel`：`sub_cat` → `None` 重试）。检索结果不足 3 件时，触发分块证据补充搜索（`_supplementary_evidence_search`）。

**效果：** 口语查询 → 精准商品匹配，全链路可追踪（`rag_logger.py` 记录 embedding→reranker→final 三段日志）。

### 3. 评分如何可解释而非黑盒？

**挑战：** 传统推荐系统输出一个分数，用户不知道为什么。购物场景需要明确告知：推荐理由、风险提示、证据来源。

**方案：** 6 维加权公式，每维独立计算 + 绑定证据 ID，参见 [评分体系](#评分体系) 章节。

关键设计决策：
- `scoring.py` — **RAG 驱动而非 LLM 驱动**。relevance 来自 Reranker 分数，LLM 评估可选（`ENABLE_DECISION_LLM=false` 默认关闭）
- `evidence_metrics.py` — 证据可信度独立计算（6 子指标），与评分公式解耦
- **Bayesian 平滑**（`_calc_user_satisfaction`）：C=3 虚拟评论 + prior=0.80，避免"1 条 5 星 = 满分"
- **39 个子品类独立基准价**（`CATEGORY_BENCHMARKS`），避免"口红和手机用同一套标准"

**效果：** 每件商品产出 `component_scores`（7 维分解 + 权重 + 证据 ID）+ `recommendation_reason` + `risk_factors`，前端 ScoreBreakdownPanel 可视化展示。

### 4. 多轮对话如何记住上下文？

**挑战：** 用户说"第二个便宜的有吗"，系统必须知道"第二个"指上一轮推荐的哪件商品、"便宜"在当前品类下的价格区间是什么。

**方案：** 三层记忆架构 + FollowUpEngine 统一追问检测，参见 [记忆系统](#记忆系统) 章节。

关键设计决策：
- `followup_engine.py` — **7 种追问模式统一检测**，按优先级：序数指代 → 品牌引用 → 上次引用 → 预算更新 → 购物车意图 → 对比意图 → 模糊追问
- `conversation_service.py` `merge_constraints` — **话题切换检测**：品类变化时自动清空旧约束，防止"上次搜 T 恤，这次搜耳机"品类泄漏
- `router_agent.py` `_build_session_context` — **问答链**：小O问了问题 + 用户简短回答"好"→ 从 `pending_question` 推断搜索意图
- `context_compressor.py` — 对话增量压缩为 `conversation_summary`，异步执行不阻塞 SSE

**效果：** 用户可连续 10+ 轮对话，系统正确理解指代、继承约束、感知话题切换。对话标题 LLM 自动生成。

### 5. 如何防止 AI 幻觉？

**挑战：** LLM 可能编造不存在的品牌、价格、商品名。购物场景下"推荐一个根本不存在的产品"比"不知道"糟糕得多。

**方案：** 四层防线：

1. **强制引用约束** — `response_agent.py` `_answer_cites_products`：LLM 回答必须包含至少一个候选商品的品牌或标题片段，否则**回退到模板**
2. **品牌白名单** — `response_guard.py` `_KNOWN_BRANDS`：65 个品牌列表，检测到陌生品牌 → 标记 `hallucination`
3. **价格准确检查** — `response_guard.py` `_check_price`：回答中的价格必须与候选商品一致
4. **6s 超时模板兜底** — `response_agent.py` `_generate_with_llm_fallback`：`asyncio.wait_for(timeout=6.0)` → 超时或异常 → 结构化模板

**效果：** 幻觉四道防线覆盖品牌/价格/证据/超时四个维度。`harness_report` 汇总所有检查结果，前端 HarnessValidationPanel 可视化。

### 6. 数据库架构如何支撑 Agent 全链路？

**挑战：** Agent 系统需要同时管理商品数据、用户会话、向量检索、高频缓存——单一数据库无法满足所有场景。

**方案：** 三库分立，各司其职：

**PostgreSQL — 结构化数据（7 表）：**

| 表 | 用途 | 关键字段 |
|------|------|------|
| `products` | 商品主数据 | product_id / title / brand / category / base_price / skus(JSONB) / rag_knowledge(JSONB) |
| `users` | 用户账户 | user_id / username / password_hash / token |
| `conversations` | 对话会话 | conversation_id / user_id / context_snapshot(JSONB) / title / summary |
| `conversation_messages` | 对话消息 | message_id / conversation_id / role / content / product_refs(JSONB) / evidence_refs(JSONB) |
| `cart_items` | 购物车 | cart_item_id / user_id / product_id / sku_id / quantity / selected |
| `orders` | 订单记录 | order_id / user_id / items(JSONB) / total_price / status |
| `user_preference_entries` | 长期偏好 | entry_id / user_id / category / brands(JSONB) / avoid_tags(JSONB) / budget_min/max / enabled |

**Qdrant — 向量检索（双集合）：**
- `products` 集合：商品级向量（1024d COSINE），承载主检索链路
- `product_chunks` 集合：分块级向量（FAQ / 评论 / 描述），承载证据补充和深度匹配
- `qdrant_client.py` `init_qdrant` — collection 不存在时自动创建
- `qdrant_vector_repo.py` — `query_points` ANN 搜索 + 分数阈值过滤

**Redis — 四级缓存（透明降级）：**
- `cache.py` `cached` — get-or-compute 模式，Redis 不可用时**自动穿透到 factory**
- 视觉识别缓存：1h（`REDIS_CACHE_TTL_VISUAL`）
- 搜索结果缓存：5min（`REDIS_CACHE_TTL_SEARCH`）
- LLM 改写缓存：30min（`REDIS_CACHE_TTL_REWRITE`）
- Workflow 结果缓存：5min（`REDIS_CACHE_TTL_WORKFLOW`）

**效果：** 三库各司其职——PG 管业务数据、Qdrant 管向量检索、Redis 管热缓存。任一不可用时系统自动降级，不中断服务。

### 7. 模糊意图如何匹配精准商品？

**挑战：** 用户说"送女朋友礼物"——没有品类、没有预算、没有品牌偏好。传统关键词搜索几乎不可能返回有用结果。

**方案：** 四维约束提取 + 多级放宽 + 品牌别名：

1. **规则提取** — `rules.py` `detect_category` / `detect_budget` / `detect_scenario` / `detect_sub_category`：词库匹配 4 品类 + 42 子品类 + 金额正则 + 场景关键词
2. **LLM 增强** — `router_agent.py` `execute`：LLM 和规则结果**合并**（LLM 补充场景关键词、规格关键词），但高置信度规则意图（闲聊/风险检查/购物操作）**不被 LLM 覆盖**
3. **子品类自动放宽** — `retrieval_agent.py` `_text_channel`：`sub_category` 检索无结果 → 自动退为 `None` 重试
4. **品牌别名** — `rules.py` `BRAND_ALIASES`：60+ 品牌中英双向映射，"不要 Nike" → 同时排除 "Nike" 和 "耐克"
5. **约束引导推荐** — `recommend.py` `/api/recommend/guide`：品类→子品类→预算，多轮追问逐步缩小范围

**效果：** 即使"送女朋友礼物"这种零信息输入，也能通过多轮引导锁定品类和预算，最终给出推荐。

### 8. 文字 + 图片双模态如何有效融合？

**挑战：** 用户拍照 + 文字"有类似这个但便宜点的吗"，视觉识别结果和文本约束来自两个独立 Agent，需要正确合并而非简单拼接。

**方案：** 并行执行 + 分层融合：

1. **并行执行** — `graph.py` `_node_router`：Router 和 Visual **同时启动**（`asyncio.create_task`），互不阻塞
2. **视觉品类映射** — `graph.py` `_map_visual_category`：80+ 子品类 → 大类映射表，"粉底液"→"美妆护肤"
3. **品类覆盖策略** — `_node_visual`：高置信度（≥0.2）时，视觉结果注入 `search_query`；**以视觉为准**覆盖 constraints.category/sub_category
4. **精确匹配置顶** — 高置信度（≥0.5）时，品牌+标题滑窗在 DB 中搜索 → `visual_matched_pids` → 钉在检索结果顶部 + 分数设为 0.99
5. **低置信度降级** — 置信度 < 0.5 时跳过精确匹配，走同类推荐

**效果：** 拍照识图 + 文字追问二合一。视觉提供品类锚点，文字提供预算/偏好约束，两者并行不串行。

### 9. 外部依赖不可靠时如何保障可用？

**挑战：** Qwen API 超时、PostgreSQL 断开、Qdrant 不可用、Redis 挂了——任何一个故障都可能导致整个推荐链路中断。

**方案：** 三级降级策略，每层独立：

| 依赖 | 正常 | 降级方案 | 代码 |
|------|------|----------|------|
| **PostgreSQL** | asyncpg 连接池 | JSON 文件读写（`json_product_repo.py`） | `main.py` `on_startup` |
| **Qdrant** | ANN 向量搜索 | 本地 Embedding 缓存 JSON（`stub_vector_repo.py`） | `retrieval_agent.py` `_supplementary_evidence_search` |
| **Redis** | 四级缓存 | 透传 factory（`cache.py` `cached` Redis=None 分支） | `redis_client.py` `get_redis` |
| **LLM** | Qwen API 调用 | 模板兜底（6s 超时） / Mock 全离线模式 | `response_agent.py` / `mock_model.py` |

- `main.py` `on_startup` — 每项依赖独立 try/except，一个失败不影响其他
- `cache.py` `cached` — `if redis is None: return await factory()` 透明穿透
- `graph.py` `_node_reranker` — reranker 异常直接跳过，不阻塞链路
- `OMNICART_MOCK_MODE=true` — 全链路 Mock 数据，无需任何外部依赖即可运行

**效果：** 单项故障不扩散。Mock 模式下零依赖可运行全部功能，适合评委本地体验。

### 10. 对话如何直接转化为下单？

**挑战：** 传统 AI 客服只能聊天，用户需要切换到购物车页面手动操作。OmniCart 的目标是**自然语言驱动完整购物闭环**——从推荐到下单不离开对话界面。

**方案：** SSE 流式端点内购物操作分流 + 自然语言参数解析：

1. **意图分流** — `agent_stream.py`：进入 SSE 前先检测购物操作关键词（下单/加购/删除/清空/修改地址），命中则**分流到购物流程**，不走进 Agent Workflow
2. **中文序数指代解析** — `agent_stream.py` `_parse_ordinal`："删除第二个"→ 正则提取"二"→ 映射 `CHINESE_NUM={"二": 2}` → 定位购物车第 2 项
3. **SKU 规格选择** — `agent_stream.py`：多 SKU 商品加购时 → 列出规格选项卡片 → 用户选择 → 写入 `pending_sku_product` → 匹配确认 → 加购
4. **订单确认卡片** — `agent_stream.py` `order_words` 逻辑：下单 → 读取地址 → 生成订单汇总 → 返回 `quick_reply: "确认下单"` 按钮 → 用户确认 → 持久化 PG
5. **FollowUpEngine 加购意图** — `followup_engine.py` `_CART_PATTERN`：检测到"加入购物车"→ 标记 `follow_up_type="cart_intent"` → SSE 端直接执行加购

**效果：** 全链路自然语言：推荐 → "第二个加购" → "下单" → 确认 → 订单持久化。FollowUpEngine 检测到的加购意图在 SSE 端直接执行，不经过 Agent Workflow 省延迟。

---

## API 速查

### 推荐 (4 端点)

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/recommend` | V0 同步推荐（兼容旧客户端） |
| `POST` | `/api/recommend/v2` | V2 LangGraph 5-Agent 工作流 |
| `POST` | `/api/recommend/stream` | **SSE 流式推荐**（主力端点） |
| `POST` | `/api/recommend/guide` | 约束引导式推荐（品类→预算多轮） |

### 商品 & 图片 (3 端点)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/products` | 商品列表（品类/关键词/价格筛选+分页） |
| `GET` | `/api/products/{id}` | 商品详情（SKU/FAQ/评论/评价摘要） |
| `POST` | `/api/upload` | 图片上传（魔术字校验+10MB限制） |

### 购物车 & 结算 (7 端点)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/cart` | 查看购物车 |
| `POST` | `/api/cart/items` | 加购（SKU 归属校验） |
| `PUT` | `/api/cart/items/{id}` | 修改数量/选中状态 |
| `DELETE` | `/api/cart/items/{id}` | 移除商品 |
| `DELETE` | `/api/cart/clear` | 清空购物车 |
| `POST` | `/api/checkout` | 模拟结算 |
| `GET` | `/api/orders` | 订单列表 |

### 用户 & 地址 (7 端点)

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/auth/register` | 注册 |
| `POST` | `/api/auth/login` | 登录 |
| `GET` | `/api/auth/profile` | 个人信息 |
| `GET/POST/PUT/DELETE` | `/api/addresses[/{id}]` | 地址 CRUD |

### 会话 & 偏好 (9 端点)

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET/DELETE` | `/api/conversations[/{id}]` | 对话列表/删除 |
| `GET` | `/api/conversations/{id}/messages` | 对话消息（含商品引用） |
| `GET/PUT/DELETE` | `/api/preferences` | 会话偏好 |
| `GET/PUT/DELETE` | `/api/preferences/entries[/{id}]` | 长期偏好条目管理 |

### 语音 & 评测 (5 端点)

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/voice/transcribe` | ASR 语音转文字 |
| `POST` | `/api/voice/tts` | TTS 文字转语音 |
| `POST` | `/api/eval/run` | 运行 Golden Query 评测 |
| `GET` | `/api/eval/results` | 历史评测结果 |
| `GET` | `/eval` | Chart.js 可视化仪表盘 |

---

## 评测体系

> 10 条 Golden Query 覆盖 4 大品类，自动评测 + 可视化仪表盘

**评测指标：** Recall@5 / Recall@10 / MRR / NDCG@10 / Category Accuracy / P95 Latency

**评测方法：**
```bash
# 运行评测
curl -X POST http://localhost:8006/api/eval/run?method=default

# 查看结果
curl http://localhost:8006/api/eval/results

# 可视化仪表盘
open http://localhost:8006/eval
```

仪表盘基于 Chart.js 构建，支持分块检索对比评测、历史趋势、逐 Query 详情。

---

## 部署运维

| 项目 | 值 |
|------|-----|
| 公网 IP | **8.137.187.54** |
| 端口 | 8006 |
| 配置 | 阿里云轻量 2C4G 50G SSD |
| Docker | 26.1.3 + Compose v2 |
| 项目路径 | `~/OmniCart-Agent` |

```bash
# 常用运维命令
docker compose ps                              # 服务状态
docker compose logs backend -f                 # 实时日志
docker compose up -d --build backend           # 更新后端
docker compose exec backend python scripts/smoke_recommend.py  # 冒烟测试
curl http://localhost:8006/api/health          # 健康检查
```

详见 [DEPLOY.md](DEPLOY.md)（部署指南）和 [SERVER_OPS.md](SERVER_OPS.md)（运维手册）。

---

## 文档索引

### 开发与部署

| 文档 | 内容 |
|------|------|
| [DEVELOPMENT.md](DEVELOPMENT.md) | 开发者上手指南（结构 / 环境 / 流程 / 门禁 / 踩坑） |
| [MODULES.md](MODULES.md) | 重要功能模块说明 |
| [本地运行指南.md](本地运行指南.md) | macOS 逐步启动（含端口与常见问题） |
| [DEPLOY.md](DEPLOY.md) | 部署指南（Docker + 云服务器 + APK） |
| [SERVER_OPS.md](SERVER_OPS.md) | 服务器运维手册 |
| [CLAUDE.md](CLAUDE.md) | AI 协作规范（项目指令） |

### 设计与决策

| 文档 | 内容 |
|------|------|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 架构说明 |
| [docs/CONSTITUTION.md](docs/CONSTITUTION.md) | 项目工程宪章（分层与质量约束） |
| [docs/adr/](docs/adr/) | 架构决策记录：RAG 框架 / 多路记忆 / 上下文压缩 |
| [docs/specs/](docs/specs/) | 各期需求与方案 spec（QU v2 / 向量化 v6 / amap 架构升级 等） |
| [docs/全链路请求流程与性能优化分析.md](docs/全链路请求流程与性能优化分析.md) | 全链路请求流程拆解与性能优化 |
| [docs/架构升级方案-借鉴amap治理与编排.md](docs/架构升级方案-借鉴amap治理与编排.md) | framework/providers 分层升级方案 |
| [docs/工作日志.md](docs/工作日志.md) | 开发工作日志（按任务倒序，含动机与踩坑记录） |

---

<p align="center">
  <sub>Built with ❤️ for ByteDance Agent Challenge · OmniCart Agent Team</sub>
</p>
