"""H2Brain - Real Data Processor

Loads real hydrogen vehicle telemetry CSV data, applies conversion formulas,
segments trips, classifies road conditions, detects power modes and load changes.

Data Source & Conversion References:
  - Raw → Physical conversion formulas (rate/offset) are sourced from the official
    T05 data package document: "数据计算方法(3).md" (数据字段计算方法).
    Formula: actual_value = raw_value * rate + offset
    e.g. speed: raw * 0.1 (km/h), current: raw * 0.1 - 3000 (A),
    temperature: raw - 40 (deg C), pressure: raw * 0.1 (MPa).
  - H2 lower heating value (LHV) = 33.3 kWh/kg.
    Source: NIST Chemistry WebBook, Standard Reference Database 69.
    https://webbook.nist.gov/cgi/cbook.cgi?ID=C1333740 (Hydrogen, H2)
  - PEM fuel cell nominal efficiency = 50%.
    Source: DOE Fuel Cell Technologies Office, "Fuel Cells Fact Sheet" (2015),
    typical PEMFC stack efficiency range 40-60% at rated power.
    https://www.energy.gov/eere/fuelcells/fuel-cells-fact-sheet
  - H2 mass calculation uses real-gas equation (from manual record spreadsheet):
    m = 24.569533 * V * n * P / (101.325 * (T + 273.15 + 1.9155 * P))
    where V=cylinder volume(L), n=number of cylinders, P=pressure(MPa),
    T=temperature(degC). The constant 24.569533 incorporates H2 molar mass
    and unit conversions per the ideal gas law with compressibility correction.
"""

from __future__ import annotations

import os
import pickle
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .road_classifier import classify_road_conditions_v2, explain_methodology
from .thresholds import THRESHOLDS

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = (
    Path(os.environ.get("H2BRAIN_DATA_DIR", ""))
    if os.environ.get("H2BRAIN_DATA_DIR")
    else (
        Path(__file__).resolve().parent.parent.parent.parent
        / "T05_数据包"
        / "T05_氢能车辆运营智能分析与决策助手数据包"
    )
)
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

VEHICLE_FILES = {
    "V1": {
        "label": "测试车辆1#",
        "file": "测试车辆1#车辆数据.parquet",
        "region": "湖北襄阳",
    },
    "V2": {
        "label": "测试车辆2#",
        "file": "测试车辆2#车辆数据.parquet",
        "region": "新疆吐鲁番",
    },
}

# Columns to load from CSV (subset of 130+ columns)
COLUMNS = [
    "time_数据采集时间",
    "lon_经度",
    "lat_纬度",
    "canData_speed_车速",
    "canData_mile_累计里程",
    "canData_battVol_总电压",
    "canData_battCur_总电流",
    "canData_battSoc_电池SOC",
    "canData_runModel_运行模式",
    "celData_remainPercent_剩余氢百分比",
    "celData_maxTemp_氢系统中最高温度",
    "celData_maxPressure_氢气最高压力",
    "celDataExt_fcWorkState_燃料电池工作状态",
    "celDataExt_h2Per100Km_百公里氢耗",
    "celDataExt_h2_remain_氢气剩余量",
    "celDataExt_h2_remain_per_氢气剩余量百分比",
    "celDataExt_h2_total_consume_累计氢耗",
    "celDataExt_high_pressure_高压压力(气瓶平均压力)",
    "celDataExt_fuelCell_output_vol_A_燃料电池输出电压(A堆)",
    "celDataExt_fuelcell_output_cur_A_燃料电池输出电流(A堆)",
    "celDataExt_fuelCell_output_vol_B_燃料电池输出电压(B堆)",
    "celDataExt_fuelcell_output_cur_B_燃料电池输出电流(B堆)",
    "celDataExt_volpile_input_temp_A_电堆入口温度(A堆)",
    "celDataExt_volpile_output_temp_A_电堆出口温度(A堆)",
    "H49Data_longitudinal_acc_纵向加速度",
]

# Conversion formulas: raw_value -> physical_value
# Format: column_name -> (rate, offset)
# Reference: Official T05 data package "数据计算方法(3).md"
# Formula: actual_value = raw_value * rate + offset
CONVERSIONS = {
    "canData_speed_车速": (0.1, 0),
    "canData_mile_累计里程": (0.1, 0),
    "canData_battVol_总电压": (0.1, 0),
    "canData_battCur_总电流": (0.1, -3000),
    "lon_经度": (1e-6, 0),
    "lat_纬度": (1e-6, 0),
    "celData_maxTemp_氢系统中最高温度": (1, -40),
    "celData_maxPressure_氢气最高压力": (0.1, 0),
    "celDataExt_high_pressure_高压压力(气瓶平均压力)": (0.01, 0),
    "celDataExt_h2_remain_氢气剩余量": (0.01, 0),
    "celDataExt_h2Per100Km_百公里氢耗": (0.1, 0),
    "celDataExt_h2_total_consume_累计氢耗": (0.1, 0),
    "celDataExt_fuelCell_output_vol_A_燃料电池输出电压(A堆)": (0.1, 0),
    "celDataExt_fuelcell_output_cur_A_燃料电池输出电流(A堆)": (0.1, 0),
    "celDataExt_fuelCell_output_vol_B_燃料电池输出电压(B堆)": (0.1, 0),
    "celDataExt_fuelcell_output_cur_B_燃料电池输出电流(B堆)": (0.1, 0),
    "celDataExt_volpile_input_temp_A_电堆入口温度(A堆)": (1, -40),
    "celDataExt_volpile_output_temp_A_电堆出口温度(A堆)": (1, -40),
}

# Time gap threshold for trip segmentation (seconds)
TRIP_GAP_THRESHOLD = 600  # 10 minutes

# Road condition colors
ROAD_COLORS = {
    "高速": "#2196F3",
    "城市-快速路": "#FF9800",
    "城市-国道": "#4CAF50",
    "山区": "#9C27B0",
    "怠速": "#F44336",
    "场区-装卸": "#E91E63",
}

# Power mode colors
MODE_COLORS = {
    "燃电": "#1565C0",
    "能量回收": "#2E7D32",
    "驻车发电": "#E65100",
    "纯电": "#0277BD",
    "怠速": "#757575",
}


# ---------------------------------------------------------------------------
# Data Loading & Conversion
# ---------------------------------------------------------------------------


