FROM python:3.11-slim

WORKDIR /app

# 清华镜像加速
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 依赖层（利用 Docker 缓存）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 源码
COPY backend/ ./backend/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY ecommerce_agent_dataset/ ./ecommerce_agent_dataset/

# 入口
COPY backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8006

ENTRYPOINT ["/entrypoint.sh"]
