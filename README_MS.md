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

基于真实氢能重卡CAN总线遥测数据的智能分析与决策助手。

## 赛道
T05 - 氢能车辆运营智能分析与决策（命题一：氢耗数据分析深度）

## 核心功能
1. **工况识别引擎** — 6类路况自动识别 + 5类动力模式检测
2. **异常氢耗检测与归因** — 电堆功率积分法 + 5维归因分析
3. **驾驶行为分析** — 急加速/急减速/超速检测与严重度量化
4. **影响因子分析** — Pearson相关系数量化各因子对氢耗的影响
5. **同类行程对标** — 全车队行程氢耗横向对比与自动评级
6. **自动分析报告** — 一键生成7段结构化报告
7. **CSV数据上传** — 支持上传新车辆数据自动分析

## 真实数据
- 车辆1#（湖北襄阳）：333,649行遥测数据，16行程，1,859km，百公里氢耗4.98kg
- 车辆2#（新疆吐鲁番）：300,018行遥测数据，12行程，6,849km，百公里氢耗6.19kg

## 架构
- 前端：React 19 + TypeScript + Vite + Ant Design + ECharts
- 后端：FastAPI + Pandas + NumPy
- 部署：Docker 单容器（nginx + uvicorn + supervisord）

## 本地运行
```bash
docker build -t h2brain .
docker run -p 7860:7860 h2brain
```

访问 http://localhost:7860

## 核心页面
- **精细化行程分析** (/trip-analysis) — 完整Dashboard，含6指标卡+路况标签表+4图联动+异常氢耗检测+驾驶行为+因子分析+对标表+报告弹窗+CSV上传
