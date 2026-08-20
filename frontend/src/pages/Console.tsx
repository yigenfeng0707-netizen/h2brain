// 氢智行 H2Brain - 运营总览大屏
import { useEffect, useState } from 'react'
import { Card, Row, Col, Table, Tag, Spin, Empty } from 'antd'
import { apiGet } from '@/lib/request'
import ReactECharts from 'echarts-for-react'

interface Kpi {
  vehicles_total: number
  vehicles_online: number
  vehicles_in_transit: number
  fleets: number
  orders_today: number
  avg_hydrogen_consumption: number
  avg_hydrogen_cost: number
  hydrogen_efficiency: number
  fuel_cell_avg_health: number
  cost_saved_today: number
  carbon_reduction: number
}

interface Vehicle {
  plate: string
  driver_name: string
  fleet_name: string
  status: string
  hydrogen_level: number
  mileage: number
  hydrogen_consumption: number
  fuel_cell_health: string
  range_remaining: number
  today_orders: number
  model: string
}

const STATUS_COLORS: Record<string, string> = {
  online: 'green',
  in_transit: 'cyan',
  refueling: 'gold',
  low_hydrogen: 'orange',
  maintenance: 'volcano',
  offline: 'default',
}

const STATUS_LABELS: Record<string, string> = {
  online: '在线待命',
  in_transit: '运输中',
  refueling: '加氢中',
  low_hydrogen: '氢量不足',
  maintenance: '维修中',
  offline: '离线',
}

export default function Console() {
  const [kpi, setKpi] = useState<Kpi | null>(null)
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [events, setEvents] = useState<any[]>([])
  const [trends, setTrends] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      apiGet.operationsSummary(),
      apiGet.operationsVehicles(),
      apiGet.operationsEvents(),
      apiGet.operationsTrends(),
    ]).then(([k, v, e, t]) => {
      setKpi(k.data)
      setVehicles(v.data)
      setEvents(e.data)
      setTrends(t.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />

  const kpiCards = kpi ? [
    { title: '车辆总数', value: kpi.vehicles_total, unit: '辆', color: '#69F0AE' },
    { title: '在线车辆', value: kpi.vehicles_online, unit: '辆', color: '#00E5FF' },
    { title: '运输中', value: kpi.vehicles_in_transit, unit: '辆', color: '#00C853' },
    { title: '今日订单', value: kpi.orders_today, unit: '单', color: '#FFD740' },
    { title: '平均氢耗', value: kpi.avg_hydrogen_consumption, unit: 'kg/百公里', color: '#69F0AE' },
    { title: '氢能利用率', value: kpi.hydrogen_efficiency, unit: '%', color: '#00E5FF' },
    { title: '电池健康度', value: kpi.fuel_cell_avg_health, unit: '%', color: '#00C853' },
    { title: '今日节省', value: kpi.cost_saved_today, unit: '元', color: '#FFD740' },
    { title: '碳减排', value: kpi.carbon_reduction, unit: 'kg CO2', color: '#69F0AE' },
  ] : []

  const consumptionChart = trends ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trends.hydrogen_consumption.map((d: any) => d.day) },
    yAxis: { type: 'value', name: 'kg/百公里' },
    series: [{
      data: trends.hydrogen_consumption.map((d: any) => d.value),
      type: 'line',
      smooth: true,
      areaStyle: { color: 'rgba(105,240,174,0.15)' },
      lineStyle: { color: '#69F0AE', width: 2 },
      itemStyle: { color: '#69F0AE' },
    }],
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  } : null

  const efficiencyChart = trends ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trends.efficiency.map((d: any) => d.day) },
    yAxis: { type: 'value', name: '%', max: 100 },
    series: [{
      data: trends.efficiency.map((d: any) => d.value),
      type: 'bar',
      itemStyle: { color: '#00E5FF', borderRadius: [4, 4, 0, 0] },
    }],
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  } : null

  const vehicleColumns = [
    { title: '车牌', dataIndex: 'plate', key: 'plate', width: 110 },
    { title: '司机', dataIndex: 'driver_name', key: 'driver_name', width: 70 },
    { title: '车队', dataIndex: 'fleet_name', key: 'fleet_name', width: 120 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => <Tag color={STATUS_COLORS[s]}>{STATUS_LABELS[s] || s}</Tag> },
    { title: '氢量(%)', dataIndex: 'hydrogen_level', key: 'hydrogen_level', width: 80,
      render: (v: number) => <span style={{ color: v < 20 ? '#FF6B35' : '#69F0AE' }}>{v}%</span> },
    { title: '续航(km)', dataIndex: 'range_remaining', key: 'range_remaining', width: 80 },
    { title: '氢耗(kg)', dataIndex: 'hydrogen_consumption', key: 'hydrogen_consumption', width: 90 },
    { title: '电池健康', dataIndex: 'fuel_cell_health', key: 'fuel_cell_health', width: 90,
      render: (s: string) => {
        const colors: Record<string, string> = { excellent: 'green', good: 'cyan', attention: 'gold', warning: 'red' }
        return <Tag color={colors[s] || 'default'}>{s}</Tag>
      } },
    { title: '今日订单', dataIndex: 'today_orders', key: 'today_orders', width: 80 },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* KPI 卡片 */}
      <Row gutter={[8, 8]}>
        {kpiCards.map((card) => (
          <Col key={card.title} xs={12} sm={8} md={6} lg={4} xl={3}>
            <div className="h2-kpi-card">
              <div style={{ color: 'rgba(224,245,232,0.6)', fontSize: 12 }}>{card.title}</div>
              <div className="h2-num" style={{ fontSize: 'clamp(20px,2vw,28px)', color: card.color, marginTop: 4 }}>
                {card.value}
                <span style={{ fontSize: 12, marginLeft: 4, opacity: 0.7 }}>{card.unit}</span>
              </div>
            </div>
          </Col>
        ))}
      </Row>

      {/* 图表行 */}
      <Row gutter={[8, 8]}>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>7日氢耗趋势 (kg/百公里)</h3>
            {consumptionChart && <ReactECharts option={consumptionChart} style={{ height: 240 }} />}
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>7日氢能利用率 (%)</h3>
            {efficiencyChart && <ReactECharts option={efficiencyChart} style={{ height: 240 }} />}
          </div>
        </Col>
      </Row>

      {/* 车辆列表 + 事件流 */}
      <Row gutter={[8, 8]}>
        <Col xs={24} lg={16}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>车辆实时状态</h3>
            <Table
              dataSource={vehicles}
              columns={vehicleColumns}
              rowKey="plate"
              size="small"
              pagination={{ pageSize: 8, size: 'small' }}
              scroll={{ x: 800 }}
            />
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>实时事件流</h3>
            <div style={{ maxHeight: 400, overflow: 'auto' }}>
              {events.length === 0 ? <Empty /> : events.map((ev, i) => (
                <div key={i} style={{
                  padding: '8px 0',
                  borderBottom: '1px solid rgba(105,240,174,0.08)',
                  fontSize: 12,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Tag color={ev.level === 'critical' ? 'red' : ev.level === 'warning' ? 'orange' : 'green'}>
                      {ev.title}
                    </Tag>
                    <span style={{ color: 'rgba(224,245,232,0.4)', fontSize: 10 }}>
                      {new Date(ev.timestamp).toLocaleTimeString('zh-CN')}
                    </span>
                  </div>
                  <div style={{ color: 'rgba(224,245,232,0.7)', marginTop: 4 }}>{ev.detail}</div>
                </div>
              ))}
            </div>
          </div>
        </Col>
      </Row>
    </div>
  )
}
