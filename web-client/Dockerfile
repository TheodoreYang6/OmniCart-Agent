# ---- 构建 ----
FROM node:22-alpine AS build
WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
# 同源部署：API_BASE 留空走相对路径，由 nginx 反代 /api 到后端
RUN npm run build

# ---- 托管 ----
FROM nginx:1.27-alpine

# OMNICART_PROXY_TARGET 决定 /api 反代目标（默认 compose 内的 backend:8006，
# 本机原生后端可设为 host.docker.internal:8006）
ENV OMNICART_PROXY_TARGET=backend:8006
COPY nginx/templates/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
