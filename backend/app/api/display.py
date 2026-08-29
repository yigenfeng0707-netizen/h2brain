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
    "title": "氢能重卡试点运营优化（襄阳·吐鲁番双站点真实数据回测）",
    "period": "2026-08-01 ~ 2026-08-18（T05 官方数据包，18天）",
    "metrics": [
        {
            "name": "测试车辆",
            "before": "2辆",
            "after": "2辆",
            "change": "V1襄阳/V2吐鲁番",
            "method": "官方 T05 数据包提供的全部真实测试车辆（63.4万行遥测）",
        },
        {
            "name": "工况识别吻合率",
            "before": "人工标注",
            "after": "100%",
            "change": "多维证据矩阵 v2.1",
            "method": "分类器输出与官方手工记录表逐行程比对，28个行程全吻合",
        },
        {
            "name": "百公里氢耗",
            "before": "实测值",
            "after": "推演优化",
            "change": "见价值量化页",
            "method": "总氢耗÷总里程×100，实测数据由遥测累计氢耗列差分汇总",
        },
        {
            "name": "异常工况识别",
            "before": "人工抽检",
            "after": "全自动",
            "change": "全覆盖",
            "method": "对每个行程分段计算百公里氢耗偏离度，超均值±1.5σ标记为异常",
        },
        {
            "name": "碳减排",
            "before": "0kg",
            "after": "6871kg",
            "change": "绿氢口径",
            "method": "柴油CO2=里程8708km÷100×30L/100km×2.63kg/L，绿氢按0排放计",
        },
        {
            "name": "成本节省",
            "before": "0元",
            "after": "见价值量化页",
            "change": "对标柴油重卡",
            "method": "节省=(柴油燃料+维护成本)-(氢燃料+维护成本)，参数见价值量化页",
        },
    ],
    "summary": (
        "本案例基于 T05 官方数据包 2 辆真实测试重卡（V1 湖北襄阳 / V2 新疆吐鲁番）"
        "18 天 63.4 万行遥测的回测分析：多维证据矩阵路况分类器以 100% 吻合率对齐官方手工记录，"
        "行程级氢耗异常与驾驶行为自动识别全覆盖，经济与碳减排价值依据对标同级柴油重卡（参数与公式见「价值量化分析」页）。"
        "加氢站调度与路径规划为沙盘推演演示，页面上均有明确标注。"
    ),
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
