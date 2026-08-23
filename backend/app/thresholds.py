"""H2Brain - Threshold Calibration Module

Extracts all hardcoded analysis thresholds into named constants and provides
data-driven calibration based on actual telemetry distributions.

Calibration approach:
- Road classification speeds: based on speed distribution percentiles
- Power mode thresholds: based on power distribution percentiles when stationary vs moving
- Load change threshold: based on power delta distribution (95th percentile)
- Driving behavior: industry standards for heavy-duty vehicles (fixed but documented)
- Anomaly detection: adaptive based on per-trip statistics (already data-driven)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger("h2brain.thresholds")

# ============================================================================
# Default Thresholds (calibrated from V1+V2 telemetry data)
# ============================================================================

DEFAULTS = {
    # --- Trip Segmentation ---
    "trip_gap_seconds": 600,  # 10 min gap -> new trip
    "trip_min_moving_points": 10,  # min moving data points for valid trip
    "trip_moving_speed": 1.0,  # km/h, above = "moving"
    # --- Road Classification (speed in km/h) ---
    "road_speed_idle": 3.0,  # below = idle
    "road_speed_yard": 15.0,  # below = yard/loading
    "road_speed_urban": 50.0,  # below = urban road
    "road_speed_highway": 80.0,  # below = highway, above = highway
    "road_std_urban": 15.0,  # speed std threshold for urban national road
    "road_std_mountain": 20.0,  # speed std threshold for mountain road
    "road_min_segment_duration": 30,  # seconds, shorter segments merged
    "road_rolling_window": 60,  # rolling window size (points)
    # --- Power Mode Detection ---
    "power_idle_kw": 5.0,  # kW, stationary power generation threshold
    "power_drive_kw": 10.0,  # kW, active fuel cell driving threshold
    "power_regen_batt_cur": -5.0,  # A, regenerative braking current threshold
    "power_stationary_speed": 1.0,  # km/h, below = stationary
    # --- Load Change Detection ---
    "load_change_rate_kw": 20.0,  # kW per 5s, load change event threshold
    "load_change_min_kw": 10.0,  # kW, minimum significant power change
    # --- Driving Behavior ---
    "rapid_accel_ms2": 1.5,  # m/s^2, rapid acceleration threshold
    "hard_brake_ms2": -2.0,  # m/s^2, hard braking threshold
    "speeding_kmh": 90.0,  # km/h, speeding threshold for heavy trucks
    "rapid_accel_min_points": 2,  # min consecutive points for rapid accel event
    "hard_brake_min_points": 2,  # min consecutive points for hard brake event
    "speeding_min_points": 5,  # min consecutive points for speeding event
    # --- Anomaly Detection ---
    "anomaly_std_multiplier": 0.5,  # threshold = avg + multiplier * std
    "anomaly_high_load_changes": 30,  # load change count for "frequent load change"
    "anomaly_low_speed_kmh": 20.0,  # low speed for anomaly attribution
    "anomaly_high_power_kw": 100.0,  # high power for anomaly attribution
    # --- Factor Analysis ---
    "factor_corr_strong": 0.7,  # strong correlation threshold
    "factor_corr_moderate": 0.4,  # moderate correlation threshold
    "factor_corr_weak": 0.2,  # weak correlation threshold
    "factor_min_samples": 10,  # min moving samples for factor analysis
}


class Thresholds:
    """Threshold registry with optional override from calibration or config file."""

    def __init__(self, overrides: dict[str, float] | None = None):
        self._values = dict(DEFAULTS)
        if overrides:
            self._values.update(overrides)

    def __getitem__(self, key: str) -> float:
        return self._values[key]

    def __getattr__(self, name: str) -> float:
        if name in self._values:
            return self._values[name]
        raise AttributeError(f"Unknown threshold: {name}")

    def to_dict(self) -> dict[str, float]:
        return dict(self._values)

    def update(self, overrides: dict[str, float]):
        self._values.update(overrides)


# Global singleton (used by data_processor.py)
THRESHOLDS = Thresholds()


def calibrate_from_data(
    vehicle_data: dict[str, pd.DataFrame],
    trips: dict[str, list[pd.DataFrame]],
) -> dict[str, Any]:
    """Compute data-driven threshold calibrations from actual telemetry.

    Returns a dict with:
    - calibrated: thresholds adjusted based on data distributions
    - report: human-readable calibration report
    - stats: raw statistics used for calibration
    """
    stats: dict[str, Any] = {}
    calibrated: dict[str, float] = {}

    # Combine all trip data for distribution analysis
    all_trips = []
    for vid, trip_list in trips.items():
        for trip in trip_list:
            all_trips.append(trip)

    if not all_trips:
        return {"calibrated": {}, "report": "No trip data available", "stats": {}}

    combined = pd.concat(all_trips, ignore_index=True)
    moving = combined[combined["speed"] > 1.0]
    stationary = combined[combined["speed"] <= 1.0]

    # --- Speed distribution for road classification ---
    speed_vals = moving["speed"].values
    stats["speed"] = {
        "count": len(speed_vals),
        "mean": float(np.mean(speed_vals)),
        "median": float(np.median(speed_vals)),
        "p10": float(np.percentile(speed_vals, 10)),
        "p25": float(np.percentile(speed_vals, 25)),
        "p50": float(np.percentile(speed_vals, 50)),
        "p75": float(np.percentile(speed_vals, 75)),
        "p90": float(np.percentile(speed_vals, 90)),
        "p95": float(np.percentile(speed_vals, 95)),
        "std": float(np.std(speed_vals)),
    }

    # Calibrate road speed thresholds using percentiles
    # Idle: keep at 3 km/h (industry standard, data-independent)
    # Yard: p10 of moving speed (slowest 10% of moving data)
    calibrated["road_speed_yard"] = max(10.0, min(20.0, stats["speed"]["p10"]))

    # Urban: p50 of moving speed (median)
    calibrated["road_speed_urban"] = max(40.0, min(60.0, stats["speed"]["p50"]))

    # Highway: p75 of moving speed
    calibrated["road_speed_highway"] = max(70.0, min(90.0, stats["speed"]["p75"]))

    # --- Power distribution for power mode ---
    power_moving = moving["stack_power"].values
    power_stationary = stationary["stack_power"].values

    stats["power"] = {
        "moving_mean": float(np.mean(power_moving)) if len(power_moving) > 0 else 0,
        "moving_p25": float(np.percentile(power_moving, 25))
        if len(power_moving) > 0
        else 0,
        "moving_p50": float(np.percentile(power_moving, 50))
        if len(power_moving) > 0
        else 0,
        "stationary_mean": float(np.mean(power_stationary))
        if len(power_stationary) > 0
        else 0,
        "stationary_p75": float(np.percentile(power_stationary, 75))
        if len(power_stationary) > 0
        else 0,
    }

    # Calibrate power thresholds
    # Idle power: p75 of stationary power (most stationary power is low)
    if len(power_stationary) > 100:
        calibrated["power_idle_kw"] = max(
            3.0, min(8.0, stats["power"]["stationary_p75"])
        )

    # Drive power: p25 of moving power (lower quartile of active driving)
    if len(power_moving) > 100:
        calibrated["power_drive_kw"] = max(8.0, min(15.0, stats["power"]["moving_p25"]))

    # --- Load change rate ---
    # Calculate 5s power deltas across all trips
    all_deltas = []
    for trip in all_trips:
        if len(trip) < 2:
            continue
        dt = trip["timestamp"].diff().dt.total_seconds().fillna(1)
        dp = trip["stack_power"].diff()
        dp_5s = dp / dt * 5
        all_deltas.extend(dp_5s.dropna().abs().tolist())

    if all_deltas:
        deltas_arr = np.array(all_deltas)
        stats["load_change"] = {
            "count": len(deltas_arr),
            "mean": float(np.mean(deltas_arr)),
            "p50": float(np.percentile(deltas_arr, 50)),
            "p75": float(np.percentile(deltas_arr, 75)),
            "p90": float(np.percentile(deltas_arr, 90)),
            "p95": float(np.percentile(deltas_arr, 95)),
        }
        # Load change threshold: p90 of absolute power deltas
        calibrated["load_change_rate_kw"] = max(
            15.0, min(30.0, stats["load_change"]["p90"])
        )

    # --- Acceleration distribution for driving behavior ---
    all_accels = []
    for trip in all_trips:
        if len(trip) < 2:
            continue
        dt = trip["timestamp"].diff().dt.total_seconds().fillna(0.1)
        dt = dt.clip(lower=0.1)
        accel = (trip["speed"].diff() / 3.6) / dt
        all_accels.extend(accel.dropna().tolist())

    if all_accels:
        accels_arr = np.array(all_accels)
        stats["acceleration"] = {
            "count": len(accels_arr),
            "mean": float(np.mean(accels_arr)),
            "p5": float(np.percentile(accels_arr, 5)),
            "p95": float(np.percentile(accels_arr, 95)),
            "std": float(np.std(accels_arr)),
        }
        # Rapid accel: p95 of acceleration values (top 5% = aggressive)
        calibrated["rapid_accel_ms2"] = max(1.0, min(2.5, stats["acceleration"]["p95"]))
        # Hard brake: p5 of acceleration values (bottom 5%)
        calibrated["hard_brake_ms2"] = max(-3.0, min(-1.5, stats["acceleration"]["p5"]))

    # --- H2 per 100km distribution for anomaly detection ---
    h2_values = []
    for trip in all_trips:
        if len(trip) < 2:
            continue
        distance = trip["speed"].sum() / 3600  # km
        if distance > 0.1:
            h2_used = trip["h2_consumed_cum"].iloc[-1] - trip["h2_consumed_cum"].iloc[0]
            if h2_used > 0:
                h2_values.append(h2_used / distance * 100)

    if h2_values:
        h2_arr = np.array(h2_values)
        stats["h2_per_100km"] = {
            "count": len(h2_arr),
            "mean": float(np.mean(h2_arr)),
            "median": float(np.median(h2_arr)),
            "p25": float(np.percentile(h2_arr, 25)),
            "p75": float(np.percentile(h2_arr, 75)),
            "std": float(np.std(h2_arr)),
        }

    # --- Generate report ---
    report_lines = [
        "# H2Brain 阈值标定报告",
        f"",
        f"数据样本: {len(all_trips)} 个行程, {len(combined)} 行遥测数据",
        f"有效运动数据: {len(moving)} 行, 静止数据: {len(stationary)} 行",
        "",
        "## 速度分布统计 (km/h)",
    ]
    if "speed" in stats:
        s = stats["speed"]
        report_lines.extend(
            [
                f"- 均值: {s['mean']:.1f}",
                f"- 中位数: {s['median']:.1f}",
                f"- P10/P25/P50/P75/P90: {s['p10']:.1f} / {s['p25']:.1f} / {s['p50']:.1f} / {s['p75']:.1f} / {s['p90']:.1f}",
                f"- 标准差: {s['std']:.1f}",
            ]
        )

    report_lines.append("\n## 功率分布统计 (kW)")
    if "power" in stats:
        p = stats["power"]
        report_lines.extend(
            [
                f"- 行驶时均值: {p['moving_mean']:.1f}",
                f"- 行驶时 P25: {p['moving_p25']:.1f}",
                f"- 静止时均值: {p['stationary_mean']:.1f}",
                f"- 静止时 P75: {p['stationary_p75']:.1f}",
            ]
        )

    report_lines.append("\n## 变载速率统计 (kW/5s)")
    if "load_change" in stats:
        lc = stats["load_change"]
        report_lines.extend(
            [
                f"- 均值: {lc['mean']:.1f}",
                f"- P50/P75/P90/P95: {lc['p50']:.1f} / {lc['p75']:.1f} / {lc['p90']:.1f} / {lc['p95']:.1f}",
            ]
        )

    report_lines.append("\n## 加速度分布统计 (m/s²)")
    if "acceleration" in stats:
        a = stats["acceleration"]
        report_lines.extend(
            [
                f"- 均值: {a['mean']:.2f}",
                f"- P5/P95: {a['p5']:.2f} / {a['p95']:.2f}",
                f"- 标准差: {a['std']:.2f}",
            ]
        )

    report_lines.append("\n## 氢耗分布统计 (kg/100km)")
    if "h2_per_100km" in stats:
        h = stats["h2_per_100km"]
        report_lines.extend(
            [
                f"- 均值: {h['mean']:.2f}",
                f"- 中位数: {h['median']:.2f}",
                f"- P25/P75: {h['p25']:.2f} / {h['p75']:.2f}",
                f"- 标准差: {h['std']:.2f}",
            ]
        )

    report_lines.append("\n## 标定结果对比")
    report_lines.append(f"| 参数 | 默认值 | 标定值 | 变化 |")
    report_lines.append(f"|------|--------|--------|------|")
    for key, new_val in sorted(calibrated.items()):
        old_val = DEFAULTS.get(key, "N/A")
        if isinstance(old_val, (int, float)):
            change = ((new_val - old_val) / old_val * 100) if old_val != 0 else 0
            change_str = f"{change:+.1f}%"
        else:
            change_str = "N/A"
        report_lines.append(f"| {key} | {old_val} | {new_val:.1f} | {change_str} |")

    report = "\n".join(report_lines)

    return {
        "calibrated": calibrated,
        "report": report,
        "stats": stats,
    }


def save_calibration_report(report: str, output_path: str | Path):
    """Save calibration report to file."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    logger.info(f"Calibration report saved to {output_path}")


def load_config(config_path: str | Path) -> dict[str, float]:
    """Load threshold overrides from JSON config file."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)