def _load_and_convert(filepath: str, vehicle_id: str) -> pd.DataFrame:
    """Load data file (parquet or CSV) and apply conversion formulas."""
    if filepath.endswith(".parquet"):
        df = pd.read_parquet(filepath)
    else:
        df = pd.read_csv(filepath, usecols=COLUMNS, encoding="utf-8-sig")

    # Parse timestamp
    df["timestamp"] = pd.to_datetime(df["time_数据采集时间"], format="mixed")
    df = df.sort_values("timestamp").reset_index(drop=True)

    # Apply conversions
    for col, (rate, offset) in CONVERSIONS.items():
        if col in df.columns:
            df[col] = df[col] * rate + offset

    # Compute derived fields
    # Stack power: P = (V_A * I_A + V_B * I_B) / 1000  (kW)
    vol_a = df["celDataExt_fuelCell_output_vol_A_燃料电池输出电压(A堆)"]
    cur_a = df["celDataExt_fuelcell_output_cur_A_燃料电池输出电流(A堆)"]
    vol_b = df["celDataExt_fuelCell_output_vol_B_燃料电池输出电压(B堆)"]
    cur_b = df["celDataExt_fuelcell_output_cur_B_燃料电池输出电流(B堆)"]
    df["stack_power"] = (vol_a * cur_a + vol_b * cur_b) / 1000.0
    df.loc[df["stack_power"] < 0, "stack_power"] = 0

    # Rename for convenience
    df.rename(
        columns={
            "canData_speed_车速": "speed",
            "canData_mile_累计里程": "mileage",
            "canData_battVol_总电压": "batt_vol",
            "canData_battCur_总电流": "batt_cur",
            "canData_battSoc_电池SOC": "batt_soc",
            "canData_runModel_运行模式": "run_model",
            "celData_remainPercent_剩余氢百分比": "h2_percent",
            "celData_maxTemp_氢系统中最高温度": "h2_max_temp",
            "celData_maxPressure_氢气最高压力": "h2_max_pressure",
            "celDataExt_fcWorkState_燃料电池工作状态": "fc_work_state",
            "celDataExt_h2Per100Km_百公里氢耗": "h2_per_100km",
            "celDataExt_h2_remain_氢气剩余量": "h2_remain",
            "celDataExt_h2_remain_per_氢气剩余量百分比": "h2_remain_per",
            "celDataExt_h2_total_consume_累计氢耗": "h2_total_consume",
            "celDataExt_high_pressure_高压压力(气瓶平均压力)": "high_pressure",
            "celDataExt_volpile_input_temp_A_电堆入口温度(A堆)": "stack_temp_in",
            "celDataExt_volpile_output_temp_A_电堆出口温度(A堆)": "stack_temp_out",
            "H49Data_longitudinal_acc_纵向加速度": "long_acc",
        },
        inplace=True,
    )

    # Add vehicle_id
    df["vehicle_id"] = vehicle_id

    # Filter invalid GPS (0,0)
    df.loc[(df["lon_经度"] == 0) & (df["lat_纬度"] == 0), ["lon_经度", "lat_纬度"]] = (
        np.nan
    )

    # Rename GPS columns to English for safe access
    df.rename(
        columns={
            "lon_经度": "gps_lon",
            "lat_纬度": "gps_lat",
        },
        inplace=True,
    )

    # Compute cumulative H2 consumption from stack power integral
    # H2_rate = stack_power / (LHV * efficiency)
    # LHV of H2 = 33.3 kWh/kg (NIST Chemistry WebBook, H2 lower heating value)
    # PEM fuel cell efficiency = 50% (DOE Fuel Cell Technologies Office, typical PEMFC stack efficiency at rated power)
    # So H2_rate = stack_power / 16.65  (kg/h)
    H2_LHV = 33.3  # kWh/kg, NIST Standard Reference Database 69
    FC_EFFICIENCY = 0.50  # DOE Fuel Cells Fact Sheet (2015), PEMFC 40-60% range
    dt_seconds = df["timestamp"].diff().dt.total_seconds().fillna(0)
    # Cap dt at 300s to handle data gaps within trips while preserving real power generation time
    dt_seconds = dt_seconds.clip(upper=300)
    df["h2_consumed_cum"] = (
        df["stack_power"] * dt_seconds / 3600 / (H2_LHV * FC_EFFICIENCY)
    ).cumsum()

    return df


# ---------------------------------------------------------------------------
# Trip Segmentation
# ---------------------------------------------------------------------------


def _segment_trips(df: pd.DataFrame) -> list[pd.DataFrame]:
    """Segment data into trips based on time gaps > 10 minutes."""
    df = df.copy()
    df["time_diff"] = df["timestamp"].diff().dt.total_seconds()
    # First row has NaN time_diff
    df["time_diff"] = df["time_diff"].fillna(0)

    # Find trip boundaries: time gap > threshold
    trip_starts = df[df["time_diff"] > TRIP_GAP_THRESHOLD].index.tolist()
    trip_starts = [0] + trip_starts

    trips = []
    for i, start in enumerate(trip_starts):
        end = trip_starts[i + 1] if i + 1 < len(trip_starts) else len(df)
        trip = df.iloc[start:end].copy()
        # Only keep trips with actual movement
        moving_rows = trip[trip["speed"] > 1]
        if len(moving_rows) > 10:  # At least 10 moving data points
            trips.append(trip)
    return trips


# ---------------------------------------------------------------------------
# Road Condition Classification
# ---------------------------------------------------------------------------


