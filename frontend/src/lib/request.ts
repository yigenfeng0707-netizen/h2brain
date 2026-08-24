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
    api.post('/react', data),
  agentExecute: (agentKey: string, data: { query: string; vehicle_plate?: string }) =>
    api.post(`/agents/${agentKey}/execute`, data, { timeout: 90000 }),
  analysisUpload: (data: FormData) =>
    api.post('/analysis/upload', data, { timeout: 120000 }),
}
