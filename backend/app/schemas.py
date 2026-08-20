"""氢智行 H2Brain - 数据模型（Pydantic schemas）

所有字段围绕氢能车辆运营场景设计。
Phase 1 使用模拟数据；Phase 2 对接真实氢能运营平台数据。
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --- Enums ---


class VehicleStatus(str, Enum):
    ONLINE = "online"  # 在线待命
    IN_TRANSIT = "in_transit"  # 运输中
    REFUELING = "refueling"  # 加氢中
    MAINTENANCE = "maintenance"  # 维修保养
    LOW_HYDROGEN = "low_hydrogen"  # 氢量不足
    OFFLINE = "offline"  # 离线


class OrderStatus(str, Enum):
    PENDING = "pending"  # 待派单
    DISPATCHED = "dispatched"  # 已派单
    IN_TRANSIT = "in_transit"  # 运输中
    REFUELING = "refueling"  # 加氢中
    DELIVERED = "delivered"  # 已送达
    CANCELLED = "cancelled"  # 已取消


class AlertLevel(str, Enum):
    INFO = "info"  # 信息
    WARNING = "warning"  # 预警
    CRITICAL = "critical"  # 紧急


class FuelCellHealth(str, Enum):
    EXCELLENT = "excellent"  # 优秀
    GOOD = "good"  # 良好
    ATTENTION = "attention"  # 需关注
    WARNING = "warning"  # 警告


# --- Vehicle ---


class HydrogenVehicle(BaseModel):
    plate: str = Field(..., description="车牌号，如 京A·H2308")
    driver_name: str
    fleet_name: str
    status: VehicleStatus
    lng: float = Field(..., description="当前经度")
    lat: float = Field(..., description="当前纬度")
    hydrogen_level: float = Field(..., description="当前氢量(%)", ge=0, le=100)
    mileage: float = Field(..., description="本月里程(公里)")
    hydrogen_consumption: float = Field(..., description="百公里氢耗(kg)", ge=0)
    fuel_cell_health: FuelCellHealth
    range_remaining: float = Field(..., description="剩余续航(公里)", ge=0)
    today_orders: int = 0
    model: str = Field(default="福田智蓝H2-31T", description="车型")


class VehiclePoolSummary(BaseModel):
    """车队汇总"""

    total: int
    online: int
    in_transit: int
    refueling: int
    low_hydrogen: int
    offline: int
    fleets: int


# --- Hydrogen Station ---


class HydrogenStation(BaseModel):
    station_id: str
    name: str
    lng: float
    lat: float
    status: str = Field(..., description="normal/maintenance/offline")
    hydrogen_pressure: float = Field(..., description="加氢压力(MPa)")
    storage_capacity: float = Field(..., description="储氢量(kg)")
    current_storage: float = Field(..., description="当前余量(kg)")
    queue_length: int = Field(default=0, description="排队车辆数")
    avg_wait_time: int = Field(default=0, description="平均等待时间(分钟)")
    price_per_kg: float = Field(..., description="氢价(元/kg)")


# --- Order ---


class TransportOrder(BaseModel):
    order_id: str
    cargo_type: str = Field(..., description="货物类型")
    origin: str = Field(..., description="起运地")
    destination: str = Field(..., description="目的地")
    vehicle_plate: str
    status: OrderStatus
    fee: float = Field(..., description="运费(元)")
    distance: float = Field(..., description="里程(公里)")
    hydrogen_needed: float = Field(..., description="预估氢耗(kg)")
    created_at: str


# --- Realtime Event ---


class RealtimeEvent(BaseModel):
    """实时事件流"""

    event_type: str = Field(..., description="dispatch/refuel/alert/complete/optimize")
    level: AlertLevel = AlertLevel.INFO
    title: str
    detail: str
    vehicle_plate: Optional[str] = None
    station_id: Optional[str] = None
    timestamp: str


# --- KPI ---


class DashboardKpi(BaseModel):
    vehicles_total: int
    vehicles_online: int
    vehicles_in_transit: int
    fleets: int
    orders_today: int
    avg_hydrogen_consumption: float = Field(..., description="平均百公里氢耗(kg)")
    avg_hydrogen_cost: float = Field(..., description="平均百公里氢成本(元)")
    hydrogen_efficiency: float = Field(..., description="氢能利用率(%)")
    fuel_cell_avg_health: float = Field(..., description="燃料电池平均健康度(%)")
    cost_saved_today: float = Field(..., description="今日预估节省成本(元)")
    carbon_reduction: float = Field(..., description="今日碳减排(kg CO2)")


# --- ReAct ---


class ReactRequest(BaseModel):
    scenario: str = Field(default="hydrogen_optimization", description="场景类型")
    query: str = Field(..., description="用户问题")
    vehicle_plate: Optional[str] = None
    context: Optional[dict] = None


class ReactStep(BaseModel):
    thought: str
    action: str
    observation: str


class ReactResponse(BaseModel):
    steps: list[ReactStep]
    final_answer: str
    scenario: str
