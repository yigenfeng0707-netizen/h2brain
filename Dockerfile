# ============================================
# Stage 1: Build frontend
# ============================================
FROM node:20-alpine AS frontend-builder

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm config set registry https://registry.npmmirror.com && npm install
COPY frontend/ .
RUN npm run build

# ============================================
# Stage 2: Final image with backend + nginx
# ============================================
FROM python:3.12-slim

# Install nginx and supervisord
RUN apt-get update && \
    apt-get install -y --no-install-recommends nginx supervisor && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Setup backend
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY backend/ .

# Copy pre-processed data files (only needed columns, ~70MB total)
COPY backend/data/ /app/data/

# Setup frontend
RUN rm -rf /usr/share/nginx/html/*
COPY --from=frontend-builder /frontend/dist /usr/share/nginx/html

# Setup nginx config
COPY deploy/modelscope/nginx.conf /etc/nginx/conf.d/default.conf
RUN rm -f /etc/nginx/sites-enabled/default

# Setup supervisord
COPY deploy/modelscope/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Environment
ENV APP_ENV=production
ENV DEBUG=false
ENV H2BRAIN_DATA_DIR=/app/data

# LLM 密钥不进镜像不进 git：由 entrypoint.sh 在启动时从部署平台环境变量注入
#   LLM_API_KEY (主: 阿里百炼 qwen-plus) / LLM_FALLBACK_API_KEY (备: 阶跃星辰 step-3.7-flash)
# 部署后在平台环境变量中配置，未配置则智能体走离线示例模式
COPY deploy/modelscope/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 7860

CMD ["/entrypoint.sh"]
