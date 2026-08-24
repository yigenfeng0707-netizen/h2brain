"""H2Brain - ReAct Reasoning Engine

Implements the Thought -> Action -> Observation loop powered by LLM.
Tools query real data from mock_data and data_processor.

When LLM is not configured, falls back to offline samples gracefully.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Generator, Callable

from . import llm_client
from .schemas import ReactRequest, ReactResponse, ReactStep
from .mock_data import (
    get_vehicles,
    get_stations,
    get_orders,
    get_kpi,
    get_pool_summary,
    get_events,
)

logger = logging.getLogger("h2brain.react")

MAX_ITERATIONS = 5

# ---------------------------------------------------------------------------
# Tool definitions - each tool returns a string observation
# ---------------------------------------------------------------------------

TOOL_DESCRIPTIONS = [
    {
        "name": "query_vehicle",
        "desc": "Query a single vehicle by plate number. Returns status, hydrogen level, consumption, range, fleet, driver, fuel cell health.",
        "params": "plate (str): vehicle plate number, e.g. 'jingA-H2308'",
    },
    {
        "name": "query_vehicles",
        "desc": "Query all vehicles in the fleet. Returns a summary list with plate, status, hydrogen level, consumption, range.",
        "params": "none",
    },
    {
        "name": "query_stations",
        "desc": "Query all hydrogen refueling stations. Returns station name, location, storage, queue length, wait time, price.",
        "params": "none",
    },
    {
        "name": "query_orders",
        "desc": "Query transport orders. Returns order id, cargo type, origin, destination, distance, hydrogen needed, fee, status.",
        "params": "none",
    },
    {
        "name": "query_kpi",
        "desc": "Query fleet-level KPIs: total vehicles, online count, avg consumption, avg cost, efficiency, carbon reduction.",
        "params": "none",
    },
    {
        "name": "query_pool_summary",
        "desc": "Query fleet pool summary: total, online, in_transit, refueling, low_hydrogen, offline counts.",
        "params": "none",
    },
    {
        "name": "query_events",
        "desc": "Query recent realtime events: dispatch, refuel, alerts, optimizations, completions.",
        "params": "none",
    },
    {
        "name": "analyze_real_trips",
        "desc": "Query real telemetry trip data for a vehicle. Returns trip list with distance, duration, h2 consumption, avg speed.",
        "params": "vehicle_id (str): 'V1' or 'V2'",
    },
    {
        "name": "analyze_real_trip_detail",
        "desc": "Query detailed analysis of a specific real trip: road segments, anomalies, driving behaviors, factor analysis.",
        "params": "vehicle_id (str): 'V1' or 'V2'; trip_id (int): trip index",
    },
    {
        "name": "compute_cost",
        "desc": "Compute fleet cost breakdown: hydrogen cost, maintenance, labor, depreciation. Returns per-vehicle and total.",
        "params": "none",
    },
    {
        "name": "analyze_fuelcell_health",
        "desc": "Analyze fuel cell health from real telemetry: voltage analysis, thermal stress, efficiency, degradation trend, health score (0-100), RUL prediction, maintenance recommendations.",
        "params": "vehicle_id (str): 'V1' or 'V2'",
    },
    {
        "name": "plan_route",
        "desc": "Plan optimal route for a vehicle to a destination. Checks hydrogen sufficiency, recommends refueling stops if needed, estimates trip cost.",
        "params": "vehicle_plate (str): plate number; dest_lng (float): longitude; dest_lat (float): latitude",
    },
    {
        "name": "schedule_station_dispatch",
        "desc": "Recommend the best refueling station for a vehicle based on distance, queue length (M/M/c Erlang C wait time), storage, and price. Returns ranked station list.",
        "params": "vehicle_plate (str): plate number",
    },
    {
        "name": "optimize_fleet",
        "desc": "Optimize order-vehicle matching using multi-objective scoring (hydrogen sufficiency, proximity, utility, cost, load balance). Returns assignments with profit estimates.",
        "params": "max_orders (int): max orders to assign, default 10",
    },
]


def _tool_query_vehicle(params: dict) -> str:
    plate = params.get("plate", "")
    # Extract alphanumeric part for matching (handles both Chinese and pinyin prefixes)
    plate_clean = plate.replace(" ", "").replace("-", "").replace("\u00b7", "").strip()
    # Extract just the alphanumeric suffix (e.g. "H2308" from "jingA-H2308" or "jingA-H2308")
    import re as _re

    plate_suffix = _re.sub(r"[^A-Za-z0-9]", "", plate_clean)
    # Take last 4+ chars as the matching key
    match_key = plate_suffix[-5:] if len(plate_suffix) >= 5 else plate_suffix

    for v in get_vehicles():
        v_plate_clean = v.plate.replace(" ", "").replace("-", "").replace("\u00b7", "")
        v_suffix = _re.sub(r"[^A-Za-z0-9]", "", v_plate_clean)
        v_key = v_suffix[-5:] if len(v_suffix) >= 5 else v_suffix

        if (
            (match_key and v_key and match_key.lower() == v_key.lower())
            or (plate_clean.lower() in v_plate_clean.lower())
            or (v_plate_clean.lower() in plate_clean.lower())
        ):
            return (
                f"Vehicle: {v.plate} | Driver: {v.driver_name} | Fleet: {v.fleet_name} | "
                f"Model: {v.model} | Status: {v.status.value} | "
                f"Hydrogen: {v.hydrogen_level}% | Range: {v.range_remaining}km | "
                f"Consumption: {v.hydrogen_consumption} kg/100km | "
                f"Fuel Cell Health: {v.fuel_cell_health.value} | "
                f"Today Orders: {v.today_orders} | "
                f"Location: ({v.lng:.4f}, {v.lat:.4f}) | "
                f"Monthly Mileage: {v.mileage:.0f}km"
            )
    return f"Vehicle not found: {plate}. Available plates: {[v.plate for v in get_vehicles()[:5]]}..."


def _tool_query_vehicles(params: dict) -> str:
    vehicles = get_vehicles()
    lines = [f"Total {len(vehicles)} vehicles:\n"]
    for v in vehicles:
        lines.append(
            f"- {v.plate} [{v.status.value}] H2={v.hydrogen_level}% "
            f"Range={v.range_remaining}km Consumption={v.hydrogen_consumption}kg/100km "
            f"Health={v.fuel_cell_health.value} Fleet={v.fleet_name} Driver={v.driver_name}"
        )
    return "\n".join(lines)


def _tool_query_stations(params: dict) -> str:
    stations = get_stations()
    lines = [f"Total {len(stations)} stations:\n"]
    for s in stations:
        lines.append(
            f"- {s.station_id} {s.name} [{s.status}] "
            f"Storage={s.current_storage}/{s.storage_capacity}kg "
            f"Queue={s.queue_length} Wait={s.avg_wait_time}min "
            f"Price={s.price_per_kg} yuan/kg "
            f"Pressure={s.hydrogen_pressure}MPa "
            f"Location=({s.lng:.4f}, {s.lat:.4f})"
        )
    return "\n".join(lines)


def _tool_query_orders(params: dict) -> str:
    orders = get_orders()
    lines = [f"Total {len(orders)} orders:\n"]
    for o in orders:
        lines.append(
            f"- {o.order_id} [{o.status.value}] "
            f"{o.origin} -> {o.destination} "
            f"Cargo={o.cargo_type} Dist={o.distance}km "
            f"H2_needed={o.hydrogen_needed}kg Fee={o.fee}yuan "
            f"Vehicle={o.vehicle_plate}"
        )
    return "\n".join(lines)


def _tool_query_kpi(params: dict) -> str:
    k = get_kpi()
    # Also include real-data KPIs from actual telemetry
    real_kpi_lines = []
    try:
        from .data_processor import get_processor

        processor = get_processor()
        for vid in ("V1", "V2"):
            trips = processor.get_trips(vid)
            if trips:
                total_km = sum(t["distance_km"] for t in trips)
                total_h2 = sum(t["h2_consumed_kg"] for t in trips)
                avg_h2_per_100 = total_h2 / total_km * 100 if total_km > 0 else 0
                real_kpi_lines.append(
                    f"  [Real] {vid}: {len(trips)} trips, {total_km:.0f}km, "
                    f"{total_h2:.1f}kg H2, {avg_h2_per_100:.2f}kg/100km"
                )
    except Exception as e:
        real_kpi_lines.append(f"  [Real] data unavailable: {e}")

    lines = [
        "Fleet KPI (Simulated):",
        f"  Vehicles: {k.vehicles_total} (online={k.vehicles_online}, in_transit={k.vehicles_in_transit})",
        f"  Fleets: {k.fleets}",
        f"  Orders Today: {k.orders_today}",
        f"  Avg Consumption: {k.avg_hydrogen_consumption} kg/100km",
        f"  Avg Cost: {k.avg_hydrogen_cost} yuan/100km",
        f"  H2 Efficiency: {k.hydrogen_efficiency}%",
        f"  Fuel Cell Avg Health: {k.fuel_cell_avg_health}%",
        f"  Cost Saved Today: {k.cost_saved_today} yuan",
        f"  Carbon Reduction: {k.carbon_reduction} kg CO2",
        "\nReal Telemetry KPI:",
    ]
    lines.extend(real_kpi_lines)
    return "\n".join(lines)


def _tool_query_pool_summary(params: dict) -> str:
    p = get_pool_summary()
    return (
        f"Fleet Pool Summary:\n"
        f"  Total: {p.total} | Online: {p.online} | In Transit: {p.in_transit}\n"
        f"  Refueling: {p.refueling} | Low Hydrogen: {p.low_hydrogen} | Offline: {p.offline}\n"
        f"  Fleets: {p.fleets}"
    )


def _tool_query_events(params: dict) -> str:
    events = get_events()
    lines = [f"Recent {len(events)} events:\n"]
    for e in events[:10]:
        lines.append(
            f"- [{e.level.value.upper()}] {e.title}: {e.detail} "
            f"(Vehicle: {e.vehicle_plate or 'N/A'}) @ {e.timestamp}"
        )
    return "\n".join(lines)


def _tool_analyze_real_trips(params: dict) -> str:
    vehicle_id = params.get("vehicle_id", "V1")
    try:
        from .data_processor import get_processor

        processor = get_processor()
        trips = processor.get_trips(vehicle_id)
        if not trips:
            return f"No trips found for vehicle {vehicle_id}"
        lines = [f"Vehicle {vehicle_id}: {len(trips)} trips\n"]
        for t in trips:
            lines.append(
                f"- Trip {t['trip_id']} [{t['date']} {t['start_time']}-{t['end_time']}] "
                f"Dist={t['distance_km']}km Dur={t['duration_h']}h "
                f"AvgSpeed={t['avg_speed']}km/h "
                f"H2={t['h2_consumed_kg']}kg ({t['h2_per_100km']}kg/100km) "
                f"Power={t['stack_power_avg']}kW"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("analyze_real_trips failed: %s", e)
        return f"Real data analysis unavailable: {e}"


def _tool_analyze_real_trip_detail(params: dict) -> str:
    vehicle_id = params.get("vehicle_id", "V1")
    trip_id = params.get("trip_id", 0)
    try:
        from .data_processor import get_processor

        processor = get_processor()
        detail = processor.get_trip_detail(vehicle_id, int(trip_id))
        if detail is None:
            return f"Trip {trip_id} of {vehicle_id} not found"

        ov = detail["overview"]
        anomalies = detail.get("anomalies", [])
        behaviors = detail.get("driving_behaviors", [])
        factors = detail.get("factor_analysis", {})
        road_segs = detail.get("road_segments", [])

        lines = [
            f"Trip {trip_id} ({vehicle_id}) Detail:\n",
            f"  Distance: {ov['distance_km']}km | Duration: {ov['duration_h']}h | Avg Speed: {ov['avg_speed']}km/h",
            f"  H2 Consumed: {ov['h2_consumed_kg']}kg | H2/100km: {ov['h2_per_100km']}kg",
            f"  Stack Power: avg={ov['stack_power_avg']}kW max={ov['stack_power_max']}kW",
            f"  SOC: {ov['soc_start']}% -> {ov['soc_end']}%",
            f"  H2: {ov['h2_percent_start']}% -> {ov['h2_percent_end']}%",
        ]

        if road_segs:
            lines.append(f"\n  Road Segments ({len(road_segs)}):")
            for seg in road_segs:
                lines.append(
                    f"    - {seg['road_type']} {seg['start_time']}-{seg['end_time']} "
                    f"Dist={seg['distance_km']}km H2={seg['h2_consumed_kg']}kg "
                    f"({seg['h2_per_100km']}kg/100km) LoadChanges={seg['load_changes']}"
                )

        if anomalies:
            lines.append(f"\n  Anomalies ({len(anomalies)}):")
            for a in anomalies:
                reasons_str = ", ".join(r["factor"] for r in a["reasons"])
                lines.append(
                    f"    - {a['segment_time']} ({a['road_type']}): "
                    f"H2={a['h2_per_100km']}kg/100km (+{a['deviation_pct']}%) "
                    f"Reasons: {reasons_str}"
                )
                lines.append(f"      Suggestion: {a['suggestion']}")

        if behaviors:
            type_counts = {}
            for b in behaviors:
                type_counts[b["type"]] = type_counts.get(b["type"], 0) + 1
            lines.append(f"\n  Driving Behaviors: {type_counts}")

        if factors and factors.get("factors"):
            lines.append(f"\n  Factor Analysis: {factors.get('summary', '')}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning("analyze_real_trip_detail failed: %s", e)
        return f"Real trip detail unavailable: {e}"


def _tool_compute_cost(params: dict) -> str:
    vehicles = get_vehicles()
    kpi = get_kpi()
    avg_price = 34.0  # avg hydrogen price yuan/kg

    lines = ["Fleet Cost Breakdown:\n"]
    total_h2_cost = 0
    for v in vehicles:
        monthly_h2 = v.mileage / 100 * v.hydrogen_consumption
        h2_cost = monthly_h2 * avg_price
        maintenance = v.mileage * 0.8
        labor = 8000  # monthly driver salary
        depreciation = 12000 / 30  # monthly depreciation (300k vehicle / 30 months)
        total = h2_cost + maintenance + labor + depreciation
        total_h2_cost += h2_cost
        lines.append(
            f"  {v.plate}: H2={h2_cost:.0f} Maint={maintenance:.0f} "
            f"Labor={labor} Deprec={depreciation:.0f} Total={total:.0f} yuan/mo"
        )

    grand_total = sum(
        v.mileage / 100 * v.hydrogen_consumption * avg_price
        + v.mileage * 0.8
        + 8000
        + 400
        for v in vehicles
    )
    h2_pct = total_h2_cost / grand_total * 100 if grand_total > 0 else 0
    lines.append(
        f"\n  Fleet Total: {grand_total:.0f} yuan/mo | "
        f"H2 Cost: {total_h2_cost:.0f} yuan ({h2_pct:.1f}%) | "
        f"Avg Cost/100km: {kpi.avg_hydrogen_cost} yuan"
    )
    return "\n".join(lines)


# --- Fuel Cell Health Tool ---


def _tool_analyze_fuelcell_health(params: dict) -> str:
    vehicle_id = params.get("vehicle_id", "V1")
    try:
        from .fuelcell_health import analyze_fuel_cell_health

        report = analyze_fuel_cell_health(vehicle_id)
        lines = [
            f"Fuel Cell Health Report - {vehicle_id}\n",
            f"  Health Score: {report.get('health_score', 'N/A')}/100 ({report.get('health_level_cn', report.get('health_level', '?'))})",
            f"  Voltage: avg={report.get('voltage_analysis', {}).get('stack_a', {}).get('mean', '?')}V "
            f"nominal=380V",
            f"  Thermal: stress_events={report.get('thermal_analysis', {}).get('thermal_stress_events', '?')}",
            f"  Efficiency: {report.get('efficiency_analysis', {}).get('stack_efficiency_pct', '?')}%",
            f"  Degradation: {report.get('degradation_trend', {}).get('interpretation', '?')}",
            f"  RUL: {report.get('rul_estimate', {}).get('remaining_hours', '?')}h",
            "\n  Recommendations:",
        ]
        for rec in report.get("recommendations", []):
            lines.append(f"    - {rec}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("analyze_fuelcell_health failed: %s", e)
        return f"Fuel cell health analysis unavailable: {e}"


# --- Route Planning Tool ---


def _tool_plan_route(params: dict) -> str:
    try:
        from .route_optimizer import plan_route

        vehicle_plate = params.get("vehicle_plate", "")
        dest_lng = float(params.get("dest_lng", 121.47))
        dest_lat = float(params.get("dest_lat", 31.23))
        result = plan_route(vehicle_plate, dest_lng, dest_lat)
        lines = [
            f"Route Plan for {result.get('vehicle', vehicle_plate)}:\n",
            f"  Feasible: {result.get('feasible', '?')}",
            f"  Plan: {result.get('plan', '?')}",
            f"  Current H2: {result.get('current_h2_pct', '?')}%",
            f"  Safe Range: {result.get('safe_range_km', '?')}km",
            f"  Direct Distance: {result.get('direct_distance_km', '?')}km",
        ]
        if result.get("refuel_station"):
            s = result["refuel_station"]
            lines.extend(
                [
                    f"\n  Refuel Stop: {s.get('name', '?')}",
                    f"    Distance: {s.get('distance_km', '?')}km",
                    f"    Queue: {s.get('queue_length', '?')} vehicles",
                    f"    Storage: {s.get('storage_current', '?')}kg / {s.get('storage_capacity', '?')}kg",
                    f"    Price: {s.get('price_per_kg', '?')} yuan/kg",
                ]
            )
        if result.get("estimated_cost_yuan") is not None:
            lines.append(
                f"\n  Total distance: {result.get('total_distance_km', '?')}km"
            )
            lines.append(
                f"  Estimated cost: {result.get('estimated_cost_yuan', '?')} yuan"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("plan_route failed: %s", e)
        return f"Route planning unavailable: {e}"


# --- Station Dispatch Tool ---


def _tool_schedule_station_dispatch(params: dict) -> str:
    try:
        from .route_optimizer import schedule_station_dispatch

        vehicle_plate = params.get("vehicle_plate", "")
        result = schedule_station_dispatch(vehicle_plate)
        rec = result.get("recommendation", {})
        all_stations = result.get("all_stations", [])
        lines = [
            f"Station Dispatch for {vehicle_plate}:\n",
            f"  Stations evaluated: {result.get('stations_evaluated', 0)}",
            "\n  Top recommendation:",
            f"    Station: {rec.get('name', '?')} ({rec.get('station_id', '?')})",
            f"    Distance: {rec.get('distance_km', '?')}km",
            f"    Queue: {rec.get('queue_length', '?')} vehicles | Wait: ~{rec.get('predicted_wait_min', '?')}min",
            f"    H2 available: {rec.get('h2_available_kg', '?')}kg",
            f"    Price: {rec.get('price_per_kg', '?')} yuan/kg",
            f"    Score: {rec.get('score', '?')}",
        ]
        if len(all_stations) > 1:
            lines.append(f"\n  Other stations ({len(all_stations) - 1}):")
            for s in all_stations[1:3]:
                lines.append(
                    f"    - {s.get('name', '?')}: {s.get('distance_km', '?')}km, "
                    f"wait={s.get('predicted_wait_min', '?')}min, "
                    f"price={s.get('price_per_kg', '?')} yuan/kg, "
                    f"score={s.get('score', '?')}"
                )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("schedule_station_dispatch failed: %s", e)
        return f"Station dispatch unavailable: {e}"


# --- Fleet Optimization Tool ---


def _tool_optimize_fleet(params: dict) -> str:
    try:
        from .fleet_optimizer import optimize_fleet_assignment

        max_orders = int(params.get("max_orders", 10))
        result = optimize_fleet_assignment(max_orders=max_orders)
        lines = [
            "Fleet Optimization Report:\n",
            f"  Pending Orders: {result['total_pending_orders']}",
            f"  Available Vehicles: {result['total_available_vehicles']}",
            f"  Assigned: {result['assigned_count']} | Unassigned: {result['unassigned_count']}",
            f"  Fleet Utilization: {result['fleet_utilization_pct']}%",
            f"  Total Revenue: {result['total_revenue_yuan']:.0f} yuan",
            f"  Total Cost: {result['total_cost_yuan']:.0f} yuan",
            f"  Total Profit: {result['total_profit_yuan']:.0f} yuan",
            f"  Avg Match Score: {result['avg_match_score']}",
        ]
        lines.append("\n  Assignments:")
        for a in result["assignments"][:5]:
            lines.append(
                f"    - Order {a['order_id']} -> {a['assigned_vehicle']} "
                f"| Profit: {a['estimated_profit']:.0f} yuan "
                f"| Score: {a['match_score']}"
            )
        if result.get("unassigned"):
            lines.append(f"\n  Unassigned: {len(result['unassigned'])} orders")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("optimize_fleet failed: %s", e)
        return f"Fleet optimization unavailable: {e}"


# Tool registry
TOOLS: dict[str, Callable[..., str]] = {
    "query_vehicle": _tool_query_vehicle,
    "query_vehicles": _tool_query_vehicles,
    "query_stations": _tool_query_stations,
    "query_orders": _tool_query_orders,
    "query_kpi": _tool_query_kpi,
    "query_pool_summary": _tool_query_pool_summary,
    "query_events": _tool_query_events,
    "analyze_real_trips": _tool_analyze_real_trips,
    "analyze_real_trip_detail": _tool_analyze_real_trip_detail,
    "compute_cost": _tool_compute_cost,
    "analyze_fuelcell_health": _tool_analyze_fuelcell_health,
    "plan_route": _tool_plan_route,
    "schedule_station_dispatch": _tool_schedule_station_dispatch,
    "optimize_fleet": _tool_optimize_fleet,
}


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

SCENARIO_CONTEXT = {
    "hydrogen_optimization": (
        "You are the Hydrogen Consumption Optimization Agent for a hydrogen fuel cell truck fleet. "
        "Your job is to analyze vehicle hydrogen consumption anomalies and provide optimization recommendations. "
        "Focus on: per-vehicle consumption vs fleet average, road condition impact, driving behavior, fuel cell health."
    ),
    "route_planning": (
        "You are the Route Planning Agent for a hydrogen fuel cell truck fleet. "
        "Your job is to plan optimal transport routes considering remaining hydrogen, refueling station locations, "
        "and order destinations. Ensure vehicles never run out of hydrogen."
    ),
    "station_dispatch": (
        "You are the Hydrogen Station Dispatch Agent. "
        "Your job is to recommend the best refueling station for vehicles based on queue length, wait time, "
        "hydrogen price, and storage availability. Minimize total waiting time and cost."
    ),
    "cost_analysis": (
        "You are the Cost Analysis Agent for a hydrogen fuel cell truck fleet. "
        "Your job is to analyze the full cost structure (hydrogen, maintenance, labor, depreciation), "
        "identify cost drivers, and recommend cost reduction strategies."
    ),
    "fleet_management": (
        "You are the Fleet Management Agent for a hydrogen fuel cell truck fleet. "
        "Your job is to optimize vehicle-order matching, manage fleet capacity, and maximize utilization. "
        "Consider vehicle status, hydrogen level, range, and order requirements."
    ),
    "fuelcell_health": (
        "You are the Fuel Cell Health Agent for a hydrogen fuel cell truck fleet. "
        "Your job is to analyze fuel cell degradation, voltage/thermal stress, efficiency loss, "
        "and predict remaining useful life (RUL) using real telemetry data. "
        "Provide maintenance recommendations based on health scores."
    ),
}


def _build_tool_doc() -> str:
    lines = []
    for t in TOOL_DESCRIPTIONS:
        lines.append(f"- {t['name']}: {t['desc']}\n  Params: {t['params']}")
    return "\n".join(lines)


def _build_system_prompt(scenario: str) -> str:
    context = SCENARIO_CONTEXT.get(
        scenario,
        "You are an intelligent agent for a hydrogen fuel cell truck fleet operations platform.",
    )
    tool_doc = _build_tool_doc()
    return f"""{context}

