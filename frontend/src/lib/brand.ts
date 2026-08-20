// 氢智行 H2Brain - 品牌常量
export const BRAND = {
  name: '氢智行',
  enName: 'H2Brain',
  slogan: '让每克氢都跑在刀刃上',
  track: '2026 浦发 IGNITE 未来能源黑客松 - 氢能车辆运营智能分析与决策',
  colors: {
    primary: '#00C853',
    light: '#69F0AE',
    accent: '#00E5FF',
    dark: '#0A2E1F',
  },
} as const

// 六大核心智能体
export const AGENTS = [
  { key: 'hydrogen_opt', name: '氢耗优化 Agent', icon: 'H2', metric: '百公里氢耗 -12%', core: true },
  { key: 'route_plan', name: '路径规划 Agent', icon: 'R', metric: '续航匹配率 98%+' },
  { key: 'station_dispatch', name: '加氢站调度 Agent', icon: 'S', metric: '等待时间 -60%' },
  { key: 'fleet_manage', name: '车队管理 Agent', icon: 'F', metric: '利用率 +25%' },
  { key: 'cost_analysis', name: '成本分析 Agent', icon: 'Y', metric: '运营成本 -18%' },
  { key: 'fuelcell_health', name: '燃料电池健康 Agent', icon: 'H', metric: '寿命预测准确率 95%+' },
] as const

// 五层架构
export const ARCH_LAYERS = [
  { level: 'L5', name: '用户接入层', desc: '车队管理 - 司机App - 加氢站终端 - 氢能监管平台 | IoT - 车载OBD - 北斗/高德' },
  { level: 'L4', name: '智能体服务层', desc: '系统大脑 - 六大氢能智能体协同 - 总控Agent任务编排' },
  { level: 'L3', name: '数据与检索层', desc: '氢能垂直知识库 | 车辆数字孪生 | 实时运力池 | 氢耗时序数据' },
  { level: 'L2', name: '核心技术层', desc: 'LLM | RAG | MCP协议总线 | 运筹优化 | LSTM时序预测' },
  { level: 'L1', name: '基础设施层', desc: '氢能示范区私有云 | 百车级并发 | 等保二级 | Grafana驾驶舱' },
] as const

// 大兴氢能示范区坐标
export const H2_ZONE = {
  name: '中关村(大兴)国际氢能示范区',
  lng: 116.341,
  lat: 39.727,
} as const
