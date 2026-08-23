"""H2Brain - Fleet Management Multi-Objective Optimizer

Optimizes order-vehicle matching using a weighted scoring model:
- Hydrogen sufficiency (can the vehicle complete the order?)
- Proximity (is the vehicle close to the pickup point?)
- Utilization balance (is the vehicle underutilized?)
- Cost efficiency (minimize cost per order)
- Fleet load balancing (distribute orders evenly)

Uses greedy assignment with priority queue for near-optimal solution.
"""

from __future__ import annotations

import math
import json
from typing import Any

from .mock_data import get_vehicles, get_orders, VehicleStatus
from .route_optimizer import haversine_distance

# Scoring weights (sum to 1.0)
W_H2 = 0.30  # Hydrogen sufficiency
W_PROXIMITY = 0.25  # Proximity to pickup
W_UTILITY = 0.20  # Vehicle utility (prefer lower utilization)
W_COST = 0.15  # Cost efficiency
W_BALANCE = 0.10  # Fleet load balancing


def _compute_h2_score(vehicle, order) -> float:
    """Score based on hydrogen sufficiency. 1.0 = plenty, 0.0 = insufficient."""
    needed_kg = order.hydrogen_needed
    available_kg = 30.0 * (vehicle.hydrogen_level / 100.0)  # 30kg tank
    if available_kg < needed_kg:
        return 0.0  # Cannot complete
    ratio = available_kg / max(needed_kg, 0.1)
    # Diminishing returns above 2x
    return min(1.0, 1.0 / (1.0 + max(0, ratio - 2.0) * 0.3))


def _compute_proximity_score(vehicle, order) -> float:
    """Score based on distance from vehicle to pickup. Closer = higher score."""
    # Use mock vehicle GPS; origin is a named location, approximate distance
    # Since we don't have exact origin GPS, use vehicle range as proxy
    # In production, this would use real GPS coordinates
    # Estimate: if vehicle has enough range, proximity is good
    if vehicle.range_remaining < 10:
        return 0.1
    # Assume pickup within 5-30km, score decreases with distance
    # Use a mock distance based on vehicle status
    if vehicle.status == VehicleStatus.ONLINE:
        mock_distance = 8.0  # idle, likely near depot
    elif vehicle.status == VehicleStatus.IN_TRANSIT:
        mock_distance = 25.0  # need to finish current trip first
    elif vehicle.status == VehicleStatus.REFUELING:
        mock_distance = 15.0  # at station, will be available soon
    else:
        mock_distance = 50.0  # far away
    return max(0.0, 1.0 - mock_distance / 50.0)


def _compute_utility_score(vehicle, orders) -> float:
    """Score based on vehicle utilization. Prefer vehicles with fewer orders."""
    today_orders = vehicle.today_orders
    # Ideal: 2-3 orders per day. Penalize overloaded and underloaded.
    if today_orders <= 1:
        return 0.9  # Underutilized, great candidate
    elif today_orders <= 3:
        return 0.7  # Normal load
    elif today_orders <= 5:
        return 0.4  # Getting busy
    else:
        return 0.1  # Overloaded


def _compute_cost_score(vehicle, order) -> float:
    """Score based on cost efficiency. Lower cost per km = higher score."""
    # Cost = hydrogen_needed * avg_price
    # Efficiency = fee / (hydrogen_needed * price)
    avg_price = 34.0
    cost = order.hydrogen_needed * avg_price
    if cost <= 0:
        return 0.5
    profit_ratio = order.fee / cost
    # Normalize: ratio > 3 = excellent, < 1 = poor
    return max(0.0, min(1.0, (profit_ratio - 1.0) / 2.0))


def _compute_balance_score(vehicle, assignment_count: dict[str, int]) -> float:
    """Score based on fleet load balancing. Prefer vehicles with fewer assignments."""
    count = assignment_count.get(vehicle.plate, 0)
    # Normalize: 0 assignments = 1.0, 3+ = 0.0
    return max(0.0, 1.0 - count / 3.0)


