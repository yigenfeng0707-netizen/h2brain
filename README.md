# 氢智行 H2Brain

> 让每克氢都跑在刀刃上

**2026 浦发·IGNITE 未来能源黑客松** — 氢能车辆运营智能分析与决策赛道

## 项目简介

氢智行 H2Brain 是面向氢能重卡/物流车队的智能运营决策平台，基于 AI 多智能体架构，实现氢耗优化、路径规划、加氢站调度、车队管理、成本分析和燃料电池健康预测六大核心能力。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Vite 8 + Ant Design 6 + ECharts 6 + TailwindCSS |
| 后端 | FastAPI + Pydantic + NumPy + OpenAI SDK |
| 架构 | LLM + RAG + MCP + 运筹优化 + ReAct 推理 |
| 部署 | Docker Compose |

## 快速启动

### 方式一：本地开发

```bash
# 1. 启动后端
cd backend
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000

# 2. 启动前端
cd frontend
npm install
npm run dev
```

访问 http://localhost:5173

### 方式二：Docker 部署

```bash
docker-compose up -d --build
```

访问 http://localhost

## 六大智能体

| Agent | 核心能力 | 关键指标 |
|-------|---------|---------|
| 氢耗优化 Agent | 实时氢耗监控 + 行驶参数优化 | 百公里氢耗 -12% |
| 路径规划 Agent | 续航圈计算 + 多站路径择优 | 续航匹配率 98%+ |
| 加氢站调度 Agent | 排队预测 + 动态分流 | 等待时间 -60% |
| 车队管理 Agent | 运力画像 + 订单匹配 | 利用率 +25% |
| 成本分析 Agent | 全成本核算 + TCO对标 | 运营成本 -18% |
| 燃料电池健康 Agent | 衰减预测 + 维保推荐 | 寿命预测准确率 95%+ |

## 项目结构

```
h2brain/
  backend/           # FastAPI 后端
    app/
      api/           # 6 个路由模块
      config.py      # 配置
      schemas.py     # 数据模型
      mock_data.py   # 模拟数据（大兴氢能示范区）
  frontend/          # React 前端
    src/
      pages/         # 页面组件
      layouts/       # 布局
      lib/           # 工具库
  docker-compose.yml
```

## 赛事信息

- **赛道**: 氢能车辆运营智能分析与决策（第五题）
- **赛事**: 2026 浦发·IGNITE 未来能源黑客松
- **地点**: 中关村(大兴)国际氢能示范区
