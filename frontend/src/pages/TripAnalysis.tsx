// 氢智行 H2Brain - 精细化行程分析 Dashboard
// 基于真实氢能车辆遥测数据，对标参考设计图
import { useState, useEffect, useMemo, useRef } from 'react'
import { Card, Select, Row, Col, Table, Spin, Empty, Tag, Statistic, Button, Modal, Upload, message, Tooltip, Progress } from 'antd'
import { UploadOutlined, FileTextOutlined, ThunderboltOutlined, WarningOutlined, BarChartOutlined, ExperimentOutlined } from '@ant-design/icons'
import type { UploadProps } from 'antd'
import ReactECharts from 'echarts-for-react'
import { apiGet, apiPost } from '@/lib/request'

// ---- Types ----
interface TripSummary {
  trip_id: number
  vehicle_id: string
  date: string
  start_time: string
  end_time: string
  duration_h: number
  distance_km: number
  avg_speed: number
  max_speed: number
  h2_consumed_kg: number
  h2_per_100km: number
  stack_power_avg: number
  stack_power_max: number
  soc_start: number
  soc_end: number
  h2_start: number
  h2_end: number
  h2_percent_start: number
  h2_percent_end: number
  gps_start: [number, number]
  gps_end: [number, number]
  weather_summary?: string
}

interface RoadSegment {
  road_type: string
  color: string
  start_time: string
  end_time: string
  duration_h: number
  distance_km: number
  avg_speed: number
  h2_consumed_kg: number
  h2_per_100km: number
  stack_power_kw: number
  load_changes: number
}

interface PowerMode {
  mode: string
  color: string
  start_time: string
  end_time: string
  duration_min: number
  soc_start: number
  soc_end: number
  soc_change: number
  h2_start: number
  h2_end: number
  avg_power_kw: number
}

interface LoadChange {
  time: string
  timestamp_idx: number
  power_before: number
  power_after: number
  delta: number
  type: string
}

interface TimeSeries {
  timestamps: number[]
  speed: number[]
  stack_power: number[]
  batt_soc: number[]
  h2_remain: number[]
  h2_percent: number[]
  batt_cur: number[]
  high_pressure: number[]
  stack_temp_in: number[]
  h2_consumed_cum: number[]
}

interface RoadBand {
  start_min: number
  end_min: number
  road_type: string
  color: string
}

interface ModeBand {
  start_min: number
  end_min: number
  mode: string
  color: string
}

interface AnomalyReason {
  factor: string
  detail: string
  impact: string
}

interface Anomaly {
  segment_time: string
  road_type: string
  h2_per_100km: number
  trip_avg: number
  deviation_pct: number
  reasons: AnomalyReason[]
  suggestion: string
}

interface DrivingBehavior {
  type: string
  time: string
  timestamp_idx: number
  severity: number
  speed: number
  description: string
}

interface FactorItem {
  factor: string
  correlation: number
  strength: string
  direction: string
}

interface FactorAnalysis {
  factors: FactorItem[]
  summary: string
  minute_count: number
}

interface BenchmarkItem {
  trip_id: number
  date: string
  start_time: string
  distance_km: number
  duration_h: number
  h2_consumed_kg: number
  h2_per_100km: number
  avg_speed: number
  max_power: number
  vs_avg: number
  rating: string
}

interface Benchmark {
  comparisons: BenchmarkItem[]
  summary: string
  avg_h2_per_100km: number
  best_trip_id: number
  worst_trip_id: number
}

interface ReportSection {
  title: string
  content: string
}

interface AnalysisReport {
  vehicle_id: string
  trip_id: number
  generated_at: string
  sections: ReportSection[]
  recommendations: string[]
}

interface WeatherInfo {
  weather_summary: string
  avg_temperature: number | null
  weather_start: { label: string; temp: number; wind: number } | null
  weather_mid: { label: string; temp: number; wind: number } | null
  weather_end: { label: string; temp: number; wind: number } | null
}

interface TripDetail {
  overview: TripSummary
  road_segments: RoadSegment[]
  power_modes: PowerMode[]
  load_changes: LoadChange[]
  load_change_count: number
  time_series: TimeSeries
  road_bands: RoadBand[]
  mode_bands: ModeBand[]
  anomalies: Anomaly[]
  driving_behaviors: DrivingBehavior[]
  factor_analysis: FactorAnalysis
  weather?: WeatherInfo | null
}

interface Vehicle {
  vehicle_id: string
  label: string
  region: string
  total_rows: number
  total_trips: number
  total_distance_km: number
  total_h2_consumed_kg: number
  date_range: string
  avg_h2_per_100km: number
}

// ---- Helpers ----
function fmtDuration(h: number): string {
  if (!h || isNaN(h)) return '—'
  const hh = Math.floor(h)
  const mm = Math.round((h - hh) * 60)
  return `${hh}h ${mm}min`
}

function fmtNum(v: number | undefined | null, digits = 1): string {
  if (v === undefined || v === null || isNaN(v)) return '—'
  return v.toFixed(digits)
}

