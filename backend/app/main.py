"""氢智行 H2Brain - FastAPI 应用入口

五层架构（L1-L5）的后端承载。
Phase 1 提供：健康检查、运营数据、智能调度、ReAct决策推理、智能体展示。
"""

import json
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import (
    health,
    operations,
    dispatch,
    react,
    agents,
    display,
    analysis,
    optimization,
)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[H2Brain] started | env={settings.app_env} | llm={settings.llm_enabled}")
    yield
    print("[H2Brain] stopped")


app = FastAPI(
    title="氢智行 H2Brain API",
    description="氢能车辆运营智能分析与决策平台",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# 路由挂载
app.include_router(health.router, prefix=API_PREFIX, tags=["系统"])
app.include_router(operations.router, prefix=API_PREFIX, tags=["运营数据"])
app.include_router(dispatch.router, prefix=API_PREFIX, tags=["智能调度"])
app.include_router(react.router, prefix=API_PREFIX, tags=["ReAct决策"])
app.include_router(agents.router, prefix=API_PREFIX, tags=["智能体"])
app.include_router(display.router, prefix=API_PREFIX, tags=["展示"])
app.include_router(analysis.router, prefix=API_PREFIX, tags=["真实数据分析"])
app.include_router(optimization.router, prefix=API_PREFIX, tags=["智能优化"])


@app.get("/", tags=["根"])
def root():
    return {
        "name": "氢智行 H2Brain",
        "slogan": "让每克氢都跑在刀刃上",
        "docs": "/docs",
    }
