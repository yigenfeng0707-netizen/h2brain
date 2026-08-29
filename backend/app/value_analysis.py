"""H2Brain - Value Quantification Module

Calculates economic benefits and emission reduction based on real fleet data.
Compares hydrogen fuel cell trucks against equivalent diesel trucks.
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger("h2brain.value_analysis")

# ── Industry parameters (2026 China heavy-duty truck averages) ──

# Hydrogen
H2_PRICE_YUAN_PER_KG = 35.0  # 35 yuan/kg (industrial average)
H2_CO2_KG_PER_KG_GREEN = 0.0  # Green H2: near-zero well-to-wheel
H2_CO2_KG_PER_KG_GRAY = 10.0  # Gray H2 from SMR: ~10 kg CO2/kg

# Diesel (equivalent 49t heavy-duty truck)
DIESEL_PRICE_YUAN_PER_L = 7.5  # 7.5 yuan/L
DIESEL_CONSUMPTION_L_PER_100KM = 30.0  # 30 L/100km for 49t truck
DIESEL_CO2_KG_PER_L = 2.63  # 2.63 kg CO2 per liter diesel

# Maintenance
H2_MAINTENANCE_YUAN_PER_KM = 0.35  # Lower: fewer moving parts
DIESEL_MAINTENANCE_YUAN_PER_KM = 0.55  # Higher: engine oil, filters, DPF

# Vehicle lifecycle
ANNUAL_MILEAGE_KM = 100_000  # 100k km/year per truck
VEHICLE_LIFETIME_YEARS = 8

# Premium of H2 truck over diesel (purchase price difference)
H2_TRUCK_PREMIUM_YUAN = 300_000  # ~30万 premium


def _sensitivity_analysis(
    total_km: float,
    total_h2_kg: float,
    vehicle_count: int,
) -> dict[str, Any]:
    """敏感性分析：固定实测单位经济性，单变量扫描行业参数。

    方法说明（可解释性）：
    - 每公里氢耗 = total_h2_kg / total_km（实测值，不随情景变化）
    - 每公里柴油等效油耗 = 30 L/100km（行业参数）
    - 年度节省 = (柴油燃料+柴油维保) - (氢燃料+氢维保)，按扫描情景重算
    - 回收期 = 购车溢价总额 / 年度节省；生命周期净节省 = 年度节省 × 8 - 溢价
    - 每次只动一个变量（氢价/柴油价/年里程），其余取基准值
    """
    total_premium = H2_TRUCK_PREMIUM_YUAN * vehicle_count
    h2_kg_per_km = total_h2_kg / total_km if total_km > 0 else 0
    diesel_l_per_km = DIESEL_CONSUMPTION_L_PER_100KM / 100

    def _metrics(annual_km: float, h2_price: float, diesel_price: float) -> dict:
        h2_fuel = h2_kg_per_km * annual_km * h2_price
        diesel_fuel = diesel_l_per_km * annual_km * diesel_price
        h2_maint = annual_km * H2_MAINTENANCE_YUAN_PER_KM
        diesel_maint = annual_km * DIESEL_MAINTENANCE_YUAN_PER_KM
        annual_saved = (diesel_fuel + diesel_maint) - (h2_fuel + h2_maint)
        payback = total_premium / annual_saved if annual_saved > 0 else None
        return {
            "annual_cost_saved_yuan": round(annual_saved, 0),
            "payback_years": round(payback, 1) if payback is not None else None,
            "lifetime_savings_yuan": round(
                annual_saved * VEHICLE_LIFETIME_YEARS - total_premium, 0
            ),
        }

    def _scan(name: str, unit: str, values: list[float], kind: str) -> dict:
        rows = []
        for v in values:
            if kind == "h2_price":
                m = _metrics(
                    ANNUAL_MILEAGE_KM * vehicle_count, v, DIESEL_PRICE_YUAN_PER_L
                )
            elif kind == "diesel_price":
                m = _metrics(
                    ANNUAL_MILEAGE_KM * vehicle_count, H2_PRICE_YUAN_PER_KG, v
                )
            else:  # annual mileage per vehicle
                m = _metrics(v * vehicle_count, H2_PRICE_YUAN_PER_KG, DIESEL_PRICE_YUAN_PER_L)
            rows.append({"value": v, **m})
        return {"variable": name, "unit": unit, "rows": rows}

    return {
        "method": (
            f"固定实测单位经济性（百公里氢耗 {h2_kg_per_km * 100:.2f} kg/100km、"
            f"柴油 {DIESEL_CONSUMPTION_L_PER_100KM:.0f} L/100km），"
            "单变量扫描行业参数，其余参数取基准值（氢价 35 元/kg、柴油 7.5 元/L、"
            "年里程 10 万 km/辆、寿命 8 年、购车溢价 30 万/辆）"
        ),
        "h2_price": _scan("氢价", "元/kg", [25, 27.5, 30, 32.5, 35, 37.5, 40], "h2_price"),
        "diesel_price": _scan("柴油价", "元/L", [6.0, 6.5, 7.0, 7.5, 8.0, 8.5], "diesel_price"),
        "annual_mileage": _scan(
            "单车辆年里程", "万 km", [60_000, 80_000, 100_000, 120_000, 150_000], "mileage"
        ),
    }


def compute_value_analysis(
    vehicles: list[dict[str, Any]],
    trips: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute economic and environmental value from real fleet data.

    Args:
        vehicles: List of vehicle summary dicts (from DataProcessor.get_vehicles)
        trips: List of trip dicts (from DataProcessor.get_trips)

    Returns:
        Dict with economic, emission, and ROI analysis.
    """
    total_km = sum(v.get("total_distance_km", 0) for v in vehicles)
    total_h2_kg = sum(v.get("total_h2_consumed_kg", 0) for v in vehicles)
    vehicle_count = len(vehicles)

    if total_km <= 0:
        return {"error": "No distance data available"}

    # ── Hydrogen cost ──
    h2_cost = total_h2_kg * H2_PRICE_YUAN_PER_KG
    h2_cost_per_100km = (
        (total_h2_kg / total_km * 100) * H2_PRICE_YUAN_PER_KG if total_km > 0 else 0
    )
    avg_h2_per_100km = total_h2_kg / total_km * 100 if total_km > 0 else 0

    # ── Equivalent diesel cost ──
    diesel_needed_l = total_km / 100 * DIESEL_CONSUMPTION_L_PER_100KM
    diesel_cost = diesel_needed_l * DIESEL_PRICE_YUAN_PER_L
    diesel_cost_per_100km = DIESEL_CONSUMPTION_L_PER_100KM * DIESEL_PRICE_YUAN_PER_L

    # ── Maintenance cost ──
    h2_maintenance = total_km * H2_MAINTENANCE_YUAN_PER_KM
    diesel_maintenance = total_km * DIESEL_MAINTENANCE_YUAN_PER_KM

    # ── Total operating cost ──
    h2_total = h2_cost + h2_maintenance
    diesel_total = diesel_cost + diesel_maintenance
    cost_saved = diesel_total - h2_total
    cost_saved_per_100km = (
        diesel_cost_per_100km
        + DIESEL_MAINTENANCE_YUAN_PER_KM * 100
        - h2_cost_per_100km
        - H2_MAINTENANCE_YUAN_PER_KM * 100
    )

    # ── Emission reduction ──
    # Diesel CO2
    diesel_co2 = diesel_needed_l * DIESEL_CO2_KG_PER_L

    # H2 CO2 (assume green hydrogen for competition context)
    h2_co2_green = total_h2_kg * H2_CO2_KG_PER_KG_GREEN
    h2_co2_gray = total_h2_kg * H2_CO2_KG_PER_KG_GRAY

    co2_reduced_green = diesel_co2 - h2_co2_green  # Full reduction with green H2
    co2_reduced_gray = diesel_co2 - h2_co2_gray  # Partial reduction with gray H2

    # ── Annual projection ──
    data_period_days = 18  # Data covers Aug 1-18 (18 days)
    (
        ANNUAL_MILEAGE_KM * vehicle_count / (total_km / data_period_days * 365)
        if total_km > 0
        else 1
    )
    # Simpler: scale by annual mileage per vehicle
    annual_km_per_vehicle = ANNUAL_MILEAGE_KM
    annual_total_km = annual_km_per_vehicle * vehicle_count
    scale_factor = annual_total_km / total_km if total_km > 0 else 1

    annual_h2_cost = h2_cost * scale_factor
    annual_diesel_cost = diesel_cost * scale_factor
    annual_h2_maintenance = h2_maintenance * scale_factor
    annual_diesel_maintenance = diesel_maintenance * scale_factor
    annual_cost_saved = cost_saved * scale_factor
    annual_co2_reduced = co2_reduced_green * scale_factor

    # ── ROI ──
    total_premium = H2_TRUCK_PREMIUM_YUAN * vehicle_count
    payback_years = (
        total_premium / annual_cost_saved if annual_cost_saved > 0 else float("inf")
    )
    lifetime_savings = annual_cost_saved * VEHICLE_LIFETIME_YEARS - total_premium

    # ── Per-vehicle breakdown ──
    per_vehicle = []
    for v in vehicles:
        v_km = v.get("total_distance_km", 0)
        v_h2 = v.get("total_h2_consumed_kg", 0)
        v_h2_cost = v_h2 * H2_PRICE_YUAN_PER_KG
        v_diesel_l = v_km / 100 * DIESEL_CONSUMPTION_L_PER_100KM
        v_diesel_cost = v_diesel_l * DIESEL_PRICE_YUAN_PER_L
        v_diesel_co2 = v_diesel_l * DIESEL_CO2_KG_PER_L
        v_h2_per_100km = v_h2 / v_km * 100 if v_km > 0 else 0

        per_vehicle.append(
            {
                "vehicle_id": v.get("vehicle_id"),
                "label": v.get("label"),
                "region": v.get("region"),
                "total_km": round(v_km, 1),
                "h2_consumed_kg": round(v_h2, 2),
                "h2_per_100km": round(v_h2_per_100km, 2),
                "h2_cost_yuan": round(v_h2_cost, 0),
                "diesel_equivalent_cost_yuan": round(v_diesel_cost, 0),
                "co2_reduced_kg": round(
                    v_diesel_co2 - v_h2 * H2_CO2_KG_PER_KG_GREEN, 0
                ),
                "cost_saved_yuan": round(
                    v_diesel_cost
                    - v_h2_cost
                    + v_km
                    * (DIESEL_MAINTENANCE_YUAN_PER_KM - H2_MAINTENANCE_YUAN_PER_KM),
                    0,
                ),
            }
        )

    return {
        # Real data summary
        "data_summary": {
            "vehicle_count": vehicle_count,
            "total_trips": len(trips),
            "total_distance_km": round(total_km, 1),
            "total_h2_consumed_kg": round(total_h2_kg, 2),
            "avg_h2_per_100km": round(avg_h2_per_100km, 2),
            "data_period_days": data_period_days,
        },
        # Economic analysis
        "economic": {
            "h2_fuel_cost_yuan": round(h2_cost, 0),
            "h2_maintenance_cost_yuan": round(h2_maintenance, 0),
            "h2_total_cost_yuan": round(h2_total, 0),
            "h2_cost_per_100km": round(h2_cost_per_100km, 1),
            "diesel_fuel_cost_yuan": round(diesel_cost, 0),
            "diesel_maintenance_cost_yuan": round(diesel_maintenance, 0),
            "diesel_total_cost_yuan": round(diesel_total, 0),
            "diesel_cost_per_100km": round(diesel_cost_per_100km, 1),
            "cost_saved_yuan": round(cost_saved, 0),
            "cost_saved_per_100km": round(cost_saved_per_100km, 1),
            "cost_reduction_pct": round(cost_saved / diesel_total * 100, 1)
            if diesel_total > 0
            else 0,
        },
        # Emission analysis
        "emission": {
            "diesel_co2_kg": round(diesel_co2, 0),
            "h2_co2_green_kg": round(h2_co2_green, 0),
            "h2_co2_gray_kg": round(h2_co2_gray, 0),
            "co2_reduced_green_kg": round(co2_reduced_green, 0),
            "co2_reduced_gray_kg": round(co2_reduced_gray, 0),
            "co2_reduction_pct_green": round(co2_reduced_green / diesel_co2 * 100, 1)
            if diesel_co2 > 0
            else 0,
            "co2_per_km_diesel_g": round(diesel_co2 / total_km * 1000, 1)
            if total_km > 0
            else 0,
            "co2_per_km_h2_green_g": round(h2_co2_green / total_km * 1000, 1)
            if total_km > 0
            else 0,
        },
        # Annual projection
        "annual_projection": {
            "annual_km_per_vehicle": annual_km_per_vehicle,
            "annual_total_km": round(annual_total_km, 0),
            "annual_h2_cost": round(annual_h2_cost, 0),
            "annual_diesel_cost": round(annual_diesel_cost, 0),
            "annual_maintenance_saved": round(
                annual_diesel_maintenance - annual_h2_maintenance, 0
            ),
            "annual_cost_saved": round(annual_cost_saved, 0),
            "annual_co2_reduced_tons": round(annual_co2_reduced / 1000, 1),
        },
        # ROI
        "roi": {
            "vehicle_premium_yuan": H2_TRUCK_PREMIUM_YUAN,
            "total_premium_yuan": total_premium,
            "payback_years": round(payback_years, 1)
            if payback_years != float("inf")
            else None,
            "lifetime_years": VEHICLE_LIFETIME_YEARS,
            "lifetime_savings_yuan": round(lifetime_savings, 0),
            "roi_ratio": round(lifetime_savings / total_premium, 2)
            if total_premium > 0
            else 0,
        },
        # Parameters used
        "parameters": {
            "h2_price_yuan_per_kg": H2_PRICE_YUAN_PER_KG,
            "diesel_price_yuan_per_l": DIESEL_PRICE_YUAN_PER_L,
            "diesel_consumption_l_per_100km": DIESEL_CONSUMPTION_L_PER_100KM,
            "diesel_co2_kg_per_l": DIESEL_CO2_KG_PER_L,
            "h2_maintenance_yuan_per_km": H2_MAINTENANCE_YUAN_PER_KM,
            "diesel_maintenance_yuan_per_km": DIESEL_MAINTENANCE_YUAN_PER_KM,
            "annual_mileage_km": ANNUAL_MILEAGE_KM,
            "vehicle_lifetime_years": VEHICLE_LIFETIME_YEARS,
        },
        # Per-vehicle breakdown
        "per_vehicle": per_vehicle,
        # Sensitivity analysis (single-variable sweeps of industry parameters)
        "sensitivity": _sensitivity_analysis(total_km, total_h2_kg, vehicle_count),
    }
