// 氢智行 H2Brain - 价值量化分析 Dashboard
import { useEffect, useState } from 'react'
import { Spin, Empty, Row, Col, Card, Statistic, Table, Tag, Typography, Divider } from 'antd'
import {
  DollarOutlined, ThunderboltOutlined, CloudOutlined, RiseOutlined,
  ArrowDownOutlined, ArrowUpOutlined, CarOutlined, ExperimentOutlined,
} from '@ant-design/icons'
import ReactECharts from 'echarts-for-react'
import { apiGet } from '@/lib/request'

const { Text, Title } = Typography

interface SensRow {
  value: number
  annual_cost_saved_yuan: number
  payback_years: number | null
  lifetime_savings_yuan: number
}
interface SensScan {
  variable: string
  unit: string
  rows: SensRow[]
}

interface ValueData {
  data_summary: {
    vehicle_count: number
    total_trips: number
    total_distance_km: number
    total_h2_consumed_kg: number
    avg_h2_per_100km: number
    data_period_days: number
  }
  economic: {
    h2_fuel_cost_yuan: number
    h2_maintenance_cost_yuan: number
    h2_total_cost_yuan: number
    h2_cost_per_100km: number
    diesel_fuel_cost_yuan: number
    diesel_maintenance_cost_yuan: number
    diesel_total_cost_yuan: number
    diesel_cost_per_100km: number
    cost_saved_yuan: number
    cost_saved_per_100km: number
    cost_reduction_pct: number
  }
  emission: {
    diesel_co2_kg: number
    h2_co2_green_kg: number
    h2_co2_gray_kg: number
    co2_reduced_green_kg: number
    co2_reduced_gray_kg: number
    co2_reduction_pct_green: number
    co2_per_km_diesel_g: number
    co2_per_km_h2_green_g: number
  }
  annual_projection: {
    annual_km_per_vehicle: number
    annual_total_km: number
    annual_h2_cost: number
    annual_diesel_cost: number
    annual_maintenance_saved: number
    annual_cost_saved: number
    annual_co2_reduced_tons: number
  }
  roi: {
    vehicle_premium_yuan: number
    total_premium_yuan: number
    payback_years: number | null
    lifetime_years: number
    lifetime_savings_yuan: number
    roi_ratio: number
  }
  parameters: Record<string, number>
  sensitivity: {
    method: string
    h2_price: SensScan
    diesel_price: SensScan
    annual_mileage: SensScan
  }
  per_vehicle: Array<{
    vehicle_id: string
    label: string
    region: string
    total_km: number
    h2_consumed_kg: number
    h2_per_100km: number
    h2_cost_yuan: number
    diesel_equivalent_cost_yuan: number
    co2_reduced_kg: number
    cost_saved_yuan: number
  }>
}

const fmtYuan = (n: number) => `${n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} 元`
const fmtKg = (n: number) => `${n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} kg`
const fmtTon = (n: number) => `${n.toFixed(1)} 吨`
const fmtKm = (n: number) => `${n.toLocaleString('zh-CN', { maximumFractionDigits: 0 })} km`

