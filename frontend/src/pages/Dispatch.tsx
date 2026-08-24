// 氢智行 H2Brain - 智能调度大屏
import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Spin, Empty, Button } from 'antd'
import { apiGet } from '@/lib/request'
import ReactECharts from 'echarts-for-react'

interface Vehicle {
  plate: string
  driver_name: string
  fleet_name: string
  status: string
  lng: number
  lat: number
  hydrogen_level: number
  range_remaining: number
  hydrogen_consumption: number
  model: string
}

interface Station {
  station_id: string
  name: string
  lng: number
  lat: number
  status: string
  hydrogen_pressure: number
  current_storage: number
  storage_capacity: number
  queue_length: number
  avg_wait_time: number
  price_per_kg: number
}

interface Order {
  order_id: string
  cargo_type: string
  origin: string
  destination: string
  vehicle_plate: string
  status: string
  fee: number
  distance: number
  hydrogen_needed: number
}

const ORDER_STATUS_COLORS: Record<string, string> = {
  pending: 'orange',
  dispatched: 'blue',
  in_transit: 'cyan',
  refueling: 'gold',
  delivered: 'green',
  cancelled: 'red',
}

const ORDER_STATUS_LABELS: Record<string, string> = {
  pending: '待派单',
  dispatched: '已派单',
  in_transit: '运输中',
  refueling: '加氢中',
  delivered: '已送达',
  cancelled: '已取消',
}

const VEHICLE_STATUS_LABELS: Record<string, string> = {
  in_transit: '运输中',
  online: '在线待命',
  low_hydrogen: '低氢量',
  offline: '离线',
}

const STATION_STATUS_LABELS: Record<string, string> = {
  normal: '正常',
  maintenance: '维护中',
  offline: '离线',
}