function fmtGPS(gps: [number, number]): string {
  if (!gps || gps.length < 2) return '—'
  return `${gps[0].toFixed(4)}, ${gps[1].toFixed(4)}`
}

// ---- Chart Background Bands ----
function buildMarkAreas(bands: { start_min: number; end_min: number; color: string }[]) {
  return bands.map((b) => [
    { xAxis: b.start_min, itemStyle: { color: b.color + '30' } },
    { xAxis: b.end_min },
  ])
}

// ---- Speed Chart ----
function SpeedChart({ ts, roadBands }: { ts: TimeSeries; roadBands: RoadBand[] }) {
  const option = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ts.timestamps,
      name: 'min',
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', name: 'km/h', scale: true },
    series: [
      {
        type: 'line',
        data: ts.speed,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#00E5FF' },
        areaStyle: { color: 'rgba(0,229,255,0.08)' },
        markArea: {
          silent: true,
          data: buildMarkAreas(roadBands),
        },
      },
    ],
  }), [ts, roadBands])
  return <ReactECharts option={option} style={{ height: 220 }} />
}

// ---- Stack Power Chart ----
function StackPowerChart({ ts, roadBands }: { ts: TimeSeries; roadBands: RoadBand[] }) {
  const option = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ts.timestamps,
      name: 'min',
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', name: 'kW', scale: true },
    series: [
      {
        type: 'line',
        data: ts.stack_power,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#FF9800' },
        areaStyle: { color: 'rgba(255,152,0,0.08)' },
        markArea: {
          silent: true,
          data: buildMarkAreas(roadBands),
        },
      },
    ],
  }), [ts, roadBands])
  return <ReactECharts option={option} style={{ height: 220 }} />
}

// ---- Load Change Events Chart ----
function LoadChangeChart({
  ts,
  roadBands,
  loadChanges,
}: {
  ts: TimeSeries
  roadBands: RoadBand[]
  loadChanges: LoadChange[]
}) {
  // Map load changes to x-axis positions (find nearest timestamp index)
  const changePoints = useMemo(() => {
    return loadChanges.map((lc) => {
      // Find nearest timestamp
      let minDist = Infinity
      let nearestIdx = 0
      for (let i = 0; i < ts.timestamps.length; i++) {
        const dist = Math.abs(ts.timestamps[i] - lc.timestamp_idx / 60)
        if (dist < minDist) {
          minDist = dist
          nearestIdx = i
        }
      }
      return { idx: nearestIdx, delta: lc.delta, type: lc.type }
    })
  }, [loadChanges, ts.timestamps])

  const option = useMemo(() => ({
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex
        if (idx === undefined) return ''
        const pt = changePoints.find((p) => p.idx === idx)
        if (pt) {
          return `变载事件<br/>类型: ${pt.type}<br/>功率变化: ${fmtNum(pt.delta, 1)} kW`
        }
        return `时间: ${ts.timestamps[idx]} min`
      },
    },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ts.timestamps,
      name: 'min',
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', name: 'kW', scale: true },
    series: [
      {
        type: 'scatter',
        data: ts.timestamps.map((_, i) => {
          const pt = changePoints.find((p) => p.idx === i)
          return pt ? pt.delta : null
        }),
        symbolSize: 6,
        itemStyle: {
          color: (params: any) => {
            const v = params.value
            if (v === null || v === undefined) return 'transparent'
            return v > 0 ? '#FF5252' : '#4CAF50'
          },
        },
        markArea: {
          silent: true,
          data: buildMarkAreas(roadBands),
        },
      },
      {
        type: 'line',
        data: ts.timestamps.map(() => 0),
        symbol: 'none',
        lineStyle: { width: 0.5, color: 'rgba(255,255,255,0.15)' },
      },
    ],
  }), [ts, roadBands, changePoints])
  return <ReactECharts option={option} style={{ height: 220 }} />
}

// ---- Battery Current Chart ----
function BattCurChart({ ts, roadBands }: { ts: TimeSeries; roadBands: RoadBand[] }) {
  const option = useMemo(() => ({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ts.timestamps,
      name: 'min',
      axisLabel: { fontSize: 10 },
    },
    yAxis: { type: 'value', name: 'A', scale: true },
    series: [
      {
        type: 'line',
        data: ts.batt_cur,
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 1.5, color: '#E040FB' },
        areaStyle: { color: 'rgba(224,64,251,0.06)' },
        markArea: {
          silent: true,
          data: buildMarkAreas(roadBands),
        },
        markLine: {
          silent: true,
          symbol: 'none',
          data: [{ yAxis: 0, lineStyle: { color: 'rgba(255,255,255,0.2)', type: 'dashed' } }],
        },
      },
    ],
  }), [ts, roadBands])
  return <ReactECharts option={option} style={{ height: 220 }} />
}