You are equipped with the following tools to query real fleet data:

{tool_doc}

## Response Format

You must respond in ONE of two JSON formats:

### Option A - Take an action (Thought + Action)
```json
{{
  "thought": "Your reasoning about what to do next",
  "action": "tool_name",
  "action_input": {{"param": "value"}}
}}
```

### Option B - Give the final answer
```json
{{
  "thought": "Your reasoning for the final answer",
  "final_answer": "Your comprehensive answer to the user's question"
}}
```

## Rules
1. Be efficient. If you already have enough context to answer directly, give the final_answer immediately without tool calls.
2. You can take at most {MAX_ITERATIONS} actions. After gathering enough data, give the final answer.
3. Action names must be one of the tools listed above.
4. action_input must be a JSON object with the required parameters.
5. The final_answer should be detailed, specific, and include data from your observations.
6. All responses must be valid JSON. Do not add text outside the JSON block.
7. Respond in Chinese (the user's language).
8. The "thought" and "final_answer" values MUST be plain strings (用中文自然语言表述), never nested JSON objects or arrays.
9. NEVER call the same tool with the same parameters twice — you already have that data in previous observations. NEVER invent tool names that are not in the list above (e.g., there is NO math/calculation/average tool). All computed values (averages, percentages, max, comparisons) must be calculated by YOURSELF inside the "thought" field, then give the final_answer.
10. You only have {MAX_ITERATIONS} actions in total. Plan ahead: query first, analyze the data you got, then answer. Do not waste actions on redundant queries.
"""


# ---------------------------------------------------------------------------
# Response parser
# ---------------------------------------------------------------------------


def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from the LLM response text."""
    # Try direct parse first
    text = text.strip()
    # Remove markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)

    # Try to find JSON object
    # Find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    json_str = text[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try fixing common issues
        json_str = json_str.replace("'", '"')
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return None


def _coerce_str(value) -> str:
    """LLM 有时会把 thought/final_answer 返回成 dict/list 而非字符串，
    统一转成字符串，避免 ReactStep/ReactResponse 的 Pydantic 校验失败。"""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


# ---------------------------------------------------------------------------
# ReAct Engine
# ---------------------------------------------------------------------------


class ReactEngine:
    """Runs the ReAct reasoning loop with LLM and tools."""

    def __init__(self, req: ReactRequest):
        self.req = req
        self.scenario = req.scenario
        self.query = req.query
        self.context = req.context or {}
        self.steps: list[ReactStep] = []
        self.messages: list[dict[str, str]] = []
        self._init_messages()

    def _init_messages(self):
        system_prompt = _build_system_prompt(self.scenario)
        self.messages.append({"role": "system", "content": system_prompt})

        # Build user message with context
        user_content = f"User question: {self.query}"
        if self.req.vehicle_plate:
            user_content += f"\nTarget vehicle: {self.req.vehicle_plate}"
        if self.context:
            user_content += (
                f"\nAdditional context: {json.dumps(self.context, ensure_ascii=False)}"
            )
        user_content += "\n\nPlease analyze step by step using the available tools."

        self.messages.append({"role": "user", "content": user_content})

    def _call_llm(self) -> str:
        """Call LLM and return the response text."""
        return llm_client.chat(
            self.messages,
            temperature=0.4,
            max_tokens=2048,
        )

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool and return the observation string."""
        func = TOOLS.get(tool_name)
        if func is None:
            return f"Error: Unknown tool '{tool_name}'. Available tools: {list(TOOLS.keys())}"
        try:
            result = func(tool_input or {})
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            logger.error("Tool '%s' execution failed: %s", tool_name, e)
            return f"Error executing tool '{tool_name}': {e}"

    def run(self) -> ReactResponse:
        """Run the full ReAct loop synchronously. Returns ReactResponse."""
        for iteration in range(MAX_ITERATIONS):
            try:
                llm_response = self._call_llm()
            except Exception as e:
                logger.error("LLM call failed at iteration %d: %s", iteration, e)
                # If we have steps, generate a fallback answer from what we have
                if self.steps:
                    fallback = self._generate_fallback_answer()
                    return ReactResponse(
                        steps=self.steps,
                        final_answer=fallback,
                        scenario=self.scenario,
                    )
                raise

            parsed = _extract_json(llm_response)

            if parsed is None:
                # Could not parse, try once more with a clarification
                logger.warning(
                    "Failed to parse LLM response at iteration %d: %s",
                    iteration,
                    llm_response[:200],
                )
                self.messages.append({"role": "assistant", "content": llm_response})
                self.messages.append(
                    {
                        "role": "user",
                        "content": "Your previous response was not valid JSON. Please respond in the required JSON format with thought, action, action_input OR thought, final_answer.",
                    }
                )
                continue

            thought = _coerce_str(parsed.get("thought", ""))

            # Check if this is a final answer
            if "final_answer" in parsed:
                final_answer = _coerce_str(parsed["final_answer"])
                # Record the last thought as a step if we haven't recorded it
                if thought and not any(s.thought == thought for s in self.steps):
                    self.steps.append(
                        ReactStep(
                            thought=thought,
                            action="generate_final_answer()",
                            observation=final_answer[:200] + "..."
                            if len(final_answer) > 200
                            else final_answer,
                        )
                    )
                return ReactResponse(
                    steps=self.steps,
                    final_answer=final_answer,
                    scenario=self.scenario,
                )

            # This is an action step
            action = parsed.get("action", "")
            action_input = parsed.get("action_input", {})

            if not action:
                logger.warning("No action in parsed response: %s", parsed)
                continue

            # Execute the tool
            observation = self._execute_tool(
                action, action_input if isinstance(action_input, dict) else {}
            )

            # Record the step
            step = ReactStep(
                thought=thought,
                action=f"{action}({json.dumps(action_input, ensure_ascii=False)})"
                if action_input
                else f"{action}()",
                observation=observation,
            )
            self.steps.append(step)

            # Feed the observation back to the LLM
            self.messages.append({"role": "assistant", "content": llm_response})
            self.messages.append(
                {
                    "role": "user",
                    "content": f"Observation: {observation}\n\nYou have {MAX_ITERATIONS - iteration - 1} action(s) left. Do NOT repeat any previous tool call — that data is already above. Either call a DIFFERENT tool for genuinely missing information, or directly provide the final_answer now (compute averages/percentages/comparisons yourself from the observations).",
                }
            )

        # Max iterations reached
        fallback = self._generate_fallback_answer()
        return ReactResponse(
            steps=self.steps,
            final_answer=fallback,
            scenario=self.scenario,
        )

    def run_stream(self) -> Generator[dict, None, None]:
        """Run the ReAct loop, yielding SSE events as dicts.

        Yields:
          {"type": "step", "index": N, "thought": ..., "action": ..., "observation": ...}
          {"type": "final", "answer": ..., "scenario": ...}
        """
        for iteration in range(MAX_ITERATIONS):
            try:
                llm_response = self._call_llm()
            except Exception as e:
                logger.error("LLM stream call failed at iteration %d: %s", iteration, e)
                if self.steps:
                    fallback = self._generate_fallback_answer()
                    for i, step in enumerate(self.steps):
                        yield {
                            "type": "step",
                            "index": i,
                            "thought": step.thought,
                            "action": step.action,
                            "observation": step.observation,
                        }
                    yield {
                        "type": "final",
                        "answer": fallback,
                        "scenario": self.scenario,
                    }
                    return
                raise

            parsed = _extract_json(llm_response)

            if parsed is None:
                self.messages.append({"role": "assistant", "content": llm_response})
                self.messages.append(
                    {
                        "role": "user",
                        "content": "Your previous response was not valid JSON. Please respond in the required JSON format.",
                    }
                )
                continue

            thought = _coerce_str(parsed.get("thought", ""))

            if "final_answer" in parsed:
                final_answer = _coerce_str(parsed["final_answer"])
                if thought and not any(s.thought == thought for s in self.steps):
                    step = ReactStep(
                        thought=thought,
                        action="generate_final_answer()",
                        observation=final_answer[:200] + "..."
                        if len(final_answer) > 200
                        else final_answer,
                    )
                    self.steps.append(step)
                    yield {
                        "type": "step",
                        "index": len(self.steps) - 1,
                        "thought": step.thought,
                        "action": step.action,
                        "observation": step.observation,
                    }
                yield {
                    "type": "final",
                    "answer": final_answer,
                    "scenario": self.scenario,
                }
                return

            action = parsed.get("action", "")
            action_input = parsed.get("action_input", {})

            if not action:
                continue

            observation = self._execute_tool(
                action, action_input if isinstance(action_input, dict) else {}
            )

            step = ReactStep(
                thought=thought,
                action=f"{action}({json.dumps(action_input, ensure_ascii=False)})"
                if action_input
                else f"{action}()",
                observation=observation,
            )
            self.steps.append(step)

            yield {
                "type": "step",
                "index": len(self.steps) - 1,
                "thought": step.thought,
                "action": step.action,
                "observation": step.observation,
            }

            self.messages.append({"role": "assistant", "content": llm_response})
            self.messages.append(
                {
                    "role": "user",
                    "content": f"Observation: {observation}\n\nYou have {MAX_ITERATIONS - iteration - 1} action(s) left. Do NOT repeat any previous tool call — that data is already above. Either call a DIFFERENT tool for genuinely missing information, or directly provide the final_answer now (compute averages/percentages/comparisons yourself from the observations).",
                }
            )

        # Max iterations
        fallback = self._generate_fallback_answer()
        yield {"type": "final", "answer": fallback, "scenario": self.scenario}

    def _generate_fallback_answer(self) -> str:
        """Generate a fallback answer from collected observations."""
        if not self.steps:
            return "Unable to complete analysis due to insufficient data. Please try again."

        parts = ["Based on the data collected:\n"]
        for i, step in enumerate(self.steps, 1):
            parts.append(f"{i}. {step.thought}")
            parts.append(f"   Observation: {step.observation[:300]}")
        parts.append("\nPlease refer to the above data for detailed analysis.")
        return "\n".join(parts)
