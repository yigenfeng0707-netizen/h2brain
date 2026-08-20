"""氢智行 H2Brain - 模拟数据层

生成氢能车辆运营的模拟数据，用于黑客松 Demo 演示。
数据基于北京大兴氢能示范区的真实场景参数。
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from .schemas import (
    AlertLevel,
    DashboardKpi,
    FuelCellHealth,
    HydrogenStation,
    HydrogenVehicle,
    OrderStatus,
    RealtimeEvent,
    TransportOrder,
    VehiclePoolSummary,
    VehicleStatus,
)

# 北京大兴氢能示范区周边加氢站（模拟坐标）
STATIONS_DATA = [
    {
        "station_id": "HRS-001",
        "name": "大兴国际氢能示范区加氢站",
        "lng": 116.341,
        "lat": 39.727,
        "price_per_kg": 35.0,
    },
    {
        "station_id": "HRS-002",
        "name": "黄村加氢站",
        "lng": 116.338,
        "lat": 39.759,
        "price_per_kg": 33.0,
    },
    {
        "station_id": "HRS-003",
        "name": "亦庄经济开发区加氢站",
        "lng": 116.541,
        "lat": 39.799,
        "price_per_kg": 36.0,
    },
    {
        "station_id": "HRS-004",
        "name": "房山氢能产业园加氢站",
        "lng": 116.143,
        "lat": 39.762,
        "price_per_kg": 32.0,
    },
    {
        "station_id": "HRS-005",
        "name": "通州物流港加氢站",
        "lng": 116.657,
        "lat": 39.904,
        "price_per_kg": 34.0,
    },
]

VEHICLE_MODELS = ["福田智蓝H2-31T", "飞驰FSQ-18T", "大运氢能-25T", "解放J7-氢能版-31T"]
FLEET_NAMES = ["大兴氢能车队A", "亦庄绿运车队B", "通州氢速车队C", "房山氢源车队D"]
DRIVER_NAMES = [
    "张伟",
    "李强",
    "王磊",
    "刘洋",
    "陈刚",
    "赵军",
    "杨帆",
    "周勇",
    "吴鹏",
    "徐明",
]
CARGO_TYPES = ["冷链物流", "建材运输", "快递干线", "钢材运输", "化工品运输"]

VEHICLE_PLATES = [
    "京A-H2308",
    "京B-H0816",
    "京A-H1025",
    "京C-H3567",
    "京B-H2098",
    "京A-H3091",
    "京D-H1102",
    "京B-H4567",
    "京A-H2789",
    "京C-H3344",
    "京B-H1900",
    "京A-H4456",
    "京D-H2087",
    "京C-H1678",
    "京B-H3399",
]


def _random_status() -> VehicleStatus:
    weights = [0.3, 0.35, 0.1, 0.05, 0.12, 0.08]
    return random.choices(list(VehicleStatus), weights=weights)[0]


def _random_health() -> FuelCellHealth:
    weights = [0.45, 0.30, 0.15, 0.10]
    return random.choices(list(FuelCellHealth), weights=weights)[0]


def _random_lng_lat() -> tuple[float, float]:
    base_lng, base_lat = 116.341, 39.727
    return base_lng + random.uniform(-0.3, 0.3), base_lat + random.uniform(-0.15, 0.15)


def generate_vehicles() -> list[HydrogenVehicle]:
    vehicles = []
    for i, plate in enumerate(VEHICLE_PLATES):
        status = _random_status()
        lng, lat = _random_lng_lat()
        h2_level = (
            random.uniform(15, 95)
            if status != VehicleStatus.LOW_HYDROGEN
            else random.uniform(5, 15)
        )
        health = _random_health()
        consumption = round(random.uniform(7.5, 12.0), 1)
        mileage = round(random.uniform(3000, 12000), 0)

        vehicles.append(
            HydrogenVehicle(
                plate=plate,
                driver_name=random.choice(DRIVER_NAMES),
                fleet_name=FLEET_NAMES[i % len(FLEET_NAMES)],
                status=status,
                lng=lng,
                lat=lat,
                hydrogen_level=round(h2_level, 1),
                mileage=mileage,
                hydrogen_consumption=consumption,
                fuel_cell_health=health,
                range_remaining=round(h2_level * 4.5, 0),
                today_orders=random.randint(0, 5),
                model=random.choice(VEHICLE_MODELS),
            )
        )
    return vehicles


def generate_stations() -> list[HydrogenStation]:
    stations = []
    for s in STATIONS_DATA:
        storage_cap = random.uniform(300, 500)
        current = random.uniform(storage_cap * 0.2, storage_cap * 0.8)
        stations.append(
            HydrogenStation(
                station_id=s["station_id"],
                name=s["name"],
                lng=s["lng"],
                lat=s["lat"],
                status=random.choices(
                    ["normal", "maintenance", "offline"], weights=[0.85, 0.1, 0.05]
                )[0],
                hydrogen_pressure=round(random.uniform(35, 70), 1),
                storage_capacity=round(storage_cap, 1),
                current_storage=round(current, 1),
                queue_length=random.randint(0, 6),
                avg_wait_time=random.randint(0, 25),
                price_per_kg=s["price_per_kg"],
            )
        )
    return stations


def generate_orders(vehicles: list[HydrogenVehicle]) -> list[TransportOrder]:
    origins = [
        "大兴物流园",
        "亦庄仓储中心",
        "通州快递分拨中心",
        "房山建材城",
        "顺义空港物流",
    ]
    destinations = ["天津港", "石家庄物流园", "保定配送中心", "唐山港", "廊坊快递中心"]
    orders = []
    now = datetime.now()
    for i in range(10):
        v = random.choice(vehicles)
        distance = round(random.uniform(50, 350), 1)
        h2_needed = round(distance * v.hydrogen_consumption / 100, 1)
        created = now - timedelta(hours=random.randint(0, 12))
        orders.append(
            TransportOrder(
                order_id=f"ORD-2026-{1000 + i}",
                cargo_type=random.choice(CARGO_TYPES),
                origin=random.choice(origins),
                destination=random.choice(destinations),
                vehicle_plate=v.plate,
                status=random.choice(list(OrderStatus)),
                fee=round(distance * random.uniform(8, 15), 0),
                distance=distance,
                hydrogen_needed=h2_needed,
                created_at=created.isoformat(),
            )
        )
    return orders


def generate_events() -> list[RealtimeEvent]:
    templates = [
        (
            "dispatch",
            AlertLevel.INFO,
            "智能派单",
            "车辆 {plate} 已匹配最优订单，预计氢耗 {h2}kg",
        ),
        (
            "refuel",
            AlertLevel.INFO,
            "加氢调度",
            "车辆 {plate} 已导航至 {station}，预计等待 {wait}分钟",
        ),
        (
            "alert",
            AlertLevel.WARNING,
            "氢量预警",
            "车辆 {plate} 氢量仅 {level}%，建议立即加氢",
        ),
        (
            "optimize",
            AlertLevel.INFO,
            "氢耗优化",
            "车辆 {plate} 路线已优化，预计节省氢耗 {save}kg",
        ),
        (
            "complete",
            AlertLevel.INFO,
            "订单完成",
            "车辆 {plate} 已完成运输，实际氢耗 {h2}kg",
        ),
        (
            "alert",
            AlertLevel.CRITICAL,
            "燃料电池告警",
            "车辆 {plate} 燃料电池效率下降至 {eff}%，建议检修",
        ),
    ]
    events = []
    now = datetime.now()
    for i in range(15):
        tpl = random.choice(templates)
        plate = random.choice(VEHICLE_PLATES)
        event = RealtimeEvent(
            event_type=tpl[0],
            level=tpl[1],
            title=tpl[2],
            detail=tpl[3].format(
                plate=plate,
                h2=round(random.uniform(3, 15), 1),
                station=random.choice([s["name"] for s in STATIONS_DATA]),
                wait=random.randint(3, 20),
                level=random.randint(5, 14),
                save=round(random.uniform(0.5, 3.0), 1),
                eff=random.randint(65, 80),
            ),
            vehicle_plate=plate,
            timestamp=(now - timedelta(minutes=i * 3)).isoformat(),
        )
        events.append(event)
    return events


def generate_kpi(vehicles: list[HydrogenVehicle]) -> DashboardKpi:
    online_count = sum(1 for v in vehicles if v.status not in (VehicleStatus.OFFLINE,))
    in_transit = sum(1 for v in vehicles if v.status == VehicleStatus.IN_TRANSIT)
    avg_consumption = round(
        sum(v.hydrogen_consumption for v in vehicles) / len(vehicles), 1
    )
    avg_cost = round(avg_consumption * 34.0, 0)

    return DashboardKpi(
        vehicles_total=len(vehicles),
        vehicles_online=online_count,
        vehicles_in_transit=in_transit,
        fleets=len(FLEET_NAMES),
        orders_today=random.randint(25, 60),
        avg_hydrogen_consumption=avg_consumption,
        avg_hydrogen_cost=avg_cost,
        hydrogen_efficiency=round(random.uniform(82, 92), 1),
        fuel_cell_avg_health=round(random.uniform(78, 90), 1),
        cost_saved_today=round(random.uniform(2500, 4800), 0),
        carbon_reduction=round(random.uniform(180, 320), 1),
    )


def generate_vehicle_pool_summary(
    vehicles: list[HydrogenVehicle],
) -> VehiclePoolSummary:
    return VehiclePoolSummary(
        total=len(vehicles),
        online=sum(1 for v in vehicles if v.status == VehicleStatus.ONLINE),
        in_transit=sum(1 for v in vehicles if v.status == VehicleStatus.IN_TRANSIT),
        refueling=sum(1 for v in vehicles if v.status == VehicleStatus.REFUELING),
        low_hydrogen=sum(1 for v in vehicles if v.status == VehicleStatus.LOW_HYDROGEN),
        offline=sum(1 for v in vehicles if v.status == VehicleStatus.OFFLINE),
        fleets=len(FLEET_NAMES),
    )


# 预生成数据缓存
_vehicles = generate_vehicles()
_stations = generate_stations()
_orders = generate_orders(_vehicles)
_events = generate_events()
_kpi = generate_kpi(_vehicles)
_pool_summary = generate_vehicle_pool_summary(_vehicles)


def get_vehicles() -> list[HydrogenVehicle]:
    return _vehicles


def get_stations() -> list[HydrogenStation]:
    return _stations


def get_orders() -> list[TransportOrder]:
    return _orders


def get_events() -> list[RealtimeEvent]:
    return _events


def get_kpi() -> DashboardKpi:
    return _kpi


def get_pool_summary() -> VehiclePoolSummary:
    return _pool_summary
