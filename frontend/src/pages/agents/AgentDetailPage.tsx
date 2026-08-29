// 氢智行 H2Brain - 智能体详情页通用组件
import { useEffect, useState, useRef, isValidElement } from 'react'
import { Spin, Empty, Tag, Row, Col, Input, Button, Card, Space, Typography, Tooltip } from 'antd'
import { SendOutlined, RobotOutlined, UserOutlined, BulbOutlined, CheckCircleOutlined, PictureOutlined } from '@ant-design/icons'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ReactECharts from 'echarts-for-react'
import api, { apiGet, apiPost, agentExecuteStream } from '@/lib/request'

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
  thinking?: boolean
  key?: string
}

// 周报配图 URL 模式（后端工具/端点返回）
const REPORT_IMG_RE = /\/api\/v1\/agents\/report-image\/([a-z0-9]+)/g

// ── Markdown 富文本渲染 ──────────────────────────────────────────────
// LLM 结论含 Markdown（标题/列表/表格/加粗）时渲染为富文本；
// 含 ```echarts 代码块时自动调用 ECharts 渲染专业图表（失败兜底显示原文）。

// ECharts 代码块渲染：解析 option JSON，非法时兜底为源码展示
function EChartsBlock({ code }: { code: string }) {
  const cleaned = code.trim().replace(/^```(?:echarts)?\s*\n?/, '').replace(/\n?```\s*$/, '')
  try {
    const option = JSON.parse(cleaned)
    if (typeof option !== 'object' || option === null) throw new Error('not an option object')
    return (
      <div style={{ marginTop: 10, padding: 8, borderRadius: 8, background: 'rgba(4,20,14,0.85)', border: '1px solid rgba(0,229,255,0.25)' }}>
        <ReactECharts option={option} notMerge={true} style={{ height: 280 }} />
      </div>
    )
  } catch {
    return (
      <pre style={{ margin: '8px 0', padding: 10, borderRadius: 6, background: 'rgba(4,20,14,0.9)', border: '1px solid rgba(105,240,174,0.2)', color: 'rgba(224,245,232,0.7)', fontSize: 11, overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
        {cleaned}
      </pre>
    )
  }
}

// Markdown 各元素暗色主题样式（表格/列表/标题/行内代码）
const MD_TEXT = 'rgba(224,245,232,0.88)'
const MD_TEXT_DIM = 'rgba(224,245,232,0.55)'

const mdComponents = {
  h1: (p: any) => <h3 style={{ color: '#69F0AE', fontSize: 16, margin: '14px 0 8px', fontWeight: 700 }} {...p} />,
  h2: (p: any) => <h4 style={{ color: '#69F0AE', fontSize: 15, margin: '12px 0 6px', fontWeight: 700 }} {...p} />,
  h3: (p: any) => <h5 style={{ color: '#69F0AE', fontSize: 14, margin: '10px 0 6px', fontWeight: 600 }} {...p} />,
  p: (p: any) => <p style={{ margin: '6px 0', fontSize: 13, color: MD_TEXT, lineHeight: 1.75 }} {...p} />,
  ul: (p: any) => <ul style={{ margin: '6px 0', paddingLeft: 20, fontSize: 13, lineHeight: 1.75, color: MD_TEXT }} {...p} />,
  ol: (p: any) => <ol style={{ margin: '6px 0', paddingLeft: 22, fontSize: 13, lineHeight: 1.75, color: MD_TEXT }} {...p} />,
  li: (p: any) => <li style={{ margin: '2px 0' }} {...p} />,
  strong: (p: any) => <strong style={{ color: '#00E676' }} {...p} />,
  blockquote: (p: any) => (
    <blockquote style={{ margin: '8px 0', padding: '6px 12px', borderLeft: '3px solid rgba(105,240,174,0.5)', background: 'rgba(105,240,174,0.06)', color: MD_TEXT_DIM, fontSize: 12 }} {...p} />
  ),
  // 表格：暗色边框 + 滚动容器（宽表不撑破气泡）
  table: (p: any) => (
    <div style={{ overflowX: 'auto', margin: '10px 0' }}>
      <table style={{ borderCollapse: 'collapse', width: '100%', fontSize: 12 }} {...p} />
    </div>
  ),
  th: (p: any) => (
    <th style={{ border: '1px solid rgba(105,240,174,0.35)', padding: '6px 10px', background: 'rgba(105,240,174,0.12)', color: '#69F0AE', textAlign: 'left', whiteSpace: 'nowrap' }} {...p} />
  ),
  td: (p: any) => (
    <td style={{ border: '1px solid rgba(105,240,174,0.2)', padding: '5px 10px', color: MD_TEXT, whiteSpace: 'nowrap' }} {...p} />
  ),
  // 行内代码
  code: ({ children, className, ...rest }: any) => (
    <code style={{ background: 'rgba(0,229,255,0.1)', color: '#00E5FF', borderRadius: 4, padding: '1px 5px', fontSize: 12 }} className={className} {...rest}>
      {children}
    </code>
  ),
  // 块级代码：echarts 语言走专业渲染，其余暗色源码块
  pre: ({ children, ...rest }: any) => {
    const child = Array.isArray(children) ? children[0] : children
    if (isValidElement<any>(child) && String(child.props?.className || '').includes('language-echarts')) {
      return <EChartsBlock code={String(child.props?.children ?? '')} />
    }
    return (
      <pre style={{ margin: '8px 0', padding: 10, borderRadius: 6, background: 'rgba(4,20,14,0.9)', border: '1px solid rgba(105,240,174,0.2)', color: 'rgba(224,245,232,0.7)', fontSize: 11, overflowX: 'auto' }} {...rest}>
        {children}
      </pre>
    )
  },
}

// 消息内容渲染: Markdown 富文本 + 配图内联 + echarts 专业图表
function MessageBody({ content }: { content: string }) {
  const urls = content.match(REPORT_IMG_RE)
  const text = urls
    ? content
        .replace(/配图链接：?\s*\/api\/v1\/agents\/report-image\/[a-z0-9]+/g, '')
        .replace(/!\[[^\]]*\]\(\/api\/v1\/agents\/report-image\/[a-z0-9]+\)/g, '')
        .replace(/\n{3,}/g, '\n\n')
        .trim()
    : content
  return (
    <>
      {text && (
        <div style={{ wordBreak: 'break-word' }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
            {text}
          </ReactMarkdown>
        </div>
      )}
      {urls?.map((u, i) => (
        <div key={i} style={{ marginTop: 8 }}>
          <img
            src={u}
            alt="运营周报配图"
            style={{
              width: '100%', maxWidth: 480, borderRadius: 8,
              border: '1px solid rgba(105,240,174,0.3)',
              display: 'block',
            }}
          />
        </div>
      ))}
    </>
  )
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
    '生成一张运营周报配图。',
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
  const [imgLoading, setImgLoading] = useState(false)
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

  // 一键生成运营周报配图（商汤图像模型 + 真实 KPI 提示词）
  // 异步任务模式: 提交拿 task_id -> 轮询状态 -> 完成后渲染（防网关 504）
  const generateReportImage = async () => {
    if (imgLoading) return
    const ts = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    const msgId = `img-${Date.now()}`
    setMessages(prev => [...prev, {
      role: 'agent',
      content: '正在生成运营周报配图…（商汤图像模型，基于真实 KPI 构建提示词，约 30-120 秒，网络抖动会自动重试）',
      timestamp: ts(), thinking: true, key: msgId,
    }])
    setImgLoading(true)
    const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))
    try {
      // 1) 提交任务（立即返回）
      const res = await apiPost.reportImage({})
      const taskId = res.data?.task_id
      if (!taskId) throw new Error('未返回任务 ID')
      // 2) 轮询状态（每 4 秒，上限 240 秒，含后端断连重试时间）
      let d: any = null
      for (let i = 0; i < 60; i++) {
        await sleep(4000)
        const st = await api.get(`/agents/report-image/task/${taskId}`, { timeout: 15000 })
        d = st.data
        if (d?.status === 'failed') throw new Error(d?.error || '生成失败')
        if (d?.status === 'done') break
      }
      if (!d || d.status !== 'done') throw new Error('生成超时，请稍后重试')
      // 3) 渲染结果
      const body = [
        `运营周报配图已生成（主题：${d.theme || '运营周报总览'}）`,
        '',
        `📊 真实 KPI：${d.kpi_summary || ''}`,
        `🎨 提示词：${d.prompt || ''}`,
        '',
        `![运营周报配图](${d.image_url})`,
      ].join('\n')
      setMessages(prev => prev.map(m => (m as any).key === msgId
        ? { ...m, content: body, thinking: false, timestamp: ts() }
        : m))
    } catch (e: any) {
      const msg = e?.response?.data?.detail || e?.message || '未知错误'
      setMessages(prev => prev.map(m => (m as any).key === msgId
        ? { ...m, content: `配图生成失败：${msg}`, thinking: false, timestamp: ts() }
        : m))
    } finally {
      setImgLoading(false)
    }
  }

  const askAgent = async (question: string) => {
    if (!question.trim() || asking) return
    const now = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    setMessages(prev => [...prev, { role: 'user', content: question, timestamp: now }])
    setInput('')
    setAsking(true)

    const ts = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    // 思考过程气泡: 随流式事件渐进更新, 最终被答案替换
    const thinkingId = `thinking-${Date.now()}`
    setMessages(prev => [...prev, { role: 'agent', content: '正在思考...', timestamp: ts(), thinking: true, key: thinkingId }])

    const updateThinking = (text: string) => {
      setMessages(prev => prev.map(m => (m as any).key === thinkingId ? { ...m, content: text } : m))
    }
    const replaceWithAnswer = (content: string, offline = false) => {
      setMessages(prev => prev.map(m => (m as any).key === thinkingId
        ? { ...m, content, thinking: false, offline, timestamp: ts() }
        : m))
    }

    // POST 降级重试: 流式失败或未返回结论时, 同步接口再试一次
    const postFallback = async () => {
      try {
        const res = await apiPost.agentExecute(agentKey, { query: question })
        const result = res.data?.result || {}
        const agentReply = result.final_answer || result.answer || result.response || result.summary
        replaceWithAnswer(
          typeof agentReply === 'string' ? agentReply : JSON.stringify(result, null, 2),
          res.data?.llm_enabled === false,
        )
      } catch {
        replaceWithAnswer('智能体请求失败，请稍后重试或检查网络连接。')
      }
    }

    try {
      let gotConclusion = false
      await agentExecuteStream(agentKey, { query: question }, (ev) => {
        if (ev.type === 'step') {
          const action = ev.action ? String(ev.action).split('(')[0] : ''
          updateThinking(`步骤 ${ev.index + 1}: ${action || '分析中'}…\n${ev.observation ? String(ev.observation).slice(0, 120) : ''}`)
        } else if (ev.type === 'final') {
          gotConclusion = true
          replaceWithAnswer(String(ev.answer ?? ''))
        } else if (ev.type === 'error') {
          gotConclusion = true
          replaceWithAnswer(`推理失败: ${ev.message || '未知错误'}，请重试。`)
        }
      })
      // 兜底: 流结束但未收到 final 事件 -> 自动降级 POST 重试一次
      if (!gotConclusion) await postFallback()
    } catch {
      // 流式彻底失败(网络/路由) -> 降级到 POST 重试一次
      await postFallback()
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
            <h3 style={{ color: '#00E5FF', marginBottom: 12, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>
                <RobotOutlined style={{ marginRight: 8 }} />
                智能体对话
              </span>
              <Tooltip title="基于车队真实 KPI 自动构建提示词，调用商汤图像模型生成周报封面配图">
                <Button
                  size="small"
                  ghost
                  icon={<PictureOutlined />}
                  loading={imgLoading}
                  disabled={asking}
                  onClick={generateReportImage}
                  style={{ borderColor: 'rgba(105,240,174,0.4)', color: '#69F0AE' }}
                >
                  生成周报配图
                </Button>
              </Tooltip>
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
                    {msg.thinking && (
                      <Paragraph style={{
                        margin: 0,
                        color: 'rgba(224,245,232,0.45)',
                        fontSize: 13,
                        whiteSpace: 'pre-wrap',
                      }}>
                        <Spin size="small" style={{ marginRight: 8 }} />
                        {msg.content}
                      </Paragraph>
                    )}
                    {!msg.thinking && (
                      <div style={{ color: 'rgba(224,245,232,0.9)', fontSize: 13 }}>
                        <MessageBody content={msg.content} />
                      </div>
                    )}
                    <Text style={{ fontSize: 10, color: 'rgba(224,245,232,0.25)' }}>
                      {msg.timestamp}
                      {msg.offline && (
                        <span style={{ marginLeft: 6, color: 'rgba(255,152,0,0.7)' }}>· 离线模式</span>
                      )}
                    </Text>
                  </div>
                </div>
              ))}
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
