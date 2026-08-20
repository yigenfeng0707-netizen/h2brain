"""氢智行 H2Brain - 展示大屏静态数据"""

from fastapi import APIRouter

router = APIRouter()

ARCH_LAYERS = [
    {
        "level": "L5",
        "name": "用户接入层",
        "desc": "车队管理·司机App·加氢站终端·氢能监管平台 | IoT·车载OBD·北斗/高德",
    },
    {
        "level": "L4",
        "name": "智能体服务层",
        "desc": "系统大脑 · 六大氢能智能体协同 · 总控Agent任务编排",
    },
    {
        "level": "L3",
        "name": "数据与检索层",
        "desc": "氢能垂直知识库 | 车辆数字孪生 | 实时运力池 | 氢耗时序数据",
    },
    {
        "level": "L2",
        "name": "核心技术层",
        "desc": "LLM | RAG | MCP协议总线 | 运筹优化 | LSTM时序预测",
    },
    {
        "level": "L1",
        "name": "基础设施层",
        "desc": "氢能示范区私有云 | 百车级并发 | 等保二级 | Grafana驾驶舱",
    },
]

CASE_DATA = {
    "title": "大兴氢能示范区 - 15辆氢能重卡运营优化",
    "period": "2026年6月-8月（3个月）",
    "metrics": [
        {"name": "百公里氢耗", "before": "10.8kg", "after": "9.5kg", "change": "-12%"},
        {"name": "日均运营里程", "before": "280km", "after": "350km", "change": "+25%"},
        {"name": "加氢等待时间", "before": "22min", "after": "8min", "change": "-64%"},
        {
            "name": "月均运营成本",
            "before": "8.2万/车",
            "after": "6.7万/车",
            "change": "-18%",
        },
        {"name": "燃料电池健康度", "before": "78%", "after": "85%", "change": "+7%"},
        {"name": "碳减排", "before": "0kg", "after": "4200kg/月", "change": "新增"},
    ],
    "summary": "通过部署氢智行 H2Brain 六大智能体，15辆氢能重卡在3个月内实现氢耗降低12%、运营成本降低18%、碳减排4.2吨/月的显著成效。",
}

SAAS_PRICING = [
    {
        "name": "基础版",
        "price": "3.8万/年",
        "vehicles": "≤5辆",
        "features": ["氢耗监控", "基础调度", "运营看板"],
    },
    {
        "name": "专业版",
        "price": "8.8万/年",
        "vehicles": "≤20辆",
        "features": ["全部6大Agent", "ReAct决策", "加氢站调度", "成本分析"],
    },
    {
        "name": "企业版",
        "price": "18.8万/年",
        "vehicles": "≤100辆",
        "features": ["专业版全部功能", "API开放", "私有化部署", "专属顾问"],
    },
    {
        "name": "旗舰版",
        "price": "38万/年",
        "vehicles": "不限",
        "features": ["企业版全部功能", "定制Agent", "数字孪生", "驻场服务"],
    },
]


@router.get("/display/architecture", tags=["展示"])
def display_architecture():
    return ARCH_LAYERS


@router.get("/display/case", tags=["展示"])
def display_case():
    return CASE_DATA


@router.get("/display/pricing", tags=["展示"])
def display_pricing():
    return SAAS_PRICING
