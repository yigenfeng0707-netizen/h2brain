"""氢智行 H2Brain - 运营数据接口"""

from fastapi import APIRouter

from ..mock_data import (
    get_events,
    get_kpi,
    get_pool_summary,
    get_stations,
    get_vehicles,
)

router = APIRouter()


@router.get("/operations/summary", tags=["运营数据"])
def operations_summary():
    """运营总览 KPI"""
    return get_kpi()


@router.get("/operations/vehicles", tags=["运营数据"])
def operations_vehicles():
    """车辆列表"""
    return get_vehicles()


@router.get("/operations/stations", tags=["运营数据"])
def operations_stations():
    """加氢站列表"""
    return get_stations()


@router.get("/operations/pool", tags=["运营数据"])
def operations_pool():
    """车队汇总"""
    return get_pool_summary()


@router.get("/operations/events", tags=["运营数据"])
def operations_events():
    """实时事件流"""
    return get_events()


@router.get("/operations/trends", tags=["运营数据"])
def operations_trends():
    """氢耗趋势（7天模拟）"""
    import random

    days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return {
        "hydrogen_consumption": [
            {"day": d, "value": round(random.uniform(8.0, 11.5), 1)} for d in days
        ],
        "cost_trend": [
            {"day": d, "value": round(random.uniform(280, 390), 0)} for d in days
        ],
        "efficiency": [
            {"day": d, "value": round(random.uniform(83, 91), 1)} for d in days
        ],
    }
