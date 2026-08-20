// 氢智行 H2Brain - SaaS 定价
import { useEffect, useState } from 'react'
import { Row, Col, Spin, Empty, Tag } from 'antd'
import { apiGet } from '@/lib/request'

export default function SaaSPricing() {
  const [pricing, setPricing] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiGet.displayPricing().then(res => {
      setPricing(res.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />
  if (!pricing.length) return <Empty />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="h2-panel" style={{ padding: 20, textAlign: 'center' }}>
        <h2 style={{ color: '#69F0AE' }}>氢智行 H2Brain SaaS 定价</h2>
        <p style={{ color: 'rgba(224,245,232,0.5)', fontSize: 12 }}>让每克氢都跑在刀刃上</p>
      </div>

      <Row gutter={[12, 12]}>
        {pricing.map((plan, i) => (
          <Col key={i} xs={24} sm={12} md={6}>
            <div
              className="h2-panel"
              style={{
                padding: 24,
                textAlign: 'center',
                border: i === 1 ? '1px solid rgba(105,240,174,0.5)' : undefined,
              }}
            >
              {i === 1 && (
                <Tag color="green" style={{ marginBottom: 8 }}>推荐</Tag>
              )}
              <h3 style={{ color: '#69F0AE', fontSize: 20 }}>{plan.name}</h3>
              <div className="h2-num" style={{ fontSize: 28, color: '#00E5FF', margin: '8px 0' }}>
                {plan.price}
              </div>
              <div style={{ color: 'rgba(224,245,232,0.5)', fontSize: 12, marginBottom: 16 }}>
                {plan.vehicles}
              </div>
              <div style={{ textAlign: 'left' }}>
                {plan.features.map((f: string, j: number) => (
                  <div key={j} style={{ padding: '6px 0', color: 'rgba(224,245,232,0.7)', fontSize: 13 }}>
                    <span style={{ color: '#69F0AE', marginRight: 8 }}>+</span>{f}
                  </div>
                ))}
              </div>
            </div>
          </Col>
        ))}
      </Row>
    </div>
  )
}
