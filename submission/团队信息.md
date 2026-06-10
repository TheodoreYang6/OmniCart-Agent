# 团队信息

## 队名

（由队长在提交表单中填写）

## 团队成员

| 姓名 | 角色 | 职责 |
|------|------|------|
| **杨启铎** | 全栈架构 | 项目整体架构设计、FastAPI 后端开发、5-Agent 协同系统（Router / Visual / Retrieval / Decision / Response）、LangGraph 工作流编排、RAG 全链路检索（Embedding + Qdrant + Reranker + 证据补充）、7 维证据评分引擎、三层记忆系统（短期 / 长期 / 会话）、FollowUpEngine 追问检测、SSE 流式对话、购物闭环（自然语言加购 / 下单）、语音导购（ASR + TTS）、Docker 容器化部署、阿里云服务器运维、全部技术文档撰写 |
| **胡金成** | 后端 / 数据 | RAG 评测体系搭建（10 条 Golden Query 设计、Recall@K / MRR / NDCG@K 指标计算、Chart.js 可视化仪表盘）、PostgreSQL + Qdrant + Redis 数据库架构设计与维护、数据播种与索引脚本 |
| **章恒睿** | Android 客户端 | Android 原生客户端全部开发：Jetpack Compose 四 Tab 架构（商品 / 豆仔 / 购物车 / 我的）、SSE 流式对话界面、拍照识图、语音输入、购物车管理、偏好设置、Agent 洞察面板（追踪 / 证据 / 评分 / 安全）、Demo 演示模式、APK 签名混淆打包 |

## 分工说明

杨启铎负责项目整体架构设计与全栈开发，核心工作包括 LangGraph 5-Agent 协同编排、RAG 全链路检索管道、评分引擎与记忆系统的设计与实现，以及 Docker 部署与服务器运维。

胡金成负责 RAG 评测体系与数据库架构，设计了 10 条覆盖 4 大品类的 Golden Query 评测集，实现了 Recall@K、MRR、NDCG@K 等检索指标自动计算和 Chart.js 可视化仪表盘，同时负责 PostgreSQL 7 张业务表、Qdrant 双集合向量索引和 Redis 四级缓存的架构设计与数据维护。

章恒睿独立完成 Android 原生客户端全部开发工作，基于 Jetpack Compose + Material 3 实现了四 Tab 主架构，核心功能包括 SSE 流式打字机对话、拍照识图、语音导购、对话式购物操作、偏好管理和 Agent 洞察面板，并完成了 Release APK 的签名混淆打包。
