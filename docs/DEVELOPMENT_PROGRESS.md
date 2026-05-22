# OmniCart Agent 开发进度

更新时间：2026-05-22
当前阶段：**V1 参赛版 ~75% 完成，核心链路全部打通**
当前重点：P1 任务（Auth → 地址 → 偏好 → Evidence Checker → Skill Registry）
当前阻塞：无

## 本次会话完成（2026-05-22）

### 数据库架构定型
- PostgreSQL 18 安装 + omnicart 数据库 + 三张表（products/cart_items/user_preferences）
- Qdrant 1.18 安装 + products collection（1024d COSINE）
- 100 件商品迁移到 PG + 索引到 Qdrant
- Repository 抽象层（ABC + JsonProductRepository + PgProductRepository）
- 向量仓库（QdrantVectorRepository + StubVectorRepository 降级）
- Hybrid Search（Qdrant 向量 + jieba 关键词 RRF 融合）
- 购物车 PG/内存双模（PgCartRepository + MemCartRepository）
- 偏好 PG/内存双模（PgPreferenceRepository + MemPreferenceRepository）
- sync-async 桥接（nest_asyncio）
- Alembic 迁移框架 + seed 脚本

### Android 四 Tab 核心闭环
- 商品 Tab → 豆仔推荐 → 加入购物车 → 购物车管理 → 结算
- 对话历史：ChatMessage 消息列表，多轮不覆盖
- 新对话按钮（顶栏 + 号）
- 品类话题切换检测（Router Agent 规则优先 LLM + PreferenceMemory 自动清除）
- 购物车自动刷新（cartRefreshKey + LaunchedEffect）
- OmniCartApi 补全 8 个接口（cart/checkout/agent_action）
- CartViewModel 从假数据切换为真实 API
- ProductCard "加入购物车"按钮 + Snackbar 反馈
- CartScreen/ChatScreen 去掉双层 Scaffold 修复空白

### 文档
- `docs/答辩QA手册.md`（13 章，覆盖数据库/RAG/Agent/评分/多模态/客户端/追问应对）
- `docs/TASK_LIST.md`（51 项任务，V0→V2，优先级分级）

## 进度总览

| 模块 | 状态 | 完成度 |
|------|------|--------|
| V0-Core | 完成 | 100% |
| V0-Android | 完成 | 100% |
| V1-Core 后端 P0 | 完成 | 100% |
| V1-Core 后端 P1 | 待开始 | 0/8 |
| V1-Core 后端 P2 | 待开始 | 0/10 |
| V1-Core Android P0 | 待开始 | 0/1 |
| V1-Core Android P1 | 待开始 | 0/6 |
| V1-Core Android P2 | 待开始 | 0/4 |
| V1-Plus | 待开始 | 0/10 |
| V2 | 待开始 | 0/12 |

## 下一步

1. P1-1: 用户登录/注册 API
2. P1-2: 收货地址 CRUD API
3. P1-3: 用户偏好 REST API
4. P1-4: Evidence Checker 接入 Workflow
