// 氢智行 H2Brain - 五层架构展示
import { useEffect, useState } from 'react'
import { Spin } from 'antd'
import { apiGet } from '@/lib/request'
import { ARCH_LAYERS } from '@/lib/brand'

export default function Architecture() {
  const [layers, setLayers] = useState(ARCH_LAYERS as readonly any[])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    apiGet.displayArchitecture().then(res => {
      setLayers(res.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="h2-panel" style={{ padding: 20, textAlign: 'center' }}>
        <h2 style={{ color: '#69F0AE', marginBottom: 4 }}>氢智行 H2Brain - 五层架构</h2>
        <p style={{ color: 'rgba(224,245,232,0.5)', fontSize: 12 }}>
          LLM + RAG + MCP + 运筹优化 | 六大氢能智能体协同
        </p>
      </div>

      {layers.map((layer, i) => (
        <div
          key={i}
          className="h2-panel"
          style={{
            padding: 20,
            borderLeft: `4px solid ${['#69F0AE', '#00C853', '#00E5FF', '#FFD740', '#FF6B35'][i]}`,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <span
              style={{
                fontSize: 28,
                fontWeight: 900,
                color: ['#69F0AE', '#00C853', '#00E5FF', '#FFD740', '#FF6B35'][i],
                minWidth: 50,
              }}
            >
              {layer.level}
            </span>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: '#e0f5e8' }}>{layer.name}</div>
              <div style={{ color: 'rgba(224,245,232,0.6)', fontSize: 13, marginTop: 4 }}>
                {layer.desc}
              </div>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
