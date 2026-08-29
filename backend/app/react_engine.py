"""H2Brain - ReAct Reasoning Engine

Implements the Thought -> Action -> Observation loop powered by LLM.
Tools query real telemetry data from data_processor (V1/V2 真实测试车辆);
加氢站/订单/事件为调度推演沙盘数据（输出中均明确标注）。所有工具输出为中文。

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
    get_stations,
    get_orders,
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
        "desc": "查询单辆真实测试车辆的运营概况（数据来源：T05 官方数据包遥测）。返回行程数、总里程、总氢耗、平均百公里氢耗等。",
        "params": "vehicle_id (str): 车辆编号，'V1' 或 'V2'",
    },
    {
        "name": "query_vehicles",
        "desc": "查询全部真实测试车辆列表。返回每辆车的数据期、行程数、总里程、总氢耗、平均百公里氢耗。",
        "params": "无",
    },
    {
        "name": "query_stations",
        "desc": "查询加氢站列表（调度推演沙盘数据）。返回站名、位置、储氢量、排队长度、等待时间、氢价。",
        "params": "无",
    },
    {
        "name": "query_orders",
        "desc": "查询运输订单（调度推演沙盘数据）。返回订单号、货物类型、起讫点、距离、所需氢量、运费、状态。",
        "params": "无",
    },
    {
        "name": "query_kpi",
        "desc": "查询车队级 KPI（真实遥测口径）：车辆数、遥测行数、行程总数、总里程、加权平均百公里氢耗、对标柴油碳减排。",
        "params": "无",
    },
    {
        "name": "query_pool_summary",
        "desc": "查询车队运力池汇总（调度推演沙盘数据）：总数、在线、运输中、加氢中、低氢量、离线。",
        "params": "无",
    },
    {
        "name": "query_events",
        "desc": "查询最近实时事件流（调度推演沙盘数据）：派单、加氢、告警、优化、完成。",
        "params": "无",
    },
    {
        "name": "analyze_real_trips",
        "desc": "查询某辆车的真实遥测行程列表。返回每个行程的日期、里程、时长、均速、氢耗、百公里氢耗、电堆功率。",
        "params": "vehicle_id (str): 'V1' 或 'V2'",
    },
    {
        "name": "analyze_real_trip_detail",
        "desc": "查询某个真实行程的详细分析：工况分段（多维证据矩阵分类）、氢耗异常段、驾驶行为、影响因素归因。",
        "params": "vehicle_id (str): 'V1' 或 'V2'; trip_id (int): 行程编号",
    },
    {
        "name": "compute_cost",
        "desc": "计算车队成本拆解（基于真实遥测）：氢燃料成本、维护成本、对标柴油重卡的成本节省，含公式与参数说明。",
        "params": "无",
    },
    {
        "name": "analyze_fuelcell_health",
        "desc": "基于真实遥测分析燃料电池健康：电压分析、热应力、效率、衰减趋势、健康评分（0-100）、RUL 寿命预测（含 LSTM 升级方案说明）、维护建议。",
        "params": "vehicle_id (str): 'V1' 或 'V2'",
    },
    {
        "name": "plan_route",
        "desc": "为车辆规划到目的地的最优路线（调度沙盘推演）。检查氢量续航充足性，必要时推荐途中加氢站，预估行程成本。",
        "params": "vehicle_plate (str): 车牌号; dest_lng (float): 目标经度; dest_lat (float): 目标纬度",
    },
    {
        "name": "generate_report_image",
        "desc": "为运营周报生成一张配图：基于车队真实 KPI（里程/氢耗/成本节省/碳减排）自动构建提示词并调用商汤图像模型出图，返回配图链接与提示词说明。",
        "params": "theme (str, 可选): 配图主题侧重，如 '碳减排'、'安全运营'；不传则为运营周报总览",
    },
    {
        "name": "schedule_station_dispatch",
        "desc": "为车辆推荐最优加氢站（调度沙盘推演）：基于距离、排队长度（M/M/c Erlang C 等待时间预测）、储氢量与氢价综合评分，返回排序站点列表。",
        "params": "vehicle_plate (str): 车牌号",
    },
    {
        "name": "optimize_fleet",
        "desc": "订单-车辆智能匹配优化（调度沙盘推演）：多目标评分（氢量充足度、就近性、效用、成本、负载均衡），返回分配方案与利润预估。",
        "params": "max_orders (int): 最多分配订单数，默认 10",
    },
]


def _real_vehicle_summary(vid: str) -> str | None:
    """从 data_processor 取真实车辆摘要 (中文)。"""
    try:
        from .data_processor import get_processor

        proc = get_processor()
        proc._ensure_loaded()
        for v in proc.get_vehicles():
            if v["vehicle_id"] == vid:
                return (
                    f"车辆{vid}（{v['label']}，运营区域：{v['region']}）｜"
                    f"数据期 {v['date_range']} 共 {v['total_rows']} 行遥测｜"
                    f"行程 {v['total_trips']} 个｜总里程 {v['total_distance_km']:.0f}km｜"
                    f"总氢耗 {v['total_h2_consumed_kg']:.1f}kg｜"
                    f"平均百公里氢耗 {v['avg_h2_per_100km']:.2f}kg"
                )
    except Exception as e:
        logger.warning("real vehicle summary failed: %s", e)
    return None


def _tool_query_vehicle(params: dict) -> str:
    vid = params.get("vehicle_id") or params.get("plate", "")
    # 真实数据: V1 / V2 (1# / 2#)
    for cand, real_vid in (("V1", "V1"), ("V2", "V2"), ("1#", "V1"), ("2#", "V2"),
                           ("车辆1#", "V1"), ("车辆2#", "V2"), ("测试车辆1#", "V1"), ("测试车辆2#", "V2")):
        if cand.lower() in str(vid).lower():
            summary = _real_vehicle_summary(real_vid)
            if summary:
                return summary

    # 兜底: 列出真实车辆
    out = ["真实测试车辆共 2 辆（数据来源：T05 官方数据包遥测）：\n"]
    for v in ("V1", "V2"):
        s = _real_vehicle_summary(v)
        if s:
            out.append(f"- {s}")
    out.append(
        "\n提示：请用 vehicle_id='V1'（测试车辆1#，湖北襄阳）或 'V2'（测试车辆2#，新疆吐鲁番）查询。"
    )
    return "\n".join(out)


def _tool_query_vehicles(params: dict) -> str:
    lines = ["真实测试车队共 2 辆（数据来源：T05 官方数据包，63.4 万行遥测）：\n"]
    for v in ("V1", "V2"):
        s = _real_vehicle_summary(v)
        if s:
            lines.append(f"- {s}")
    return "\n".join(lines)


def _tool_query_stations(params: dict) -> str:
    stations = get_stations()
    lines = ["加氢站列表（调度推演沙盘数据，用于调度算法演示）：\n"]
    for s in stations:
        lines.append(
            f"- {s.station_id} {s.name} [状态:{s.status}] "
            f"储氢={s.current_storage}/{s.storage_capacity}kg "
            f"排队={s.queue_length}车 预计等待={s.avg_wait_time}min "
            f"氢价={s.price_per_kg}元/kg "
            f"压力={s.hydrogen_pressure}MPa "
            f"位置=({s.lng:.4f}, {s.lat:.4f})"
        )
    lines.append("\n注：以上为调度沙盘推演数据（无真实加氢站运营数据接入），仅用于调度算法演示。")
    return "\n".join(lines)


def _tool_query_orders(params: dict) -> str:
    orders = get_orders()
    status_cn = {
        "pending": "待派单",
        "assigned": "已派单",
        "in_transit": "运输中",
        "completed": "已完成",
        "cancelled": "已取消",
    }
    lines = ["运输订单列表（调度推演沙盘数据）：\n"]
    for o in orders:
        st = status_cn.get(o.status.value, o.status.value)
        lines.append(
            f"- 订单{o.order_id} [{st}] "
            f"{o.origin} → {o.destination} "
            f"货物={o.cargo_type} 距离={o.distance}km "
            f"预计耗氢={o.hydrogen_needed}kg 运费={o.fee}元 "
            f"指派车辆={o.vehicle_plate}"
        )
    lines.append("\n注：以上为调度沙盘订单（演示用），真实车辆运营分析请查询 V1/V2 行程数据。")
    return "\n".join(lines)


def _tool_query_kpi(params: dict) -> str:
    """运营 KPI — 以真实遥测数据为主口径，杜绝虚构车队规模。"""
    lines = ["运营 KPI（数据来源：T05 官方数据包真实遥测）：\n"]
    try:
        from .data_processor import get_processor

        processor = get_processor()
        processor._ensure_loaded()
        vehicles = processor.get_vehicles()
        total_km = sum(v["total_distance_km"] for v in vehicles)
        total_h2 = sum(v["total_h2_consumed_kg"] for v in vehicles)
        total_trips = sum(v["total_trips"] for v in vehicles)
        total_rows = sum(v["total_rows"] for v in vehicles)
        avg_h2 = total_h2 / total_km * 100 if total_km > 0 else 0
        # 柴油对标碳减排口径: 30L/100km × 2.63kg CO2/L
        co2 = total_km / 100 * 30.0 * 2.63
        lines += [
            f"  车辆数：{len(vehicles)} 辆（V1 湖北襄阳 / V2 新疆吐鲁番）",
            f"  遥测数据：{total_rows} 行，数据期 2026-08-01 ~ 08-18",
            f"  行程总数：{total_trips} 个 | 总里程：{total_km:.0f}km | 总氢耗：{total_h2:.1f}kg",
            f"  加权平均百公里氢耗：{avg_h2:.2f}kg（计算：总氢耗÷总里程×100）",
            f"  氢燃料成本：{total_h2 * 35:.0f} 元（按 35 元/kg）",
            f"  对标柴油碳减排：{co2:.0f} kg CO2（计算：里程÷100×30L/100km×2.63kg/L，绿氢按 0 排放计）",
        ]
        for v in vehicles:
            lines.append(
                f"  - {v['vehicle_id']}（{v['label']}，{v['region']}）："
                f"{v['total_trips']} 行程，{v['total_distance_km']:.0f}km，"
                f"{v['total_h2_consumed_kg']:.1f}kg，{v['avg_h2_per_100km']:.2f}kg/100km"
            )
    except Exception as e:
        lines.append(f"  真实数据暂不可用：{e}")
    lines.append(
        "\n注：平台没有虚构车队规模数据；加氢站/订单为调度沙盘演示，需另行调用对应工具查询。"
    )
    return "\n".join(lines)


def _tool_query_pool_summary(params: dict) -> str:
    p = get_pool_summary()
    return (
        f"车队运力池汇总（调度推演沙盘数据，非真实车队）：\n"
        f"  总数：{p.total} | 在线：{p.online} | 运输中：{p.in_transit}\n"
        f"  加氢中：{p.refueling} | 低氢量：{p.low_hydrogen} | 离线：{p.offline}\n"
        f"  车队数：{p.fleets}\n"
        f"注：真实测试车辆仅 V1/V2 两辆，请以 query_kpi / query_vehicles 的真实口径为准。"
    )


def _tool_query_events(params: dict) -> str:
    events = get_events()
    level_cn = {"info": "信息", "warning": "警告", "critical": "严重", "success": "成功"}
    lines = [f"最近 {len(events)} 条事件（调度沙盘事件流）：\n"]
    for e in events[:10]:
        lv = level_cn.get(e.level.value, e.level.value)
        lines.append(
            f"- [{lv}] {e.title}：{e.detail}（车辆：{e.vehicle_plate or '无'}）@ {e.timestamp}"
        )
    lines.append("\n注：以上为调度推演沙盘事件；真实驾驶行为事件请查看行程分析工具。")
    return "\n".join(lines)


def _tool_analyze_real_trips(params: dict) -> str:
    vehicle_id = params.get("vehicle_id", "V1")
    try:
        from .data_processor import get_processor

        processor = get_processor()
        trips = processor.get_trips(vehicle_id)
        if not trips:
            return f"车辆 {vehicle_id} 暂无行程数据"
        lines = [f"车辆 {vehicle_id} 行程列表（真实遥测，共 {len(trips)} 个行程）：\n"]
        for t in trips:
            lines.append(
                f"- 行程 {t['trip_id']} [{t['date']} {t['start_time']}-{t['end_time']}] "
                f"里程={t['distance_km']}km 时长={t['duration_h']}h "
                f"均速={t['avg_speed']}km/h "
                f"氢耗={t['h2_consumed_kg']}kg（{t['h2_per_100km']}kg/100km） "
                f"电堆功率={t['stack_power_avg']}kW"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("analyze_real_trips failed: %s", e)
        return f"真实数据分析暂不可用：{e}"


def _tool_analyze_real_trip_detail(params: dict) -> str:
    vehicle_id = params.get("vehicle_id", "V1")
    trip_id = params.get("trip_id", 0)
    try:
        from .data_processor import get_processor

        processor = get_processor()
        detail = processor.get_trip_detail(vehicle_id, int(trip_id))
        if detail is None:
            return f"车辆 {vehicle_id} 未找到行程 {trip_id}"

        ov = detail["overview"]
        anomalies = detail.get("anomalies", [])
        behaviors = detail.get("driving_behaviors", [])
        factors = detail.get("factor_analysis", {})
        road_segs = detail.get("road_segments", [])

        lines = [
            f"行程 {trip_id}（车辆 {vehicle_id}）详情：\n",
            f"  里程：{ov['distance_km']}km | 时长：{ov['duration_h']}h | 均速：{ov['avg_speed']}km/h",
            f"  氢耗：{ov['h2_consumed_kg']}kg | 百公里氢耗：{ov['h2_per_100km']}kg",
            f"  电堆功率：均值={ov['stack_power_avg']}kW 峰值={ov['stack_power_max']}kW",
            f"  动力电池SOC：{ov['soc_start']}% -> {ov['soc_end']}%",
            f"  氢量：{ov['h2_percent_start']}% -> {ov['h2_percent_end']}%",
        ]

        if road_segs:
            lines.append(f"\n  工况分段（{len(road_segs)} 段，多维证据矩阵分类）：")
            for seg in road_segs:
                lines.append(
                    f"    - {seg['road_type']} {seg['start_time']}-{seg['end_time']} "
                    f"里程={seg['distance_km']}km 氢耗={seg['h2_consumed_kg']}kg "
                    f"（{seg['h2_per_100km']}kg/100km）载荷变化={seg['load_changes']}次"
                )

        if anomalies:
            lines.append(f"\n  氢耗异常段（{len(anomalies)} 个，判定方法：分段百公里氢耗偏离均值超阈值）：")
            for a in anomalies:
                reasons_str = "、".join(r["factor"] for r in a["reasons"])
                lines.append(
                    f"    - {a['segment_time']}（{a['road_type']}）："
                    f"氢耗={a['h2_per_100km']}kg/100km（偏高 {a['deviation_pct']}%）"
                    f"成因：{reasons_str}"
                )
                lines.append(f"      建议：{a['suggestion']}")

        if behaviors:
            type_counts = {}
            for b in behaviors:
                type_counts[b["type"]] = type_counts.get(b["type"], 0) + 1
            lines.append(f"\n  驾驶行为统计：{type_counts}")

        if factors and factors.get("factors"):
            lines.append(f"\n  影响因素分析：{factors.get('summary', '')}")

        return "\n".join(lines)
    except Exception as e:
        logger.warning("analyze_real_trip_detail failed: %s", e)
        return f"行程详情暂不可用：{e}"


def _tool_compute_cost(params: dict) -> str:
    """成本分析 — 基于真实遥测计算，并写明公式与参数来源。"""
    H2_PRICE = 35.0  # 元/kg（行业均价参数）
    DIESEL_PRICE = 7.5  # 元/L
    DIESEL_L_PER_100 = 30.0  # 49吨柴油重卡对标油耗
    H2_MAINT_PER_KM = 0.35  # 元/km
    DIESEL_MAINT_PER_KM = 0.55  # 元/km

    lines = [
        "车队成本分析（基于 T05 官方数据包真实遥测，公式与参数如下）：\n",
        "  计算方法：",
        "    氢燃料成本 = 总氢耗 × 35 元/kg",
        "    柴油对标燃料成本 = 总里程÷100 × 30 L/100km × 7.5 元/L",
        "    维护成本 = 里程 × 单价（氢 0.35 元/km，柴油 0.55 元/km）",
        "    成本节省 = (柴油燃料+柴油维护) - (氢燃料+氢维护)\n",
    ]
    try:
        from .data_processor import get_processor

        proc = get_processor()
        proc._ensure_loaded()
        vehicles = proc.get_vehicles()
        total_km = sum(v["total_distance_km"] for v in vehicles)
        total_h2 = sum(v["total_h2_consumed_kg"] for v in vehicles)
    except Exception as e:
        return f"真实数据暂不可用，无法计算成本：{e}"

    h2_cost = total_h2 * H2_PRICE
    h2_maint = total_km * H2_MAINT_PER_KM
    diesel_cost = total_km / 100 * DIESEL_L_PER_100 * DIESEL_PRICE
    diesel_maint = total_km * DIESEL_MAINT_PER_KM
    saved = (diesel_cost + diesel_maint) - (h2_cost + h2_maint)

    lines += [
        f"  实测数据：{len(vehicles)} 辆车，总里程 {total_km:.0f}km，总氢耗 {total_h2:.1f}kg（18 天数据期）",
        f"  氢燃料成本：{total_h2:.1f}kg × 35 = {h2_cost:.0f} 元",
        f"  氢维护成本：{total_km:.0f}km × 0.35 = {h2_maint:.0f} 元",
        f"  柴油对标燃料：{total_km:.0f}÷100×30×7.5 = {diesel_cost:.0f} 元",
        f"  柴油对标维护：{total_km:.0f}km × 0.55 = {diesel_maint:.0f} 元",
        f"  对标柴油成本节省：({diesel_cost:.0f}+{diesel_maint:.0f}) - ({h2_cost:.0f}+{h2_maint:.0f}) = {saved:.0f} 元",
        f"  氢重卡百公里成本：{total_h2 / total_km * 100 * H2_PRICE + H2_MAINT_PER_KM * 100:.0f} 元/100km",
        f"  柴油重卡百公里成本：{DIESEL_L_PER_100 * DIESEL_PRICE + DIESEL_MAINT_PER_KM * 100:.0f} 元/100km",
        "\n  分车型成本明细：",
    ]
    for v in vehicles:
        v_km = v["total_distance_km"]
        v_h2 = v["total_h2_consumed_kg"]
        lines.append(
            f"    - {v['vehicle_id']}（{v['label']}）：里程 {v_km:.0f}km | 氢耗 {v_h2:.1f}kg | "
            f"氢燃料成本 {v_h2 * H2_PRICE:.0f} 元 | 百公里氢成本 {v_h2 / v_km * 100 * H2_PRICE:.0f} 元"
        )
    lines.append(
        "\n  参数说明：35 元/kg 氢价、7.5 元/L 柴油价、30 L/100km 与维护单价均为行业公开均值参数；"
        "里程与氢耗为官方数据包真实实测值。完整年度推演与投资回收期见「价值量化分析」页。"
    )
    return "\n".join(lines)


# --- Fuel Cell Health Tool ---


def _tool_analyze_fuelcell_health(params: dict) -> str:
    vehicle_id = params.get("vehicle_id", "V1")
    try:
        from .fuelcell_health import analyze_fuel_cell_health

        report = analyze_fuel_cell_health(vehicle_id)
        rul = report.get("remaining_useful_life", {})
        lines = [
            f"燃料电池健康报告 - 车辆 {vehicle_id}：\n",
            f"  健康评分：{report.get('health_score', 'N/A')}/100（{report.get('health_level_cn', report.get('health_level', '?'))}）",
            f"  电压分析：均值={report.get('voltage_analysis', {}).get('stack_a', {}).get('mean', '?')}V（额定 380V）",
            f"  热应力：高温应力事件={report.get('thermal_analysis', {}).get('thermal_stress_events', '?')} 次",
            f"  电堆效率：{report.get('efficiency_analysis', {}).get('stack_efficiency_pct', '?')}%",
            f"  衰减趋势：{report.get('degradation_trend', {}).get('interpretation', '?')}",
            f"  剩余寿命（RUL）预测：剩余约 {rul.get('estimated_remaining_trips') or '数据不足'} 个行程"
            f"（方法：{rul.get('estimation_method', '?')}）",
        ]
        for rec in report.get("recommendations", []):
            lines.append(f"    - {rec}")

        # LSTM RUL 升级方案（技术路线说明）
        lstm_plan = rul.get("lstm_upgrade_plan")
        if lstm_plan:
            lines.append("\n  【RUL 预测 LSTM 升级方案】")
            for k, v in lstm_plan.items():
                lines.append(f"    ▸ {k}：{v}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("analyze_fuelcell_health failed: %s", e)
        return f"燃料电池健康分析暂不可用：{e}"


# --- Route Planning Tool ---


def _tool_plan_route(params: dict) -> str:
    try:
        from .route_optimizer import plan_route

        vehicle_plate = params.get("vehicle_plate", "")
        dest_lng = float(params.get("dest_lng", 121.47))
        dest_lat = float(params.get("dest_lat", 31.23))
        result = plan_route(vehicle_plate, dest_lng, dest_lat)
        lines = [
            f"路径规划结果 - 车辆 {result.get('vehicle', vehicle_plate)}（调度沙盘推演）：\n",
            f"  可行性：{'可行' if result.get('feasible') else '不可行'}",
            f"  规划结论：{result.get('plan', '?')}",
            f"  当前氢量：{result.get('current_h2_pct', '?')}%",
            f"  安全续航：{result.get('safe_range_km', '?')}km",
            f"  直线距离：{result.get('direct_distance_km', '?')}km",
        ]
        if result.get("refuel_station"):
            s = result["refuel_station"]
            lines.extend(
                [
                    f"\n  推荐加氢站：{s.get('name', '?')}",
                    f"    距离：{s.get('distance_km', '?')}km",
                    f"    排队：{s.get('queue_length', '?')} 车",
                    f"    储氢：{s.get('storage_current', '?')}kg / {s.get('storage_capacity', '?')}kg",
                    f"    氢价：{s.get('price_per_kg', '?')} 元/kg",
                ]
            )
        if result.get("estimated_cost_yuan") is not None:
            lines.append(
                f"\n  总行驶距离：{result.get('total_distance_km', '?')}km"
            )
            lines.append(
                f"  预估成本：{result.get('estimated_cost_yuan', '?')} 元"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("plan_route failed: %s", e)
        return f"路径规划暂不可用：{e}"


# --- Station Dispatch Tool ---


def _tool_schedule_station_dispatch(params: dict) -> str:
    try:
        from .route_optimizer import schedule_station_dispatch

        vehicle_plate = params.get("vehicle_plate", "")
        result = schedule_station_dispatch(vehicle_plate)
        rec = result.get("recommendation", {})
        all_stations = result.get("all_stations", [])
        lines = [
            f"加氢站调度推荐 - 车辆 {vehicle_plate}（调度沙盘推演）：\n",
            f"  评估站点数：{result.get('stations_evaluated', 0)}",
            "\n  首选推荐：",
            f"    站点：{rec.get('name', '?')}（{rec.get('station_id', '?')}）",
            f"    距离：{rec.get('distance_km', '?')}km",
            f"    排队：{rec.get('queue_length', '?')} 车 | 预计等待：约 {rec.get('predicted_wait_min', '?')} 分钟",
            f"    可加氢量：{rec.get('h2_available_kg', '?')}kg",
            f"    氢价：{rec.get('price_per_kg', '?')} 元/kg",
            f"    综合评分：{rec.get('score', '?')}",
        ]
        if len(all_stations) > 1:
            lines.append(f"\n  其他备选站点（{len(all_stations) - 1} 个）：")
            for s in all_stations[1:3]:
                lines.append(
                    f"    - {s.get('name', '?')}：{s.get('distance_km', '?')}km，"
                    f"等待={s.get('predicted_wait_min', '?')} 分钟，"
                    f"氢价={s.get('price_per_kg', '?')} 元/kg，"
                    f"评分={s.get('score', '?')}"
                )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("schedule_station_dispatch failed: %s", e)
        return f"加氢站调度暂不可用：{e}"


# --- Fleet Optimization Tool ---


def _tool_optimize_fleet(params: dict) -> str:
    try:
        from .fleet_optimizer import optimize_fleet_assignment

        max_orders = int(params.get("max_orders", 10))
        result = optimize_fleet_assignment(max_orders=max_orders)
        lines = [
            "车队运力优化报告（调度沙盘推演，多目标评分：氢量充足度/距离/效用/成本/负载均衡）：\n",
            f"  待分配订单：{result['total_pending_orders']} 个",
            f"  可用车辆：{result['total_available_vehicles']} 辆",
            f"  已分配：{result['assigned_count']} | 未分配：{result['unassigned_count']}",
            f"  车队利用率：{result['fleet_utilization_pct']}%",
            f"  总营收：{result['total_revenue_yuan']:.0f} 元",
            f"  总成本：{result['total_cost_yuan']:.0f} 元",
            f"  总利润：{result['total_profit_yuan']:.0f} 元",
            f"  平均匹配评分：{result['avg_match_score']}",
        ]
        lines.append("\n  分配明细：")
        for a in result["assignments"][:5]:
            lines.append(
                f"    - 订单 {a['order_id']} → {a['assigned_vehicle']} "
                f"| 预估利润：{a['estimated_profit']:.0f} 元 "
                f"| 评分：{a['match_score']}"
            )
        if result.get("unassigned"):
            lines.append(f"\n  未分配订单：{len(result['unassigned'])} 个")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("optimize_fleet failed: %s", e)
        return f"车队优化暂不可用：{e}"


# ---------------------------------------------------------------------------
# 周报配图生成（商汤图像模型 + 真实 KPI 提示词）
# ---------------------------------------------------------------------------


def _tool_generate_report_image(params: dict) -> str:
    theme = str(params.get("theme") or "").strip()
    try:
        from .report_image import generate_report_image

        info = generate_report_image(theme)
        return (
            "运营周报配图已生成。\n"
            f"主题：{info['theme']}\n"
            f"配图链接：{info['image_url']}\n"
            f"提示词（可解释依据）：{info['prompt']}\n"
            f"配图对应的真实 KPI：{info['kpi_summary']}\n"
            "请在最终结论中附上配图链接，供用户查看。"
        )
    except RuntimeError as e:
        return f"配图暂不可用：{e}"
    except Exception as e:  # noqa: BLE001
        logger.warning("generate_report_image failed: %s", e)
        return f"配图生成失败：{e}"


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
    "generate_report_image": _tool_generate_report_image,
    "schedule_station_dispatch": _tool_schedule_station_dispatch,
    "optimize_fleet": _tool_optimize_fleet,
}


# ---------------------------------------------------------------------------
# System prompt builder
# ---------------------------------------------------------------------------

SCENARIO_CONTEXT = {
    "hydrogen_optimization": (
        "你是氢能燃料电池重卡车队的「氢耗优化智能体」。"
        "你的职责：分析车辆氢耗异常并给出可解释的优化建议。"
        "分析维度：单车百公里氢耗与车队均值对比、工况（路况分类）影响、驾驶行为、燃料电池健康度。"
        "所有定量结论必须写明计算方法（如 百公里氢耗=总氢耗÷总里程×100）。"
    ),
    "route_planning": (
        "你是氢能重卡车队的「路径规划智能体」（调度沙盘推演）。"
        "你的职责：结合剩余氢量、加氢站分布与订单目的地规划安全经济的运输路线，确保车辆不因缺氢停驶。"
        "结论中需说明续航测算依据（安全续航=剩余可用氢量÷百公里氢耗×100×安全系数）。"
    ),
    "station_dispatch": (
        "你是「加氢站调度智能体」（调度沙盘推演）。"
        "你的职责：基于排队长度（Erlang C 模型预测等待时间）、氢价与储氢量，为车辆推荐最优加氢站，"
        "使总等待时间与加氢成本最小。结论中需说明综合评分的构成。"
    ),
    "cost_analysis": (
        "你是氢能重卡车队的「成本分析智能体」。"
        "你的职责：基于真实遥测数据拆解成本结构（氢燃料、维护），对标同级柴油重卡计算成本节省，"
        "并识别成本驱动因素、给出降本建议。"
        "所有成本数字必须展示公式与参数（如 氢燃料成本=总氢耗×氢价），参数需标注来源（真实实测/行业均价参数）。"
    ),
    "fleet_management": (
        "你是氢能重卡车队的「车队管理智能体」（调度沙盘推演）。"
        "你的职责：优化订单-车辆匹配、管理车队运力、最大化利用率。"
        "决策依据：车辆状态、氢量、续航与订单需求，评分维度为氢量充足度/就近性/效用/成本/负载均衡。"
    ),
    "fuelcell_health": (
        "你是氢能重卡车队的「燃料电池健康智能体」。"
        "你的职责：基于真实遥测数据分析电堆衰减、电压偏差、热应力与效率损失，"
        "预测剩余使用寿命（RUL，当前为线性外推基线，已设计 LSTM 升级方案）并依据健康评分给出维护建议。"
    ),
}


def _build_tool_doc() -> str:
    lines = []
    for t in TOOL_DESCRIPTIONS:
        lines.append(f"- {t['name']}: {t['desc']}\n  参数: {t['params']}")
    return "\n".join(lines)


def _build_system_prompt(scenario: str) -> str:
    context = SCENARIO_CONTEXT.get(
        scenario,
        "你是氢能燃料电池重卡运营平台的智能助手。",
    )
    tool_doc = _build_tool_doc()
    return f"""{context}

