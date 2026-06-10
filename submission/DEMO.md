# OmniCart Agent 体验指南

评委您好，以下是 3 种方式快速体验 OmniCart Agent。

---

## 方式一：直接安装 APK（最快，30 秒）

APK 已配置连接云服务器 `8.137.187.54:8006`，安装即用。

**下载安装：**

```
http://8.137.187.54:8006/api/uploads/douzai.apk
```

Android 手机浏览器打开以上链接 → 下载 → 安装 → 打开即可体验。

**体验路径：**

1. 打开 App → 底部切到「🫘 豆仔」Tab
2. 输入 "推荐一款蓝牙耳机，500以内" → 观看 SSE 打字机效果
3. 点击商品卡片 → 查看详情（SKU / FAQ / 评论 / 评分拆解）
4. 点击「问豆仔」→ 深度分析该商品 + 同类对比
5. 说 "第二个加入购物车" → 对话式加购（含 SKU 规格选择）
6. 说 "下单" → 模拟下单流程
7. 切到「📦 商品」Tab → 浏览 105 件商品，按分类筛选
8. 切到「🛒 购物车」Tab → 查看/管理已加购商品
9. 切到「👤 我的」Tab → 登录注册 / 偏好设置 / 地址管理

**更多体验：**
- 点击输入栏 📷 拍照 → 识别商品 → 推荐同类
- 长按 🎤 录音 → 语音转文字 → SSE 推荐 → TTS 朗读回复
- 点击 ⚡ 开关 → 快速模式（模板秒回）
- 点击 ➕ → 约束引导推荐 / Demo 演示
- 点击 Agent 分析结果旁的 🧠 → 洞察面板（追踪/证据/评分/安全）

---

## 方式二：Docker 一行起跑（如需本地部署，2 分钟）

```bash
# 1. 克隆
git clone https://github.com/TheodoreYang6/OmniCart-Agent.git
cd OmniCart-Agent

# 2. 配置（Mock 模式无需 API Key 也能跑）
cp .env.docker .env
# 可选: 编辑 .env 填入 QWEN_API_KEY=你的密钥

# 3. 启动
docker compose up -d

# 4. 初始化数据（仅首次）
docker compose exec backend python scripts/seed_postgresql.py
docker compose exec backend python scripts/index_products.py

# 5. 验证
curl http://localhost:8006/api/health
# → {"status":"ok","service":"omnicart-agent","version":"2.0.0"}
```

然后安装 APK 或直接用 curl 测试：

```bash
# V2 工作流推荐
curl -X POST http://localhost:8006/api/recommend/v2 \
  -H "Content-Type: application/json" \
  -d '{"user_query": "推荐一款蓝牙耳机，500以内"}'

# SSE 流式推荐
curl -N -X POST http://localhost:8006/api/recommend/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "推荐一款防晒霜"}'
```

---

## 方式三：本地 Python 开发（如需修改代码，3 分钟）

```bash
# Python 3.11+ 环境
pip install -r requirements.txt

# Mock 模式启动（无需 API Key / PostgreSQL / Qdrant / Redis）
OMNICART_MOCK_MODE=true uvicorn backend.app.main:app --port 8006

# 验证
curl http://localhost:8006/api/health
```

---

## 核心 API 速测

| 端点 | 说明 | curl 命令 |
|------|------|-----------|
| 健康检查 | 服务状态 | `curl http://localhost:8006/api/health` |
| V2 推荐 | LangGraph 5-Agent 工作流 | `curl -X POST .../api/recommend/v2 -H "Content-Type: application/json" -d '{"user_query":"推荐蓝牙耳机"}'` |
| SSE 流式 | 主力端点，打字机效果 | `curl -N -X POST .../api/recommend/stream -H "Content-Type: application/json" -d '{"message":"推荐一款跑鞋"}'` |
| 商品列表 | 分页+筛选 | `curl .../api/products?category=数码电子&page=1` |
| 商品详情 | 含 SKU/FAQ/评论 | `curl .../api/products/p_digi_001` |
| 评测运行 | Golden Query 评测 | `curl -X POST .../api/eval/run?method=default` |
| 评测仪表盘 | Chart.js 可视化 | 浏览器打开 `http://localhost:8006/eval` |

---

## 服务地址

| 项目 | 地址 |
|------|------|
| 云服务器 API | `http://8.137.187.54:8006/api/health` |
| APK 下载 | `http://8.137.187.54:8006/api/uploads/douzai.apk` |
| 本地部署 | `http://localhost:8006` |

---

## 更多文档

- [README.md](README.md) — 项目总览 + 系统架构 + 功能矩阵
- [DEPLOY.md](DEPLOY.md) — 详细部署指南（Docker + 云服务器 + APK）
- [SERVER_OPS.md](SERVER_OPS.md) — 服务器运维手册
