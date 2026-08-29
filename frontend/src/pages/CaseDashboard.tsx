// 氢智行 H2Brain - 案例数据看板（真实数据回测 + 计算方法说明）
import { useEffect, useState } from 'react'
import { Row, Col, Spin, Empty, Table, Tag } from 'antd'
import { apiGet } from '@/lib/request'

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
  if (!caseData) return <Empty description="无法加载案例数据" />

  const columns = [
    {
      title: '指标',
      dataIndex: 'name',
      key: 'name',
      width: 140,
      render: (t: string) => <span style={{ color: '#69F0AE', fontWeight: 600 }}>{t}</span>,
    },
    {
      title: '基线',
      dataIndex: 'before',
      key: 'before',
      width: 110,
      render: (t: string) => <span style={{ color: '#FF6B35' }}>{t}</span>,
    },
    {
      title: '成效',
      dataIndex: 'after',
      key: 'after',
      width: 110,
      render: (t: string) => <span style={{ color: '#69F0AE', fontWeight: 700 }}>{t}</span>,
    },
    {
      title: '口径',
      dataIndex: 'change',
      key: 'change',
      width: 130,
      render: (t: string) => <Tag color="cyan">{t}</Tag>,
    },
    {
      title: '计算方法 / 数据来源',
      dataIndex: 'method',
      key: 'method',
      render: (t: string) => <span style={{ color: 'rgba(224,245,232,0.65)', fontSize: 12 }}>{t}</span>,
    },
  ]

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
                <span style={{ color: '#00E5FF', fontSize: 12, fontWeight: 700 }}>{m.change}</span>
              </div>
            </div>
          </Col>
        ))}
      </Row>

      <div className="h2-panel" style={{ padding: 16 }}>
        <h3 style={{ color: '#69F0AE', marginBottom: 12 }}>指标口径与计算方法（可解释性说明）</h3>
        <Table
          dataSource={caseData.metrics}
          columns={columns}
          rowKey="name"
          pagination={false}
          size="small"
          style={{ background: 'transparent' }}
        />
        <p style={{ color: 'rgba(224,245,232,0.35)', fontSize: 11, marginTop: 12 }}>
          说明：真实数据指标均来自 T05 官方数据包遥测回测；涉及经济与碳减排的完整参数、公式与年度推演见「价值量化分析」页；
          加氢站调度与路径规划为沙盘推演演示数据。
        </p>
      </div>
    </div>
  )
}