你可以调用以下工具查询车队数据（真实遥测工具返回 T05 官方数据包实测值，沙盘工具在返回中已标注）：

{tool_doc}

## 响应格式

你必须且只能以下列两种 JSON 格式之一回复：

### 方式 A - 执行行动（思考 + 行动）
```json
{{
  "thought": "你对该步骤的推理分析",
  "action": "tool_name",
  "action_input": {{"param": "value"}}
}}
```

### 方式 B - 给出最终结论
```json
{{
  "thought": "你得出最终结论的推理过程",
  "final_answer": "对用户问题的完整回答"
}}
```

## 规则
1. 高效行动：如果已有足够信息可直接回答，立即给出 final_answer，不必调用工具。
2. 你最多只能执行 {MAX_ITERATIONS} 次行动，收集到足够数据后必须给出最终结论。
3. action 名称必须使用上面列出的工具，不得虚构。
4. action_input 必须是包含所需参数的 JSON 对象。
5. final_answer 必须详细、具体，引用观察结果中的真实数据；涉及定量结论时写明计算公式与参数来源。
6. 整个回复必须是合法 JSON，JSON 块之外不得添加任何文字。
7. 全程使用中文回复（thought 与 final_answer 均为中文）。
8. "thought" 和 "final_answer" 的值必须是字符串（绝不能是嵌套的 JSON 对象或数组）。final_answer 内部可使用 Markdown 富文本格式：### 小标题、**关键数字加粗**、- 要点列表；当结论涉及多车/多指标数值对比时，优先用 Markdown 表格（| 列 | 列 |）呈现，每列含表头分隔行。
9. 当结论适合可视化（趋势对比、占比构成、排行）时，可在 final_answer 末尾附一个 ECharts 图表代码块，格式如下（option 必须是合法 JSON：双引号、无注释、无尾逗号，配色用暗色主题色 #69F0AE/#00E5FF/#FF7043）：
```echarts
{{"title": {{"text": "图表标题", "textStyle": {{"color": "#69F0AE"}}}}, "tooltip": {{}}, "xAxis": {{"type": "category", "data": ["标签1", "标签2"], "axisLabel": {{"color": "#E0F5E8"}}}}, "yAxis": {{"type": "value", "axisLabel": {{"color": "#E0F5E8"}}}}, "series": [{{"type": "bar", "data": [1, 2], "itemStyle": {{"color": "#00E5FF"}}}}]}}
```
10. 严禁用相同参数重复调用同一工具（数据已在之前的观察结果里）；严禁虚构列表之外的工具名（例如：没有 math/calculation/average 工具）。所有计算（均值、百分比、最值、对比）必须在 "thought" 字段内自行完成，再给出 final_answer。
11. 你总共只有 {MAX_ITERATIONS} 次行动机会。提前规划：先查询、再分析已有数据、后作答，不要在冗余查询上浪费行动次数。
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
            max_tokens=4096,  # 推理模型(如step系列)reasoning占位大,2048会导致JSON截断
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
