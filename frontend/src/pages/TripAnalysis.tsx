// 氢智行 H2Brain - 精细化行程分析 Dashboard
// 基于真实氢能车辆遥测数据，对标参考设计图
import { useState, useEffect, useMemo, useRef } from 'react'
import { Card, Select, Row, Col, Table, Spin, Empty, Tag, Statistic, Button, Modal, Upload, message, Tooltip, Progress, Collapse } from 'antd'
import { UploadOutlined, FileTextOutlined, ThunderboltOutlined, WarningOutlined, BarChartOutlined, ExperimentOutlined, InfoCircleOutlined } from '@ant-design/icons'
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

/** 多维证据矩阵 - 单特征证据项 */
interface EvidenceItem {
  feature: string
  feature_label: string
  unit: string
  value: number
  expected_low: number
  expected_high: number
  expected: string
  match_ratio: number
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
  // ---- v2 多维证据矩阵新增 ----
  /** 置信度 0-1 */
  confidence?: number
  /** 人类可读判定依据 */
  verdict?: string
  /** 6 类路况得分对比 */
  class_scores?: Record<string, number>
  /** 7 维特征逐项证据 */
  evidence?: EvidenceItem[]
  start_iso?: string
  end_iso?: string
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
  // ---- v2 新增 GPS 轨迹 (null = GPS 无效) ----
  gps_lon?: (number | null)[]
  gps_lat?: (number | null)[]
}

interface RoadBand {
  start_min: number
  end_min: number
  road_type: string
  color: string
  /** v2 新增: 置信度 0-1 */
  confidence?: number
}

/** 多维证据矩阵 - 方法论说明 */
interface MethodologyFeature {
  key: string
  label: string
  unit: string
}

interface RoadMethodology {
  name: string
  version: string
  window: string
  features: MethodologyFeature[]
  classes: string[]
  rationale: string
  vs_old: string
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
  /** v2 多维证据矩阵路况识别方法论 */
  road_methodology?: RoadMethodology
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

/** 根据背景色亮度返回黑或白文字色，保证对比度 */
function getContrastColor(hex: string): string {
  if (!hex || !hex.startsWith('#')) return '#fff'
  const c = hex.replace('#', '')
  const r = parseInt(c.substring(0, 2), 16)
  const g = parseInt(c.substring(2, 4), 16)
  const b = parseInt(c.substring(4, 6), 16)
  // 相对亮度 (WCAG 简化版)
  const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
  return luminance > 0.55 ? '#1a1a1a' : '#fff'
}

/** 6 类路况颜色兜底 (与后端 ROAD_COLORS 一致, 运行时以 road_bands/segments 实际颜色优先) */
const ROAD_CLASS_COLORS: Record<string, string> = {
  '高速': '#2196F3',
  '城市-快速路': '#FF9800',
  '城市-国道': '#4CAF50',
  '山区': '#9C27B0',
  '怠速': '#F44336',
  '场区-装卸': '#E91E63',
}

/** 匹配率 → 颜色 (高=绿, 中=黄, 低=红) */
function matchRatioColor(ratio: number): string {
  if (ratio >= 0.8) return '#69F0AE'
  if (ratio >= 0.5) return '#FFB347'
  return '#FF6B6B'
}

/** 置信度 → 颜色 */
function confidenceColor(c: number): string {
  if (c >= 0.95) return '#69F0AE'
  if (c >= 0.85) return '#FFB347'
  return '#FF6B6B'
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

// ---- Evidence Row (单特征证据条) ----
function EvidenceRow({ ev }: { ev: EvidenceItem }) {
  const ratio = Math.max(0, Math.min(1, ev.match_ratio ?? 0))
  const color = matchRatioColor(ratio)
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, fontSize: 12 }}>
      <span style={{ width: 100, flexShrink: 0, color: 'rgba(224,245,232,0.85)' }}>
        {ev.feature_label}
      </span>
      <span style={{ width: 92, flexShrink: 0, textAlign: 'right', color: '#E0F5E8', fontWeight: 600 }}>
        {fmtNum(ev.value, 2)}
        {ev.unit ? ` ${ev.unit}` : ''}
      </span>
      <span style={{ width: 132, flexShrink: 0, fontSize: 11, color: 'rgba(224,245,232,0.45)' }}>
        期望 {ev.expected}
      </span>
      <div style={{ flex: 1, minWidth: 60, height: 6, background: 'rgba(255,255,255,0.06)', borderRadius: 3 }}>
        <div style={{ width: `${ratio * 100}%`, height: '100%', background: color, borderRadius: 3 }} />
      </div>
      <span style={{ width: 38, flexShrink: 0, textAlign: 'right', color, fontWeight: 600 }}>
        {(ratio * 100).toFixed(0)}%
      </span>
    </div>
  )
}

