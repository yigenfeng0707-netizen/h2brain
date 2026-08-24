// 氢智行 H2Brain - 智能体详情页通用组件
import { useEffect, useState, useRef } from 'react'
import { Spin, Empty, Tag, Row, Col, Input, Button, Card, Space, Typography, Tooltip } from 'antd'
import { SendOutlined, RobotOutlined, UserOutlined, BulbOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { apiGet, apiPost } from '@/lib/request'

const { Text, Paragraph } = Typography

interface AgentData {
  key: string
  name: string
  icon: string
  metric: string
  desc: string
  capabilities: string[]
  tech: string
  llm_enabled?: boolean
}

interface ChatMessage {
  role: 'user' | 'agent'
  content: string
  timestamp: string
  offline?: boolean
}

// Preset questions per agent type
const PRESET_QUESTIONS: Record<string, string[]> = {
  hydrogen_opt: [
    '当前车队平均百公里氢耗是多少？',
    '哪辆车氢耗异常最高？给出原因分析。',
    '如何优化驾驶行为以降低氢耗？',
  ],
  route_plan: [
    '氢气余量20%时安全续航半径是多少？',
    '从襄阳到武汉沿途有哪些加氢站？',
    '如何规划多订单串联路线？',
  ],
  station_dispatch: [
    '当前各加氢站排队情况如何？',
    '推荐车辆1#去哪个站加氢？',
    '如何避开高峰时段？',
  ],
  fleet_manage: [
    '车队利用率是多少？',
    '有哪些空驶行程？如何优化？',
    '推荐司机的最佳换班方案。',
  ],
  cost_analysis: [
    '单车全成本TCO是多少？',
    '氢气价格波动对运营成本的影响？',
    '如何降低维护成本？',
  ],
  fuelcell_health: [
    '电堆健康评分是多少？',
    '极化曲线分析结果如何？',
    '电堆剩余寿命RUL预测？',
  ],
}

export default function AgentDetailPage({ agentKey }: { agentKey: string }) {
  const [agent, setAgent] = useState<AgentData | null>(null)
  const [loading, setLoading] = useState(true)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [asking, setAsking] = useState(false)
  const chatEndRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setLoading(true)
    setMessages([])
    apiGet.agentDetail(agentKey).then(res => {
      setAgent(res.data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [agentKey])

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  if (loading) return <Spin size="large" style={{ display: 'flex', justifyContent: 'center', padding: 100 }} />
  if (!agent) return <Empty />

  const presets = PRESET_QUESTIONS[agentKey] || []

  const askAgent = async (question: string) => {
    if (!question.trim() || asking) return
    const now = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    setMessages(prev => [...prev, { role: 'user', content: question, timestamp: now }])
    setInput('')
    setAsking(true)

    try {
      const res = await apiPost.agentExecute(agentKey, { query: question })
      const result = res.data?.result || {}
      const agentReply = result.final_answer
        || result.answer
        || result.response
        || result.summary
        || JSON.stringify(result, null, 2)
      const isOffline = res.data?.llm_enabled === false
      setMessages(prev => [...prev, {
        role: 'agent',
        content: typeof agentReply === 'string' ? agentReply : JSON.stringify(agentReply, null, 2),
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
        offline: isOffline,
      }])
    } catch {
      setMessages(prev => [...prev, {
        role: 'agent',
        content: '智能体响应超时，正在以离线模式返回分析结果。请稍后重试或检查网络连接。',
        timestamp: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
      }])
    } finally {
      setAsking(false)
    }
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
            {agent.llm_enabled !== undefined && (
              <Tag color={agent.llm_enabled ? 'green' : 'orange'} style={{ marginTop: 4 }}>
                {agent.llm_enabled ? 'LLM 已启用' : '离线模式'}
              </Tag>
            )}
          </div>
        </div>
      </div>

      <Row gutter={[8, 8]}>
        {/* 能力列表 */}
        <Col xs={24} lg={8}>
          <div className="h2-panel" style={{ padding: 16, height: '100%' }}>
            <h3 style={{ color: '#69F0AE', marginBottom: 12 }}>
              <CheckCircleOutlined style={{ marginRight: 8 }} />
              核心能力
            </h3>
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

        {/* 交互问答面板 */}
        <Col xs={24} lg={16}>
          <div className="h2-panel" style={{ padding: 16, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <h3 style={{ color: '#00E5FF', marginBottom: 12 }}>
              <RobotOutlined style={{ marginRight: 8 }} />
              智能体对话
            </h3>

            {/* 预设问题 */}
            {presets.length > 0 && messages.length === 0 && (
              <div style={{ marginBottom: 12 }}>
                <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 12 }}>
                  <BulbOutlined /> 快捷提问:
                </Text>
                <Space wrap style={{ marginTop: 8 }}>
                  {presets.map((q, i) => (
                    <Button
                      key={i}
                      size="small"
                      ghost
                      style={{ borderColor: 'rgba(0,229,255,0.3)', color: 'rgba(0,229,255,0.8)' }}
                      onClick={() => askAgent(q)}
                      disabled={asking}
                    >
                      {q}
                    </Button>
                  ))}
                </Space>
              </div>
            )}

            {/* 对话区域 */}
            <div style={{
              flex: 1, minHeight: 300, maxHeight: 400, overflowY: 'auto',
              padding: 12, borderRadius: 8,
              background: 'rgba(0,0,0,0.2)',
              border: '1px solid rgba(255,255,255,0.05)',
            }}>
              {messages.length === 0 && !asking && (
                <div style={{ textAlign: 'center', paddingTop: 60, color: 'rgba(224,245,232,0.25)' }}>
                  <RobotOutlined style={{ fontSize: 40, marginBottom: 12 }} />
                  <p>向智能体提问，获取专业分析结果</p>
                </div>
              )}
              {messages.map((msg, i) => (
                <div key={i} style={{
                  display: 'flex',
                  flexDirection: msg.role === 'user' ? 'row-reverse' : 'row',
                  gap: 8, marginBottom: 12,
                }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                    background: msg.role === 'user'
                      ? 'rgba(0,229,255,0.15)'
                      : 'rgba(0,200,83,0.15)',
                    color: msg.role === 'user' ? '#00E5FF' : '#69F0AE',
                  }}>
                    {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  </div>
                  <div style={{
                    maxWidth: '75%',
                    padding: '8px 12px',
                    borderRadius: msg.role === 'user' ? '12px 2px 12px 12px' : '2px 12px 12px 12px',
                    background: msg.role === 'user'
                      ? 'rgba(0,229,255,0.08)'
                      : 'rgba(0,200,83,0.08)',
                    border: `1px solid ${msg.role === 'user' ? 'rgba(0,229,255,0.2)' : 'rgba(105,240,174,0.2)'}`,
                  }}>
                    <Paragraph style={{
                      margin: 0, color: 'rgba(224,245,232,0.9)', fontSize: 13,
                      whiteSpace: 'pre-wrap',
                    }}>
                      {msg.content}
                    </Paragraph>
                    <Text style={{ fontSize: 10, color: 'rgba(224,245,232,0.25)' }}>
                      {msg.timestamp}
                      {msg.offline && (
                        <span style={{ marginLeft: 6, color: 'rgba(255,152,0,0.7)' }}>· 离线模式</span>
                      )}
                    </Text>
                  </div>
                </div>
              ))}
              {asking && (
                <div style={{ display: 'flex', gap: 8 }}>
                  <div style={{
                    width: 32, height: 32, borderRadius: '50%',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'rgba(0,200,83,0.15)', color: '#69F0AE',
                  }}>
                    <RobotOutlined />
                  </div>
                  <div style={{
                    padding: '8px 16px', borderRadius: '2px 12px 12px 12px',
                    background: 'rgba(0,200,83,0.05)',
                    border: '1px solid rgba(105,240,174,0.15)',
                  }}>
                    <Spin size="small" /> <Text style={{ color: 'rgba(224,245,232,0.4)', fontSize: 13, marginLeft: 8 }}>思考中...</Text>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>

            {/* 输入框 */}
            <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
              <Input
                value={input}
                onChange={e => setInput(e.target.value)}
                onPressEnter={() => askAgent(input)}
                placeholder="输入问题..."
                disabled={asking}
                style={{
                  background: 'rgba(0,0,0,0.3)',
                  borderColor: 'rgba(0,229,255,0.2)',
                  color: 'rgba(224,245,232,0.9)',
                }}
              />
              <Button
                type="primary"
                icon={<SendOutlined />}
                loading={asking}
                onClick={() => askAgent(input)}
                style={{
                  background: 'linear-gradient(135deg, rgba(0,200,83,0.3), rgba(0,229,255,0.2))',
                  borderColor: 'rgba(105,240,174,0.4)',
                }}
              >
                发送
              </Button>
            </div>
          </div>
        </Col>
      </Row>
    </div>
  )
}
