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
        "name": "Hydrogen Consumption Optimization",
        "desc": "Analyze vehicle hydrogen consumption anomalies and provide optimization recommendations",
        "query_hint": "jingA-H2308 recent fuel consumption is high, please analyze and recommend optimizations",
    },
    "route_planning": {
        "name": "Route Planning",
        "desc": "Plan optimal refueling and transport routes for vehicles",
        "query_hint": "jingB-H0816 needs to go from Daxing to Tianjin Port, hydrogen at 40%, please plan the route",
    },
    "station_dispatch": {
        "name": "Station Dispatch",
        "desc": "Recommend the best refueling station to reduce waiting time",
        "query_hint": "Which station near Yizhuang has the shortest queue? Lowest hydrogen price?",
    },
    "cost_analysis": {
        "name": "Cost Analysis",
        "desc": "Analyze operating cost structure and provide cost reduction recommendations",
        "query_hint": "What proportion is hydrogen cost in the fleet this month? How to reduce it?",
    },
    "fleet_management": {
        "name": "Fleet Management",
        "desc": "Fleet capacity scheduling and optimization",
        "query_hint": "Today there are 8 pending orders and 5 available vehicles, how to assign them?",
    },
}

# Offline samples (used when LLM is not configured or as fallback)
OFFLINE_SAMPLE = {
    "hydrogen_optimization": ReactResponse(
        scenario="hydrogen_optimization",
        steps=[
            ReactStep(
                thought="The user is asking about high fuel consumption for jingA-H2308, I need to check the vehicle's operating data",
                action="query_vehicle(plate='jingA-H2308')",
                observation="Consumption 11.2kg/100km (fleet avg 9.1kg), 23% above average. Recent 3 days mainly heavy-load uphill routes, driving score 72 (low)",
            ),
            ReactStep(
                thought="Possible causes for high consumption: 1. Heavy-load uphill routes 2. Aggressive driving 3. Fuel cell efficiency degradation",
                action="analyze_factors(vehicle='jingA-H2308', dimensions=['route', 'driving', 'fuelcell'])",
                observation="Route contribution +15%, driving behavior +6%, fuel cell efficiency decline +2%. Main factor is route heavy-load",
            ),
            ReactStep(
                thought="Provide targeted optimization recommendations: route optimization, driving guidance, fuel cell inspection",
                action="generate_recommendations()",
                observation="Recommendations: 1. Avoid G106 K35-K42 continuous uphill, take Jingjin Expressway instead 2. Train driver on smooth acceleration 3. Schedule fuel cell health check",
            ),
        ],
        final_answer="jingA-H2308 consumption is 11.2kg/100km, 23% above fleet average. Main causes: heavy-load uphill routes in recent 3 days (+15%), low driving score (+6%). Recommendations: 1. Route optimization to avoid continuous uphill, expected savings 1.8kg/100km; 2. Smooth acceleration training, expected savings 0.7kg/100km; 3. Schedule fuel cell health check. After comprehensive optimization, expected reduction to 8.7kg/100km, monthly savings ~2,800 yuan.",
    ),
    "route_planning": ReactResponse(
        scenario="route_planning",
        steps=[
            ReactStep(
                thought="User needs to plan a route from Daxing to Tianjin Port for jingB-H0816, hydrogen at 40%",
                action="query_vehicle(plate='jingB-H0816')",
                observation="Remaining hydrogen 40%, range ~180km. Daxing to Tianjin Port ~150km, direct route feasible but hydrogen is tight",
            ),
            ReactStep(
                thought="Need to confirm refueling stations along the route for safety margin",
                action="search_stations(route='Daxing-Tianjin Port', radius=5)",
                observation="Tongzhou Logistics Port Station (HRS-005) is mid-route, 55km from start, no queue, price 34 yuan/kg",
            ),
            ReactStep(
                thought="Recommended plan: refuel at Tongzhou station first, then direct to Tianjin Port",
                action="optimize_route(via='HRS-005')",
                observation="Recommended route: Daxing -> Tongzhou Logistics Port Station (refuel 30kg) -> Tianjin Port. Total 152km, arrival hydrogen 55%, estimated cost 1,020 yuan",
            ),
        ],
        final_answer="Recommended route: Daxing -> Tongzhou Logistics Port Station (HRS-005, refuel 30kg) -> Tianjin Port. Total 152km, arrival hydrogen 55%, sufficient safety margin. Station has no queue, price 34 yuan/kg, estimated cost 1,020 yuan. Compared to direct route (only 5% hydrogen on arrival), safety is greatly improved.",
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
