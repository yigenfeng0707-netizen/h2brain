"""H2Brain - Route Planning & Station Scheduling Algorithms

Route planning: Haversine distance, range circle, multi-station optimization
Station scheduling: M/M/c queuing theory model for wait time prediction
"""

from __future__ import annotations

import math
from typing import Any

from .mock_data import get_vehicles, get_stations

# Earth radius in km
EARTH_RADIUS_KM = 6371.0

# Hydrogen consumption rate: kg per km (average for heavy truck)
H2_PER_KM = 0.095  # ~9.5 kg/100km

# Tank capacity: kg (typical 31T hydrogen truck)
TANK_CAPACITY_KG = 30.0


def haversine_distance(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    """Compute great-circle distance between two GPS points in km."""
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_KM * c


def compute_range_circle(
    hydrogen_pct: float, consumption_kg_per_100km: float = 9.5
) -> float:
    """Compute safe range circle radius in km.

    Args:
        hydrogen_pct: Current hydrogen level percentage (0-100)
        consumption_kg_per_100km: Vehicle consumption rate

    Returns:
        Safe range in km (with 15% safety margin)
    """
    available_kg = TANK_CAPACITY_KG * (hydrogen_pct / 100.0)
    raw_range = (available_kg / consumption_kg_per_100km) * 100.0
    # 15% safety margin
    return raw_range * 0.85


def find_nearby_stations(
    vehicle_lng: float,
    vehicle_lat: float,
    max_radius_km: float = 50.0,
) -> list[dict[str, Any]]:
    """Find all stations within max_radius_km of the vehicle.

    Returns list of station dicts sorted by distance, each with:
        station info + distance_km + reachable (bool)
    """
    stations = get_stations()
    results = []
    for s in stations:
        dist = haversine_distance(vehicle_lng, vehicle_lat, s.lng, s.lat)
        if dist <= max_radius_km:
            results.append(
                {
                    "station_id": s.station_id,
                    "name": s.name,
                    "lng": s.lng,
                    "lat": s.lat,
                    "distance_km": round(dist, 1),
                    "status": s.status,
                    "storage_current": round(s.current_storage, 1),
                    "storage_capacity": round(s.storage_capacity, 1),
                    "queue_length": s.queue_length,
                    "avg_wait_time": s.avg_wait_time,
                    "price_per_kg": s.price_per_kg,
                    "hydrogen_pressure": s.hydrogen_pressure,
                }
            )
    results.sort(key=lambda x: x["distance_km"])
    return results


def plan_route(
    vehicle_plate: str,
    destination_lng: float,
    destination_lat: float,
    destination_name: str = "destination",
) -> dict[str, Any]:
    """Plan optimal route for a vehicle to reach a destination.

    Considers:
    - Current hydrogen level and range
    - Direct route feasibility
    - Refueling station selection if needed
    - Cost estimation

    Returns:
        Route plan dict with feasibility, stations, segments, cost
    """
    # Find vehicle
    vehicles = get_vehicles()
    vehicle = None
    for v in vehicles:
        if vehicle_plate.replace("-", "").replace(" ", "").replace(
            "\u00b7", ""
        ) in v.plate.replace("-", "").replace(" ", "").replace("\u00b7", ""):
            vehicle = v
            break

    if vehicle is None:
        return {"error": f"Vehicle not found: {vehicle_plate}"}

    # Compute distances
    direct_distance = haversine_distance(
        vehicle.lng, vehicle.lat, destination_lng, destination_lat
    )
    safe_range = compute_range_circle(
        vehicle.hydrogen_level, vehicle.hydrogen_consumption
    )

    # Direct route feasible?
    direct_feasible = direct_distance <= safe_range
    max(
        0,
        vehicle.hydrogen_level
        - (direct_distance / safe_range * vehicle.hydrogen_level * 0.85)
        if safe_range > 0
        else 0,
    )

    # Find stations along the route (within 15km of the straight line)
    nearby = find_nearby_stations(
        vehicle.lng, vehicle.lat, max_radius_km=max(direct_distance * 0.7, 30)
    )

    # If direct route not feasible, find best refueling station
    best_station = None
    if not direct_feasible and nearby:
        # Score each station: minimize (distance_to_station + wait_time_penalty + price_penalty)
        best_score = float("inf")
        for s in nearby:
            if s["status"] != "normal":
                continue
            if s["storage_current"] < 5.0:
                continue
            dist_to_station = s["distance_km"]
            dist_station_to_dest = haversine_distance(
                s["lng"], s["lat"], destination_lng, destination_lat
            )
            # Can vehicle reach the station?
            if dist_to_station > safe_range:
                continue
            # Total route via station
            total_via = dist_to_station + dist_station_to_dest
            # Score: total distance + wait time (min) * cost factor + price
            wait_penalty = s["avg_wait_time"] * 0.5  # 1 min wait = 0.5 km penalty
            price_penalty = (s["price_per_kg"] - 33.0) * 2  # baseline 33 yuan/kg
            score = total_via + wait_penalty + price_penalty
            if score < best_score:
                best_score = score
                best_station = s

    # Build route plan
    if direct_feasible:
        h2_needed_kg = (direct_distance / 100.0) * vehicle.hydrogen_consumption
        cost = h2_needed_kg * 34.0  # avg price
        return {
            "vehicle": vehicle.plate,
            "current_h2_pct": vehicle.hydrogen_level,
            "safe_range_km": round(safe_range, 1),
            "destination": destination_name,
            "direct_distance_km": round(direct_distance, 1),
            "feasible": True,
            "plan": "direct",
            "segments": [
                {
                    "from": "current_position",
                    "to": destination_name,
                    "distance_km": round(direct_distance, 1),
                    "estimated_h2_used_kg": round(h2_needed_kg, 1),
                    "arrival_h2_pct": round(
                        max(
                            0,
                            vehicle.hydrogen_level
                            - h2_needed_kg / TANK_CAPACITY_KG * 100,
                        ),
                        1,
                    ),
                }
            ],
            "total_distance_km": round(direct_distance, 1),
            "estimated_cost_yuan": round(cost, 0),
            "refuel_needed": False,
        }
    elif best_station:
        dist_to_station = best_station["distance_km"]
        dist_station_to_dest = haversine_distance(
            best_station["lng"], best_station["lat"], destination_lng, destination_lat
        )
        total_distance = dist_to_station + dist_station_to_dest
        h2_to_station = (dist_to_station / 100.0) * vehicle.hydrogen_consumption
        # Refuel to 90% at station
        refuel_kg = TANK_CAPACITY_KG * 0.9 - (
            vehicle.hydrogen_level / 100.0 * TANK_CAPACITY_KG - h2_to_station
        )
        refuel_kg = max(0, refuel_kg)
        h2_station_to_dest = (
            dist_station_to_dest / 100.0
        ) * vehicle.hydrogen_consumption
        arrival_h2 = max(0, 90 - h2_station_to_dest / TANK_CAPACITY_KG * 100)
        refuel_cost = refuel_kg * best_station["price_per_kg"]

        return {
            "vehicle": vehicle.plate,
            "current_h2_pct": vehicle.hydrogen_level,
            "safe_range_km": round(safe_range, 1),
            "destination": destination_name,
            "direct_distance_km": round(direct_distance, 1),
            "feasible": True,
            "plan": "via_station",
            "refuel_station": best_station,
            "segments": [
                {
                    "from": "current_position",
                    "to": f"station:{best_station['name']}",
                    "distance_km": round(dist_to_station, 1),
                    "estimated_h2_used_kg": round(h2_to_station, 1),
                },
                {
                    "from": f"station:{best_station['name']}",
                    "to": destination_name,
                    "distance_km": round(dist_station_to_dest, 1),
                    "refuel_kg": round(refuel_kg, 1),
                    "refuel_cost_yuan": round(refuel_cost, 0),
                    "estimated_h2_used_kg": round(h2_station_to_dest, 1),
                    "arrival_h2_pct": round(arrival_h2, 1),
                },
            ],
            "total_distance_km": round(total_distance, 1),
            "estimated_cost_yuan": round(refuel_cost, 0),
            "refuel_needed": True,
            "wait_time_min": best_station["avg_wait_time"],
        }
    else:
        return {
            "vehicle": vehicle.plate,
            "current_h2_pct": vehicle.hydrogen_level,
            "safe_range_km": round(safe_range, 1),
            "destination": destination_name,
            "direct_distance_km": round(direct_distance, 1),
            "feasible": False,
            "plan": "no_route",
            "error": "No reachable refueling station found within safe range. Vehicle may need emergency refueling.",
            "nearby_stations": nearby[:3],
        }


# ---------------------------------------------------------------------------
# Station Scheduling: M/M/c Queuing Theory
# ---------------------------------------------------------------------------


def compute_mm_c_wait_time(
    arrival_rate: float,
    service_rate: float,
    num_servers: int,
) -> dict[str, float]:
    """Compute M/M/c queuing model metrics.

    Args:
        arrival_rate: lambda, vehicles per minute
        service_rate: mu, vehicles served per minute per server
        num_servers: c, number of refueling points

    Returns:
        Dict with Lq, Wq, L, W, rho, P0
    """
    lam = arrival_rate
    mu = service_rate
    c = num_servers
    rho = lam / (c * mu)

    if rho >= 1:
        return {
            "utilization": round(rho, 3),
            "queue_length_avg": float("inf"),
            "wait_time_avg_min": float("inf"),
            "system_length_avg": float("inf"),
            "system_time_avg_min": float("inf"),
            "idle_probability": 0.0,
            "stable": False,
        }

    # Erlang C formula: P0 (probability of empty system)
    # P0 = [sum_{n=0}^{c-1} (lam/mu)^n / n! + (lam/mu)^c / (c! * (1 - rho))]^-1
    a = lam / mu  # offered load
    sum_part = 0.0
    for n in range(c):
        sum_part += a**n / math.factorial(n)
    erlang_c = (a**c) / (math.factorial(c) * (1 - rho))
    p0 = 1.0 / (sum_part + erlang_c)

    # Average queue length Lq = C(c, a) * rho / (1 - rho)
    lq = erlang_c * p0 * rho / (1 - rho)
    # Average wait time Wq = Lq / lam
    wq = lq / lam if lam > 0 else 0
    # Average system length L = Lq + a
    sys_len = lq + a
    # Average system time W = Wq + 1/mu
    w = wq + 1.0 / mu if mu > 0 else 0

    return {
        "utilization": round(rho, 3),
        "queue_length_avg": round(lq, 2),
        "wait_time_avg_min": round(wq, 1),
        "system_length_avg": round(sys_len, 2),
        "system_time_avg_min": round(w, 1),
        "idle_probability": round(p0, 3),
        "stable": True,
    }


def schedule_station_dispatch(
    vehicle_plate: str | None = None,
    max_radius_km: float = 30.0,
) -> dict[str, Any]:
    """Recommend best station for a vehicle using queuing theory.

    If vehicle_plate is provided, searches nearby stations.
    Otherwise, evaluates all stations.

    Returns:
        Station ranking with queuing metrics and recommendation
    """
    stations = get_stations()
    vehicles = get_vehicles()

    # Determine vehicle location
    vehicle_lng, vehicle_lat = None, None
    if vehicle_plate:
        for v in vehicles:
            if vehicle_plate.replace("-", "").replace(" ", "") in v.plate.replace(
                "-", ""
            ).replace(" ", "").replace("\u00b7", ""):
                vehicle_lng, vehicle_lat = v.lng, v.lat
                break

    rankings = []
    for s in stations:
        # Distance
        if vehicle_lng is not None:
            dist = haversine_distance(vehicle_lng, vehicle_lat, s.lng, s.lat)
            if dist > max_radius_km:
                continue
        else:
            dist = 0.0

        if s.status != "normal":
            rankings.append(
                {
                    "station_id": s.station_id,
                    "name": s.name,
                    "status": s.status,
                    "distance_km": round(dist, 1),
                    "available": False,
                    "reason": f"Station status: {s.status}",
                }
            )
            continue

        # Estimate queuing parameters
        # arrival_rate: based on current queue length and historical data
        # Assume each refueling takes ~8 minutes (service_rate = 1/8 per min)
        service_rate = 1.0 / 8.0  # vehicles per minute per server
        # Arrival rate: estimate from queue length (if queue > 0, arrival > service)
        # Use queue_length as proxy: if queue=3, arrival_rate ~= service_rate * 1.3
        if s.queue_length > 0:
            arrival_rate = service_rate * (1 + s.queue_length * 0.15)
        else:
            arrival_rate = service_rate * 0.5

        # Number of servers (refueling points): assume 2 per station
        num_servers = 2

        queuing = compute_mm_c_wait_time(arrival_rate, service_rate, num_servers)

        # Check if station has enough hydrogen
        available_h2 = s.current_storage
        can_serve = available_h2 > 5.0

        # Total cost score: distance + wait_time + price
        wait_penalty = queuing["wait_time_avg_min"] if queuing["stable"] else 60
        price_penalty = (s.price_per_kg - 32.0) * 3  # baseline 32 yuan/kg
        total_score = dist + wait_penalty * 0.3 + price_penalty

        rankings.append(
            {
                "station_id": s.station_id,
                "name": s.name,
                "status": s.status,
                "distance_km": round(dist, 1),
                "available": can_serve,
                "queue_length": s.queue_length,
                "predicted_wait_min": queuing["wait_time_avg_min"]
                if queuing["stable"]
                else None,
                "utilization": queuing["utilization"],
                "price_per_kg": s.price_per_kg,
                "h2_available_kg": round(available_h2, 1),
                "queuing_stable": queuing["stable"],
                "score": round(total_score, 1),
            }
        )

    rankings.sort(key=lambda x: x.get("score", 9999))

    # Build recommendation
    best = None
    for r in rankings:
        if r.get("available") and r.get("queuing_stable", False):
            best = r
            break

    return {
        "vehicle_plate": vehicle_plate,
        "search_radius_km": max_radius_km,
        "stations_evaluated": len(rankings),
        "recommendation": best,
        "all_stations": rankings,
        "queuing_model": "M/M/c (Erlang C)",
        "service_time_min": 8,
        "num_servers": 2,
    }
