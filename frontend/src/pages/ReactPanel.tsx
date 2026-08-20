// 氢智行 H2Brain - ReAct 决策面板
import { useEffect, useState } from 'react'
import { Card, Row, Col, Select, Input, Button, Tag, Spin, Empty, Typography } from 'antd'
import { apiGet, apiPost } from '@/lib/request'

const { TextArea } = Input
const { Text, Paragraph } = Typography

interface Template {
  key: string
  name: string
  desc: string
  query_hint: string
}

interface ReactStep {
  thought: string
  action: string
  observation: string
}

interface ReactResponse {
  steps: ReactStep[]
  final_answer: string
  scenario: string
}

const STEP_COLORS = ['#69F0AE', '#00E5FF', '#FFD740', '#FF6B35', '#B388FF']

export default function ReactPanel() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [scenario, setScenario] = useState('hydrogen_optimization')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ReactResponse | null>(null)

  useEffect(() => {
    apiGet.reactTemplates().then(res => {
      setTemplates(res.data)
      if (res.data.length > 0) {
        setQuery(res.data[0].query_hint)
      }
    })
  }, [])

  const handleScenarioChange = (key: string) => {
    setScenario(key)
    const tpl = templates.find(t => t.key === key)
    if (tpl) setQuery(tpl.query_hint)
  }

  const handleInvoke = async () => {
    setLoading(true)
    setResult(null)
    try {
      const res = await apiPost.react({ scenario, query })
      setResult(res.data)
    } catch {
      // ignore
    }
    setLoading(false)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div className="h2-panel" style={{ padding: 16 }}>
        <h2 style={{ color: '#69F0AE', marginBottom: 12 }}>ReAct 决策推理面板</h2>
        <Row gutter={[8, 8]} align="middle">
          <Col xs={24} md={6}>
            <Select
              value={scenario}
              onChange={handleScenarioChange}
              style={{ width: '100%' }}
              options={templates.map(t => ({ value: t.key, label: t.name }))}
            />
          </Col>
          <Col xs={24} md={14}>
            <TextArea
              value={query}
              onChange={e => setQuery(e.target.value)}
              rows={2}
              placeholder="输入你的问题..."
            />
          </Col>
          <Col xs={24} md={4}>
            <Button
              type="primary"
              size="large"
              block
              loading={loading}
              onClick={handleInvoke}
              style={{ background: '#00C853', borderColor: '#00C853' }}
            >
              开始推理
            </Button>
          </Col>
        </Row>
        {templates.find(t => t.key === scenario) && (
          <div style={{ marginTop: 8, color: 'rgba(224,245,232,0.5)', fontSize: 12 }}>
            {templates.find(t => t.key === scenario)?.desc}
          </div>
        )}
      </div>

      {loading && (
        <div className="h2-panel" style={{ padding: 40, textAlign: 'center' }}>
          <Spin size="large" />
          <div style={{ color: '#69F0AE', marginTop: 16 }}>Agent 正在思考中...</div>
        </div>
      )}

      {result && (
        <>
          <Row gutter={[8, 8]}>
            {result.steps.map((step, i) => (
              <Col key={i} xs={24}>
                <div className="h2-panel" style={{ padding: 16, borderLeft: `3px solid ${STEP_COLORS[i % STEP_COLORS.length]}` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                    <Tag color="green" style={{ fontSize: 14, padding: '2px 8px' }}>Step {i + 1}</Tag>
                  </div>
                  <div style={{ marginBottom: 6 }}>
                    <Text style={{ color: STEP_COLORS[i % STEP_COLORS.length], fontWeight: 700 }}>Thought: </Text>
                    <Text style={{ color: 'rgba(224,245,232,0.85)' }}>{step.thought}</Text>
                  </div>
                  <div style={{ marginBottom: 6, fontFamily: 'monospace', fontSize: 12, color: '#00E5FF' }}>
                    Action: {step.action}
                  </div>
                  <div>
                    <Text style={{ color: 'rgba(224,245,232,0.6)', fontWeight: 600 }}>Observation: </Text>
                    <Text style={{ color: 'rgba(224,245,232,0.7)' }}>{step.observation}</Text>
                  </div>
                </div>
              </Col>
            ))}
          </Row>

          <div className="h2-panel" style={{ padding: 20, border: '1px solid rgba(105,240,174,0.4)' }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 8 }}>Final Answer</h3>
            <Paragraph style={{ color: 'rgba(224,245,232,0.9)', fontSize: 14, lineHeight: 1.8 }}>
              {result.final_answer}
            </Paragraph>
          </div>
        </>
      )}

      {!loading && !result && (
        <div className="h2-panel" style={{ padding: 40, textAlign: 'center' }}>
          <Empty description="选择场景并输入问题，点击开始推理" />
        </div>
      )}
    </div>
  )
}
