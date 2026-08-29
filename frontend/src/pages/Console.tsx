// 氢智行 H2Brain - 运营总览大屏（T05 官方测试车辆真实遥测）
import { useEffect, useState } from 'react'
import { Row, Col, Table, Tag, Spin, Empty } from 'antd'
import dayjs from 'dayjs'
import { apiGet } from '@/lib/request'
import ReactECharts from 'echarts-for-react'

interface OperationsSummary {
  vehicles_total: number
  vehicles_online: number
  trips_total: number
  total_km: number
  total_h2_kg: number
  avg_hydrogen_consumption: number
  carbon_reduction: number
  data_rows: number
  data_period: string
  data_source: string
}

interface Vehicle {
  vehicle_id: string
  plate: string
  region: string
  status: 'online' | 'in_transit' | 'offline'
  soc: number
  h2_percent: number
  lng: number
  lat: number
  last_seen: string
  total_km: number
  total_trips: number
  h2_per_100km: number
  total_h2_kg: number
  date_range: string
  total_rows: number
}

interface TrendPoint {
  day: string
  value: number
}

interface OperationsTrends {
  daily_km: TrendPoint[]
  daily_h2: TrendPoint[]
  h2_per_100km: TrendPoint[]
}

interface OpsEvent {
  level: 'info' | 'warning'
  title: string
  detail: string
  timestamp: string
}

const STATUS_COLORS: Record<string, string> = {
  online: 'green',
  in_transit: 'cyan',
  offline: 'default',
}

const STATUS_LABELS: Record<string, string> = {
  online: '在线',
  in_transit: '运输中',
  offline: '离线',
}

