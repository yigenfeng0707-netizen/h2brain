---
title: 氢智行 H2Brain
emoji: 🚛
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# 氢智行 H2Brain

氢能车辆运营智能分析与决策平台 —— 基于多智能体协同的氢能重卡运营优化系统。

## 赛道
T05 - 氢能车辆运营智能分析与决策（浦发·IGNITE 未来能源黑客松）

## 架构
- 前端：React 19 + TypeScript + Vite + Ant Design + ECharts
- 后端：FastAPI + Pydantic + NumPy + ReAct 推理引擎
- 部署：Docker 单容器（nginx + uvicorn + supervisord）

## 六大智能体
1. 氢耗优化 Agent (hydrogen_opt)
2. 路径规划 Agent (route_plan)
3. 加氢站调度 Agent (station_dispatch)
4. 车队管理 Agent (fleet_manage)
5. 成本分析 Agent (cost_analysis)
6. 燃料电池健康 Agent (fuelcell_health)

## 本地运行
```bash
docker build -t h2brain .
docker run -p 7860:7860 h2brain
```

访问 http://localhost:7860