export default function ValueAnalysis() {
  const [data, setData] = useState<ValueData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiGet.analysisValue().then(res => {
      setData(res.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />
  if (!data) return <Empty description="无法加载价值分析数据" />

  const eco = data.economic
  const emi = data.emission
  const ann = data.annual_projection
  const roi = data.roi
  const ds = data.data_summary

  // Cost comparison chart
  const costChart = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['氢能重卡', '柴油重卡'], textStyle: { color: 'rgba(224,245,232,0.6)' } },
    xAxis: { type: 'category', data: ['燃料成本', '维护成本', '总成本'], axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    yAxis: { type: 'value', name: '元', axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    series: [
      {
        name: '氢能重卡',
        type: 'bar',
        data: [eco.h2_fuel_cost_yuan, eco.h2_maintenance_cost_yuan, eco.h2_total_cost_yuan],
        itemStyle: { color: '#69F0AE' },
        barWidth: 30,
      },
      {
        name: '柴油重卡',
        type: 'bar',
        data: [eco.diesel_fuel_cost_yuan, eco.diesel_maintenance_cost_yuan, eco.diesel_total_cost_yuan],
        itemStyle: { color: '#FF7043' },
        barWidth: 30,
      },
    ],
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  }

  // CO2 comparison chart
  const co2Chart = {
    tooltip: { trigger: 'item', formatter: '{b}: {c} kg ({d}%)' },
    legend: { bottom: 0, textStyle: { color: 'rgba(224,245,232,0.6)' } },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      data: [
        { value: emi.co2_reduced_green_kg, name: 'CO2 减排量', itemStyle: { color: '#69F0AE' } },
        { value: emi.h2_co2_green_kg, name: 'H2 排放', itemStyle: { color: '#00E5FF' } },
      ],
      label: { color: 'rgba(224,245,232,0.7)' },
    }],
  }

  // Annual trend chart
  const annualChart = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['氢能成本', '柴油成本', '累计节省'], textStyle: { color: 'rgba(224,245,232,0.6)' } },
    xAxis: { type: 'category', data: ['第1年', '第2年', '第3年', '第4年', '第5年', '第6年', '第7年', '第8年'], axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    yAxis: [
      { type: 'value', name: '年成本(元)', axisLabel: { color: 'rgba(224,245,232,0.5)' } },
      { type: 'value', name: '累计节省(元)', axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    ],
    series: [
      {
        name: '氢能成本',
        type: 'bar',
        data: Array(8).fill(ann.annual_h2_cost),
        itemStyle: { color: 'rgba(105,240,174,0.6)' },
      },
      {
        name: '柴油成本',
        type: 'bar',
        data: Array(8).fill(ann.annual_diesel_cost),
        itemStyle: { color: 'rgba(255,112,67,0.6)' },
      },
      {
        name: '累计节省',
        type: 'line',
        yAxisIndex: 1,
        data: Array.from({ length: 8 }, (_, i) => ann.annual_cost_saved * (i + 1) - roi.total_premium_yuan),
        smooth: true,
        lineStyle: { color: '#00E5FF', width: 2 },
        itemStyle: { color: '#00E5FF' },
        areaStyle: { color: 'rgba(0,229,255,0.1)' },
      },
    ],
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  }

  // 敏感性分析图：单变量扫描，柱=年度节省（按 8 年净节省正负着色），线=回收期（红虚线为 8 年寿命线）
  const sensChart = (scan: SensScan, labelFmt: (v: number) => string) => {
    const rows = scan.rows
    return {
      tooltip: {
        trigger: 'axis',
        formatter: (params: any[]) => {
          const r = rows[params[0].dataIndex]
          const pb = r.payback_years != null ? `${r.payback_years} 年` : '无法回收（年节省≤0）'
          return (
            `<b>${scan.variable} ${labelFmt(r.value)} ${scan.unit}</b><br/>` +
            `年度节省：${(r.annual_cost_saved_yuan / 10000).toFixed(1)} 万元<br/>` +
            `回收期：${pb}<br/>` +
            `8年净节省：${(r.lifetime_savings_yuan / 10000).toFixed(1)} 万元`
          )
        },
      },
      legend: { data: ['年度节省(万元)', '回收期(年)'], textStyle: { color: 'rgba(224,245,232,0.6)' }, top: 0 },
      xAxis: { type: 'category', data: rows.map(r => labelFmt(r.value)), axisLabel: { color: 'rgba(224,245,232,0.6)' } },
      yAxis: [
        { type: 'value', name: '万元/年', axisLabel: { color: 'rgba(224,245,232,0.5)' }, nameTextStyle: { color: 'rgba(224,245,232,0.5)' } },
        { type: 'value', name: '年', splitLine: { show: false }, axisLabel: { color: 'rgba(224,245,232,0.5)' }, nameTextStyle: { color: 'rgba(224,245,232,0.5)' } },
      ],
      series: [
        {
          name: '年度节省(万元)',
          type: 'bar',
          barWidth: '45%',
          data: rows.map(r => ({
            value: +(r.annual_cost_saved_yuan / 10000).toFixed(1),
            itemStyle: { color: r.lifetime_savings_yuan >= 0 ? 'rgba(0,230,118,0.75)' : 'rgba(255,152,0,0.5)' },
          })),
        },
        {
          name: '回收期(年)',
          type: 'line',
          yAxisIndex: 1,
          data: rows.map(r => (r.payback_years != null && r.payback_years < 50 ? r.payback_years : null)),
          lineStyle: { color: '#00E5FF', width: 2 },
          itemStyle: { color: '#00E5FF' },
          markLine: {
            silent: true,
            symbol: 'none',
            data: [{ yAxis: 8 }],
            lineStyle: { color: '#FF5252', type: 'dashed' },
            label: { formatter: '寿命 8 年', color: '#FF8A80' },
          },
        },
      ],
      grid: { left: '3%', right: '8%', bottom: '3%', top: 36, containLabel: true },
    }
  }

  // 敏感性关键结论（从扫描行动态取数，避免硬编码）
  const sens = data.sensitivity
  const h2r30 = sens.h2_price.rows.find(r => r.value === 30)
  const h2r25 = sens.h2_price.rows.find(r => r.value === 25)
  const dsr85 = sens.diesel_price.rows.find(r => r.value === 8.5)
  const mkr15 = sens.annual_mileage.rows.find(r => r.value === 150000)

  const vehicleColumns = [
    { title: '车辆', dataIndex: 'label', key: 'label', render: (t: string, r: any) => <span style={{ color: '#69F0AE' }}>{t}</span> },
    { title: '地区', dataIndex: 'region', key: 'region' },
    { title: '里程(km)', dataIndex: 'total_km', key: 'total_km', render: (v: number) => v.toFixed(1) },
    { title: '氢耗(kg)', dataIndex: 'h2_consumed_kg', key: 'h2_consumed_kg', render: (v: number) => v.toFixed(2) },
    { title: 'kg/100km', dataIndex: 'h2_per_100km', key: 'h2_per_100km', render: (v: number) => <span style={{ color: '#00E5FF' }}>{v.toFixed(2)}</span> },
    { title: '氢成本(元)', dataIndex: 'h2_cost_yuan', key: 'h2_cost_yuan', render: (v: number) => fmtYuan(v) },
    { title: '柴油等效(元)', dataIndex: 'diesel_equivalent_cost_yuan', key: 'diesel_equivalent_cost_yuan', render: (v: number) => fmtYuan(v) },
    { title: 'CO2减排(kg)', dataIndex: 'co2_reduced_kg', key: 'co2_reduced_kg', render: (v: number) => <Tag color="green">{v.toFixed(0)}</Tag> },
    { title: '节省(元)', dataIndex: 'cost_saved_yuan', key: 'cost_saved_yuan', render: (v: number) => <span style={{ color: '#69F0AE' }}>+{fmtYuan(v)}</span> },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 标题 */}
      <div className="h2-panel" style={{ padding: 24 }}>
        <Title level={4} style={{ color: '#69F0AE', marginBottom: 8 }}>
          <DollarOutlined style={{ marginRight: 8 }} />
          价值量化分析
        </Title>
        <Text style={{ color: 'rgba(224,245,232,0.6)', fontSize: 13 }}>
          基于 {ds.vehicle_count} 辆车、{ds.total_trips} 个行程、{fmtKm(ds.total_distance_km)} 真实运营数据，
          对比同等柴油重卡的经济效益与碳减排量。数据周期：{ds.data_period_days} 天。
        </Text>
      </div>

      {/* 核心指标卡 */}
      <Row gutter={[8, 8]}>
        <Col xs={12} md={6}>
          <div className="h2-panel h2-kpi-card" style={{ padding: 16 }}>
            <Statistic
              title={<span style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>成本节省</span>}
              value={eco.cost_saved_yuan}
              precision={0}
              prefix={<ArrowDownOutlined style={{ color: '#69F0AE' }} />}
              suffix="元"
              valueStyle={{ color: '#69F0AE', fontSize: 24 }}
            />
            <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 11 }}>-{eco.cost_reduction_pct}% vs 柴油</Text>
          </div>
        </Col>
        <Col xs={12} md={6}>
          <div className="h2-panel h2-kpi-card" style={{ padding: 16 }}>
            <Statistic
              title={<span style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>CO2 减排</span>}
              value={emi.co2_reduced_green_kg}
              precision={0}
              prefix={<CloudOutlined style={{ color: '#00E5FF' }} />}
              suffix="kg"
              valueStyle={{ color: '#00E5FF', fontSize: 24 }}
            />
            <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 11 }}>绿氢 {emi.co2_reduction_pct_green}% 减排率</Text>
          </div>
        </Col>
        <Col xs={12} md={6}>
          <div className="h2-panel h2-kpi-card" style={{ padding: 16 }}>
            <Statistic
              title={<span style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>年均节省</span>}
              value={ann.annual_cost_saved}
              precision={0}
              prefix={<RiseOutlined style={{ color: '#69F0AE' }} />}
              suffix="元/年"
              valueStyle={{ color: '#69F0AE', fontSize: 24 }}
            />
            <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 11 }}>年均减排 {fmtTon(ann.annual_co2_reduced_tons)} CO2</Text>
          </div>
        </Col>
        <Col xs={12} md={6}>
          <div className="h2-panel h2-kpi-card" style={{ padding: 16 }}>
            <Statistic
              title={<span style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>投资回收期</span>}
              value={roi.payback_years ?? 'N/A'}
              precision={1}
              suffix="年"
              valueStyle={{ color: '#FFB74D', fontSize: 24 }}
            />
            <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 11 }}>车辆溢价 {fmtYuan(roi.vehicle_premium_yuan)}/辆</Text>
          </div>
        </Col>
      </Row>

      {/* 图表行 */}
      <Row gutter={[8, 8]}>
        {/* 成本对比 */}
        <Col xs={24} lg={10}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>
              <DollarOutlined style={{ marginRight: 8 }} />
              运营成本对比（实际数据周期）
            </h3>
            <ReactECharts option={costChart} style={{ height: 280 }} />
          </div>
        </Col>

        {/* 碳减排 */}
        <Col xs={24} lg={7}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>
              <CloudOutlined style={{ marginRight: 8 }} />
              碳排放对比
            </h3>
            <ReactECharts option={co2Chart} style={{ height: 280 }} />
            <div style={{ textAlign: 'center', marginTop: 4 }}>
              <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>
                柴油: {fmtKg(emi.diesel_co2_kg)} → 绿氢: {fmtKg(emi.h2_co2_green_kg)}
              </Text>
            </div>
          </div>
        </Col>

        {/* 百公里指标 */}
        <Col xs={24} lg={7}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#FFB74D', marginBottom: 8 }}>
              <ThunderboltOutlined style={{ marginRight: 8 }} />
              百公里指标
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, paddingTop: 12 }}>
              <div>
                <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>百公里氢成本</Text>
                <div style={{ fontSize: 22, color: '#69F0AE', fontWeight: 700 }}>{eco.h2_cost_per_100km} 元</div>
                <Text style={{ fontSize: 11, color: 'rgba(224,245,232,0.3)' }}>vs 柴油 {eco.diesel_cost_per_100km} 元</Text>
              </div>
              <Divider style={{ margin: '4px 0', borderColor: 'rgba(255,255,255,0.06)' }} />
              <div>
                <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>百公里CO2排放</Text>
                <div style={{ fontSize: 22, color: '#00E5FF', fontWeight: 700 }}>{emi.co2_per_km_h2_green_g} g/km</div>
                <Text style={{ fontSize: 11, color: 'rgba(224,245,232,0.3)' }}>vs 柴油 {emi.co2_per_km_diesel_g} g/km</Text>
              </div>
              <Divider style={{ margin: '4px 0', borderColor: 'rgba(255,255,255,0.06)' }} />
              <div>
                <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>百公里节省</Text>
                <div style={{ fontSize: 22, color: '#FFB74D', fontWeight: 700 }}>+{eco.cost_saved_per_100km} 元</div>
              </div>
            </div>
          </div>
        </Col>
      </Row>

      {/* 年度趋势 */}
      <Row gutter={[8, 8]}>
        <Col xs={24}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>
              <RiseOutlined style={{ marginRight: 8 }} />
              8年全生命周期成本与累计节省趋势
            </h3>
            <Text style={{ color: 'rgba(224,245,232,0.45)', fontSize: 11, display: 'block', marginBottom: 8 }}>
              模型推演：实测 18 天单位经济性 × 行业年化参数（年里程 10 万 km/辆、寿命 8 年），非 8 年实测数据；
              假设各年成本水平不变（未计入氢价走势与电堆衰减）
            </Text>
            <ReactECharts option={annualChart} style={{ height: 300 }} />
          </div>
        </Col>
      </Row>

      {/* 敏感性分析（单变量扫描） */}
      <Row gutter={[8, 8]}>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>
              <ExperimentOutlined style={{ marginRight: 8 }} />
              氢价敏感性分析
            </h3>
            <Text style={{ color: 'rgba(224,245,232,0.45)', fontSize: 11, display: 'block', marginBottom: 8 }}>
              扫描 25~40 元/kg（基准 35）；其余参数固定。绿色柱 = 8 年生命周期内盈利；红色虚线 = 8 年寿命线，回收期压线即为盈亏平衡
            </Text>
            <ReactECharts option={sensChart(sens.h2_price, v => `${v}`)} style={{ height: 280 }} />
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>
              <ExperimentOutlined style={{ marginRight: 8 }} />
              柴油价敏感性分析
            </h3>
            <Text style={{ color: 'rgba(224,245,232,0.45)', fontSize: 11, display: 'block', marginBottom: 8 }}>
              扫描 6.0~8.5 元/L（基准 7.5）；柴油越贵，氢能经济性越强。6.0 元/L 时年节省转负（本实测氢耗下无法回收）
            </Text>
            <ReactECharts option={sensChart(sens.diesel_price, v => `${v}`)} style={{ height: 280 }} />
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>
              <ExperimentOutlined style={{ marginRight: 8 }} />
              年里程敏感性分析
            </h3>
            <Text style={{ color: 'rgba(224,245,232,0.45)', fontSize: 11, display: 'block', marginBottom: 8 }}>
              扫描 6~15 万 km/辆/年（基准 10 万）；里程越高，固定购车溢价摊薄越快。15 万 km 为干线物流高强度场景
            </Text>
            <ReactECharts option={sensChart(sens.annual_mileage, v => `${v / 10000}`)} style={{ height: 280 }} />
          </div>
        </Col>
        <Col xs={24} lg={12}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 12 }}>
              <RiseOutlined style={{ marginRight: 8 }} />
              敏感性分析关键结论
            </h3>
            {h2r30 && (
              <Text style={{ color: 'rgba(224,245,232,0.85)', fontSize: 13, display: 'block', marginBottom: 10 }}>
                · 氢价降至 <b style={{ color: '#00E676' }}>30 元/kg</b>（2026 年多地主产区已实现）：回收期缩至
                <b style={{ color: '#00E676' }}> {h2r30.payback_years} 年</b>，8 年净赚
                <b style={{ color: '#00E676' }}> {(h2r30.lifetime_savings_yuan / 10000).toFixed(0)} 万元</b>
              </Text>
            )}
            {h2r25 && (
              <Text style={{ color: 'rgba(224,245,232,0.85)', fontSize: 13, display: 'block', marginBottom: 10 }}>
                · 氢价进一步降至 <b style={{ color: '#00E676' }}>25 元/kg</b>（绿氢规模化目标价）：回收期
                <b style={{ color: '#00E676' }}> {h2r25.payback_years} 年</b>，8 年净赚
                <b style={{ color: '#00E676' }}> {(h2r25.lifetime_savings_yuan / 10000).toFixed(0)} 万元</b>
              </Text>
            )}
            {dsr85 && (
              <Text style={{ color: 'rgba(224,245,232,0.85)', fontSize: 13, display: 'block', marginBottom: 10 }}>
                · 柴油价升至 <b style={{ color: '#00E676' }}>8.5 元/L</b>（油价上行情景）：回收期
                <b style={{ color: '#00E676' }}> {dsr85.payback_years} 年</b>
              </Text>
            )}
            {mkr15 && (
              <Text style={{ color: 'rgba(224,245,232,0.85)', fontSize: 13, display: 'block', marginBottom: 10 }}>
                · 年里程提至 <b style={{ color: '#00E676' }}>15 万 km/辆</b>（干线物流高强度）：回收期
                <b style={{ color: '#00E676' }}> {mkr15.payback_years} 年</b>
              </Text>
            )}
            <Text style={{ color: 'rgba(224,245,232,0.5)', fontSize: 11, display: 'block', marginTop: 4, lineHeight: 1.8 }}>
              方法：{sens.method}。基准情景（氢价 35 元/kg）下回收期 8.0 年、生命周期约打平——结论对氢价最敏感：
              氢价每降 1 元/kg，年节省增加约 1.2 万元（两辆车），是本项目价值主张的核心杠杆。
            </Text>
          </div>
        </Col>
      </Row>

      {/* 单车明细 */}
      <Row gutter={[8, 8]}>
        <Col xs={24}>
          <div className="h2-panel" style={{ padding: 16 }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 12 }}>
              <CarOutlined style={{ marginRight: 8 }} />
              单车价值明细
            </h3>
            <Table
              dataSource={data.per_vehicle}
              columns={vehicleColumns}
              rowKey="vehicle_id"
              pagination={false}
              size="small"
              style={{ background: 'transparent' }}
            />
          </div>
        </Col>
      </Row>

      {/* 计算方法与公式说明 */}
      <div className="h2-panel" style={{ padding: 16 }}>
        <h3 style={{ color: '#69F0AE', marginBottom: 12 }}>计算方法与公式说明（可解释性）</h3>
        <Table
          dataSource={[
            {
              key: '1',
              item: '氢燃料成本',
              formula: `总氢耗 ${ds.total_h2_consumed_kg} kg × 氢价 ${data.parameters.h2_price_yuan_per_kg} 元/kg = ${fmtYuan(eco.h2_fuel_cost_yuan)}`,
              source: '总氢耗为 T05 官方数据包遥测累计氢耗列差分汇总（真实值）；氢价为行业均价参数',
            },
            {
              key: '2',
              item: '柴油等效燃料成本',
              formula: `总里程 ${fmtKm(ds.total_distance_km)} ÷ 100 × 油耗 ${data.parameters.diesel_consumption_l_per_100km} L/100km × 油价 ${data.parameters.diesel_price_yuan_per_l} 元/L = ${fmtYuan(eco.diesel_fuel_cost_yuan)}`,
              source: '对标同吨位柴油重卡（30L/100km），里程为真实值',
            },
            {
              key: '3',
              item: '成本节省',
              formula: `(柴油燃料+柴油维护) - (氢燃料+氢维护) = ${fmtYuan(eco.cost_saved_yuan)}（降幅 ${eco.cost_reduction_pct}%）`,
              source: `维护单价：氢 ${data.parameters.h2_maintenance_yuan_per_km} 元/km vs 柴油 ${data.parameters.diesel_maintenance_yuan_per_km} 元/km（行业参数）`,
            },
            {
              key: '4',
              item: 'CO2 减排（绿氢口径）',
              formula: `柴油CO2(里程÷100×油耗×${data.parameters.diesel_co2_kg_per_l} kg/L) - 绿氢CO2(≈0) = ${fmtKg(emi.co2_reduced_green_kg)}`,
              source: '柴油排放因子 2.63 kg/L（国标口径）；绿氢按井口到车轮近零排放计',
            },
            {
              key: '5',
              item: '年度推演',
              formula: `按 ${ann.annual_km_per_vehicle.toLocaleString()} km/辆/年 × ${ds.vehicle_count} 辆等比缩放实测数据`,
              source: '年里程为重卡行业均值参数；实测数据周期 18 天',
            },
            {
              key: '5b',
              item: '生命周期推演',
              formula: `年节省 × ${roi.lifetime_years} 年 − 购车溢价 = 全生命周期净节省 ${fmtYuan(roi.lifetime_savings_yuan)}`,
              source: '车辆寿命 8 年为重卡行业惯例参数（比赛数据包仅含 18 天实测，不含多年数据）',
            },
            {
              key: '6',
              item: '投资回收期',
              formula: `车辆溢价 ${fmtYuan(roi.vehicle_premium_yuan)}/辆 × ${ds.vehicle_count} 辆 ÷ 年节省 ${fmtYuan(ann.annual_cost_saved)} = ${roi.payback_years ?? '∞'} 年`,
              source: '氢能重卡较同级柴油车约贵 30 万（市场公开报价口径）',
            },
            {
              key: '6b',
              item: '敏感性分析',
              formula: `固定实测百公里氢耗 ${ds.avg_h2_per_100km} kg，单变量扫描氢价 25~40 元/kg、柴油价 6~8.5 元/L、年里程 6~15 万 km/辆，重算年度节省与回收期`,
              source: data.sensitivity.method,
            },
          ]}
          columns={[
            { title: '计算项', dataIndex: 'item', key: 'item', width: 150, render: (t: string) => <span style={{ color: '#69F0AE', fontWeight: 600 }}>{t}</span> },
            { title: '计算公式与代入过程', dataIndex: 'formula', key: 'formula', render: (t: string) => <span style={{ color: 'rgba(224,245,232,0.8)', fontSize: 12 }}>{t}</span> },
            { title: '数据来源 / 参数性质', dataIndex: 'source', key: 'source', width: 340, render: (t: string) => <span style={{ color: 'rgba(224,245,232,0.45)', fontSize: 11 }}>{t}</span> },
          ]}
          pagination={false}
          size="small"
          style={{ background: 'transparent' }}
        />
        <Text style={{ color: 'rgba(224,245,232,0.35)', fontSize: 11, display: 'block', marginTop: 12 }}>
          方法说明：里程、氢耗取自 T05 官方数据包真实遥测；价格与排放因子为行业公开均值参数（已在公式中逐项代入）。
          柴油对标车型假设 49 吨级、30L/100km。绿氢口径下氢燃料电池车全生命周期尾气与井口排放近似为零。
        </Text>
      </div>
    </div>
  )
}
