"""氢智行 H2Brain - 运营数据接口 (真实数据版)

大屏数据全部来自 data_processor 的真实遥测分析 (V1/V2 两辆测试车辆,
共 63 万行数据, 28 个行程, 8708 km)。不再使用 mock 车队。

- /operations/summary  → 真实运营 KPI (车辆/行程/里程/氢耗/碳减排)
- /operations/vehicles → 2 辆真实车辆最新状态 (SOC/氢量/里程/位置)
- /operations/events   → 真实事件流 (驾驶行为 + 行程完成, 取最近行程)
- /operations/trends   → 按日真实里程/氢耗聚合 (数据期 08-01 ~ 08-18)
- /operations/stations / pool → 保留规划沙盘 mock (调度推演功能, 非大屏)
"""

from fastapi import APIRouter

import numpy as np

from ..data_processor import get_processor
from ..mock_data import get_pool_summary, get_stations

router = APIRouter()

# 柴油重卡对标（与 value_analysis.py 口径统一）: 49T 柴油车 30L/100km × 2.63 kg CO2/L → 0.789 kg CO2/km
DIESEL_CO2_PER_KM = 0.789

_events_cache: dict = {}
_trends_cache: dict = {}


def _weighted_h2_100km(trips_km: list, trips_h2: list) -> float:
    total_km = sum(trips_km)
    total_h2 = sum(trips_h2)
    return round(total_h2 / total_km * 100, 2) if total_km > 0 else 0.0


@router.get("/operations/summary", tags=["运营数据"])
def operations_summary():
    """运营总览 KPI — 真实数据"""
    proc = get_processor()
    proc._ensure_loaded()

    vehicles = proc.get_vehicles()
    total_km = sum(v["total_distance_km"] for v in vehicles)
    total_h2 = sum(v["total_h2_consumed_kg"] for v in vehicles)
    trip_count = sum(v["total_trips"] for v in vehicles)
    avg_h2 = _weighted_h2_100km(
        [v["total_distance_km"] for v in vehicles],
        [v["total_h2_consumed_kg"] for v in vehicles],
    )

    return {
        "vehicles_total": len(vehicles),
        "vehicles_online": len(vehicles),
        "trips_total": trip_count,
        "total_km": round(total_km, 0),
        "total_h2_kg": round(total_h2, 1),
        "avg_hydrogen_consumption": avg_h2,
        "carbon_reduction": round(total_km * DIESEL_CO2_PER_KM, 0),
        "data_rows": sum(v["total_rows"] for v in vehicles),
        "data_period": "2026-08-01 ~ 2026-08-18",
        "data_source": "T05 官方测试车辆真实遥测",
    }


@router.get("/operations/vehicles", tags=["运营数据"])
def operations_vehicles():
    """车辆列表 — 2 辆真实测试车辆最新状态"""
    proc = get_processor()
    proc._ensure_loaded()

    result = []
    for v in proc.get_vehicles():
        vid = v["vehicle_id"]
        df = proc._vehicle_data.get(vid)
        status, soc, h2_pct, lng, lat, last_seen = "offline", None, None, None, None, None
        if df is not None and len(df) > 0:
            tail = df.iloc[-1]
            last_seen = str(tail["timestamp"])
            minutes_since = (
                np.datetime64("2026-08-18T23:59") - tail["timestamp"].to_datetime64()
            ) / np.timedelta64(1, "m")
            moving = float(tail["speed"]) > 1
            if minutes_since > 24 * 60:
                status = "offline"
            elif moving:
                status = "in_transit"
            else:
                status = "online"
            soc = round(float(tail["batt_soc"]), 0) if not np.isnan(tail["batt_soc"]) else None
            h2_pct = (
                round(float(tail["h2_percent"]), 0)
                if not np.isnan(tail["h2_percent"])
                else None
            )
            if not np.isnan(tail["gps_lon"]):
                lng, lat = round(float(tail["gps_lon"]), 4), round(float(tail["gps_lat"]), 4)

        result.append(
            {
                "vehicle_id": vid,
                "plate": v["label"],
                "region": v["region"],
                "status": status,
                "soc": soc,
                "h2_percent": h2_pct,
                "lng": lng,
                "lat": lat,
                "last_seen": last_seen,
                "total_km": round(float(v["total_distance_km"]), 0),
                "total_trips": v["total_trips"],
                "h2_per_100km": round(float(v["avg_h2_per_100km"]), 2),
                "total_h2_kg": round(float(v["total_h2_consumed_kg"]), 1),
                "date_range": v["date_range"],
                "total_rows": v["total_rows"],
            }
        )
    return result