// ---- Class Scores Chart (6 类得分对比横向条形图) ----
function ClassScoresChart({ scores, winner }: { scores: Record<string, number>; winner: string }) {
  const entries = Object.entries(scores).sort((a, b) => b[1] - a[1])
  if (entries.length === 0) return null
  const option = {
    grid: { left: 88, right: 46, top: 4, bottom: 4 },
    xAxis: { type: 'value', min: 0, max: 1, show: false },
    yAxis: {
      type: 'category',
      data: entries.map((e) => e[0]),
      axisTick: { show: false },
      axisLine: { show: false },
      axisLabel: { color: 'rgba(224,245,232,0.8)', fontSize: 11 },
    },
    series: [
      {
        type: 'bar',
        barWidth: 10,
        data: entries.map(([k, v]) => ({
          value: v,
          itemStyle: {
            color: k === winner ? '#69F0AE' : 'rgba(105,240,174,0.25)',
            borderRadius: 2,
          },
        })),
        label: {
          show: true,
          position: 'right',
          fontSize: 10,
          color: 'rgba(224,245,232,0.6)',
          formatter: (p: any) => Number(p.value).toFixed(3),
        },
      },
    ],
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => `${p.name}: ${Number(p.value).toFixed(3)}`,
    },
  }
  return <ReactECharts option={option} style={{ height: entries.length * 26 + 8 }} />
}

// ---- Road Evidence Panel (展开行: 判定依据 + 7 维证据 + 6 类得分) ----
function RoadEvidencePanel({ seg }: { seg: RoadSegment }) {
  return (
    <div style={{ padding: '4px 4px 8px' }}>
      {seg.verdict && (
        <div
          style={{
            marginBottom: 10,
            padding: '8px 12px',
            fontSize: 12,
            lineHeight: 1.8,
            color: 'rgba(224,245,232,0.82)',
            background: 'rgba(105,240,174,0.06)',
            border: '1px solid rgba(105,240,174,0.15)',
            borderRadius: 6,
          }}
        >
          <span style={{ color: '#69F0AE', fontWeight: 700 }}>判定依据: </span>
          {seg.verdict}
        </div>
      )}
      <Row gutter={[16, 8]}>
        <Col xs={24} md={13}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#69F0AE', marginBottom: 6 }}>
            特征证据矩阵 · {seg.evidence?.length ?? 0} 维逐项匹配
          </div>
          {seg.evidence?.map((ev) => (
            <EvidenceRow key={ev.feature} ev={ev} />
          ))}
        </Col>
        <Col xs={24} md={11}>
          <div style={{ fontSize: 12, fontWeight: 600, color: '#69F0AE', marginBottom: 6 }}>
            6 类路况得分对比 · 判定「{seg.road_type}」
          </div>
          <ClassScoresChart scores={seg.class_scores ?? {}} winner={seg.road_type} />
        </Col>
      </Row>
    </div>
  )
}

// ---- Methodology Card (可折叠方法论说明) ----
function MethodologyCard({
  methodology,
  roadBands,
}: {
  methodology: RoadMethodology
  roadBands: RoadBand[]
}) {
  const colorMap = useMemo(() => {
    const m: Record<string, string> = { ...ROAD_CLASS_COLORS }
    for (const b of roadBands) m[b.road_type] = b.color
    return m
  }, [roadBands])

  return (
    <Collapse
      size="small"
      style={{ marginBottom: 8 }}
      items={[
        {
          key: 'm',
          label: (
            <span style={{ fontSize: 13 }}>
              <InfoCircleOutlined style={{ color: '#69F0AE', marginRight: 6 }} />
              <span style={{ color: '#69F0AE', fontWeight: 700 }}>
                方法论 · {methodology.name} v{methodology.version}
              </span>
              <span style={{ color: 'rgba(224,245,232,0.45)', marginLeft: 10, fontSize: 12 }}>
                完全可解释的多维证据矩阵 · 点击展开详情
              </span>
            </span>
          ),
          children: (
            <div style={{ fontSize: 12, color: 'rgba(224,245,232,0.75)', lineHeight: 1.9 }}>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: '#69F0AE', fontWeight: 600 }}>窗口与平滑: </span>
                {methodology.window}
              </div>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: '#69F0AE', fontWeight: 600 }}>
                  识别类别 ({methodology.classes.length} 类):{' '}
                </span>
                {methodology.classes.map((c) => {
                  const color = colorMap[c] ?? '#888888'
                  return (
                    <Tag
                      key={c}
                      style={{
                        fontSize: 11,
                        background: `${color}20`,
                        borderColor: `${color}50`,
                        color,
                      }}
                    >
                      {c}
                    </Tag>
                  )
                })}
              </div>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: '#69F0AE', fontWeight: 600 }}>
                  特征 ({methodology.features.length} 维):{' '}
                </span>
                {methodology.features.map((f) => (
                  <Tag
                    key={f.key}
                    style={{
                      fontSize: 11,
                      background: 'rgba(105,240,174,0.08)',
                      borderColor: 'rgba(105,240,174,0.25)',
                      color: 'rgba(224,245,232,0.85)',
                    }}
                  >
                    {f.label}
                    {f.unit ? ` (${f.unit})` : ''}
                  </Tag>
                ))}
              </div>
              <div style={{ marginBottom: 4 }}>
                <span style={{ color: '#69F0AE', fontWeight: 600 }}>原理: </span>
                {methodology.rationale}
              </div>
              <div>
                <span style={{ color: '#FFB347', fontWeight: 600 }}>vs 旧版: </span>
                {methodology.vs_old}
              </div>
            </div>
          ),
        },
      ]}
    />
  )
}