export default function Console() {
  const [kpi, setKpi] = useState<OperationsSummary | null>(null)
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [events, setEvents] = useState<OpsEvent[]>([])
  const [trends, setTrends] = useState<OperationsTrends | null>(null)
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

  const kpiCards: { title: string; value: string | number; unit: string; color: string; small?: boolean }[] = kpi ? [
    { title: '车辆总数', value: kpi.vehicles_total, unit: '辆', color: '#69F0AE' },
    { title: '行程总数', value: kpi.trips_total, unit: '单', color: '#00E5FF' },
    { title: '总里程', value: kpi.total_km.toLocaleString(), unit: 'km', color: '#00C853' },
    { title: '总氢耗', value: kpi.total_h2_kg, unit: 'kg', color: '#FFD740' },
    { title: '平均百公里氢耗', value: kpi.avg_hydrogen_consumption, unit: 'kg', color: '#69F0AE' },
    { title: '碳减排', value: (kpi.carbon_reduction / 1000).toFixed(1), unit: 't CO₂', color: '#00E5FF' },
    { title: '数据行数', value: (kpi.data_rows / 10000).toFixed(1), unit: '万行', color: '#00C853' },
    { title: '数据周期', value: kpi.data_period, unit: '', color: '#FFD740', small: true },
  ] : []

  const dailyKmChart = trends ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trends.daily_km.map((d: TrendPoint) => d.day) },
    yAxis: { type: 'value', name: 'km' },
    series: [{
      data: trends.daily_km.map((d: TrendPoint) => d.value),
      type: 'bar',
      itemStyle: { color: '#00E5FF', borderRadius: [4, 4, 0, 0] },
    }],
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  } : null

  const h2Per100kmChart = trends ? {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: trends.h2_per_100km.map((d: TrendPoint) => d.day) },
    yAxis: { type: 'value', name: 'kg/100km' },
    series: [{
      data: trends.h2_per_100km.map((d: TrendPoint) => d.value),
      type: 'line',
      smooth: true,
      areaStyle: { color: 'rgba(105,240,174,0.15)' },
      lineStyle: { color: '#69F0AE', width: 2 },
      itemStyle: { color: '#69F0AE' },
    }],
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  } : null

  const vehicleColumns = [
    { title: '车辆', dataIndex: 'vehicle_id', key: 'vehicle_id', width: 60 },
    { title: '车牌', dataIndex: 'plate', key: 'plate', width: 110 },
    { title: '运营区域', dataIndex: 'region', key: 'region', width: 110 },
    { title: '状态', dataIndex: 'status', key: 'status', width: 90,
      render: (s: string) => <Tag color={STATUS_COLORS[s]}>{STATUS_LABELS[s] || s}</Tag> },
    { title: 'SOC', dataIndex: 'soc', key: 'soc', width: 70,
      render: (v: number) => <span style={{ color: v < 30 ? '#FF6B35' : '#69F0AE' }}>{v}%</span> },
    { title: '剩余氢量', dataIndex: 'h2_percent', key: 'h2_percent', width: 80,
      render: (v: number) => <span style={{ color: v < 20 ? '#FF6B35' : '#69F0AE' }}>{v}%</span> },
    { title: '总里程(km)', dataIndex: 'total_km', key: 'total_km', width: 100,
      render: (v: number) => v.toLocaleString() },
    { title: '行程数', dataIndex: 'total_trips', key: 'total_trips', width: 70 },
    { title: '百公里氢耗(kg)', dataIndex: 'h2_per_100km', key: 'h2_per_100km', width: 115 },
    { title: '最后上报', dataIndex: 'last_seen', key: 'last_seen', width: 125,
      render: (t: string) => dayjs(t).format('MM-DD HH:mm') },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 数据源说明 */}
      {kpi && (
        <Tag color="cyan" style={{ alignSelf: 'flex-start', fontSize: 12, padding: '3px 12px', borderRadius: 12 }}>
          真实遥测数据 · {kpi.vehicles_total} 辆测试车 · {Math.round(kpi.data_rows / 10000)}万行 · {kpi.data_period}
        </Tag>
      )}

      {/* KPI 卡片 */}
      <Row gutter={[8, 8]}>
        {kpiCards.map((card) => (
          <Col key={card.title} xs={12} sm={8} md={6} lg={4} xl={3}>
            <div className="h2-kpi-card">
              <div style={{ color: 'rgba(224,245,232,0.6)', fontSize: 12 }}>{card.title}</div>
              <div className="h2-num" style={{ fontSize: card.small ? 'clamp(13px,1.2vw,17px)' : 'clamp(20px,2vw,28px)', color: card.color, marginTop: 4 }}>
                {card.value}
                {card.unit && <span style={{ fontSize: 12, marginLeft: 4, opacity: 0.7 }}>{card.unit}</span>}
              </div>
            </div>
          </Col>
        ))}
      </Row>

      {/* 图表行 */}
      <Row gutter={[8, 8]}>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>数据期内每日里程</h3>
            {dailyKmChart && <ReactECharts option={dailyKmChart} style={{ height: 240 }} />}
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>每日百公里氢耗</h3>
            {h2Per100kmChart && <ReactECharts option={h2Per100kmChart} style={{ height: 240 }} />}
          </div>
        </Col>
      </Row>

      {/* 车辆列表 + 事件流 */}
      <Row gutter={[8, 8]}>
        <Col xs={24} lg={16}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>测试车辆运营状态</h3>
            <Table
              dataSource={vehicles}
              columns={vehicleColumns}
              rowKey="vehicle_id"
              size="small"
              pagination={{ pageSize: 8, size: 'small', hideOnSinglePage: true }}
              scroll={{ x: 1000 }}
            />
          </div>
        </Col>
        <Col xs={24} lg={8}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>运营事件流</h3>
            <div style={{ maxHeight: 400, overflow: 'auto' }}>
              {events.length === 0 ? <Empty /> : events.map((ev, i) => (
                <div key={i} style={{
                  padding: '8px 0',
                  borderBottom: '1px solid rgba(105,240,174,0.08)',
                  fontSize: 12,
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <Tag color={ev.level === 'warning' ? 'orange' : 'green'}>
                      {ev.title}
                    </Tag>
                    <span style={{ color: 'rgba(224,245,232,0.4)', fontSize: 10 }}>
                      {dayjs(ev.timestamp).format('MM-DD HH:mm')}
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