// ---- Road Condition Table ----
function RoadTable({ segments }: { segments: RoadSegment[] }) {
  const columns = [
    {
      title: '时间段',
      dataIndex: 'start_time',
      render: (_: any, r: RoadSegment) => `${r.start_time}~${r.end_time}`,
    },
    {
      title: '路况',
      dataIndex: 'road_type',
      render: (text: string, r: RoadSegment) => (
        <Tag color={r.color} style={{ color: '#fff' }}>
          {text}
        </Tag>
      ),
    },
    { title: '里程 km', dataIndex: 'distance_km', render: (v: number) => fmtNum(v) },
    { title: '均速', dataIndex: 'avg_speed', render: (v: number) => (v > 0 ? fmtNum(v) : '—') },
    { title: '氢耗 kg', dataIndex: 'h2_consumed_kg', render: (v: number) => fmtNum(v, 2) },
    {
      title: '百公里氢耗',
      dataIndex: 'h2_per_100km',
      render: (v: number) => (v > 0 ? fmtNum(v, 2) : '—'),
    },
    { title: '电堆 kW', dataIndex: 'stack_power_kw', render: (v: number) => fmtNum(v) },
    { title: '变载', dataIndex: 'load_changes' },
  ]

  const totalRow: RoadSegment = {
    road_type: '合计',
    color: '#666',
    start_time: '—',
    end_time: '—',
    duration_h: segments.reduce((s, r) => s + r.duration_h, 0),
    distance_km: segments.reduce((s, r) => s + r.distance_km, 0),
    avg_speed: 0,
    h2_consumed_kg: segments.reduce((s, r) => s + r.h2_consumed_kg, 0),
    h2_per_100km: 0,
    stack_power_kw: 0,
    load_changes: segments.reduce((s, r) => s + r.load_changes, 0),
  }

  const data = [...segments, totalRow]

  return (
    <Table
      columns={columns}
      dataSource={data}
      rowKey={(_, i) => String(i)}
      pagination={false}
      size="small"
      rowClassName={(_, i) => (i === data.length - 1 ? 'trip-total-row' : '')}
    />
  )
}

// ---- Color Bar ----
function ColorBar({ bands }: { bands: RoadBand[] }) {
  const totalMin = bands[bands.length - 1]?.end_min || 1
  return (
    <div style={{ display: 'flex', height: 24, borderRadius: 4, overflow: 'hidden', marginTop: 8 }}>
      {bands.map((b, i) => {
        const width = ((b.end_min - b.start_min) / totalMin) * 100
        return (
          <div
            key={i}
            style={{
              width: `${width}%`,
              background: b.color,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 10,
              color: '#fff',
              overflow: 'hidden',
              whiteSpace: 'nowrap',
            }}
            title={`${b.road_type} (${fmtNum(b.start_min, 0)}~${fmtNum(b.end_min, 0)}min)`}
          >
            {width > 5 ? b.road_type : ''}
          </div>
        )
      })}
    </div>
  )
}

// ---- Power Mode Table ----
function ModeTable({ modes }: { modes: PowerMode[] }) {
  const columns = [
    {
      title: '时间段',
      dataIndex: 'start_time',
      render: (_: any, r: PowerMode) => `${r.start_time}~${r.end_time}`,
    },
    {
      title: '动力模式',
      dataIndex: 'mode',
      render: (text: string, r: PowerMode) => (
        <Tag color={r.color} style={{ color: '#fff' }}>
          {text}
        </Tag>
      ),
    },
    {
      title: '持续',
      dataIndex: 'duration_min',
      render: (v: number) => fmtDuration(v / 60),
    },
    {
      title: 'SOC 变化',
      dataIndex: 'soc_change',
      render: (_: any, r: PowerMode) => `${r.soc_start}% → ${r.soc_end}%`,
    },
    {
      title: 'H2%',
      dataIndex: 'h2_start',
      render: (_: any, r: PowerMode) => `${r.h2_start}% → ${r.h2_end}%`,
    },
    {
      title: '均功率 kW',
      dataIndex: 'avg_power_kw',
      render: (v: number) => fmtNum(v),
    },
  ]
  return (
    <Table
      columns={columns}
      dataSource={modes}
      rowKey={(_, i) => String(i)}
      pagination={false}
      size="small"
    />
  )
}

