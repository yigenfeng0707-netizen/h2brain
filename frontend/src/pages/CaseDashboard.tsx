// 氢智行 H2Brain - 案例数据看板
import { useEffect, useState } from 'react'
import { Row, Col, Spin, Empty } from 'antd'
import { apiGet } from '@/lib/request'
import ReactECharts from 'echarts-for-react'

export default function CaseDashboard() {
  const [caseData, setCaseData] = useState<any>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiGet.displayCase().then(res => {
      setCaseData(res.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />
  if (!caseData) return <Empty />

  const chart = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['优化前', '优化后'], textStyle: { color: 'rgba(224,245,232,0.6)' } },
    xAxis: { type: 'category', data: caseData.metrics.map((m: any) => m.name), axisLabel: { color: 'rgba(224,245,232,0.6)', rotate: 20 } },
    yAxis: { type: 'value', axisLabel: { color: 'rgba(224,245,232,0.6)' } },
    series: [
      {
        name: '优化前',
        type: 'bar',
        data: caseData.metrics.map((m: any) => {
          const v = parseFloat(m.before)
          return isNaN(v) ? 0 : v
        }),
        itemStyle: { color: '#FF6B35', borderRadius: [4, 4, 0, 0] },
      },
      {
        name: '优化后',
        type: 'bar',
        data: caseData.metrics.map((m: any) => {
          const v = parseFloat(m.after)
          return isNaN(v) ? 0 : v
        }),
        itemStyle: { color: '#69F0AE', borderRadius: [4, 4, 0, 0] },
      },
    ],
    grid: { left: '3%', right: '4%', bottom: '10%', containLabel: true },
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="h2-panel" style={{ padding: 20 }}>
        <h2 style={{ color: '#69F0AE', marginBottom: 4 }}>{caseData.title}</h2>
        <p style={{ color: 'rgba(224,245,232,0.5)', fontSize: 12 }}>{caseData.period}</p>
        <p style={{ color: 'rgba(224,245,232,0.7)', fontSize: 13, marginTop: 8 }}>{caseData.summary}</p>
      </div>

      <Row gutter={[8, 8]}>
        {caseData.metrics.map((m: any, i: number) => (
          <Col key={i} xs={12} md={8} lg={4}>
            <div className="h2-kpi-card">
              <div style={{ color: 'rgba(224,245,232,0.6)', fontSize: 12 }}>{m.name}</div>
              <div style={{ marginTop: 6, fontSize: 13 }}>
                <span style={{ color: '#FF6B35' }}>{m.before}</span>
                <span style={{ color: 'rgba(224,245,232,0.3)', margin: '0 4px' }}>{'->'}</span>
                <span style={{ color: '#69F0AE', fontWeight: 700 }}>{m.after}</span>
              </div>
              <div style={{ marginTop: 4 }}>
                <span style={{ color: m.change.startsWith('-') || m.change.includes('新增') ? '#69F0AE' : '#00E5FF', fontSize: 12, fontWeight: 700 }}>
                  {m.change}
                </span>
              </div>
            </div>
          </Col>
        ))}
      </Row>

      <div className="h2-panel" style={{ padding: 16 }}>
        <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>优化前后对比</h3>
        <ReactECharts option={chart} style={{ height: 350 }} />
      </div>
    </div>
  )
}