def _classify_road_conditions(trip: pd.DataFrame) -> list[dict]:
    """Classify road conditions within a trip using rolling statistics."""
    df = trip.copy()
    # Rolling window for speed statistics (60 points ~ 1 min at 1Hz)
    window = min(60, len(df) // 5)
    if window < 5:
        window = 5

    df["speed_roll_mean"] = (
        df["speed"].rolling(window=window, center=True, min_periods=1).mean()
    )
    df["speed_roll_std"] = (
        df["speed"].rolling(window=window, center=True, min_periods=1).std().fillna(0)
    )
    df["power_roll_mean"] = (
        df["stack_power"].rolling(window=window, center=True, min_periods=1).mean()
    )

    # Classify each point
    conditions = []
    for _, row in df.iterrows():
        avg_speed = row["speed_roll_mean"]
        speed_std = row["speed_roll_std"]
        row["power_roll_mean"]

        if avg_speed < THRESHOLDS.road_speed_idle:
            cond = "怠速"
        elif avg_speed < THRESHOLDS.road_speed_yard:
            cond = "场区-装卸"
        elif avg_speed < THRESHOLDS.road_speed_urban:
            if speed_std > THRESHOLDS.road_std_urban:
                cond = "城市-国道"
            else:
                cond = "城市-快速路"
        elif avg_speed < THRESHOLDS.road_speed_highway:
            if speed_std > THRESHOLDS.road_std_mountain:
                cond = "山区"
            else:
                cond = "高速"
        else:
            cond = "高速"
        conditions.append(cond)

    df["road_cond"] = conditions

    # Group consecutive same-condition points into segments
    segments = []
    seg_start = 0
    for i in range(1, len(df)):
        if df["road_cond"].iloc[i] != df["road_cond"].iloc[0 + seg_start]:
            seg = df.iloc[seg_start:i]
            _add_road_segment(segments, seg)
            seg_start = i
    # Last segment
    seg = df.iloc[seg_start:]
    _add_road_segment(segments, seg)

    # Merge very short segments (< 30 seconds) into neighbors
    merged = _merge_short_segments(segments, df)
    # Merge adjacent segments of same road type
    merged = _merge_adjacent_same_type(merged)

    return merged


def _add_road_segment(segments: list, seg: pd.DataFrame):
    """Add a road condition segment to the list."""
    if len(seg) < 2:
        return
    duration = (
        seg["timestamp"].iloc[-1] - seg["timestamp"].iloc[0]
    ).total_seconds() / 3600
    distance = seg["mileage"].iloc[-1] - seg["mileage"].iloc[0]
    if distance < 0:
        distance = 0
    moving = seg[seg["speed"] > 1]
    avg_speed = moving["speed"].mean() if len(moving) > 0 else 0
    seg["h2_remain"].iloc[0]
    seg["h2_remain"].iloc[-1]
    # Use cumulative H2 from power integral
    h2_used = max(0, seg["h2_consumed_cum"].iloc[-1] - seg["h2_consumed_cum"].iloc[0])
    h2_per_100 = (h2_used / distance * 100) if distance > 0.1 else 0
    stack_power = seg["stack_power"].mean()
    # Load changes
    power_diff = seg["stack_power"].diff().abs()
    load_changes = int((power_diff > 20).sum())

    segments.append(
        {
            "road_type": seg["road_cond"].iloc[0],
            "color": ROAD_COLORS.get(seg["road_cond"].iloc[0], "#999"),
            "start_time": seg["timestamp"].iloc[0].strftime("%H:%M"),
            "end_time": seg["timestamp"].iloc[-1].strftime("%H:%M"),
            "duration_h": round(duration, 2),
            "distance_km": round(distance, 1),
            "avg_speed": round(avg_speed, 1),
            "h2_consumed_kg": round(h2_used, 2),
            "h2_per_100km": round(h2_per_100, 2),
            "stack_power_kw": round(stack_power, 1),
            "load_changes": load_changes,
        }
    )


def _merge_short_segments(segments: list, df: pd.DataFrame) -> list[dict]:
    """Merge segments shorter than 2 minutes into their neighbors."""
    if not segments:
        return segments
    merged = [segments[0]]
    for seg in segments[1:]:
        if seg["duration_h"] < 2 / 60 and merged:
            # Merge into previous
            prev = merged[-1]
            prev["duration_h"] = round(prev["duration_h"] + seg["duration_h"], 2)
            prev["distance_km"] = round(prev["distance_km"] + seg["distance_km"], 1)
            prev["h2_consumed_kg"] = round(
                prev["h2_consumed_kg"] + seg["h2_consumed_kg"], 2
            )
            prev["end_time"] = seg["end_time"]
            prev["load_changes"] += seg["load_changes"]
        else:
            merged.append(seg)
    return merged


def _merge_adjacent_same_type(segments: list[dict]) -> list[dict]:
    """Merge adjacent segments of the same road type."""
    if not segments:
        return segments
    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        if seg["road_type"] == prev["road_type"]:
            # Merge into previous
            total_dist = prev["distance_km"] + seg["distance_km"]
            prev["duration_h"] = round(prev["duration_h"] + seg["duration_h"], 2)
            prev["distance_km"] = round(total_dist, 1)
            prev["h2_consumed_kg"] = round(
                prev["h2_consumed_kg"] + seg["h2_consumed_kg"], 2
            )
            prev["end_time"] = seg["end_time"]
            prev["load_changes"] += seg["load_changes"]
            # Recalculate avg speed and h2_per_100km
            prev["avg_speed"] = round(
                total_dist / prev["duration_h"] if prev["duration_h"] > 0 else 0, 1
            )
            prev["h2_per_100km"] = round(
                prev["h2_consumed_kg"] / total_dist * 100 if total_dist > 0.1 else 0, 2
            )
            # Weighted average stack power
            prev_dur = prev["duration_h"]
            seg_dur = seg["duration_h"]
            prev["stack_power_kw"] = round(
                (
                    prev["stack_power_kw"] * (prev_dur - seg_dur)
                    + seg["stack_power_kw"] * seg_dur
                )
                / prev_dur
                if prev_dur > 0
                else 0,
                1,
            )
        else:
            merged.append(seg)
    return merged


# ---------------------------------------------------------------------------
# Power Mode Detection
# ---------------------------------------------------------------------------


def _detect_power_modes(trip: pd.DataFrame) -> list[dict]:
    """Detect power mode transitions within a trip."""
    df = trip.copy()

    modes = []
    for _, row in df.iterrows():
        speed = row["speed"]
        power = row["stack_power"]
        row["fc_work_state"]
        batt_cur = row["batt_cur"]

        if (
            speed < THRESHOLDS.power_stationary_speed
            and power > THRESHOLDS.power_idle_kw
        ):
            mode = "驻车发电"
        elif power > THRESHOLDS.power_drive_kw:
            mode = "燃电"
        elif speed < THRESHOLDS.power_stationary_speed:
            mode = "怠速"
        elif (
            batt_cur < THRESHOLDS.power_regen_batt_cur
            and power < THRESHOLDS.power_idle_kw
        ):
            mode = "能量回收"
        else:
            mode = "纯电"
        modes.append(mode)

    df["power_mode"] = modes

    # Group into segments
    segments = []
    seg_start = 0
    for i in range(1, len(df)):
        if df["power_mode"].iloc[i] != df["power_mode"].iloc[seg_start]:
            seg = df.iloc[seg_start:i]
            _add_mode_segment(segments, seg)
            seg_start = i
    seg = df.iloc[seg_start:]
    _add_mode_segment(segments, seg)

    # Merge adjacent same-mode segments
    return _merge_adjacent_same_mode(segments)


def _merge_adjacent_same_mode(segments: list[dict]) -> list[dict]:
    """Merge adjacent segments of the same power mode."""
    if not segments:
        return segments
    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        if seg["mode"] == prev["mode"]:
            total_min = prev["duration_min"] + seg["duration_min"]
            prev["duration_min"] = round(total_min, 1)
            prev["end_time"] = seg["end_time"]
            prev["soc_end"] = seg["soc_end"]
            prev["soc_change"] = round(seg["soc_end"] - prev["soc_start"], 1)
            prev["h2_end"] = seg["h2_end"]
            prev["avg_power_kw"] = round(
                (
                    prev["avg_power_kw"] * (total_min - seg["duration_min"])
                    + seg["avg_power_kw"] * seg["duration_min"]
                )
                / total_min
                if total_min > 0
                else 0,
                1,
            )
        else:
            merged.append(seg)
    return merged


def _add_mode_segment(segments: list, seg: pd.DataFrame):
    """Add a power mode segment."""
    if len(seg) < 2:
        return
    duration = (
        seg["timestamp"].iloc[-1] - seg["timestamp"].iloc[0]
    ).total_seconds() / 60
    if duration < 0.5:
        return
    mode = seg["power_mode"].iloc[0]
    soc_start = seg["batt_soc"].iloc[0]
    soc_end = seg["batt_soc"].iloc[-1]
    h2_start = seg["h2_remain_per"].iloc[0]
    h2_end = seg["h2_remain_per"].iloc[-1]
    avg_power = seg["stack_power"].mean()

    segments.append(
        {
            "mode": mode,
            "color": MODE_COLORS.get(mode, "#999"),
            "start_time": seg["timestamp"].iloc[0].strftime("%H:%M"),
            "end_time": seg["timestamp"].iloc[-1].strftime("%H:%M"),
            "duration_min": round(duration, 1),
            "soc_start": round(soc_start, 1),
            "soc_end": round(soc_end, 1),
            "soc_change": round(soc_end - soc_start, 1),
            "h2_start": round(h2_start, 1),
            "h2_end": round(h2_end, 1),
            "avg_power_kw": round(avg_power, 1),
        }
    )


# ---------------------------------------------------------------------------
# Load Change Event Detection
# ---------------------------------------------------------------------------


def _detect_load_changes(trip: pd.DataFrame) -> list[dict]:
    """Detect load change events where stack power changes > 20kW within 5 seconds."""
    df = trip.copy()
    # Calculate time difference in seconds
    df["dt"] = df["timestamp"].diff().dt.total_seconds().fillna(1)
    # Calculate power change rate
    df["dp"] = df["stack_power"].diff()
    # Normalize to 5-second rate
    df["dp_5s"] = df["dp"] / df["dt"] * 5

    events = []
    threshold = THRESHOLDS.load_change_rate_kw  # kW per 5s
    in_event = False
    event_start = None

    for i in range(1, len(df)):
        if abs(df["dp_5s"].iloc[i]) > threshold:
            if not in_event:
                event_start = i
                in_event = True
        else:
            if in_event and event_start is not None:
                # Record event
                seg = df.iloc[event_start:i]
                power_change = seg["stack_power"].iloc[-1] - seg["stack_power"].iloc[0]
                if (
                    abs(power_change) > THRESHOLDS.load_change_min_kw
                ):  # Only record significant changes
                    events.append(
                        {
                            "time": seg["timestamp"].iloc[0].strftime("%H:%M:%S"),
                            "timestamp_idx": event_start,
                            "power_before": round(seg["stack_power"].iloc[0], 1),
                            "power_after": round(seg["stack_power"].iloc[-1], 1),
                            "delta": round(power_change, 1),
                            "type": "增载" if power_change > 0 else "减载",
                        }
                    )
                in_event = False

    return events


# ---------------------------------------------------------------------------
# Trip Metrics
# ---------------------------------------------------------------------------


def _get_trip_weather_summary(trip: pd.DataFrame) -> str | None:
    """Quick weather summary string for overview (lightweight, single API call)."""
    try:
        from .weather import tag_trip_weather

        result = tag_trip_weather(trip)
        return result.get("weather_summary") if result else None
    except Exception:
        return None


def _compute_trip_overview(trip: pd.DataFrame, trip_id: int, vehicle_id: str) -> dict:
    """Compute summary metrics for a trip."""
    start_ts = trip["timestamp"].iloc[0]
    end_ts = trip["timestamp"].iloc[-1]
    duration_h = (end_ts - start_ts).total_seconds() / 3600
    distance = trip["mileage"].iloc[-1] - trip["mileage"].iloc[0]
    if distance < 0:
        distance = 0
    moving = trip[trip["speed"] > 1]
    avg_speed = moving["speed"].mean() if len(moving) > 0 else 0
    max_speed = trip["speed"].max()
    h2_start = trip["h2_remain"].iloc[0]
    h2_end = trip["h2_remain"].iloc[-1]
    # Use cumulative H2 consumption from power integral (most reliable)
    h2_consumed = max(
        0, trip["h2_consumed_cum"].iloc[-1] - trip["h2_consumed_cum"].iloc[0]
    )
    h2_per_100 = (h2_consumed / distance * 100) if distance > 0.1 else 0
    stack_power_avg = trip["stack_power"].mean()
    stack_power_max = trip["stack_power"].max()
    soc_start = trip["batt_soc"].iloc[0]
    soc_end = trip["batt_soc"].iloc[-1]

    # GPS bounds
    valid_gps = trip.dropna(subset=["gps_lon", "gps_lat"])
    if len(valid_gps) > 0:
        gps_start = [valid_gps["gps_lat"].iloc[0], valid_gps["gps_lon"].iloc[0]]
        gps_end = [valid_gps["gps_lat"].iloc[-1], valid_gps["gps_lon"].iloc[-1]]
    else:
        gps_start = gps_end = [0, 0]

    return {
        "trip_id": trip_id,
        "vehicle_id": vehicle_id,
        "date": start_ts.strftime("%Y-%m-%d"),
        "start_time": start_ts.strftime("%H:%M"),
        "end_time": end_ts.strftime("%H:%M"),
        "duration_h": round(duration_h, 2),
        "distance_km": round(distance, 1),
        "avg_speed": round(avg_speed, 1),
        "max_speed": round(max_speed, 1),
        "h2_consumed_kg": round(h2_consumed, 2),
        "h2_per_100km": round(h2_per_100, 2),
        "stack_power_avg": round(stack_power_avg, 1),
        "stack_power_max": round(stack_power_max, 1),
        "soc_start": round(soc_start, 1),
        "soc_end": round(soc_end, 1),
        "h2_start": round(h2_start, 1),
        "h2_end": round(h2_end, 1),
        "h2_percent_start": round(trip["h2_remain_per"].iloc[0], 1),
        "h2_percent_end": round(trip["h2_remain_per"].iloc[-1], 1),
        "gps_start": gps_start,
        "gps_end": gps_end,
        "weather_summary": _get_trip_weather_summary(trip),
    }


# ---------------------------------------------------------------------------
# Time Series Downsampling
# ---------------------------------------------------------------------------


def _downsample_timeseries(trip: pd.DataFrame, target_points: int = 800) -> dict:
    """Downsample time series data for chart rendering."""
    n = len(trip)
    if n <= target_points:
        step = 1
    else:
        step = n // target_points

    sampled = trip.iloc[::step]

    # Format timestamps as relative minutes from start
    start_ts = trip["timestamp"].iloc[0]
    rel_minutes = [(ts - start_ts).total_seconds() / 60 for ts in sampled["timestamp"]]

    return {
        "timestamps": [round(m, 1) for m in rel_minutes],
        "speed": [round(v, 1) for v in sampled["speed"]],
        "stack_power": [round(v, 1) for v in sampled["stack_power"]],
        "batt_soc": [round(v, 1) for v in sampled["batt_soc"]],
        "h2_remain": [round(v, 1) for v in sampled["h2_remain"]],
        "h2_percent": [round(v, 1) for v in sampled["h2_remain_per"]],
        "batt_cur": [round(v, 1) for v in sampled["batt_cur"]],
        "high_pressure": [round(v, 1) for v in sampled["high_pressure"]],
        "stack_temp_in": [round(v, 1) for v in sampled["stack_temp_in"]],
        "h2_consumed_cum": [round(v, 2) for v in sampled["h2_consumed_cum"]],
        # GPS 轨迹 (供地图按路况着色; 无效点为 null)
        "gps_lon": [
            None if pd.isna(v) else round(float(v), 5) for v in sampled["gps_lon"]
        ],
        "gps_lat": [
            None if pd.isna(v) else round(float(v), 5) for v in sampled["gps_lat"]
        ],
    }


# ---------------------------------------------------------------------------
# Driving Behavior Detection
# ---------------------------------------------------------------------------


def _detect_driving_behaviors(trip: pd.DataFrame) -> list[dict]:
    """Detect aggressive driving behaviors: rapid accel, hard brake, speeding."""
    behaviors = []
    df = trip.copy()

    # Compute acceleration (m/s^2) from speed (km/h)
    dt = df["timestamp"].diff().dt.total_seconds().fillna(0)
    dt = dt.clip(lower=0.1)  # avoid div by zero
    accel = (df["speed"].diff() / 3.6) / dt  # km/h -> m/s then accel
    accel = accel.fillna(0)

    # Rapid acceleration: > threshold sustained for at least 2s
    rapid_accel_mask = accel > THRESHOLDS.rapid_accel_ms2
    if rapid_accel_mask.any():
        # Group consecutive True values
        groups = []
        current_group = []
        for i, val in enumerate(rapid_accel_mask):
            if val:
                current_group.append(i)
            elif current_group:
                groups.append(current_group)
                current_group = []
        if current_group:
            groups.append(current_group)

        for grp in groups:
            if len(grp) < 2:
                continue
            idx = grp[len(grp) // 2]
            behaviors.append(
                {
                    "type": "急加速",
                    "time": df["timestamp"].iloc[idx].strftime("%H:%M:%S"),
                    "timestamp_idx": idx,
                    "severity": round(float(accel.iloc[idx]), 2),
                    "speed": round(float(df["speed"].iloc[idx]), 1),
                    "description": f"加速度 {accel.iloc[idx]:.1f} m/s², 车速 {df['speed'].iloc[idx]:.0f} km/h",
                }
            )

    # Hard braking: below threshold m/s^2
    hard_brake_mask = accel < THRESHOLDS.hard_brake_ms2
    if hard_brake_mask.any():
        groups = []
        current_group = []
        for i, val in enumerate(hard_brake_mask):
            if val:
                current_group.append(i)
            elif current_group:
                groups.append(current_group)
                current_group = []
        if current_group:
            groups.append(current_group)

        for grp in groups:
            if len(grp) < 2:
                continue
            idx = grp[len(grp) // 2]
            behaviors.append(
                {
                    "type": "急减速",
                    "time": df["timestamp"].iloc[idx].strftime("%H:%M:%S"),
                    "timestamp_idx": idx,
                    "severity": round(float(abs(accel.iloc[idx])), 2),
                    "speed": round(float(df["speed"].iloc[idx]), 1),
                    "description": f"减速度 {abs(accel.iloc[idx]):.1f} m/s², 车速 {df['speed'].iloc[idx]:.0f} km/h",
                }
            )

    # Speeding: speed above threshold (typical highway limit for heavy trucks)
    speeding_mask = df["speed"] > THRESHOLDS.speeding_kmh
    if speeding_mask.any():
        groups = []
        current_group = []
        for i, val in enumerate(speeding_mask):
            if val:
                current_group.append(i)
            elif current_group:
                groups.append(current_group)
                current_group = []
        if current_group:
            groups.append(current_group)

        for grp in groups:
            if len(grp) < 5:
                continue
            max_idx = grp[np.argmax(df["speed"].iloc[grp].values)]
            behaviors.append(
                {
                    "type": "超速",
                    "time": df["timestamp"].iloc[max_idx].strftime("%H:%M:%S"),
                    "timestamp_idx": int(max_idx),
                    "severity": round(float(df["speed"].iloc[max_idx]), 1),
                    "speed": round(float(df["speed"].iloc[max_idx]), 1),
                    "description": f"最高车速 {df['speed'].iloc[max_idx]:.0f} km/h, 持续 {len(grp)} 个采样点",
                }
            )

    # Sort by timestamp
    behaviors.sort(key=lambda x: x["timestamp_idx"])

    # Limit to top 50 to avoid overwhelming
    return behaviors[:50]


# ---------------------------------------------------------------------------
# Anomaly Hydrogen Consumption Detection with Reason Attribution
# ---------------------------------------------------------------------------


def _detect_h2_anomalies(trip: pd.DataFrame, road_segments: list[dict]) -> list[dict]:
    """Detect anomalous hydrogen consumption segments and attribute causes."""
    if not road_segments:
        return []

    # Calculate trip-level average h2_per_100km
    trip_h2_values = [
        s["h2_per_100km"]
        for s in road_segments
        if s["h2_per_100km"] and s["h2_per_100km"] > 0
    ]
    if not trip_h2_values:
        return []

    trip_avg = np.mean(trip_h2_values)
    trip_std = np.std(trip_h2_values) if len(trip_h2_values) > 1 else trip_avg * 0.3
    threshold = (
        trip_avg + THRESHOLDS.anomaly_std_multiplier * trip_std
    )  # Flag segments above avg + multiplier*std

    anomalies = []
    df = trip.copy()
    df["timestamp"].iloc[0]

    for seg in road_segments:
        h2 = seg.get("h2_per_100km", 0)
        if not h2 or h2 <= 0:
            continue

        if h2 > threshold:
            # Attribute reasons
            reasons = []

            # 1. High load changes
            if seg.get("load_changes", 0) > THRESHOLDS.anomaly_high_load_changes:
                reasons.append(
                    {
                        "factor": "变载频繁",
                        "detail": f"该路段变载事件 {seg['load_changes']} 次, 频繁功率波动导致氢耗增加",
                        "impact": "high",
                    }
                )

            # 2. Low average speed (congestion)
            if (
                seg.get("avg_speed", 0) > 0
                and seg["avg_speed"] < THRESHOLDS.anomaly_low_speed_kmh
            ):
                reasons.append(
                    {
                        "factor": "低速行驶",
                        "detail": f"均速仅 {seg['avg_speed']:.1f} km/h, 频繁启停导致效率下降",
                        "impact": "medium",
                    }
                )

            # 3. High stack power
            if seg.get("stack_power_kw", 0) > THRESHOLDS.anomaly_high_power_kw:
                reasons.append(
                    {
                        "factor": "高功率需求",
                        "detail": f"电堆平均功率 {seg['stack_power_kw']:.0f} kW, 大功率输出导致氢耗升高",
                        "impact": "high",
                    }
                )

            # 4. Road type context
            road_type = seg.get("road_type", "")
            if road_type == "山区":
                reasons.append(
                    {
                        "factor": "山区爬坡",
                        "detail": "山区路况坡度大, 爬坡需更高功率输出",
                        "impact": "high",
                    }
                )
            elif road_type == "场区-装卸":
                reasons.append(
                    {
                        "factor": "场区作业",
                        "detail": "场区内频繁启停和低速作业, 燃料电池效率低",
                        "impact": "medium",
                    }
                )
            elif road_type == "怠速":
                reasons.append(
                    {
                        "factor": "长时间怠速",
                        "detail": "怠速状态下燃料电池仍维持最低功率运行, 里程几乎无增加但氢气持续消耗",
                        "impact": "high",
                    }
                )

            # 5. Check if this segment has high speed variability
            try:
                seg_start = datetime.strptime(f"{seg['start_time']}", "%H:%M")
                seg_end = datetime.strptime(f"{seg['end_time']}", "%H:%M")
                # Handle overnight trips
                if seg_end < seg_start:
                    seg_end = seg_end.replace(hour=seg_end.hour + 24)

                # Find data in this segment
                trip_date = df["timestamp"].iloc[0].strftime("%Y-%m-%d")
                seg_start_dt = datetime.strptime(
                    f"{trip_date} {seg['start_time']}", "%Y-%m-%d %H:%M"
                )
                seg_end_dt = datetime.strptime(
                    f"{trip_date} {seg['end_time']}", "%Y-%m-%d %H:%M"
                )
                if seg_end_dt < seg_start_dt:
                    seg_end_dt = seg_end_dt.replace(day=seg_end_dt.day + 1)

                mask = (df["timestamp"] >= seg_start_dt) & (
                    df["timestamp"] <= seg_end_dt
                )
                seg_data = df[mask]

                if len(seg_data) > 5:
                    speed_std = seg_data["speed"].std()
                    if speed_std > 20:
                        reasons.append(
                            {
                                "factor": "速度波动大",
                                "detail": f"该路段车速标准差 {speed_std:.1f} km/h, 速度频繁波动导致额外氢耗",
                                "impact": "medium",
                            }
                        )
            except Exception:
                pass

            if not reasons:
                reasons.append(
                    {
                        "factor": "综合因素",
                        "detail": "该路段氢耗偏高, 建议关注驾驶行为和路况条件",
                        "impact": "low",
                    }
                )

            # Compute deviation
            deviation_pct = ((h2 - trip_avg) / trip_avg * 100) if trip_avg > 0 else 0

            anomalies.append(
                {
                    "segment_time": f"{seg['start_time']}~{seg['end_time']}",
                    "road_type": seg["road_type"],
                    "h2_per_100km": round(h2, 2),
                    "trip_avg": round(trip_avg, 2),
                    "deviation_pct": round(deviation_pct, 1),
                    "reasons": reasons,
                    "suggestion": _generate_suggestion(reasons, seg),
                }
            )

    return anomalies


def _generate_suggestion(reasons: list[dict], seg: dict) -> str:
    """Generate optimization suggestion based on anomaly reasons."""
    high_impact = [r for r in reasons if r["impact"] == "high"]
    suggestions = []

    for r in high_impact:
        if r["factor"] == "变载频繁":
            suggestions.append("建议保持匀速行驶, 减少急加速急减速, 降低功率波动频率")
        elif r["factor"] == "高功率需求":
            suggestions.append("建议控制车速在经济区间(60-70km/h), 降低电堆功率输出")
        elif r["factor"] == "山区爬坡":
            suggestions.append("山区路段建议提前加速冲坡, 避免坡中大功率持续输出")
        elif r["factor"] == "长时间怠速":
            suggestions.append("建议长时间停车时关闭燃料电池, 减少怠速氢耗")

    if not suggestions:
        suggestions.append("建议关注该路段驾驶行为, 保持平稳驾驶")

    return "; ".join(suggestions)


# ---------------------------------------------------------------------------
# Factor Analysis (Correlation)
# ---------------------------------------------------------------------------


def _compute_factor_analysis(trip: pd.DataFrame) -> dict:
    """Analyze factors influencing hydrogen consumption."""
    df = trip.copy()

    # Compute per-minute hydrogen consumption rate
    # H2 LHV = 33.3 kWh/kg (NIST), PEM FC efficiency = 50% (DOE) — see module docstring
    dt = df["timestamp"].diff().dt.total_seconds().fillna(0)
    dt = dt.clip(lower=0.1, upper=300)
    (
        df["stack_power"] * dt / 3600 / (33.3 * 0.50)
    )  # kg per interval; see module docstring for sources

    # Compute per-minute aggregates
    df["minute"] = df["timestamp"].dt.floor("min")
    minute_agg = (
        df.groupby("minute")
        .agg(
            speed_mean=("speed", "mean"),
            speed_std=("speed", "std"),
            power_mean=("stack_power", "mean"),
            batt_cur_mean=("batt_cur", "mean"),
            soc=("batt_soc", "mean"),
            h2_rate=("stack_power", "mean"),  # Use power as proxy for h2 rate
        )
        .fillna(0)
    )

    # Only analyze minutes with actual movement
    moving = minute_agg[minute_agg["speed_mean"] > 1]
    if len(moving) < 10:
        return {
            "factors": [],
            "summary": "数据点不足, 无法进行因子分析",
        }

    # Correlation analysis - correlate each factor with power (proxy for H2 rate)
    factors = []
    correlations = {
        "车速": "speed_mean",
        "速度波动": "speed_std",
        "电池电流": "batt_cur_mean",
    }

    for factor_name, col1 in correlations.items():
        if col1 in moving.columns and "h2_rate" in moving.columns:
            corr = moving[col1].corr(moving["h2_rate"])
            if np.isnan(corr):
                corr = 0
            factors.append(
                {
                    "factor": factor_name,
                    "correlation": round(float(corr), 3),
                    "strength": _corr_strength(corr),
                    "direction": "正相关" if corr > 0 else "负相关",
                }
            )

    # Sort by absolute correlation
    factors.sort(key=lambda x: abs(x["correlation"]), reverse=True)

    # Generate summary
    top_factor = factors[0] if factors else None
    if top_factor:
        summary = f"氢耗与{top_factor['factor']}相关性最强 (r={top_factor['correlation']:.2f}), "
        summary += f"呈{top_factor['direction']}; "
        if abs(top_factor["correlation"]) > THRESHOLDS.factor_corr_strong:
            summary += "影响显著, 是优化重点方向"
        elif abs(top_factor["correlation"]) > THRESHOLDS.factor_corr_moderate:
            summary += "影响中等, 值得关注"
        else:
            summary += "影响较弱"
    else:
        summary = "无法计算因子相关性"

    return {
        "factors": factors,
        "summary": summary,
        "minute_count": len(moving),
    }


def _corr_strength(corr: float) -> str:
    """Describe correlation strength."""
    abs_c = abs(corr)
    if abs_c > THRESHOLDS.factor_corr_strong:
        return "强"
    elif abs_c > THRESHOLDS.factor_corr_moderate:
        return "中等"
    elif abs_c > THRESHOLDS.factor_corr_weak:
        return "弱"
    return "极弱"


# ---------------------------------------------------------------------------
# Trip Benchmarking
# ---------------------------------------------------------------------------


def _benchmark_trips(
    vehicle_id: str,
    all_trips: list[pd.DataFrame],
) -> dict:
    """Compare trips for benchmarking hydrogen consumption."""
    if not all_trips:
        return {"comparisons": [], "summary": "无行程数据"}

    trip_stats = []
    for i, trip in enumerate(all_trips):
        if len(trip) == 0:
            continue
        distance = trip["mileage"].iloc[-1] - trip["mileage"].iloc[0]
        if distance < 0.5:
            continue
        h2 = max(0, trip["h2_consumed_cum"].iloc[-1] - trip["h2_consumed_cum"].iloc[0])
        h2_per_100 = h2 / distance * 100 if distance > 0 else 0

        trip_stats.append(
            {
                "trip_id": i,
                "date": trip["timestamp"].iloc[0].strftime("%m-%d"),
                "start_time": trip["timestamp"].iloc[0].strftime("%H:%M"),
                "distance_km": round(distance, 1),
                "duration_h": round(len(trip) / 3600, 2),
                "h2_consumed_kg": round(h2, 2),
                "h2_per_100km": round(h2_per_100, 2),
                "avg_speed": round(distance / (len(trip) / 3600), 1)
                if len(trip) > 0
                else 0,
                "max_power": round(float(trip["stack_power"].max()), 1),
            }
        )

    if not trip_stats:
        return {"comparisons": [], "summary": "无有效行程数据"}

    # Calculate statistics
    h2_values = [t["h2_per_100km"] for t in trip_stats]
    avg_h2 = np.mean(h2_values)
    best_trip = min(trip_stats, key=lambda x: x["h2_per_100km"])
    worst_trip = max(trip_stats, key=lambda x: x["h2_per_100km"])

    # Group by distance range for similar-trip comparison
    for t in trip_stats:
        t["vs_avg"] = (
            round((t["h2_per_100km"] - avg_h2) / avg_h2 * 100, 1) if avg_h2 > 0 else 0
        )
        t["rating"] = _rate_h2(t["h2_per_100km"], avg_h2)

    return {
        "comparisons": trip_stats,
        "summary": f"共 {len(trip_stats)} 个行程, 平均百公里氢耗 {avg_h2:.2f} kg, "
        f"最优 {best_trip['h2_per_100km']:.2f} kg (行程{best_trip['trip_id']}), "
        f"最差 {worst_trip['h2_per_100km']:.2f} kg (行程{worst_trip['trip_id']})",
        "avg_h2_per_100km": round(float(avg_h2), 2),
        "best_trip_id": best_trip["trip_id"],
        "worst_trip_id": worst_trip["trip_id"],
    }


def _rate_h2(h2: float, avg: float) -> str:
    """Rate hydrogen consumption vs average."""
    if avg <= 0:
        return "—"
    ratio = h2 / avg
    if ratio < 0.85:
        return "优秀"
    elif ratio < 1.0:
        return "良好"
    elif ratio < 1.15:
        return "偏高"
    return "异常"


# ---------------------------------------------------------------------------
# Auto Analysis Report Generation
# ---------------------------------------------------------------------------


def _generate_analysis_report(
    vehicle_id: str,
    trip_id: int,
    detail: dict,
    benchmark: dict,
) -> dict:
    """Generate structured analysis report text."""
    ov = detail["overview"]
    anomalies = detail.get("anomalies", [])
    behaviors = detail.get("driving_behaviors", [])
    factors = detail.get("factor_analysis", {})
    road_segs = detail.get("road_segments", [])

    sections = []

    # Section 1: Trip Summary
    sections.append(
        {
            "title": "行程概览",
            "content": (
                f"车辆 {vehicle_id} 行程 {trip_id}: "
                f"{ov['start_time']} ~ {ov['end_time']}, "
                f"总里程 {ov['distance_km']:.1f} km, "
                f"全程耗时 {ov['duration_h']:.1f} 小时, "
                f"均速 {ov['avg_speed']:.1f} km/h, "
                f"总氢耗 {ov['h2_consumed_kg']:.2f} kg, "
                f"百公里氢耗 {ov['h2_per_100km']:.2f} kg."
            ),
        }
    )

    # Section 2: Road Condition Distribution
    if road_segs:
        road_summary = {}
        for seg in road_segs:
            rt = seg["road_type"]
            if rt not in road_summary:
                road_summary[rt] = {"distance": 0, "h2": 0, "count": 0}
            road_summary[rt]["distance"] += seg.get("distance_km", 0)
            road_summary[rt]["h2"] += seg.get("h2_consumed_kg", 0)
            road_summary[rt]["count"] += 1

        road_text = "路况分布: "
        parts = []
        for rt, stats in sorted(road_summary.items(), key=lambda x: -x[1]["distance"]):
            parts.append(f"{rt} {stats['distance']:.1f}km ({stats['count']}段)")
        road_text += ", ".join(parts)
        sections.append({"title": "路况分布", "content": road_text})

    # Section 3: Anomaly Analysis
    if anomalies:
        anomaly_text = f"检测到 {len(anomalies)} 个异常氢耗路段:\n"
        for a in anomalies:
            anomaly_text += (
                f"  - {a['segment_time']} ({a['road_type']}): "
                f"百公里氢耗 {a['h2_per_100km']} kg, "
                f"偏离均值 +{a['deviation_pct']}%. "
                f"原因: {', '.join(r['factor'] for r in a['reasons'])}. "
                f"建议: {a['suggestion']}\n"
            )
        sections.append({"title": "异常氢耗检测", "content": anomaly_text.strip()})
    else:
        sections.append(
            {"title": "异常氢耗检测", "content": "未检测到明显异常氢耗路段"}
        )

    # Section 4: Factor Analysis
    if factors.get("factors"):
        factor_text = factors.get("summary", "")
        for f in factors["factors"][:3]:
            factor_text += f"\n  - {f['factor']}: 相关系数 {f['correlation']:.2f} ({f['strength']} {f['direction']})"
        sections.append({"title": "氢耗影响因子分析", "content": factor_text})

    # Section 5: Driving Behavior
    if behaviors:
        behavior_counts = {}
        for b in behaviors:
            behavior_counts[b["type"]] = behavior_counts.get(b["type"], 0) + 1
        behavior_text = f"驾驶行为标签: 共检测到 {len(behaviors)} 个事件 - "
        behavior_text += ", ".join(f"{k} {v}次" for k, v in behavior_counts.items())
        sections.append({"title": "驾驶行为分析", "content": behavior_text})
    else:
        sections.append(
            {"title": "驾驶行为分析", "content": "驾驶行为平稳, 未检测到异常驾驶事件"}
        )

    # Section 6: Benchmarking
    if benchmark.get("comparisons"):
        bench_text = benchmark.get("summary", "")
        sections.append({"title": "同类行程对标", "content": bench_text})

    # Section 7: Recommendations
    recommendations = []
    if anomalies:
        recommendations.append("重点关注异常氢耗路段, 优化驾驶行为和路线选择")
    if behaviors:
        rec_types = set(b["type"] for b in behaviors)
        if "急加速" in rec_types:
            recommendations.append("减少急加速, 保持平稳油门控制")
        if "急减速" in rec_types:
            recommendations.append("提前预判路况, 减少紧急制动")
        if "超速" in rec_types:
            recommendations.append("控制车速在法规限速内, 超速行驶显著增加氢耗")
    if factors.get("factors"):
        top = factors["factors"][0]
        if abs(top["correlation"]) > 0.5:
            recommendations.append(
                f"重点优化{top['factor']}: 与氢耗相关性最强(r={top['correlation']:.2f})"
            )
    if not recommendations:
        recommendations.append("整体驾驶表现良好, 建议保持当前驾驶习惯")

    sections.append(
        {
            "title": "优化建议",
            "content": "\n".join(
                f"  {i + 1}. {r}" for i, r in enumerate(recommendations)
            ),
        }
    )

    return {
        "vehicle_id": vehicle_id,
        "trip_id": trip_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sections": sections,
        "recommendations": recommendations,
    }


# ---------------------------------------------------------------------------
# Main Processor Class
# ---------------------------------------------------------------------------


class DataProcessor:
    """Main data processor with lazy loading and caching."""

    def __init__(self):
        self._loaded = False
        self._vehicle_data: dict[str, pd.DataFrame] = {}
        self._trips: dict[str, list[pd.DataFrame]] = {}
        self._trip_details: dict[tuple[str, int], dict] = {}

    def _ensure_loaded(self):
        """Lazy load data on first access."""
        if self._loaded:
            return

        cache_file = CACHE_DIR / "processed_data.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, "rb") as f:
                    cached = pickle.load(f)
                self._vehicle_data = cached["vehicle_data"]
                self._trips = cached["trips"]
                self._loaded = True
                print(
                    f"[DataProcessor] Loaded from cache: {sum(len(v) for v in self._trips.values())} trips"
                )
                return
            except Exception as e:
                print(f"[DataProcessor] Cache load failed: {e}, reloading...")

        self._load_and_process()
        self._loaded = True

    def _load_and_process(self):
        """Load CSV files and process trips."""
        for vid, info in VEHICLE_FILES.items():
            filepath = DATA_DIR / info["file"]
            if not filepath.exists():
                print(f"[DataProcessor] File not found: {filepath}")
                continue

            print(f"[DataProcessor] Loading {vid} ({info['label']})...")
            df = _load_and_convert(str(filepath), vid)
            self._vehicle_data[vid] = df

            trips = _segment_trips(df)
            self._trips[vid] = trips
            print(f"[DataProcessor] {vid}: {len(df)} rows, {len(trips)} trips")

        # Save to cache
        try:
            cache_file = CACHE_DIR / "processed_data.pkl"
            with open(cache_file, "wb") as f:
                pickle.dump(
                    {
                        "vehicle_data": self._vehicle_data,
                        "trips": self._trips,
                    },
                    f,
                )
            print(f"[DataProcessor] Cached to {cache_file}")
        except Exception as e:
            print(f"[DataProcessor] Cache save failed: {e}")

    def get_vehicles(self) -> list[dict]:
        """Return list of available vehicles with summary stats."""
        self._ensure_loaded()
        vehicles = []
        for vid, info in VEHICLE_FILES.items():
            if vid not in self._vehicle_data:
                continue
            df = self._vehicle_data[vid]
            trips = self._trips.get(vid, [])
            total_distance = sum(
                t["mileage"].iloc[-1] - t["mileage"].iloc[0]
                for t in trips
                if len(t) > 0
            )
            total_h2 = sum(
                max(0, t["h2_consumed_cum"].iloc[-1] - t["h2_consumed_cum"].iloc[0])
                for t in trips
                if len(t) > 0
            )
            vehicles.append(
                {
                    "vehicle_id": vid,
                    "label": info["label"],
                    "region": info["region"],
                    "total_rows": len(df),
                    "total_trips": len(trips),
                    "total_distance_km": round(total_distance, 1),
                    "total_h2_consumed_kg": round(total_h2, 2),
                    "date_range": f"{df['timestamp'].iloc[0].strftime('%m-%d')} ~ {df['timestamp'].iloc[-1].strftime('%m-%d')}",
                    "avg_h2_per_100km": round(total_h2 / total_distance * 100, 2)
                    if total_distance > 0
                    else 0,
                }
            )
        return vehicles

    def get_trips(self, vehicle_id: str) -> list[dict]:
        """Return list of trips for a vehicle."""
        self._ensure_loaded()
        trips = self._trips.get(vehicle_id, [])
        result = []
        for i, trip in enumerate(trips):
            overview = _compute_trip_overview(trip, i, vehicle_id)
            result.append(overview)
        return result

    def get_trip_detail(self, vehicle_id: str, trip_id: int) -> dict | None:
        """Return detailed analysis for a specific trip."""
        self._ensure_loaded()

        cache_key = (vehicle_id, trip_id)
        if cache_key in self._trip_details:
            return self._trip_details[cache_key]

        trips = self._trips.get(vehicle_id, [])
        if trip_id < 0 or trip_id >= len(trips):
            return None

        trip = trips[trip_id]
        overview = _compute_trip_overview(trip, trip_id, vehicle_id)
        # 多维证据矩阵路况识别 v2 (替代旧版速度均值+波动率双指标法)
        road_segments = classify_road_conditions_v2(trip)
        road_methodology = explain_methodology()
        power_modes = _detect_power_modes(trip)
        power_modes = _merge_adjacent_same_mode(power_modes)
        load_changes = _detect_load_changes(trip)
        time_series = _downsample_timeseries(trip)

        # Build road condition background bands for charts
        road_bands = []
        ts_start = trip["timestamp"].iloc[0]
        for seg in road_segments:
            # v2 段自带 ISO 起止时间 (支持跨午夜行程)
            start_dt = pd.Timestamp(seg["start_iso"])
            end_dt = pd.Timestamp(seg["end_iso"])
            start_min = (start_dt - ts_start).total_seconds() / 60
            end_min = (end_dt - ts_start).total_seconds() / 60
            road_bands.append(
                {
                    "start_min": round(start_min, 1),
                    "end_min": round(end_min, 1),
                    "road_type": seg["road_type"],
                    "color": seg["color"],
                    "confidence": seg.get("confidence", 1.0),
                }
            )

        # Build power mode bands
        mode_bands = []
        for seg in power_modes:
            start_dt = datetime.strptime(
                f"{overview['date']} {seg['start_time']}", "%Y-%m-%d %H:%M"
            )
            end_dt = datetime.strptime(
                f"{overview['date']} {seg['end_time']}", "%Y-%m-%d %H:%M"
            )
            start_min = (start_dt - ts_start).total_seconds() / 60
            end_min = (end_dt - ts_start).total_seconds() / 60
            mode_bands.append(
                {
                    "start_min": round(start_min, 1),
                    "end_min": round(end_min, 1),
                    "mode": seg["mode"],
                    "color": seg["color"],
                }
            )

        # Driving behaviors
        driving_behaviors = _detect_driving_behaviors(trip)

        # Anomaly detection
        anomalies = _detect_h2_anomalies(trip, road_segments)

        # Factor analysis
        factor_analysis = _compute_factor_analysis(trip)

        # Weather tags (Open-Meteo Archive API)
        weather_tags = None
        try:
            from .weather import tag_trip_weather

            weather_tags = tag_trip_weather(trip)
        except Exception:
            pass

        detail = {
            "overview": overview,
            "road_segments": road_segments,
            "road_methodology": road_methodology,
            "power_modes": power_modes,
            "load_changes": load_changes,
            "load_change_count": len(load_changes),
            "time_series": time_series,
            "road_bands": road_bands,
            "mode_bands": mode_bands,
            "driving_behaviors": driving_behaviors,
            "anomalies": anomalies,
            "factor_analysis": factor_analysis,
            "weather": weather_tags,
        }

        self._trip_details[cache_key] = detail
        return detail

    def get_benchmark(self, vehicle_id: str) -> dict:
        """Return trip benchmarking for a vehicle."""
        self._ensure_loaded()
        trips = self._trips.get(vehicle_id, [])
        return _benchmark_trips(vehicle_id, trips)

    def get_report(self, vehicle_id: str, trip_id: int) -> dict | None:
        """Generate auto analysis report for a trip."""
        self._ensure_loaded()
        detail = self.get_trip_detail(vehicle_id, trip_id)
        if detail is None:
            return None
        benchmark = self.get_benchmark(vehicle_id)
        return _generate_analysis_report(vehicle_id, trip_id, detail, benchmark)

    def process_uploaded_csv(self, filepath: str, vehicle_id: str = "UPLOADED") -> dict:
        """Process an uploaded CSV file and return basic analysis."""
        df = _load_and_convert(filepath, vehicle_id)
        trips = _segment_trips(df)
        if not trips:
            return {"error": "No valid trips detected in uploaded data"}

        self._vehicle_data[vehicle_id] = df
        self._trips[vehicle_id] = trips
        self._trip_details.clear()

        vehicles = []
        for vid in self._vehicle_data:
            v_trips = self._trips.get(vid, [])
            total_distance = sum(
                t["mileage"].iloc[-1] - t["mileage"].iloc[0]
                for t in v_trips
                if len(t) > 0
            )
            total_h2 = sum(
                max(0, t["h2_consumed_cum"].iloc[-1] - t["h2_consumed_cum"].iloc[0])
                for t in v_trips
                if len(t) > 0
            )
            vehicles.append(
                {
                    "vehicle_id": vid,
                    "label": "uploaded"
                    if vid == "UPLOADED"
                    else VEHICLE_FILES.get(vid, {}).get("label", vid),
                    "region": "uploaded"
                    if vid == "UPLOADED"
                    else VEHICLE_FILES.get(vid, {}).get("region", ""),
                    "total_rows": len(self._vehicle_data[vid]),
                    "total_trips": len(v_trips),
                    "total_distance_km": round(total_distance, 1),
                    "total_h2_consumed_kg": round(total_h2, 2),
                    "date_range": f"{df['timestamp'].iloc[0].strftime('%m-%d')} ~ {df['timestamp'].iloc[-1].strftime('%m-%d')}",
                    "avg_h2_per_100km": round(total_h2 / total_distance * 100, 2)
                    if total_distance > 0
                    else 0,
                }
            )

        return {
            "status": "ok",
            "vehicle_id": vehicle_id,
            "trips_detected": len(trips),
            "vehicles": vehicles,
        }

    def calibrate_thresholds(self) -> dict:
        """Run data-driven threshold calibration and return report."""
        self._ensure_loaded()
        from .thresholds import calibrate_from_data

        result = calibrate_from_data(self._vehicle_data, self._trips)

        # Clear trip detail cache so new thresholds take effect
        self._trip_details.clear()

        return result

    def get_thresholds(self) -> dict:
        """Return current threshold values."""
        from .thresholds import THRESHOLDS

        return THRESHOLDS.to_dict()

    def apply_calibrated_thresholds(self, calibrated: dict):
        """Apply calibrated threshold values."""
        from .thresholds import THRESHOLDS

        THRESHOLDS.update(calibrated)
        self._trip_details.clear()


# Singleton instance
_processor: DataProcessor | None = None


def get_processor() -> DataProcessor:
    """Get the singleton data processor instance."""
    global _processor
    if _processor is None:
        _processor = DataProcessor()
    return _processor
