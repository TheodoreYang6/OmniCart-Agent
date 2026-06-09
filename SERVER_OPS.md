# OmniCart Agent 服务器运维手册

## 服务器信息

| 项目 | 值 |
|------|-----|
| 公网 IP | 8.137.187.54 |
| 端口 | 8006 |
| 系统 | Alibaba Cloud 轻量应用服务器 |
| 配置 | 2 vCPU / 4 GiB / 50 GiB SSD |
| Docker | 26.1.3 |
| 项目路径 | `~/OmniCart-Agent` |

## 四种容器

| 服务 | 端口 | 用途 |
|------|------|------|
| backend | 8006 | FastAPI 后端 |
| postgres | 5432 | 商品/用户/订单数据 |
| qdrant | 6333 | 向量检索 |
| redis | 6379 | 缓存/TTS |

---

## 启动

```bash
cd ~/OmniCart-Agent
docker compose up -d
docker compose ps   # 确认四容器都是 Up/healthy
curl http://localhost:8006/api/health
```

## 停止

```bash
cd ~/OmniCart-Agent
docker compose down     # 保留数据
docker compose down -v  # ⚠️ 彻底清除含数据
```

## 重启

```bash
cd ~/OmniCart-Agent
docker compose restart backend   # 只重启后端
docker compose restart           # 重启全部
```

## 更新代码

```bash
cd ~/OmniCart-Agent
git pull
docker compose up -d --build backend   # 重新构建并重启后端
```

## 初始化数据

只有首次部署或清空数据后需要：

```bash
docker compose exec backend python scripts/seed_postgresql.py
docker compose exec backend python scripts/index_products.py
```

## 日常检查

```bash
docker compose ps                      # 服务状态
docker compose logs backend --tail=50  # 最近日志
docker compose logs backend -f         # 实时日志
curl http://localhost:8006/api/health  # API 是否正常
docker stats --no-stream               # 资源占用
df -h                                  # 磁盘剩余
```

## 防火墙

轻量服务器控制台 → 服务器 → 防火墙 → 确保 8006 TCP 已开放。

## APK 下载

队友访问以下链接下载安装：

```
http://8.137.187.54:8006/api/uploads/douzai.apk
```

更新 APK 后上传到服务器：

```bash
# 在本地执行
scp 豆仔.apk admin@8.137.187.54:~/OmniCart-Agent/data/uploads/douzai.apk
```

## 数据备份

```bash
# PostgreSQL 备份
docker compose exec postgres pg_dump -U omnicart omnicart > backup_$(date +%Y%m%d).sql

# 恢复
docker compose exec -T postgres psql -U omnicart omnicart < backup.sql
```

## 常见问题

| 问题 | 解决 |
|------|------|
| 手机连不上 | 检查防火墙是否开放 8006 |
| API 报 500 | `docker compose logs backend --tail=50` 查错误 |
| 容器起不来 | `docker compose down && docker compose up -d` |
| 磁盘满了 | `docker system prune -a` 清理旧镜像 |
| API Key 失效 | `vim .env` 更新 QWEN_API_KEY → `docker compose restart backend` |
