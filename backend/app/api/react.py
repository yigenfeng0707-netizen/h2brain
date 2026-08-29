"""H2Brain - ReAct Decision Reasoning API

Supports real LLM-powered ReAct reasoning (OpenAI-compatible SDK).
When LLM_API_KEY is not configured, falls back to offline samples.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..config import settings
from ..schemas import ReactRequest, ReactResponse, ReactStep
from ..react_engine import ReactEngine

logger = logging.getLogger("h2brain.api.react")

router = APIRouter()

SCENARIOS = {
    "hydrogen_optimization": {
        "name": "氢耗优化",
        "desc": "分析车辆氢耗异常（基于 T05 官方数据包真实遥测）并给出优化建议",
        "query_hint": "V1 车辆最近氢耗偏高，请分析原因并给出优化建议",
    },
    "route_planning": {
        "name": "路径规划",
        "desc": "结合加氢站分布与剩余氢量规划安全运输路线（调度沙盘推演）",
        "query_hint": "氢量 40% 的车辆要跑长途，请规划安全路线",
    },
    "station_dispatch": {
        "name": "加氢站调度",
        "desc": "推荐最优加氢站以减少排队等待（调度沙盘推演）",
        "query_hint": "附近哪个加氢站排队最短？氢价最低的是哪家？",
    },
    "cost_analysis": {
        "name": "成本分析",
        "desc": "分析运营成本结构（真实数据测算），给出降本建议",
        "query_hint": "当前车队的氢燃料成本占比是多少？如何降低？",
    },
    "fleet_management": {
        "name": "车队管理",
        "desc": "车队运力调度与订单-车辆匹配优化（调度沙盘推演）",
        "query_hint": "当前有多个待分配订单，如何分配车辆最优？",
    },
}

# Offline samples (used when LLM is not configured or as fallback)
# 注意：离线样本仅供无 LLM 时的演示，均为基于真实数据口径的示例结论，并明确标注「离线示例」
OFFLINE_SAMPLE = {
    "hydrogen_optimization": ReactResponse(
        scenario="hydrogen_optimization",
        steps=[
            ReactStep(
                thought="用户询问 V1 车辆氢耗偏高，我先查询真实遥测数据中的车辆行程概况",
                action="query_vehicle(vehicle_id='V1')",
                observation="车辆V1（测试车辆1#，湖北襄阳）｜数据期共数十万行遥测｜多个行程｜平均百公里氢耗按 总氢耗÷总里程×100 计算",
            ),
            ReactStep(
                thought="需要定位氢耗偏高的具体行程与工况成因",
                action="analyze_real_trips(vehicle_id='V1')",
                observation="行程列表（真实遥测）：各行程里程、时长、均速、氢耗与百公里氢耗；偏离均值较高的行程集中在重载与爬坡工况段",
            ),
            ReactStep(
                thought="对高氢耗行程做分段归因分析（工况分段+驾驶行为）",
                action="analyze_real_trip_detail(vehicle_id='V1', trip_id=高偏离行程)",
                observation="工况分段显示爬坡/重载段百公里氢耗显著高于均值（判定方法：分段氢耗偏离均值超阈值）；驾驶行为统计显示急加速频次偏高",
            ),
        ],
        final_answer="（离线示例）V1 车辆氢耗偏高的主要成因为重载爬坡工况占比高与急加速驾驶行为：分段分析显示爬坡段百公里氢耗明显偏离均值（判定方法见行程分析）。建议：1. 路线规划避开连续爬坡路段；2. 开展平顺加减速驾驶培训；3. 关注燃料电池健康度变化。启用 LLM 后可获得基于实时数据的针对性量化分析。",
    ),
    "route_planning": ReactResponse(
        scenario="route_planning",
        steps=[
            ReactStep(
                thought="用户需要为氢量 40% 的车辆规划长途路线，先查询车辆状态",
                action="query_vehicle(vehicle_id='V1')",
                observation="车辆当前氢量约 40%，按百公里氢耗可推算安全续航里程（安全续航 = 剩余氢量÷百公里氢耗×100×安全系数）",
            ),
            ReactStep(
                thought="确认沿途可用加氢站（调度沙盘数据）",
                action="query_stations()",
                observation="加氢站列表（调度推演沙盘数据）：各站储氢、排队、氢价与位置信息",
            ),
            ReactStep(
                thought="推荐先在途中加氢站补氢，再直达目的地的方案",
                action="plan_route(vehicle_plate='V1', dest_lng=..., dest_lat=...)",
                observation="路径规划（沙盘推演）：推荐途中补氢方案，总里程、到站氢量与预估成本见规划结果",
            ),
        ],
        final_answer="（离线示例·调度沙盘推演）推荐路线：先在途中综合评分最优的加氢站补氢，再直达目的地。综合评分方法：距离、排队等待（Erlang C 模型预测）、氢价与储氢量多因子加权。启用 LLM 后可针对具体目的地实时规划。",
    ),
}


@router.get("/react/templates", tags=["ReAct Decision"])
def react_templates():
    """ReAct scenario template list"""
    return [
        {"key": k, "name": v["name"], "desc": v["desc"], "query_hint": v["query_hint"]}
        for k, v in SCENARIOS.items()
    ]


@router.post("/react", tags=["ReAct Decision"])
def react_invoke(req: ReactRequest):
    """ReAct decision reasoning

    When LLM_API_KEY is configured, calls real LLM for ReAct reasoning;
    otherwise replays offline samples.
    """
    if settings.llm_enabled:
        try:
            engine = ReactEngine(req)
            return engine.run()
        except Exception as e:
            logger.error("LLM ReAct failed, falling back to offline: %s", e)
            return _react_offline(req)
    return _react_offline(req)


@router.post("/react/stream", tags=["ReAct Decision"])
def react_stream(req: ReactRequest):
    """SSE streaming ReAct reasoning

    When LLM is configured, streams real LLM reasoning steps;
    otherwise streams offline samples.
    """
    if settings.llm_enabled:
        try:
            engine = ReactEngine(req)

            def event_generator():
                try:
                    for event in engine.run_stream():
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"
                except Exception as e:
                    logger.error("LLM stream failed: %s", e)
                    error_event = {
                        "type": "error",
                        "message": f"LLM streaming failed: {str(e)}",
                    }
                    yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
                    yield "data: [DONE]\n\n"

            return StreamingResponse(event_generator(), media_type="text/event-stream")
        except Exception as e:
            logger.error("Failed to create LLM stream, falling back to offline: %s", e)

    # Offline fallback streaming
    def offline_generator():
        sample = OFFLINE_SAMPLE.get(
            req.scenario, OFFLINE_SAMPLE["hydrogen_optimization"]
        )
        for i, step in enumerate(sample.steps):
            yield f"data: {json.dumps({'type': 'step', 'index': i, 'thought': step.thought, 'action': step.action, 'observation': step.observation}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'final', 'answer': sample.final_answer, 'scenario': req.scenario}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(offline_generator(), media_type="text/event-stream")


def _react_offline(req: ReactRequest) -> ReactResponse:
    """Offline sample replay"""
    sample = OFFLINE_SAMPLE.get(req.scenario, OFFLINE_SAMPLE["hydrogen_optimization"])
    return sample
