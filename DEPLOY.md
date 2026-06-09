# OmniCart Agent 部署指南

## 前置条件

- 服务器：Linux (Ubuntu 20.04+ / CentOS 7+) 2C4G+
- Docker 24+ + Docker Compose v2
- 域名/IP 可访问，开放端口 8006

## 一、服务器初始化（一次性）

```bash
# 安装 Docker
curl -fsSL https://get.docker.com | bash
sudo usermod -aG docker $USER
newgrp docker

# 验证
docker --version
docker compose version
```

## 二、部署应用

```bash
# 1. 拉取代码
cd ~
git clone <你的仓库地址> omnicart-agent
cd omnicart-agent

# 2. 配置环境变量
cp .env.docker .env
vim .env   # 修改 QWEN_API_KEY=你的真实密钥
```

**.env 中需要修改的项：**

| 变量 | 说明 |
|------|------|
| `QWEN_API_KEY` | 阿里云 DashScope API Key（必填） |
| `OMNICART_MOCK_MODE` | 设为 `false` 使用真实 LLM |

**其他数据库/缓存连接无需修改**，容器内通过服务名自动互通。

```bash
# 3. 启动所有服务
docker compose up -d

# 4. 查看状态（等全部 healthy）
docker compose ps

# 5. 首次初始化数据（仅第一次）
docker compose exec backend python scripts/seed_postgresql.py
docker compose exec backend python scripts/index_products.py

# 6. 验证
curl http://localhost:8006/api/health
# 返回 {"status":"ok","service":"omnicart-agent","version":"0.1.0"}
```

## 三、更新代码

```bash
cd ~/omnicart-agent
git pull
docker compose up -d --build backend   # 重新构建并重启后端
```

## 四、日常运维

```bash
# 查看服务状态
docker compose ps

# 查看后端日志
docker compose logs -f backend

# 查看错误
docker compose logs backend --tail=50 | grep -i error

# 重启单个服务
docker compose restart backend

# 停止全部（保留数据）
docker compose down

# 彻底清除（含数据）
docker compose down -v
```

## 五、数据备份

```bash
# PostgreSQL 备份
docker compose exec postgres pg_dump -U omnicart omnicart > backup_$(date +%Y%m%d).sql

# Qdrant 快照
curl -X POST http://localhost:6333/collections/products/snapshots

# 恢复
docker compose exec -T postgres psql -U omnicart omnicart < backup.sql
```

## 六、Android 客户端配置

### 构建 APK

```bash
# Debug（开发测试）
cd android-client
export JAVA_HOME=<JDK路径>
./gradlew assembleDebug
# 输出: app/build/outputs/apk/debug/app-debug.apk

# Release（分发用，已签名）
./gradlew assembleRelease
# 输出: app/build/outputs/apk/release/app-release.apk
```

### 修改 API 地址

编辑 `android-client/app/build.gradle.kts`：
```kotlin
buildTypes {
    debug {
        buildConfigField("String", "BASE_URL", "\"http://你的服务器IP:8006/\"")
    }
    release {
        buildConfigField("String", "BASE_URL", "\"http://你的服务器IP:8006/\"")
    }
}
```

修改后重新 `./gradlew assembleDebug` 或 `assembleRelease`。

### 安装到手机

```bash
# USB 连接 + 开发者模式
adb install app/build/outputs/apk/debug/app-debug.apk

# 或直接传 APK 文件给手机安装
```

## 七、Nginx 反向代理（可选）

生产环境建议在 Docker 前面加 Nginx：

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://127.0.0.1:8006;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;  # SSE 流式需要
    }
}
```

## 八、故障排查

| 问题 | 检查 |
|------|------|
| 后端启动失败 | `docker compose logs backend` 查看错误 |
| PostgreSQL 连不上 | `docker compose logs postgres` 确认 healthy |
| Qdrant 连不上 | `curl http://localhost:6333/health` |
| API 返回 500 | 检查 `.env` 中 QWEN_API_KEY 是否有效 |
| Mock 模式可用 | `.env` 中设 `OMNICART_MOCK_MODE=true` |
