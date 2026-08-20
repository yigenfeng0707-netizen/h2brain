// 氢智行 H2Brain - 智能体详情页通用组件
import { useEffect, useState } from 'react'
import { Spin, Empty, Tag, Row, Col } from 'antd'
import { apiGet } from '@/lib/request'
import ReactECharts from 'echarts-for-react'

interface AgentData {
  key: string
  name: string
  icon: string
  metric: string
  desc: string
  capabilities: string[]
  tech: string
}

export default function AgentDetailPage({ agentKey }: { agentKey: string }) {
  const [agent, setAgent] = useState<AgentData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    apiGet.agentDetail(agentKey).then(res => {
      setAgent(res.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [agentKey])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />
  if (!agent) return <Empty />

  // 生成模拟性能图表
  const perfChart = {
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: ['W1', 'W2', 'W3', 'W4', 'W5', 'W6', 'W7', 'W8'], axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    yAxis: { type: 'value', axisLabel: { color: 'rgba(224,245,232,0.5)' } },
    series: [{
      data: Array.from({ length: 8 }, () => Math.round(60 + Math.random() * 35)),
      type: 'line',
      smooth: true,
      areaStyle: { color: 'rgba(105,240,174,0.15)' },
      lineStyle: { color: '#69F0AE', width: 2 },
      itemStyle: { color: '#69F0AE' },
    }],
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {/* 智能体头部 */}
      <div className="h2-panel" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <div style={{
            width: 60, height: 60, borderRadius: 12,
            background: 'linear-gradient(135deg, rgba(0,200,83,0.2), rgba(0,229,255,0.1))',
            border: '1px solid rgba(105,240,174,0.3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 24, fontWeight: 900, color: '#69F0AE',
          }}>
            {agent.icon}
          </div>
          <div style={{ flex: 1 }}>
            <h2 style={{ color: '#69F0AE', marginBottom: 4 }}>{agent.name}</h2>
            <p style={{ color: 'rgba(224,245,232,0.6)', fontSize: 13 }}>{agent.desc}</p>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ color: 'rgba(224,245,232,0.4)', fontSize: 11 }}>核心指标</div>
            <div className="h2-num" style={{ fontSize: 20, color: '#00E5FF' }}>{agent.metric}</div>
          </div>
        </div>
      </div>

      <Row gutter={[8, 8]}>
        {/* 能力列表 */}
        <Col xs={24} lg={14}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 12 }}>核心能力</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {agent.capabilities.map((cap, i) => (
                <div key={i} className="h2-kpi-card" style={{ padding: 12, display: 'flex', alignItems: 'center', gap: 12 }}>
                  <span style={{
                    width: 28, height: 28, borderRadius: 6,
                    background: 'rgba(0,200,83,0.15)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#69F0AE', fontWeight: 700, fontSize: 14,
                  }}>{i + 1}</span>
                  <span style={{ color: 'rgba(224,245,232,0.85)', fontSize: 13 }}>{cap}</span>
                </div>
              ))}
            </div>
            <div style={{ marginTop: 12, padding: 12, borderRadius: 8, background: 'rgba(0,229,255,0.05)' }}>
              <span style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>技术栈: </span>
              <Tag color="cyan" style={{ marginLeft: 4 }}>{agent.tech}</Tag>
            </div>
          </div>
        </Col>

        {/* 性能趋势 */}
        <Col xs={24} lg={10}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 8 }}>8周性能趋势</h3>
            <ReactECharts option={perfChart} style={{ height: 280 }} />
          </div>
        </Col>
      </Row>
    </div>
  )
}
