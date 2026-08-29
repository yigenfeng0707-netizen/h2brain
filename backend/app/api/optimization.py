"""氢智行 H2Brain - 智能优化接口

- 燃料电池健康分析（电压/热应力/效率/衰减/RUL，真实遥测）
- 路径规划（氢量续航检查、途中加氢推荐、成本预估，沙盘推演）
- 加氢站调度（M/M/c 排队论，排序推荐，沙盘推演）
- 车队优化（多目标订单-车辆匹配，沙盘推演）
"""

from __future__ import annotations

import json

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from ..fuelcell_health import analyze_fuel_cell_health
from ..route_optimizer import plan_route, schedule_station_dispatch
from ..fleet_optimizer import optimize_fleet_assignment

router = APIRouter()


def _json_response(data) -> Response:
    """Serialize data with numpy type support."""

    def convert(obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [convert(v) for v in obj]
        return obj

    return Response(
        content=json.dumps(convert(data), ensure_ascii=False),
        media_type="application/json",
    )


# ---------------------------------------------------------------------------
# Fuel Cell Health
# ---------------------------------------------------------------------------


@router.get("/optimization/fuelcell-health/{vehicle_id}", tags=["智能优化"])
def get_fuelcell_health(vehicle_id: str):
    """获取燃料电池健康分析报告

    基于真实遥测数据分析：电压偏差、热应力、效率衰减、健康评分、RUL预测
    """
    try:
        report = analyze_fuel_cell_health(vehicle_id)
        return _json_response(report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Route Planning
# ---------------------------------------------------------------------------


class RoutePlanRequest(BaseModel):
    vehicle_plate: str
    dest_lng: float = 121.47
    dest_lat: float = 31.23


@router.post("/optimization/route-plan", tags=["智能优化"])
def post_route_plan(req: RoutePlanRequest):
    """路径规划：检查氢气余量，推荐加氢站经停，估算行程成本"""
    try:
        result = plan_route(req.vehicle_plate, req.dest_lng, req.dest_lat)
        return _json_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Station Dispatch
# ---------------------------------------------------------------------------


@router.get("/optimization/station-dispatch/{vehicle_plate}", tags=["智能优化"])
def get_station_dispatch(vehicle_plate: str):
    """加氢站智能调度推荐

    基于 M/M/c Erlang C 排队模型计算等待时间，综合距离、库存、价格评分排序
    """
    try:
        result = schedule_station_dispatch(vehicle_plate)
        return _json_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Fleet Optimization
# ---------------------------------------------------------------------------


@router.get("/optimization/fleet", tags=["智能优化"])
def get_fleet_optimization(max_orders: int = Query(10, ge=1, le=50)):
    """车队多目标优化：订单-车辆智能匹配

    评分维度：氢气充足率(30%) + 就近性(25%) + 利用率(20%) + 成本(15%) + 负载均衡(10%)
    """
    try:
        result = optimize_fleet_assignment(max_orders=max_orders)
        return _json_response(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