// ---- Main Page ----
export default function TripAnalysis() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [selectedVehicle, setSelectedVehicle] = useState<string>('')
  const [trips, setTrips] = useState<TripSummary[]>([])
  const [selectedTrip, setSelectedTrip] = useState<number>(0)
  const [tripDetail, setTripDetail] = useState<TripDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [benchmark, setBenchmark] = useState<Benchmark | null>(null)
  const [benchLoading, setBenchLoading] = useState(false)
  const [report, setReport] = useState<AnalysisReport | null>(null)
  const [reportLoading, setReportLoading] = useState(false)
  const [reportVisible, setReportVisible] = useState(false)
  const [uploadLoading, setUploadLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    apiGet
      .analysisVehicles()
      .then((res) => {
        setVehicles(res.data)
        if (res.data.length > 0) setSelectedVehicle(res.data[0].vehicle_id)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!selectedVehicle) return
    setLoading(true)
    apiGet
      .analysisTrips(selectedVehicle)
      .then((res) => {
        setTrips(res.data)
        if (res.data.length > 0) setSelectedTrip(res.data[0].trip_id)
      })
      .finally(() => setLoading(false))
  }, [selectedVehicle])

  useEffect(() => {
    if (!selectedVehicle || trips.length === 0) return
    setDetailLoading(true)
    apiGet
      .analysisTripDetail(selectedVehicle, selectedTrip)
      .then((res) => setTripDetail(res.data))
      .finally(() => setDetailLoading(false))
  }, [selectedVehicle, selectedTrip, trips.length])

  // Fetch benchmark when vehicle changes
  useEffect(() => {
    if (!selectedVehicle) return
    setBenchLoading(true)
    apiGet
      .analysisBenchmark(selectedVehicle)
      .then((res) => setBenchmark(res.data))
      .finally(() => setBenchLoading(false))
  }, [selectedVehicle])

  // Generate report
  const handleGenerateReport = () => {
    if (!selectedVehicle) return
    setReportLoading(true)
    setReportVisible(true)
    apiGet
      .analysisReport(selectedVehicle, selectedTrip)
      .then((res) => {
        setReport(res.data)
      })
      .catch(() => {
        message.error('报告生成失败')
      })
      .finally(() => setReportLoading(false))
  }

  // Upload CSV
  const uploadProps: UploadProps = {
    name: 'file',
    accept: '.csv',
    showUploadList: false,
    customRequest: async (options) => {
      const { file, onSuccess, onError } = options
      setUploadLoading(true)
      const formData = new FormData()
      formData.append('file', file as File)
      formData.append('vehicle_id', 'UPLOADED')
      try {
        const res = await apiPost.analysisUpload(formData)
        onSuccess?.(res.data)
        message.success(`上传成功，识别到 ${res.data.trips?.length ?? 0} 个行程`)
        // Refresh vehicle list
        apiGet.analysisVehicles().then((r) => {
          setVehicles(r.data)
          const uploaded = r.data.find((v: Vehicle) => v.vehicle_id === 'UPLOADED')
          if (uploaded) setSelectedVehicle('UPLOADED')
        })
      } catch (err: unknown) {
        onError?.(err as Error)
        message.error('上传失败，请检查文件格式')
      } finally {
        setUploadLoading(false)
      }
    },
  }

  const ov = tripDetail?.overview

  return (
    <div style={{ color: 'rgba(224,245,232,0.85)' }}>
      <Spin spinning={loading || detailLoading}>
        {/* Selector Bar */}
        <Card
          size="small"
          style={{ marginBottom: 12, background: 'rgba(10,46,31,0.6)', border: '1px solid rgba(105,240,174,0.15)' }}
        >
          <Row gutter={16} align="middle">
            <Col>
              <span style={{ color: '#69F0AE', fontWeight: 700, fontSize: 16 }}>
                精细化行程分析
              </span>
            </Col>
            <Col flex="auto" />
            <Col>
              <Select
                value={selectedVehicle}
                onChange={setSelectedVehicle}
                style={{ width: 200 }}
                options={vehicles.map((v) => ({
                  value: v.vehicle_id,
                  label: `${v.vehicle_id} (${v.total_trips}行程 / ${fmtNum(v.total_distance_km, 0)}km)`,
                }))}
              />
            </Col>
            <Col>
              <Select
                value={selectedTrip}
                onChange={setSelectedTrip}
                style={{ width: 320 }}
                options={trips.map((t) => ({
                  value: t.trip_id,
                  label: `#${t.trip_id} ${t.date} ${t.start_time}-${t.end_time} (${fmtNum(t.distance_km, 0)}km)`,
                }))}
              />
            </Col>
            <Col>
              <Button
                type="primary"
                icon={<FileTextOutlined />}
                loading={reportLoading}
                onClick={handleGenerateReport}
                style={{ background: '#1a6e4e', borderColor: '#69F0AE' }}
              >
                生成分析报告
              </Button>
            </Col>
            <Col>
              <Upload {...uploadProps}>
                <Button icon={<UploadOutlined />} loading={uploadLoading}>
                  上传CSV
                </Button>
              </Upload>
            </Col>
          </Row>
        </Card>

        {ov && (
          <>
            {/* Header Info */}
            <div style={{ marginBottom: 12 }}>
              <span style={{ fontSize: 18, fontWeight: 700, color: '#69F0AE' }}>
                {ov.vehicle_id} · 行程 #{ov.trip_id}
              </span>
              <span style={{ marginLeft: 12, color: 'rgba(224,245,232,0.5)', fontSize: 13 }}>
                {ov.date} {ov.start_time}→{ov.end_time} · GPS: {fmtGPS(ov.gps_start)} →{' '}
                {fmtGPS(ov.gps_end)}
                {ov.weather_summary && (
                  <span style={{ marginLeft: 8, color: '#69F0AE' }}>
                    🌤 {ov.weather_summary}
                  </span>
                )}
              </span>
            </div>

            {/* Overview Metric Cards */}
            <Row gutter={[8, 8]} style={{ marginBottom: 12 }}>
              <Col xs={12} md={4}>
                <Card size="small" style={{ background: 'rgba(10,46,31,0.4)', textAlign: 'center' }}>
                  <Statistic title="全程时长" value={fmtDuration(ov.duration_h)} />
                </Card>
              </Col>
              <Col xs={12} md={4}>
                <Card size="small" style={{ background: 'rgba(10,46,31,0.4)', textAlign: 'center' }}>
                  <Statistic title="均速 km/h" value={fmtNum(ov.avg_speed)} />
                </Card>
              </Col>
              <Col xs={12} md={4}>
                <Card size="small" style={{ background: 'rgba(10,46,31,0.4)', textAlign: 'center' }}>
                  <Statistic title="总里程 km" value={fmtNum(ov.distance_km)} />
                </Card>
              </Col>
              <Col xs={12} md={4}>
                <Card size="small" style={{ background: 'rgba(10,46,31,0.4)', textAlign: 'center' }}>
                  <Statistic title="总氢耗 kg" value={fmtNum(ov.h2_consumed_kg, 2)} />
                </Card>
              </Col>
              <Col xs={12} md={4}>
                <Card size="small" style={{ background: 'rgba(10,46,31,0.4)', textAlign: 'center' }}>
                  <Statistic title="百公里氢耗" value={fmtNum(ov.h2_per_100km, 2)} suffix="kg" />
                </Card>
              </Col>
              <Col xs={12} md={4}>
                <Card size="small" style={{ background: 'rgba(10,46,31,0.4)', textAlign: 'center' }}>
                  <Statistic
                    title="电堆kW / 变载"
                    value={`${fmtNum(ov.stack_power_avg, 0)} / ${tripDetail?.load_change_count ?? 0}`}
                  />
                </Card>
              </Col>
            </Row>

            {/* Road Condition Table */}
            <Card
              size="small"
              title={
                <span style={{ color: '#69F0AE' }}>
                  路况标签 · 工况引擎自动识别
                </span>
              }
              style={{ marginBottom: 12, background: 'rgba(10,46,31,0.4)' }}
            >
              <RoadTable segments={tripDetail.road_segments} />
              <ColorBar bands={tripDetail.road_bands} />
            </Card>

            {/* 4 Charts */}
            <Card
              size="small"
              title={
                <span style={{ color: '#69F0AE' }}>
                  行程走势图 · 色块与上方路况标签一一对应
                </span>
              }
              style={{ marginBottom: 12, background: 'rgba(10,46,31,0.4)' }}
            >
              <Row gutter={[8, 8]}>
                <Col xs={24} md={12}>
                  <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.6)', marginBottom: 4 }}>
                    车速 (km/h)
                  </div>
                  <SpeedChart ts={tripDetail.time_series} roadBands={tripDetail.road_bands} />
                </Col>
                <Col xs={24} md={12}>
                  <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.6)', marginBottom: 4 }}>
                    电堆功率 (kW)
                  </div>
                  <StackPowerChart
                    ts={tripDetail.time_series}
                    roadBands={tripDetail.road_bands}
                  />
                </Col>
                <Col xs={24} md={12}>
                  <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.6)', marginBottom: 4 }}>
                    变载事件 ({'ΔP > 20kW / 5s'})
                  </div>
                  <LoadChangeChart
                    ts={tripDetail.time_series}
                    roadBands={tripDetail.road_bands}
                    loadChanges={tripDetail.load_changes}
                  />
                </Col>
                <Col xs={24} md={12}>
                  <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.6)', marginBottom: 4 }}>
                    电池电流 (A)
                  </div>
                  <BattCurChart ts={tripDetail.time_series} roadBands={tripDetail.road_bands} />
                </Col>
              </Row>
            </Card>

            {/* Power Mode Table */}
            <Card
              size="small"
              title={
                <span style={{ color: '#69F0AE' }}>
                  车况标签 · 动力系统运行模式识别
                </span>
              }
              style={{ background: 'rgba(10,46,31,0.4)' }}
            >
              {/* Mode color bar */}
              <div
                style={{
                  display: 'flex',
                  height: 20,
                  borderRadius: 4,
                  overflow: 'hidden',
                  marginBottom: 8,
                }}
              >
                {tripDetail.mode_bands.map((b, i) => {
                  const totalMin =
                    tripDetail.mode_bands[tripDetail.mode_bands.length - 1]?.end_min || 1
                  const width = ((b.end_min - b.start_min) / totalMin) * 100
                  return (
                    <div
                      key={i}
                      style={{
                        width: `${width}%`,
                        background: b.color,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 9,
                        color: '#fff',
                        overflow: 'hidden',
                      }}
                      title={`${b.mode} (${fmtNum(b.start_min, 0)}~${fmtNum(b.end_min, 0)}min)`}
                    >
                      {width > 6 ? b.mode : ''}
                    </div>
                  )
                })}
              </div>
              <ModeTable modes={tripDetail.power_modes} />
            </Card>

            {/* Anomaly Detection */}
            {tripDetail.anomalies && tripDetail.anomalies.length > 0 && (
              <Card
                size="small"
                title={
                  <span style={{ color: '#FF6B6B' }}>
                    <WarningOutlined /> 异常氢耗检测与归因 · 共 {tripDetail.anomalies.length} 个异常段
                  </span>
                }
                style={{ marginTop: 12, background: 'rgba(10,46,31,0.4)', border: '1px solid rgba(255,107,107,0.2)' }}
              >
                {tripDetail.anomalies.map((a, i) => (
                  <div
                    key={i}
                    style={{
                      marginBottom: 12,
                      padding: '8px 12px',
                      background: 'rgba(255,107,107,0.06)',
                      borderRadius: 6,
                      border: '1px solid rgba(255,107,107,0.1)',
                    }}
                  >
                    <Row gutter={8} align="middle">
                      <Col>
                        <Tag color="red">{a.road_type}</Tag>
                      </Col>
                      <Col>
                        <span style={{ color: 'rgba(224,245,232,0.7)', fontSize: 13 }}>
                          {a.segment_time}
                        </span>
                      </Col>
                      <Col>
                        <span style={{ color: '#FF6B6B', fontWeight: 600 }}>
                          {fmtNum(a.h2_per_100km, 2)} kg/100km
                        </span>
                      </Col>
                      <Col>
                        <Tag color={(a.deviation_pct ?? 0) > 100 ? 'volcano' : 'orange'}>
                          偏高 {fmtNum(a.deviation_pct, 1)}%
                        </Tag>
                      </Col>
                    </Row>
                    <div style={{ marginTop: 6, fontSize: 12, color: 'rgba(224,245,232,0.6)' }}>
                      <span style={{ color: '#69F0AE', fontWeight: 600 }}>归因:</span>{' '}
                      {a.reasons.map((r, j) => (
                        <Tag
                          key={j}
                          style={{
                            fontSize: 11,
                            marginBottom: 2,
                            background: 'rgba(255,107,107,0.1)',
                            borderColor: 'rgba(255,107,107,0.2)',
                            color: 'rgba(255,200,200,0.85)',
                          }}
                        >
                          {r.factor}: {r.detail} ({r.impact})
                        </Tag>
                      ))}
                    </div>
                    {a.suggestion && (
                      <div style={{ marginTop: 4, fontSize: 12, color: 'rgba(105,240,174,0.8)' }}>
                        <span style={{ fontWeight: 600 }}>建议:</span> {a.suggestion}
                      </div>
                    )}
                  </div>
                ))}
              </Card>
            )}

            {/* Driving Behavior Analysis */}
            {tripDetail.driving_behaviors && tripDetail.driving_behaviors.length > 0 && (
              <Card
                size="small"
                title={
                  <span style={{ color: '#FFB347' }}>
                    <ThunderboltOutlined /> 驾驶行为分析 · 共 {tripDetail.driving_behaviors.length} 个事件
                  </span>
                }
                style={{ marginTop: 12, background: 'rgba(10,46,31,0.4)' }}
              >
                <Row gutter={[8, 8]} style={{ marginBottom: 8 }}>
                  {(['急加速', '急减速', '超速'] as const).map((bt) => {
                    const count = tripDetail.driving_behaviors!.filter(
                      (b) => b.type === bt
                    ).length
                    const color =
                      bt === '急加速' ? '#FFB347' : bt === '急减速' ? '#FF6B6B' : '#FF4757'
                    return (
                      <Col xs={8} key={bt}>
                        <div
                          style={{
                            textAlign: 'center',
                            padding: '6px 0',
                            background: `${color}15`,
                            borderRadius: 6,
                            border: `1px solid ${color}30`,
                          }}
                        >
                          <div style={{ fontSize: 24, fontWeight: 700, color }}>{count}</div>
                          <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.6)' }}>{bt}</div>
                        </div>
                      </Col>
                    )
                  })}
                </Row>
                <Table
                  size="small"
                  pagination={{ pageSize: 8 }}
                  dataSource={tripDetail.driving_behaviors}
                  rowKey={(_, idx) => String(idx)}
                  columns={[
                    {
                      title: '类型',
                      dataIndex: 'type',
                      width: 80,
                      render: (v: string) => {
                        const color = v === '急加速' ? 'orange' : v === '急减速' ? 'red' : 'volcano'
                        return <Tag color={color}>{v}</Tag>
                      },
                    },
                    {
                      title: '时间',
                      dataIndex: 'time',
                      width: 100,
                    },
                    {
                      title: '车速 km/h',
                      dataIndex: 'speed',
                      width: 100,
                      render: (v: number) => v?.toFixed(1) ?? '—',
                    },
                    {
                      title: '严重度',
                      dataIndex: 'severity',
                      width: 80,
                      render: (v: number) => {
                        const pct = Math.min(v * 100, 100)
                        return (
                          <Progress
                            percent={pct}
                            size="small"
                            strokeColor={v > 0.7 ? '#FF4757' : v > 0.4 ? '#FFB347' : '#69F0AE'}
                          />
                        )
                      },
                    },
                    {
                      title: '描述',
                      dataIndex: 'description',
                    },
                  ]}
                />
              </Card>
            )}

            {/* Factor Analysis */}
            {tripDetail.factor_analysis && tripDetail.factor_analysis.factors.length > 0 && (
              <Card
                size="small"
                title={
                  <span style={{ color: '#69F0AE' }}>
                    <ExperimentOutlined /> 氢耗影响因子分析 · {tripDetail.factor_analysis.minute_count} 分钟样本
                  </span>
                }
                style={{ marginTop: 12, background: 'rgba(10,46,31,0.4)' }}
              >
                <Row gutter={[12, 8]}>
                  {tripDetail.factor_analysis.factors.map((f, i) => {
                    const absR = Math.abs(f.correlation)
                    const barColor =
                      f.direction === '正相关'
                        ? absR > 0.5
                          ? '#FF6B6B'
                          : absR > 0.3
                            ? '#FFB347'
                            : '#69F0AE'
                        : absR > 0.5
                          ? '#4ECDC4'
                          : absR > 0.3
                            ? '#69F0AE'
                            : 'rgba(105,240,174,0.4)'
                    return (
                      <Col xs={24} md={8} key={i}>
                        <div
                          style={{
                            padding: '8px 12px',
                            background: 'rgba(10,46,31,0.5)',
                            borderRadius: 6,
                            border: '1px solid rgba(105,240,174,0.1)',
                          }}
                        >
                          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                            <span style={{ fontSize: 13, color: 'rgba(224,245,232,0.8)' }}>
                              {f.factor}
                            </span>
                            <Tag
                              style={{
                                fontSize: 10,
                                background: `${barColor}20`,
                                borderColor: `${barColor}40`,
                                color: barColor,
                              }}
                            >
                              {f.strength}
                            </Tag>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <div style={{ flex: 1, height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3 }}>
                              <div
                                style={{
                                  width: `${absR * 100}%`,
                                  height: '100%',
                                  background: barColor,
                                  borderRadius: 3,
                                }}
                              />
                            </div>
                            <span style={{ fontSize: 12, color: barColor, fontWeight: 600, minWidth: 60, textAlign: 'right' }}>
                              r={fmtNum(f.correlation, 3)} ({f.direction})
                            </span>
                          </div>
                        </div>
                      </Col>
                    )
                  })}
                </Row>
                {tripDetail.factor_analysis.summary && (
                  <div style={{ marginTop: 8, fontSize: 12, color: 'rgba(224,245,232,0.5)' }}>
                    {tripDetail.factor_analysis.summary}
                  </div>
                )}
              </Card>
            )}

            {/* Weather Tags */}
            {tripDetail.weather && (
              <Card
                size="small"
                title={
                  <span style={{ color: '#69F0AE' }}>
                    🌤 天气标签 · Open-Meteo 气象数据
                  </span>
                }
                style={{ marginTop: 12, background: 'rgba(10,46,31,0.4)' }}
              >
                <Row gutter={[12, 8]}>
                  <Col xs={24} md={6}>
                    <Statistic
                      title="全程天气"
                      value={tripDetail.weather.weather_summary || '—'}
                    />
                  </Col>
                  <Col xs={24} md={6}>
                    <Statistic
                      title="平均气温"
                      value={
                        tripDetail.weather.avg_temperature != null
                          ? `${tripDetail.weather.avg_temperature.toFixed(1)} °C`
                          : '—'
                      }
                    />
                  </Col>
                  {(['weather_start', 'weather_mid', 'weather_end'] as const).map((key) => {
                    const w = tripDetail.weather![key]
                    const labelMap = { weather_start: '起点', weather_mid: '中段', weather_end: '终点' }
                    return (
                      <Col xs={12} md={4} key={key}>
                        <div style={{ textAlign: 'center' }}>
                          <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.45)' }}>
                            {labelMap[key]}
                          </div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: '#E0F5E8' }}>
                            {w ? w.label : '—'}
                          </div>
                          <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.5)' }}>
                            {w ? `${fmtNum(w.temp, 1)}°C · ${fmtNum(w.wind, 1)}m/s` : ''}
                          </div>
                        </div>
                      </Col>
                    )
                  })}
                </Row>
              </Card>
            )}

            {/* Benchmark Comparison */}
            {benchmark && benchmark.comparisons.length > 0 && (
              <Card
                size="small"
                title={
                  <span style={{ color: '#69F0AE' }}>
                    <BarChartOutlined />                     同类行程对标 · {selectedVehicle} 全部 {benchmark.comparisons.length} 个行程 · 平均 {fmtNum(benchmark.avg_h2_per_100km, 2)} kg/100km
                  </span>
                }
                style={{ marginTop: 12, background: 'rgba(10,46,31,0.4)' }}
              >
                <Spin spinning={benchLoading}>
                  <Table
                    size="small"
                    pagination={{ pageSize: 10 }}
                    dataSource={benchmark.comparisons}
                    rowKey="trip_id"
                    rowClassName={(record) =>
                      record.trip_id === selectedTrip ? 'trip-total-row' : ''
                    }
                    columns={[
                      {
                        title: '#',
                        dataIndex: 'trip_id',
                        width: 50,
                        render: (v: number) => `#${v}`,
                      },
                      {
                        title: '日期',
                        dataIndex: 'date',
                        width: 100,
                      },
                      {
                        title: '里程 km',
                        dataIndex: 'distance_km',
                        width: 90,
                        render: (v: number) => v?.toFixed(1) ?? '—',
                        sorter: (a, b) => a.distance_km - b.distance_km,
                      },
                      {
                        title: '时长 h',
                        dataIndex: 'duration_h',
                        width: 80,
                        render: (v: number) => v?.toFixed(1) ?? '—',
                      },
                      {
                        title: '氢耗 kg',
                        dataIndex: 'h2_consumed_kg',
                        width: 90,
                        render: (v: number) => v?.toFixed(2) ?? '—',
                      },
                      {
                        title: '百公里氢耗',
                        dataIndex: 'h2_per_100km',
                        width: 110,
                        render: (v: number) => (
                          <span style={{ fontWeight: 600, color: '#69F0AE' }}>
                            {v?.toFixed(2)}
                          </span>
                        ),
                        sorter: (a, b) => a.h2_per_100km - b.h2_per_100km,
                      },
                      {
                        title: 'vs 均值',
                        dataIndex: 'vs_avg',
                        width: 90,
                          render: (v: number) => {
                            const vv = v ?? 0
                            const color = vv < -5 ? '#69F0AE' : vv > 5 ? '#FF6B6B' : '#FFB347'
                            const sign = vv > 0 ? '+' : ''
                            return (
                              <span style={{ color }}>
                                {sign}
                                {fmtNum(vv, 1)}%
                            </span>
                          )
                        },
                        sorter: (a, b) => a.vs_avg - b.vs_avg,
                      },
                      {
                        title: '评级',
                        dataIndex: 'rating',
                        width: 80,
                        render: (v: string) => {
                          const color =
                            v === '优秀' ? 'green' : v === '良好' ? 'cyan' : v === '偏高' ? 'orange' : 'red'
                          return <Tag color={color}>{v}</Tag>
                        },
                      },
                    ]}
                  />
                </Spin>
              </Card>
            )}
          </>
        )}

        {/* Report Modal */}
        <Modal
          title={
            <span style={{ color: '#69F0AE' }}>
              <FileTextOutlined /> 行程分析报告
            </span>
          }
          open={reportVisible}
          onCancel={() => setReportVisible(false)}
          footer={[
            <Button key="close" onClick={() => setReportVisible(false)}>
              关闭
            </Button>,
          ]}
          width={800}
        >
          <Spin spinning={reportLoading}>
            {report && (
              <div style={{ maxHeight: '70vh', overflowY: 'auto', padding: '0 8px' }}>
                <div style={{ marginBottom: 12, color: 'rgba(224,245,232,0.5)', fontSize: 13 }}>
                  {report.vehicle_id} · 行程 #{report.trip_id} · 生成时间 {report.generated_at}
                </div>
                {report.sections.map((s, i) => (
                  <div key={i} style={{ marginBottom: 16 }}>
                    <h3 style={{ color: '#69F0AE', fontSize: 15, marginBottom: 4 }}>
                      {i + 1}. {s.title}
                    </h3>
                    <div
                      style={{
                        fontSize: 13,
                        color: 'rgba(224,245,232,0.75)',
                        lineHeight: 1.8,
                        whiteSpace: 'pre-wrap',
                      }}
                    >
                      {s.content}
                    </div>
                  </div>
                ))}
                {report.recommendations.length > 0 && (
                  <div
                    style={{
                      padding: 12,
                      background: 'rgba(105,240,174,0.08)',
                      borderRadius: 8,
                      border: '1px solid rgba(105,240,174,0.2)',
                    }}
                  >
                    <h3 style={{ color: '#69F0AE', fontSize: 15, marginBottom: 8 }}>
                      优化建议
                    </h3>
                    {report.recommendations.map((r, i) => (
                      <div
                        key={i}
                        style={{ fontSize: 13, color: 'rgba(224,245,232,0.8)', marginBottom: 4 }}
                      >
                        {i + 1}. {r}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Spin>
        </Modal>

        {!tripDetail && !detailLoading && (
          <Empty description="选择车辆和行程查看分析" />
        )}
      </Spin>

      <style>{`
        .trip-total-row td {
          background: rgba(105,240,174,0.08) !important;
          font-weight: 700;
        }
      `}</style>
    </div>
  )
}
