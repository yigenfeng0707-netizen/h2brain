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

| Agent | 核心算法 | 关键指标 |
|-------|---------|---------|
| 氢耗优化 Agent | 工况识别 + Pearson归因 + 电堆功率积分法 | 百公里氢耗 -12% |
| 路径规划 Agent | Haversine续航圈 + 多站路径择优 + 15%安全余量 | 续航匹配率 98%+ |
| 加氢站调度 Agent | M/M/c Erlang C排队论 + 距离/等待/价格综合评分 | 等待时间 -60% |
| 车队管理 Agent | 多目标加权匹配(氢气30%+就近25%+利用率20%+成本15%+均衡10%) | 利用率 +25% |
| 成本分析 Agent | 全成本核算(TCO) + 氢成本占比分析 | 运营成本 -18% |
| 燃料电池健康 Agent | 极化曲线采样 + 热应力检测 + 衰减趋势 + RUL预测 | 健康评分0-100 |

## 项目结构

```
h2brain/
  backend/           # FastAPI 后端
    app/
      api/           # 7 个路由模块 (含 optimization)
      config.py      # 配置
      schemas.py     # 数据模型
      mock_data.py   # 模拟数据（大兴氢能示范区）
      data_processor.py  # 真实遥测数据处理 (63万行CAN总线)
      fuelcell_health.py # 燃料电池健康分析算法
      route_optimizer.py # 路径规划+加氢站调度算法
      fleet_optimizer.py # 车队多目标优化算法
      react_engine.py    # LLM ReAct推理引擎
      llm_client.py      # 商汤日日新 LLM客户端
      weather.py         # Open-Meteo 天气数据集成
      thresholds.py      # 数据驱动阈值标定 (30+ 常量)
      value_analysis.py  # 经济+碳减排+ROI 价值量化
      validation.py      # 算法精度验证 (vs 官方手工记录 ground truth)
    tests/
      test_core.py       # 50+ 测试用例
  frontend/          # React 前端
    src/
      pages/         # 14 个页面组件
      layouts/       # 布局
      lib/           # 工具库
    public/
      project-doc.html  # 项目介绍文档 (静态版, 免登录)
  docker-compose.yml
```

## 真实数据

- **车辆1#**（湖北襄阳）：333,649行遥测数据，16行程，1,859km
- **车辆2#**（新疆吐鲁番）：300,018行遥测数据，12行程，6,849km
- 数据来源：T05赛题官方数据包，CAN总线10秒采样
- **算法验证**: 自动分割与工况识别结果已与官方手工记录表（114条行程 ground truth）对比验证，工况吻合率 100%

## 链接

| 资源 | 地址 |
|------|------|
| Demo | https://gsym236998-h2brain.ms.show |
| GitHub | https://github.com/yigenfeng0707-netizen/h2brain |
| 演示视频 | https://www.bilibili.com/video/BV1Dy8T6nEY9 |
| 项目文档 | https://icn4knwqw97v.feishu.cn/wiki/CbsKwrf4GiFUPzkLc9Kcc2j3nVc |
| 项目文档(静态版) | /project-doc.html (Demo 内置, 免登录访问) |

> 注: 飞书文档需登录飞书账号查看；如需免登录访问，请使用 Demo 内置的静态版项目文档。

## 赛事信息

- **赛道**: T05 - 氢能车辆运营智能分析与决策（命题一：氢耗数据分析深度）
- **赛事**: 2026 浦发·IGNITE 未来能源黑客松
- **地点**: 中关村(大兴)国际氢能示范区

## 团队信息

- **团队名称**: 氢智行 H2Brain
- **参赛形式**: 个人参赛
- **成员**: 冯亦根
