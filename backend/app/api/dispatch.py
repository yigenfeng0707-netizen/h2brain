"""氢智行 H2Brain - 智能调度接口"""

from fastapi import APIRouter

from ..mock_data import get_orders, get_vehicles

router = APIRouter()


@router.get("/dispatch/vehicles", tags=["智能调度"])
def dispatch_vehicles():
    """调度大屏 - 车辆实时位置"""
    return get_vehicles()


@router.get("/dispatch/orders", tags=["智能调度"])
def dispatch_orders():
    """调度大屏 - 运输订单"""
    return get_orders()


@router.get("/dispatch/recommend", tags=["智能调度"])
def dispatch_recommend():
    """智能派单推荐"""
    vehicles = get_vehicles()
    orders = get_orders()
    # 简单模拟：为待派单订单推荐最优车辆
    pending = [o for o in orders if o.status.value == "pending"]
    available = [v for v in vehicles if v.status.value == "online"]

    recommendations = []
    for order in pending[:5]:
        if available:
            v = available[0]
            recommendations.append(
                {
                    "order_id": order.order_id,
                    "recommended_vehicle": v.plate,
                    "reason": f"氢量{v.hydrogen_level}%，续航{v.range_remaining}km，匹配度最高",
                    "estimated_hydrogen": order.hydrogen_needed,
                    "estimated_cost": round(order.hydrogen_needed * 34.0, 0),
                }
            )
    return {"recommendations": recommendations, "total_pending": len(pending)}
