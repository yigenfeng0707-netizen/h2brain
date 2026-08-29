#!/bin/sh
# 运行时注入 LLM 配置（密钥不进镜像、不进 git）
# 部署平台（魔搭创空间/本地 docker）配置环境变量:
#   LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
#   LLM_FALLBACK_API_KEY / LLM_FALLBACK_BASE_URL / LLM_FALLBACK_MODEL
# 未配置密钥时服务仍可启动（智能体走离线示例模式）

ENV_FILE=/app/backend/.env

echo 'APP_ENV=production' > "$ENV_FILE"
echo 'DEBUG=false' >> "$ENV_FILE"
echo 'CORS_ORIGINS=["*"]' >> "$ENV_FILE"

# 主 LLM: 阿里百炼 qwen-plus
if [ -n "$LLM_API_KEY" ]; then
    echo "LLM_API_KEY=$LLM_API_KEY" >> "$ENV_FILE"
    echo "LLM_BASE_URL=${LLM_BASE_URL:-https://llm-uarugoa0rqgduef5.cn-beijing.maas.aliyuncs.com/compatible-mode/v1}" >> "$ENV_FILE"
    echo "LLM_MODEL=${LLM_MODEL:-qwen-plus}" >> "$ENV_FILE"
fi

# 备用 LLM: 阶跃星辰 step-3.7-flash
if [ -n "$LLM_FALLBACK_API_KEY" ]; then
    echo "LLM_FALLBACK_API_KEY=$LLM_FALLBACK_API_KEY" >> "$ENV_FILE"
    echo "LLM_FALLBACK_BASE_URL=${LLM_FALLBACK_BASE_URL:-https://api.stepfun.com/step_plan/v1}" >> "$ENV_FILE"
    echo "LLM_FALLBACK_MODEL=${LLM_FALLBACK_MODEL:-step-3.7-flash}" >> "$ENV_FILE"
fi

# 图像生成: 商汤 SenseNova（运营周报配图）
if [ -n "$IMAGE_API_KEY" ]; then
    echo "IMAGE_API_KEY=$IMAGE_API_KEY" >> "$ENV_FILE"
    echo "IMAGE_BASE_URL=${IMAGE_BASE_URL:-https://token.sensenova.cn/v1}" >> "$ENV_FILE"
    echo "IMAGE_MODEL=${IMAGE_MODEL:-sensenova-u1.5-lite}" >> "$ENV_FILE"
fi

exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