export default function Dispatch() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [stations, setStations] = useState<Station[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [recommend, setRecommend] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      apiGet.dispatchVehicles(),
      apiGet.operationsStations(),
      apiGet.dispatchOrders(),
      apiGet.dispatchRecommend(),
    ]).then(([v, s, o, r]) => {
      setVehicles(v.data)
      setStations(s.data)
      setOrders(o.data)
      setRecommend(r.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />

  // 加氢站散点图(含车辆,tooltip按类型分流)
  const stationMap = {
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const d = p.data
        const raw = d.value?.[2] ?? {}
        if (d.itemType === 'vehicle') {
          const v = raw as Vehicle
          return `<b>${v.plate}</b>（${v.model}）<br/>状态: ${VEHICLE_STATUS_LABELS[v.status] || v.status}<br/>司机: ${v.driver_name || '-'} | 车队: ${v.fleet_name || '-'}<br/>氢量: ${v.hydrogen_level}%（约 ${v.range_remaining}km）<br/>百公里氢耗: ${v.hydrogen_consumption}kg`
        }
        const s = raw as Station
        return `<b>${s.name}</b><br/>状态: ${STATION_STATUS_LABELS[s.status] || s.status}<br/>储氢: ${s.current_storage}/${s.storage_capacity}kg<br/>排队: ${s.queue_length}辆 | 等待: ${s.avg_wait_time}min<br/>氢价: ${s.price_per_kg}元/kg`
      },
    },
    xAxis: { type: 'value', name: '经度', min: 116.0, max: 116.8, axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    yAxis: { type: 'value', name: '纬度', min: 39.6, max: 40.0, axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    series: [
      {
        type: 'scatter',
        name: '加氢站',
        data: stations.map(s => ({
          name: s.name,
          itemType: 'station',
          value: [s.lng, s.lat, s],
          symbolSize: 20 + s.queue_length * 3,
          itemStyle: {
            color: s.status === 'normal' ? '#69F0AE' : s.status === 'maintenance' ? '#FFD740' : '#6B7280',
          },
        })),
      },
      {
        type: 'scatter',
        name: '车辆',
        data: vehicles.map(v => ({
          name: v.plate,
          itemType: 'vehicle',
          value: [v.lng, v.lat, v],
          symbolSize: 10,
          itemStyle: {
            color: v.status === 'in_transit' ? '#00E5FF' :
                   v.status === 'online' ? '#69F0AE' :
                   v.status === 'low_hydrogen' ? '#FF6B35' : '#6B7280',
          },
        })),
      },
    ],
    grid: { left: '5%', right: '5%', bottom: '10%', containLabel: true },
  }

  const stationColumns = [
    { title: '加氢站', dataIndex: 'name', key: 'name' },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => <Tag color={s === 'normal' ? 'green' : s === 'maintenance' ? 'gold' : 'default'}>{s === 'normal' ? '正常' : s === 'maintenance' ? '维护' : '离线'}</Tag> },
    { title: '储氢量', key: 'storage', width: 100,
      render: (_: any, r: Station) => `${r.current_storage}/${r.storage_capacity}kg` },
    { title: '排队', dataIndex: 'queue_length', key: 'queue_length', width: 60 },
    { title: '等待(min)', dataIndex: 'avg_wait_time', key: 'avg_wait_time', width: 80 },
    { title: '氢价(元/kg)', dataIndex: 'price_per_kg', key: 'price_per_kg', width: 100 },
  ]

  const orderColumns = [
    { title: '订单号', dataIndex: 'order_id', key: 'order_id', width: 130 },
    { title: '货物', dataIndex: 'cargo_type', key: 'cargo_type', width: 90 },
    { title: '起点', dataIndex: 'origin', key: 'origin', width: 120 },
    { title: '终点', dataIndex: 'destination', key: 'destination', width: 120 },
    { title: '车辆', dataIndex: 'vehicle_plate', key: 'vehicle_plate', width: 100 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 80,
      render: (s: string) => <Tag color={ORDER_STATUS_COLORS[s] || 'default'}>{ORDER_STATUS_LABELS[s] || s}</Tag> },
    { title: '里程(km)', dataIndex: 'distance', key: 'distance', width: 80 },
    { title: '氢耗(kg)', dataIndex: 'hydrogen_needed', key: 'hydrogen_needed', width: 80 },
    { title: '运费(元)', dataIndex: 'fee', key: 'fee', width: 80 },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <Row gutter={[8, 8]}>
        <Col xs={24} lg={14}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>车辆与加氢站实时分布</h3>
            <ReactECharts option={stationMap} style={{ height: 360 }} />
          </div>
        </Col>
        <Col xs={24} lg={10}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>智能派单推荐</h3>
            {recommend?.recommendations?.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {recommend.recommendations.map((r: any, i: number) => (
                  <div key={i} className="h2-kpi-card" style={{ padding: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#69F0AE', fontWeight: 700 }}>{r.order_id}</span>
                      <span style={{ color: '#00E5FF' }}>推荐: {r.recommended_vehicle}</span>
                    </div>
                    <div style={{ color: 'rgba(224,245,232,0.7)', fontSize: 12, marginTop: 4 }}>
                      {r.reason}
                    </div>
                    <div style={{ color: 'rgba(224,245,232,0.5)', fontSize: 11, marginTop: 4 }}>
                      预估氢耗: {r.estimated_hydrogen}kg | 成本: {r.estimated_cost}元
                    </div>
                  </div>
                ))}
              </div>
            ) : <Empty description="暂无待派单订单" />}
          </div>
        </Col>
      </Row>

      <Row gutter={[8, 8]}>
        <Col xs={24} lg={10}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>加氢站状态</h3>
            <Table
              dataSource={stations}
              columns={stationColumns}
              rowKey="station_id"
              size="small"
              pagination={false}
              scroll={{ x: 600 }}
            />
          </div>
        </Col>
        <Col xs={24} lg={14}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>运输订单</h3>
            <Table
              dataSource={orders}
              columns={orderColumns}
              rowKey="order_id"
              size="small"
              pagination={{ pageSize: 8, size: 'small' }}
              scroll={{ x: 900 }}
            />
          </div>
        </Col>
      </Row>
    </div>
  )
}
