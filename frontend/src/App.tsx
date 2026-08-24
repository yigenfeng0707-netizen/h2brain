// 氢智行 H2Brain - 应用根组件（路由配置）
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { ConfigProvider, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import MainLayout from '@/layouts/MainLayout'
import Console from '@/pages/Console'
import Dispatch from '@/pages/Dispatch'
import ReactPanel from '@/pages/ReactPanel'
import Architecture from '@/pages/Architecture'
import CaseDashboard from '@/pages/CaseDashboard'
import SaaSPricing from '@/pages/SaaSPricing'
import TripAnalysis from '@/pages/TripAnalysis'
import ValueAnalysis from '@/pages/ValueAnalysis'
import ErrorBoundary from '@/components/ErrorBoundary'
import HydrogenOptAgent from '@/pages/agents/HydrogenOptAgent'
import RouteAgent from '@/pages/agents/RouteAgent'
import StationAgent from '@/pages/agents/StationAgent'
import FleetAgent from '@/pages/agents/FleetAgent'
import CostAgent from '@/pages/agents/CostAgent'
import HealthAgent from '@/pages/agents/HealthAgent'

export default function App() {
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: theme.darkAlgorithm,
        token: {
          colorPrimary: '#00C853',
          colorInfo: '#00E5FF',
          borderRadius: 8,
        },
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route element={<MainLayout />}>
            <Route index element={<Navigate to="/console" replace />} />
            <Route path="/console" element={<Console />} />
            <Route path="/dispatch" element={<Dispatch />} />
            <Route path="/react" element={<ReactPanel />} />
            <Route path="/agents/hydrogen_opt" element={<HydrogenOptAgent />} />
            <Route path="/agents/route_plan" element={<RouteAgent />} />
            <Route path="/agents/station_dispatch" element={<StationAgent />} />
            <Route path="/agents/fleet_manage" element={<FleetAgent />} />
            <Route path="/agents/cost_analysis" element={<CostAgent />} />
            <Route path="/agents/fuelcell_health" element={<HealthAgent />} />
            <Route path="/architecture" element={<Architecture />} />
            <Route path="/case" element={<CaseDashboard />} />
            <Route path="/pricing" element={<SaaSPricing />} />
            <Route path="/trip-analysis" element={<ErrorBoundary><TripAnalysis /></ErrorBoundary>} />
            <Route path="/value-analysis" element={<ValueAnalysis />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  )
}
