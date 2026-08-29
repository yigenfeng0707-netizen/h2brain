// 氢智行 H2Brain - API 请求封装
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || '/api/v1',
  timeout: 15000,
})

export default api

// API 方法
export const apiGet = {
  health: () => api.get('/health'),
  operationsSummary: () => api.get('/operations/summary'),
  operationsVehicles: () => api.get('/operations/vehicles'),
  operationsStations: () => api.get('/operations/stations'),
  operationsPool: () => api.get('/operations/pool'),
  operationsEvents: () => api.get('/operations/events'),
  operationsTrends: () => api.get('/operations/trends'),
  dispatchVehicles: () => api.get('/dispatch/vehicles'),
  dispatchOrders: () => api.get('/dispatch/orders'),
  dispatchRecommend: () => api.get('/dispatch/recommend'),
  reactTemplates: () => api.get('/react/templates'),
  agents: () => api.get('/agents'),
  agentDetail: (key: string) => api.get(`/agents/${key}`),
  displayArchitecture: () => api.get('/display/architecture'),
  displayCase: () => api.get('/display/case'),
  displayPricing: () => api.get('/display/pricing'),
  // 真实数据分析
  analysisVehicles: () => api.get('/analysis/vehicles'),
  analysisTrips: (vehicleId: string) => api.get(`/analysis/trips/${vehicleId}`),
  analysisTripDetail: (vehicleId: string, tripId: number) =>
    api.get(`/analysis/trip/${vehicleId}/${tripId}`, { timeout: 30000 }),
  analysisBenchmark: (vehicleId: string) => api.get(`/analysis/benchmark/${vehicleId}`),
  analysisReport: (vehicleId: string, tripId: number) =>
    api.get(`/analysis/report/${vehicleId}/${tripId}`, { timeout: 30000 }),
  analysisValue: () => api.get('/analysis/value', { timeout: 30000 }),
}

export const apiPost = {
  react: (data: { scenario: string; query: string; vehicle_plate?: string }) =>
    api.post('/react', data, { timeout: 300000 }),
  agentExecute: (agentKey: string, data: { query: string; vehicle_plate?: string }) =>
    api.post(`/agents/${agentKey}/execute`, data, { timeout: 300000 }),
  analysisUpload: (data: FormData) =>
    api.post('/analysis/upload', data, { timeout: 120000 }),
  // 运营周报配图（异步任务: 提交立即返回 task_id，前端轮询状态）
  reportImage: (data: { theme?: string }) =>
    api.post('/agents/report-image', data, { timeout: 30000 }),
}

// Agent SSE 流式执行: 后端逐事件推送, 免疫网关/axios超时
export async function agentExecuteStream(
  agentKey: string,
  data: { query: string; vehicle_plate?: string },
  onEvent: (event: any) => void,
): Promise<void> {
  const base = import.meta.env.VITE_API_BASE || '/api/v1'
  const resp = await fetch(`${base}/agents/${agentKey}/execute/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!resp.ok || !resp.body) throw new Error(`stream failed: ${resp.status}`)

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() || ''
    for (const part of parts) {
      const line = part.trim()
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6)
      if (payload === '[DONE]') return
      try {
        onEvent(JSON.parse(payload))
      } catch { /* 忽略无法解析的片段 */ }
    }
  }
}
