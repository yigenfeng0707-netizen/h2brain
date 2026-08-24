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
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple

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
RUN echo 'APP_ENV=production' > /app/backend/.env && \
    echo 'DEBUG=false' >> /app/backend/.env && \
    echo 'CORS_ORIGINS=["*"]' >> /app/backend/.env && \
    echo 'LLM_API_KEY=sk-bulmEVxNZokZedif4sxINRbv5hbD7SVd' >> /app/backend/.env && \
    echo 'LLM_BASE_URL=https://token.sensenova.cn/v1' >> /app/backend/.env && \
    echo 'LLM_MODEL=sensenova-6.8-flash-lite' >> /app/backend/.env

EXPOSE 7860

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
