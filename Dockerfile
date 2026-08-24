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

# Overwrite .env with production values (avoid local dev .env leaking into container)
# Primary: openai-next gpt-4o-mini / Fallback: openai-next 按量 gpt-5.6-sol (奇绩算力)
RUN echo 'APP_ENV=production' > /app/backend/.env && \
    echo 'DEBUG=false' >> /app/backend/.env && \
    echo 'CORS_ORIGINS=["*"]' >> /app/backend/.env && \
    echo 'LLM_API_KEY=sk-ghfkYiYWryR3Px5HC4Be6fBc330640F9B9A4952f10A95763' >> /app/backend/.env && \
    echo 'LLM_BASE_URL=https://api.openai-next.com/v1' >> /app/backend/.env && \
    echo 'LLM_MODEL=gpt-4o-mini' >> /app/backend/.env && \
    echo 'LLM_FALLBACK_API_KEY=sk-H6Um1v2aEow1BF5XCb288e9d9f29454599Af16C1Ab9bEf5c' >> /app/backend/.env && \
    echo 'LLM_FALLBACK_BASE_URL=https://api.openai-next.com/v1' >> /app/backend/.env && \
    echo 'LLM_FALLBACK_MODEL=gpt-5.6-sol' >> /app/backend/.env

EXPOSE 7860

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
