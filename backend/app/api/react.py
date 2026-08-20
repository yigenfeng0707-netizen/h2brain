"""氢智行 H2Brain - ReAct 决策推理接口

支持 LLM 接入（OpenAI 兼容 SDK），未配置 Key 时回放离线样例。
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..config import settings
from ..schemas import ReactRequest, ReactResponse, ReactStep

router = APIRouter()

SCENARIOS = {
    "hydrogen_optimization": {
        "name": "氢耗优化",
        "desc": "分析车辆氢耗异常，给出优化建议",
        "query_hint": "京A-H2308 最近百公里氢耗偏高，请分析原因并给出优化建议",
    },
    "route_planning": {
        "name": "路径规划",
        "desc": "为车辆规划最优加氢与运输路线",
        "query_hint": "京B-H0816 需从大兴到天津港，氢量40%，请规划路线",
    },
    "station_dispatch": {
        "name": "加氢站调度",
        "desc": "推荐最优加氢站，减少等待",
        "query_hint": "亦庄附近哪 个加氢站排队最短？氢价最低？",
    },
    "cost_analysis": {
        "name": "成本分析",
        "desc": "分析运营成本结构，给出降本建议",
        "query_hint": "本月车队氢能成本占比多少？如何降低？",
    },
    "fleet_management": {
        "name": "车队管理",
        "desc": "车队运力调度与优化",
        "query_hint": "今天有8个待运订单，5辆车可用，如何分配？",
    },
}

OFFLINE_SAMPLE = {
    "hydrogen_optimization": ReactResponse(
        scenario="hydrogen_optimization",
        steps=[
            ReactStep(
                thought="用户询问京A-H2308氢耗偏高的原因，我需要查看该车的运行数据",
                action="query_vehicle_data(plate='京A-H2308')",
                observation="百公里氢耗 11.2kg（车队均值 9.1kg），偏高 23%。近3天主要为重载上坡路段，驾驶评分 72分（偏低）",
            ),
            ReactStep(
                thought="氢耗偏高的可能原因：1.重载上坡路段多 2.驾驶行为激进 3.燃料电池效率衰减",
                action="analyze_factors(vehicle='京A-H2308', dimensions=['route', 'driving', 'fuelcell'])",
                observation="路况贡献 +15%、驾驶行为贡献 +6%、燃料电池效率下降贡献 +2%。主要因素为路段重型化",
            ),
            ReactStep(
                thought="给出针对性优化建议：路线优化、驾驶行为指导、燃料电池检查",
                action="generate_recommendations()",
                observation="建议：1.避开 G106 K35-K42 连续上坡段，改走京津高速 2.培训司机平稳加速 3.安排燃料电池健康检测",
            ),
        ],
        final_answer="京A-H2308 百公里氢耗 11.2kg，高于车队均值 23%。主要原因：近3天重载上坡路段占比高（贡献+15%），驾驶评分偏低（贡献+6%）。建议：1.路线优化避开连续上坡段，预计可降氢耗 1.8kg/百公里；2.平稳加速驾驶培训，预计降 0.7kg/百公里；3.安排燃料电池健康检测。综合优化后预计降至 8.7kg/百公里，月节省氢成本约 2,800元。",
    ),
    "route_planning": ReactResponse(
        scenario="route_planning",
        steps=[
            ReactStep(
                thought="用户需要为京B-H0816规划从大兴到天津港的路线，氢量40%",
                action="query_vehicle(plate='京B-H0816')",
                observation="剩余氢量 40%，续航约 180km。大兴到天津港约 150km，直达可行但氢量紧张",
            ),
            ReactStep(
                thought="需要确认沿途加氢站，确保安全余量",
                action="search_stations(route='大兴-天津港', radius=5)",
                observation="通州物流港加氢站(HRS-005)位于路线中段，距起点 55km，当前无排队，氢价 34元/kg",
            ),
            ReactStep(
                thought="推荐方案：先到通州加氢站补氢，再直奔天津港",
                action="optimize_route(via='HRS-005')",
                observation="推荐路线：大兴 → 通州物流港加氢站(补氢30kg) → 天津港。总里程 152km，到达后剩余氢量 55%，预计氢成本 1,020元",
            ),
        ],
        final_answer="推荐路线：大兴出发 → 通州物流港加氢站(HRS-005)补氢30kg → 天津港。总里程152km，中途补氢后到达时剩余氢量55%，安全余量充足。加氢站当前无排队，氢价34元/kg，预计本次运输氢成本1,020元。相比直达方案（到达时仅剩5%氢量），安全性大幅提升。",
    ),
}


@router.get("/react/templates", tags=["ReAct决策"])
def react_templates():
    """ReAct 场景模板列表"""
    return [
        {"key": k, "name": v["name"], "desc": v["desc"], "query_hint": v["query_hint"]}
        for k, v in SCENARIOS.items()
    ]


@router.post("/react", tags=["ReAct决策"])
def react_invoke(req: ReactRequest):
    """ReAct 决策推理

    配置了 LLM_API_KEY 时调用真实大模型；否则回放离线样例。
    """
    if settings.llm_enabled:
        return _react_with_llm(req)
    return _react_offline(req)


def _react_offline(req: ReactRequest) -> ReactResponse:
    """离线样例回放"""
    sample = OFFLINE_SAMPLE.get(req.scenario, OFFLINE_SAMPLE["hydrogen_optimization"])
    return sample


def _react_with_llm(req: ReactRequest):
    """调用真实 LLM 进行 ReAct 推理（SSE 流式）"""
    # Phase 2 实现：接入 OpenAI 兼容 SDK
    return _react_offline(req)


@router.post("/react/stream", tags=["ReAct决策"])
def react_stream(req: ReactRequest):
    """SSE 流式 ReAct 推理"""

    def event_generator():
        sample = OFFLINE_SAMPLE.get(
            req.scenario, OFFLINE_SAMPLE["hydrogen_optimization"]
        )
        for i, step in enumerate(sample.steps):
            yield f"data: {json.dumps({'type': 'step', 'index': i, 'thought': step.thought, 'action': step.action, 'observation': step.observation}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'final', 'answer': sample.final_answer, 'scenario': req.scenario}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
