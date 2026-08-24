"""H2Brain - Agent Display & Execution API

Provides six hydrogen-energy intelligent agents:
- Static metadata for display
- Execution endpoint that routes to the ReAct engine
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..config import settings
from ..schemas import ReactRequest

logger = logging.getLogger("h2brain.api.agents")

router = APIRouter()

AGENTS_DATA = [
    {
        "key": "hydrogen_opt",
        "name": "Hydrogen Consumption Optimization Agent",
        "icon": "h2",
        "metric": "Consumption -12% per 100km",
        "desc": "Multi-dimensional analysis based on vehicle load, road conditions, weather, and driving behavior to recommend optimal driving parameters and reduce hydrogen consumption per 100km.",
        "capabilities": [
            "Real-time consumption monitoring and anomaly detection",
            "Road-condition-based speed optimization recommendations",
            "Driving behavior scoring and energy-saving guidance",
            "Historical consumption trend analysis and benchmarking",
        ],
        "tech": "LLM + RAG + Time Series Prediction",
        "scenario": "hydrogen_optimization",
    },
    {
        "key": "route_plan",
        "name": "Route Planning Agent",
        "icon": "route",
        "metric": "Range matching rate 98%+",
        "desc": "Integrates refueling station distribution, remaining hydrogen, and order destinations to plan optimal transport routes ensuring vehicles never run out of hydrogen.",
        "capabilities": [
            "Safety range circle calculation based on hydrogen level",
            "Multi-station route optimization",
            "Real-time traffic and congestion avoidance",
            "Multi-order串联 route optimization",
        ],
        "tech": "Haversine Distance + Range Circle + Multi-station Optimization",
        "scenario": "route_planning",
    },
    {
        "key": "station_dispatch",
        "name": "Station Dispatch Agent",
        "icon": "station",
        "metric": "Wait time -60%",
        "desc": "Monitors real-time station queues and intelligently assigns vehicles to optimal stations, reducing waiting time.",
        "capabilities": [
            "Real-time station queue prediction",
            "Dynamic分流 and off-peak scheduling",
            "Hydrogen price comparison and cost optimization",
            "Storage warning and restock recommendations",
        ],
        "tech": "M/M/c Erlang C Queuing Theory + Multi-factor Scoring",
        "scenario": "station_dispatch",
    },
    {
        "key": "fleet_manage",
        "name": "Fleet Management Agent",
        "icon": "fleet",
        "metric": "Utilization +25%",
        "desc": "Unified fleet capacity scheduling, intelligent order-vehicle matching based on order demand and vehicle status to maximize utilization.",
        "capabilities": [
            "Real-time fleet capacity profiling",
            "Intelligent order-vehicle matching",
            "Driver shift optimization",
            "Empty-trip governance and return freight matching",
        ],
        "tech": "Multi-objective Weighted Scoring (5-dimension) + Greedy Assignment",
        "scenario": "fleet_management",
    },
    {
        "key": "cost_analysis",
        "name": "Cost Analysis Agent",
        "icon": "cost",
        "metric": "Operating cost -18%",
        "desc": "Full-chain cost breakdown: hydrogen, maintenance, labor, depreciation. Provides multi-dimensional cost analysis and optimization recommendations.",
        "capabilities": [
            "Per-vehicle full cost accounting",
            "Hydrogen price fluctuation impact analysis",
            "Maintenance cost prediction",
            "TCO benchmarking and optimization path",
        ],
        "tech": "OLAP + LLM Attribution Analysis",
        "scenario": "cost_analysis",
    },
    {
        "key": "fuelcell_health",
        "name": "Fuel Cell Health Agent",
        "icon": "health",
        "metric": "Health score 0-100 + RUL prediction",
        "desc": "Based on stack voltage, temperature, degradation rate and other multi-dimensional data to predict fuel cell health status and remaining lifespan.",
        "capabilities": [
            "Polarization curve sampling across power ranges",
            "Thermal stress analysis (inlet-outlet temperature differential)",
            "Efficiency analysis (power vs hydrogen consumption)",
            "Degradation trend prediction and RUL estimation",
            "Health score computation (0-100) and maintenance recommendations",
        ],
        "tech": "Polarization Curve Analysis + Linear RUL Prediction",
        "scenario": "fuelcell_health",
    },
]

# Map agent key -> scenario for ReAct engine
AGENT_SCENARIO_MAP = {a["key"]: a["scenario"] for a in AGENTS_DATA}


class AgentExecRequest(BaseModel):
    """Request body for agent execution."""

    query: str = Field(..., description="User question for the agent")
    vehicle_plate: str | None = Field(
        None, description="Target vehicle plate (optional)"
    )
    context: dict | None = Field(None, description="Additional context (optional)")


@router.get("/agents", tags=["Agents"])
def list_agents():
    """List all six agents"""
    # Add LLM status to each agent
    result = []
    for a in AGENTS_DATA:
        agent_info = dict(a)
        agent_info["llm_enabled"] = settings.llm_enabled
        result.append(agent_info)
    return result


@router.get("/agents/{agent_key}", tags=["Agents"])
def get_agent(agent_key: str):
    """Get agent details"""
    for a in AGENTS_DATA:
        if a["key"] == agent_key:
            agent_info = dict(a)
            agent_info["llm_enabled"] = settings.llm_enabled
            return agent_info
    raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")


@router.post("/agents/{agent_key}/execute", tags=["Agents"])
def execute_agent(agent_key: str, req: AgentExecRequest):
    """Execute an agent with a user query.

    Routes to the ReAct engine with the appropriate scenario.
    When LLM is configured, performs real LLM reasoning;
    otherwise returns offline sample results.
    """
    if agent_key not in AGENT_SCENARIO_MAP:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    scenario = AGENT_SCENARIO_MAP[agent_key]

    # Build ReactRequest
    react_req = ReactRequest(
        scenario=scenario,
        query=req.query,
        vehicle_plate=req.vehicle_plate,
        context=req.context,
    )

    if settings.llm_enabled:
        try:
            from ..react_engine import ReactEngine

            engine = ReactEngine(react_req)
            result = engine.run()
            return {
                "agent_key": agent_key,
                "agent_name": next(
                    a["name"] for a in AGENTS_DATA if a["key"] == agent_key
                ),
                "llm_enabled": True,
                "result": result,
            }
        except Exception as e:
            logger.error(
                "Agent '%s' LLM execution failed, falling back to offline: %s",
                agent_key,
                e,
            )

    # Offline fallback
    from .react import _react_offline

    result = _react_offline(react_req)
    return {
        "agent_key": agent_key,
        "agent_name": next(a["name"] for a in AGENTS_DATA if a["key"] == agent_key),
        "llm_enabled": False,
        "result": result,
    }


@router.post("/agents/{agent_key}/execute/stream", tags=["Agents"])
def execute_agent_stream(agent_key: str, req: AgentExecRequest):
    """Execute an agent with SSE streaming (immune to gateway/axios timeouts).

    Events:
      {"type": "step", "index": N, "thought": ..., "action": ..., "observation": ...}
      {"type": "final", "answer": ..., "scenario": ...}
      {"type": "error", "message": ...}
      [DONE]
    """
    if agent_key not in AGENT_SCENARIO_MAP:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_key}' not found")

    scenario = AGENT_SCENARIO_MAP[agent_key]
    react_req = ReactRequest(
        scenario=scenario,
        query=req.query,
        vehicle_plate=req.vehicle_plate,
        context=req.context,
    )

    def event_generator():
        if not settings.llm_enabled:
            err = {"type": "error", "message": "LLM 未配置"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        try:
            from ..react_engine import ReactEngine

            engine = ReactEngine(react_req)
            for event in engine.run_stream():
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:  # noqa: BLE001 - top-level guard for the stream
            logger.error("Agent '%s' stream failed: %s", agent_key, e)
            err = {"type": "error", "message": f"推理失败: {e}"}
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
