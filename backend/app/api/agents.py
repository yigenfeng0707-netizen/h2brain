"""氢智行 H2Brain - 智能体展示接口"""

from fastapi import APIRouter

router = APIRouter()

AGENTS_DATA = [
    {
        "key": "hydrogen_opt",
        "name": "氢耗优化 Agent",
        "icon": "h2",
        "metric": "百公里氢耗 -12%",
        "desc": "基于车辆载重、路况、天气、驾驶行为多维度分析，实时推荐最优行驶参数，降低百公里氢耗。",
        "capabilities": [
            "实时氢耗监控与异常检测",
            "基于路况的行驶速度优化建议",
            "驾驶行为评分与节能指导",
            "历史氢耗趋势分析与对标",
        ],
        "tech": "LLM + RAG + 时序预测",
    },
    {
        "key": "route_plan",
        "name": "路径规划 Agent",
        "icon": "route",
        "metric": "续航匹配率 98%+",
        "desc": "融合加氢站分布、车辆剩余氢量、订单目的地，智能规划最优运输路线，确保不断氢。",
        "capabilities": [
            "基于氢量的安全续航圈计算",
            "多加氢站路径择优",
            "实时路况与拥堵避让",
            "多订单串联路径优化",
        ],
        "tech": "图搜索 + OR-Tools + 高德API",
    },
    {
        "key": "station_dispatch",
        "name": "加氢站调度 Agent",
        "icon": "station",
        "metric": "等待时间 -60%",
        "desc": "实时监控各加氢站排队情况，智能分配车辆到最优加氢站，减少等待时间。",
        "capabilities": [
            "加氢站实时排队预测",
            "动态分流与错峰调度",
            "氢价对比与成本优化",
            "储氢量预警与补货建议",
        ],
        "tech": "排队论 + 强化学习",
    },
    {
        "key": "fleet_manage",
        "name": "车队管理 Agent",
        "icon": "fleet",
        "metric": "利用率 +25%",
        "desc": "全车队运力统一调度，基于订单需求与车辆状态智能分配任务，最大化车辆利用率。",
        "capabilities": [
            "车队运力实时画像",
            "订单-车辆智能匹配",
            "司机排班优化",
            "空驶治理与回程货源匹配",
        ],
        "tech": "多目标优化 + MCP协议",
    },
    {
        "key": "cost_analysis",
        "name": "成本分析 Agent",
        "icon": "cost",
        "metric": "运营成本 -18%",
        "desc": "全链路成本拆解：氢能、维保、人工、折旧，提供多维度成本分析与优化建议。",
        "capabilities": [
            "单车全成本核算",
            "氢价波动影响分析",
            "维保成本预测",
            "TCO对标与优化路径",
        ],
        "tech": "OLAP + LLM归因分析",
    },
    {
        "key": "fuelcell_health",
        "name": "燃料电池健康 Agent",
        "icon": "health",
        "metric": "寿命预测准确率 95%+",
        "desc": "基于电堆电压、温度、衰减率等多维数据，预测燃料电池健康状态与剩余寿命。",
        "capabilities": [
            "电堆性能实时评估",
            "衰减趋势预测",
            "维保时机智能推荐",
            "健康度分级告警",
        ],
        "tech": "LSTM时序预测 + 数字孪生",
    },
]


@router.get("/agents", tags=["智能体"])
def list_agents():
    """六大智能体列表"""
    return AGENTS_DATA


@router.get("/agents/{agent_key}", tags=["智能体"])
def get_agent(agent_key: str):
    """智能体详情"""
    for a in AGENTS_DATA:
        if a["key"] == agent_key:
            return a
    return {"detail": "not found"}, 404
