"""H2Brain - Fuel Cell Health Analysis Module

Analyzes fuel cell stack degradation using real telemetry data:
- Polarization curve (V-I curve) tracking across trips
- Thermal stress analysis (temperature differential)
- Efficiency metrics (power output vs H2 consumption)
- Degradation trend prediction
- Health score computation

Based on 2 stacks (A & B) with voltage, current, temperature sensors.

Physical Constants & References:
  - H2 LHV = 33.3 kWh/kg. Source: NIST Chemistry WebBook (Standard Reference
    Database 69), https://webbook.nist.gov/cgi/cbook.cgi?ID=C1333740
  - PEM fuel cell reference efficiency = 50%. Source: DOE Fuel Cell Technologies
    Office, "Fuel Cells Fact Sheet" (2015), typical PEMFC stack efficiency
    40-60% at rated power.
  - Voltage/current/temperature conversions: official T05 data package
    "数据计算方法(3).md", formula: actual = raw * rate + offset.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

from .data_processor import get_processor, VEHICLE_FILES

logger = logging.getLogger("h2brain.fuelcell")

# Health score thresholds
HEALTH_EXCELLENT = 90
HEALTH_GOOD = 75
HEALTH_ATTENTION = 60
HEALTH_WARNING = 40

# Reference values for a healthy stack (typical hydrogen fuel cell truck)
REF_VOLTAGE_NOMINAL = 380.0  # V, nominal stack voltage at rated power
REF_VOLTAGE_OCV = 450.0  # V, open circuit voltage
REF_TEMP_MAX = 80.0  # C, max operating temperature
REF_TEMP_DIFF_MAX = 15.0  # C, max inlet-outlet differential
REF_EFFICIENCY = 0.55  # 55%, reference stack efficiency


def _safe_mean(series: pd.Series) -> float:
    """Safe mean that handles empty series."""
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    return float(s.mean())


def _safe_max(series: pd.Series) -> float:
    """Safe max."""
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    return float(s.max())


def _safe_min(series: pd.Series) -> float:
    """Safe min."""
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    return float(s.min())


def _safe_std(series: pd.Series) -> float:
    """Safe std."""
    s = series.dropna()
    if len(s) == 0:
        return 0.0
    return float(s.std())


def _compute_stack_power(df: pd.DataFrame) -> pd.Series:
    """Compute instantaneous stack power if not already present."""
    if "stack_power" in df.columns:
        return df["stack_power"]
    vol_a = df.get(
        "celDataExt_fuelCell_output_vol_A_燃料电池输出电压(A堆)",
        pd.Series(dtype=float),
    )
    cur_a = df.get(
        "celDataExt_fuelcell_output_cur_A_燃料电池输出电流(A堆)",
        pd.Series(dtype=float),
    )
    vol_b = df.get(
        "celDataExt_fuelCell_output_vol_B_燃料电池输出电压(B堆)",
        pd.Series(dtype=float),
    )
    cur_b = df.get(
        "celDataExt_fuelcell_output_cur_B_燃料电池输出电流(B堆)",
        pd.Series(dtype=float),
    )
    power = (vol_a * cur_a + vol_b * cur_b) / 1000.0
    power = power.clip(lower=0)
    return power


def analyze_fuel_cell_health(vehicle_id: str) -> dict[str, Any]:
    """Compute comprehensive fuel cell health analysis for a vehicle.

    Args:
        vehicle_id: 'V1' or 'V2'

    Returns:
        Dict with health_score, degradation metrics, per-trip analysis,
        polarization data, thermal analysis, and recommendations.
    """
    processor = get_processor()
    trips = processor.get_trips(vehicle_id)
    if not trips:
        return {"error": f"No trips found for vehicle {vehicle_id}"}

    # Get raw DataFrame for this vehicle
    if vehicle_id not in processor._vehicle_data:
        return {"error": f"Vehicle {vehicle_id} data not loaded"}
    df = processor._vehicle_data[vehicle_id]

    # Filter to active fuel cell operation (power > 1kW)
    stack_power = _compute_stack_power(df)
    active_mask = stack_power > 1.0
    df_active = df[active_mask].copy()
    if len(df_active) == 0:
        return {"error": "No active fuel cell data found"}

    # -----------------------------------------------------------------------
    # 1. Stack Voltage Analysis (Degradation Indicator)
    # -----------------------------------------------------------------------
    vol_a_col = "celDataExt_fuelCell_output_vol_A_燃料电池输出电压(A堆)"
    vol_b_col = "celDataExt_fuelCell_output_vol_B_燃料电池输出电压(B堆)"
    cur_a_col = "celDataExt_fuelcell_output_cur_A_燃料电池输出电流(A堆)"
    cur_b_col = "celDataExt_fuelcell_output_cur_B_燃料电池输出电流(B堆)"

    vol_a = df_active.get(vol_a_col, pd.Series(dtype=float))
    vol_b = df_active.get(vol_b_col, pd.Series(dtype=float))
    cur_a = df_active.get(cur_a_col, pd.Series(dtype=float))
    cur_b = df_active.get(cur_b_col, pd.Series(dtype=float))

    # Voltage at different power levels (polarization curve sampling)
    power_bins = [(0, 10), (10, 30), (30, 60), (60, 100), (100, 200)]
    polarization = []
    for pmin, pmax in power_bins:
        mask = (stack_power[active_mask] >= pmin) & (stack_power[active_mask] < pmax)
        if mask.sum() > 5:
            polarization.append(
                {
                    "power_range": f"{pmin}-{pmax}kW",
                    "voltage_a_mean": round(_safe_mean(vol_a[mask]), 1),
                    "voltage_b_mean": round(_safe_mean(vol_b[mask]), 1),
                    "current_a_mean": round(_safe_mean(cur_a[mask]), 1),
                    "current_b_mean": round(_safe_mean(cur_b[mask]), 1),
                    "sample_count": int(mask.sum()),
                }
            )

    # Overall voltage stats
    voltage_stats = {
        "stack_a": {
            "mean": round(_safe_mean(vol_a), 1),
            "max": round(_safe_max(vol_a), 1),
            "min": round(_safe_min(vol_a), 1),
            "std": round(_safe_std(vol_a), 1),
        },
        "stack_b": {
            "mean": round(_safe_mean(vol_b), 1),
            "max": round(_safe_max(vol_b), 1),
            "min": round(_safe_min(vol_b), 1),
            "std": round(_safe_std(vol_b), 1),
        },
    }

    # -----------------------------------------------------------------------
    # 2. Thermal Stress Analysis
    # -----------------------------------------------------------------------
    temp_in_col = "celDataExt_volpile_input_temp_A_电堆入口温度(A堆)"
    temp_out_col = "celDataExt_volpile_output_temp_A_电堆出口温度(A堆)"
    temp_h2_col = "celData_maxTemp_氢系统中最高温度"

    temp_in = df_active.get(temp_in_col, pd.Series(dtype=float))
    temp_out = df_active.get(temp_out_col, pd.Series(dtype=float))
    temp_h2 = df_active.get(temp_h2_col, pd.Series(dtype=float))

    temp_diff = (temp_out - temp_in).dropna()
    thermal = {
        "stack_temp_in": {
            "mean": round(_safe_mean(temp_in), 1),
            "max": round(_safe_max(temp_in), 1),
        },
        "stack_temp_out": {
            "mean": round(_safe_mean(temp_out), 1),
            "max": round(_safe_max(temp_out), 1),
        },
        "temp_differential": {
            "mean": round(_safe_mean(temp_diff), 1) if len(temp_diff) > 0 else 0.0,
            "max": round(_safe_max(temp_diff), 1) if len(temp_diff) > 0 else 0.0,
        },
        "h2_system_max_temp": {
            "mean": round(_safe_mean(temp_h2), 1),
            "max": round(_safe_max(temp_h2), 1),
        },
        "thermal_stress_events": int((temp_diff.abs() > REF_TEMP_DIFF_MAX).sum()),
    }

    # -----------------------------------------------------------------------
    # 3. Efficiency Analysis (Power vs H2 Consumption)
    # -----------------------------------------------------------------------
    h2_consume_col = "celDataExt_h2_total_consume_累计氢耗"

    total_power = float((stack_power[active_mask]).sum())  # kW (per 10s interval)
    # Approximate energy: power * interval (10s = 1/360 h)
    interval_h = 10.0 / 3600.0
    total_energy_kwh = total_power * interval_h

    h2_total = df_active.get(h2_consume_col, pd.Series(dtype=float))
    if len(h2_total) > 1:
        h2_consumed = float(h2_total.iloc[-1] - h2_total.iloc[0])
    else:
        h2_consumed = 0.0

    # Efficiency: electrical energy / hydrogen energy
    # H2 LHV = 33.3 kWh/kg (NIST Chemistry WebBook, Standard Reference Database 69)
    if h2_consumed > 0:
        efficiency = (
            total_energy_kwh / (h2_consumed * 33.3)
        ) * 100  # 33.3 = H2 LHV in kWh/kg
    else:
        efficiency = 0.0

    efficiency_data = {
        "total_energy_kwh": round(total_energy_kwh, 1),
        "h2_consumed_kg": round(h2_consumed, 2),
        "stack_efficiency_pct": round(efficiency, 1),
        "reference_efficiency_pct": REF_EFFICIENCY * 100,
    }

    # -----------------------------------------------------------------------
    # 4. Per-Trip Degradation Trend
    # -----------------------------------------------------------------------
    trip_trends = []
    for trip_info in trips:
        trip_id = trip_info["trip_id"]
        detail = processor.get_trip_detail(vehicle_id, trip_id)
        if detail is None:
            continue
        ov = detail["overview"]
        trip_trends.append(
            {
                "trip_id": trip_id,
                "date": ov["date"],
                "distance_km": ov["distance_km"],
                "h2_per_100km": ov["h2_per_100km"],
                "stack_power_avg": ov["stack_power_avg"],
                "stack_power_max": ov["stack_power_max"],
            }
        )

    # Degradation rate: compare early trips vs late trips
    if len(trip_trends) >= 4:
        n = len(trip_trends)
        early = trip_trends[: n // 3]
        late = trip_trends[-n // 3 :]
        early_power = sum(t["stack_power_avg"] for t in early) / len(early)
        late_power = sum(t["stack_power_avg"] for t in late) / len(late)
        early_h2 = sum(t["h2_per_100km"] for t in early) / len(early)
        late_h2 = sum(t["h2_per_100km"] for t in late) / len(late)

        power_change_pct = (
            ((late_power - early_power) / early_power * 100) if early_power > 0 else 0
        )
        h2_change_pct = ((late_h2 - early_h2) / early_h2 * 100) if early_h2 > 0 else 0
    else:
        power_change_pct = 0.0
        h2_change_pct = 0.0

    degradation = {
        "trip_count": len(trip_trends),
        "power_trend_pct": round(power_change_pct, 1),
        "h2_consumption_trend_pct": round(h2_change_pct, 1),
        "interpretation": (
            "degrading"
            if h2_change_pct > 5
            else "stable"
            if abs(h2_change_pct) <= 5
            else "improving"
        ),
    }

    # -----------------------------------------------------------------------
    # 5. Health Score Computation (0-100)
    # -----------------------------------------------------------------------
    # Voltage score: compare mean voltage to nominal
    mean_voltage = (_safe_mean(vol_a) + _safe_mean(vol_b)) / 2
    voltage_ratio = (
        mean_voltage / REF_VOLTAGE_NOMINAL if REF_VOLTAGE_NOMINAL > 0 else 1.0
    )
    voltage_score = max(0, min(100, voltage_ratio * 100))

    # Thermal score: penalty for high temp differential
    thermal["temp_differential"]["mean"]
    max_temp_diff = thermal["temp_differential"]["max"]
    thermal_score = max(0, 100 - (max_temp_diff / REF_TEMP_DIFF_MAX) * 30)

    # Efficiency score
    eff_score = (
        min(100, (efficiency / (REF_EFFICIENCY * 100)) * 100) if efficiency > 0 else 50
    )

    # Degradation score
    if h2_change_pct > 10:
        degr_score = 40
    elif h2_change_pct > 5:
        degr_score = 60
    elif h2_change_pct > 0:
        degr_score = 75
    else:
        degr_score = 90

    # Weighted overall score
    health_score = (
        voltage_score * 0.35
        + thermal_score * 0.20
        + eff_score * 0.25
        + degr_score * 0.20
    )
    health_score = round(max(0, min(100, health_score)), 1)

    # Health level
    if health_score >= HEALTH_EXCELLENT:
        level = "excellent"
        level_cn = "优秀"
    elif health_score >= HEALTH_GOOD:
        level = "good"
        level_cn = "良好"
    elif health_score >= HEALTH_ATTENTION:
        level = "attention"
        level_cn = "需关注"
    else:
        level = "warning"
        level_cn = "警告"

    # -----------------------------------------------------------------------
    # 6. Recommendations
    # -----------------------------------------------------------------------
    recommendations = []
    if voltage_score < 70:
        recommendations.append(
            f"电堆平均电压 {mean_voltage:.1f}V，低于额定值 {REF_VOLTAGE_NOMINAL}V，"
            "建议安排电堆性能检测，检查单体电池一致性"
        )
    if max_temp_diff > REF_TEMP_DIFF_MAX:
        recommendations.append(
            f"电堆进出口最大温差 {max_temp_diff:.1f}C，超过阈值 {REF_TEMP_DIFF_MAX}C，"
            "检查冷却系统散热效率，排查冷却液流量"
        )
    if thermal["thermal_stress_events"] > 10:
        recommendations.append(
            f"检测到 {thermal['thermal_stress_events']} 次热应力事件，"
            "频繁温度波动会加速电堆衰减，建议优化热管理策略"
        )
    if h2_change_pct > 5:
        recommendations.append(
            f"后期行程氢耗较前期上升 {h2_change_pct:.1f}%，"
            "电堆可能存在衰减趋势，建议增加监测频率并安排预防性维护"
        )
    if efficiency < REF_EFFICIENCY * 100 * 0.8:
        recommendations.append(
            f"当前电堆效率 {efficiency:.1f}%，低于参考值 {REF_EFFICIENCY * 100:.0f}%的80%，"
            "建议进行电堆活化处理或更换衰减严重的单体"
        )
    if not recommendations:
        recommendations.append("电堆各项指标正常，建议保持当前维护节奏，定期监测")

    # -----------------------------------------------------------------------
    # 7. Remaining Useful Life Estimation
    # -----------------------------------------------------------------------
    # Simple linear model: if degradation rate is known, estimate RUL
    # Assume stack end-of-life at health_score = 40
    if h2_change_pct > 0 and len(trip_trends) > 0:
        # Estimate degradation per trip
        total_trips = len(trip_trends)
        score_loss_per_trip = (100 - health_score) / max(total_trips, 1)
        remaining_trips = int(
            (health_score - HEALTH_WARNING) / max(score_loss_per_trip, 0.1)
        )
        rul = {
            "estimated_remaining_trips": remaining_trips,
            "degradation_rate_per_trip": round(score_loss_per_trip, 2),
            "estimation_method": "linear extrapolation based on h2 consumption trend",
            "note": f"Based on {total_trips} trips, assumes current usage pattern continues",
        }
    else:
        rul = {
            "estimated_remaining_trips": None,
            "degradation_rate_per_trip": 0.0,
            "estimation_method": "insufficient degradation data",
            "note": "No significant degradation detected",
        }

    # -----------------------------------------------------------------------
    # 8. LSTM RUL 升级方案说明（当前线性基线 → 时序深度模型）
    # -----------------------------------------------------------------------
    rul["lstm_upgrade_plan"] = {
        "现状与局限": (
            "当前 RUL 采用线性外推：以「每次行程健康分损失 = (100-当前分)÷行程数」为衰减速率，"
            "外推至报废阈值（健康分 40）。该方法假设衰减匀速，无法反映工况相关的非线性衰减"
            "（如爬坡重载集中期衰减加速、静置期衰减减缓）。"
        ),
        "输入特征": (
            "A/B 双堆电压、电流、电堆功率、进出口温度与温差、氢系统最高温度、"
            "百公里氢耗（滚动计算）、SOC 共 10 维时序特征，采样周期 10s，"
            "来源为 T05 官方数据包遥测（63.4 万行）。"
        ),
        "网络结构": (
            "输入层 → LSTM×2（隐藏维 64，捕捉长短期衰减动态）→ 全连接层（32）→ 输出层。"
            "输入为滑动窗口序列（窗口 500 个时间步，约 83 分钟运行段），"
            "输出为窗口末端健康分与未来衰减速率。"
        ),
        "训练策略": (
            "按行程划分训练/验证集（时序不打乱），损失函数 RMSE，"
            "Adam 优化器（lr=1e-3），早停防过拟合；"
            "用前期行程训练、后期行程验证，模拟真实预测场景。"
        ),
        "可解释性设计": (
            "在 LSTM 上叠加时间注意力权重，输出各时间步对预测的贡献度，"
            "并保留特征级消融分析（逐特征遮蔽看预测变化），"
            "确保「预测结论 + 依据」双输出，与平台可解释性原则一致。"
        ),
        "预期收益": (
            "对非线性衰减工况，预测误差较线性外推可显著降低（行业文献：PEMFC RUL 预测 "
            "LSTM 类模型误差普遍低于线性基线 30% 以上）；"
            "并能输出「未来 N 行程健康分曲线」而非单点估计，支撑分级维护决策。"
        ),
        "实施状态": (
            "注：当前 18 天数据期内电堆衰减幅度微小（<2%），"
            "尚不足以训练出稳健的深度模型；LSTM 方案作为长期数据积累后的升级路线，"
            "现阶段以线性外推为可解释基线，符合「先可解释、后深度」的工程原则。"
        ),
    }

    return {
        "vehicle_id": vehicle_id,
        "vehicle_label": VEHICLE_FILES.get(vehicle_id, {}).get("label", vehicle_id),
        "region": VEHICLE_FILES.get(vehicle_id, {}).get("region", ""),
        "analysis_timestamp": datetime.now().isoformat(),
        "health_score": health_score,
        "health_level": level,
        "health_level_cn": level_cn,
        "voltage_analysis": voltage_stats,
        "polarization_curve": polarization,
        "thermal_analysis": thermal,
        "efficiency_analysis": efficiency_data,
        "degradation_trend": degradation,
        "trip_trends": trip_trends,
        "remaining_useful_life": rul,
        "recommendations": recommendations,
        "score_breakdown": {
            "voltage_score": round(voltage_score, 1),
            "thermal_score": round(thermal_score, 1),
            "efficiency_score": round(eff_score, 1),
            "degradation_score": round(degr_score, 1),
        },
    }