@router.get("/operations/stations", tags=["运营数据"])
def operations_stations():
    """加氢站列表 (调度规划沙盘)"""
    return get_stations()


@router.get("/operations/pool", tags=["运营数据"])
def operations_pool():
    """车队汇总 (调度规划沙盘)"""
    return get_pool_summary()


@router.get("/operations/events", tags=["运营数据"])
def operations_events():
    """真实事件流: 最近行程的驾驶行为事件 + 行程完成事件"""
    if _events_cache.get("events"):
        return _events_cache["events"]

    proc = get_processor()
    proc._ensure_loaded()

    events = []
    from ..data_processor import _detect_driving_behaviors

    for vid in ["V1", "V2"]:
        trips = proc._trips.get(vid, [])
        label = "V1" if vid == "V1" else "V2"
        # 最近 2 个行程的驾驶行为事件
        for trip in trips[-2:]:
            try:
                behaviors = _detect_driving_behaviors(trip)
                for b in behaviors[:8]:
                    idx = b.get("timestamp_idx", 0)
                    ev_time = (
                        str(trip["timestamp"].iloc[min(idx, len(trip) - 1)])
                        if idx is not None and len(trip) > 0
                        else str(trip["timestamp"].iloc[0])
                    )
                    events.append(
                        {
                            "level": "warning" if b.get("severity", 0) > 1 else "info",
                            "title": b.get("type", "驾驶行为"),
                            "detail": f"{label} {b.get('description', '')}",
                            "timestamp": ev_time,
                        }
                    )
            except Exception:
                continue
        # 行程完成事件
        if trips:
            last = trips[-1]
            events.append(
                {
                    "level": "info",
                    "title": "行程完成",
                    "detail": (
                        f"{label} 最新行程 {round(float(last['mileage'].iloc[-1] - last['mileage'].iloc[0]), 1)} km"
                    ),
                    "timestamp": str(last["timestamp"].iloc[-1]),
                }
            )

    events.sort(key=lambda e: e["timestamp"], reverse=True)
    result = events[:30]
    _events_cache["events"] = result
    return result


@router.get("/operations/trends", tags=["运营数据"])
def operations_trends():
    """按日真实里程 / 氢耗 / 平均百公里氢耗"""
    if _trends_cache.get("trends"):
        return _trends_cache["trends"]

    proc = get_processor()
    proc._ensure_loaded()

    daily = {}
    for vid in ["V1", "V2"]:
        for trip in proc._trips.get(vid, []):
            day = str(trip["timestamp"].iloc[0].date())
            km = float(trip["mileage"].iloc[-1] - trip["mileage"].iloc[0])
            h2 = float(trip["h2_consumed_cum"].iloc[-1] - trip["h2_consumed_cum"].iloc[0])
            if day not in daily:
                daily[day] = {"km": 0.0, "h2": 0.0}
            daily[day]["km"] += max(0.0, km)
            daily[day]["h2"] += max(0.0, h2)

    days = sorted(daily.keys())
    result = {
        "daily_km": [
            {"day": d[5:], "value": round(daily[d]["km"], 1)} for d in days
        ],
        "daily_h2": [
            {"day": d[5:], "value": round(daily[d]["h2"], 1)} for d in days
        ],
        "h2_per_100km": [
            {
                "day": d[5:],
                "value": round(daily[d]["h2"] / daily[d]["km"] * 100, 2)
                if daily[d]["km"] > 1
                else 0,
            }
            for d in days
        ],
    }
    _trends_cache["trends"] = result
    return result