// ---- GPS Trajectory Map (按路况着色, 经纬度散点+连线, 无需地图底图) ----
function GpsMap({ ts, roadBands }: { ts: TimeSeries; roadBands: RoadBand[] }) {
  const H = 400
  const wrapRef = useRef<HTMLDivElement>(null)
  const [wrapW, setWrapW] = useState(0)

  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => setWrapW(el.clientWidth)
    update()
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const { hasGps, option } = useMemo(() => {
    const lons = ts.gps_lon ?? []
    const lats = ts.gps_lat ?? []
    const times = ts.timestamps ?? []
    const pts: { t: number; lon: number; lat: number }[] = []
    for (let i = 0; i < Math.min(lons.length, lats.length); i++) {
      const lo = lons[i]
      const la = lats[i]
      if (lo == null || la == null) continue
      pts.push({ t: times[i] ?? 0, lon: lo, lat: la })
    }
    if (pts.length < 2) return { hasGps: false, option: null }

    // 按 road_band 时间区间分组 → 每个区间一条 polyline, 同类合并为一个 series (图例去重)
    const byType = new Map<
      string,
      { color: string; polylines: { coords: [number, number][]; label: string }[] }
    >()
    for (const b of roadBands) {
      const coords: [number, number][] = []
      for (const p of pts) {
        if (p.t >= b.start_min && p.t <= b.end_min) coords.push([p.lon, p.lat])
      }
      if (coords.length < 2) continue
      const entry = byType.get(b.road_type) ?? { color: b.color, polylines: [] }
      entry.polylines.push({
        coords,
        label: `${fmtNum(b.start_min, 0)}~${fmtNum(b.end_min, 0)} min`,
      })
      byType.set(b.road_type, entry)
    }

    // 经纬度包围盒 + 3% 边距
    let minLon = Infinity
    let maxLon = -Infinity
    let minLat = Infinity
    let maxLat = -Infinity
    for (const p of pts) {
      if (p.lon < minLon) minLon = p.lon
      if (p.lon > maxLon) maxLon = p.lon
      if (p.lat < minLat) minLat = p.lat
      if (p.lat > maxLat) maxLat = p.lat
    }
    const padLon = Math.max((maxLon - minLon) * 0.03, 1e-4)
    const padLat = Math.max((maxLat - minLat) * 0.03, 1e-4)
    const lon0 = minLon - padLon
    const lon1 = maxLon + padLon
    const lat0 = minLat - padLat
    const lat1 = maxLat + padLat

    // 等比网格: 按当地经纬度实际距离换算, 保证轨迹不变形
    const latMid = (minLat + maxLat) / 2
    const kmPerLon = 111.32 * Math.cos((latMid * Math.PI) / 180)
    const kmPerLat = 110.57
    const trackW = (lon1 - lon0) * kmPerLon
    const trackH = (lat1 - lat0) * kmPerLat
    const chartW = wrapW > 60 ? wrapW : 700
    const availW = chartW - 16
    const availH = H - 44 - 10 // 顶部图例区 + 底部余量
    const scale = Math.min(availW / trackW, availH / trackH)
    const gridW = Math.max(Math.min(availW, trackW * scale), 10)
    const gridH = Math.max(Math.min(availH, trackH * scale), 10)
    const gridLeft = (chartW - gridW) / 2
    const gridTop = 40 + (availH - gridH) / 2

    const series: object[] = []
    for (const [type, entry] of byType) {
      series.push({
        name: type,
        type: 'lines',
        coordinateSystem: 'cartesian2d',
        polyline: true,
        lineStyle: { color: entry.color, width: 3, opacity: 0.9 },
        emphasis: { lineStyle: { width: 5 } },
        data: entry.polylines.map((pl) => ({ coords: pl.coords, label: pl.label })),
      })
    }
    const first = pts[0]
    const last = pts[pts.length - 1]
    series.push({
      name: '起点',
      type: 'scatter',
      z: 10,
      data: [{ value: [first.lon, first.lat] }],
      symbolSize: 12,
      itemStyle: { color: '#FF5252', borderColor: 'rgba(255,255,255,0.9)', borderWidth: 1.5 },
    })
    series.push({
      name: '终点',
      type: 'scatter',
      z: 10,
      data: [{ value: [last.lon, last.lat] }],
      symbolSize: 12,
      itemStyle: { color: '#69F0AE', borderColor: 'rgba(255,255,255,0.9)', borderWidth: 1.5 },
    })

    const opt = {
      tooltip: {
        trigger: 'item',
        formatter: (p: any) => {
          const extra = p?.data?.label ? `<br/>时段: ${p.data.label}` : ''
          const coord =
            p?.data?.value != null
              ? `<br/>${p.data.value[0].toFixed(4)}°E, ${p.data.value[1].toFixed(4)}°N`
              : ''
          return `<b>${p.seriesName}</b>${extra}${coord}`
        },
      },
      legend: {
        top: 2,
        left: 'center',
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: 'rgba(224,245,232,0.75)', fontSize: 11 },
        data: [...byType.keys(), '起点', '终点'],
      },
      grid: { left: gridLeft, top: gridTop, width: gridW, height: gridH },
      xAxis: {
        type: 'value',
        min: lon0,
        max: lon1,
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { show: true, lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      },
      yAxis: {
        type: 'value',
        min: lat0,
        max: lat1,
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { show: true, lineStyle: { color: 'rgba(255,255,255,0.05)' } },
      },
      series,
    }
    return { hasGps: true, option: opt }
  }, [ts, roadBands, wrapW])

  if (!hasGps || !option) {
    return <Empty description="该行程无 GPS 数据" style={{ padding: '80px 0' }} />
  }
  return (
    <div ref={wrapRef} style={{ width: '100%' }}>
      <ReactECharts option={option} style={{ height: H }} notMerge />
    </div>
  )
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
        <Tag style={{
          backgroundColor: r.color,
          color: getContrastColor(r.color),
          border: 'none',
          fontWeight: 600,
        }}>
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
    {
      title: '置信度',
      dataIndex: 'confidence',
      width: 118,
      render: (_: any, r: RoadSegment) => {
        if (r.road_type === '合计' || r.confidence == null) {
          return <span style={{ color: 'rgba(224,245,232,0.35)' }}>—</span>
        }
        const color = confidenceColor(r.confidence)
        return (
          <Tooltip title={`判定「${r.road_type}」综合置信度 ${(r.confidence * 100).toFixed(1)}% · 展开行查看证据链`}>
            <Progress
              percent={r.confidence * 100}
              size="small"
              strokeColor={color}
              format={(p) => (
                <span style={{ color, fontSize: 11 }}>
                  {((p === undefined ? 0 : p) / 100).toFixed(3)}
                </span>
              )}
            />
          </Tooltip>
        )
      },
    },
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
      expandable={{
        expandedRowRender: (r: RoadSegment) => <RoadEvidencePanel seg={r} />,
        rowExpandable: (r: RoadSegment) =>
          r.road_type !== '合计' &&
          !!(r.verdict || r.evidence?.length || r.class_scores),
      }}
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
              fontSize: 11,
              fontWeight: 600,
              color: getContrastColor(b.color),
              overflow: 'hidden',
              whiteSpace: 'nowrap',
            }}
            title={`${b.road_type} (${fmtNum(b.start_min, 0)}~${fmtNum(b.end_min, 0)}min)${
              b.confidence != null ? ` · 置信度 ${(b.confidence * 100).toFixed(1)}%` : ''
            }`}
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
        <Tag style={{
          backgroundColor: r.color,
          color: getContrastColor(r.color),
          border: 'none',
          fontWeight: 600,
        }}>
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
                  路况标签 · 工况引擎自动识别（多维证据矩阵 v2 · 点击行展开证据链）
                </span>
              }
              style={{ marginBottom: 12, background: 'rgba(10,46,31,0.4)' }}
            >
              {tripDetail.road_methodology && (
                <MethodologyCard
                  methodology={tripDetail.road_methodology}
                  roadBands={tripDetail.road_bands}
                />
              )}
              <RoadTable segments={tripDetail.road_segments} />
              <ColorBar bands={tripDetail.road_bands} />
            </Card>

            {/* GPS Trajectory Map */}
            <Card
              size="small"
              title={
                <span style={{ color: '#69F0AE' }}>
                  🛰 GPS 行程轨迹 · 按路况着色
                </span>
              }
              style={{ marginBottom: 12, background: 'rgba(10,46,31,0.4)' }}
            >
              <GpsMap ts={tripDetail.time_series} roadBands={tripDetail.road_bands} />
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
                  height: 22,
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
                        fontSize: 11,
                        fontWeight: 600,
                        color: getContrastColor(b.color),
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
