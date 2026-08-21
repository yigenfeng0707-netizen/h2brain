// 氢智行 H2Brain - 主布局（顶部品牌导航 + 侧边导航）
import { useState } from 'react'
import { Layout, Menu, Drawer, Button, Grid } from 'antd'
import { MenuOutlined } from '@ant-design/icons'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import { BRAND } from '@/lib/brand'

const { Header, Sider, Content } = Layout
const { useBreakpoint } = Grid

const NAV_ITEMS = [
  { key: '/console', label: '运营总览大屏', icon: 'H2' },
  { key: '/dispatch', label: '智能调度大屏', icon: '>' },
  { key: '/react', label: 'ReAct 决策面板', icon: '*' },
  { key: '/agents/hydrogen_opt', label: '氢耗优化 Agent', icon: 'H2' },
  { key: '/agents/route_plan', label: '路径规划 Agent', icon: 'R' },
  { key: '/agents/station_dispatch', label: '加氢站调度 Agent', icon: 'S' },
  { key: '/agents/fleet_manage', label: '车队管理 Agent', icon: 'F' },
  { key: '/agents/cost_analysis', label: '成本分析 Agent', icon: 'Y' },
  { key: '/agents/fuelcell_health', label: '燃料电池健康 Agent', icon: 'H' },
  { key: '/architecture', label: '五层架构', icon: '#' },
  { key: '/case', label: '案例数据看板', icon: '+' },
  { key: '/pricing', label: 'SaaS 定价', icon: '$' },
  { key: '/trip-analysis', label: '行程分析 Dashboard', icon: '~' },
]

function renderMenu(selectedKey: string, onNavigate: (key: string) => void) {
  return (
    <Menu
      mode="inline"
      theme="dark"
      selectedKeys={[selectedKey]}
      onClick={({ key }) => onNavigate(key)}
      style={{ background: 'transparent', borderInlineEnd: 'none' }}
      items={NAV_ITEMS.map((it) => ({
        key: it.key,
        label: (
          <span style={{ fontSize: 14 }}>
            <span style={{ marginRight: 8, color: '#69F0AE', fontWeight: 700 }}>{it.icon}</span>
            {it.label}
          </span>
        ),
      }))}
    />
  )
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const screens = useBreakpoint()
  const isDesktop = !!screens.lg
  const [drawerOpen, setDrawerOpen] = useState(false)

  const handleNavigate = (key: string) => {
    navigate(key)
    setDrawerOpen(false)
  }

  return (
    <Layout style={{ minHeight: '100vh', background: '#051811' }}>
      <Header
        style={{
          background: 'linear-gradient(90deg, #0A2E1F, #0F3D2A)',
          borderBottom: '1px solid rgba(105,240,174,0.25)',
          display: 'flex',
          alignItems: 'center',
          padding: isDesktop ? '0 24px' : '0 12px',
          gap: 8,
        }}
      >
        {!isDesktop && (
          <Button
            type="text"
            icon={<MenuOutlined style={{ color: '#69F0AE', fontSize: 20 }} />}
            onClick={() => setDrawerOpen(true)}
            aria-label="open menu"
          />
        )}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, minWidth: 0, flex: 1 }}>
          <span
            style={{
              fontSize: isDesktop ? 22 : 18,
              fontWeight: 800,
              color: '#69F0AE',
              letterSpacing: 1,
              whiteSpace: 'nowrap',
            }}
            className="h2-glow-text"
          >
            {BRAND.name} <span style={{ color: '#00C853' }}>{BRAND.enName}</span>
          </span>
          {isDesktop && (
            <span style={{ color: 'rgba(224,245,232,0.55)', fontSize: 12 }}>
              {BRAND.slogan}
            </span>
          )}
        </div>
        <span style={{ color: 'rgba(224,245,232,0.5)', fontSize: 12, whiteSpace: 'nowrap' }}>
          {isDesktop ? BRAND.track : 'IGNITE'}
        </span>
      </Header>

      <Layout>
        {isDesktop ? (
          <Sider
            width={220}
            style={{ background: '#0A2E1F', borderRight: '1px solid rgba(105,240,174,0.12)' }}
          >
            {renderMenu(location.pathname, handleNavigate)}
          </Sider>
        ) : (
          <Drawer
            placement="left"
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            width={260}
            styles={{ body: { background: '#0A2E1F', padding: 0 } }}
          >
            {renderMenu(location.pathname, handleNavigate)}
          </Drawer>
        )}
        <Content style={{ padding: isDesktop ? 16 : 8, overflow: 'auto', background: '#051811' }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