def optimize_fleet_assignment(
    max_orders: int = 10,
) -> dict[str, Any]:
    """Optimize order-vehicle matching for the fleet.

    Uses greedy assignment: sort orders by priority (fee/distance),
    then for each order, score all available vehicles and assign to best.

    Returns:
        Dict with assignments, unassigned orders, fleet utilization, metrics
    """
    vehicles = get_vehicles()
    orders = get_orders()

    # Filter to pending orders and available vehicles
    pending_orders = [o for o in orders if o.status.value == "pending"][:max_orders]
    available_vehicles = [
        v for v in vehicles if v.status.value in ("online", "in_transit", "refueling")
    ]

    if not pending_orders:
        return {
            "message": "No pending orders to assign",
            "assignments": [],
            "fleet_utilization": {},
        }
    if not available_vehicles:
        return {
            "message": "No available vehicles",
            "assignments": [],
            "unassigned_orders": len(pending_orders),
        }

    # Sort orders by priority: higher fee/distance = higher priority
    sorted_orders = sorted(
        pending_orders,
        key=lambda o: (o.fee / max(o.distance, 1), o.fee),
        reverse=True,
    )

    assignment_count: dict[str, int] = {}
    assignments = []
    unassigned = []

    for order in sorted_orders:
        best_vehicle = None
        best_score = -1.0
        score_details = []

        for vehicle in available_vehicles:
            # Skip if vehicle already assigned too many orders
            if assignment_count.get(vehicle.plate, 0) >= 3:
                continue

            h2_score = _compute_h2_score(vehicle, order)
            if h2_score == 0.0:
                score_details.append(
                    {
                        "vehicle": vehicle.plate,
                        "score": 0.0,
                        "reason": "insufficient_hydrogen",
                    }
                )
                continue

            prox_score = _compute_proximity_score(vehicle, order)
            util_score = _compute_utility_score(vehicle, order)
            cost_score = _compute_cost_score(vehicle, order)
            balance_score = _compute_balance_score(vehicle, assignment_count)

            total = (
                h2_score * W_H2
                + prox_score * W_PROXIMITY
                + util_score * W_UTILITY
                + cost_score * W_COST
                + balance_score * W_BALANCE
            )

            score_details.append(
                {
                    "vehicle": vehicle.plate,
                    "score": round(total, 3),
                    "h2_score": round(h2_score, 2),
                    "proximity_score": round(prox_score, 2),
                    "utility_score": round(util_score, 2),
                    "cost_score": round(cost_score, 2),
                    "balance_score": round(balance_score, 2),
                    "hydrogen_pct": vehicle.hydrogen_level,
                    "range_km": vehicle.range_remaining,
                    "today_orders": vehicle.today_orders,
                }
            )

            if total > best_score:
                best_score = total
                best_vehicle = vehicle

        if best_vehicle is not None:
            assignment_count[best_vehicle.plate] = (
                assignment_count.get(best_vehicle.plate, 0) + 1
            )
            avg_price = 34.0
            estimated_cost = order.hydrogen_needed * avg_price
            profit = order.fee - estimated_cost
            assignments.append(
                {
                    "order_id": order.order_id,
                    "cargo_type": order.cargo_type,
                    "origin": order.origin,
                    "destination": order.destination,
                    "distance_km": order.distance,
                    "fee": order.fee,
                    "estimated_h2_kg": order.hydrogen_needed,
                    "estimated_cost": round(estimated_cost, 0),
                    "estimated_profit": round(profit, 0),
                    "assigned_vehicle": best_vehicle.plate,
                    "vehicle_fleet": best_vehicle.fleet_name,
                    "vehicle_driver": best_vehicle.driver_name,
                    "match_score": round(best_score, 3),
                    "hydrogen_level": best_vehicle.hydrogen_level,
                    "range_remaining": best_vehicle.range_remaining,
                }
            )
        else:
            unassigned.append(
                {
                    "order_id": order.order_id,
                    "destination": order.destination,
                    "reason": "no suitable vehicle (insufficient hydrogen or all overloaded)",
                }
            )

    # Compute fleet utilization
    total_vehicles = len(available_vehicles)
    assigned_vehicles = len(assignment_count)
    utilization_rate = assigned_vehicles / total_vehicles if total_vehicles > 0 else 0

    # Compute total metrics
    total_revenue = sum(a["fee"] for a in assignments)
    total_cost = sum(a["estimated_cost"] for a in assignments)
    total_profit = sum(a["estimated_profit"] for a in assignments)

    return {
        "total_pending_orders": len(pending_orders),
        "total_available_vehicles": total_vehicles,
        "assigned_count": len(assignments),
        "unassigned_count": len(unassigned),
        "fleet_utilization_pct": round(utilization_rate * 100, 1),
        "total_revenue_yuan": round(total_revenue, 0),
        "total_cost_yuan": round(total_cost, 0),
        "total_profit_yuan": round(total_profit, 0),
        "avg_match_score": round(
            sum(a["match_score"] for a in assignments) / max(len(assignments), 1), 3
        ),
        "assignments": assignments,
        "unassigned": unassigned,
        "scoring_weights": {
            "hydrogen": W_H2,
            "proximity": W_PROXIMITY,
            "utility": W_UTILITY,
            "cost": W_COST,
            "balance": W_BALANCE,
        },
    }
